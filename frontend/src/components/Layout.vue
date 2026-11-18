<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="aside">
      <div class="brand" @click="$router.push('/dashboard')">
        <svg viewBox="0 0 32 32" width="28" height="28"><rect width="32" height="32" rx="7" fill="#14b8a6" />
          <path d="M7 22l6-7 5 4 7-10" stroke="white" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <div v-if="!collapsed" class="brand-text">
          <div class="brand-name">通用模型预测服务</div>
          <div class="brand-sub">UniPredict Platform</div>
        </div>
      </div>
      <el-menu :default-active="active" :collapse="collapsed" router background-color="#0b1f24"
               text-color="#b6c6c9" active-text-color="#ffffff" class="menu">
        <template v-for="g in groups" :key="g.title">
          <div v-if="!collapsed" class="menu-group">{{ g.title }}</div>
          <el-menu-item v-for="m in g.items.filter(i => !i.admin || auth.isAdmin)" :key="m.path" :index="m.path">
            <el-icon><component :is="m.icon" /></el-icon>
            <template #title>{{ m.label }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="flex">
          <el-button text @click="collapsed = !collapsed">
            <el-icon size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>
          <span class="crumb">{{ $route.meta.title }}</span>
        </div>
        <div class="flex">
          <el-button text tag="a" href="/docs" target="_blank"><el-icon><Document /></el-icon>&nbsp;接口文档</el-button>
          <el-dropdown @command="onCommand">
            <span class="user">
              <el-avatar :size="28" class="avatar">{{ (auth.user?.display_name || auth.user?.username || '?').slice(0, 1) }}</el-avatar>
              <span>{{ auth.user?.display_name || auth.user?.username }}</span>
              <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'info'" effect="plain">{{ auth.isAdmin ? '管理员' : auth.user?.team }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <keep-alive include="QuickPredict">
            <component :is="Component" :key="$route.fullPath" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>

    <el-dialog v-model="pwd.show" title="修改密码" width="380px">
      <el-form label-width="80px">
        <el-form-item label="原密码"><el-input v-model="pwd.old" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="pwd.new" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwd.show = false">取消</el-button>
        <el-button type="primary" @click="changePassword">确定</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { auth } from '../store'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const active = computed(() => '/' + (route.path.split('/')[1] || 'dashboard'))

const groups = [
  { title: '概览', items: [{ path: '/dashboard', label: '工作台', icon: 'Odometer' }] },
  {
    title: '预测',
    items: [
      { path: '/quick', label: '一键预测', icon: 'MagicStick' },
      { path: '/predict', label: '在线预测', icon: 'Aim' }
    ]
  },
  {
    title: '数据与模型',
    items: [
      { path: '/templates', label: '数据模板', icon: 'Collection' },
      { path: '/datasets', label: '数据集', icon: 'Files' },
      { path: '/train', label: '模型训练', icon: 'Cpu' },
      { path: '/jobs', label: '任务队列', icon: 'List' },
      { path: '/models', label: '模型仓库', icon: 'Box' }
    ]
  },
  {
    title: '服务',
    items: [
      { path: '/api', label: 'API 接入', icon: 'Connection' },
      { path: '/monitor', label: '运行监控', icon: 'Monitor' },
      { path: '/admin', label: '系统管理', icon: 'Setting', admin: true }
    ]
  }
]

const pwd = reactive({ show: false, old: '', new: '' })

async function changePassword() {
  const { default: http } = await import('../api/http')
  await http.post('/auth/change-password', { old_password: pwd.old, new_password: pwd.new })
  ElMessage.success('密码已修改')
  pwd.show = false
}

function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.clear()
    router.push('/login')
  } else if (cmd === 'password') {
    Object.assign(pwd, { show: true, old: '', new: '' })
  }
}
</script>

<style scoped>
.layout { height: 100vh; }
.aside { background: #0b1f24; transition: width 0.2s; overflow-x: hidden; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 10px; padding: 16px 18px; cursor: pointer; }
.brand-name { color: #fff; font-weight: 600; font-size: 15px; white-space: nowrap; }
.brand-sub { color: #6b8a8f; font-size: 11px; letter-spacing: 0.5px; }
.menu { border-right: none; flex: 1; }
.menu-group { color: #58777c; font-size: 11px; padding: 14px 20px 6px; letter-spacing: 1px; }
.menu :deep(.el-menu-item.is-active) { background: #0f766e !important; }
.menu :deep(.el-menu-item) { height: 44px; }
.header { background: #fff; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; height: 56px; }
.crumb { font-weight: 600; }
.user { display: flex; align-items: center; gap: 8px; cursor: pointer; outline: none; }
.avatar { background: #0f766e; }
.main { padding: 0; overflow-y: auto; }
</style>
