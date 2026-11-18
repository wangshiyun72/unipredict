<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">在线预测</h2>
        <p class="page-desc">选择模型后，可以手动输入单个样本进行预测并查看每个特征的贡献，也可以上传文件批量预测。</p>
      </div>
      <el-select v-model="modelId" filterable placeholder="选择模型" style="width: 420px" @change="loadModel">
        <el-option v-for="m in sortedModels" :key="m.id" :label="`#${m.id} ${m.name}`" :value="m.id">
          <div class="flex-between"><span>#{{ m.id }} {{ m.name }}</span>
            <span class="muted" style="font-size: 12px">{{ m.status === 'published' ? '已发布 · ' : '' }}{{ m.metrics?.primary ? `${m.metrics.primary_label} ${fmt(m.metrics.primary_value, 3)}` : '' }}</span></div>
        </el-option>
      </el-select>
    </div>

    <el-empty v-if="!model" description="请先在右上角选择一个模型" />

    <template v-else>
      <div class="card mb flex-between">
        <div class="flex">
          <el-tag :class="FAMILY[model.family]?.cls">{{ FAMILY[model.family]?.label }}</el-tag>
          <b>{{ model.name }}</b>
          <span class="muted">{{ TASK[model.task] }} · 预测「{{ model.target }}」</span>
        </div>
        <router-link :to="`/models/${model.id}`">模型详情 →</router-link>
      </div>

      <el-tabs v-model="tab" type="border-card">
        <el-tab-pane label="单条预测与解释" name="single">
          <div class="grid" style="grid-template-columns: 380px minmax(0, 1fr)">
            <div>
              <el-form label-position="top" size="default">
                <el-form-item v-for="f in model.input_schema" :key="f.name">
                  <template #label>
                    <span>{{ f.name }}</span>
                    <span v-if="f.min !== undefined && f.min !== null" class="muted" style="font-size: 12px">（训练范围 {{ fmt(f.min) }} ~ {{ fmt(f.max) }}）</span>
                  </template>
                  <el-select v-if="f.choices" v-model="record[f.name]" filterable allow-create style="width: 100%">
                    <el-option v-for="c in f.choices" :key="c" :label="c" :value="c" />
                  </el-select>
                  <el-input-number v-else-if="f.type === 'numeric'" v-model="record[f.name]" :step="stepOf(f)" controls-position="right" style="width: 100%" />
                  <el-input v-else v-model="record[f.name]" :placeholder="f.type === 'smiles' ? '例如 CCO' : ''" />
                </el-form-item>
              </el-form>
              <div class="flex">
                <el-button type="primary" :loading="running" @click="predictOne"><el-icon><Aim /></el-icon>&nbsp;预测</el-button>
                <el-button @click="resetRecord">恢复典型值</el-button>
              </div>
            </div>
            <div>
              <el-empty v-if="!single" description="填写左侧字段后点击「预测」" />
              <template v-else>
                <div class="result-box">
                  <div class="muted">预测「{{ model.target }}」</div>
                  <div class="result-value">{{ fmt(single.predictions[0]) }}</div>
                  <div class="muted" style="font-size: 12px">服务端耗时 {{ single.latency_ms }} ms</div>
                </div>
                <div v-if="single.probabilities" class="mt">
                  <div class="card-title">各类别概率</div>
                  <EChart :option="probOption" height="200px" />
                </div>
                <div v-if="single.explanations?.length" class="mt">
                  <div class="card-title">这次预测的特征贡献 <span class="sub">局部可解释性</span></div>
                  <ExplainChart :explanation="single.explanations[0]" />
                </div>
              </template>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="批量预测" name="batch">
          <div class="flex mb" style="flex-wrap: wrap">
            <el-upload :auto-upload="false" :show-file-list="false" accept=".csv,.xlsx,.xls" :on-change="batchUpload">
              <el-button type="primary" :loading="running"><el-icon><Upload /></el-icon>&nbsp;上传文件并预测</el-button>
            </el-upload>
            <span class="muted">或选择已有数据集：</span>
            <el-select v-model="batchDs" filterable style="width: 300px" placeholder="数据集">
              <el-option v-for="d in datasets" :key="d.id" :label="`${d.name}（${d.n_rows} 行）`" :value="d.id" />
            </el-select>
            <el-button :disabled="!batchDs" :loading="running" @click="batchPredict(batchDs)">预测</el-button>
          </div>
          <div class="muted mb" style="font-size: 12px">文件需包含以下字段：{{ model.input_schema.map(f => f.name).join('、') }}。如果包含真实值列「{{ model.target }}」，会自动给出评估指标。</div>
          <template v-if="batch">
            <div class="flex-between mb">
              <b>共 {{ batch.n_rows }} 条，服务端耗时 {{ batch.latency_ms }} ms</b>
              <el-button size="small" type="primary" @click="download(`/exports/${batch.export}`, batch.export)"><el-icon><Download /></el-icon>&nbsp;下载结果 CSV</el-button>
            </div>
            <PredictionSummary :result="batch" />
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import http, { download } from '../api/http'
import EChart from '../components/EChart.vue'
import ExplainChart from '../components/ExplainChart.vue'
import PredictionSummary from '../components/PredictionSummary.vue'
import { FAMILY, TASK, fmt } from '../utils'

