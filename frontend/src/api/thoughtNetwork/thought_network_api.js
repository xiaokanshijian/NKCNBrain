import axios from 'axios'
import { API_BASE_URL } from '@/config/apiConfig';

// 分析思维网络
export function analyzeThoughtNetwork(userId, notebookName) {
  return axios.post(`${API_BASE_URL}/api/analyze_thought_network`, {
    user_id: userId,
    notebook_name: notebookName
  })
}

// 传播思维信号
export function propagateThoughtSignals(network, sourceNodeId) {
  return axios.post(`${API_BASE_URL}/api/propagate_thought_signals`, {
    network: network,
    source_node_id: sourceNodeId
  })
}

// 生成思维洞察
export function generateThoughtInsights(userId, notebookName, network) {
  return axios.post(`${API_BASE_URL}/api/generate_thought_insights`, {
    user_id: userId,
    notebook_name: notebookName,
    network: network
  })
}
