import axios from 'axios'

const DEFAULT_TASK_TYPE = 'copd'
const DEFAULT_MODALITY = 'breath'

function buildRespllmPayload(params) {
  const raw = params.metadata && typeof params.metadata === 'object' ? params.metadata : {}
  const task_type = (raw.task_type && String(raw.task_type).trim()) || DEFAULT_TASK_TYPE
  const modality = (raw.modality && String(raw.modality).trim()) || DEFAULT_MODALITY
  const audio_filename = (params.audioFile && params.audioFile.name) ? params.audioFile.name : 'audio.wav'
  const metadata = {}
  if (raw.gender != null && String(raw.gender).trim()) metadata.gender = String(raw.gender).trim()
  if (raw.age != null && String(raw.age).trim()) metadata.age = String(raw.age).trim()
  if (raw.symptoms != null && String(raw.symptoms).trim()) metadata.symptoms = String(raw.symptoms).trim()
  if (raw.medhistory != null && String(raw.medhistory).trim()) metadata.medhistory = String(raw.medhistory).trim()
  return { task_type, modality, audio_filename, metadata }
}

export function callMultimodalLittleModel(params) {
  const username = localStorage.getItem('userId') || ''
  const { task_type, modality, audio_filename, metadata } = buildRespllmPayload(params)
  metadata.model_id = params.model_id

  const formData = new FormData()
  if (params.audioFile) {
    const file = params.audioFile
    const blob = file instanceof Blob ? file : new Blob([file])
    formData.append('audio', new File([blob], audio_filename, { type: file.type || 'audio/wav' }))
  }
  formData.append('task_type', task_type)
  formData.append('modality', modality)
  formData.append('audio_filename', audio_filename)
  formData.append('metadata', JSON.stringify(metadata))
  if (params.userText) formData.append('user_text', params.userText)
  if (username) formData.append('username', username)

  try {
    console.log('[multimodal_little_model] request payload keys:', {
      task_type,
      modality,
      has_audio: !!params.audioFile,
      metadata_keys: Object.keys(metadata || {}),
      has_user_text: !!params.userText,
      has_username: !!username
    })
  } catch (e) {}

  const apiUrl = 'http://192.0.2.1:8000/respllm/predict'
  return axios.post(apiUrl, formData, {
    headers: { 'Content-Type': 'multipart/form-data', 'Connection': 'close' },
    timeout: 60000,
    validateStatus: (status) => status === 200 || status === 500
  }).then(response => {
    const data = response.data
    if (response.status === 500) {
      const result = (data && (data.prediction_result || data.result)) || data
      const hasResult = result && (result.prediction != null || result.answer != null || (typeof result === 'object' && (result.prediction || result.explanation || result.confidence != null)))
      if (hasResult) return data
      const msg = (data && (data.error || data.message || data.msg || data.detail)) || '服务器错误'
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
    return data || response
  }).catch(error => {
    if (error.response) {
      const data = error.response.data
      const msg = (data && (data.error || data.message || data.msg || data.detail)) || '服务器错误'
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
    if (error.request) throw new Error('网络请求失败，请检查网络连接')
    throw new Error(error.message || '未知错误')
  })
}

export function formatMultimodalLittleModelResult(result, model_id, metadata = {}) {
  if (!result) return ''
  let data = result
  if (result && result.data) data = result.data
  let formattedText = ''
  if (model_id === '4001') {
    formattedText = '多模态小模型(RespLLM)分析结果：\n'
    if (metadata && Object.keys(metadata).length > 0) {
      formattedText += '\n--- 用户信息 ---\n'
      if (metadata.gender) formattedText += `性别: ${metadata.gender}\n`
      if (metadata.age) formattedText += `年龄: ${metadata.age}\n`
      if (metadata.symptoms) formattedText += `症状: ${metadata.symptoms}\n`
      if (metadata.medhistory) formattedText += `病史: ${metadata.medhistory}\n`
      if (metadata.task_type) formattedText += `任务类型: ${metadata.task_type}\n`
      if (metadata.modality) formattedText += `音频模态: ${metadata.modality}\n`
      formattedText += '\n'
    }
    formattedText += '--- 预测结果 ---\n'
    const resultData = data.prediction_result || data.result
    if (resultData) {
      if (resultData.prediction) formattedText += `预测: ${resultData.prediction}\n`
      if (resultData.confidence !== undefined) formattedText += `置信度: ${(resultData.confidence * 100).toFixed(2)}%\n`
      if (resultData.explanation) formattedText += `解释: ${resultData.explanation}\n`
      if (resultData.recommendation) formattedText += `建议: ${resultData.recommendation}\n`
    } else {
      formattedText += JSON.stringify(data)
    }
  } else if (model_id === '4002') {
    formattedText = '多模态小模型(CaReAQA)分析结果：\n'
    if (metadata && Object.keys(metadata).length > 0) {
      formattedText += '\n--- 用户信息 ---\n'
      if (metadata.gender) formattedText += `性别: ${metadata.gender}\n`
      if (metadata.age) formattedText += `年龄: ${metadata.age}\n`
      if (metadata.symptoms) formattedText += `症状: ${metadata.symptoms}\n`
      if (metadata.medhistory) formattedText += `病史: ${metadata.medhistory}\n`
      if (metadata.task_type) formattedText += `任务类型: ${metadata.task_type}\n`
      if (metadata.modality) formattedText += `音频模态: ${metadata.modality}\n`
      formattedText += '\n'
    }
    formattedText += '--- 回答结果 ---\n'
    if (data.result && data.result.answer) {
      if (data.result.question) formattedText += `问题: ${data.result.question}\n`
      formattedText += `回答: ${data.result.answer}\n`
    } else if (data.answer) {
      formattedText += `回答: ${data.answer}\n`
    } else if (data.content) {
      formattedText += `回答: ${data.content}\n`
    } else {
      formattedText += JSON.stringify(data)
    }
  } else {
    formattedText = JSON.stringify(data)
  }
  return formattedText
}
