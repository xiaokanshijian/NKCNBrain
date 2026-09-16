import request from '@/utils/request'
import axios from 'axios'
import { API_BASE_URL } from '@/config/apiConfig';

export function exportUserData(formData) {
    // return request.post(
    //     '/api/export_user_data/', 
    //     formData, 
    //     {
    //         headers: { 
    //             'Content-Type': 'multipart/form-data' 
    //         },
    //         responseType: 'blob'  // 重要：用于下载文件
    //     });
    
    // 🔥 使用axios直接请求，绕过request拦截器，避免Content-Type被覆盖和响应处理问题
    return axios.post(
        `${API_BASE_URL}/api/export_user_data/`,
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            },
            responseType: 'blob',  // 重要：用于下载文件
            timeout: 300000000,  // 5分钟超时（大文件可能需要更长时间）
            withCredentials: false
        });
}


// 文件上传直接使用axios，绕过request拦截器
export function importUserData(formData) {
    return axios.post(
        `${API_BASE_URL}/api/import_user_data/`,
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            },
            timeout: 300000000,
            withCredentials: false
        });
}