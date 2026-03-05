import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface PushLog {
  timestamp: string
  level: 'info' | 'success' | 'warning' | 'error'
  message: string
}

export interface PushProgress {
  current: number
  total: number
  percentage: number
  status: 'idle' | 'connecting' | 'pushing' | 'paused' | 'completed' | 'failed'
}

export const usePushStore = defineStore('push', () => {
  const connected = ref(false)
  const logs = ref<PushLog[]>([])
  const progress = ref<PushProgress>({
    current: 0,
    total: 0,
    percentage: 0,
    status: 'idle'
  })

  const isPushing = computed(() => progress.value.status === 'pushing')
  const isPaused = computed(() => progress.value.status === 'paused')
  const isCompleted = computed(() => progress.value.status === 'completed')
  const isFailed = computed(() => progress.value.status === 'failed')

  const setConnected = (value: boolean) => {
    connected.value = value
  }

  const addLog = (log: PushLog) => {
    logs.value.push(log)
  }

  const clearLogs = () => {
    logs.value = []
  }

  const updateProgress = (current: number, total: number) => {
    progress.value.current = current
    progress.value.total = total
    progress.value.percentage = total > 0 ? Math.round((current / total) * 100) : 0
  }

  const setStatus = (status: PushProgress['status']) => {
    progress.value.status = status
  }

  const resetProgress = () => {
    progress.value = {
      current: 0,
      total: 0,
      percentage: 0,
      status: 'idle'
    }
    logs.value = []
  }

  return {
    connected,
    logs,
    progress,
    isPushing,
    isPaused,
    isCompleted,
    isFailed,
    setConnected,
    addLog,
    clearLogs,
    updateProgress,
    setStatus,
    resetProgress
  }
})
