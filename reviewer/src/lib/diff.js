import { diffLines } from 'diff'

function normalizeLeaf(value) {
  if (value === undefined) return undefined
  if (value === null) return null
  if (typeof value === 'object') return JSON.stringify(value)
  return value
}

export function flattenObject(value, prefix = '', output = {}) {
  if (Array.isArray(value)) {
    if (!value.length && prefix) output[prefix] = '[]'
    value.forEach((item, index) => flattenObject(item, `${prefix}[${index}]`, output))
    return output
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
    if (!entries.length && prefix) output[prefix] = '{}'
    entries.forEach(([key, item]) => flattenObject(item, prefix ? `${prefix}.${key}` : key, output))
    return output
  }
  if (prefix) output[prefix] = normalizeLeaf(value)
  return output
}

export function diffObjects(before, after) {
  const left = flattenObject(before || {})
  const right = flattenObject(after || {})
  return Array.from(new Set([...Object.keys(left), ...Object.keys(right)]))
    .sort((a, b) => a.localeCompare(b, 'zh-CN', { numeric: true }))
    .filter(path => !Object.is(left[path], right[path]))
    .map(path => ({
      path,
      before: left[path],
      after: right[path],
      type: !(path in left) ? 'added' : !(path in right) ? 'removed' : 'changed',
    }))
}

export function diffText(before = '', after = '') {
  return diffLines(String(before), String(after)).map(part => ({
    value: part.value,
    type: part.added ? 'added' : part.removed ? 'removed' : 'same',
  }))
}
