<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand-block">
        <div class="brand-mark">NK</div>
        <div>
          <h1>连续图片批改查验台</h1>
          <p>原稿、阶段结果与两轮差异的本地审阅工具</p>
        </div>
      </div>

      <div class="header-actions">
        <button type="button" class="soft-button" :disabled="importBusy" @click="folderInput?.click()">
          导入文件夹
        </button>
        <button type="button" class="soft-button" :disabled="importBusy" @click="zipInput?.click()">
          导入 ZIP
        </button>
        <button type="button" class="primary-button" @click="showDataManager = true">数据管理</button>
        <input ref="folderInput" class="hidden-input" type="file" webkitdirectory multiple @change="handleFolderImport" />
        <input ref="zipInput" class="hidden-input" type="file" accept=".zip,application/zip" @change="handleZipImport" />
      </div>
    </header>

    <div v-if="notice" :class="['notice-bar', notice.type === 'error' ? 'is-error' : '']">
      <span>{{ notice.text }}</span>
      <button type="button" aria-label="关闭提示" @click="notice = null">×</button>
    </div>

    <section class="control-deck">
      <div class="run-compare-block">
        <span class="control-label">对比轮次</span>
        <label class="run-select is-a">
          <b>A</b>
          <select v-model="runAId"><option v-for="run in runs" :key="run.id" :value="run.id">{{ run.name }}</option></select>
        </label>
        <label class="run-select is-b">
          <b>B</b>
          <select v-model="runBId"><option v-for="run in runs" :key="run.id" :value="run.id">{{ run.name }}</option></select>
        </label>
        <div class="variant-toggle" role="group" aria-label="右侧显示轮次">
          <button type="button" :class="{ active: activeVariant === 'A' }" @click="activeVariant = 'A'">看 A</button>
          <button type="button" :class="{ active: activeVariant === 'B' }" @click="activeVariant = 'B'">看 B</button>
        </div>
      </div>

      <label>
        <span class="control-label">学科</span>
        <select v-model="subjectFilter">
          <option value="all">全部学科</option>
          <option value="math">数学</option>
          <option value="english">英语</option>
          <option value="chinese">语文</option>
        </select>
      </label>
      <label class="sample-select">
        <span class="control-label">测试文件</span>
        <select v-model="activeGroupId">
          <option v-for="sample in sampleOptions" :key="sample.groupId" :value="sample.groupId">
            {{ sample.displayName }} · {{ sample.pageCount }} 页
          </option>
        </select>
      </label>

      <div class="viewer-controls">
        <span class="control-label">页面</span>
        <button type="button" :disabled="page <= 1" @click="previousPage">←</button>
        <input v-model.number="page" type="number" min="1" :max="pageCount" aria-label="页码" />
        <span>/ {{ pageCount || '—' }}</span>
        <button type="button" :disabled="page >= pageCount" @click="nextPage">→</button>
        <button type="button" @click="zoom = Math.max(0.55, zoom - 0.1)">−</button>
        <span>{{ Math.round(zoom * 100) }}%</span>
        <button type="button" @click="zoom = Math.min(1.8, zoom + 0.1)">＋</button>
        <button type="button" @click="zoom = 0.9">适宽</button>
      </div>
    </section>

    <section class="stage-toolbar">
      <div class="stage-tabs" role="tablist" aria-label="页面批改阶段">
        <button
          v-for="item in pageStages"
          :key="item.id"
          type="button"
          :class="{ active: stage === item.id }"
          @click="stage = item.id"
        >
          <span>{{ item.index }}</span>{{ item.label }}
        </button>
      </div>
      <div class="stage-summary">
        <span :class="['run-dot', activeVariant.toLowerCase()]">{{ activeVariant }}</span>
        <strong>{{ activeRun?.shortName || activeRun?.name || '未选择轮次' }}</strong>
        <span>{{ activeSample?.subjectLabel }} · {{ activeQuestions.length }} 个题块</span>
      </div>
    </section>

    <main class="viewer-wrap">
      <button class="edge-nav edge-prev" type="button" :disabled="page <= 1" aria-label="上一页" @click="previousPage">‹</button>
      <div class="viewer-grid">
        <PdfPane
          title="原始页面"
          :subtitle="leftSample?.pdf?.name || leftSample?.sourceFileName || ''"
          :source-url="pdfUrl"
          :page="page"
          :zoom="zoom"
        />
        <PdfPane
          :title="rightPaneTitle"
          :subtitle="`${activeVariant} · ${activeRun?.shortName || activeRun?.name || ''}`"
          :source-url="pdfUrl"
          :image-url="rightImageUrl"
          :page="page"
          :zoom="zoom"
          :questions="activeQuestions"
          :stage="stage"
          :selected-question-id="selectedQuestionId"
          @select-question="selectedQuestionId = $event"
        />
      </div>
      <button class="edge-nav edge-next" type="button" :disabled="page >= pageCount" aria-label="下一页" @click="nextPage">›</button>
    </main>

    <section class="details-panel">
      <nav class="details-tabs" aria-label="详细内容">
        <button
          v-for="tab in detailTabs"
          :key="tab.id"
          type="button"
          :class="{ active: detailTab === tab.id }"
          @click="detailTab = tab.id"
        >{{ tab.label }}<span v-if="tabCount(tab.id)">{{ tabCount(tab.id) }}</span></button>
      </nav>

      <div v-if="detailTab === 'question'" class="details-content question-details">
        <div v-if="selectedQuestion" class="question-detail-grid">
          <article class="detail-card question-hero">
            <div class="eyebrow">第 {{ page }} 页 · 题目 {{ selectedQuestion.id }}</div>
            <h2>{{ selectedQuestion.stem_excerpt || selectedQuestion.parent_stem_excerpt || '未提供题干摘要' }}</h2>
            <div class="verdict-line">
              <span :class="['verdict-pill', `is-${selectedQuestion.verdict || 'uncertain'}`]">{{ verdictLabel(selectedQuestion.verdict) }}</span>
              <span v-if="selectedQuestion.cross_page" class="meta-pill">跨页题</span>
              <span v-if="selectedQuestion.knowledge_point" class="meta-pill">{{ selectedQuestion.knowledge_point }}</span>
            </div>
          </article>
          <article class="detail-card"><span>学生作答</span><strong>{{ selectedQuestion.student_answer || '—' }}</strong></article>
          <article class="detail-card"><span>参考答案</span><strong>{{ selectedQuestion.correct_answer || '—' }}</strong></article>
          <article class="detail-card"><span>模型理解</span><strong>{{ selectedQuestion.understanding || '—' }}</strong></article>
          <article class="detail-card"><span>错误类型</span><strong>{{ selectedQuestion.error_type || '—' }}</strong></article>
          <article class="detail-card confidence-card">
            <span>阶段置信度</span>
            <div><b>版面</b><i :style="confidenceWidth(selectedQuestion.layout_confidence)"></i><em>{{ scoreText(selectedQuestion.layout_confidence) }}</em></div>
            <div><b>识别</b><i :style="confidenceWidth(selectedQuestion.recognition_confidence)"></i><em>{{ scoreText(selectedQuestion.recognition_confidence) }}</em></div>
            <div><b>理解</b><i :style="confidenceWidth(selectedQuestion.understanding_confidence)"></i><em>{{ scoreText(selectedQuestion.understanding_confidence) }}</em></div>
            <div><b>批改</b><i :style="confidenceWidth(selectedQuestion.grading_confidence)"></i><em>{{ scoreText(selectedQuestion.grading_confidence) }}</em></div>
          </article>
          <article v-if="selectedQuestion.review" class="detail-card review-card">
            <span>模型复核</span>
            <strong>{{ selectedQuestion.review.ok ? '通过' : '发现问题' }}</strong>
            <p>{{ selectedQuestion.review.reason || selectedQuestion.review.detail || '未提供复核说明' }}</p>
            <pre v-if="selectedQuestion.review.fix">{{ JSON.stringify(selectedQuestion.review.fix, null, 2) }}</pre>
          </article>
          <article class="detail-card raw-question-card">
            <span>完整题目字段</span>
            <JsonTree :value="selectedQuestion" />
          </article>
        </div>
        <div v-else class="panel-empty">当前阶段没有可选题目。可以切换阶段或在“全部文件”中查看原始产物。</div>
      </div>

      <div v-else-if="detailTab === 'diff'" class="details-content diff-content">
        <div class="section-heading">
          <div><span class="eyebrow">A / B 字段差异</span><h2>第 {{ page }} 页 · {{ selectedQuestionId ? `题目 ${selectedQuestionId}` : '整页' }}</h2></div>
          <span class="count-badge">{{ questionDiff.length }} 处变化</span>
        </div>
        <div v-if="questionDiff.length" class="diff-table">
          <div class="diff-row diff-head"><span>字段</span><span>A · {{ runA?.shortName || runA?.name }}</span><span>B · {{ runB?.shortName || runB?.name }}</span></div>
          <div v-for="item in questionDiff" :key="item.path" :class="['diff-row', `is-${item.type}`]">
            <code>{{ item.path }}</code><pre>{{ printable(item.before) }}</pre><pre>{{ printable(item.after) }}</pre>
          </div>
        </div>
        <div v-else class="panel-empty compact">当前题目在两轮之间没有字段变化，或其中一轮缺少对应题目。</div>

        <div class="thinking-diff-block">
          <div class="section-heading small">
            <div><span class="eyebrow">思维链逐行差异</span><h3>选择同名思维链文件</h3></div>
            <select v-model="diffThinkingName"><option value="">请选择文件</option><option v-for="name in thinkingDiffOptions" :key="name" :value="name">{{ name }}</option></select>
          </div>
          <div v-if="diffThinkingLoading" class="panel-empty compact">正在比较文本…</div>
          <pre v-else-if="thinkingDiffParts.length" class="text-diff"><span v-for="(part, index) in thinkingDiffParts" :key="index" :class="`is-${part.type}`">{{ part.value }}</span></pre>
          <div v-else class="panel-empty compact">选择文件后显示 A/B 逐行变化；单侧缺失的文件也会标记为新增或删除。</div>
        </div>
      </div>

      <div v-else-if="detailTab === 'stages'" class="details-content file-workspace">
        <aside class="file-sidebar">
          <div v-for="group in stageGroups" :key="group.stage" class="file-group">
            <h3>{{ stageLabel(group.stage) }} <span>{{ group.files.length }}</span></h3>
            <button v-for="file in group.files" :key="file.id" type="button" :class="{ active: previewEntry?.id === file.id }" @click="previewEntry = file">
              <span>{{ file.name }}</span><small v-if="file.page">P{{ file.page }}</small>
            </button>
          </div>
        </aside>
        <FilePreview :entry="previewEntry" :read-text="readEntryText" :resolve-url="resolveEntryUrl" />
      </div>

      <div v-else-if="detailTab === 'thinking'" class="details-content file-workspace">
        <aside class="file-sidebar">
          <div class="sidebar-heading"><strong>全部思维链与错误文本</strong><span>{{ activeThinkingFiles.length }} 个</span></div>
          <button v-for="file in activeThinkingFiles" :key="file.id" type="button" :class="{ active: previewEntry?.id === file.id }" @click="previewEntry = file">
            <span>{{ file.name }}</span><small v-if="file.page">P{{ file.page }}</small>
          </button>
        </aside>
        <FilePreview :entry="previewEntry" :read-text="readEntryText" :resolve-url="resolveEntryUrl" />
      </div>

      <div v-else-if="detailTab === 'human'" class="details-content human-review">
        <div class="human-summary">
          <details v-for="doc in humanDocs" :key="doc.name">
            <summary>{{ doc.name }}</summary><pre>{{ doc.text }}</pre>
          </details>
        </div>
        <div v-if="humanRows.length" class="human-grid">
          <div class="human-table table-scroll">
            <table>
              <thead><tr><th>#</th><th v-for="field in humanFields" :key="field">{{ field }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, index) in humanRows" :key="index" :class="{ active: index === humanRowIndex }" @click="humanRowIndex = index">
                  <td>{{ index + 1 }}</td><td v-for="field in humanFields" :key="field">{{ row[field] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="human-images">
            <article><span>原版面附件</span><img v-if="humanOriginalUrl" :src="humanOriginalUrl" alt="人工查验原版面" /><div v-else class="panel-empty compact">无对应附件</div></article>
            <article><span>批改结果附件</span><img v-if="humanResultUrl" :src="humanResultUrl" alt="人工查验批改结果" /><div v-else class="panel-empty compact">无对应附件</div></article>
          </div>
        </div>
        <div v-else class="panel-empty">这个样本没有第一轮人工查验 CSV。</div>
      </div>

      <div v-else class="details-content file-workspace all-files">
        <aside class="file-sidebar">
          <div class="file-search"><input v-model="fileSearch" type="search" placeholder="搜索文件名、路径或阶段" /><span>{{ filteredFiles.length }}/{{ sampleFiles.length }}</span></div>
          <button v-for="file in filteredFiles" :key="file.id" type="button" :class="{ active: previewEntry?.id === file.id }" @click="previewEntry = file">
            <span>{{ file.relativePath }}</span><small>{{ stageLabel(file.stage) }}</small>
          </button>
        </aside>
        <FilePreview :entry="previewEntry" :read-text="readEntryText" :resolve-url="resolveEntryUrl" />
      </div>
    </section>

    <div v-if="showDataManager" class="modal-backdrop" @click.self="showDataManager = false">
      <section class="data-modal">
        <header><div><span class="eyebrow">本机数据</span><h2>导入与存储管理</h2></div><button type="button" aria-label="关闭" @click="showDataManager = false">×</button></header>
        <div class="storage-meter">
          <div><strong>{{ formatBytes(storageInfo.usage) }}</strong><span>已使用</span></div>
          <div><strong>{{ formatBytes(storageInfo.quota) }}</strong><span>浏览器配额</span></div>
          <div><strong>{{ importedDatasets.length }}</strong><span>导入数据集</span></div>
          <i><b :style="{ width: storagePercent + '%' }"></b></i>
        </div>
        <div class="dataset-list">
          <article class="dataset-card builtin-card">
            <div><strong>内置测试数据</strong><span>2 轮 · 12 个样本 · 黄金集已排除</span></div><em>只读</em>
          </article>
          <article v-for="dataset in importedDatasets" :key="dataset.id" class="dataset-card">
            <div><strong>{{ dataset.name }}</strong><span>{{ dataset.runs?.[0]?.samples?.length || 0 }} 个样本 · {{ formatBytes(dataset.totalSize) }} · {{ formatDate(dataset.createdAt) }}</span></div>
            <div class="dataset-actions"><button type="button" @click="editDatasetName(dataset)">重命名</button><button type="button" class="danger" @click="removeDataset(dataset)">删除</button></div>
          </article>
          <div v-if="!importedDatasets.length" class="panel-empty compact">尚未导入额外结果。文件夹和 ZIP 都会保存在当前浏览器中。</div>
        </div>
        <footer><span>所有导入均留在本机，不会上传网络。</span><div><button type="button" class="soft-button" @click="folderInput?.click()">导入文件夹</button><button type="button" class="primary-button" @click="zipInput?.click()">导入 ZIP</button></div></footer>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import FilePreview from './components/FilePreview.vue'
import JsonTree from './components/JsonTree.vue'
import PdfPane from './components/PdfPane.vue'
import { STAGE_LABELS, STAGE_ORDER, verdictLabel as localVerdictLabel } from './lib/artifacts.js'
import { decodeTextBuffer, parseCsvText } from './lib/csv.js'
import { diffObjects, diffText } from './lib/diff.js'
import { buildImportedDataset, filesFromFileList, filesFromZip } from './lib/importer.js'
import { deleteDataset, getStoredFile, listDatasets, renameDataset, requestPersistentStorage, saveDataset, storageEstimate } from './lib/storage.js'

const runs = ref([])
const builtinRuns = ref([])
const importedDatasets = ref([])
const runAId = ref('round-1')
const runBId = ref('round-2')
const activeVariant = ref('B')
const subjectFilter = ref('all')
const activeGroupId = ref('')
const page = ref(1)
const zoom = ref(0.9)
const stage = ref('grading')
const selectedQuestionId = ref('')
const detailTab = ref('question')
const previewEntry = ref(null)
const fileSearch = ref('')
const pdfUrl = ref('')
const rightImageUrl = ref('')
const pageDataA = ref(emptyPageData())
const pageDataB = ref(emptyPageData())
const loadToken = ref(0)
const objectUrls = new Map()
const notice = ref(null)
const folderInput = ref(null)
const zipInput = ref(null)
const importBusy = ref(false)
const showDataManager = ref(false)
const storageInfo = ref({ usage: 0, quota: 0 })

const diffThinkingName = ref('')
const thinkingDiffParts = ref([])
const diffThinkingLoading = ref(false)
const humanRows = ref([])
const humanFields = ref([])
const humanRowIndex = ref(0)
const humanOriginalUrl = ref('')
const humanResultUrl = ref('')
const humanDocs = ref([])

const pageStages = [
  { id: 'layout', index: '01', label: '无损版面' },
  { id: 'understanding', index: '02', label: '无损理解' },
  { id: 'grading', index: '03', label: '三区批改' },
  { id: 'review', index: '04', label: '模型复核' },
]
const detailTabs = [
  { id: 'question', label: '题目详情' },
  { id: 'diff', label: 'A/B 差异' },
  { id: 'stages', label: '阶段产物' },
  { id: 'thinking', label: '思维链' },
  { id: 'human', label: '人工查验' },
  { id: 'files', label: '全部文件' },
]

const runA = computed(() => runs.value.find(run => run.id === runAId.value) || null)
const runB = computed(() => runs.value.find(run => run.id === runBId.value) || null)
const activeRun = computed(() => activeVariant.value === 'A' ? runA.value : runB.value)

function runSample(run, groupId) {
  return run?.samples?.find(sample => sample.groupId === groupId) || null
}

const sampleA = computed(() => runSample(runA.value, activeGroupId.value))
const sampleB = computed(() => runSample(runB.value, activeGroupId.value))
const activeSample = computed(() => activeVariant.value === 'A' ? sampleA.value : sampleB.value)
const leftSample = computed(() => activeSample.value || sampleB.value || sampleA.value)

const sampleOptions = computed(() => {
  const map = new Map()
  for (const run of [runA.value, runB.value]) {
    for (const sample of run?.samples || []) {
      if (subjectFilter.value !== 'all' && sample.subject !== subjectFilter.value) continue
      if (!map.has(sample.groupId)) map.set(sample.groupId, sample)
    }
  }
  const subjectOrder = { math: 1, english: 2, chinese: 3, unknown: 9 }
  return Array.from(map.values()).sort((a, b) => {
    const order = (subjectOrder[a.subject] || 9) - (subjectOrder[b.subject] || 9)
    return order || a.displayName.localeCompare(b.displayName, 'zh-CN', { numeric: true })
  })
})

const pageCount = computed(() => activeSample.value?.pageCount || leftSample.value?.pageCount || 0)
const activePageData = computed(() => activeVariant.value === 'A' ? pageDataA.value : pageDataB.value)
const activeQuestions = computed(() => activePageData.value.questions[stage.value] || [])
const selectedQuestion = computed(() => activeQuestions.value.find(question => String(question.id) === String(selectedQuestionId.value)) || null)
const rightPaneTitle = computed(() => pageStages.find(item => item.id === stage.value)?.label || '批改页面')

const questionDiff = computed(() => {
  const qa = (pageDataA.value.questions[stage.value] || []).find(item => String(item.id) === String(selectedQuestionId.value))
  const qb = (pageDataB.value.questions[stage.value] || []).find(item => String(item.id) === String(selectedQuestionId.value))
  if (qa || qb) return diffObjects(qa || {}, qb || {})
  return diffObjects(pageDataA.value.documents[stage.value] || {}, pageDataB.value.documents[stage.value] || {})
})

const sampleFiles = computed(() => {
  const files = [...(activeSample.value?.files || []), ...(activeRun.value?.files || [])]
  return files.sort((a, b) => a.relativePath.localeCompare(b.relativePath, 'zh-CN', { numeric: true }))
})
const filteredFiles = computed(() => {
  const query = fileSearch.value.trim().toLowerCase()
  if (!query) return sampleFiles.value
  return sampleFiles.value.filter(file => `${file.relativePath} ${stageLabel(file.stage)}`.toLowerCase().includes(query))
})
const activeThinkingFiles = computed(() => sampleFiles.value.filter(file => file.stage === 'thinking'))
const stageGroups = computed(() => STAGE_ORDER.map(item => ({
  stage: item,
  files: sampleFiles.value.filter(file => file.stage === item),
})).filter(group => group.files.length))

const thinkingFilesA = computed(() => sampleA.value?.files?.filter(file => file.stage === 'thinking') || [])
const thinkingFilesB = computed(() => sampleB.value?.files?.filter(file => file.stage === 'thinking') || [])
const thinkingDiffOptions = computed(() => Array.from(new Set([
  ...thinkingFilesA.value.map(file => file.name),
  ...thinkingFilesB.value.map(file => file.name),
])).sort((a, b) => a.localeCompare(b, 'zh-CN', { numeric: true })))

const storagePercent = computed(() => storageInfo.value.quota ? Math.min(100, (storageInfo.value.usage / storageInfo.value.quota) * 100) : 0)

function emptyPageData() {
  return { documents: { layout: null, understanding: null, grading: null, review: null }, questions: { layout: [], understanding: [], grading: [], review: [] }, imageEntry: {} }
}

function stageLabel(value) {
  return STAGE_LABELS[value] || value || '其他文件'
}

function stageEntry(sample, targetStage, targetPage) {
  const candidates = (sample?.files || []).filter(file => file.stage === targetStage && file.page === targetPage)
  const jsonFiles = candidates.filter(file => file.relativePath.toLowerCase().endsWith('.json'))
  if (targetStage === 'review') return jsonFiles.find(file => file.name.toLowerCase().endsWith('.review.json')) || jsonFiles[0] || null
  return jsonFiles[0] || null
}

function stageImageEntry(sample, targetStage, targetPage) {
  const marker = { layout: 'annotated_layout', understanding: 'annotated_understanding', grading: '/annotated/' }[targetStage]
  if (!marker) return null
  return (sample?.files || []).find(file => file.page === targetPage && /\.(?:png|jpe?g|webp)$/i.test(file.name) && file.relativePath.toLowerCase().includes(marker)) || null
}

async function readJsonEntry(entry) {
  if (!entry) return null
  try { return JSON.parse(await readEntryText(entry)) } catch { return null }
}

function mergeQuestions(...documents) {
  const map = new Map()
  for (const document of documents) {
    const questions = document?.questions || document?.items || []
    for (const question of questions) {
      if (!question?.id) continue
      const current = map.get(String(question.id)) || { id: question.id }
      if (document?.items && !document?.questions) current.review = question
      else Object.assign(current, question)
      map.set(String(question.id), current)
    }
  }
  return Array.from(map.values())
}

async function loadPageData(sample) {
  if (!sample) return emptyPageData()
  const layoutEntry = stageEntry(sample, 'layout', page.value)
  const understandingEntry = stageEntry(sample, 'understanding', page.value)
  const gradingEntry = stageEntry(sample, 'grading', page.value)
  const reviewEntry = stageEntry(sample, 'review', page.value)
  const [layout, understanding, grading, review] = await Promise.all([
    readJsonEntry(layoutEntry), readJsonEntry(understandingEntry), readJsonEntry(gradingEntry), readJsonEntry(reviewEntry),
  ])
  return {
    documents: { layout, understanding, grading, review },
    questions: {
      layout: mergeQuestions(layout),
      understanding: mergeQuestions(layout, understanding),
      grading: mergeQuestions(layout, understanding, grading),
      review: mergeQuestions(layout, understanding, grading, review),
    },
    imageEntry: {
      layout: stageImageEntry(sample, 'layout', page.value),
      understanding: stageImageEntry(sample, 'understanding', page.value),
      grading: stageImageEntry(sample, 'grading', page.value),
    },
  }
}

async function refreshPageData() {
  const token = ++loadToken.value
  const [a, b] = await Promise.all([loadPageData(sampleA.value), loadPageData(sampleB.value)])
  if (token !== loadToken.value) return
  pageDataA.value = a
  pageDataB.value = b
  await refreshRightImage()
}

async function refreshPdfUrl() {
  pdfUrl.value = leftSample.value?.pdf ? await resolveEntryUrl(leftSample.value.pdf) : ''
}

async function refreshRightImage() {
  const entry = activePageData.value.imageEntry?.[stage.value]
  rightImageUrl.value = entry ? await resolveEntryUrl(entry) : ''
}

function publicUrl(value) {
  if (!value) return ''
  if (/^(?:blob:|data:|https?:)/.test(value)) return value
  return new URL(value.replace(/^\//, ''), document.baseURI).href
}

async function resolveEntryUrl(entry) {
  if (!entry) return ''
  if (entry.url) return publicUrl(entry.url)
  if (!entry.storageKey) return ''
  if (objectUrls.has(entry.storageKey)) return objectUrls.get(entry.storageKey)
  const stored = await getStoredFile(entry.storageKey)
  if (!stored?.blob) throw new Error('IndexedDB 中缺少该文件')
  const url = URL.createObjectURL(stored.blob)
  objectUrls.set(entry.storageKey, url)
  return url
}

async function readEntryBuffer(entry) {
  if (entry.url) {
    const response = await fetch(publicUrl(entry.url))
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.arrayBuffer()
  }
  const stored = await getStoredFile(entry.storageKey)
  if (!stored?.blob) throw new Error('IndexedDB 中缺少该文件')
  return stored.blob.arrayBuffer()
}

async function readEntryText(entry) {
  return decodeTextBuffer(await readEntryBuffer(entry))
}

function ensureSampleSelection() {
  const options = sampleOptions.value
  if (!options.some(sample => sample.groupId === activeGroupId.value)) activeGroupId.value = options[0]?.groupId || ''
}

function previousPage() {
  if (page.value > 1) page.value -= 1
}

function nextPage() {
  if (page.value < pageCount.value) page.value += 1
}

function handleKeydown(event) {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) return
  if (event.key === 'ArrowLeft') previousPage()
  if (event.key === 'ArrowRight') nextPage()
}

function scoreText(value) {
  const score = Number(value)
  return Number.isFinite(score) ? `${Math.round(score)}%` : '—'
}

function confidenceWidth(value) {
  const score = Number(value)
  return { '--score': `${Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0}%` }
}

function verdictLabel(value) {
  return localVerdictLabel(value)
}

function printable(value) {
  if (value === undefined) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function tabCount(id) {
  if (id === 'diff') return questionDiff.value.length || ''
  if (id === 'thinking') return activeThinkingFiles.value.length || ''
  if (id === 'files') return sampleFiles.value.length || ''
  if (id === 'stages') return stageGroups.value.length || ''
  if (id === 'human') return humanRows.value.length || ''
  return ''
}

async function refreshThinkingDiff() {
  thinkingDiffParts.value = []
  if (!diffThinkingName.value) return
  diffThinkingLoading.value = true
  try {
    const a = thinkingFilesA.value.find(file => file.name === diffThinkingName.value)
    const b = thinkingFilesB.value.find(file => file.name === diffThinkingName.value)
    const [left, right] = await Promise.all([a ? readEntryText(a) : '', b ? readEntryText(b) : ''])
    thinkingDiffParts.value = diffText(left, right)
  } finally {
    diffThinkingLoading.value = false
  }
}

async function loadHumanReview() {
  humanRows.value = []
  humanFields.value = []
  humanDocs.value = []
  const baseRun = builtinRuns.value.find(run => run.id === 'round-1')
  const sample = runSample(baseRun, activeGroupId.value)
  const csv = sample?.files?.find(file => file.relativePath.toLowerCase().endsWith('.csv'))
  if (csv) {
    const parsed = parseCsvText(await readEntryText(csv))
    humanRows.value = parsed.rows
    humanFields.value = parsed.fields
  }
  for (const doc of baseRun?.files || []) {
    humanDocs.value.push({ name: doc.name, text: await readEntryText(doc) })
  }
  humanRowIndex.value = 0
  await refreshHumanAttachments()
}

function rowField(row, includes) {
  const key = Object.keys(row || {}).find(item => includes.every(piece => item.includes(piece)))
  return key ? row[key] : ''
}

async function refreshHumanAttachments() {
  humanOriginalUrl.value = ''
  humanResultUrl.value = ''
  const baseRun = builtinRuns.value.find(run => run.id === 'round-1')
  const sample = runSample(baseRun, activeGroupId.value)
  const row = humanRows.value[humanRowIndex.value]
  if (!sample || !row) return
  const originalIndex = rowField(row, ['原版面'])
  const resultIndex = rowField(row, ['批改结果'])
  const original = sample.files.find(file => file.relativePath.replace(/\\/g, '/').endsWith(`附件/原版面/${originalIndex}.png`))
  const result = sample.files.find(file => file.relativePath.replace(/\\/g, '/').endsWith(`附件/批改结果/${resultIndex}.png`))
  if (original) humanOriginalUrl.value = await resolveEntryUrl(original)
  if (result) humanResultUrl.value = await resolveEntryUrl(result)
}

async function reloadImportedDatasets() {
  importedDatasets.value = await listDatasets()
  runs.value = [...builtinRuns.value, ...importedDatasets.value.flatMap(dataset => dataset.runs || [])]
  storageInfo.value = await storageEstimate()
}

function defaultImportName(files, fallback) {
  const first = files[0]?.path?.split('/')[0]
  return first && first !== files[0]?.name ? first : fallback
}

async function persistImport(name, files) {
  importBusy.value = true
  notice.value = { type: 'info', text: `正在解析“${name}”…` }
  try {
    await requestPersistentStorage()
    const { dataset, storedFiles } = await buildImportedDataset(name, files, builtinRuns.value)
    await saveDataset(dataset, storedFiles)
    await reloadImportedDatasets()
    const importedRun = dataset.runs[0]
    runBId.value = importedRun.id
    activeVariant.value = 'B'
    activeGroupId.value = importedRun.samples[0]?.groupId || activeGroupId.value
    notice.value = { type: 'info', text: `已导入 ${importedRun.samples.length} 个样本、${storedFiles.length} 个文件，并保存到本机浏览器。` }
  } catch (error) {
    notice.value = { type: 'error', text: `导入失败：${error.message}` }
  } finally {
    importBusy.value = false
  }
}

async function handleFolderImport(event) {
  const raw = await filesFromFileList(event.target.files)
  event.target.value = ''
  if (!raw.length) return
  await persistImport(defaultImportName(raw, `导入结果 ${new Date().toLocaleString('zh-CN')}`), raw)
}

async function handleZipImport(event) {
  const zip = event.target.files?.[0]
  event.target.value = ''
  if (!zip) return
  try {
    importBusy.value = true
    notice.value = { type: 'info', text: `正在解压“${zip.name}”…` }
    const raw = await filesFromZip(zip)
    importBusy.value = false
    await persistImport(zip.name.replace(/\.zip$/i, ''), raw)
  } catch (error) {
    importBusy.value = false
    notice.value = { type: 'error', text: `ZIP 读取失败：${error.message}` }
  }
}

async function editDatasetName(dataset) {
  const name = window.prompt('新的数据集名称', dataset.name)?.trim()
  if (!name || name === dataset.name) return
  await renameDataset(dataset.id, name)
  await reloadImportedDatasets()
}

async function removeDataset(dataset) {
  if (!window.confirm(`确认删除“${dataset.name}”及其本机文件？此操作不影响原始测试目录。`)) return
  await deleteDataset(dataset.id)
  if (dataset.runs?.some(run => run.id === runAId.value)) runAId.value = 'round-1'
  if (dataset.runs?.some(run => run.id === runBId.value)) runBId.value = 'round-2'
  await reloadImportedDatasets()
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!bytes) return '0 B'
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '未知时间'
}

async function loadCatalog() {
  const response = await fetch(new URL('builtin/catalog.json', document.baseURI))
  if (!response.ok) throw new Error(`内置目录读取失败：HTTP ${response.status}`)
  const catalog = await response.json()
  builtinRuns.value = catalog.runs || []
  await reloadImportedDatasets()
  ensureSampleSelection()
}

watch([runAId, runBId, subjectFilter], ensureSampleSelection)
watch(activeGroupId, () => { page.value = 1; selectedQuestionId.value = ''; loadHumanReview() })
watch(pageCount, count => { if (count && page.value > count) page.value = count })
watch([sampleA, sampleB, page], refreshPageData, { deep: false })
watch(leftSample, refreshPdfUrl, { deep: false })
watch([activeVariant, stage], refreshRightImage)
watch(activeQuestions, questions => {
  if (!questions.some(item => String(item.id) === String(selectedQuestionId.value))) selectedQuestionId.value = questions[0]?.id ? String(questions[0].id) : ''
})
watch(diffThinkingName, refreshThinkingDiff)
watch(humanRowIndex, refreshHumanAttachments)
watch(detailTab, async value => {
  if (value === 'human') await loadHumanReview()
  if (['stages', 'thinking', 'files'].includes(value) && !previewEntry.value) previewEntry.value = sampleFiles.value[0] || null
})
watch(activeSample, () => { previewEntry.value = sampleFiles.value.find(file => file.stage === 'manifest') || sampleFiles.value[0] || null })

onMounted(async () => {
  window.addEventListener('keydown', handleKeydown)
  try {
    await loadCatalog()
    await nextTick()
    await Promise.all([refreshPdfUrl(), refreshPageData(), loadHumanReview()])
  } catch (error) {
    notice.value = { type: 'error', text: error.message }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  for (const url of objectUrls.values()) URL.revokeObjectURL(url)
})
</script>
