import { createRouter, createWebHashHistory } from 'vue-router'
import { auth } from '../store'
import Layout from '../components/Layout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '工作台' } },
      { path: 'quick', name: 'quick', component: () => import('../views/QuickPredict.vue'), meta: { title: '一键预测' } },
      { path: 'templates', name: 'templates', component: () => import('../views/Templates.vue'), meta: { title: '数据模板' } },
      { path: 'datasets', name: 'datasets', component: () => import('../views/Datasets.vue'), meta: { title: '数据集' } },
      { path: 'train', name: 'train', component: () => import('../views/Train.vue'), meta: { title: '模型训练' } },
      { path: 'jobs', name: 'jobs', component: () => import('../views/Jobs.vue'), meta: { title: '任务队列' } },
      { path: 'models', name: 'models', component: () => import('../views/Models.vue'), meta: { title: '模型仓库' } },
      { path: 'models/:id', name: 'model-detail', component: () => import('../views/ModelDetail.vue'), meta: { title: '模型详情' } },
      { path: 'predict', name: 'predict', component: () => import('../views/Predict.vue'), meta: { title: '在线预测' } },
      { path: 'api', name: 'api', component: () => import('../views/ApiAccess.vue'), meta: { title: 'API 接入' } },
      { path: 'monitor', name: 'monitor', component: () => import('../views/Monitor.vue'), meta: { title: '运行监控' } },
      { path: 'admin', name: 'admin', component: () => import('../views/Admin.vue'), meta: { title: '系统管理', admin: true } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  if (!to.meta.public && !auth.token) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !auth.isAdmin) return { name: 'dashboard' }
  if (to.meta.title) document.title = `${to.meta.title} - 通用模型预测服务平台`
  return true
})

export default router
