import request from './request'

export interface UploadResponse {
  id: number
  order_no: string
  title: string
  description: string
  status: string
  excel_file_path: string
  created_by: string | null
  created_at: string
  updated_at: string
  original_data: any[]
  formatted_data: any[]
}

export interface UpdatePoliciesRequest {
  policies: any[]
}

// 上传文件
export const uploadFile = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post<UploadResponse>('/orders/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

// 更新策略数据
export const updatePolicies = (orderId: string, data: UpdatePoliciesRequest) => {
  return request.put(`/orders/${orderId}/policies`, data)
}

// 获取工单详情
export const getOrderDetail = (orderId: string) => {
  return request.get(`/orders/${orderId}`)
}

// 获取策略合并分析
export const getMergeAnalysis = (orderId: string) => {
  return request.post(`/push/orders/${orderId}/merge`)
}
