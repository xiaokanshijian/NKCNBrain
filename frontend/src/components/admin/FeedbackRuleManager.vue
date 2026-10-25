<template>
  <section class="feedback-rule-manager">
    <div class="manager-heading">
      <div>
        <h2>批改规则管理</h2>
        <p>这里的修改只影响后续采用当前规则的新运行；历史结果继续使用自身快照。</p>
      </div>
      <div class="heading-actions">
        <el-button v-if="activeTab === 'rules'" @click="restoreAllBuiltin">恢复全部内置正文</el-button>
        <el-button v-if="activeTab === 'rules'" type="primary" @click="openCreate">新增规则</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="批改规则" name="rules">
        <div class="filters">
          <el-input v-model="filters.keyword" clearable placeholder="搜索名称或正文" />
          <el-select v-model="filters.educationLevel" clearable placeholder="学段" @change="onFilterEducationLevelChange">
            <el-option v-for="item in options.education_levels" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.grade" clearable :disabled="!filters.educationLevel" placeholder="先选择学段">
            <el-option v-for="grade in filterGradeOptions" :key="grade" :label="gradeLabel(filters.educationLevel, grade)" :value="grade" />
          </el-select>
          <el-select v-model="filters.subject" clearable placeholder="学科">
            <el-option v-for="item in options.subjects" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.materialType" clearable placeholder="材料类型">
            <el-option v-for="item in options.material_types" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.usage" clearable placeholder="用途">
            <el-option v-for="item in options.usages" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <el-table v-loading="loading" :data="filteredRules" row-key="id" empty-text="没有匹配的批改规则">
          <el-table-column prop="name" label="名称" min-width="210" />
          <el-table-column label="范围" min-width="280">
            <template #default="{ row }">
              <div>{{ scopeLabel(row) }}</div>
              <div class="muted">{{ materialLabel(row) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="用途" min-width="150">
            <template #default="{ row }">{{ labels(row.usages, 'usages') }}</template>
          </el-table-column>
          <el-table-column label="来源" min-width="210">
            <template #default="{ row }">
              <el-tag size="small" :type="row.built_in ? 'info' : 'success'">
                {{ row.built_in ? '内置迁移' : '管理页新增' }}
              </el-tag>
              <div class="muted source-text">{{ sourceLabel(row) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="row.built_in" link type="warning" @click="restoreRule(row)">恢复出厂</el-button>
              <el-button v-else link type="danger" @click="removeRule(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="table-summary">显示 {{ filteredRules.length }} 条，共 {{ rules.length }} 条</div>
      </el-tab-pane>

      <el-tab-pane label="按 Skill 规范预览" name="skillmd">
        <p class="muted skill-md-hint">按本子 Skill.md 的规范结构通读当前筛选下将生效的细则。点上方节名仍打开对应条文改正文；细表本身保留。</p>
        <div class="skill-md-toc">
          <el-button v-for="row in filteredRules" :key="row.id" link type="primary" @click="openEdit(row)">{{ row.name }}</el-button>
        </div>
        <pre class="skill-md-preview">{{ skillMdPreview }}</pre>
      </el-tab-pane>

      <el-tab-pane label="其他资源与归属" name="ownership">
        <el-alert
          title="以下内容只登记归属和维护入口，不表示已经迁入本页动态管理。"
          type="info"
          :closable="false"
          show-icon
        />
        <el-table :data="ownershipItems" row-key="name" class="ownership-table">
          <el-table-column prop="name" label="资源" min-width="190" />
          <el-table-column prop="usage" label="用途" min-width="180" />
          <el-table-column prop="source" label="来源" min-width="300" />
          <el-table-column prop="owner" label="归属" min-width="180" />
          <el-table-column prop="maintenance" label="维护入口" min-width="150" />
          <el-table-column prop="status" label="状态" min-width="190" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑批改规则' : '新增批改规则'" width="min(760px, 94vw)" append-to-body>
      <el-form label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="学段">
          <el-select v-model="form.education_level" clearable :disabled="form.built_in" placeholder="不选表示不限" @change="onFormEducationLevelChange">
            <el-option v-for="item in options.education_levels" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="form.grades" multiple clearable :disabled="form.built_in || !form.education_level" :placeholder="form.education_level ? '不选表示该学段全部年级' : '请先选择学段'">
            <el-option v-for="grade in formGradeOptions" :key="grade" :label="gradeLabel(form.education_level, grade)" :value="grade" />
          </el-select>
        </el-form-item>
        <el-form-item label="学科">
          <el-select v-model="form.subjects" multiple clearable filterable :disabled="form.built_in" placeholder="不选表示不限">
            <el-option v-for="item in options.subjects" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="材料类型">
          <el-select v-model="form.material_types" multiple clearable :disabled="form.built_in" placeholder="不选表示不限">
            <el-option v-for="item in options.material_types" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="用途" required>
          <el-checkbox-group v-model="form.usages" :disabled="form.built_in">
            <el-checkbox v-for="item in options.usages" :key="item.value" :label="item.value">{{ item.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="form.built_in" label="来源">
          <div class="readonly-source">{{ sourceLabel(form) }}；范围、用途和执行条件本阶段保持只读。</div>
        </el-form-item>
        <el-form-item label="规则正文" required>
          <el-input v-model="form.body" type="textarea" :rows="12" maxlength="20000" show-word-limit />
        </el-form-item>
        <el-form-item v-if="editingId" label="历史版本">
          <div v-if="historyLoading" class="muted">正在读取历史版本…</div>
          <div v-else-if="!ruleHistory.length" class="muted">尚无历史版本。保存修改后会出现，可回滚到保存前的正文。</div>
          <ul v-else class="rule-history">
            <li v-for="item in ruleHistory" :key="item.history_id">
              <div>
                <strong>{{ formatHistoryTime(item.saved_at) }}</strong>
                <span class="muted"> · {{ item.reason_label || '保存前' }}</span>
                <div class="history-preview">{{ item.body_preview }}</div>
              </div>
              <el-button link type="primary" :disabled="rollingBack" @click="rollbackTo(item)">回滚到此版</el-button>
            </li>
          </ul>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRule">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script>
import { ElMessageBox } from 'element-plus'
import { deleteFeedbackRule, getFeedbackRuleHistory, getFeedbackRules, restoreAllBuiltinFeedbackRules, restoreFeedbackRule, rollbackFeedbackRule, saveFeedbackRule } from '@/api/feedback_rules'

const emptyForm = () => ({
  id: '',
  name: '',
  education_level: '',
  education_levels: [],
  grades: [],
  subjects: [],
  material_types: [],
  usages: ['understanding'],
  body: '',
  source: { kind: 'managed', label: '管理页新增' },
  built_in: false,
})

export default {
  name: 'FeedbackRuleManager',
  data() {
    return {
      activeTab: 'rules',
      loading: false,
      saving: false,
      dialogVisible: false,
      editingId: '',
      rules: [],
      ownershipItems: [],
      options: { education_levels: [], grades: [], subjects: [], material_types: [], usages: [] },
      filters: { keyword: '', educationLevel: '', grade: '', subject: '', materialType: '', usage: '' },
      form: emptyForm(),
      ruleHistory: [],
      historyLoading: false,
      rollingBack: false,
    }
  },
  computed: {
    filterGradeOptions() {
      return this.gradeOptionsForLevel(this.filters.educationLevel)
    },
    formGradeOptions() {
      return this.gradeOptionsForLevel(this.form.education_level)
    },
    filteredRules() {
      const keyword = this.filters.keyword.trim().toLowerCase()
      return this.rules.filter(rule => {
        if (keyword && !`${rule.name}\n${rule.body}`.toLowerCase().includes(keyword)) return false
        if (!this.scopeMatches(rule.education_levels, this.filters.educationLevel)) return false
        if (!this.scopeMatches(rule.grades, this.filters.grade)) return false
        if (!this.scopeMatches(rule.subjects, this.filters.subject)) return false
        if (!this.scopeMatches(rule.material_types, this.filters.materialType)) return false
        return !this.filters.usage || rule.usages.includes(this.filters.usage)
      })
    },
    skillMdTitle() {
      const parts = []
      if (this.filters.educationLevel) parts.push(this.optionLabel(this.filters.educationLevel, 'education_levels'))
      if (this.filters.grade && this.filters.educationLevel) parts.push(this.gradeLabel(this.filters.educationLevel, this.filters.grade))
      if (this.filters.subject) parts.push(this.optionLabel(this.filters.subject, 'subjects'))
      if (this.filters.materialType) parts.push(this.optionLabel(this.filters.materialType, 'material_types'))
      if (this.filters.usage) parts.push(this.optionLabel(this.filters.usage, 'usages'))
      return parts.length ? `${parts.join('·')}批改细则` : '作业批改内部细则'
    },
    skillMdPreview() {
      const title = this.skillMdTitle
      const groups = { layout: [], understanding: [], grading: [] }
      this.filteredRules.forEach(rule => {
        const usage = (rule.usages || [])[0]
        if (groups[usage]) groups[usage].push(rule)
        else groups.understanding.push(rule)
      })
      const lines = [
        '---',
        'name: homework-grading-skill',
        'description: 批改内部细则。按材料学段、学科、品类自动套用；内置项不可关闭。Use when 作业、试卷、作文或笔记需要版面识别、理解或批改条文。NOT for 本子教学方法包，也不可改动判分协议底座。',
        'metadata:',
        `  title: "${title}"`,
        '  source: managed_feedback_rules',
        '  standards:',
        '  - Agent Skills Spec',
        '  - NKCN',
        '---',
        '',
        `# ${title}`,
        '',
        '## 核心主张',
        '',
      ]
      const claims = this.filteredRules.filter(rule => /主张|原则|规范|总则/.test(rule.name || ''))
      if (claims.length) {
        claims.forEach(rule => {
          lines.push(`### ${rule.name}`)
          lines.push((rule.body || '').trim())
          lines.push('')
        })
      } else {
        lines.push('先依据原页可见事实，再评价、再给下一步。专项规则优先于本子方法，不得改对错判定。各用途的具体主张见下方怎么做。')
        lines.push('')
      }
      lines.push(
        '## 何时用 / 何时不用',
        '',
        '**用在这些场景**：当前范围内的作业、试卷、作文、笔记批改；版面识别、理解作答、整篇诊断与批语组织。',
        '',
        '**不用在这些场景**：改对错判定或可核对的标准答案；关闭内置细则；把本子教学方法写进对错判定；协议底座（字段结构）不在此页修改。',
        '',
        '**与相邻能力的区分**：本子 Skill 是教学方法，启动时可勾选。这里是批改准确率底座，命中材料后自动套用。',
        '',
        '## 怎么做（工作流）',
        '',
      )
      ;[['layout', '版面'], ['understanding', '理解'], ['grading', '批改']].forEach(([usage, heading]) => {
        lines.push(`### ${heading}`, '')
        if (!groups[usage].length) {
          lines.push('（当前筛选下无此用途细则）', '')
          return
        }
        groups[usage].forEach(rule => {
          lines.push(`#### ${rule.name}`)
          lines.push((rule.body || '').trim())
          lines.push('')
        })
      })
      lines.push('## 约束与输出期望', '', '专项规则优先于本子方法；不得改对错判定与可核对的标准答案。解释链用白话三问；作业/试卷单题短评不套三问。改正文只影响此后新开批改，历史批改仍用当时快照。', '')
      return lines.join('\n')
    },
  },
  mounted() {
    this.loadRules()
  },
  methods: {
    async loadRules() {
      this.loading = true
      try {
        const response = await getFeedbackRules()
        if (response?.error_num !== 0) throw new Error(response?.msg || '加载失败')
        this.rules = Array.isArray(response.rules) ? response.rules : []
        this.ownershipItems = Array.isArray(response.ownership_items) ? response.ownership_items : []
        this.options = response.options || this.options
      } catch (error) {
        this.$message.error(`加载批改规则失败：${error.message || error}`)
      } finally {
        this.loading = false
      }
    },
    scopeMatches(scope, value) {
      if (value === '' || value === null || value === undefined) return true
      return !Array.isArray(scope) || scope.length === 0 || scope.includes(value)
    },
    optionLabel(value, optionKey) {
      const item = (this.options[optionKey] || []).find(option => option.value === value)
      return item?.label || value
    },
    labels(values, optionKey) {
      return Array.isArray(values) && values.length
        ? values.map(value => this.optionLabel(value, optionKey)).join('、')
        : '不限'
    },
    scopeLabel(rule) {
      const level = Array.isArray(rule.education_levels) && rule.education_levels.length ? rule.education_levels[0] : ''
      const levelText = level ? this.optionLabel(level, 'education_levels') : '不限学段'
      const grades = Array.isArray(rule.grades) && rule.grades.length
        ? rule.grades.map(value => this.gradeLabel(level, value)).join('、')
        : '不限年级'
      return `${levelText} · ${grades} · ${this.labels(rule.subjects, 'subjects')}`
    },
    materialLabel(rule) {
      return `材料：${this.labels(rule.material_types, 'material_types')}`
    },
    sourceLabel(rule) {
      const source = rule?.source || {}
      if (source.kind === 'builtin') return `${source.skill_id || ''}/${source.rule_id || rule.id}`
      return source.label || '管理页新增'
    },
    openCreate() {
      this.editingId = ''
      this.form = emptyForm()
      this.ruleHistory = []
      this.dialogVisible = true
    },
    openEdit(rule) {
      this.editingId = rule.id
      this.form = JSON.parse(JSON.stringify(rule))
      this.form.education_level = this.form.education_levels?.[0] || ''
      this.dialogVisible = true
      this.loadHistory(rule.id)
    },
    chineseNumber(value) {
      const digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
      const number = Number(value)
      if (number <= 10) return digits[number] || String(value)
      if (number < 20) return `十${digits[number - 10]}`
      if (number === 20) return '二十'
      return String(value)
    },
    gradeLabel(level, grade) {
      const number = this.chineseNumber(grade)
      const labels = {
        primary: `小学${number}年级`,
        junior: `初${number}`,
        senior: `高${number}`,
        university: `大${number}`,
        vocational: `职教${number}年级`,
        postgraduate: `研${number}`,
        adult: `成人教育第${number}年`,
        other: `其他学段第${number}年`,
      }
      return labels[level] || `${number}年级`
    },
    gradeOptionsForLevel(level) {
      if (!level) return []
      const limits = { primary: 6, junior: 3, senior: 3 }
      const maximum = limits[level] || Math.max(...(this.options.grades || [20]))
      return (this.options.grades || []).filter(value => value <= maximum)
    },
    onFilterEducationLevelChange() {
      this.filters.grade = ''
    },
    onFormEducationLevelChange() {
      this.form.grades = []
    },
    async submitRule() {
      if (!this.form.name.trim() || !this.form.body.trim()) {
        this.$message.warning('名称和规则正文不能为空')
        return
      }
      if (!this.form.usages.length) {
        this.$message.warning('至少选择一个用途')
        return
      }
      const payload = this.form.built_in
        ? { id: this.form.id, name: this.form.name, body: this.form.body }
        : {
            ...(this.editingId ? { id: this.form.id } : {}),
            name: this.form.name,
            education_levels: this.form.education_level ? [this.form.education_level] : [],
            grades: this.form.grades,
            subjects: this.form.subjects,
            material_types: this.form.material_types,
            usages: this.form.usages,
            body: this.form.body,
          }
      this.saving = true
      try {
        const response = await saveFeedbackRule(payload)
        if (response?.error_num !== 0) throw new Error(response?.msg || '保存失败')
        this.$message.success('规则已保存；后续采用当前规则的新运行生效')
        this.dialogVisible = false
        await this.loadRules()
      } catch (error) {
        this.$message.error(`保存规则失败：${error.message || error}`)
      } finally {
        this.saving = false
      }
    },
    async loadHistory(ruleId) {
      if (!ruleId) {
        this.ruleHistory = []
        return
      }
      this.historyLoading = true
      try {
        const response = await getFeedbackRuleHistory(ruleId)
        if (response?.error_num !== 0) throw new Error(response?.msg || '读取历史失败')
        this.ruleHistory = Array.isArray(response.history) ? response.history : []
      } catch (error) {
        this.ruleHistory = []
        this.$message.error(`读取历史版本失败：${error.message || error}`)
      } finally {
        this.historyLoading = false
      }
    },
    formatHistoryTime(value) {
      const text = String(value || '').replace('T', ' ')
      return text || '未知时间'
    },
    async rollbackTo(item) {
      if (!this.editingId || !item?.history_id || this.rollingBack) return
      try {
        await ElMessageBox.confirm(
          `回滚到 ${this.formatHistoryTime(item.saved_at)} 的版本？当前正文会先存进历史，仍可再回滚。`,
          '回滚细则',
          { type: 'warning', confirmButtonText: '回滚', cancelButtonText: '取消' },
        )
      } catch (error) {
        if (error === 'cancel' || error === 'close') return
        throw error
      }
      this.rollingBack = true
      try {
        const response = await rollbackFeedbackRule(this.editingId, item.history_id)
        if (response?.error_num !== 0) throw new Error(response?.msg || '回滚失败')
        const rule = response.rule || {}
        this.form = { ...emptyForm(), ...rule, education_level: (rule.education_levels || [])[0] || '' }
        this.$message.success('已回滚；此后新开批改使用该版本正文')
        await this.loadRules()
        await this.loadHistory(this.editingId)
      } catch (error) {
        if (error === 'cancel' || error === 'close') return
        this.$message.error(`回滚失败：${error.message || error}`)
      } finally {
        this.rollingBack = false
      }
    },
    async restoreAllBuiltin() {
      try {
        await ElMessageBox.confirm(
          '将全部内置细则正文恢复为出厂 resources.texts？只影响此后新开批改。',
          '恢复全部内置正文',
          { type: 'warning', confirmButtonText: '全部恢复', cancelButtonText: '取消' },
        )
        const response = await restoreAllBuiltinFeedbackRules()
        if (response?.error_num !== 0) throw new Error(response?.msg || '恢复失败')
        this.$message.success(`已恢复 ${response.count || 0} 条内置正文`)
        await this.loadRules()
      } catch (error) {
        if (error === 'cancel' || error === 'close') return
        this.$message.error(`整包恢复失败：${error.message || error}`)
      }
    },
    async restoreRule(rule) {
      try {
        await ElMessageBox.confirm(
          `将“${rule.name}”正文恢复为内置出厂内容？只影响此后新开批改。`,
          '恢复出厂正文',
          { type: 'warning', confirmButtonText: '恢复', cancelButtonText: '取消' },
        )
        const response = await restoreFeedbackRule(rule.id)
        if (response?.error_num !== 0) throw new Error(response?.msg || '恢复失败')
        this.$message.success('已恢复出厂正文')
        await this.loadRules()
      } catch (error) {
        if (error === 'cancel' || error === 'close') return
        this.$message.error(`恢复出厂失败：${error.message || error}`)
      }
    },
    async removeRule(rule) {
      if (rule.built_in) {
        this.$message.warning('内置细则不能删除或关闭，只能编辑正文或恢复出厂')
        return
      }
      try {
        await ElMessageBox.confirm(
          `删除“${rule.name}”只影响后续采用当前规则的新运行，历史结果不会删除。确定继续吗？`,
          '删除批改规则',
          { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
        )
        const response = await deleteFeedbackRule(rule.id)
        if (response?.error_num !== 0) throw new Error(response?.msg || '删除失败')
        this.$message.success('规则已删除')
        await this.loadRules()
      } catch (error) {
        if (error === 'cancel' || error === 'close') return
        this.$message.error(`删除规则失败：${error.message || error}`)
      }
    },
  },
}
</script>

<style scoped>
.feedback-rule-manager {
  margin: 0;
  padding: 16px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
}
.manager-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.heading-actions { display: flex; gap: 8px; flex-shrink: 0; }
.manager-heading h2 { margin: 0 0 8px; }
.manager-heading p, .muted { color: #909399; font-size: 13px; }
.filters { display: grid; grid-template-columns: minmax(180px, 1.4fr) repeat(5, minmax(120px, 1fr)); gap: 10px; margin: 12px 0 18px; }
.filters :deep(.el-select) { width: 100%; }
.table-summary { margin-top: 10px; text-align: right; color: #909399; font-size: 13px; }
.source-text { margin-top: 5px; overflow-wrap: anywhere; }
.ownership-table { margin-top: 16px; }
.readonly-source { color: #606266; line-height: 1.5; }
.rule-history {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 220px;
  overflow: auto;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.rule-history li {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #ebeef5;
}
.rule-history li:last-child { border-bottom: 0; }
.history-preview {
  margin-top: 4px;
  color: #606266;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.skill-md-hint { margin: 8px 0 12px; }
.skill-md-toc { display: flex; flex-wrap: wrap; gap: 4px 8px; margin-bottom: 12px; }
.skill-md-preview {
  white-space: pre-wrap;
  word-break: break-word;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  max-height: 70vh;
  overflow: auto;
  font-size: 13px;
  line-height: 1.65;
}
:deep(.el-dialog .el-select) { width: 100%; }
@media (max-width: 1100px) {
  .filters { grid-template-columns: repeat(2, minmax(160px, 1fr)); }
}
@media (max-width: 600px) {
  .filters { grid-template-columns: minmax(0, 1fr); }
  .manager-heading { flex-wrap: wrap; gap: 10px; }
}
</style>
