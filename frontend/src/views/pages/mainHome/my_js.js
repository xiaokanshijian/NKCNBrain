import request from '@/utils/request'

export function addBook(username, id, bookName, description, sid, sname, isdemo) {
    return request(
        {
            url: '/api/addBook',
            method: 'get',
            params: { username, id, bookName, description, sid, sname }
        }
    )
}

export function uploadDemoNotebook(username, bookName, sid, sname) {
    return request(
        {
            url: '/api/uploadDemoNotebook',
            method: 'get',
            params: { username, bookName, sid, sname }
        }
    )
}

export function addScene(username, description) {
    return request(
        {
            url: '/api/addScene',
            method: 'get',
            params: { username, description }
        }
    )
}
export function getBookListByName(username, sid, limit = null) {
    // console.log('t1');
    let params = { username, sid };
    if (limit) {
        params.limit = limit;
    }
    return request(
        {
            url: '/api/getBookListByName',
            method: 'get',
            params: params
        }
    )
    // console.log('t2');
}

export function deleteBook(username, bookId) {
    return request(
        {
            url: '/api/deleteBook',
            method: 'get',
            params: { username, bookId }
        }
    )
}

export function makeAndGetProgressId() {
    return request(
        {
            url: '/api/makeAndGetProgressId',
            method: 'get',
        }
    )
}

export function check_load_progress(progress_id) {
    return request(
        {
            url: '/api/check_load_progress',
            method: 'get',
            params: { progress_id }
        }
    )
}

export function loadUser(originRealName, username, sceneName, progressId) {
    return request(
        {
            url: '/api/loadUser',
            method: 'get',
            params: { originRealName, username, sceneName, progressId }
        }
    )
}

export function loadUserSimplify(username) {
    return request(
        {
            url: '/api/loadUserSimplify',
            method: 'get',
            params: { username }
        }
    )
}

export function getSceneByName(username) {
    return request(
        {
            url: '/api/getSceneByName',
            method: 'get',
            params: { username }
        }
    )
}

export function getSceneSummary(formData) {
    return request.post(
        '/api/getSceneSummary',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function saveSceneExcel(formData) {
    return request.post(
        '/api/saveSceneExcel',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function saveAndReloadSceneExcel(formData) {
    return request.post(
        '/api/saveAndReloadSceneExcel',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}
export function saveSceneDoc(formData) {
    return request.post(
        '/api/saveSceneDoc',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function saveSceneDocOK(formData) {
    return request.post(
        '/api/saveSceneDocOK',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function shareBook(formData) {
    return request.post(
        '/api/shareBook',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateBookTime(formData) {
    return request.post(
        '/api/updateBookTime',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateBookDescri(formData) {
    return request.post(
        '/api/updateBookDescri',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateBookSyncUsers(formData) {
    return request.post(
        '/api/updateBookSyncUsers',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateBookSyncTodo(formData) {
    return request.post(
        '/api/updateBookSyncTodo',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function get_same_level_users(formData) {
    return request.post(
        '/api/get_same_level_users',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getFirstBookByName(formData) {
    return request.post(
        '/api/getFirstBookByName',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getSubordinatesList(formData) {
    return request.post(
        '/api/getSubordinatesList',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateUserLevel(formData) {
    return request.post(
        '/api/updateUserLevel',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function updateUserCoacher(formData) {
    return request.post(
        '/api/updateUserCoacher',
        formData,
        {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
}

export function getTaskCluster(payload) {
    return request({
        url: '/api/task_cluster_get',
        method: 'post',
        data: payload,
    });
}

export function analyzeTaskCluster(payload) {
    return request({
        url: '/api/task_cluster_analyze',
        method: 'post',
        data: payload,
    });
}

export function getTaskClusterProgress(payload) {
    return request({
        url: '/api/task_cluster_progress',
        method: 'post',
        data: payload,
    });
}

export function updateTaskClusterMeta(payload) {
    return request({
        url: '/api/task_cluster_update_meta',
        method: 'post',
        data: payload,
    });
}

export function adjustTaskClusterNotebook(payload) {
    return request({
        url: '/api/task_cluster_adjust_notebook',
        method: 'post',
        data: payload,
    });
}

export function createTaskCluster(payload) {
    return request({
        url: '/api/task_cluster_create',
        method: 'post',
        data: payload,
    });
}

export function deleteTaskCluster(payload) {
    return request({
        url: '/api/task_cluster_delete',
        method: 'post',
        data: payload,
    });
}

/** 场景/任务簇大本体语义梳理 */
export function sceneClusterSemanticStart(payload) {
    return request({
        url: '/api/scene_cluster_semantic_start',
        method: 'post',
        data: payload,
    });
}

export function sceneClusterSemanticStatus(params) {
    return request({
        url: '/api/scene_cluster_semantic_status',
        method: 'get',
        params,
    });
}

export function sceneClusterSemanticRollback(payload) {
    return request({
        url: '/api/scene_cluster_semantic_rollback',
        method: 'post',
        data: payload,
    });
}

export function sceneClusterSemanticResult(params) {
    return request({
        url: '/api/scene_cluster_semantic_result',
        method: 'get',
        params,
    });
}