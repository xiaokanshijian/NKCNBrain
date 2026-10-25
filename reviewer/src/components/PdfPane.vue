<template>
  <section class="document-pane">
    <header class="pane-header">
      <div>
        <strong>{{ title }}</strong>
        <span v-if="subtitle">{{ subtitle }}</span>
      </div>
      <span v-if="loading" class="pane-state">正在渲染…</span>
      <span v-else-if="error" class="pane-state is-error">{{ error }}</span>
    </header>
    <div class="page-scroll">
      <div v-if="!sourceUrl && !imageUrl" class="missing-document">
        <strong>缺少原始页面</strong>
        <span>仍可在下方查看阶段 JSON、报告和思维链文件。</span>
      </div>
      <div v-else ref="stage" class="page-stage" :style="stageStyle">
        <img v-if="imageUrl" ref="image" :src="imageUrl" alt="阶段页面" @load="onImageLoad" @error="onImageError" />
        <canvas v-else ref="canvas"></canvas>
        <div v-if="showOverlays" class="overlay-layer">
          <button
            v-for="question in visibleQuestions"
            :key="question.id"
            type="button"
            :class="['question-box', boxClass(question), { 'is-selected': question.id === selectedQuestionId }]"
            :style="boxStyle(question)"
            :title="questionTitle(question)"
            @click="$emit('select-question', question.id)"
          >
            <span class="question-id">{{ question.id }}</span>
            <span v-if="question.cross_page" class="question-flag">跨</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script>
import { markRaw } from 'vue'
import * as pdfjsLib from 'pdfjs-dist/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { positionToBbox, verdictLabel } from '../lib/artifacts.js'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl
const documentCache = new Map()

async function loadDocument(url) {
  if (!documentCache.has(url)) {
    documentCache.set(url, pdfjsLib.getDocument({ url, cMapPacked: true }).promise)
  }
  return documentCache.get(url)
}

export default {
  name: 'PdfPane',
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, default: '' },
    sourceUrl: { type: String, default: '' },
    imageUrl: { type: String, default: '' },
    page: { type: Number, default: 1 },
    zoom: { type: Number, default: 1 },
    questions: { type: Array, default: () => [] },
    stage: { type: String, default: 'grading' },
    selectedQuestionId: { type: String, default: '' },
    showOverlayOnImage: { type: Boolean, default: false },
  },
  emits: ['select-question', 'page-count'],
  data() {
    return {
      loading: false,
      error: '',
      width: 0,
      height: 0,
      renderTask: null,
      renderToken: 0,
    }
  },
  computed: {
    visibleQuestions() {
      return this.questions.filter(question => this.bbox(question))
    },
    showOverlays() {
      return this.visibleQuestions.length && (!this.imageUrl || this.showOverlayOnImage)
    },
    stageStyle() {
      if (!this.width || !this.height) return {}
      return { width: `${this.width}px`, height: `${this.height}px` }
    },
  },
  watch: {
    sourceUrl: 'renderPage',
    imageUrl: 'renderPage',
    page: 'renderPage',
    zoom: 'renderPage',
  },
  mounted() {
    this.renderPage()
  },
  beforeUnmount() {
    this.renderToken += 1
    this.cancelRender()
  },
  methods: {
    cancelRender() {
      const task = this.renderTask
      this.renderTask = null
      if (!task) return
      try {
        task.cancel()
      } catch {
        // PDF.js 任务可能已经自然完成；此时无需再处理。
      }
    },
    async renderPage() {
      const token = ++this.renderToken
      this.cancelRender()
      this.error = ''
      this.width = 0
      this.height = 0
      if (this.imageUrl || !this.sourceUrl) return
      this.loading = true
      try {
        const pdf = await loadDocument(this.sourceUrl)
        this.$emit('page-count', pdf.numPages)
        const safePage = Math.max(1, Math.min(this.page, pdf.numPages))
        const pdfPage = await pdf.getPage(safePage)
        if (token !== this.renderToken) return
        const viewport = pdfPage.getViewport({ scale: 1.15 * this.zoom })
        const canvas = this.$refs.canvas
        if (!canvas) return
        const ratio = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        this.width = viewport.width
        this.height = viewport.height
        const context = canvas.getContext('2d')
        // PDF.js 的 RenderTask 使用原生私有字段。Vue 深层响应式会把类实例
        // 包装成 Proxy，随后读取 task.promise 就会抛出
        // "Cannot read from private field"。保留原始实例并始终通过局部变量访问。
        const renderTask = pdfPage.render({
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
        })
        this.renderTask = markRaw(renderTask)
        await renderTask.promise
        if (this.renderTask === renderTask) this.renderTask = null
      } catch (error) {
        if (error?.name !== 'RenderingCancelledException') this.error = `页面渲染失败：${error.message}`
      } finally {
        if (token === this.renderToken) this.loading = false
      }
    },
    onImageLoad(event) {
      this.width = event.target.naturalWidth
      this.height = event.target.naturalHeight
      this.loading = false
    },
    onImageError() {
      this.error = '阶段图片加载失败'
    },
    bbox(question) {
      if (question.bbox && !Array.isArray(question.bbox)) return question.bbox
      return positionToBbox(question.position || question.bbox)
    },
    boxStyle(question) {
      const bbox = this.bbox(question)
      if (!bbox) return { display: 'none' }
      return {
        left: `${bbox.x * 100}%`,
        top: `${bbox.y * 100}%`,
        width: `${bbox.w * 100}%`,
        height: `${bbox.h * 100}%`,
      }
    },
    boxClass(question) {
      if (this.stage === 'layout') return this.confidenceClass(question.layout_confidence)
      if (this.stage === 'understanding') {
        const values = [question.recognition_confidence, question.understanding_confidence].map(Number).filter(Number.isFinite)
        const confidence = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
        return this.confidenceClass(confidence)
      }
      return `is-${question.verdict || 'uncertain'}`
    },
    confidenceClass(value) {
      const score = Number(value)
      if (!Number.isFinite(score)) return 'is-uncertain'
      if (score >= 85) return 'is-correct'
      if (score >= 65) return 'is-partial'
      return 'is-wrong'
    },
    questionTitle(question) {
      const pieces = [`题目 ${question.id || '-'}`]
      if (question.verdict) pieces.push(verdictLabel(question.verdict))
      if (question.student_answer) pieces.push(`作答：${question.student_answer}`)
      if (question.cross_page_note) pieces.push(question.cross_page_note)
      return pieces.join(' · ')
    },
  },
}
</script>
