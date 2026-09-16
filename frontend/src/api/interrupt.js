import request from '@/utils/request'
import { API_BASE_URL } from '@/config/apiConfig'

const BASE_URL = API_BASE_URL; // 统一从配置文件获取

/**
 * 中断AI响应
 * @param {Object} data - 中断请求参数
 * @param {string} data.username - 用户名
 * @param {string} data.model_id - 模型ID (可选)
 * @param {string} data.session_id - 会话ID (可选，更精确)
 * @param {boolean} data.force - 是否强制中断 (默认true)
 * @returns {Promise}
 */
export function interruptResponse(data) {
    // 默认使用强制中断
    const requestData = {
        ...data,
        force: data.force !== undefined ? data.force : true
    };
    
    return request.post(
        `${BASE_URL}/api/interrupt_response`,
        requestData,
        {
            headers: {
                'Content-Type': 'application/json'
            }
        }
    );
}

/**
 * 获取活跃会话列表
 * @param {string} username - 用户名 (可选)
 * @returns {Promise}
 */
export function getActiveSessions(username = null) {
    const url = username 
        ? `${BASE_URL}/api/get_active_sessions?username=${username}`
        : `${BASE_URL}/api/get_active_sessions`;
    
    return request.get(url);
}

/**
 * 强制清理会话
 * @param {Object} data - 清理请求参数
 * @param {string} data.username - 用户名
 * @returns {Promise}
 */
export function forceCleanupSessions(data) {
    return request.post(
        `${BASE_URL}/api/force_cleanup_sessions`,
        data,
        {
            headers: {
                'Content-Type': 'application/json'
            }
        }
    );
}

/**
 * 新消息全局中断 - 中断用户所有活跃窗口
 * @param {string} username - 用户名
 * @returns {Promise}
 */
export function interruptAllOnNewMessage(username) {
    return request.post(
        `${BASE_URL}/api/interrupt_all_on_new_message`,
        { username: username },
        {
            headers: {
                'Content-Type': 'application/json'
            }
        }
    );
}

/**
 * 查询活跃会话列表（用于调试）
 * @returns {Promise}
 */
export function getActiveSessionsList() {
    return request.get(`${BASE_URL}/api/get_active_sessions`);
}
