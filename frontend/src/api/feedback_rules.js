import request from '@/utils/request'

export function getFeedbackRules() {
  return request.get('/api/ci/feedback-rules')
}

export function getFeedbackRuleHistory(id) {
  return request.get('/api/ci/feedback-rules', { params: { history_of: id } })
}

export function rollbackFeedbackRule(id, historyId) {
  return request.post('/api/ci/feedback-rules', { id, history_id: historyId, rollback: true })
}

export function saveFeedbackRule(data) {
  return request.post('/api/ci/feedback-rules', data)
}

export function restoreFeedbackRule(id) {
  return request.post('/api/ci/feedback-rules', { id, restore_factory: true })
}

export function restoreAllBuiltinFeedbackRules() {
  return request.post('/api/ci/feedback-rules', { restore_all: true })
}

export function deleteFeedbackRule(id) {
  return request.delete('/api/ci/feedback-rules', { data: { id } })
}
