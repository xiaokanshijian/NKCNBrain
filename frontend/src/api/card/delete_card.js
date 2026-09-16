import request from '@/utils/request'

// 保存删除的文件记录
export function saveDeletedFiles(data) {
    return request({
        url: '/api/save_deleted_files',
        method: 'post',
        data
    })
}

// 获取删除的文件记录
export function getDeletedFiles(params) {
    return request({
        url: '/api/get_deleted_files',
        method: 'get',
        params
    })
}