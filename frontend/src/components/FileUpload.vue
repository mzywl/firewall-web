<template>
  <div class="file-upload">
    <el-upload
      ref="uploadRef"
      class="upload-demo"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      :before-upload="beforeUpload"
      :limit="1"
      accept=".xlsx,.xls"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">
        拖拽文件到此处或 <em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          仅支持 .xlsx 或 .xls 格式文件
        </div>
      </template>
    </el-upload>
    
    <div v-if="currentFile" class="file-info">
      <el-icon><document /></el-icon>
      <span>{{ currentFile.name }}</span>
      <el-button type="danger" size="small" @click="removeFile">删除</el-button>
    </div>

    <div class="upload-actions">
      <el-button type="primary" :loading="uploading" :disabled="!currentFile" @click="handleUpload">
        开始上传
      </el-button>
    </div>

    <el-progress v-if="uploadProgress > 0" :percentage="uploadProgress" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document } from '@element-plus/icons-vue'
import type { UploadFile, UploadInstance } from 'element-plus'

const emit = defineEmits<{
  success: [file: File]
}>()

const uploadRef = ref<UploadInstance>()
const currentFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)

const handleFileChange = (file: UploadFile) => {
  if (file.raw) {
    currentFile.value = file.raw
  }
}

const beforeUpload = (file: File) => {
  const isExcel = file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' || 
                  file.type === 'application/vnd.ms-excel'
  const isLt10M = file.size / 1024 / 1024 < 10

  if (!isExcel) {
    ElMessage.error('只能上传 Excel 文件！')
    return false
  }
  if (!isLt10M) {
    ElMessage.error('文件大小不能超过 10MB！')
    return false
  }
  return true
}

const removeFile = () => {
  currentFile.value = null
  uploadRef.value?.clearFiles()
  uploadProgress.value = 0
}

const handleUpload = async () => {
  if (!currentFile.value) return

  uploading.value = true
  uploadProgress.value = 0

  // 模拟上传进度
  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) {
      uploadProgress.value += 10
    }
  }, 200)

  try {
    emit('success', currentFile.value)
    uploadProgress.value = 100
    ElMessage.success('上传成功！')
  } catch (error) {
    ElMessage.error('上传失败，请重试')
    uploadProgress.value = 0
  } finally {
    clearInterval(progressInterval)
    uploading.value = false
  }
}
</script>

<style scoped>
.file-upload {
  padding: 20px;
}

.upload-demo {
  width: 100%;
}

.file-info {
  margin-top: 20px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.upload-actions {
  margin-top: 20px;
  text-align: center;
}
</style>
