export const STAGE_LABELS = {
  input: '原始输入',
  manifest: '任务清单',
  layout: '无损版面',
  understanding: '无损理解',
  grading: '三区批改',
  review: '模型复核',
  correction: '复核修正',
  session: '篇目切分',
  memory: '错题记忆',
  ontology_evidence: '本体证据',
  ontology: '学生本体',
  report: '整篇报告',
  verification: '规则校验',
  hallucination: '幻觉检查',
  thinking: '思维链',
  human: '人工查验',
  metadata: '元数据',
  other: '其他文件',
}

export const STAGE_ORDER = Object.keys(STAGE_LABELS)

export function normalizePath(value = '') {
  const clean = String(value).replace(/\\/g, '/').replace(/^\/+/, '')
  const parts = []
  for (const part of clean.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') {
      parts.pop()
      continue
    }
    parts.push(part)
  }
  return parts.join('/')
}

export function extractPageNumber(path = '') {
  const match = normalizePath(path).match(/_page(\d+)(?:\.|$)/i)
  return match ? Number(match[1]) : null
}

export function isFinalPageJson(path = '') {
  const name = normalizePath(path).split('/').pop() || ''
  return /_page\d+\.json$/i.test(name)
    && !/\.(?:detect|grade|review)\.json$/i.test(name)
}

export function classifyArtifact(path = '') {
  const normalized = normalizePath(path)
  const lower = normalized.toLowerCase()
  const name = lower.split('/').pop() || ''

  if (lower.endsWith('.pdf')) return 'input'
  if (name === 'manifest.json') return 'manifest'
  if (lower.endsWith('.csv') || lower.includes('/附件/') || lower.includes('/attachments/')) return 'human'
  if (name.includes('thinking') || name.endsWith('.error.txt')) return 'thinking'
  if (name.includes('.review.') || name.endsWith('.review.json') || name.includes('review.glyph')) return 'review'
  if (name.endsWith('.detect.json')) return 'layout'
  if (name.endsWith('.grade.json')) return 'understanding'
  if (isFinalPageJson(normalized)) return 'grading'
  if (name === 'corrections_applied.json' || name.includes('pass1_5')) return 'correction'
  if (name.includes('answer_statement_verification') || name.endsWith('_verification.json')) return 'verification'
  if (name.includes('hallucination')) return 'hallucination'
  if (name.includes('ontology_evidence')) return 'ontology_evidence'
  if (name.includes('ontology')) return 'ontology'
  if (name.includes('_sessions.json') || name.includes('session_rerun')) return 'session'
  if (name.includes('_memory.json')) return 'memory'
  if (name.endsWith('_report.json') || name.includes('_feedback.')) return 'report'
  if (name === 'sample_meta.json' || name.includes('rerun_manifest') || name.includes('comparison_summary')) return 'metadata'
  return 'other'
}

export function positionToBbox(position) {
  if (!Array.isArray(position) || position.length !== 4) return null
  const values = position.map(value => Number(value))
  if (values.some(value => !Number.isFinite(value))) return null
  const [x1, y1, x2, y2] = values.map(value => value / 1000)
  if (x2 <= x1 || y2 <= y1) return null
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }
}

export function artifactPageKey(path, stage) {
  const page = extractPageNumber(path)
  return page == null ? `${stage}:${normalizePath(path)}` : `${stage}:page:${page}`
}

export function verdictLabel(value) {
  return {
    correct: '正确',
    wrong: '错误',
    partial: '部分正确',
    unanswered: '未作答',
    uncertain: '待确认',
  }[value] || value || '未标记'
}
