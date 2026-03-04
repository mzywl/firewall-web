import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const loading = ref(false)
  const currentUser = ref<string | null>(null)

  const setLoading = (value: boolean) => {
    loading.value = value
  }

  const setUser = (user: string | null) => {
    currentUser.value = user
  }

  return {
    loading,
    currentUser,
    setLoading,
    setUser
  }
})
