<template>
  <div v-if="m" class="page">
    <div class="page-header">
      <div>
        <div class="flex">
          <el-button text @click="$router.back()"><el-icon><ArrowLeft /></el-icon></el-button>
          <h2 class="page-title">{{ m.name }}</h2>
          <el-tag :class="FAMILY[m.family]?.cls">{{ FAMILY[m.family]?.label }}</el-tag>
          <el-tag :type="STATUS[m.status]?.type">{{ STATUS[m.status]?.label }}</el-tag>
          <el-icon v-if="m.is_best" color="#f59e0b" size="20"><Trophy /></el-icon>
        </div>
        <p class="page-desc">{{ m.adapter_name }} · {{ TASK[m.task] }}任务 · 预测「{{ m.target }}」 · {{ m.adapter_description }}</p>
      </div>
      <div class="flex">
        <el-button @click="$router.push({ path: '/predict', query: { model: m.id } })"><el-icon><Aim /></el-icon>&nbsp;在线预测</el-button>
        <el-button @click="$router.push({ path: '/api', query: { model: m.id } })"><el-icon><Connection /></el-icon>&nbsp;API 调用</el-button>
        <template v-if="canEdit">
          <el-button v-if="m.status !== 'published'" type="success" @click="patch({ status: 'published' })">发布</el-button>
          <el-button v-else type="warning" plain @click="patch({ status: 'ready' })">取消发布</el-button>
        </template>
      </div>
    </div>

    <div class="card mb">
      <el-descriptions :column="4" size="small" border>
        <el-descriptions-item label="模型 ID">{{ m.id }}</el-descriptions-item>
        <el-descriptions-item label="创建者">{{ m.owner_name }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ m.created_at }}</el-descriptions-item>
        <el-descriptions-item label="共享范围">
          <el-select v-if="canEdit" :model-value="m.visibility" size="small" style="width: 120px" @change="(v) => patch({ visibility: v })">
            <el-option v-for="(l, k) in VISIBILITY" :key="k" :label="l" :value="k" />
          </el-select>
          <span v-else>{{ VISIBILITY[m.visibility] }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="训练 / 测试样本">{{ m.detail?.n_train ?? '-' }} / {{ m.detail?.n_test ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="训练耗时">{{ m.detail?.train_seconds ? m.detail.train_seconds + ' s' : '-' }}</el-descriptions-item>
        <el-descriptions-item label="累计调用">{{ m.usage?.calls ?? 0 }} 次 / {{ m.usage?.rows ?? 0 }} 条</el-descriptions-item>
        <el-descriptions-item label="平均耗时">{{ fmt(m.usage?.avg_latency, 1) }} ms</el-descriptions-item>
        <el-descriptions-item label="模型参数" :span="4">
          <span class="mono" style="font-size: 12px">{{ JSON.stringify(m.detail?.params || {}) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <ModelResult :model="m" />

    <div class="card mt">
      <div class="card-title">输入字段 <span class="sub">调用预测时需要提供的字段</span></div>
      <el-table :data="m.input_schema || []" size="small">
        <el-table-column prop="name" label="字段名" min-width="160" />
        <el-table-column label="类型" width="120"><template #default="{ row }">{{ COLUMN_TYPES[row.type] }}</template></el-table-column>
        <el-table-column label="训练数据范围 / 可选值" min-width="260">
          <template #default="{ row }">
            <span v-if="row.choices">{{ row.choices.slice(0, 10).join('、') }}</span>
            <span v-else-if="row.min !== undefined">{{ fmt(row.min) }} ~ {{ fmt(row.max) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="默认值（典型值）" width="160"><template #default="{ row }">{{ fmt(row.default) }}</template></el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import ModelResult from '../components/ModelResult.vue'
import { auth } from '../store'
import { COLUMN_TYPES, FAMILY, STATUS, TASK, VISIBILITY, fmt } from '../utils'

const route = useRoute()
const m = ref(null)
const canEdit = computed(() => m.value && (m.value.owner_id === auth.user.id || auth.isAdmin))

async function load() {
  m.value = await http.get(`/models/${route.params.id}`)
}
onMounted(load)

async function patch(data) {
  await http.patch(`/models/${m.value.id}`, data)
  Object.assign(m.value, data)
  ElMessage.success('已更新')
}
</script>
