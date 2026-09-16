import request from '@/utils/request'

export function test(formData) {
    return request.post(
        '/api/test',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function test_upload_audio(formData) {
    return request.post(
        '/api/upload_audio',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function test_get_speech_text(formData) {
    return request.post(
        '/api/get_speech_text',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}