/**
 * DMT分析相关的API接口
 */
import request from '@/utils/request'
import axios from 'axios'
import API_BASE_URL from '@/config/apiConfig'

/**
 * 启动DMT分析
 * @param {FormData} formData - 包含username, image, config文件的FormData
 * @returns {Promise} API响应
 */
export function startDMTAnalysis(formData) {
  // 使用原生axios避免request.js的Content-Type拦截器影响
  return axios.post(`${API_BASE_URL}/api/start_dmt_analysis`, formData, {
    timeout: 300000000,
    withCredentials: false
  }).then(response => response.data);
}

/**
 * 获取DMT分析状态
 * @param {string} taskId - 任务ID
 * @returns {Promise} API响应
 */
export function getDMTAnalysisStatus(taskId) {
  return request.get(
    `/api/get_dmt_analysis_status?task_id=${taskId}`
  );
}

/**
 * 获取DMT分析结果
 * @param {string} taskId - 任务ID
 * @returns {Promise} API响应
 */
export function getDMTAnalysisResult(taskId) {
  return request.get(
    `/api/get_dmt_analysis_result?task_id=${taskId}`
  );
}

/**
 * 停止DMT分析
 * @param {string} taskId - 任务ID
 * @returns {Promise} API响应
 */
export function stopDMTAnalysis(taskId) {
  const formData = new FormData();
  formData.append('task_id', taskId);
  
  // 使用原生axios避免request.js的Content-Type拦截器影响
  return axios.post(`${API_BASE_URL}/api/stop_dmt_analysis`, formData, {
    timeout: 300000000,
    withCredentials: false
  }).then(response => response.data);
} 