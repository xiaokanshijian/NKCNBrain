import request from '@/utils/request'

export function getSystemChoice(data) {
    return request.post('/api/get_system_choice/', data)
}

export function setSystemChoice(data) {
    return request.post('/api/set_system_choice/', data)
}

