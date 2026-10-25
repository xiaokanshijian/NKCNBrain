import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

// 执行真实组件方法，使用可控请求与时钟复现乱序，不启动后端或模型。
const require = createRequire(import.meta.url)
const { parse: parseVue } = require('@vue/compiler-sfc')
const { parse } = require('@babel/parser')
const vue = await readFile(new URL('../src/views/mainPage.vue', import.meta.url), 'utf8')
const script = parseVue(vue).descriptor.script.content
const ast = parse(script, { sourceType: 'module' })
const component = ast.program.body.find(node => node.type === 'ExportDefaultDeclaration').declaration
const methods = component.properties.find(node => node.key?.name === 'methods').value.properties
const names = ['_startCIPoll', '_pollCIProgress', 'clearCIPollTimer', '_stopCIPollTimer',
  '_loadCIResult', '_loadCIHomeworkVersions', '_rememberCIGradingTask', '_restoreCIGradingTask',
  '_resumeCIGradingTask', '_ciConnectionFailure', 'reconnectCIGradingTask',
  '_loadCIGradingTaskResult', 'reloadCIGradingResult', '_resetCIState', 'handleCloseContinuousImagePanel']

function fixture () {
  let timerId = 0
  const timers = new Map()
  const requests = []
  const results = []
  const errors = []
  const storage = new Map()
  const deps = {
    getCIProgress: taskId => new Promise((resolve, reject) => requests.push({ taskId, resolve, reject })),
    getCIResult: payload => new Promise(resolve => results.push(Object.assign(resolve, { payload }))),
    listCIHomeworkVersions: async () => ({ error_num: 0, versions: [] }),
    queryCIAnalyses: async () => ({ error_num: 0, singles: [], groups: [] }),
    setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId },
    clearTimeout: id => timers.delete(id),
    localStorage: { getItem: () => 'synthetic-user' },
    sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key) },
    console: { error: (...args) => errors.push(args) }
  }
  const ctx = {
    ciPollTimer: null, ciPollGeneration: 0, ciPollInFlightGeneration: null,
    ciRunningTask: { task_id: 'a', completed: false }, ciBatchSketchR: { running: false },
    ciSuppressOpenCIPanelOnComplete: true, ciSuppressAutoOpenWorkArea: true,
    ciHomeworkPendingPageView: '', ciHomeworkRunId: '', ciActiveResult: null,
    ciActiveAnalysisId: '', ciResultGeneration: 0, ciResultTarget: null, ciResultRetry: null, ciPollFailures: 0,
    _formatCIProgressSection: value => value, _closeCIProgressNotification () {},
    _showCIProgressNotification () {},
    $message: { error: message => errors.push(message), info () {}, warning () {} }
  }
  for (const name of names) {
    const node = methods.find(node => node.key?.name === name)
    assert(node, name)
    const method = script.slice(node.start, node.end)
    const callable = node.async ? method.replace(/^async /, 'async function ') : `function ${method}`
    ctx[name] = new Function(...Object.keys(deps), `return ${callable}`)(...Object.values(deps)).bind(ctx)
  }
  const tick = (delay = 2000) => {
    const entry = [...timers].find(([, timer]) => timer.delay === delay)
    assert(entry, `timer ${delay} must exist`)
    timers.delete(entry[0])
    return entry[1].fn()
  }
  return { ctx, requests, results, timers, errors, tick, storage }
}
const done = { error_num: 0, completed: true, status: 'completed', error: '', current_section: '完成' }
const running = { ...done, completed: false, status: 'running', current_section: '处理中' }

