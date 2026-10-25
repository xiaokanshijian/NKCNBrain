import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

// Load the actual browser ES module without changing the project's module configuration.
const source = await readFile(new URL('../src/utils/homeworkEvidence.js', import.meta.url), 'utf8')
const { resolveHomeworkEvidencePage: resolve } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
const pages = [
  { page: 3, questions: [{ id: '3-1' }, { id: '1' }] },
  { page: 10, questions: [{ id: '10-1' }, { id: '1' }] },
  { page: 35, questions: [{ id: '六-2' }] }
]
for (const [ref, expected] of [
  ['p3:3-1', 0], ['p10:10-1', 1], ['p35:六-2', 2],
  ['3-1', 0], ['六-2', 2], ['1', -1], ['3', -1],
  ['p99:1', -1], ['p3:missing', -1], ['3garbage', -1],
  ['', -1], [null, -1], ['p3:', -1]
]) assert.equal(resolve(ref, pages), expected, String(ref))
assert.equal(resolve('p3:1', [{ page: 3, questions: [{ id: '1' }, { id: '1' }] }]), -1)
assert.equal(resolve('p3:1', []), -1)
console.log('15 evidence resolution checks passed')
