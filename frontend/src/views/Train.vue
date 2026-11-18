<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">模型训练</h2>
        <p class="page-desc">在服务器上训练 / 部署一组通用模型与轻量模型。训练任务进入后台队列异步执行，可同时比较多个模型，平台自动选出最优模型。</p>
      </div>
    </div>

    <div class="grid" style="grid-template-columns: minmax(0, 1fr) 420px">
      <div class="card">
        <div class="card-title">① 数据与目标</div>
        <el-form label-width="110px">
          <el-form-item label="数据集">
            <el-select v-model="form.dataset_id" filterable placeholder="选择数据集" style="width: 100%" @change="loadDataset">
              <el-option v-for="d in datasets" :key="d.id" :label="`${d.name}（${d.n_rows} 行 × ${d.n_cols} 列）`" :value="d.id" />
            </el-select>
          </el-form-item>
          <template v-if="ds">
            <el-form-item label="目标列">
              <el-select v-model="form.target" style="width: 100%">
                <el-option v-for="c in usableCols" :key="c.name" :label="`${c.name}（${COLUMN_TYPES[c.type]}）`" :value="c.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="任务类型">
              <el-radio-group v-model="form.task">
                <el-radio-button value="">自动判断</el-radio-button>
                <el-radio-button value="regression">回归（预测数值）</el-radio-button>
                <el-radio-button value="classification">分类（预测类别）</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="排除的列">
              <el-select v-model="form.drop_columns" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="可选">
                <el-option v-for="c in ds.profile.filter(c => c.name !== form.target)" :key="c.name" :label="c.name" :value="c.name" />
              </el-select>
            </el-form-item>
          </template>
        </el-form>

        <div class="card-title mt">② 自动归一化与验证</div>
        <el-form label-width="110px">
          <el-form-item label="归一化方式">
            <el-select v-model="form.scaler" style="width: 260px">
              <el-option label="自动选择（推荐）" value="auto" />
              <el-option label="Z-score 标准化" value="standard" />
              <el-option label="Min-Max 归一化" value="minmax" />
              <el-option label="Robust 稳健缩放" value="robust" />
              <el-option label="不缩放" value="none" />
            </el-select>
            <span class="muted" style="margin-left: 10px; font-size: 12px">自动模式根据离群值与取值范围选择</span>
          </el-form-item>
          <el-form-item label="测试集比例">
            <el-slider v-model="form.test_size" :min="0.1" :max="0.4" :step="0.05" :format-tooltip="(v) => `${Math.round(v * 100)}%`" style="width: 260px" />
          </el-form-item>
          <el-form-item label="自动发布">
            <el-switch v-model="form.auto_publish" active-text="训练完成后自动发布最优模型（可被 API 调用）" />
          </el-form-item>
        </el-form>
      </div>

      <div class="card">
        <div class="card-title">③ 选择模型 <span class="sub">已选 {{ form.models.length }} 个</span></div>
        <div v-for="(group, fam) in grouped" :key="fam" class="mb">
          <div class="fam-title"><el-tag size="small" :class="FAMILY[fam]?.cls">{{ FAMILY[fam]?.label }}</el-tag></div>
          <div v-for="a in group" :key="a.key" class="model-item">
            <el-checkbox v-model="form.models" :value="a.key" :disabled="!a.available || !taskOk(a)">
              <b>{{ a.name }}</b>
              <el-tag v-if="a.uses_gpu" size="small" type="success" effect="plain" style="margin-left: 4px">GPU</el-tag>
            </el-checkbox>
            <div class="muted model-desc">{{ a.available ? a.description : a.availability }}</div>
            <el-collapse v-if="a.params.length && form.models.includes(a.key)" class="param-box">
              <el-collapse-item title="调整参数（可选）">
                <el-form label-width="120px" size="small">
                  <el-form-item v-for="p in a.params" :key="p.name" :label="p.label">
                    <el-select v-if="p.type === 'choice'" v-model="params[a.key][p.name]" style="width: 150px">
                      <el-option v-for="c in p.choices" :key="c" :label="c" :value="c" />
                    </el-select>
                    <el-input-number v-else v-model="params[a.key][p.name]" :min="p.min" :max="p.max"
                                     :step="p.type === 'int' ? 1 : (p.default < 0.01 ? 0.0001 : 0.01)"
                                     :precision="p.type === 'int' ? 0 : undefined" controls-position="right" style="width: 150px" />
                  </el-form-item>
                </el-form>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
        <el-button type="primary" size="large" style="width: 100%" :disabled="!canSubmit" :loading="submitting" @click="submit">
          提交训练任务
        </el-button>
      </div>
    </div>

    <div v-if="jobId" class="card mt">
      <div class="card-title">训练进度</div>
      <JobProgress :job-id="jobId" @done="onDone" />
      <div v-if="leaderboard.length" class="mt">
        <el-table :data="leaderboard" size="small">
          <el-table-column label="模型" min-width="200">
            <template #default="{ row }">
              <router-link v-if="row.model_id" :to="`/models/${row.model_id}`">{{ row.name }}</router-link><span v-else>{{ row.name }}</span>
              <el-icon v-if="row.is_best" color="#f59e0b" style="margin-left: 4px"><Trophy /></el-icon>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag size="small" :type="row.status === 'succeeded' ? 'success' : 'danger'">{{ row.status === 'succeeded' ? '成功' : '失败' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="主指标" width="160"><template #default="{ row }">{{ row.metrics ? `${row.metrics.primary_label} ${fmt(row.metrics.primary_value)}` : row.error }}</template></el-table-column>
          <el-table-column label="训练耗时" width="100"><template #default="{ row }">{{ row.train_seconds ? row.train_seconds + ' s' : '-' }}</template></el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import JobProgress from '../components/JobProgress.vue'
import { COLUMN_TYPES, FAMILY, fmt } from '../utils'

const route = useRoute()
const datasets = ref([])
const adapters = ref([])
const ds = ref(null)
const submitting = ref(false)
const jobId = ref(null)
const leaderboard = ref([])
const params = reactive({})
const form = reactive({ dataset_id: null, target: '', task: '', drop_columns: [], scaler: 'auto', test_size: 0.2, auto_publish: true, models: [] })

const usableCols = computed(() => (ds.value?.profile || []).filter((c) => ['numeric', 'categorical'].includes(c.type)))
const grouped = computed(() => {
  const g = {}
  for (const a of adapters.value) (g[a.family] = g[a.family] || []).push(a)
  return g
})
const canSubmit = computed(() => form.dataset_id && form.target && form.models.length)

function taskOk(a) {
  return !form.task || a.tasks.includes(form.task)
}

onMounted(async () => {
  ;[datasets.value, adapters.value] = await Promise.all([http.get('/datasets'), http.get('/adapters')])
  for (const a of adapters.value) params[a.key] = Object.fromEntries(a.params.map((p) => [p.name, p.default]))
  form.models = adapters.value.filter((a) => a.available && a.quick_default).map((a) => a.key)
  if (route.query.dataset) {
    form.dataset_id = Number(route.query.dataset)
    loadDataset()
  }
})

async function loadDataset() {
  ds.value = await http.get(`/datasets/${form.dataset_id}`)
  const cols = usableCols.value
  form.target = cols.length ? cols[cols.length - 1].name : ''
  form.drop_columns = []
}

async function submit() {
  submitting.value = true
  try {
    const body = { ...form, task: form.task || null, params: Object.fromEntries(form.models.map((k) => [k, params[k]])) }
    const res = await http.post('/jobs/train', body)
    jobId.value = res.job_id
    leaderboard.value = []
    ElMessage.success(`已提交任务 #${res.job_id}`)
  } finally {
    submitting.value = false
  }
}

function onDone(job) {
  if (job.status === 'succeeded') leaderboard.value = job.result?.leaderboard || []
}
</script>

<style scoped>
.fam-title { margin-bottom: 6px; }
.model-item { padding: 6px 0 6px 4px; border-bottom: 1px dashed var(--border); }
.model-desc { font-size: 12px; margin-left: 24px; line-height: 1.5; }
.param-box { margin: 6px 0 0 24px; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr !important; } }
</style>
