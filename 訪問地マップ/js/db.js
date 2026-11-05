// db.js — IndexedDB データ層 (Dexie.js)
const db = new Dexie('VisitedPlacesDB');

db.version(1).stores({
  pins: '++id, lat, lng, title, createdAt',
});

const PinDB = {
  async add(pinData) {
    const id = await db.pins.add({
      lat: pinData.lat,
      lng: pinData.lng,
      title: pinData.title,
      memo: pinData.memo || '',
      photoBlob: pinData.photoBlob || null,
      createdAt: new Date().toISOString(),
    });
    return id;
  },

  async getAll() {
    return await db.pins.toArray();
  },

  async getById(id) {
    return await db.pins.get(id);
  },

  async delete(id) {
    await db.pins.delete(id);
  },

  async update(id, changes) {
    await db.pins.update(id, changes);
  },
};
