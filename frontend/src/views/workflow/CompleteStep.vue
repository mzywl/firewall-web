<template>
  <div class="workflow-step">
    <div class="step-header">
      <div class="success-icon">
        <el-icon :size="80" color="#67c23a"><circle-check /></el-icon>
      </div>
      <h2>推送完成</h2>
      <p class="step-desc">策略已成功推送到防火墙</p>
    </div>

    <div class="step-content">
      <!-- 推送结果摘要 -->
      <el-card class="summary-card">
        <template #header>
          <span>推送结果摘要</span>
        </template>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="工单号">
            {{ orderStore.currentOrder.orderId }}
          </el-descriptions-item>
          <el-descriptions-item label="文件名">
            {{ orderStore.currentOrder.fileName }}
          </el-descriptions-item>
          <el-descriptions-item label="推送状态">
            <el-tag :type="pushStore.isCompleted ? 'success' : 'danger'">
              {{ pushStore.isCompleted ? '成功' : '失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ currentTime }}
          </el-descriptions-item>
          <el-descriptions-item label="策略总数">
            {{ pushStore.progress.total }}
          </el-descriptions-item>
          <el-descriptions-item label="成功推送">
            {{ pushStore.progress.current }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 推送日志摘要 -->
      <el-card class="logs-summary-card">
        <template #header>
          <span>推送日志</span>
        </template>

        <div class="logs-summary">
          <div
            v-for="(log, index) in recentLogs"
            :key="index"
            :class="['log-item', `log-${log.level}`]"
          >
            <span class="log-time">{{ formatTime(log.timestamp) }}</span>
            <span class="log-level">{{ log.level.toUpperCase() }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <div class="step-actions">
      <el-button @click="handleViewHistory">查看历史记录</el-button>
      <el-button type="primary" @click="handleBackHome">返回首页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck } from '@element-plus/icons-vue'
import { usePushStore } from '@/store/push'
import { useOrderStore } from '@/store/order'

const router = useRouter()
const pushStore = usePushStore()
const orderStore = useOrderStore()

const currentTime = computed(() => {
  return new Date().toLocaleString('zh-CN')
})

// 最近的10条日志
const recentLogs = computed(() => {
  return pushStore.logs.slice(-10)
})

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}

const handleViewHistory = () => {
  router.push('/history')
}

const handleBackHome = () => {
  // 清空当前工单数据
  orderStore.clearOrder()
  pushStore.resetProgress()
  
  router.push('/')
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
  text-align: center;
}

.success-icon {
  margin-bottom: 20px;
}

.step-header h2 {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.step-desc {
  font-size: 16px;
  color: #67c23a;
}

.step-content {
  margin-bottom: 30px;
}

.summary-card {
  margin-bottom: 20px;
}

.logs-summary-card {
  max-height: 400px;
}

.logs-summary {
  max-height: 300px;
  overflow-y: auto;
  background-color: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.log-item {
  padding: 4px 0;
  display: flex;
  gap: 10px;
  color: #606266;
}

.log-time {
  color: #909399;
  min-width: 80px;
}

.log-level {
  min-width: 60px;
  font-weight: bold;
}

.log-info .log-level {
  color: #409eff;
}

.log-success .log-level {
  color: #67c23a;
}

.log-warning .log-level {
  color: #e6a23c;
}

.log-error .log-level {
  color: #f56c6c;
}

.log-message {
  flex: 1;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}
</style>
