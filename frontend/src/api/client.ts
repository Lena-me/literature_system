import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { isAuthRoute, toAuthUserMessage } from '@/utils/authMessages'

export const API_PREFIX = '/api/v1'

// 响应拦截器做了 response => response.data 解包，
// 因此所有 http 方法的实际返回类型是 T 而非 AxiosResponse<T>。
// 保留第二个泛型 _D 兼容旧代码中的 http.post<any, T>(...) 写法。
interface UnwrappedInstance extends AxiosInstance {
  request<T = any, _D = any>(config: AxiosRequestConfig): Promise<T>
  get<T = any, _D = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  delete<T = any, _D = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  head<T = any, _D = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  options<T = any, _D = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any, _D = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any, _D = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  patch<T = any, _D = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
}

const rawHttp = axios.create({
  baseURL: API_PREFIX,
  timeout: 180000,
  headers: { 'Content-Type': 'application/json' },
})

/** LLM 相关接口（推荐问题、标题生成等）耗时较长 */
export const LLM_HTTP_TIMEOUT = 180000

export const http = rawHttp as UnwrappedInstance

http.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  response => response.data,
  error => {
    const status = error?.response?.status
    const rawDetail = error?.response?.data?.detail || error?.message
    const onAuthPage = isAuthRoute()
    const detail = onAuthPage
      ? toAuthUserMessage(rawDetail)
      : (rawDetail || '请求失败')

    if (status === 401) {
      localStorage.removeItem('access_token')
      if (!location.pathname.includes('/login')) location.href = '/login'
    } else if (status === 403) {
      ElMessage.error(typeof detail === 'string' ? detail : '暂无访问权限')
      return Promise.reject(error)
    }

    ElMessage.error(typeof detail === 'string' ? detail : toAuthUserMessage(detail))
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
