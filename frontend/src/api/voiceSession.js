import { API_BASE_URL } from '@/config/apiConfig'

export async function requestVoiceSession(service) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 15000)
  try {
    const endpoint = process.env.VUE_APP_VOICE_SESSION_URL || API_BASE_URL + '/api/voice/session'
    const separator = endpoint.includes('?') ? '&' : '?'
    const response = await fetch(endpoint + separator + 'service=' + encodeURIComponent(service), {
      credentials: 'include',
      signal: controller.signal
    })
    const data = await response.json()
    if (!response.ok || data.error_num !== 0) throw new Error(data.msg || '语音服务不可用')
    const url = new URL(data.url)
    const expectedHost = service === 'iat' ? 'iat-api.xfyun.cn' : 'tts-api.xfyun.cn'
    if (url.protocol !== 'wss:' || url.hostname !== expectedHost || !data.app_id) {
      throw new Error('语音服务返回了无效的连接信息')
    }
    return data
  } finally {
    clearTimeout(timer)
  }
}
