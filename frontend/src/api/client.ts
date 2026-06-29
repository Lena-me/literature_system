import axios from 'axios'
import { ElMessage } from 'element-plus'

export const API_PREFIX = '/api/v1'

export const http = axios.create({
  baseURL: API_PREFIX,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' }
})

http.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  response => response.data,
  error => {
    const status = error?.response?.status
    const detail = error?.response?.data?.detail || error?.message || '请求失败'

    if (status === 401) {
      localStorage.removeItem('access_token')
      if (!location.pathname.includes('/login')) location.href = '/login'
    } else if (status === 403) {
      ElMessage.error(typeof detail === 'string' ? detail : 'No permission to access this resource')
      return Promise.reject(error)
    }

    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    return Promise.reject(error)
  }
)

export async function rawDownload(url: string, params?: Record<string, any>) {
  const token = localStorage.getItem('access_token')

  try {
    return await axios.get(`${API_PREFIX}${url}`, {
      params,
      responseType: 'blob',
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
  } catch (error: any) {
    const blob = error?.response?.data

    if (blob instanceof Blob) {
      try {
        const text = await blob.text()
        const json = JSON.parse(text)
        error.response.data = json
      } catch {
        // 如果不是 JSON，保留原始 blob 错误。
      }
    }

    throw error
  }
}
