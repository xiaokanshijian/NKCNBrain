import request from '@/utils/request'
import axios from 'axios';
import API_BASE_URL from '@/config/apiConfig'

// export function mergeCardBackend(cardIndexList)
// {
//     return request(
//         {
//             url: '/api/mergeCardBackend',
//             method: 'get',
//             params: {cardIndexList}
//         }
//     )
// }

export function mergeCardBackend(formData) {
    return request.post(
        '/api/mergeCardBackend',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function chageContent(formData) {
    return request.post(
        '/api/chageContent',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function changeInterGrowthForUser(formData) {
    return request.post(
        '/api/changeInterGrowthForUser',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function changeInterGrowth(formData) {
    return request.post(
        '/api/changeInterGrowth',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getAIFeedback(formData) {
    return request.post(
        '/api/getAIFeedback',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getAIModification(formData) {
    return request.post(
        '/api/getAIModification',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function generateComprehensiveAdvice(formData) {
    return request.post(
        '/api/generateComprehensiveAdvice',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function deleteChoosedCard(cid) {
    return request(
        {
            url: '/api/deleteChoosedCard',
            method: 'get',
            params: { cid }
        }
    )
}

export function cardUserDefine(formData) {
    return request.post(
        '/api/cardUserDefine',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}
export function getSubScene(formData) {
    return request.post(
        '/api/getSubScene',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}
export function changeText(formData) {
    return request.post(
        '/api/changeText',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function setNewSubExcel(formData) {
    return request.post(
        '/api/setNewSubExcel',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function react(formData) {
    return request.post(
        '/api/react',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

// export function addCardDirect(formData) {
//     return request.post(
//         '/api/add_card_directly',
//         formData,
//         {
//             headers: {
//                 'Content-Type': 'multipart/form-data'
//             }
//         });
// }
export function addCardDirect(formData) {
    // 创建一个新的、不带拦截器的axios实例，否则会被request.js将类型统一变为application/json，无法传图片
    const fileUploadRequest = axios.create({
        baseURL: API_BASE_URL,  // 统一从配置文件获取
        timeout: 300000000
    });
    
    // 使用这个新实例发送请求
    return fileUploadRequest.post(
        '/api/add_card_directly',
        formData
    );
}

export function multiQAScore(formData) {
    return request.post(
        '/api/get_multiQA_score',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function multiQAScorePlus(formData) {
    return request.post(
        '/api/get_multiQA_score_plus',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateComment(formData) {
    return request.post(
        '/api/updateComment',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getComment(formData) {
    return request.post(
        '/api/getComment',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function merge2Responses(formData) {
    return request.post(
        '/api/merge2Responses',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getCardsContentByIds(formData) {
    return request.post(
        '/api/getCardsContentByIds',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getCardHistory(formData) {
    return request.post(
        '/api/getCardHistory',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getLastContent(formData) {
    return request.post(
        '/api/getLastContent',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function cardTidyUpById(formData) {
    return request.post(
        '/api/card_tidyUpById',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function card_updateType(formData) {
    return request.post(
        '/api/card_updateType',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function cardUpdPostIndex(formData) {
    return request.post(
        '/api/card_updatePostIndex',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function backCardVersion(formData) {
    return request.post(
        '/api/card_backVersionById',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}