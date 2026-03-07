<template>
  <el-container class="preview-page">
    <el-header>
      <h2>策略预览</h2>
      <div class="header-actions">
        <el-button @click="handleBack">返回</el-button>
        <el-button type="primary" @click="handleConfirmPush">确认推送</el-button>
      </div>
    </el-header>

    <el-main>
      <!-- 策略合并分析 -->
      <el-card class="merge-card" v-if="mergeAnalysis">
        <template #header>
          <div class="card-header">
            <span>策略合并分析</span>
            <el-button size="small" @click="analyzeMerge" :loading="mergeLoading">
              <el-icon><refresh /></el-icon> 重新分析
            </el-button>
          </div>
        </template>
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="原始策略数" :value="mergeAnalysis.original_count">
              <template #prefix>
                <el-icon><document /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="合并后策略数" :value="mergeAnalysis.merged_count">
              <template #prefix>
                <el-icon color="#67c23a"><check /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="冗余策略数" :value="mergeAnalysis.redundant_count">
              <template #prefix>
                <el-icon color="#f56c6c"><warning /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="优化率" :value="optimizationRate + '%'">
              <template #prefix>
                <el-icon color="#409eff"><trend-charts /></el-icon>
              </template>
            </el-statistic>
          </el-col>
        </el-row>
      </el-card>

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
      <div class="firewall-groups">
        <div class="groups-header">
          <span>策略列表（按防火墙分组）</span>
          <el-button size="small" @click="analyzeMerge" :loading="mergeLoading" v-if="!mergeAnalysis">
            <el-icon><data-analysis /></el-icon> 分析合并
          </el-button>
        </div>
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

            <el-table :data="group.policies" border stripe>
              <el-table-column type="index" label="#" width="50" />
              <el-table-column label="源区域" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row['源区域'] || row.source_zone || '' }}
                </template>
              </el-table-column>
              <el-table-column label="源IP" min-width="150" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row['源IP'] || row.source_ip || '' }}
                </template>
              </el-table-column>
              <el-table-column label="目的区域" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row['目的区域'] || row.dest_zone || '' }}
                </template>
              </el-table-column>
              <el-table-column label="目的IP" min-width="150" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row['目的IP'] || row.dest_ip || '' }}
                </template>
              </el-table-column>
              <el-table-column label="目的端口" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row['目的端口'] || row.service || '' }}
                </template>
              </el-table-column>
              <el-table-column label="动作" min-width="100">
                <template #default="{ row }">
                  {{ row['动作'] || row.action || '' }}
                </template>
              </el-table-column>
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
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, CirclePlus, Edit, Monitor, Refresh, Check, Warning, TrendCharts, DataAnalysis } from '@element-plus/icons-vue'
import { useOrderStore } from '@/store/order'
import { getMergeAnalysis } from '@/api/firewall'

const router = useRouter()
const orderStore = useOrderStore()

interface FirewallGroup {
  firewallId: string
  firewallName: string
  policies: any[]
}

interface MergeAnalysis {
  message: string
  original_count: number
  merged_count: number
  redundant_count: number
  redundant_ids: number[]
  merged_policies: any[]
}

const activeGroups = ref<string[]>([])
const firewallGroups = ref<FirewallGroup[]>([])
const mergeAnalysis = ref<MergeAnalysis | null>(null)
const mergeLoading = ref(false)

// 优化率计算
const optimizationRate = computed(() => {
  if (!mergeAnalysis.value || mergeAnalysis.value.original_count === 0) {
    return 0
  }
  const rate = ((mergeAnalysis.value.original_count - mergeAnalysis.value.merged_count) / mergeAnalysis.value.original_count) * 100
  return Math.round(rate)
})

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
    router.push('/upload')
    return
  }

  loadPreviewData()
})

const loadPreviewData = () => {
  // 优先使用用户修改的数据，如果没有则使用格式化数据
  const data = orderStore.currentOrder.userModifiedData.length > 0
    ? orderStore.currentOrder.userModifiedData
    : orderStore.currentOrder.formattedData

  if (!data || data.length === 0) {
    ElMessage.warning('没有可预览的数据')
    return
  }

  // 按防火墙分组
  const groups = new Map<string, any[]>()

  data.forEach(policy => {
    const firewallId = policy.firewall_id || policy.firewallId || 'unknown'
    if (!groups.has(firewallId)) {
      groups.set(firewallId, [])
    }
    groups.get(firewallId)!.push(policy)
  })

  // 转换为数组
  firewallGroups.value = Array.from(groups.entries()).map(([id, policies]) => ({
    firewallId: id,
    firewallName: id === 'unknown' ? '未匹配防火墙' : `防火墙 ${id}`,
    policies
  }))

  // 默认展开第一个
  if (firewallGroups.value.length > 0) {
    activeGroups.value = [firewallGroups.value[0].firewallId]
  }
}

const analyzeMerge = async () => {
  if (!orderStore.currentOrder.orderId) {
    ElMessage.warning('工单ID不存在')
    return
  }

  mergeLoading.value = true
  try {
    const response = await getMergeAnalysis(orderStore.currentOrder.orderId)
    mergeAnalysis.value = response as MergeAnalysis
    ElMessage.success('合并分析完成')
  } catch (error) {
    console.error('Merge analysis error:', error)
    ElMessage.error('合并分析失败')
  } finally {
    mergeLoading.value = false
  }
}

const handleConfirmPush = async () => {
  try {
    await ElMessageBox.confirm(
      `确认推送 ${statistics.value.total} 条策略到 ${firewallGroups.value.length} 个防火墙？`,
      '确认推送',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 跳转到推送页面
    router.push('/push')
  } catch {
    // 用户取消
  }
}

const handleBack = () => {
  router.back()
}
</script>

<style scoped>
.preview-page {
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

.stats-card {
  margin-bottom: 20px;
}

.merge-card {
  margin-bottom: 20px;
}

.firewall-groups {
  background: white;
  padding: 20px;
  border-radius: 4px;
}

.groups-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 15px;
  font-weight: 500;
  font-size: 14px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 500;
}
</style>
