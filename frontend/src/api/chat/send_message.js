import request from '@/utils/request'
import axios from 'axios';
import API_BASE_URL from '@/config/apiConfig'

// 🔥 Tab键触发小模型辅助问题补全
export function enhance_question_with_small_model(data) {
    return request.post(
        '/api/enhance_question_with_small_model',
        data,
        {
            headers: {
                'Content-Type': 'application/json'
            }
        }
    );
}

// 🔥 生成文档全面交叉梳理建议卡片
export function generate_cross_document_suggestion_card(data) {
    return request.post(
        '/api/generate_cross_document_suggestion_card',
        data,
        {
            headers: {
                'Content-Type': 'application/json'
            }
        }
    );
}

// 🔥 更新文档全面交叉梳理建议卡片
export function update_cross_document_suggestion_card(data) {
    return request.post(
        '/api/update_cross_document_suggestion_card',
        data,
        {
            headers: {
            'Content-Type': 'application/json'
            }
        }
    );
}

/** NK2026：文档交叉梳理完成后生成各组 Gxx.md 孪生 */
export function group_twin_gxx_start(data) {
    return request.post('/api/group_twin_gxx_start', data, {
        headers: { 'Content-Type': 'application/json' },
    });
}

export function get_group_twin_gxx_progress(taskId) {
    return request.get(`/api/group_twin_gxx_progress/${taskId}/`);
}

export function group_twin_gxx_list(params) {
    return request.get('/api/group_twin_gxx_list', { params });
}

export function group_twin_gxx_content(params) {
    return request.get('/api/group_twin_gxx_content', { params });
}

/** 交叉梳理成功后：后台生成 1+n Skill */
export function cross_reorganize_skills_start(data) {
    return request.post('/api/cross_reorganize_skills_start', data, {
        headers: { 'Content-Type': 'application/json' },
    });
}

export function cross_reorganize_skills_status(data) {
    return request.post('/api/cross_reorganize_skills_status', data, {
        headers: { 'Content-Type': 'application/json' },
    });
}

export function cross_reorganize_index(data) {
    return request.post('/api/cross_reorganize_index', data, {
        headers: { 'Content-Type': 'application/json' },
    });
}

export function knowledge_conflict_start(data) {
    return request.post('/api/knowledge_conflict_start', data, {
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        }
    })
}
export function knowledge_conflict_status(data) {
    return request.post('/api/knowledge_conflict_status', data, {
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        }
    })
}
export function knowledge_conflict_get(data) {
    return request.post('/api/knowledge_conflict_get', data, {
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        }
    })
}
export function knowledge_conflict_feedback(data) {
    return request.post('/api/knowledge_conflict_feedback', data, {
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        }
    })
}
export function cross_reorganize_skill_get(data) {
    return request.post('/api/cross_reorganize_skill_get', data, {
        headers: { 'Content-Type': 'application/json' },
    });
}

// export function chat_send(formData) {
//     return request.post(
//         '/api/chat_send',
//         formData,
//         {
//             headers: {
//                 'Content-Type': 'multipart/form-data'
//             }
//         });
// }

const BASE_URL = API_BASE_URL; // 统一从配置文件获取

export function chat_send(modelName, formData, windowId) {  // 添加 windowId 参数
  // 创建中断控制器用于超时处理
  const controller = new AbortController();

  // 设置超时（原配置 300,000,000ms ≈ 3.5天）
  const timeoutId = setTimeout(() => {
    controller.abort(); // 中断请求
    console.error('Request timed out');
  }, 300000000);

  console.log("查看模型调用日志情况", modelName)
  console.log("查看内容", formData)
  console.log("查看窗口ID", windowId)

  // 根据 windowId 确定 URL 后缀
  let urlSuffix = 'normal_chat_send';
  if (windowId === 'upper') {
    urlSuffix = 'normal_chat_send_up';
  } else if (windowId === 'lower') {
    urlSuffix = 'normal_chat_send_down';
  }

  // return fetch(`${BASE_URL}/api/${modelName}_chat_send`, {
  return fetch(`${BASE_URL}/api/${urlSuffix}`, {
    method: 'POST',
    body: formData,
    signal: controller.signal,  // 绑定中断信号
    credentials: 'omit',        // 对应 withCredentials: false
    // headers: {
    //   // 注意：使用 FormData 时浏览器会自动设置 Content-Type
    //   // 但为了与 Axios 版本保持一致，这里显式声明
    //   'Content-Type': 'multipart/form-data'
    // }
  }).finally(() => {
    clearTimeout(timeoutId); // 清除超时定时器
  });
//   .then(response => {
//     clearTimeout(timeoutId);  // 清除计时器
//     if (!response.ok) {
//       throw new Error(`HTTP error! status: ${response.status}`);
//     }
//     return response.json();   // 根据实际返回类型调整（如 text()）
//   })
//   .catch(error => {
//     clearTimeout(timeoutId);
//     console.error('There was a problem with the fetch operation:', error.message);
//     throw error;  // 向上抛出错误
//   });
}

