<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">一键预测</h2>
        <p class="page-desc">最少配置：上传数据 → 选择要预测的列 → 一键完成自动归一化、多模型训练、评估、解释与批量预测。</p>
      </div>
      <el-button v-if="step > 0" @click="reset">重新开始</el-button>
    </div>

    <div class="card mb">
      <el-steps :active="step" finish-status="success" align-center>
        <el-step title="上传数据" />
        <el-step title="选择目标与模型" />
        <el-step title="训练与预测结果" />
      </el-steps>
    </div>

    <!-- 第 1 步 -->
    <div v-if="step === 0" class="card">
      <div class="card-title">上传带有目标值的历史数据</div>
      <el-upload drag :auto-upload="false" :show-file-list="false" accept=".csv,.xlsx,.xls" :on-change="onTrainFile">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">把 CSV / Excel 文件拖到这里，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">每一行是一个样本，每一列是一个变量，其中一列是要预测的目标。没有现成数据？
            <router-link to="/templates">从数据模板开始</router-link>，或选择已有数据集：</div>
        </template>
      </el-upload>
      <div class="flex mt">
        <el-select v-model="existingId" filterable placeholder="选择已有数据集" style="width: 360px">
          <el-option v-for="d in datasets" :key="d.id" :label="`${d.name}（${d.n_rows} 行）`" :value="d.id" />
        </el-select>
        <el-button :disabled="!existingId" @click="useExisting">使用该数据集</el-button>
      </div>
      <div v-if="uploading" class="mt muted"><el-icon class="is-loading"><Loading /></el-icon> 正在上传并分析数据…</div>
    </div>

    <!-- 第 2 步 -->
    <template v-if="step === 1 && ds">
      <div class="card">
        <div class="card-title">数据画像 <span class="sub">{{ ds.name }} · {{ ds.n_rows }} 行 × {{ ds.n_cols }} 列（平台已自动识别每列类型）</span></div>
        <el-table :data="ds.profile" size="small" max-height="300">
          <el-table-column prop="name" label="列名" min-width="140" />
          <el-table-column label="识别类型" width="120">
            <template #default="{ row }"><el-tag size="small" :type="['id', 'constant', 'text', 'empty'].includes(row.type) ? 'info' : ''">{{ COLUMN_TYPES[row.type] }}</el-tag></template>
          </el-table-column>
          <el-table-column label="缺失" width="90"><template #default="{ row }">{{ row.missing ? `${(row.missing_rate * 100).toFixed(1)}%` : '-' }}</template></el-table-column>
          <el-table-column label="取值范围 / 示例" min-width="220">
            <template #default="{ row }">
              <span v-if="row.type === 'numeric'">{{ fmt(row.min) }} ~ {{ fmt(row.max) }}（均值 {{ fmt(row.mean) }}）</span>
              <span v-else class="muted">{{ (row.top_values || []).slice(0, 4).join('、') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="card">
        <div class="card-title">预测设置</div>
        <el-form label-width="120px" style="max-width: 900px">
          <el-form-item label="要预测的列">
            <el-select v-model="target" style="width: 300px">
              <el-option v-for="c in ds.profile.filter(c => ['numeric', 'categorical'].includes(c.type))" :key="c.name" :label="c.name" :value="c.name" />
            </el-select>
            <el-tag class="ml" type="success" effect="plain">自动判断为：{{ TASK[guessTask] }}任务</el-tag>
          </el-form-item>
          <el-form-item label="不参与预测的列">
            <el-select v-model="dropCols" multiple collapse-tags collapse-tags-tooltip placeholder="可选，例如另一个结果列" style="width: 300px">
              <el-option v-for="c in ds.profile.filter(c => c.name !== target)" :key="c.name" :label="c.name" :value="c.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="参与比较的模型">
            <el-checkbox-group v-model="models">
              <el-checkbox v-for="a in adapters.filter(a => a.tasks.includes(guessTask))" :key="a.key" :value="a.key" :disabled="!a.available">
                <el-tooltip :content="a.available ? a.description : a.availability"><span>{{ a.name }}</span></el-tooltip>
              </el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="待预测数据">
            <el-upload :auto-upload="false" :show-file-list="false" accept=".csv,.xlsx,.xls" :on-change="onPredictFile">
              <el-button><el-icon><Upload /></el-icon>&nbsp;上传（可选）</el-button>
            </el-upload>
            <span class="ml muted">{{ predDs ? `已上传：${predDs.name}（${predDs.n_rows} 行）` : '不含目标列的新数据，训练完成后自动批量预测' }}</span>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="submitting" :disabled="!target || !models.length" @click="start">
              <el-icon><MagicStick /></el-icon>&nbsp;一键训练并预测
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </template>

    <!-- 第 3 步 -->
    <template v-if="step >= 2">
      <div class="card">
        <div class="card-title">训练进度</div>
        <JobProgress :job-id="jobId" @done="onDone" />
      </div>
      <template v-if="best">
        <div class="card flex-between">
          <div>
            <div class="flex"><el-icon color="#f59e0b" size="20"><Trophy /></el-icon><b style="font-size: 16px">最优模型：{{ best.name }}</b>
              <el-tag :class="FAMILY[best.family]?.cls">{{ FAMILY[best.family]?.label }}</el-tag>
              <el-tag type="success">已自动发布</el-tag></div>
            <div class="muted" style="margin-top: 4px">模型 ID：{{ best.id }} · 外部终端可通过 <span class="mono">POST /api/v1/models/{{ best.id }}/predict</span> 调用</div>
          </div>
          <div class="flex">
            <el-button @click="$router.push({ path: '/predict', query: { model: best.id } })">单条预测与解释</el-button>
            <el-button @click="$router.push({ path: '/api', query: { model: best.id } })">获取 API 调用方式</el-button>
            <el-button type="primary" @click="$router.push(`/models/${best.id}`)">模型详情</el-button>
          </div>
        </div>

        <div v-if="predResult" class="card">
          <div class="card-title flex-between">
            <span>批量预测结果 <span class="sub">{{ predResult.n_rows }} 条，用时 {{ predResult.latency_ms }} ms</span></span>
            <el-button size="small" type="primary" @click="downloadPred"><el-icon><Download /></el-icon>&nbsp;下载 CSV</el-button>
          </div>
          <PredictionSummary :result="predResult" />
        </div>

        <div class="mt">
          <ModelResult :model="best" />
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http, { download } from '../api/http'
import JobProgress from '../components/JobProgress.vue'
import ModelResult from '../components/ModelResult.vue'
import PredictionSummary from '../components/PredictionSummary.vue'
import { COLUMN_TYPES, FAMILY, TASK, fmt } from '../utils'

const step = ref(0)
const uploading = ref(false)
const submitting = ref(false)
const datasets = ref([])
const existingId = ref(null)
const adapters = ref([])
const ds = ref(null)
const predDs = ref(null)
const target = ref('')
const dropCols = ref([])
const models = ref([])
const jobId = ref(null)
const best = ref(null)
const predResult = ref(null)

onMounted(async () => {
  ;[datasets.value, adapters.value] = await Promise.all([http.get('/datasets'), http.get('/adapters')])
})

const guessTask = computed(() => {
  const col = ds.value?.profile.find((c) => c.name === target.value)
  if (!col) return 'regression'
  if (col.type !== 'numeric') return 'classification'
  return col.unique <= 10 && Number.isInteger(col.min) && Number.isInteger(col.max) && col.unique / ds.value.n_rows < 0.05
    ? 'classification' : 'regression'
})

watch(guessTask, (t) => {
  models.value = adapters.value.filter((a) => a.available && a.quick_default && a.tasks.includes(t)).map((a) => a.key)
})

async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file.raw)
  return http.post('/datasets', fd)
}

