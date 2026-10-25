const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/api/voiceSession.js'), 'utf8')
  .replace(/^import .*$/m, "const API_BASE_URL = 'http://localhost:8000'")
  .replace('export async function', 'async function')
function load(fetch) {
  const sandbox = { fetch, URL, AbortController, setTimeout, clearTimeout, process: { env: {} } }
  vm.createContext(sandbox)
  vm.runInContext(source + '\nthis.request = requestVoiceSession', sandbox)
  return sandbox.request
}
async function run() {
  let observed
  const request = load(async (url, options) => {
    observed = { url, options }
    return { ok: true, json: async () => ({ error_num: 0, url: 'wss://iat-api.xfyun.cn/v2/iat', app_id: 'unit-app' }) }
  })
  assert.equal((await request('iat')).app_id, 'unit-app')
  assert.equal(observed.options.credentials, 'include')
  assert.ok(observed.url.endsWith('/api/voice/session?service=iat'))
  for (const response of [
    { ok: false, payload: { error_num: 1, msg: 'not configured' } },
    { ok: true, payload: { error_num: 0, url: 'wss://attacker.example/', app_id: 'unit-app' } },
    { ok: true, payload: { error_num: 0, url: 'http://iat-api.xfyun.cn/', app_id: 'unit-app' } },
    { ok: true, payload: { error_num: 0, url: 'wss://iat-api.xfyun.cn/' } }
  ]) {
    await assert.rejects(load(async () => ({ ok: response.ok, json: async () => response.payload }))('iat'))
  }
  await assert.rejects(load(async () => { throw new Error('network unavailable') })('iat'))
  console.log('Voice session contract checks passed (6 cases).')
}
run().catch(error => { console.error(error); process.exitCode = 1 })
