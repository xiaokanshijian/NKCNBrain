import request from '@/utils/request'

// Only authentication endpoints opt into credentialed cross-origin requests.
async function csrfPost(url, data) {
  const result = await request({
    url: '/api/auth/csrf', method: 'get', withCredentials: true
  })
  if (!result.csrfToken) throw new Error('无法初始化登录会话，请重试')
  return request({
    url, method: 'post', data, withCredentials: true,
    headers: { 'X-CSRFToken': result.csrfToken }
  })
}

export async function loginSession(username, password, choose) {
  const result = await csrfPost('/api/verify_user', { username, password, choose })
  if (result.error_num === 0 && result.msg === 'success') {
    const session = await getLoginSession()
    if (session.error_num !== 0 || session.name !== result.name) {
      throw new Error('登录 Cookie 未生效，请检查浏览器或服务端配置')
    }
  }
  return result
}

export function getLoginSession() {
  return request({ url: '/api/auth/session', method: 'get', withCredentials: true })
}

export async function logoutSession() {
  const result = await csrfPost('/api/auth/logout', {})
  if (result.error_num !== 0) throw new Error('退出登录失败')
  return result
}
