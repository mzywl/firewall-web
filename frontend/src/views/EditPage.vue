<template>
  <el-container class="edit-page">
    <el-header>
      <h2>策略编辑</h2>
      <div class="header-actions">
        <el-button @click="handleBack">返回</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
        <el-button type="success" @click="handleNext">下一步</el-button>
      </div>
    </el-header>
    
    <el-main>
      <div class="table-section">
        <el-card>
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
      </div>

      <el-divider />

      <div class="table-section">
        <el-card>
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
    </el-main>
  </el-container>
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

onMounted(() => {
  // 从 store 加载数据
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传文件')
    router.push('/upload')
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
}

const formatData = () => {
  // 简单的格式化逻辑（实际应该调用后端 API）
  formattedData.value = originalData.value.map(row => ({
    ...row,
    // 这里可以添加格式化逻辑
  }))
  orderStore.setFormattedData(formattedData.value)
  ElMessage.success('数据格式化完成')
}

const handleSave = async () => {
  if (!orderStore.currentOrder.orderId) return

  saving.value = true
  try {
    await updatePolicies(orderStore.currentOrder.orderId, {
      policies: formattedData.value
    })
    ElMessage.success('保存成功')
  } catch (error) {
    console.error('Save error:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleNext = () => {
  if (formattedData.value.length === 0) {
    ElMessage.warning('请先编辑数据')
    return
  }
  router.push('/preview')
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
</style>
