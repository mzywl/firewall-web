<template>
  <el-container class="edit-page">
    <el-header>
      <h2>策略编辑</h2>
      <div class="header-actions">
        <el-button @click="handleBack">返回</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </div>
    </el-header>
    
    <el-main>
      <div class="table-section">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>策略数据编辑</span>
              <el-tag>{{ orderStore.currentOrder.fileName }}</el-tag>
            </div>
          </template>
          <TableEditor
            :data="originalData"
            :columns="columns"
            :editable="true"
            height="500px"
            @data-change="handleDataChange"
          />
        </el-card>
      </div>

      <!-- 提交选项 -->
      <el-card class="submit-card">
        <el-radio-group v-model="submitMode" class="submit-options">
          <el-radio value="auto" size="large">
            <div class="option-content">
              <div class="option-title">
                <el-icon><magic-stick /></el-icon>
                自动完成（推荐）
              </div>
              <div class="option-desc">提交后自动执行：预览 → 推送 → 完成</div>
            </div>
          </el-radio>
          <el-radio value="manual" size="large">
            <div class="option-content">
              <div class="option-title">
                <el-icon><guide /></el-icon>
                手动下一步
              </div>
              <div class="option-desc">进入预览页面，每一步手动确认</div>
            </div>
          </el-radio>
        </el-radio-group>

        <div class="submit-actions">
          <el-button 
            type="success" 
            size="large" 
            @click="handleSubmit"
            :loading="submitting"
          >
            <el-icon><check /></el-icon>
            {{ submitMode === 'auto' ? '提交并自动完成' : '下一步：预览' }}
          </el-button>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Guide, Check } from '@element-plus/icons-vue'
import TableEditor from '@/components/TableEditor.vue'
import { useOrderStore } from '@/store/order'
import { updatePolicies } from '@/api/firewall'
import websocketService from '@/api/websocket'

const router = useRouter()
const orderStore = useOrderStore()

const originalData = ref<any[]>([])
const columns = ref<string[]>([])
const saving = ref(false)
const submitting = ref(false)
const submitMode = ref<'auto' | 'manual'>('auto')

onMounted(() => {
  // 从 store 加载数据
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传文件')
    router.push('/upload')
    return
  }

  originalData.value = [...orderStore.currentOrder.originalData]
  
  // 提取列名
  if (originalData.value.length > 0) {
    columns.value = Object.keys(originalData.value[0])
  }
})

const handleDataChange = (data: any[]) => {
  originalData.value = data
  orderStore.setOriginalData(data)
  orderStore.setFormattedData(data) // 简化：直接使用编辑后的数据
}

const handleSave = async () => {
  if (!orderStore.currentOrder.orderId) return

  saving.value = true
  try {
    await updatePolicies(orderStore.currentOrder.orderId, {
      policies: originalData.value
    })
    ElMessage.success('保存成功')
  } catch (error) {
    console.error('Save error:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleSubmit = async () => {
  if (originalData.value.length === 0) {
    ElMessage.warning('请先编辑数据')
    return
  }

  // 先保存数据
  await handleSave()

  submitting.value = true

  try {
    if (submitMode.value === 'auto') {
      // 自动完成模式
      await ElMessageBox.confirm(
        '确认提交并自动完成？系统将自动执行预览、推送等所有步骤。',
        '自动完成确认',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          type: 'info'
        }
      )

      // 连接 WebSocket
      websocketService.connect(orderStore.currentOrder.orderId!)
      
      // 等待连接成功
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      // 开始自动推送
      const firewallIds = ['firewall-1', 'firewall-2'] // 实际应该从数据中提取
      websocketService.startPush(orderStore.currentOrder.orderId!, firewallIds)
      
      ElMessage.success('已开始自动推送，请稍候...')
      
      // 跳转到推送页面查看进度
      router.push('/push')
    } else {
      // 手动模式：跳转到预览页面
      router.push('/preview')
    }
  } catch {
    // 用户取消
  } finally {
    submitting.value = false
  }
}

const handleBack = () => {
  router.back()
}
</script>

<style scoped>
.edit-page {
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

.header-actions {
  display: flex;
  gap: 10px;
}

.el-main {
  padding: 20px;
  overflow-y: auto;
}

.table-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.submit-card {
  max-width: 800px;
  margin: 0 auto;
}

.submit-options {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.submit-options :deep(.el-radio) {
  width: 100%;
  height: auto;
  padding: 20px;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
  margin-right: 0;
  transition: all 0.3s;
}

.submit-options :deep(.el-radio:hover) {
  border-color: #409eff;
  background-color: #f0f9ff;
}

.submit-options :deep(.el-radio.is-checked) {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.option-content {
  margin-left: 10px;
}

.option-title {
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.option-desc {
  font-size: 13px;
  color: #909399;
}

.submit-actions {
  margin-top: 30px;
  text-align: center;
}
</style>
