<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">模型仓库</h2>
        <p class="page-desc">所有训练得到的模型和接入的外部模型统一登记在这里。<b>已发布</b>的模型可以被外部终端通过 API Key 调用。</p>
      </div>
      <div class="flex">
        <el-popconfirm v-if="auth.isAdmin" width="280" title="把所有训练任务中的最优模型设为「已发布 + 全平台公开」，所有注册用户都能使用，确定？" @confirm="publishBest">
          <template #reference><el-button type="success" plain><el-icon><Promotion /></el-icon>&nbsp;一键公开最优模型</el-button></template>
        </el-popconfirm>
        <el-button type="primary" @click="imp.show = true"><el-icon><Connection /></el-icon>&nbsp;接入外部模型</el-button>
      </div>
    </div>

    <div class="card">
      <div class="flex mb">
        <el-radio-group v-model="filter.mine" size="small" @change="load">
          <el-radio-button :value="false">我可访问的</el-radio-button>
          <el-radio-button :value="true">我创建的</el-radio-button>
        </el-radio-group>
        <el-select v-model="filter.task" size="small" clearable placeholder="任务类型" style="width: 120px" @change="load">
          <el-option label="回归" value="regression" /><el-option label="分类" value="classification" />
        </el-select>
        <el-select v-model="filter.status" size="small" clearable placeholder="状态" style="width: 120px" @change="load">
          <el-option v-for="(s, k) in STATUS" :key="k" :label="s.label" :value="k" />
        </el-select>
        <el-input v-model="filter.q" size="small" placeholder="搜索名称" clearable style="width: 200px" />
      </div>
      <el-table :data="shown" v-loading="loading" empty-text="还没有模型，去「一键预测」或「模型训练」训练一个">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="模型" min-width="260">
          <template #default="{ row }">
            <div class="flex">
              <el-tag size="small" :class="FAMILY[row.family]?.cls">{{ FAMILY[row.family]?.label }}</el-tag>
              <router-link :to="`/models/${row.id}`">{{ row.name }}</router-link>
              <el-icon v-if="row.is_best" color="#f59e0b"><Trophy /></el-icon>
            </div>
            <div class="muted" style="font-size: 12px">{{ row.dataset_name || '外部模型' }} · {{ row.owner_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="任务" width="110"><template #default="{ row }">{{ TASK[row.task] }}·{{ row.target }}</template></el-table-column>
        <el-table-column label="主指标" width="130">
          <template #default="{ row }"><span v-if="row.metrics?.primary">{{ row.metrics.primary_label }} {{ fmt(row.metrics.primary_value, 3) }}</span><span v-else class="muted">-</span></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag size="small" :type="STATUS[row.status]?.type">{{ STATUS[row.status]?.label }}</el-tag></template>
        </el-table-column>
        <el-table-column label="共享范围" width="130">
          <template #default="{ row }">
            <el-select v-if="row.owner_id === auth.user.id || auth.isAdmin" :model-value="row.visibility" size="small" @change="(v) => patch(row, { visibility: v })">
              <el-option v-for="(l, k) in VISIBILITY" :key="k" :label="l" :value="k" />
            </el-select>
            <span v-else>{{ VISIBILITY[row.visibility] }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="calls" label="调用" width="70" />
        <el-table-column prop="created_at" label="创建时间" width="165" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="$router.push({ path: '/predict', query: { model: row.id } })">预测</el-button>
            <template v-if="row.owner_id === auth.user.id || auth.isAdmin">
              <el-button v-if="row.status !== 'published'" size="small" text type="success" @click="patch(row, { status: 'published' })">发布</el-button>
              <el-button v-else size="small" text type="warning" @click="patch(row, { status: 'ready' })">取消发布</el-button>
              <el-popconfirm title="确定删除该模型？" @confirm="remove(row)">
                <template #reference><el-button size="small" text type="danger">删除</el-button></template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="imp.show" title="接入外部模型" width="600px">
      <el-alert type="info" :closable="false" show-icon class="mb"
                title="把在平台外训练好的模型接入平台，统一通过网页和 REST API 提供预测服务。推荐 ONNX 格式（PyTorch / TensorFlow / scikit-learn 都可导出）；joblib/pickle 格式仅管理员可导入。" />
      <el-form label-width="110px">
        <el-form-item label="模型文件">
          <el-upload :auto-upload="false" :limit="1" accept=".onnx,.joblib,.pkl" :on-change="(f) => (imp.file = f.raw)" :on-remove="() => (imp.file = null)">
            <el-button>选择 .onnx / .joblib 文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="模型名称"><el-input v-model="imp.name" /></el-form-item>
        <el-form-item label="任务类型">
          <el-radio-group v-model="imp.task"><el-radio value="regression">回归</el-radio><el-radio value="classification">分类</el-radio></el-radio-group>
        </el-form-item>
        <el-form-item label="预测目标名"><el-input v-model="imp.target" placeholder="例如：LC50" /></el-form-item>
        <el-form-item label="输入特征">
          <el-input v-model="imp.features" type="textarea" :rows="2" placeholder="按模型输入顺序，用英文逗号分隔，例如：温度,压力,流量" />
        </el-form-item>
        <el-form-item v-if="imp.task === 'classification'" label="类别名">
          <el-input v-model="imp.classes" placeholder="可选，按模型输出顺序，逗号分隔" />
        </el-form-item>
        <el-form-item label="样例数据">
          <el-upload :auto-upload="false" :limit="1" accept=".csv,.xlsx" :on-change="(f) => (imp.sample = f.raw)" :on-remove="() => (imp.sample = null)">
            <el-button>可选：上传样例 CSV</el-button>
          </el-upload>
          <div class="muted" style="font-size: 12px; line-height: 1.5">用于生成输入表单默认值和单样本可解释性的基线</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="imp.show = false">取消</el-button>
        <el-button type="primary" :loading="imp.loading" @click="doImport">接入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { auth } from '../store'
import { FAMILY, STATUS, TASK, VISIBILITY, fmt } from '../utils'

const list = ref([])
const loading = ref(false)
const filter = reactive({ mine: false, task: '', status: '', q: '' })
const imp = reactive({ show: false, file: null, sample: null, name: '', task: 'regression', target: '', features: '', classes: '', loading: false })

const shown = computed(() => list.value.filter((m) => !filter.q || m.name.includes(filter.q)))

async function load() {
  loading.value = true
  try {
    list.value = await http.get('/models', { params: { mine: filter.mine, task: filter.task || undefined, status: filter.status || undefined } })
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function patch(row, data) {
  await http.patch(`/models/${row.id}`, data)
  Object.assign(row, data)
  ElMessage.success(data.status === 'published' ? '已发布，外部终端现在可以通过 API 调用' : '已更新')
}

async function publishBest() {
  const res = await http.post('/admin/publish-best')
  ElMessage.success(res.message)
  load()
}

async function remove(row) {
  await http.delete(`/models/${row.id}`)
  ElMessage.success('已删除')
  load()
}

async function doImport() {
  if (!imp.file || !imp.name || !imp.features) return ElMessage.warning('请填写模型文件、名称和输入特征')
  const fd = new FormData()
  fd.append('file', imp.file)
  fd.append('name', imp.name)
  fd.append('task', imp.task)
  fd.append('target', imp.target || '预测值')
  fd.append('features', imp.features.replace(/，/g, ','))
  if (imp.classes) fd.append('classes', imp.classes.replace(/，/g, ','))
  if (imp.sample) fd.append('sample_file', imp.sample)
  imp.loading = true
  try {
    const res = await http.post('/models/import', fd)
    ElMessage.success(res.message)
    imp.show = false
    load()
  } finally {
    imp.loading = false
  }
}
</script>
