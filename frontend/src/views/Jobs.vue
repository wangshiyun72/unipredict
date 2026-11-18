<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">任务队列</h2>
        <p class="page-desc">训练任务在服务器后台线程池中排队执行：同时运行 {{ sys.jobs?.workers ?? '-' }} 个任务，
          每个用户最多 {{ sys.jobs?.max_jobs_per_user ?? '-' }} 个任务排队/运行，全局队列上限 {{ sys.jobs?.max_queue ?? '-' }}。</p>
      </div>
      <div class="flex">
        <el-tag>运行中 {{ sys.jobs?.running ?? 0 }}</el-tag>
        <el-tag type="info">排队中 {{ sys.jobs?.queued ?? 0 }}</el-tag>
        <el-button @click="load"><el-icon><Refresh /></el-icon></el-button>
      </div>
    </div>
    <div class="card">
      <el-table :data="list" v-loading="loading">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column label="数据集 / 目标" min-width="200">
          <template #default="{ row }">{{ row.params?.dataset_name }}<div class="muted" style="font-size: 12px">预测「{{ row.params?.target }}」· {{ (row.params?.models || []).length || '默认' }} 个模型</div></template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" prop="owner_name" label="提交人" width="100" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag size="small" :type="JOB_STATUS[row.status]?.type">{{ JOB_STATUS[row.status]?.label }}</el-tag></template>
        </el-table-column>
        <el-table-column label="进度" width="160">
          <template #default="{ row }"><el-progress :percentage="Math.round(row.progress * 100)" :status="row.status === 'succeeded' ? 'success' : row.status === 'failed' ? 'exception' : ''" /></template>
        </el-table-column>
        <el-table-column prop="message" label="信息" min-width="220" show-overflow-tooltip />
        <el-table-column prop="created_at" label="提交时间" width="165" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openJob(row)">详情</el-button>
            <el-button v-if="['queued', 'running'].includes(row.status)" size="small" text type="danger" @click="cancel(row)">取消</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dlg.show" :title="`任务 #${dlg.id}`" width="720px">
      <JobProgress v-if="dlg.id" :job-id="dlg.id" @update="(j) => (dlg.job = j)" />
      <el-table v-if="dlg.job?.result?.leaderboard" :data="dlg.job.result.leaderboard" size="small" class="mt">
        <el-table-column label="模型" min-width="200">
          <template #default="{ row }">
            <router-link v-if="row.model_id" :to="`/models/${row.model_id}`" @click="dlg.show = false">{{ row.name }}</router-link><span v-else>{{ row.name }}</span>
            <el-icon v-if="row.is_best" color="#f59e0b" style="margin-left: 4px"><Trophy /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="结果" min-width="200">
          <template #default="{ row }">{{ row.metrics ? `${row.metrics.primary_label} = ${fmt(row.metrics.primary_value)}` : row.error }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import http from '../api/http'
import JobProgress from '../components/JobProgress.vue'
import { auth } from '../store'
import { JOB_STATUS, fmt } from '../utils'

const list = ref([])
const sys = ref({})
const loading = ref(false)
const dlg = reactive({ show: false, id: null, job: null })
let timer = null

async function load() {
  loading.value = list.value.length === 0
  try {
    ;[list.value, sys.value] = await Promise.all([http.get('/jobs'), http.get('/stats/system')])
  } finally {
    loading.value = false
  }
  clearTimeout(timer)
  if (list.value.some((j) => ['queued', 'running'].includes(j.status))) timer = setTimeout(load, 2500)
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))

function openJob(row) {
  Object.assign(dlg, { show: true, id: row.id, job: null })
}

async function cancel(row) {
  await http.post(`/jobs/${row.id}/cancel`)
  load()
}
</script>
