<template>
  <div class="workflow-step">
    <div class="step-header">
      <h2>预览确认</h2>
      <p class="step-desc">确认最终数据无误后开始推送</p>
    </div>

    <div class="step-content">
      <!-- 统计信息 -->
      <el-card class="stats-card">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="策略总数" :value="statistics.total">
              <template #prefix>
                <el-icon><document /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="新增策略" :value="statistics.new">
              <template #prefix>
                <el-icon color="#67c23a"><circle-plus /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="修改策略" :value="statistics.modified">
              <template #prefix>
                <el-icon color="#e6a23c"><edit /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="防火墙数量" :value="firewallGroups.length">
              <template #prefix>
                <el-icon color="#409eff"><monitor /></el-icon>
              </template>
            </el-statistic>
          </el-col>
        </el-row>
      </el-card>

      <!-- 按防火墙分组展示 -->
      <el-card>
        <el-collapse v-model="activeGroups">
          <el-collapse-item
            v-for="group in firewallGroups"
            :key="group.firewallId"
            :name="group.firewallId"
          >
            <template #title>
              <div class="group-title">
                <el-icon><monitor /></el-icon>
                <span>{{ group.firewallName }}</span>
                <el-tag size="small" type="info">{{ group.policies.length }} 条策略</el-tag>
              </div>
            </template>

            <el-table :data="group.policies" border stripe max-height="400">
              <el-table-column type="index" label="#" width="50" />
              <el-table-column
                v-for="col in columns"
                :key="col"
                :prop="col"
                :label="col"
                min-width="120"
              />
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag v-if="row._status === 'new'" type="success" size="small">新增</el-tag>
                  <el-tag v-else-if="row._status === 'modified'" type="warning" size="small">修改</el-tag>
                  <el-tag v-else type="info" size="small">正常</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </el-card>
    </div>

    <div class="step-actions">
      <el-button @click="handlePrev">上一步</el-button>
      <el-button type="primary" @click="handleStartPush">开始推送</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, CirclePlus, Edit, Monitor } from '@element-plus/icons-vue'
import { useOrderStore } from '@/store/order'

const router = useRouter()
const orderStore = useOrderStore()

interface FirewallGroup {
  firewallId: string
  firewallName: string
  policies: any[]
}

const activeGroups = ref<string[]>([])
const columns = ref<string[]>([])
const firewallGroups = ref<FirewallGroup[]>([])

// 统计信息
const statistics = computed(() => {
  let total = 0
  let newCount = 0
  let modified = 0

  firewallGroups.value.forEach(group => {
    total += group.policies.length
    group.policies.forEach(policy => {
      if (policy._status === 'new') newCount++
      if (policy._status === 'modified') modified++
    })
  })

  return { total, new: newCount, modified }
})

onMounted(() => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('请先上传并编辑文件')
    router.push('/workflow/upload')
    return
  }

  loadPreviewData()
})

const loadPreviewData = () => {
  const data = orderStore.currentOrder.formattedData

  if (data.length === 0) {
    ElMessage.warning('没有可预览的数据')
    return
  }

  // 提取列名
  columns.value = Object.keys(data[0]).filter(key => !key.startsWith('_'))

  // 按防火墙分组（假设有 firewallId 字段）
  const groups = new Map<string, any[]>()
  
  data.forEach(policy => {
    const firewallId = policy.firewallId || 'default'
    if (!groups.has(firewallId)) {
      groups.set(firewallId, [])
    }
    groups.get(firewallId)!.push(policy)
  })

  // 转换为数组
  firewallGroups.value = Array.from(groups.entries()).map(([id, policies]) => ({
    firewallId: id,
    firewallName: `防火墙 ${id}`,
    policies
  }))

  // 默认展开第一个
  if (firewallGroups.value.length > 0) {
    activeGroups.value = [firewallGroups.value[0].firewallId]
  }
}

const handlePrev = () => {
  router.push('/workflow/edit')
}

const handleStartPush = () => {
  // 跳转到推送页面
  router.push('/workflow/push')
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

.stats-card {
  margin-bottom: 20px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 500;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}
</style>
