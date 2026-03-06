import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import WorkflowLayout from '@/components/WorkflowLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomePage.vue')
  },
  {
    path: '/workflow',
    component: WorkflowLayout,
    children: [
      {
        path: 'upload',
        name: 'WorkflowUpload',
        component: () => import('@/views/workflow/UploadStep.vue')
      },
      {
        path: 'edit',
        name: 'WorkflowEdit',
        component: () => import('@/views/workflow/EditStep.vue')
      },
      {
        path: 'preview',
        name: 'WorkflowPreview',
        component: () => import('@/views/workflow/PreviewStep.vue')
      },
      {
        path: 'push',
        name: 'WorkflowPush',
        component: () => import('@/views/workflow/PushStep.vue')
      },
      {
        path: 'complete',
        name: 'WorkflowComplete',
        component: () => import('@/views/workflow/CompleteStep.vue')
      }
    ]
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('@/views/HistoryPage.vue')
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('@/views/ConfigPage.vue')
  },
  // 兼容旧路由，重定向到工作流
  {
    path: '/upload',
    redirect: '/workflow/upload'
  },
  {
    path: '/edit',
    redirect: '/workflow/edit'
  },
  {
    path: '/preview',
    redirect: '/workflow/preview'
  },
  {
    path: '/push',
    redirect: '/workflow/push'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
