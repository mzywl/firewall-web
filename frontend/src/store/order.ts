import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PolicyRow {
  [key: string]: any
}

export interface OrderData {
  orderId: string | null
  originalData: PolicyRow[]        // 原始表格（用户上传的 Excel）
  formattedData: PolicyRow[]       // 格式化表格（第一次自动格式化）
  userModifiedData: PolicyRow[]    // 用户修改表格（用户在编辑页面修改后）
  fileName: string
}

export const useOrderStore = defineStore('order', () => {
  const currentOrder = ref<OrderData>({
    orderId: null,
    originalData: [],
    formattedData: [],
    userModifiedData: [],
    fileName: ''
  })

  const setOrderId = (id: string) => {
    currentOrder.value.orderId = id
  }

  const setFileName = (name: string) => {
    currentOrder.value.fileName = name
  }

  const setOriginalData = (data: PolicyRow[]) => {
    currentOrder.value.originalData = data
  }

  const setFormattedData = (data: PolicyRow[]) => {
    currentOrder.value.formattedData = data
  }

  const setUserModifiedData = (data: PolicyRow[]) => {
    currentOrder.value.userModifiedData = data
  }

  const clearOrder = () => {
    currentOrder.value = {
      orderId: null,
      originalData: [],
      formattedData: [],
      userModifiedData: [],
      fileName: ''
    }
  }

  return {
    currentOrder,
    setOrderId,
    setFileName,
    setOriginalData,
    setFormattedData,
    setUserModifiedData,
    clearOrder
  }
})
