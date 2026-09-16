import request from '@/utils/request'


export function seed_getTopicData(formData) {
    return request.post(
        '/api/seed_getTopicData',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_getQuestionData(formData) {
    return request.post(
        '/api/seed_getQuestionData',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_integrate(formData) {
    return request.post(
        '/api/seed_integrate',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_update(formData) {
    return request.post(
        '/api/seed_update',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_delete(formData) {
    return request.post(
        '/api/seed_delete',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}