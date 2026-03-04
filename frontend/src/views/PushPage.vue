<template>
  <el-container class="push-page">
    <el-header>
      <h2>策略推送</h2>
      <div class="connection-status">
        <el-tag :type="pushStore.connected ? 'success' : 'danger'" size="small">
          <el-icon><connection /></el-icon>
          {{ pushStore.connected ? '已连接' : '未连接' }}
        </el-tag>
      </div>
    </el-header>

    <el-main>
      <!-- 推送进度 -->
      <el-card class="progress-card">
        <template #header>
          <div class="card-header">
            <span>推送进度</span>
            <el-tag :type="statusType">{{ statusText }}</el-tag>
          </div>
        </template>

        <div class="progress-content">
          <el-progress
            :percentage="pushStore.progress.percentage"
            :status="progressStatus"
            :stroke-width="20"
          >
            <template #default="{ percentage }">
              <span class="progress-text">{{ percentage }}%</span>
            </template>
          </el-progress>

          <div class="progress-info">
            <span>{{ pushStore.progress.current }} / {{ pushStore.progress.total }}</span>
          </div>

          <div class="progress-actions">
            <el-button
              v-if="pushStore.isPushing"
              type="warning"
              @click="handlePause"
            >
              <el-icon><video-pause /></el-icon> 暂停
            </el-button>
            <el-button
              v-if="pushStore.isPaused"
              type="primary"
              @click="handleResume"
            >
              <el-icon><video-play /></el-icon> 继续
            </el-button>
            <el-button
              v-if="pushStore.isPushing || pushStore.isPaused"
              type="danger"
              @click="handleCancel"
            >
              <el-icon><close /></el-icon> 取消
            </el-button>
            <el-button
              v-if="!pushStore.isPushing && !pushStore.isPaused && !pushStore.isCompleted"
              type="success"
              :disabled="!pushStore.connected"
              @click="handleStart"
            >
              <el-icon><promotion /></el-icon> 开始推送
            </el-button>
            <el-button
              v-if="pushStore.isCompleted"
              type="primary"
              @click="handleViewHistory"
            >
              <el-icon><document /></el-icon> 查看历史
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- 推送日志 -->
      <el-card class="logs-card">
        <template #header>
          <div class="card-header">
            <span>推送日志</span>
            <el-button size="small" @click="handleClearLogs">清空日志</el-button>
          </div>
        </template>

        <div class="logs-container" ref="logsContainer">
          <div
            v-for="(log, index) in pushStore.logs"
            :key="index"
            :class="['log-item', `log-${log.level}`]"
          >
            <span class="log-time">{{ formatTime(log.timestamp) }}</span>
            <span class="log-level">{{ log.level.toUpperCase() }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
          <div v-if="pushStore.logs.length === 0" class="empty-logs">
            暂无日志
          </div>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  VideoPause,
  VideoPlay,
  Close,
  Promotion,
  Document
} from '@element-plus/icons-vue'
import { usePushStore } from '@/store/push'
import { useOrderStore } from '@/store/order'
import websocketService from '@/api/websocket'

const router = useRouter()
const pushStore = usePushStore()
const orderStore = useOrderStore()
const logsContainer = ref<HTMLElement>()

const statusType = computed(() => {
  switch (pushStore.progress.status) {
    case 'pushing': return 'primary'
    case 'paused': return 'warning'
    case 'completed': return 'success'
    case 'failed': return 'danger'
    default: return 'info'
  }
})

const statusText = computed(() => {
  switch (pushStore.progress.status) {
    case 'idle': return '待推送'
    case 'connecting': return '连接中'
    case 'pushing': return '推送中'
    case 'paused': return '已暂停'
    case 'completed': return '已完成'
    case 'failed': return '推送失败'
    default: return '未知'
  }
})

const progressStatus = computed(() => {
  if (pushStore.isCompleted) return 'success'
  if (pushStore.isFailed) return 'exception'
  return undefined
})

onMounted(() => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传并编辑文件')
    router.push('/upload')
    return
  }

  // 连接 WebSocket
  websocketService.connect(orderStore.currentOrder.orderId)
})

onUnmounted(() => {
  // 断开 WebSocket
  websocketService.disconnect()
})

// 自动滚动到最新日志
watch(() => pushStore.logs.length, () => {
  nextTick(() => {
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
  })
})

const handleStart = () => {
  if (!orderStore.currentOrder.orderId) return

  // 获取所有防火墙 ID（实际应该从预览页面传递）
  const firewallIds = ['firewall-1', 'firewall-2']
  
  websocketService.startPush(orderStore.currentOrder.orderId, firewallIds)
}

const handlePause = () => {
  websocketService.pausePush()
}

const handleResume = () => {
  websocketService.resumePush()
}

const handleCancel = async () => {
  try {
    await ElMessageBox.confirm('确认取消推送？', '提示', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning'
    })
    websocketService.cancelPush()
  } catch {
    // 用户取消
  }
}

const handleClearLogs = () => {
  pushStore.clearLogs()
}

const handleViewHistory = () => {
  router.push('/history')
}

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.push-page {
  height: 100vh;
  background-color: #f5f7fa;
}

.el-header {
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.el-main {
  padding: 20px;
  overflow-y: auto;
}

.progress-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-content {
  padding: 20px 0;
}

.progress-text {
  font-size: 16px;
  font-weight: bold;
}

.progress-info {
  text-align: center;
  margin: 20px 0;
  font-size: 14px;
  color: #606266;
}

.progress-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
}

.logs-card {
  height: calc(100vh - 400px);
  display: flex;
  flex-direction: column;
}

.logs-container {
  height: 100%;
  overflow-y: auto;
  background-color: #1e1e1e;
  padding: 10px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.log-item {
  padding: 4px 0;
  display: flex;
  gap: 10px;
  color: #d4d4d4;
}

.log-time {
  color: #858585;
  min-width: 80px;
}

.log-level {
  min-width: 60px;
  font-weight: bold;
}

.log-info .log-level {
  color: #4fc3f7;
}

.log-success .log-level {
  color: #66bb6a;
}

.log-warning .log-level {
  color: #ffa726;
}

.log-error .log-level {
  color: #ef5350;
}

.log-message {
  flex: 1;
}

.empty-logs {
  text-align: center;
  color: #858585;
  padding: 40px;
}
</style>
