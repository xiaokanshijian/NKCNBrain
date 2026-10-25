const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const babel = require('@babel/core')

const base = path.join(__dirname, '..')
function load(relative, imports, globals = {}) {
  let source = fs.readFileSync(path.join(base, relative), 'utf8')
  if (relative.endsWith('.vue')) source = source.match(/<script>([\s\S]*?)<\/script>/)[1]
  const compiled = babel.transformSync(source, {
    babelrc: false, configFile: false, plugins: ['@babel/plugin-transform-modules-commonjs']
  }).code
  const exports = {}
  const context = { exports, module: { exports }, require: name => imports[name] || {},
    console: { log() {} }, ...globals }
  vm.runInNewContext(compiled, context, { filename: relative })
  return context.module.exports
}
function storage(initial = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: key => data.has(key) ? data.get(key) : null,
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: key => data.delete(key)
  }
}
let cases = 0
async function check(name, run) {
  await run()
  cases++
  console.log('PASS ' + name)
}
async function main() {
  await check('login sends CSRF-protected POST and verifies session cookie', async () => {
    const calls = []
    const auth = load('src/api/authSession.js', { '@/utils/request': async config => {
      calls.push(config)
      if (config.url === '/api/auth/csrf') return { csrfToken: 'unit-csrf' }
      return { error_num: 0, msg: 'success', name: 'unit-user' }
    } })
    const result = await auth.loginSession('unit-user', 'unit-password', 'simple')
    assert.equal(result.name, 'unit-user')
    assert.equal(calls.length, 3)
    assert.ok(calls.every(c => c.withCredentials === true))
    assert.equal(calls[1].url, '/api/verify_user')
    assert.equal(calls[1].method, 'post')
    assert.equal(calls[1].data.password, 'unit-password')
    assert.equal(calls[1].params, undefined)
    assert.equal(calls[1].headers['X-CSRFToken'], 'unit-csrf')
    assert.equal(calls[2].url, '/api/auth/session')
  })
  await check('blocked cookies cannot look like successful login', async () => {
    const auth = load('src/api/authSession.js', { '@/utils/request': async config => {
      if (config.url === '/api/auth/csrf') return { csrfToken: 'unit-csrf' }
      if (config.url === '/api/auth/session') throw new Error('401 no cookie')
      return { error_num: 0, msg: 'success', name: 'unit-user' }
    } })
    await assert.rejects(auth.loginSession('unit-user', 'unit-password', 'full'))
  })
  await check('session identity must match authenticated login response', async () => {
    const auth = load('src/api/authSession.js', { '@/utils/request': async config => {
      if (config.url === '/api/auth/csrf') return { csrfToken: 'unit-csrf' }
      return { error_num: 0, msg: 'success', name: config.method === 'post' ? 'unit-user' : 'other-user' }
    } })
    await assert.rejects(auth.loginSession('unit-user', 'unit-password', 'full'))
  })
  await check('invalid password retains existing response contract', async () => {
    let calls = 0
    const auth = load('src/api/authSession.js', { '@/utils/request': async config => {
      calls++
      return config.method === 'get' ? { csrfToken: 'unit-csrf' } : { error_num: 0, msg: 'Invalid password', name: '0' }
    } })
    assert.equal((await auth.loginSession('unit-user', 'wrong', 'full')).name, '0')
    assert.equal(calls, 2)
  })
  await check('logout fetches a fresh CSRF token after login rotation', async () => {
    const calls = []
    const auth = load('src/api/authSession.js', { '@/utils/request': async config => {
      calls.push(config)
      return config.method === 'get' ? { csrfToken: 'rotated-csrf' } : { error_num: 0 }
    } })
    await auth.logoutSession()
    assert.equal(calls[1].url, '/api/auth/logout')
    assert.equal(calls[1].headers['X-CSRFToken'], 'rotated-csrf')
  })
  const navigation = load('src/utils/authNavigation.js', {}).logoutBeforeNavigation
  await check('leaving a notebook does not end the account session', async () => {
    let called = false
    const result = await navigation({ path: '/home' }, { path: '/main', matched: [{}] },
      async () => { called = true }, storage())
    assert.equal(result, false)
    assert.equal(called, false)
  })
  await check('returning to login waits for logout then clears local identity', async () => {
    const local = storage({ userId: 'unit-user', password: 'old-password', originRealName: 'unit-user' })
    let revoked = false
    await navigation({ path: '/' }, { path: '/simple', matched: [{}] },
      async () => { assert.equal(local.getItem('userId'), 'unit-user'); revoked = true }, local)
    assert.equal(revoked, true)
    assert.equal(local.getItem('userId'), null)
    assert.equal(local.getItem('password'), null)
    assert.equal(local.getItem('originRealName'), 'unit-user')
  })
  await check('logout failure does not falsely clear the local login', async () => {
    const local = storage({ userId: 'unit-user' })
    await assert.rejects(navigation({ path: '/' }, { path: '/home', matched: [{}] },
      async () => { throw new Error('network failure') }, local))
    assert.equal(local.getItem('userId'), 'unit-user')
  })
  await check('automatic login cannot trust remembered username or password', async () => {
    const local = storage({ originRealName: 'admin', userId: 'admin', password: 'cached-password' })
    const routes = []
    const component = load('src/views/login.vue', {
      '@/api/authSession': { getLoginSession: async () => { throw new Error('401 expired') } },
      '@/router': { push: route => routes.push(route) }
    }, { localStorage: local }).default
    await component.methods.quickLogin.call({ loginForm: {}, $message: { success() {} } })
    assert.equal(routes.length, 0)
    assert.equal(local.getItem('userId'), null)
    assert.equal(local.getItem('password'), null)
  })
  await check('automatic login restores identity and mode from server session', async () => {
    const local = storage({ originRealName: 'stale-user' })
    const routes = []
    const component = load('src/views/login.vue', {
      '@/api/authSession': { getLoginSession: async () => ({
        error_num: 0, name: 'unit-user', coacherName: 'unit-coach', level: 'GM', choose: 2
      }) },
      '@/router': { push: route => routes.push(route) }
    }, { localStorage: local }).default
    const page = { loginForm: {}, $message: { success() {} } }
    await component.methods.quickLogin.call(page)
    assert.equal(local.getItem('userId'), 'unit-user')
    assert.equal(page.uiMode, 'minimal')
    assert.equal(routes[0], '/minimal')
  })
  await check('global navigation guard cancels navigation on failed server logout', async () => {
    const nextCalls = []
    const component = load('src/App.vue', {
      '@/api/authSession': { logoutSession: async () => { throw new Error('offline') } },
      '@/utils/authNavigation': { logoutBeforeNavigation: navigation }
    }, { localStorage: storage() }).default
    await component.methods.beforeRouteChange.call({ $message: { error() {} } },
      { path: '/' }, { path: '/minimal', matched: [{}] }, value => nextCalls.push(value))
    assert.equal(nextCalls.length, 1)
    assert.equal(nextCalls[0], false)
  })
  console.log('Authentication frontend checks passed (' + cases + ' cases).')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
