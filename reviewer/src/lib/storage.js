import { openDB } from 'idb'

const DB_NAME = 'continuous-grading-reviewer'
const DB_VERSION = 1

async function database() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('datasets')) {
        db.createObjectStore('datasets', { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains('files')) {
        const files = db.createObjectStore('files', { keyPath: 'storageKey' })
        files.createIndex('datasetId', 'datasetId')
      }
    },
  })
}

export async function listDatasets() {
  return (await database()).getAll('datasets')
}

export async function saveDataset(dataset, files) {
  const db = await database()
  const tx = db.transaction(['datasets', 'files'], 'readwrite')
  await tx.objectStore('datasets').put(dataset)
  for (const file of files) await tx.objectStore('files').put(file)
  await tx.done
}

export async function renameDataset(id, name) {
  const db = await database()
  const dataset = await db.get('datasets', id)
  if (!dataset) return null
  dataset.name = name
  dataset.runs = (dataset.runs || []).map(run => ({ ...run, name }))
  await db.put('datasets', dataset)
  return dataset
}

export async function deleteDataset(id) {
  const db = await database()
  const tx = db.transaction(['datasets', 'files'], 'readwrite')
  const index = tx.objectStore('files').index('datasetId')
  let cursor = await index.openCursor(IDBKeyRange.only(id))
  while (cursor) {
    await cursor.delete()
    cursor = await cursor.continue()
  }
  await tx.objectStore('datasets').delete(id)
  await tx.done
}

export async function getStoredFile(storageKey) {
  return (await database()).get('files', storageKey)
}

export async function requestPersistentStorage() {
  if (!navigator.storage?.persist) return false
  return navigator.storage.persist()
}

export async function storageEstimate() {
  if (!navigator.storage?.estimate) return { usage: 0, quota: 0 }
  return navigator.storage.estimate()
}