export function rel_questions_request(formData) {
    return request.post(
        '/api/rel_questions_request',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_rel_questions_request(formData) {
    return request.post(
        '/api/card_rel_questions_request',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function asr_chat_send(formData) {
    return request.post(
        '/api/asr_chat_send',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function audio_stream(formData) {
    return request.post(
        '/api/chat_audio_stream',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            },
            responseType: 'arraybuffer',
        });
}

export function chat_upload(formData) {
    return request.post(
        '/api/chat_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

// 初始化文件上传任务
export function initFileUpload(formData) {
    return request.post(
        '/api/init_file_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function prompt_upload(formData) {
    return request.post(
        '/api/prompt_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function chat_switch(formData) {
    return request.post(
        '/api/chat_switch',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function chat_sendParams(formData) {
    return request.post(
        '/api/chat_sendParams',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function chat_sendSuperParams(formData) {
    return request.post(
        '/api/chat_sendSuperParams',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function img_getTopics(formData) {
    return request.post(
        '/api/img_getTopics',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function agent_LUI1(formData) {
    return request.post(
        '/api/agent_LUI1',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function agent_LUI2(formData) {
    return request.post(
        '/api/agent_LUI2',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function reget_topics(formData) {
    return request.post(
        '/api/reget_topics',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function reget_ques(formData) {
    return request.post(
        '/api/reget_ques',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function update_context(formData) {
    return request.post(
        '/api/update_context',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function get_context(formData) {
    return request.post(
        '/api/get_context',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function coacher_comment(formData) {
    return request.post(
        '/api/coacher_comment',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function execute_commands(formData) {
    return request.post(
        '/api/execute_commands',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function execute_commands_stream_sessionId(formData) {
    return request.post(
        '/api/execute_commands_stream_sessionId',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function execute_commands_stream(formData) {
    // 创建一个专用于流式请求的axios实例
    const streamRequest = axios.create({
        baseURL: API_BASE_URL,  // 统一从配置文件获取
        timeout: 300000000,
        withCredentials: false,
        responseType: 'stream' // 指定响应类型为流
    });
    
    // 请求拦截器 - 设置必要的头信息
    streamRequest.interceptors.request.use(config => {
        config.headers['Content-Type'] = 'application/json;charset=utf-8';
        return config
    }, error => {
        if (error.code === 'ECONNABORTED') {
            console.error('请求超时:', error.message);
            // 在这里可以处理超时的情况，比如重发请求
        }
        return Promise.reject(error)
    });

    return streamRequest.post(
        '/api/execute_commands_stream',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            },
            // 明确告诉axios不要处理响应数据
            transformResponse: [(data) => data]   
        });
}


export function chat_send_onlytext(formData) {
    return request.post(
        '/api/chat_send_onlytext',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


// 在API文件中添加流式调用函数
export function chat_send_onlytext_stream(formData) {
    // const BASE_URL = 'http://localhost:8000';
    // const BASE_URL = (process.env.VUE_APP_APP_URL || "http://localhost:8000");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
        console.error('Request timed out');
    }, 300000000);

    return fetch(`${BASE_URL}/api/chat_send_onlytext_stream`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
        credentials: 'omit',
    }).finally(() => {
        clearTimeout(timeoutId);
    });
}


export function nkcn_continue(formData) {
    return request.post(
        '/api/nkcn_continue',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function check_continue(formData) {
    return request.post(
        '/api/check_continue',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function question_enhance(formData) {
    return request.post(
        '/api/question_enhance',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function request_model_list(formData) {
    return request.post(
        '/api/request_model_list',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function update_model_list(formData) {
    return request.post(
        '/api/update_model_list',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function request_base_info(formData) {
    return request.post(
        '/api/request_base_info',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

/**
 * 删除模型
 * @param {FormData} formData - 包含删除模型所需信息的FormData对象
 * @returns {Promise} - 返回Promise对象，解析为删除操作的结果
 * 
 * FormData应包含：
 * - model_id: 要删除的模型ID（必需）
 * - username: 当前操作的用户名，用于权限验证（必需）
 */
export function delete_model(formData) {
    return request({
        url: '/api/delete_model/',
        method: 'post',
        data: formData,
        headers: {
            'Content-Type': 'multipart/form-data'
        }
    });
}
