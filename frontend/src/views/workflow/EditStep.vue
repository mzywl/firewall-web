<template>
  <div class="workflow-step">
    <div class="step-header">
      <h2>编辑策略数据</h2>
      <p class="step-desc">查看格式化数据并进行编辑</p>
    </div>

    <div class="step-content">
      <!-- 第一次格式化表格（只读） -->
      <el-card class="table-card">
        <template #header>
          <div class="card-header">
            <span>格式化数据（只读）</span>
            <el-tag>{{ orderStore.currentOrder.fileName }}</el-tag>
          </div>
        </template>
        
        <el-table 
          :data="formattedData" 
          border 
          stripe
          max-height="300"
          style="width: 100%"
        >
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="source_zone" label="源区域" min-width="120" />
          <el-table-column prop="source_ip" label="源IP" min-width="150" />
          <el-table-column prop="dest_zone" label="目的区域" min-width="120" />
          <el-table-column prop="dest_ip" label="目的IP" min-width="150" />
          <el-table-column prop="service" label="目的端口" min-width="120" />
          <el-table-column prop="action" label="动作" min-width="100" />
        </el-table>
      </el-card>

      <!-- 第二次格式化表格（可编辑） -->
      <el-card class="table-card">
        <template #header>
          <div class="card-header">
            <span>用户编辑数据（可编辑）</span>
            <div class="table-actions">
              <el-button size="small" @click="addRow">
                <el-icon><plus /></el-icon> 添加行
              </el-button>
              <el-button size="small" @click="copySelected" :disabled="!selectedRows.length">
                <el-icon><document-copy /></el-icon> 复制
              </el-button>
              <el-button size="small" @click="pasteData" :disabled="!clipboardData">
                <el-icon><document /></el-icon> 粘贴
              </el-button>
            </div>
          </div>
        </template>
        
        <el-table 
          ref="editTableRef"
          :data="userModifiedData" 
          border 
          stripe
          max-height="400"
          style="width: 100%"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="source_zone" label="源区域" min-width="120">
            <template #default="{ row, $index }">
              <el-input 
                v-model="row.source_zone" 
                @change="handleCellChange($index)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column prop="source_ip" label="源IP" min-width="150">
            <template #default="{ row, $index }">
              <el-input 
                v-model="row.source_ip" 
                @change="handleCellChange($index)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column prop="dest_zone" label="目的区域" min-width="120">
            <template #default="{ row, $index }">
              <el-input 
                v-model="row.dest_zone" 
                @change="handleCellChange($index)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column prop="dest_ip" label="目的IP" min-width="150">
            <template #default="{ row, $index }">
              <el-input 
                v-model="row.dest_ip" 
                @change="handleCellChange($index)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column prop="service" label="目的端口" min-width="120">
            <template #default="{ row, $index }">
              <el-input 
                v-model="row.service" 
                @change="handleCellChange($index)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column prop="action" label="动作" min-width="100">
            <template #default="{ row, $index }">
              <el-select 
                v-model="row.action" 
                @change="handleCellChange($index)"
                size="small"
              >
                <el-option label="允许" value="allow" />
                <el-option label="拒绝" value="deny" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ $index }">
              <el-button 
                type="danger" 
                size="small" 
                @click="deleteRow($index)"
                link
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
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
import { Plus, DocumentCopy, Document } from '@element-plus/icons-vue'
import { useOrderStore } from '@/store/order'
import { updatePolicies } from '@/api/firewall'

const router = useRouter()
const orderStore = useOrderStore()

const formattedData = ref<any[]>([])
const userModifiedData = ref<any[]>([])
const saving = ref(false)
const nextLoading = ref(false)
const autoExecute = ref(false)
const selectedRows = ref<any[]>([])
const clipboardData = ref<any[] | null>(null)
const editTableRef = ref()

onMounted(() => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传文件')
    router.push('/workflow/upload')
    return
  }

  // 加载格式化数据（只读）
  formattedData.value = [...orderStore.currentOrder.formattedData]
  
  // 加载用户修改数据（可编辑）
  if (orderStore.currentOrder.userModifiedData.length > 0) {
    userModifiedData.value = [...orderStore.currentOrder.userModifiedData]
  } else {
    // 如果没有用户修改数据，复制格式化数据作为初始值
    userModifiedData.value = JSON.parse(JSON.stringify(formattedData.value))
    orderStore.setUserModifiedData(userModifiedData.value)
  }
})

const handleCellChange = (index: number) => {
  // 更新 store
  orderStore.setUserModifiedData(userModifiedData.value)
}

const handleSelectionChange = (selection: any[]) => {
  selectedRows.value = selection
}

const addRow = () => {
  const newRow = {
    source_zone: '',
    source_ip: '',
    dest_zone: '',
    dest_ip: '',
    service: '',
    action: 'allow'
  }
  userModifiedData.value.push(newRow)
  orderStore.setUserModifiedData(userModifiedData.value)
  ElMessage.success('已添加新行')
}

const deleteRow = (index: number) => {
  userModifiedData.value.splice(index, 1)
  orderStore.setUserModifiedData(userModifiedData.value)
  ElMessage.success('已删除行')
}

const copySelected = () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要复制的行')
    return
  }
  clipboardData.value = JSON.parse(JSON.stringify(selectedRows.value))
  ElMessage.success(`已复制 ${selectedRows.value.length} 行`)
}

const pasteData = () => {
  if (!clipboardData.value) {
    ElMessage.warning('剪贴板为空')
    return
  }
  userModifiedData.value.push(...JSON.parse(JSON.stringify(clipboardData.value)))
  orderStore.setUserModifiedData(userModifiedData.value)
  ElMessage.success(`已粘贴 ${clipboardData.value.length} 行`)
}

const handleSave = async () => {
  if (!orderStore.currentOrder.orderId) return

  saving.value = true
  try {
    // 保存用户修改后的数据
    await updatePolicies(orderStore.currentOrder.orderId, {
      policies: userModifiedData.value
    })
    
    // 更新用户修改数据
    orderStore.setUserModifiedData(userModifiedData.value)
    
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
  if (userModifiedData.value.length === 0) {
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

.table-actions {
  display: flex;
  gap: 10px;
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
