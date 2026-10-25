<template>
  <section class="file-preview">
    <header v-if="entry" class="file-preview-header">
      <div>
        <strong>{{ entry.name }}</strong>
        <span>{{ entry.relativePath }} · {{ formatBytes(entry.size) }}</span>
      </div>
      <div class="preview-actions">
        <button v-if="kind === 'json'" type="button" class="text-btn" @click="rawJson = !rawJson">
          {{ rawJson ? '结构视图' : '原始 JSON' }}
        </button>
        <a v-if="url" :href="url" :download="entry.name" class="text-btn">下载</a>
      </div>
    </header>
    <div v-if="!entry" class="empty-preview">选择一个文件查看内容</div>
    <div v-else-if="loading" class="empty-preview">正在读取文件…</div>
    <div v-else-if="error" class="preview-error">{{ error }}</div>
    <template v-else>
      <pre v-if="kind === 'json' && rawJson" class="raw-preview">{{ text }}</pre>
      <JsonTree v-else-if="kind === 'json'" :value="json" />
      <pre v-else-if="kind === 'text'" class="raw-preview">{{ text }}</pre>
      <div v-else-if="kind === 'csv'" class="table-scroll">
        <table>
          <thead><tr><th v-for="field in csv.fields" :key="field">{{ field }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, index) in csv.rows" :key="index">
              <td v-for="field in csv.fields" :key="field">{{ row[field] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <img v-else-if="kind === 'image'" :src="url" :alt="entry.name" class="standalone-image" />
      <iframe v-else-if="kind === 'pdf'" :src="url" title="PDF 文件预览"></iframe>
      <div v-else class="empty-preview">此文件不支持内嵌预览，可使用右上角“下载”。</div>
    </template>
  </section>
</template>

<script>
import JsonTree from './JsonTree.vue'
import { parseCsvText } from '../lib/csv.js'

export default {
  name: 'FilePreview',
  components: { JsonTree },
  props: {
    entry: { type: Object, default: null },
    readText: { type: Function, required: true },
    resolveUrl: { type: Function, required: true },
  },
  data() {
    return {
      loading: false,
      error: '',
      text: '',
      json: null,
      csv: { fields: [], rows: [] },
      url: '',
      rawJson: false,
      token: 0,
    }
  },
  computed: {
    kind() {
      if (!this.entry) return 'unknown'
      const lower = this.entry.relativePath.toLowerCase()
      if (lower.endsWith('.json') || lower.includes('.json.')) return 'json'
      if (lower.endsWith('.csv')) return 'csv'
      if (/\.(?:txt|md|log)$/i.test(lower)) return 'text'
      if (/\.(?:png|jpe?g|gif|webp|bmp)$/i.test(lower)) return 'image'
      if (lower.endsWith('.pdf')) return 'pdf'
      return 'unknown'
    },
  },
  watch: {
    entry: { immediate: true, handler: 'load' },
  },
  methods: {
    async load() {
      const token = ++this.token
      this.loading = !!this.entry
      this.error = ''
      this.text = ''
      this.json = null
      this.url = ''
      if (!this.entry) return
      try {
        this.url = await this.resolveUrl(this.entry)
        if (['json', 'csv', 'text'].includes(this.kind)) {
          this.text = await this.readText(this.entry)
          if (this.kind === 'json') this.json = JSON.parse(this.text)
          if (this.kind === 'csv') this.csv = parseCsvText(this.text)
        }
      } catch (error) {
        this.error = `无法预览：${error.message}`
      } finally {
        if (token === this.token) this.loading = false
      }
    },
    formatBytes(value) {
      const bytes = Number(value || 0)
      if (bytes < 1024) return `${bytes} B`
      if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
      return `${(bytes / 1024 ** 2).toFixed(1)} MB`
    },
  },
}
</script>
