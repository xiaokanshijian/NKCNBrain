<template>
  <div class="cs-panel-overlay">
    <aside class="cs-panel">
      <header class="cs-header">
        <div>
          <div class="cs-title">双科交叉诊断</div>
          <div class="cs-subtitle">{{ subjectPairLabel }}</div>
        </div>
        <button class="cs-close" type="button" @click="$emit('close')">×</button>
      </header>

      <div v-if="runningTask && !runningTask.completed" class="cs-progress">
        <div class="cs-progress-title">{{ runningTask.section || '处理中' }}</div>
        <div class="cs-progress-track">
          <div class="cs-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        </div>
      </div>

      <main class="cs-body">
        <section v-if="summary" class="cs-summary-card">{{ summary }}</section>

        <section v-if="transferLinks.length" class="cs-block">
          <div class="cs-block-title">跨学科迁移</div>
          <div v-for="(link, idx) in transferLinks" :key="idx" class="cs-link-item">
            <div class="cs-link-pair">
              <span class="cs-kp">{{ link.subject_a_kp }}</span>
              <span class="cs-link-arrow">⇄</span>
              <span class="cs-kp">{{ link.subject_b_kp }}</span>
            </div>
            <div class="cs-link-desc">{{ link.explanation }}</div>
          </div>
        </section>

        <section v-if="habits.length" class="cs-block">
          <div class="cs-block-title">共性学习习惯</div>
          <div v-for="(habit, idx) in habits" :key="idx" class="cs-habit-item">
            <div class="cs-habit-pattern">{{ habit.pattern }}</div>
            <div class="cs-habit-comment">{{ habit.comment }}</div>
          </div>
        </section>

        <section v-if="priority.length" class="cs-block">
          <div class="cs-block-title">练习优先级建议</div>
          <ol class="cs-priority-list">
            <li v-for="(item, idx) in priority" :key="idx" class="cs-priority-item">
              <div class="cs-priority-head">
                <span class="cs-priority-subject">{{ subjectLabel(item.subject) }}</span>
                <span class="cs-priority-kp">{{ item.knowledge_point }}</span>
              </div>
              <div class="cs-priority-action">{{ item.action }}</div>
              <div v-if="item.reason" class="cs-priority-reason">{{ item.reason }}</div>
            </li>
          </ol>
        </section>

        <div v-if="!hasContent && !(runningTask && !runningTask.completed)" class="cs-empty">暂无交叉诊断结果</div>
      </main>
    </aside>
  </div>
</template>

<script>
export default {
  name: 'CrossSubjectPanel',
  props: {
    activeResult: Object,
    runningTask: Object,
  },
  emits: ['close'],
  computed: {
    report() {
      return this.activeResult?.cross_subject_report || {}
    },
    subjectLabelMap() {
      return {
        [this.activeResult?.subject_a]: this.activeResult?.subject_a_label,
        [this.activeResult?.subject_b]: this.activeResult?.subject_b_label,
      }
    },
    subjectPairLabel() {
      const a = this.activeResult?.subject_a_label || ''
      const b = this.activeResult?.subject_b_label || ''
      return a && b ? `${a} × ${b}` : '双科交叉'
    },
    summary() {
      return this.cleanText(this.report.summary)
    },
    transferLinks() {
      return Array.isArray(this.report.transfer_links) ? this.report.transfer_links : []
    },
    habits() {
      return Array.isArray(this.report.habit_diagnosis) ? this.report.habit_diagnosis : []
    },
    priority() {
      const list = Array.isArray(this.report.priority) ? [...this.report.priority] : []
      return list.sort((a, b) => (a.rank || 99) - (b.rank || 99))
    },
    hasContent() {
      return Boolean(this.summary || this.transferLinks.length || this.habits.length || this.priority.length)
    },
    progressPercent() {
      if (!this.runningTask || !this.runningTask.total) return 8
      return Math.max(8, Math.min(100, Math.round((this.runningTask.item / this.runningTask.total) * 100)))
    },
  },
  methods: {
    cleanText(value) {
      const text = String(value || '').replace(/\s+/g, ' ').trim()
      const invalid = ['null', 'None', '无']
      return invalid.includes(text) ? '' : text
    },
    subjectLabel(subject) {
      return this.subjectLabelMap[subject] || subject || ''
    },
  },
}
</script>

<style scoped>
.cs-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 2200;
  background: rgba(10, 18, 30, 0.12);
  display: flex;
  justify-content: flex-end;
}

.cs-panel {
  width: min(680px, 92vw);
  height: 100vh;
  background: #ffffff;
  box-shadow: -10px 0 28px rgba(20, 32, 50, 0.18);
  display: flex;
  flex-direction: column;
}

.cs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #e5eaf2;
  background: #f8fafc;
}

.cs-title {
  font-size: 17px;
  font-weight: 700;
  color: #23324a;
}

.cs-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #617087;
}

.cs-close {
  width: 30px;
  height: 30px;
  border: 1px solid #d7e0ee;
  border-radius: 6px;
  background: #fff;
  color: #52627a;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.cs-progress {
  padding: 10px 18px;
  border-bottom: 1px solid #e5eaf2;
  background: #fff;
}

.cs-progress-title {
  font-size: 12px;
  color: #53647d;
  margin-bottom: 8px;
}

.cs-progress-track {
  height: 7px;
  border-radius: 999px;
  background: #e8eef6;
  overflow: hidden;
}

.cs-progress-bar {
  height: 100%;
  background: #2d6fae;
}

.cs-body {
  flex: 1;
  overflow: auto;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cs-summary-card {
  background: #f0f5fb;
  border-left: 3px solid #2d6fae;
  border-radius: 0 4px 4px 0;
  padding: 12px 14px;
  font-size: 13.5px;
  line-height: 1.75;
  color: #2a3b55;
}

.cs-block {
  border: 1px solid #e1e8f3;
  border-radius: 6px;
  padding: 13px 14px;
}

.cs-block-title {
  font-size: 13px;
  font-weight: 700;
  color: #27364f;
  margin-bottom: 10px;
}

.cs-link-item {
  border-top: 1px solid #eef2f8;
  padding: 9px 0;
}

.cs-link-item:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.cs-link-pair {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cs-kp {
  font-size: 12.5px;
  font-weight: 600;
  color: #2d3c55;
  background: #f1f5fb;
  border-radius: 4px;
  padding: 2px 8px;
}

.cs-link-arrow {
  color: #2d6fae;
  font-weight: 700;
}

.cs-link-desc {
  margin-top: 5px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #4a5870;
}

.cs-habit-item {
  border-top: 1px solid #eef2f8;
  padding: 9px 0;
}

.cs-habit-item:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.cs-habit-pattern {
  font-size: 12.5px;
  font-weight: 600;
  color: #a05a14;
}

.cs-habit-comment {
  margin-top: 4px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #4a5870;
}

.cs-priority-list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cs-priority-item {
  font-size: 12.5px;
  color: #2f3c55;
}

.cs-priority-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cs-priority-subject {
  font-size: 11px;
  color: #fff;
  background: #2d6fae;
  border-radius: 4px;
  padding: 1px 7px;
}

.cs-priority-kp {
  font-weight: 600;
}

.cs-priority-action {
  margin-top: 4px;
  line-height: 1.6;
}

.cs-priority-reason {
  margin-top: 3px;
  font-size: 11.5px;
  color: #75849b;
}

.cs-empty {
  color: #8694aa;
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}
</style>
