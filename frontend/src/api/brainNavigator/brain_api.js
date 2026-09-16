import request from '@/utils/request'

// 分析思维状态
export function analyzeThinkingState(data) {
  return request({
    url: '/api/analyze_thinking_state',
    method: 'post',
    data: data
  })
}

// 生成四色语境导航
export function generateContextNavigation(data) {
  return request({
    url: '/api/generate_context_navigation',
    method: 'post',
    data: data
  })
}

// 获取智能行动建议
export function getActionSuggestions(data) {
  return request({
    url: '/api/get_action_suggestions',
    method: 'post',
    data: data
  })
}

// 获取真实聊天历史
export function getRealChatHistory(data) {
  return request({
    url: '/api/get_real_chat_history',
    method: 'post',
    data: data
  })
}
