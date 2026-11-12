const _IDB_NAME = 'drpiscinas-offline';
const _IDB_STORE = 'pending-visits';
const _LOCAL_CACHE_KEY = 'drp_cached_today_visits';

function _purgarVisitasViejas(visitas) {
  if (!Array.isArray(visitas)) return [];
  const hoy = new Date();
  const mesActualStr = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`;

  // Límite de los últimos 3 días (formato YYYY-MM-DD local)
  const hace3Dias = new Date(hoy);
  hace3Dias.setDate(hoy.getDate() - 3);
  const y = hace3Dias.getFullYear();
  const m = String(hace3Dias.getMonth() + 1).padStart(2, '0');
  const d = String(hace3Dias.getDate()).padStart(2, '0');
  const limite3DiasStr = `${y}-${m}-${d}`;

  return visitas.filter(v => {
    if (!v || !v.fecha) return false;
    // Si es del mes en curso, se conserva
    if (v.fecha.startsWith(mesActualStr)) return true;
    // Si es de un mes anterior, solo se conserva si cae dentro de los últimos 3 días
    return v.fecha >= limite3DiasStr;
  });
}

function getCachedTodayVisits() {
  try {
    const raw = localStorage.getItem(_LOCAL_CACHE_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    const purgadas = _purgarVisitasViejas(list);
    if (purgadas.length !== list.length) {
      localStorage.setItem(_LOCAL_CACHE_KEY, JSON.stringify(purgadas));
    }
    return purgadas;
  } catch (e) {
    return [];
  }
}

function mergeCachedTodayVisits(nuevasVisitas) {
  try {
    const actuales = getCachedTodayVisits();
    const map = new Map();
    // Indexar visitas ya existentes
    actuales.forEach(v => {
      if (v && v.casa_id && v.fecha) {
        map.set(`${String(v.casa_id)}_${v.fecha}`, v);
      }
    });
    // Agregar o actualizar con nuevas visitas
    if (Array.isArray(nuevasVisitas)) {
      nuevasVisitas.forEach(v => {
        if (v && v.casa_id && v.fecha) {
          map.set(`${String(v.casa_id)}_${v.fecha}`, v);
        }
      });
    }
    const unificadas = _purgarVisitasViejas(Array.from(map.values()));
    localStorage.setItem(_LOCAL_CACHE_KEY, JSON.stringify(unificadas));
    return unificadas;
  } catch (e) {
    console.warn('Error unificando cache local de visitas:', e);
    return getCachedTodayVisits();
  }
}

function setCachedTodayVisits(visitas) {
  return mergeCachedTodayVisits(visitas);
}

function getCachedTodayVisit(casaId, fecha) {
  if (!casaId || !fecha) return null;
  const list = getCachedTodayVisits();
  return list.find(v => String(v.casa_id) === String(casaId) && v.fecha === fecha) || null;
}

async function fetchAndCacheTodayVisits() {
  if (!navigator.onLine) return getCachedTodayVisits();
  try {
    const r = await fetch('/visits/api/recent-today', { cache: 'no-store' });
    if (!r.ok) return getCachedTodayVisits();
    const data = await r.json();
    if (data && data.ok && Array.isArray(data.visitas)) {
      mergeCachedTodayVisits(data.visitas);
      return data.visitas;
    }
  } catch (err) {
    console.warn('No se pudo actualizar el cache de visitas del día:', err);
  }
  return getCachedTodayVisits();
}

function _openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(_IDB_NAME, 1);
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore(_IDB_STORE, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror = e => reject(e.target.error);
  });
}

async function savePendingVisit(data) {
  const db = await _openDB();
  const idbPromise = new Promise((resolve, reject) => {
    const tx = db.transaction(_IDB_STORE, 'readwrite');
    const req = tx.objectStore(_IDB_STORE).add({ ...data, savedAt: Date.now() });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  const res = await idbPromise;

  // Registrar inmediatamente en la caché local de chequeo rápido para advertir duplicados en el acto
  try {
    const prodsTxt = (data.productos || []).map(p => `${p.cantidad} ${p.nombre || p.product_id}`).join(', ') || 'Sin productos';
    mergeCachedTodayVisits([{
      id: 'offline_' + (data.client_uuid || Date.now()),
      casa_id: String(data.casa_id),
      casa_nombre: data.casa_nombre || `Casa #${data.casa_id}`,
      fecha: data.fecha,
      usuario: 'vos (guardada sin conexión)',
      productos: prodsTxt,
      observaciones: data.observaciones || ''
    }]);
  } catch (err) {
    console.warn('Error registrando en caché local inmediata:', err);
  }

  return res;
}

async function getPendingVisits() {
  const db = await _openDB();
  return new Promise((resolve, reject) => {
    const req = db.transaction(_IDB_STORE, 'readonly').objectStore(_IDB_STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function deletePendingVisit(id) {
  if (id === undefined || id === null) return;
  const db = await _openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(_IDB_STORE, 'readwrite');
    const store = tx.objectStore(_IDB_STORE);
    store.delete(id);
    if (typeof id === 'string' && !isNaN(Number(id))) store.delete(Number(id));
    if (typeof id === 'number') store.delete(String(id));
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Transaction aborted'));
  });
}

async function clearPendingVisits() {
  const db = await _openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(_IDB_STORE, 'readwrite');
    tx.objectStore(_IDB_STORE).clear();
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

let _syncInProgress = false;

async function syncPendingVisits() {
  if (_syncInProgress) return { synced: 0, errors: 0, dobles: 0, doblesList: [], total: 0, skipped: true };
  _syncInProgress = true;
  try {
    const pending = await getPendingVisits();
    if (!pending.length) return { synced: 0, errors: 0, dobles: 0, doblesList: [], total: 0 };
    let synced = 0, errors = 0, dobles = 0;
    const doblesList = [];
    for (const item of pending) {
      try {
        const csrfToken = document.querySelector('[name=csrf_token]')?.value || item.csrf_token || '';
        const r = await fetch('/visits/sync-offline', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
          body: JSON.stringify(item)
        });
        const json = await r.json().catch(() => ({}));
        if (r.ok && json.ok) {
          await deletePendingVisit(item.id);
          synced++;
          if (json.doble_visita) {
            dobles++;
            doblesList.push(item.casa_nombre || `Casa #${item.casa_id}`);
          }
        } else {
          errors++;
        }
      } catch {
        errors++;
      }
    }
    if (navigator.onLine) {
      await fetchAndCacheTodayVisits().catch(() => {});
    }
    return { synced, errors, dobles, doblesList, total: pending.length };
  } finally {
    _syncInProgress = false;
  }
}

// Auto-actualizar caché de visitas al cargar y al volver a tener conexión
if (typeof window !== 'undefined') {
  if (navigator.onLine) {
    fetchAndCacheTodayVisits().catch(() => {});
  }
  window.addEventListener('online', () => {
    fetchAndCacheTodayVisits().catch(() => {});
  });
}
