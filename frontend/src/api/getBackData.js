import request from '@/utils/request'

export function get_backdata(formData) {
    return request.post(
        '/api/get_backdata',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function getUseToFinetune(formData) {
    return request.post(
        '/api/getUseToFinetune',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}