{
  const { ctx, requests, timers, tick } = fixture()
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const pending = tick()
  assert.equal(timers.size, 0, '请求期间不安排下一次轮询')
  await ctx._pollCIProgress('a', 'analysis-a', 'u')
  assert.equal(requests.length, 1, '同代次只能有一个请求')
  requests[0].resolve(done)
  await pending
  await ctx._pollCIProgress('a', 'analysis-a', 'u')
  assert.equal(requests.length, 1, '终态不再查询')
  assert.equal(ctx.ciRunningTask.completed, true)
  assert.equal(timers.size, 0)
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const old = tick()
  ctx.ciRunningTask = { task_id: 'b', completed: false }
  ctx._startCIPoll('b', 'analysis-b', 'u')
  const current = tick()
  requests[1].resolve(done)
  await current
  requests[0].resolve(running)
  await old
  assert.equal(ctx.ciRunningTask.task_id, 'b')
  assert.equal(ctx.ciRunningTask.status, 'completed')
  assert.equal(timers.size, 0, '迟到响应不能恢复轮询或运行态')
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const first = tick()
  requests[0].reject(new Error('synthetic connection lost'))
  await first
  assert.equal(ctx.ciRunningTask.error, undefined, '网络失联不是批改失败')
  assert.match(ctx.ciRunningTask.connection_error, /正在重试/)
  assert.equal(timers.size, 1)
  const second = tick()
  requests[1].resolve(done)
  await second
  assert.equal(ctx.ciRunningTask.connection_error, '')
  assert.equal(ctx.ciRunningTask.completed, true)
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const pending = tick()
  requests[0].resolve({ ...done, error: 'synthetic failed', status: 'failed' })
  await pending
  assert.equal(ctx.ciRunningTask.error, 'synthetic failed')
  assert.equal(timers.size, 0)
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const pending = tick()
  const before = ctx.ciRunningTask
  ctx.clearCIPollTimer()
  requests[0].resolve(done)
  await pending
  assert.equal(ctx.ciRunningTask, before, '销毁或取消订阅后的返回无副作用')
  assert.equal(timers.size, 0)
}
{
  const { ctx, requests, results, tick } = fixture()
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const pending = tick()
  requests[0].resolve(done)
  await Promise.resolve()
  assert.equal(results.length, 1)
  ctx.ciRunningTask = { task_id: 'b', completed: false }
  ctx._startCIPoll('b', 'analysis-b', 'u')
  results[0]({ error_num: 0, analysis_type: 'homework_grading', run_id: 'old' })
  await pending
  assert.equal(ctx.ciActiveResult, null, '旧任务结果不能覆盖新任务')
  assert.equal(ctx.ciRunningTask.task_id, 'b')
}
{
  const { ctx, requests, results, timers, tick } = fixture()
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx._startCIPoll('a', 'analysis-a', 'u')
  const pending = tick()
  requests[0].resolve(done)
  await Promise.resolve()
  results[0]({ error_num: 0, analysis_type: 'homework_grading', run_id: 'current', manifest: { selected_files: [] } })
  await pending
  assert.equal(ctx.ciHomeworkRunId, 'current')
  assert.equal(ctx.ciRunningTask, null)
  assert([...timers.values()].some(timer => timer.delay === 800))
  ctx.ciRunningTask = { task_id: 'b', completed: false }
  ctx._startCIPoll('b', 'analysis-b', 'u')
  tick(800)
  assert.equal(ctx.showContinuousImagePanel, undefined, '旧完成通知不得打开新任务面板')
}
{
  const panel = await readFile(new URL('../src/components/fileWindow/HomeworkGradingPanel.vue', import.meta.url), 'utf8')
  const panelScript = parseVue(panel).descriptor.script.content
  const definition = parse(panelScript, { sourceType: 'module' }).program.body.find(node => node.type === 'ExportDefaultDeclaration').declaration
  const computed = definition.properties.find(node => node.key?.name === 'computed').value.properties
  const warning = computed.find(node => node.key?.name === 'checkWarning')
  const readWarning = new Function(`return function ${panelScript.slice(warning.start, warning.end)}`)()
  assert.equal(readWarning.call({ manifest: {} }), '', '旧结果不伪造检查失败')
  assert.equal(readWarning.call({ manifest: { hallucination: { status: 'ready' } } }), '')
  assert.match(readWarning.call({ manifest: { hallucination: { status: 'failed' } } }), /人工核实/)
  assert.match(readWarning.call({ manifest: { rule_profile: { status: 'failed' } } }), /辅助检查未完成/)
}
console.log('7 CI polling scenarios and grading warning states passed (actual Vue methods)')

const gradingTask = { task_id: 'ci_task_a', analysis_id: 'homework_a', run_id: 'p03_a',
  workspace: 'book-a', analysis_type: 'homework_grading', task_kind: 'homework_grading', completed: false }
