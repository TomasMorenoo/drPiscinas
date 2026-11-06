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
  const db = await _openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(_IDB_STORE, 'readwrite');
    tx.objectStore(_IDB_STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function syncPendingVisits() {
  const pending = await getPendingVisits();
  if (!pending.length) return { synced: 0, errors: 0, total: 0 };
  let synced = 0, errors = 0;
  for (const item of pending) {
    try {
      const r = await fetch('/visits/sync-offline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': item.csrf_token },
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
}
