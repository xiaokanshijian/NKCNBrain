import axios from 'axios'
import API_BASE_URL from '@/config/apiConfig'

//全局参数，自定义参数可在发送请求时设置
axios.defaults.timeout = 300000000 //超时时间ms
axios.defaults.withCredentials = false
// 请求时的拦截
//回调里面不能获取错误信息
axios.interceptors.request.use(
  function (config) {

    return config;
  },
  function (error) {
    // 当请求异常时做一些处理
    console.log('请求异常：' + JSON.stringify(error));
    return Promise.reject(error);
  }
);

axios.interceptors.response.use(function (response) {
  // Do something with response data

  return response
}, function (error) {
  // Do something with response error
  console.log('响应出错：' + error)
  return Promise.reject(error)
})


const base = {
  axios: axios,
  baseUrl: API_BASE_URL,  // 统一从配置文件获取
}

export default base

// zyr7.9测试添加
const zyr_service = axios.create({
  baseURL: API_BASE_URL,  // 统一从配置文件获取
  timeout: 5000, // 请求超时时间
  withCredentials: false
});

// 请求拦截器
zyr_service.interceptors.request.use(
  config => {
    // 在发送请求之前做些什么
    config.headers['Content-Type'] = 'application/json';
    // 如果需要在请求头中添加token或其他认证信息，可以在这里添加
    // config.headers['Authorization'] = `Bearer ${yourAuthToken}`;
    return config;
  },
  error => {
    // 对请求错误做些什么
    return Promise.reject(error);
  }
);

// 响应拦截器
zyr_service.interceptors.response.use(
  response => {
    // 对响应数据做点什么
    return response;
  },
  error => {
    // 对响应错误做点什么
    return Promise.reject(error);
  }
);

// 导出一个函数，用于发送GET请求
export function get(url, params = {}) {
  return zyr_service.get(url, { params });
}

// 导出一个函数，用于发送POST请求
export function post(url, data) {
  return zyr_service.post(url, data);
}


