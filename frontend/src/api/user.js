import { loginSession } from '@/api/authSession'
import request from '@/utils/request'

export function getList() {
  return request({
    url: '/api/show_users',
    method: 'get',
  })
}

export function addUser(username, password, level, coacher) {
  return request({
    url: '/api/add_user',
    method: 'get',
    params: { username, password, level, coacher }
  })
}

export function verifyUser(username, password, choose) {
  return loginSession(username, password, choose)
}

export function ban_user(formData) {
  return request.post(
      '/api/ban_user/',
      formData,
      {
          headers: {
              'Content-Type': 'multipart/form-data'
          }
      });
}

export function open_user(formData) {
  return request.post(
      '/api/open_user/',
      formData,
      {
          headers: {
              'Content-Type': 'multipart/form-data'
          }
      });
}

export function user_exit(formData) {
  return request.post(
      '/api/user_exit/',
      formData,
      {
          headers: {
              'Content-Type': 'multipart/form-data'
          }
      });
}

export function get_onlineNum(formData) {
  return request.post(
      '/api/get_onlineNum/',
      formData,
      {
          headers: {
              'Content-Type': 'multipart/form-data'
          }
      });
}

export function get_userChosen(formData) {
  return request.post(
      '/api/get_userChosen/',
      formData,
      {
          headers: {
              'Content-Type': 'multipart/form-data'
          }
      });
}

// NOTE: 25-05-27新增
export function get_userUpDownLevelInfo(formData) {
    return request.post(
        '/api/get_userUpDownLevelInfo/',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
  }
  