const gradingDone = { ...done, ...gradingTask, completed: true, status: 'completed',
  completion: { status: 'incomplete', report_usable: true, message: '批改结果可用，质量评分待补。' } }
const savedResult = (id = 'homework_a') => ({ error_num: 0, analysis_id: id, run_id: 'current',
  analysis_type: 'homework_grading', manifest: { username: 'book-a', selected_files: [] } })
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }

{
  const { ctx, results } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  const pending = ctx._loadCIResult('homework_b', 'book-b', 'current')
  results[0](savedResult('homework_b'))
  await pending
  assert.equal(ctx.ciRunningTask.task_id, 'ci_task_a', '查看B不能删除A任务')
  assert.equal(ctx.ciActiveAnalysisId, 'homework_b')
  ctx.handleCloseContinuousImagePanel()
  assert.equal(ctx.ciRunningTask.task_id, 'ci_task_a', '关闭面板保留任务')
  ctx._resetCIState()
  assert.equal(ctx.ciRunningTask.task_id, 'ci_task_a', '查看入口重置只清展示')
}
{
  const { ctx, requests, results, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx.ciActiveAnalysisId = 'homework_b'
  ctx.ciActiveResult = savedResult('homework_b')
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  const pending = tick()
  requests[0].resolve(gradingDone)
  await pending
  assert.equal(results.length, 0, 'A完成时不抢占B结果')
  assert.equal(ctx.ciActiveAnalysisId, 'homework_b')
  assert.equal(ctx.ciRunningTask.completion.status, 'incomplete')
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  for (const [i, delay] of [2000, 2000, 4000, 8000, 15000].entries()) {
    const pending = tick(delay)
    requests[i].resolve({ error_num: 1, retryable: true, msg: 'temporary recovery read failure' })
    await pending
    assert.equal(ctx.ciRunningTask.completed, false)
    assert(!ctx.ciRunningTask.error, '查询业务错误不能变成任务错误')
  }
  assert.equal(timers.size, 0)
  assert.equal(ctx.ciRunningTask.connection_paused, true)
  ctx.reconnectCIGradingTask()
  const pending = tick()
  requests[5].resolve(gradingDone)
  await pending
  assert.equal(ctx.ciRunningTask.completed, true)
  assert.equal(ctx.ciRunningTask.connection_paused, false)
}
{
  const { ctx, requests, timers, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  const pending = tick()
  requests[0].resolve({ error_num: 1, retryable: false, error_code: 'task_not_found', msg: '任务不存在' })
  await pending
  assert.equal(timers.size, 0)
  assert.equal(ctx.ciRunningTask.completed, false)
  assert.equal(ctx.ciRunningTask.connection_paused, true)
}
{
  const { ctx, storage, requests, tick } = fixture()
  ctx.ciRunningTask = null
  storage.set('nkcn.ci.gradingTask.v1', JSON.stringify({ ...gradingTask, owner: 'synthetic-user' }))
  ctx._restoreCIGradingTask()
  assert.equal(ctx.ciRunningTask.workspace, 'book-a', '刷新后保留任务原工作区')
  const pending = tick()
  requests[0].resolve({ ...gradingDone, completed: false, status: 'running' })
  await pending
  assert.equal(ctx.ciRunningTask.task_id, 'ci_task_a')
  assert.equal(ctx.ciRunningTask.completed, false)
}
{
  const { ctx, storage, timers } = fixture()
  ctx.ciRunningTask = null
  storage.set('nkcn.ci.gradingTask.v1', JSON.stringify({ ...gradingTask, owner: 'another-account' }))
  ctx._restoreCIGradingTask()
  assert.equal(ctx.ciRunningTask, null, '不恢复其他账户的浏览器提示')
  assert.equal(timers.size, 0)
}
{
  const { ctx, requests, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  const pending = tick()
  requests[0].resolve({ ...gradingDone, run_id: 'other-run' })
  await pending
  assert.equal(ctx.ciRunningTask.run_id, 'p03_a')
  assert.equal(ctx.ciRunningTask.connection_paused, true, '不接受其他运行的终态')
}
{
  const { ctx, requests, results, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx.ciActiveAnalysisId = 'homework_a'
  const old = savedResult()
  ctx.ciActiveResult = old
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  const pending = tick()
  requests[0].resolve(gradingDone)
  for (let i = 0; i < 3; i++) {
    await flush()
    assert.equal(results.length, i + 1)
    results[i]({ error_num: 1, msg: '结果暂不可读' })
  }
  await pending
  assert.equal(results.length, 3, '只重取三次，不重跑批改')
  assert.equal(ctx.ciActiveResult, old, '结果暂不可读保留原画面')
  assert.equal(ctx.ciResultRetry.loading, false)
  const reload = ctx.reloadCIGradingResult()
  await flush()
  results[3](savedResult())
  await reload
  assert.equal(ctx.ciResultRetry, null)
  assert.equal(ctx.ciRunningTask.completed, true)
}
{
  const { ctx, requests, results, tick } = fixture()
  ctx.ciRunningTask = { ...gradingTask }
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx._startCIPoll('ci_task_a', 'homework_a', 'book-a')
  const pending = tick()
  requests[0].resolve(gradingDone)
  await flush()
  const selected = ctx._loadCIResult('homework_b', 'book-b', 'current')
  results[1](savedResult('homework_b'))
  await selected
  results[0](savedResult())
  await pending
  assert.equal(ctx.ciActiveAnalysisId, 'homework_b', '迟到的最终结果也不能覆盖新查看目标')
}
{
  const { ctx, results } = fixture()
  ctx.ciRunningTask = { ...gradingDone }
  ctx.ciSuppressOpenCIPanelOnComplete = false
  ctx.ciResultTarget = { analysis_id: 'homework_a', workspace: 'book-a', run_id: 'archive-old' }
  ctx.ciActiveAnalysisId = 'homework_a'
  ctx.ciActiveResult = savedResult()
  ctx.ciHomeworkRunId = 'archive-old'
  await ctx._loadCIGradingTaskResult(gradingDone, 'book-a')
  assert.equal(results.length, 0, '当前任务结束不替换正在查看的历史版本')
}
console.log('10 grading lifecycle scenarios passed (actual Vue methods)')

{
  const computed = component.properties.find(node => node.key?.name === 'computed').value.properties
  const node = computed.find(node => node.key?.name === 'ciViewedGradingTask')
  const readTask = new Function('localStorage', `return function ${script.slice(node.start, node.end)}`)({ getItem: () => 'book-a' })
  const ctx = { ciRunningTask: gradingTask, ciActiveAnalysisId: 'homework_b', ciActiveResult: savedResult('homework_b') }
  assert.equal(readTask.call(ctx), null, 'B面板不接收A进度或禁用状态')
  ctx.ciActiveAnalysisId = 'homework_a'
  assert.equal(readTask.call(ctx), gradingTask)
  ctx.ciActiveResult.manifest.username = 'book-b'
  assert.equal(readTask.call(ctx), null, '相同文件在其他本子不串任务状态')
}
{
  const text = parseVue(await readFile(new URL('../src/components/fileWindow/HomeworkGradingPanel.vue', import.meta.url), 'utf8')).descriptor.script.content
  const definition = parse(text, { sourceType: 'module' }).program.body.find(n => n.type === 'ExportDefaultDeclaration').declaration
  const computed = definition.properties.find(n => n.key?.name === 'computed').value.properties
  const read = name => {
    const node = computed.find(n => n.key?.name === name)
    return new Function(`return function ${text.slice(node.start, node.end)}`)()
  }
  const ctx = { activeResult: { available_actions: { retry_quality: { enabled: false, reason: '请先补齐复核' },
    resume: { enabled: true, rerun_stage: 'grading' } } } }
  assert.equal(read('canRetryRedBlue').call(ctx), false)
  assert.equal(read('redBlueEmptyText').call(ctx), '请先补齐复核')
  assert.equal(read('canResumeSessionRerun').call(ctx), true, '整份中断无需伪造篇目计划')
  ctx.activeResult.available_actions.retry_quality.enabled = true
  assert.equal(read('canRetryRedBlue').call(ctx), true)
}
console.log('2 grading panel action and task-isolation scenarios passed')
