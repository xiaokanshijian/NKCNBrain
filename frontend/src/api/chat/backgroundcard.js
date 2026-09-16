import request from '@/utils/request'


export function generate_bgc(formData) {
    return request.post(
        '/api/generate_bgc',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function send_bgc_card(formData) {
    return request.post(
        '/api/send_bgc_card',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_bgc_card(formData) {
    return request.post(
        '/api/get_bgc_card',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}


export function update_bgc_card(formData) {
    return request.post(
        '/api/update_bgc_card',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function delete_bgc_card(formData) {
    return request.post(
        '/api/delete_bgc_card',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

