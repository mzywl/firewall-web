<template>
  <el-container class="home-page">
    <el-header>
      <h1>防火墙策略自动化系统</h1>
    </el-header>
    <el-main>
      <el-row :gutter="20">
        <el-col :span="8" v-for="item in menuItems" :key="item.path">
          <el-card class="menu-card" @click="navigateTo(item.path)">
            <div class="card-content">
              <el-icon :size="48"><component :is="item.icon" /></el-icon>
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Upload, Clock, Setting } from '@element-plus/icons-vue'

const router = useRouter()

const menuItems = [
  { path: '/workflow/upload', title: '开始推送', description: '上传策略文件并开始推送流程', icon: Upload },
  { path: '/history', title: '历史记录', description: '查看推送历史', icon: Clock },
  { path: '/config', title: '防火墙配置', description: '管理防火墙设备', icon: Setting }
]

const navigateTo = (path: string) => {
  router.push(path)
}
</script>

<style scoped>
.home-page {
  height: 100vh;
}

.el-header {
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.el-main {
  padding: 40px;
}

.menu-card {
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 20px;
}

.menu-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.card-content {
  text-align: center;
  padding: 20px;
}

.card-content h3 {
  margin: 15px 0 10px;
}

.card-content p {
  color: #909399;
  font-size: 14px;
}
</style>
