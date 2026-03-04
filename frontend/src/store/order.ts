import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PolicyRow {
  [key: string]: any
}

export interface OrderData {
  orderId: string | null
  originalData: PolicyRow[]
  formattedData: PolicyRow[]
  fileName: string
}

export const useOrderStore = defineStore('order', () => {
  const currentOrder = ref<OrderData>({
    orderId: null,
    originalData: [],
    formattedData: [],
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

  const clearOrder = () => {
    currentOrder.value = {
      orderId: null,
      originalData: [],
      formattedData: [],
      fileName: ''
    }
  }

  return {
    currentOrder,
    setOrderId,
    setFileName,
    setOriginalData,
    setFormattedData,
    clearOrder
  }
})
