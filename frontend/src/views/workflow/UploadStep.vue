<template>
  <div class="workflow-step">
    <div class="step-header">
      <h2>上传策略文件</h2>
      <p class="step-desc">请上传 Excel 格式的防火墙策略文件</p>
    </div>

    <div class="step-content">
      <el-card>
        <el-form :model="uploadForm" label-width="100px" class="upload-form">
          <el-form-item label="工单号">
            <el-input 
              v-model="uploadForm.orderId" 
              placeholder="留空自动生成（ORD-时间戳）"
              clearable
            />
            <div class="form-tip">可选，默认自动生成工单号</div>
          </el-form-item>
        </el-form>
        
        <FileUpload @success="handleUploadSuccess" />
      </el-card>
    </div>

    <div class="step-actions">
      <el-button @click="handleBack">返回首页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FileUpload from '@/components/FileUpload.vue'
import { uploadFile } from '@/api/firewall'
import { useOrderStore } from '@/store/order'

const router = useRouter()
const orderStore = useOrderStore()

const uploadForm = ref({
  orderId: ''
})

const handleUploadSuccess = async (file: File) => {
  try {
    const response = await uploadFile(file)

    // 保存工单信息到 store
    orderStore.setOrderId(response.id.toString())
    orderStore.setFileName(response.title)
    orderStore.setOriginalData(response.original_data)
    orderStore.setFormattedData(response.formatted_data)

    ElMessage.success('文件上传成功！')

    // 自动跳转到编辑页面
    setTimeout(() => {
      router.push('/workflow/edit')
    }, 500)
  } catch (error) {
    console.error('Upload error:', error)
    ElMessage.error('上传失败，请重试')
  }
}

const handleBack = () => {
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

.upload-form {
  margin-bottom: 20px;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}
</style>
