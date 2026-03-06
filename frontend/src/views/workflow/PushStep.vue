<template>
  <div class="workflow-step">
    <div class="step-header">
      <h2>推送执行</h2>
      <p class="step-desc">正在推送策略到防火墙，请稍候...</p>
    </div>

    <div class="step-content">
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
            :stroke-width="24"
          >
            <template #default="{ percentage }">
              <span class="progress-text">{{ percentage }}%</span>
            </template>
          </el-progress>

          <div class="progress-info">
            <span>{{ pushStore.progress.current }} / {{ pushStore.progress.total }}</span>
          </div>
        </div>
      </el-card>

      <!-- 推送日志 -->
      <el-card class="logs-card">
        <template #header>
          <div class="card-header">
            <span>推送日志</span>
            <el-tag :type="pushStore.connected ? 'success' : 'danger'" size="small">
              <el-icon><connection /></el-icon>
              {{ pushStore.connected ? '已连接' : '未连接' }}
            </el-tag>
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
            等待推送开始...
          </div>
        </div>
      </el-card>
    </div>

    <div class="step-actions">
      <el-button @click="handlePrev" :disabled="pushStore.isPushing">上一步</el-button>
      <el-button 
        v-if="pushStore.isCompleted" 
        type="success" 
        @click="handleComplete"
      >
        查看结果
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection } from '@element-plus/icons-vue'
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

onMounted(async () => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传并编辑文件')
    router.push('/workflow/upload')
    return
  }

  // 连接 WebSocket
  websocketService.connect(orderStore.currentOrder.orderId)
  
  // 等待连接成功
  await new Promise(resolve => setTimeout(resolve, 1000))
  
  // 自动开始推送
  const firewallIds = ['firewall-1', 'firewall-2'] // 实际应该从数据中提取
  websocketService.startPush(orderStore.currentOrder.orderId, firewallIds)
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

// 监听推送完成，自动跳转
watch(() => pushStore.isCompleted, (completed) => {
  if (completed) {
    ElMessage.success('推送完成！')
    setTimeout(() => {
      router.push('/workflow/complete')
    }, 2000)
  }
})

const handlePrev = () => {
  router.push('/workflow/preview')
}

const handleComplete = () => {
  router.push('/workflow/complete')
}

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.workflow-step {
  padding: 30px;
  max-width: 1200px;
  margin: 0 auto;
}

.step-header {
  margin-bottom: 30px;
}

.step-header h2 {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.step-desc {
  font-size: 14px;
  color: #909399;
}

.step-content {
  margin-bottom: 30px;
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
  font-size: 18px;
  font-weight: bold;
}

.progress-info {
  text-align: center;
  margin: 20px 0;
  font-size: 14px;
  color: #606266;
}

.logs-card {
  height: 500px;
  display: flex;
  flex-direction: column;
}

.logs-card :deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.logs-container {
  height: 100%;
  overflow-y: auto;
  background-color: #1e1e1e;
  padding: 15px;
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

.step-actions {
  display: flex;
  justify-content: space-between;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}
</style>
