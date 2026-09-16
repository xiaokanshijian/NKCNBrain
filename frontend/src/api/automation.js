import request from '@/utils/request'

export function saveAutomationRecords(formData) {
    return request.post(
        '/api/save_automation_records', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function startAutomation(formData) {
    return request.post(
        '/api/start_automation', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function stopAutomation(formData) {
    return request.post(
        '/api/stop_automation', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function resetAutomation(formData) {
    return request.post(
        '/api/reset_automation', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function getAutomationStatus(taskId) {
    return request.get(
        '/api/get_automation_status', 
        {
            params: { 
                task_id: taskId 
            }
        });
}

export function checkHasRecords(formData) {
    return request.post(
        '/api/check_has_records', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function getFileAutomationStatus(formData) {
    return request.post(
        '/api/get_file_automation_status', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}

export function saveFileAutomationStatus(formData) {
    return request.post(
        '/api/save_file_automation_status', 
        formData, 
        {
            headers: { 
                'Content-Type': 'multipart/form-data' 
            }
        });
}