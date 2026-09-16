import request from '@/utils/request'

export function card_upload(formData) {
    return request.post(
        '/api/card_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_fill_semantic_keywords(formData) {
    return request.post(
        '/api/card_fill_semantic_keywords',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

// NOTE: 25-05-27新增
export function card_updateContentById(formData) {
    return request.post(
        '/api/card_updateContentById',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_score(formData) {
    return request.post(
        '/api/card_score',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function qa_upload(formData) {
    return request.post(
        '/api/qa_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function good_data_upload(formData) {
    return request.post(
        '/api/good_data_upload',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_eval(formData) {
    return request.post(
        '/api/card_eval',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_evalSFT(formData) {
    return request.post(
        '/api/card_evalSFT',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}