async function enterStep1(d) {
  ds.value = d.profile ? d : await http.get(`/datasets/${d.id}`)
  const usable = ds.value.profile.filter((c) => ['numeric', 'categorical'].includes(c.type))
  target.value = usable.length ? usable[usable.length - 1].name : ''
  models.value = adapters.value.filter((a) => a.available && a.quick_default && a.tasks.includes(guessTask.value)).map((a) => a.key)
  step.value = 1
}

async function onTrainFile(file) {
  uploading.value = true
  try {
    await enterStep1(await uploadFile(file))
  } finally {
    uploading.value = false
  }
}

async function useExisting() {
  await enterStep1(await http.get(`/datasets/${existingId.value}`))
}

async function onPredictFile(file) {
  predDs.value = await uploadFile(file)
  ElMessage.success('待预测数据已上传')
}

async function start() {
  submitting.value = true
  try {
    const res = await http.post('/jobs/train', {
      dataset_id: ds.value.id,
      target: target.value,
      models: models.value,
      task: guessTask.value,
      drop_columns: dropCols.value
    })
    jobId.value = res.job_id
    best.value = null
    predResult.value = null
    step.value = 2
  } finally {
    submitting.value = false
  }
}

async function onDone(job) {
  if (job.status !== 'succeeded') {
    if (job.status === 'failed') ElMessage.error('训练失败：' + job.message)
    return
  }
  step.value = 3
  const bestId = job.result?.best_model_id
  if (!bestId) return
  best.value = await http.get(`/models/${bestId}`)
  if (predDs.value) {
    predResult.value = await http.post(`/models/${bestId}/predict-dataset`, { dataset_id: predDs.value.id })
  }
}

function downloadPred() {
  download(`/exports/${predResult.value.export}`, predResult.value.export)
}

function reset() {
  step.value = 0
  ds.value = null
  predDs.value = null
  jobId.value = null
  best.value = null
  predResult.value = null
  dropCols.value = []
}
</script>

<style scoped>
.ml { margin-left: 10px; }
</style>
