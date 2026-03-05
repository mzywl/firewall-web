import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomePage.vue')
  },
  {
    path: '/upload',
    name: 'Upload',
    component: () => import('@/views/UploadPage.vue')
  },
  {
    path: '/edit',
    name: 'Edit',
    component: () => import('@/views/EditPage.vue')
  },
  {
    path: '/preview',
    name: 'Preview',
    component: () => import('@/views/PreviewPage.vue')
  },
  {
    path: '/push',
    name: 'Push',
    component: () => import('@/views/PushPage.vue')
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
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
