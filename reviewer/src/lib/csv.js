import Papa from 'papaparse'

export function decodeTextBuffer(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    try {
      return new TextDecoder('gb18030').decode(bytes)
    } catch {
      return new TextDecoder('utf-8').decode(bytes)
    }
  }
}

export function parseCsvText(text) {
  const result = Papa.parse(text, {
    header: true,
    skipEmptyLines: 'greedy',
  })
  return {
    rows: result.data,
    fields: result.meta.fields || [],
    errors: result.errors || [],
  }
}
