<template>
  <section class="notebook-skill-selector">
    <label><input type="checkbox" :checked="modelValue.enabled" @change="toggle($event.target.checked)"> 本次使用本子 Skill</label>
    <template v-if="modelValue.enabled">
      <p>可选任意个成员，模型将从中精选用于理解与三区批改</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-button v-if="error" size="small" @click="load">重新加载</el-button>
      <div v-if="packGroups.length" class="pack-select-all">
        <span>Skill 包：</span>
        <el-button
          v-for="group in packGroups"
          :key="group.source"
          size="small"
          @click="selectPack(group)"
        >全选「{{ shortSource(group.source) }}」</el-button>
      </div>
      <el-select :model-value="modelValue.names" multiple filterable
        popper-class="notebook-skill-popper" :fit-input-width="true"
        :loading="loading" :disabled="loading || !!error" placeholder="请选择具体 Skill" @update:model-value="select">
        <el-option-group v-for="group in groups" :key="group.source" :label="group.source">
          <el-option v-for="item in group.items" :key="item.name" :value="item.name"
            :label="item.title === item.name ? item.name : `${item.title}（${item.name}）`" />
        </el-option-group>
      </el-select>
      <p v-if="!loading && !error && !items.length">当前本子没有可用成员，请先导入或启用 Skill。</p>
      <p v-if="modelValue.names.length" class="skill-count">已选 {{ modelValue.names.length }} 个</p>
      <p v-for="item in selectedItems" :key="item.name" class="skill-description"><strong>{{ item.title || item.name }}</strong>：{{ item.description }}</p>
    </template>
  </section>
</template>

<script>
import { listNotebookSkills } from '@/api/continuous_image'

export default {
  name: 'NotebookSkillSelector',
  props: {
    username: { type: String, required: true },
    modelValue: { type: Object, required: true },
  },
  emits: ['update:modelValue', 'valid'],
  data() { return { items: [], loading: false, error: '', sequence: 0 } },
  computed: {
    groups() {
      const groups = new Map()
      this.items.forEach(item => {
        const source = item.pack_zip || item.source_doc || '本子文档'
        if (!groups.has(source)) groups.set(source, [])
        groups.get(source).push(item)
      })
      return [...groups].map(([source, items]) => ({ source, items }))
    },
    packGroups() {
      return this.groups.filter(group => String(group.source || '').toLowerCase().endsWith('.zip'))
    },
    selectedItems() { return this.items.filter(item => this.modelValue.names.includes(item.name)) },
    valid() {
      return !this.modelValue.enabled || (!this.loading && !this.error && this.modelValue.names.length >= 1
        && this.selectedItems.length === this.modelValue.names.length)
    },
  },
  watch: {
    username: { immediate: true, handler() { this.toggle(false); this.load() } },
    valid: { immediate: true, handler(value) { this.$emit('valid', value) } },
  },
  beforeUnmount() { this.sequence++ },
  methods: {
    toggle(enabled) { this.$emit('update:modelValue', { enabled, names: [] }) },
    select(names) { this.$emit('update:modelValue', { enabled: true, names: [...names] }) },
    shortSource(source) {
      const name = String(source || '')
      return name.length > 28 ? name.slice(0, 26) + '…' : name
    },
    selectPack(group) {
      const packNames = (group.items || []).map(item => item.name)
      const merged = [...this.modelValue.names]
      packNames.forEach(name => {
        if (!merged.includes(name)) merged.push(name)
      })
      this.select(merged)
    },
    async load() {
      const sequence = ++this.sequence
      this.loading = true; this.error = ''; this.items = []
      try {
        const response = await listNotebookSkills({ username: this.username })
        if (sequence !== this.sequence) return
        if (response.error_num !== 0) throw new Error(response.msg || 'Skill 列表读取失败')
        this.items = (response.skills || []).filter(item => item.enabled && !item.orphaned && !item.missing
          && item.name !== (response.notebook_hub || 'notebook-hub') && (item.pack_zip || item.source_doc))
      } catch (error) {
        if (sequence === this.sequence) this.error = error.message || 'Skill 列表读取失败'
      } finally { if (sequence === this.sequence) this.loading = false }
    },
  },
}
</script>

<style scoped>
/* 下拉浮层挂在body；必须高于批改迭代遮罩(4000)，不改变其它选择器。 */
:global(.notebook-skill-popper) { z-index: 4100 !important; max-width: calc(100vw - 32px); }
.notebook-skill-selector { padding: 12px 0; overflow-wrap: anywhere; }
.notebook-skill-selector .el-select { width: 100%; margin-top: 10px; }
.notebook-skill-selector p { font-size: 13px; line-height: 1.6; }
.pack-select-all { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; font-size: 13px; color: #606266; }
.skill-count { color: #909399; margin-top: 6px; }
.skill-description { color: #606266; white-space: normal; }
</style>
