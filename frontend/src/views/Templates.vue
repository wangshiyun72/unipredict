<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">数据模板</h2>
        <p class="page-desc">面向化工、环境等学科的预置预测场景。每个模板规定了字段、单位和目标列，并附带示例数据；
          按模板整理自己的数据即可直接上传预测，也可以用示例数据一键体验完整流程。</p>
      </div>
    </div>

    <div class="grid grid-2">
      <div v-for="t in list" :key="t.key" class="card tpl card-hover">
        <div class="flex-between">
          <div class="flex">
            <div class="tpl-icon"><el-icon size="22"><component :is="icons[t.key] || 'Collection'" /></el-icon></div>
            <div>
              <div class="tpl-name">{{ t.name }}</div>
              <div class="muted" style="font-size: 12px">{{ t.domain }} · {{ TASK[t.task] }} · 目标列「{{ t.target }}」</div>
            </div>
          </div>
          <el-tag v-if="t.simulated" type="warning" effect="plain">模拟示例数据</el-tag>
          <el-tag v-else type="success" effect="plain">公开数据集</el-tag>
        </div>
        <p class="desc">{{ t.description }}</p>
        <div class="scenario"><b>应用场景：</b>{{ t.scenario }}</div>
        <div class="muted src">数据来源：{{ t.source }}<span v-if="t.ready">（{{ t.n_rows }} 行）</span></div>
        <div class="flex flex-wrap actions">
          <el-button size="small" @click="showDetail(t)">字段说明</el-button>
          <el-button size="small" @click="downloadTpl(t)"><el-icon><Download /></el-icon>&nbsp;下载填写模板</el-button>
          <template v-if="t.ready">
            <el-button size="small" :loading="busy[t.key] === 'use'" @click="useTpl(t)">导入为数据集</el-button>
            <el-button size="small" type="primary" :loading="busy[t.key] === 'train'" @click="quickTrain(t)">
              <el-icon><MagicStick /></el-icon>&nbsp;一键演示训练
            </el-button>
          </template>
          <el-button v-else size="small" type="warning" :loading="busy[t.key] === 'prepare'" @click="prepare(t)">准备示例数据（需联网下载）</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="detail.show" :title="detail.t?.name" width="760px">
      <template v-if="detail.t">
        <el-table :data="detail.t.columns" size="small" border>
          <el-table-column prop="name" label="字段名" width="140">
            <template #default="{ row }"><b v-if="row.target" style="color: #0f766e">{{ row.name }}（目标）</b><span v-else>{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column prop="unit" label="单位" width="110" />
          <el-table-column prop="desc" label="说明" />
        </el-table>
        <div v-if="detail.preview" class="mt">
          <div class="card-title">示例数据（前 10 行）</div>
          <el-table :data="detail.preview" size="small" max-height="280" border>
            <el-table-column v-for="c in detail.t.columns" :key="c.name" :prop="c.name" :label="c.name" min-width="100">
              <template #default="{ row }">{{ fmt(row[c.name]) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="job.show" title="一键演示训练" width="640px" :close-on-click-modal="false">
      <p class="muted">模板「{{ job.name }}」· 参与比较的模型：{{ job.models.join('、') }}</p>
      <JobProgress v-if="job.id" :job-id="job.id" @done="onJobDone" />
      <template #footer>
        <el-button @click="job.show = false">后台运行，稍后查看</el-button>
        <el-button type="primary" :disabled="!job.bestId" @click="$router.push(`/models/${job.bestId}`)">查看最优模型</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http, { download } from '../api/http'
import JobProgress from '../components/JobProgress.vue'
import { TASK, fmt } from '../utils'

const list = ref([])
const busy = reactive({})
const detail = reactive({ show: false, t: null, preview: null })
const job = reactive({ show: false, id: null, name: '', models: [], bestId: null })
const icons = { aquatic_toxicity: 'Warning', effluent_quality: 'Drizzling', solubility: 'Mug', reaction_yield: 'TrendCharts' }

async function load() {
  list.value = await http.get('/templates')
}
onMounted(load)

async function showDetail(t) {
  const d = await http.get(`/templates/${t.key}`)
  Object.assign(detail, { show: true, t: d, preview: d.preview })
}

function downloadTpl(t) {
  download(`/templates/${t.key}/download`, `${t.name}_填写模板.csv`)
}

async function prepare(t) {
  busy[t.key] = 'prepare'
  try {
    await http.post(`/templates/${t.key}/prepare`)
    ElMessage.success('示例数据已准备好')
    await load()
  } finally {
    busy[t.key] = null
  }
}

async function useTpl(t) {
  busy[t.key] = 'use'
  try {
    const ds = await http.post(`/templates/${t.key}/use`)
    ElMessage.success(`已导入为数据集「${ds.name}」`)
  } finally {
    busy[t.key] = null
  }
}

async function quickTrain(t) {
  busy[t.key] = 'train'
  try {
    const res = await http.post(`/templates/${t.key}/quick-train`, {})
    Object.assign(job, { show: true, id: res.job_id, name: t.name, models: res.models, bestId: null })
  } finally {
    busy[t.key] = null
  }
}

function onJobDone(j) {
  if (j.status === 'succeeded') {
    job.bestId = j.result?.best_model_id
    ElMessage.success('训练完成')
  }
}
</script>

<style scoped>
.tpl { display: flex; flex-direction: column; }
.actions { margin-top: auto; padding-top: 14px; }
.tpl-icon { width: 40px; height: 40px; border-radius: 10px; background: #e7f1f0; color: #0f766e; display: flex; align-items: center; justify-content: center; }
.tpl-name { font-weight: 600; font-size: 16px; }
.desc { margin: 12px 0 8px; line-height: 1.7; }
.scenario { background: #f8fafc; border-radius: 6px; padding: 8px 10px; font-size: 13px; line-height: 1.7; color: #334155; }
.src { font-size: 12px; margin-top: 8px; }
</style>
