<template>
  <div class="workflow-step">
    <div class="step-header">
      <h2>编辑策略数据</h2>
      <p class="step-desc">编辑原始数据和格式化数据</p>
    </div>

    <div class="step-content">
      <!-- 原始数据表格 -->
      <el-card class="table-card">
        <template #header>
          <div class="card-header">
            <span>原始数据</span>
            <el-tag>{{ orderStore.currentOrder.fileName }}</el-tag>
          </div>
        </template>
        <TableEditor
          :data="originalData"
          :columns="columns"
          :editable="true"
          height="300px"
          @data-change="handleOriginalDataChange"
        />
      </el-card>

      <!-- 格式化数据表格 -->
      <el-card class="table-card">
        <template #header>
          <div class="card-header">
            <span>格式化数据</span>
            <el-button size="small" @click="formatData">重新格式化</el-button>
          </div>
        </template>
        <TableEditor
          :data="formattedData"
          :columns="columns"
          :editable="true"
          height="300px"
          @data-change="handleFormattedDataChange"
        />
      </el-card>
    </div>

    <div class="step-actions">
      <el-button @click="handlePrev">上一步</el-button>
      <div class="right-actions">
        <el-checkbox v-model="autoExecute" class="auto-execute-checkbox">
          自动执行推送
        </el-checkbox>
        <el-button @click="handleSave" :loading="saving">保存</el-button>
        <el-button type="primary" @click="handleNext" :loading="nextLoading">下一步</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import TableEditor from '@/components/TableEditor.vue'
import { useOrderStore } from '@/store/order'
import { updatePolicies } from '@/api/firewall'

const router = useRouter()
const orderStore = useOrderStore()

const originalData = ref<any[]>([])
const formattedData = ref<any[]>([])
const columns = ref<string[]>([])
const saving = ref(false)
const nextLoading = ref(false)
const autoExecute = ref(false)

onMounted(() => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传文件')
    router.push('/workflow/upload')
    return
  }

  originalData.value = [...orderStore.currentOrder.originalData]
  formattedData.value = [...orderStore.currentOrder.formattedData]
  
  // 提取列名
  if (originalData.value.length > 0) {
    columns.value = Object.keys(originalData.value[0])
  }
  
  // 如果没有格式化数据，自动格式化
  if (formattedData.value.length === 0) {
    formatData()
  }
})

const handleOriginalDataChange = (data: any[]) => {
  originalData.value = data
  orderStore.setOriginalData(data)
}

const handleFormattedDataChange = (data: any[]) => {
  formattedData.value = data
  orderStore.setFormattedData(data)
  // 同时保存到用户修改数据
  orderStore.setUserModifiedData(data)
}

const formatData = () => {
  // 简单的格式化逻辑（实际应该调用后端 API）
  formattedData.value = originalData.value.map(row => ({
    ...row
  }))
  orderStore.setFormattedData(formattedData.value)
  ElMessage.success('数据格式化完成')
}

const handleSave = async () => {
  if (!orderStore.currentOrder.orderId) return

  saving.value = true
  try {
    // 保存用户修改后的数据
    await updatePolicies(orderStore.currentOrder.orderId, {
      policies: formattedData.value
    })
    
    // 更新用户修改数据
    orderStore.setUserModifiedData(formattedData.value)
    
    ElMessage.success('保存成功')
  } catch (error) {
    console.error('Save error:', error)
    ElMessage.error('保存失败')
    throw error
  } finally {
    saving.value = false
  }
}

const handlePrev = () => {
  router.push('/workflow/upload')
}

const handleNext = async () => {
  if (formattedData.value.length === 0) {
    ElMessage.warning('请先编辑数据')
    return
  }

  nextLoading.value = true

  try {
    // 自动保存数据
    await handleSave()
    
    if (autoExecute.value) {
      // 自动执行模式：直接跳转到推送页面
      ElMessage.success('已开启自动执行，正在跳转到推送页面...')
      router.push('/workflow/push')
    } else {
      // 手动模式：跳转到预览页面
      router.push('/workflow/preview')
    }
  } catch (error) {
    console.error('Next error:', error)
    ElMessage.error('操作失败')
  } finally {
    nextLoading.value = false
  }
}
</script>

<style scoped>
.workflow-step {
  padding: 30px;
  max-width: 1400px;
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

.table-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}

.right-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.auto-execute-checkbox {
  margin-right: 10px;
}
</style>
