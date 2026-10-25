// Public endpoint configuration; never put service credentials in VUE_APP_*.
export const API_BASE_URL = process.env.VUE_APP_API_BASE_URL || 'http://localhost:8000'
export const USE_BACKEND_DEPTH_SUGGESTION = process.env.VUE_APP_USE_BACKEND_DEPTH_SUGGESTION === 'true'
export default API_BASE_URL
