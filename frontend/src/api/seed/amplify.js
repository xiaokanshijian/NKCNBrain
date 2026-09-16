import request from '@/utils/request'


export function seed_disintegrate(formData) {
    return request.post(
        '/api/seed_disintegrate',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_addSeeds(formData) {
    return request.post(
        '/api/seed_addSeeds',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_getAllCards(formData) {
    return request.post(
        '/api/seed_getAllCards',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function seed_getAllUnprocessedCards(formData) {
    return request.post(
        '/api/seed_getAllUnprocessedCards',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}