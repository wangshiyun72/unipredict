<template>
  <div class="login-page">
    <div class="intro">
      <div class="logo">
        <svg viewBox="0 0 32 32" width="44" height="44"><rect width="32" height="32" rx="7" fill="#14b8a6" />
          <path d="M7 22l6-7 5 4 7-10" stroke="white" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <div>
          <h1>通用模型预测服务平台</h1>
          <p>基于服务器端通用模型的可访问式深度学习预测服务</p>
        </div>
      </div>
      <ul class="points">
        <li><el-icon><Cpu /></el-icon><div><b>服务器端通用 / 轻量模型</b><span>TabPFN 表格基础模型、FT-Transformer、残差 MLP、梯度提升树等统一接入</span></div></li>
        <li><el-icon><MagicStick /></el-icon><div><b>最少配置一键预测</b><span>上传数据 → 选择目标列 → 自动归一化、建模、评估、预测</span></div></li>
        <li><el-icon><Connection /></el-icon><div><b>REST API 对外服务</b><span>外部终端凭 API Key 调用，限流与并发控制保障服务稳定</span></div></li>
        <li><el-icon><DataAnalysis /></el-icon><div><b>可解释 · 可视化</b><span>特征重要性、单样本贡献分析、预测结果图表化</span></div></li>
      </ul>
    </div>
    <div class="panel">
      <el-tabs v-model="tab" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item :label="tab === 'login' ? '邮箱' : '邮箱（作为登录账号）'">
          <el-input v-model="form.username" size="large" autocomplete="username" :placeholder="tab === 'login' ? '注册时使用的邮箱' : 'name@example.com'" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" size="large" show-password :placeholder="tab === 'register' ? '至少 6 位' : ''"
                    :autocomplete="tab === 'login' ? 'current-password' : 'new-password'" @keyup.enter="submit" />
        </el-form-item>
        <template v-if="tab === 'register'">
          <el-form-item label="确认密码">
            <el-input v-model="form.password2" type="password" size="large" show-password autocomplete="new-password" @keyup.enter="submit" />
          </el-form-item>
          <el-form-item label="姓名 / 昵称（可选）"><el-input v-model="form.display_name" /></el-form-item>
          <el-form-item label="团队 / 课题组（可选）">
            <el-input v-model="form.team" placeholder="同一团队的成员可以共享数据集和模型" />
          </el-form-item>
        </template>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          {{ tab === 'login' ? '登 录' : '注册并登录' }}
        </el-button>
      </el-form>
      <p class="muted tip">{{ tab === 'login' ? '还没有账号？切换到「注册」，用邮箱即可注册，无需验证码' : '注册后即可使用平台上所有公开模型' }}</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { auth } from '../store'

const route = useRoute()
const router = useRouter()
const tab = ref('login')
const loading = ref(false)
const form = reactive({ username: '', password: '', password2: '', display_name: '', team: '' })
const EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

async function submit() {
  if (!form.username || !form.password) return ElMessage.warning('请输入邮箱和密码')
  if (tab.value === 'register') {
    if (!EMAIL.test(form.username.trim())) return ElMessage.warning('请输入正确的邮箱地址，例如 name@example.com')
    if (form.password.length < 6) return ElMessage.warning('密码至少 6 位')
    if (form.password !== form.password2) return ElMessage.warning('两次输入的密码不一致')
  }
  loading.value = true
  try {
    const url = tab.value === 'login' ? '/auth/login' : '/auth/register'
    const body = tab.value === 'login'
      ? { username: form.username, password: form.password }
      : { username: form.username.trim(), password: form.password, display_name: form.display_name || null, team: form.team || '默认团队' }
    const res = await http.post(url, body)
    auth.set(res.access_token, res.user)
    ElMessage.success(`欢迎，${res.user.display_name || res.user.username}`)
    router.push(route.query.redirect || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center; gap: 64px; padding: 40px;
  background: radial-gradient(circle at 15% 20%, #134e4a 0, #0b1f24 55%);
}
.intro { color: #e6f2f1; max-width: 520px; }
.logo { display: flex; gap: 16px; align-items: center; }
.logo h1 { margin: 0; font-size: 28px; color: #fff; }
.logo p { margin: 6px 0 0; color: #8fb3b0; }
.points { list-style: none; padding: 0; margin: 40px 0 0; display: flex; flex-direction: column; gap: 22px; }
.points li { display: flex; gap: 14px; }
.points .el-icon { font-size: 22px; color: #5eead4; margin-top: 2px; }
.points b { display: block; color: #fff; margin-bottom: 4px; }
.points span { color: #9bbab7; font-size: 13px; line-height: 1.6; }
.panel { width: 380px; background: #fff; border-radius: 14px; padding: 24px 28px 20px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35); }
.tip { font-size: 12px; text-align: center; margin: 14px 0 0; }
@media (max-width: 900px) { .intro { display: none; } }
</style>
