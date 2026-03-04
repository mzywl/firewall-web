import request from './request'

export interface UploadResponse {
  orderId: string
  fileName: string
  originalData: any[]
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
