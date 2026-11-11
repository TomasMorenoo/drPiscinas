const _IDB_NAME = 'drpiscinas-offline';
const _IDB_STORE = 'pending-visits';

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
  return new Promise((resolve, reject) => {
    const tx = db.transaction(_IDB_STORE, 'readwrite');
    const req = tx.objectStore(_IDB_STORE).add({ ...data, savedAt: Date.now() });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
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
  if (_syncInProgress) return { synced: 0, errors: 0, total: 0, skipped: true };
  _syncInProgress = true;
  try {
    const pending = await getPendingVisits();
    if (!pending.length) return { synced: 0, errors: 0, total: 0 };
    let synced = 0, errors = 0;
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
        } else {
          errors++;
        }
      } catch {
        errors++;
      }
    }
    return { synced, errors, total: pending.length };
  } finally {
    _syncInProgress = false;
  }
}
