// Minimal IndexedDB key/value wrapper. Two stores:
//   "ink"  – handwritten notes per page   (key: "NIV|43|3")
//   "text" – downloaded chapter text       (key: "NIV|43|3")
const DB_NAME = "margin-bible";
const STORES = ["ink", "text"];
let dbPromise;

function open() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        for (const s of STORES) if (!req.result.objectStoreNames.contains(s)) req.result.createObjectStore(s);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

function run(store, mode, fn) {
  return open().then((db) => new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const req = fn(tx.objectStore(store));
    tx.oncomplete = () => resolve(req && req.result);
    tx.onerror = () => reject(tx.error);
  }));
}

export const get = (store, key) => run(store, "readonly", (s) => s.get(key));
export const put = (store, key, value) => run(store, "readwrite", (s) => s.put(value, key));
export const del = (store, key) => run(store, "readwrite", (s) => s.delete(key));

export async function entries(store) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const out = [];
    const req = db.transaction(store).objectStore(store).openCursor();
    req.onsuccess = () => {
      const c = req.result;
      if (c) { out.push([c.key, c.value]); c.continue(); } else resolve(out);
    };
    req.onerror = () => reject(req.error);
  });
}
