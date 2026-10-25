import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { parse } = require('@babel/parser')

async function component(file) {
  const text = await readFile(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const script = text.match(/<script>([\s\S]*?)<\/script>/)[1]
  const tree = parse(script, { sourceType: 'module' })
  const definition = tree.program.body.find(n => n.type === 'ExportDefaultDeclaration').declaration
  return (section, names, globals = {}) => {
    const props = definition.properties.find(n => n.key?.name === section).value.properties
    return vm.runInNewContext(`({${names.map(name => {
      const node = props.find(n => n.key.name === name)
      assert.ok(node, name)
      return script.slice(node.start, node.end)
    }).join(',')}})`, globals)
  }
}

const main = await component('views/mainPage.vue')
const panel = await component('components/fileWindow/HomeworkGradingPanel.vue')
const selector = await component('components/fileWindow/NotebookSkillSelector.vue')
const plain = value => JSON.parse(JSON.stringify(value))
let cases = 0
for (const action of ['cancel', 'off', 'on', 'switch', 'busy']) {
  let book = 'book-a'
  const calls = []
  const globals = { localStorage: { getItem: () => book }, console,
    startHomeworkFeedback: async data => { calls.push(data); return { error_num: 0, task_id: 'task', analysis_id: 'homework_x', analysis_type: 'homework_grading' } },
    startImageUnderstanding: () => assert.fail('不能启动普通理解'), startCIAnalysis: () => assert.fail('不能误分流') }
  const methods = main('methods', ['_startCIAnalysis', 'finishCISkillStart'], globals)
  const instance = { ...methods, ciRunningTask: null, ciSkillPending: null, sceneName: '测试场景',
    _ciSelectedContextDocs: () => ['methods.zip'], _startCIPoll() {}, _showCIProgressNotification() {},
    $message: { warning() {}, error: message => assert.fail(message) } }
  const pending = instance._startCIAnalysis(['fixture.pdf'], 'single', 'book-a', { requestedAction: 'grading' })
  assert.ok(instance.ciSkillPending)
  assert.equal(calls.length, 0)
  await instance._startCIAnalysis(['second.pdf'], 'single', 'book-a', { requestedAction: 'grading' })
  assert.equal(instance.ciSkillPending.filename, 'fixture.pdf')
  if (action === 'switch') book = 'book-b'
  if (action === 'busy') instance.ciRunningTask = { completed: false }
  instance.finishCISkillStart(action === 'cancel' ? null : { enabled: action === 'on', names: action === 'on' ? ['method'] : [] })
  await pending
  assert.equal(calls.length, ['off', 'on'].includes(action) ? 1 : 0)
  if (calls.length) {
    assert.deepEqual(plain(calls[0].files), ['fixture.pdf'])
    assert.deepEqual(plain(calls[0].notebook_skill_selection), { enabled: action === 'on', names: action === 'on' ? ['method'] : [] })
    assert.equal(calls[0].username, 'book-a')
  }
  cases++
}

for (const replace of [false, true]) {
  const events = []
  const methods = panel('methods', ['submitRerun'], { console,
    feedbackMaterialSettings: () => assert.fail('仅更换 Skill 不读取当前材料或内部规则') })
  await methods.submitRerun.call({ activeAnalysisId: 'homework_x', activeResult: { manifest: { selected_files: ['fixture.pdf'] } },
    replaceNotebookSkills: replace, notebookSkillValid: true, notebookSkillSelection: { enabled: true, names: ['method'] },
    needsFullRecompute: false, selectedRerunStage: replace ? 'all' : 'grading', selectedRerunSessionIds: ['session1'],
    preprocessModeChanged: false, refreshConfiguration: false, rerunSessions: [{}],
    selectedPreprocessMode: 'off', redBlueReady: true, useRedBlueFeedback: false,
    $emit: (event, data) => events.push([event, plain(data)]) })
  assert.equal(events.length, 1)
  const data = events[0][1]
  assert.equal(Boolean(data.fullRecompute), replace)
  assert.equal('notebookSkillSelection' in data, replace)
  assert.equal('sessionIds' in data, !replace)
  cases++
}

const loads = []
const loadMethods = selector('methods', ['load'], {
  listNotebookSkills: () => new Promise((resolve, reject) => loads.push({ resolve, reject })),
})
const instance = { sequence: 0, username: 'book-a' }
const first = loadMethods.load.call(instance)
instance.username = 'book-b'
const second = loadMethods.load.call(instance)
loads[1].resolve({ error_num: 0, skills: [
  { name: 'valid', enabled: true, pack_zip: 'b.zip' },
  { name: 'disabled', enabled: false, pack_zip: 'b.zip' },
  { name: 'orphan', enabled: true, orphaned: true, pack_zip: 'b.zip' },
  { name: 'missing', enabled: true, missing: true, pack_zip: 'b.zip' },
  { name: 'notebook-hub', enabled: true, source_doc: 'b.pdf' },
] })
await second
loads[0].resolve({ error_num: 0, skills: [{ name: 'late-a', enabled: true, pack_zip: 'a.zip' }] })
await first
assert.deepEqual(plain(instance.items.map(item => item.name)), ['valid'])
cases++
const failed = loadMethods.load.call(instance)
loads[2].reject(new Error('测试网络错误'))
await failed
assert.equal(instance.error, '测试网络错误')
const valid = selector('computed', ['valid']).valid
assert.equal(valid.call({ ...instance, modelValue: { enabled: true, names: ['valid'] }, selectedItems: [] }), false)
assert.equal(valid.call({ ...instance, modelValue: { enabled: false, names: [] } }), true)
cases++
console.log(`${cases} notebook Skill interaction groups passed`)