const route = useRoute()
const models = ref([])
const datasets = ref([])
const modelId = ref(null)
const model = ref(null)
const tab = ref('single')
const record = reactive({})
const single = ref(null)
const batch = ref(null)
const batchDs = ref(null)
const running = ref(false)
const sortedModels = computed(() => [...models.value].sort((a, b) => (b.status === 'published') - (a.status === 'published') || b.id - a.id))

onMounted(async () => {
  ;[models.value, datasets.value] = await Promise.all([http.get('/models'), http.get('/datasets')])
  const preferred = Number(route.query.model) || models.value.find((m) => m.status === 'published' && m.is_best)?.id
    || models.value.find((m) => m.status === 'published')?.id
  if (preferred) {
    modelId.value = preferred
    loadModel()
  }
})

async function loadModel() {
  model.value = await http.get(`/models/${modelId.value}`)
  single.value = null
  batch.value = null
  resetRecord()
}

function resetRecord() {
  for (const k of Object.keys(record)) delete record[k]
  for (const f of model.value.input_schema || []) record[f.name] = f.default ?? null
}

function stepOf(f) {
  if (f.min === undefined || f.max === undefined || f.min === null) return 1
  const range = f.max - f.min
  if (range <= 2) return 0.01
  if (range <= 20) return 0.1
  return 1
}

async function predictOne() {
  running.value = true
  try {
    single.value = await http.post(`/models/${model.value.id}/predict`, { records: [{ ...record }], explain: true })
  } finally {
    running.value = false
  }
}

async function batchPredict(dsId) {
  running.value = true
  try {
    batch.value = await http.post(`/models/${model.value.id}/predict-dataset`, { dataset_id: dsId })
  } finally {
    running.value = false
  }
}

async function batchUpload(file) {
  const fd = new FormData()
  fd.append('file', file.raw)
  const ds = await http.post('/datasets', fd)
  datasets.value.unshift(ds)
  batchDs.value = ds.id
  await batchPredict(ds.id)
}

const probOption = computed(() => {
  const p = single.value?.probabilities?.[0] || {}
  const names = Object.keys(p)
  return {
    grid: { left: 10, right: 50, top: 10, bottom: 10, containLabel: true },
    xAxis: { type: 'value', max: 1 },
    yAxis: { type: 'category', data: names },
    series: [{ type: 'bar', data: names.map((n) => p[n]), itemStyle: { color: '#0f766e', borderRadius: 3 },
      label: { show: true, position: 'right', formatter: (x) => (x.value * 100).toFixed(1) + '%' } }]
  }
})
</script>

<style scoped>
.result-box { background: linear-gradient(135deg, #f0fdfa, #ecfeff); border: 1px solid #99f6e4; border-radius: 10px; padding: 18px 20px; }
.result-value { font-size: 36px; font-weight: 700; color: #0f766e; margin: 4px 0; font-variant-numeric: tabular-nums; }
@media (max-width: 1000px) { .grid { grid-template-columns: 1fr !important; } }
</style>
