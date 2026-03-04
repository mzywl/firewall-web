<template>
  <div class="step-progress">
    <el-steps :active="active" finish-status="success" align-center>
      <el-step 
        v-for="(step, index) in steps" 
        :key="index"
        :title="step.title"
        :description="step.description"
        :icon="step.icon"
      />
    </el-steps>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

interface Step {
  title: string
  description: string
  icon?: any
  path: string
}

interface Props {
  steps: Step[]
}

const props = defineProps<Props>()
const route = useRoute()

// 根据当前路由计算激活的步骤
const active = computed(() => {
  const currentPath = route.path
  const index = props.steps.findIndex(step => step.path === currentPath)
  return index >= 0 ? index : 0
})
</script>

<style scoped>
.step-progress {
  padding: 20px;
  background-color: white;
  border-radius: 4px;
  margin-bottom: 20px;
}
</style>
