// Resolve evidence against actual page-local IDs; never interpret a bare ID as a page.
export function resolveHomeworkEvidencePage(value, pages) {
  if (typeof value !== 'string' && typeof value !== 'number') return -1
  const ref = String(value).trim()
  if (!ref || !Array.isArray(pages)) return -1
  const match = ref.match(/^p([1-9]\d*):([^\s:]+)$/i)
  const id = match ? match[2] : ref
  if (!match && ref.includes(':')) return -1
  const candidates = []
  pages.forEach((page, index) => {
    if (match && Number(page.page) !== Number(match[1])) return
    const questions = Array.isArray(page.questions) ? page.questions : []
    questions.forEach(question => {
      if (String(question.id) === id) candidates.push(index)
    })
  })
  return candidates.length === 1 ? candidates[0] : -1
}
