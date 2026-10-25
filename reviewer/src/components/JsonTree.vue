<template>
  <div class="json-tree">
    <template v-if="isObject">
      <details :open="depth < 2">
        <summary>{{ summaryLabel }}</summary>
        <div class="json-children">
          <div v-for="([key, item]) in entries" :key="key" class="json-row">
            <span class="json-key">{{ key }}:</span>
            <JsonTree v-if="isNested(item)" :value="item" :depth="depth + 1" />
            <span v-else :class="['json-value', valueClass(item)]">{{ formatValue(item) }}</span>
          </div>
        </div>
      </details>
    </template>
    <span v-else :class="['json-value', valueClass(value)]">{{ formatValue(value) }}</span>
  </div>
</template>

<script>
export default {
  name: 'JsonTree',
  props: {
    value: { type: null, default: null },
    depth: { type: Number, default: 0 },
  },
  computed: {
    isObject() {
      return this.value !== null && typeof this.value === 'object'
    },
    entries() {
      return this.isObject ? Object.entries(this.value) : []
    },
    summaryLabel() {
      return Array.isArray(this.value) ? `数组 · ${this.value.length} 项` : `对象 · ${this.entries.length} 字段`
    },
  },
  methods: {
    isNested(value) {
      return value !== null && typeof value === 'object'
    },
    formatValue(value) {
      if (value === null) return 'null'
      if (typeof value === 'string') return value
      if (value === undefined) return 'undefined'
      return String(value)
    },
    valueClass(value) {
      return `is-${value === null ? 'null' : typeof value}`
    },
  },
}
</script>
