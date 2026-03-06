<template>
  <el-container class="upload-page">
    <el-header>
      <h2>文件上传</h2>
    </el-header>
    <el-main>
      <el-card>
        <template #header>
          <span>上传防火墙策略文件</span>
        </template>
        
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
    </el-main>
  </el-container>
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

    // 跳转到编辑页面
    setTimeout(() => {
      router.push('/edit')
    }, 500)
  } catch (error) {
    console.error('Upload error:', error)
    ElMessage.error('上传失败，请重试')
  }
}
</script>

<style scoped>
.upload-page {
  height: 100vh;
  background-color: #f5f7fa;
}

.el-header {
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.el-main {
  padding: 40px;
}

.el-card {
  max-width: 800px;
  margin: 0 auto;
}

.upload-form {
  margin-bottom: 20px;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>
