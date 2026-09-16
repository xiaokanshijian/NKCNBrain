import request from '@/utils/request'

export function get_usp(formData) {
    return request.post(
        '/api/user_getSceneParams',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function set_usp(formData) {
    return request.post(
        '/api/user_setSceneParams',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}