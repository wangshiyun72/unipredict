<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">系统管理</h2>
        <p class="page-desc">管理平台用户、团队与访问权限，查看被拒绝的访问记录。</p>
      </div>
    </div>

    <div class="card">
      <div class="card-title">用户与团队</div>
      <el-table :data="users" size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="用户" min-width="150"><template #default="{ row }">{{ row.username }}<div class="muted" style="font-size: 12px">{{ row.display_name }}</div></template></el-table-column>
        <el-table-column label="团队" width="170">
          <template #default="{ row }"><el-input v-model="row.team" size="small" @change="(v) => patch(row, { team: v })" /></template>
        </el-table-column>
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-select :model-value="row.role" size="small" @change="(v) => patch(row, { role: v }, () => (row.role = v))">
              <el-option label="管理员" value="admin" /><el-option label="普通用户" value="user" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="限额（次/分钟）" width="170">
          <template #default="{ row }">
            <el-input-number :model-value="row.rate_limit_per_min" size="small" :min="1" :max="100000" placeholder="默认" controls-position="right"
                             @change="(v) => v && patch(row, { rate_limit_per_min: v })" />
          </template>
        </el-table-column>
        <el-table-column prop="models" label="模型数" width="80" />
        <el-table-column prop="calls" label="调用数" width="80" />
        <el-table-column label="启用" width="80">
          <template #default="{ row }"><el-switch :model-value="!!row.is_active" @change="(v) => patch(row, { is_active: v }, () => (row.is_active = v ? 1 : 0))" /></template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="165" />
      </el-table>
    </div>

    <div class="card">
      <div class="card-title flex-between">
        <span>被拒绝的访问 <span class="sub">限流 429 / 并发已满 503 / 认证失败 401</span></span>
        <el-button size="small" @click="loadLogs"><el-icon><Refresh /></el-icon></el-button>
      </div>
      <el-table :data="logs" size="small" max-height="420" empty-text="暂无记录">
        <el-table-column prop="created_at" label="时间" width="165" />
        <el-table-column prop="identity" label="访问身份" width="140" />
        <el-table-column prop="path" label="接口" min-width="200" />
        <el-table-column label="状态码" width="90"><template #default="{ row }"><el-tag size="small" type="danger">{{ row.status_code }}</el-tag></template></el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const users = ref([])
const logs = ref([])

async function load() {
  users.value = await http.get('/admin/users')
}
async function loadLogs() {
  logs.value = await http.get('/admin/access-logs')
}
onMounted(() => { load(); loadLogs() })

async function patch(row, data, after) {
  await http.patch(`/admin/users/${row.id}`, data)
  if (after) after()
  ElMessage.success('已更新')
}
</script>
