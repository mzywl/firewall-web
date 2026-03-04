import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

const instance: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    // Add auth token if needed
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
instance.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// 导出带类型的请求方法
export default {
  get: <T = any>(url: string, config?: AxiosRequestConfig) => 
    instance.get<T, T>(url, config),
  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) => 
    instance.post<T, T>(url, data, config),
  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) => 
    instance.put<T, T>(url, data, config),
  delete: <T = any>(url: string, config?: AxiosRequestConfig) => 
    instance.delete<T, T>(url, config)
}
