import request from '@/utils/request'
import { API_BASE_URL } from '@/config/apiConfig';

export function get_files(formData) {
    return request.post(
        '/api/card_getAllUserFiles',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_file_summary(formData) {  // 添加 windowId 参数
    // 创建中断控制器用于超时处理
    const controller = new AbortController();
    // 设置超时（原配置 300,000,000ms ≈ 3.5天）
    const timeoutId = setTimeout(() => {
        controller.abort();
        console.error('Request timed out');
    }, 300000000);

    console.log("查看内容", formData)

    return fetch(`${API_BASE_URL}/api/get_file_summary`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
        credentials: 'omit',
    }).finally(() => {
        clearTimeout(timeoutId);
    });
}

export function get_file_topics(formData) {
    return request.post(
        '/api/card_getFileByName',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_file_text(formData) {
    return request.post(
        '/api/card_getTextByName',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_img_text(formData) {
    return request.post(
        '/api/card_getImgText',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

// NOTE: 25-05-27新增
export function update_img_text(formData) {
    return request.post(
        '/api/card_updateImgText',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function update_img_text_stream(formData) {  // 添加 windowId 参数
    // 创建中断控制器用于超时处理
    const controller = new AbortController();
  
    // 设置超时（原配置 300,000,000ms ≈ 3.5天）
    const timeoutId = setTimeout(() => {
        controller.abort(); // 中断请求
        console.error('Request timed out');
    }, 300000000);
  
    console.log("查看内容", formData)
  
    return fetch(`${API_BASE_URL}/api/update_img_text_stream`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,  // 绑定中断信号
        credentials: 'omit',        // 对应 withCredentials: false
    }).finally(() => {
        clearTimeout(timeoutId); // 清除超时定时器
    });
}

export function topic_getRelQuestions(formData) {
    return request.post(
        '/api/topic_getRelQuestions',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_cards(formData) {
    return request.post(
        '/api/card_getAllUserCards',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_filtered_cards(formData) {
    return request.post(
        '/api/card_getFilteredCards',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_card(formData) {
    return request.post(
        '/api/card_getCardById',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function set_card(formData) {
    return request.post(
        '/api/card_setCardById',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function semantic_reorganize_start(body) {
    return request.post('/api/semantic_reorganize_start', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function semantic_reorganize_status(params) {
    return request.get('/api/semantic_reorganize_status', { params });
}

export function semantic_reorganize_rollback(body) {
    return request.post('/api/semantic_reorganize_rollback', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_generate_four_color_images(body) {
    return request.post('/api/card_generate_four_color_images', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_get_image_generating_status(params) {
    return request.get('/api/card_get_image_generating_status', { params });
}

export function card_get_html_generating_status(params) {
    return request.get('/api/card_get_html_generating_status', { params });
}

export function card_generate_single_card_image(body) {
    return request.post('/api/card_generate_single_card_image', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_iterate_card_image(body) {
    return request.post('/api/card_iterate_card_image', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_generate_overlay_test_layer(body) {
    return request.post('/api/card_generate_overlay_test_layer', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_get_overlay_test_layer_status(params) {
    return request.get('/api/card_get_overlay_test_layer_status', { params });
}

export function card_get_overlay_test_base_image(params) {
    return request.get('/api/card_get_overlay_test_base_image', { params });
}

export function card_get_overlay_test_history(params) {
    return request.get('/api/card_get_overlay_test_history', { params });
}

export function card_overlay_submit_qa_composite(body) {
    return request.post('/api/card_overlay_submit_qa_composite', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}
export function card_overlay_skip_qa_composite(body) {
    return request.post('/api/card_overlay_skip_qa_composite', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_save_overlay_custom_base_image(body) {
    return request.post('/api/card_save_overlay_custom_base_image', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}
export function card_save_overlay_custom_base_image_file(formData) {
    // request.js 的拦截器会强制改成 application/json，这里改用 fetch 直传 multipart/form-data
    return fetch(`${API_BASE_URL}/api/card_save_overlay_custom_base_image`, {
        method: 'POST',
        body: formData,
        credentials: 'omit',
    })
        .then(async (res) => {
            let data = {}
            try {
                data = await res.json()
            } catch (e) {
                data = { error_num: 1, msg: `HTTP ${res.status}` }
            }
            return { data }
        })
}

/** 手动编辑后写回 cardImage：target 为 prev | current */
export function card_save_overlay_layer_file(body) {
    return request.post('/api/card_save_overlay_layer_file', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** Gemini 生掩膜图 + OpenCV 提框；body 需含 username、cid、overlay_image；掩膜写入 cardImage/{cid}.overlay_redmask.png */
export function card_overlay_detect_red_boxes_json(body) {
    return request.post('/api/card_overlay_detect_red_boxes_json', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_iterate_overlay_test_layer(body) {
    return request.post('/api/card_iterate_overlay_test_layer', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

export function card_apply_overlay_test_layer(body) {
    return request.post('/api/card_apply_overlay_test_layer', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 将卡片图片恢复为上一次「迭代图」前的备份（仅一步） */
export function card_revert_iterate_card_image(body) {
    return request.post('/api/card_revert_iterate_card_image', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 列出当前用户已完成的 CI 分析，供「图无损理解反馈迭代文本」选择 */
export function card_list_ci_analyses_for_feedback(body) {
    return request.post('/api/card_list_ci_analyses_for_feedback', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 根据所选 CI 分析结果迭代卡片正文，写回 content 并留存 lastContent */
export function card_ci_feedback_iterate_content(body) {
    return request.post('/api/card_ci_feedback_iterate_content', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 是否已有卡片 HTML（cardHtml/{cid}.html） */
export function card_html_exists(params) {
    return request.get('/api/card_html_exists', { params });
}

/** 生成卡片 HTML（Claude Opus 4.7），body: username, cid, filenamelist?, leftSelectList?, rightSelectList?, choosedCardIdList? */
export function card_html_generate(body) {
    return request.post('/api/card_html_generate', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 迭代现有卡片 HTML（微调 body 文字，覆盖前备份 lastVersion） */
export function card_html_iterate(body) {
    return request.post('/api/card_html_iterate', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 回退到 lastVersion 留存的上一版 HTML */
export function card_html_revert(body) {
    return request.post('/api/card_html_revert', body, {
        headers: { 'Content-Type': 'application/json' }
    });
}

/** 获取已保存 HTML 原文（JSON） */
export function card_html_raw(params) {
    return request.get('/api/card_html_raw', { params });
}