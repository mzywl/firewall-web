<template>
  <div class="workflow-container">
    <!-- 左侧步骤导航 -->
    <div class="workflow-sidebar">
      <div class="workflow-header">
        <h3>防火墙策略推送</h3>
        <div class="order-info" v-if="orderStore.currentOrder.orderId">
          <span class="label">工单号：</span>
          <span class="value">{{ orderStore.currentOrder.orderId }}</span>
        </div>
      </div>

      <el-steps direction="vertical" :active="currentStepIndex" finish-status="success">
        <el-step
          v-for="(step, index) in steps"
          :key="index"
          :title="step.title"
          :description="step.description"
          :icon="step.icon"
        />
      </el-steps>
    </div>

    <!-- 右侧内容区 -->
    <div class="workflow-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Upload, Edit, View, Promotion, CircleCheck } from '@element-plus/icons-vue'
import { useOrderStore } from '@/store/order'

const route = useRoute()
const orderStore = useOrderStore()

const steps = [
  { path: '/workflow/upload', title: '上传文件', description: '上传策略文件', icon: Upload },
  { path: '/workflow/edit', title: '编辑策略', description: '编辑和修改数据', icon: Edit },
  { path: '/workflow/preview', title: '预览确认', description: '确认最终数据', icon: View },
  { path: '/workflow/push', title: '推送执行', description: '推送到防火墙', icon: Promotion },
  { path: '/workflow/complete', title: '完成', description: '查看推送结果', icon: CircleCheck }
]

const currentStepIndex = computed(() => {
  const currentPath = route.path
  const index = steps.findIndex(step => step.path === currentPath)
  return index >= 0 ? index : 0
})
</script>

<style scoped>
.workflow-container {
  display: flex;
  height: 100vh;
  background-color: #f5f7fa;
}

.workflow-sidebar {
  width: 280px;
  background-color: white;
  border-right: 1px solid #e4e7ed;
  padding: 30px 20px;
  overflow-y: auto;
}

.workflow-header {
  margin-bottom: 30px;
}

.workflow-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 15px;
}

.order-info {
  font-size: 13px;
  color: #606266;
  padding: 8px 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.order-info .label {
  color: #909399;
}

.order-info .value {
  font-weight: 500;
  color: #409eff;
}

.workflow-content {
  flex: 1;
  overflow-y: auto;
}

:deep(.el-steps) {
  padding: 0;
}

:deep(.el-step__title) {
  font-size: 15px;
  font-weight: 500;
}

:deep(.el-step__description) {
  font-size: 12px;
}
</style>
