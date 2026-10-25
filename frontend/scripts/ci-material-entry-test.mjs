import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { parse } = require('@babel/parser')
const vue = await readFile(new URL('../src/views/mainPage.vue', import.meta.url), 'utf8')
const script = vue.match(/<script>([\s\S]*?)<\/script>/)[1]
const tree = parse(script, { sourceType: 'module' })
const component = tree.program.body.find(n => n.type === 'ExportDefaultDeclaration').declaration
const methods = component.properties.find(n => n.key?.name === 'methods').value.properties
const node = methods.find(n => n.key.name === 'handleOpenHomeworkPageView')
for (const saved of [false, true]) {
  for (const stage of ['layout', 'understanding', 'grading']) {
    const settings = { error_num: 0, feedback_eligible: true, material_saved: saved,
      parse_status: saved ? 'unstructured' : 'parsed', material: saved ? { feedback_overrides: { grade: '四年级' } } : {} }
    const context = { feedbackMaterialSettings: async () => settings,
      queryCIAnalyses: async () => ({ error_num: 0, singles: [] }),
      localStorage: { getItem: () => 'synthetic_book' } }
    const handler = vm.runInNewContext(`({${script.slice(node.start, node.end)}})`, context).handleOpenHomeworkPageView
    const starts = []
    const instance = { curFileInfo: { name: 'fixture.pdf' }, _isImageOrPdf: () => true,
      _findHomeworkRecordForFile: () => null, _startCIAnalysis: async (...args) => starts.push(args),
      openFeedbackMaterial: () => assert.fail('阶段按钮不能打开材料弹窗'),
      $message: { error: message => assert.fail(message), info: message => assert.fail(message) } }
    await handler.call(instance, stage)
    assert.equal(starts.length, 1)
    assert.equal(starts[0][3].homeworkTargetStage, stage)
    assert.equal(starts[0][3].requestedAction, 'grading')
    assert.equal(starts[0][3].material, settings.material)
  }
}
for (const source of ['active', 'server']) {
  for (const ready of [true, false]) {
    const result = { analysis_type: 'homework_grading', manifest: { selected_files: ['fixture.pdf'] } }
    let opened = 0
    const context = { feedbackMaterialSettings: () => assert.fail('查看旧结果不能先加载新配置'),
      queryCIAnalyses: async () => ({ error_num: 0, singles: [] }),
      getCIResult: async () => ({ error_num: 0, ...result }),
      localStorage: { getItem: () => 'synthetic_book' } }
    const handler = vm.runInNewContext(`({${script.slice(node.start, node.end)}})`, context).handleOpenHomeworkPageView
    const instance = { curFileInfo: { name: 'fixture.pdf' }, ciActiveResult: source === 'active' ? result : null,
      _isImageOrPdf: () => true, _isHomeworkStageReadyFromManifest: () => ready,
      _findHomeworkRecordForFile: () => ({ analysis_id: 'old', status: ready ? 'completed' : 'failed' }),
      _openCIExistingResult: async () => { opened++ }, _openHomeworkPageViewMode: async () => { opened++ },
      _startCIAnalysis: () => assert.fail('已有结果不能自动重做'),
      $message: { error: message => assert.fail(message), info() {} } }
    await handler.call(instance, 'grading')
    assert.ok(opened > 0 || instance.showContinuousImagePanel)
  }
}
console.log('10 stage-entry and existing-result cases passed')
