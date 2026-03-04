import { io, Socket } from 'socket.io-client'
import { usePushStore } from '@/store/push'
import type { PushLog } from '@/store/push'

class WebSocketService {
  private socket: Socket | null = null
  private pushStore = usePushStore()

  connect(orderId: string) {
    if (this.socket?.connected) {
      return
    }

    // 连接到后端 WebSocket
    this.socket = io('http://localhost:8000', {
      transports: ['websocket'],
      query: { orderId }
    })

    this.setupListeners()
  }

  private setupListeners() {
    if (!this.socket) return

    // 连接成功
    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.pushStore.setConnected(true)
      this.pushStore.setStatus('connecting')
    })

    // 连接断开
    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
      this.pushStore.setConnected(false)
    })

    // 推送进度更新
    this.socket.on('push:progress', (data: { current: number; total: number }) => {
      this.pushStore.updateProgress(data.current, data.total)
      if (data.current < data.total) {
        this.pushStore.setStatus('pushing')
      }
    })

    // 推送日志
    this.socket.on('push:log', (data: PushLog) => {
      this.pushStore.addLog(data)
    })

    // 推送完成
    this.socket.on('push:completed', () => {
      this.pushStore.setStatus('completed')
      this.pushStore.addLog({
        timestamp: new Date().toISOString(),
        level: 'success',
        message: '推送完成！'
      })
    })

    // 推送失败
    this.socket.on('push:failed', (data: { error: string }) => {
      this.pushStore.setStatus('failed')
      this.pushStore.addLog({
        timestamp: new Date().toISOString(),
        level: 'error',
        message: `推送失败：${data.error}`
      })
    })

    // 错误处理
    this.socket.on('error', (error: Error) => {
      console.error('WebSocket error:', error)
      this.pushStore.addLog({
        timestamp: new Date().toISOString(),
        level: 'error',
        message: `连接错误：${error.message}`
      })
    })
  }

  // 开始推送
  startPush(orderId: string, firewallIds: string[]) {
    if (!this.socket?.connected) {
      console.error('WebSocket not connected')
      return
    }

    this.pushStore.resetProgress()
    this.pushStore.setStatus('pushing')
    
    this.socket.emit('push:start', { orderId, firewallIds })
  }

  // 暂停推送
  pausePush() {
    if (!this.socket?.connected) return
    
    this.socket.emit('push:pause')
    this.pushStore.setStatus('paused')
  }

  // 继续推送
  resumePush() {
    if (!this.socket?.connected) return
    
    this.socket.emit('push:resume')
    this.pushStore.setStatus('pushing')
  }

  // 取消推送
  cancelPush() {
    if (!this.socket?.connected) return
    
    this.socket.emit('push:cancel')
    this.pushStore.setStatus('idle')
  }

  // 断开连接
  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
      this.pushStore.setConnected(false)
    }
  }
}

export default new WebSocketService()
