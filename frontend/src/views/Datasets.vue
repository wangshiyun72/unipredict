<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">数据集</h2>
        <p class="page-desc">上传 CSV / Excel，平台自动识别编码与字段类型并生成数据画像。可设置为团队共享，便于课题组成员共同使用。</p>
      </div>
      <el-upload :auto-upload="false" :show-file-list="false" accept=".csv,.xlsx,.xls" :on-change="upload">
        <el-button type="primary" :loading="uploading"><el-icon><Upload /></el-icon>&nbsp;上传数据集</el-button>
      </el-upload>
    </div>

    <div class="card">
      <el-table :data="list" v-loading="loading" empty-text="还没有数据集，上传一个或从「数据模板」导入">
        <el-table-column label="名称" min-width="220">
          <template #default="{ row }">
            <el-link type="primary" @click="open(row)">{{ row.name }}</el-link>
            <el-tag v-if="row.template_key" size="small" effect="plain" style="margin-left: 6px">模板</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="规模" width="130"><template #default="{ row }">{{ row.n_rows }} 行 × {{ row.n_cols }} 列</template></el-table-column>
        <el-table-column label="所有者" width="140"><template #default="{ row }">{{ row.owner_name }}<div class="muted" style="font-size: 12px">{{ row.owner_team }}</div></template></el-table-column>
        <el-table-column label="共享范围" width="140">
          <template #default="{ row }">
            <el-select v-if="row.owner_id === auth.user.id || auth.isAdmin" :model-value="row.visibility" size="small" @change="(v) => patch(row, { visibility: v })">
              <el-option v-for="(l, k) in VISIBILITY" :key="k" :label="l" :value="k" />
            </el-select>
            <span v-else>{{ VISIBILITY[row.visibility] }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="170" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="open(row)">查看</el-button>
            <el-button size="small" text type="primary" @click="$router.push({ path: '/train', query: { dataset: row.id } })">训练</el-button>
            <el-popconfirm v-if="row.owner_id === auth.user.id || auth.isAdmin" title="确定删除该数据集？" @confirm="remove(row)">
              <template #reference><el-button size="small" text type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="drawer.show" :title="drawer.ds?.name" size="70%">
      <template v-if="drawer.ds">
        <p v-if="drawer.ds.description" class="muted">{{ drawer.ds.description }}</p>
        <div class="card-title">数据画像</div>
        <el-table :data="drawer.ds.profile" size="small" border>
          <el-table-column prop="name" label="列名" min-width="140" />
          <el-table-column label="类型" width="110"><template #default="{ row }">{{ COLUMN_TYPES[row.type] }}</template></el-table-column>
          <el-table-column label="缺失" width="90"><template #default="{ row }">{{ row.missing }}</template></el-table-column>
          <el-table-column prop="unique" label="不同取值" width="90" />
          <el-table-column label="均值" width="100"><template #default="{ row }">{{ fmt(row.mean) }}</template></el-table-column>
          <el-table-column label="标准差" width="100"><template #default="{ row }">{{ fmt(row.std) }}</template></el-table-column>
          <el-table-column label="范围 / 常见取值" min-width="200">
            <template #default="{ row }">
              <span v-if="row.type === 'numeric'">{{ fmt(row.min) }} ~ {{ fmt(row.max) }}</span>
              <span v-else class="muted">{{ (row.top_values || []).slice(0, 5).join('、') }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="card-title mt">数据预览（前 20 行）</div>
        <el-table :data="drawer.ds.preview" size="small" border max-height="400">
          <el-table-column v-for="c in drawer.ds.profile" :key="c.name" :prop="c.name" :label="c.name" min-width="110">
            <template #default="{ row }">{{ fmt(row[c.name]) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { auth } from '../store'
import { COLUMN_TYPES, VISIBILITY, fmt } from '../utils'

const list = ref([])
const loading = ref(false)
const uploading = ref(false)
const drawer = reactive({ show: false, ds: null })

async function load() {
  loading.value = true
  try { list.value = await http.get('/datasets') } finally { loading.value = false }
}
onMounted(load)

async function upload(file) {
  const fd = new FormData()
  fd.append('file', file.raw)
  uploading.value = true
  try {
    const ds = await http.post('/datasets', fd)
    ElMessage.success(`已上传：${ds.name}（${ds.n_rows} 行）`)
    await load()
    open(ds)
  } finally {
    uploading.value = false
  }
}

async function open(row) {
  drawer.ds = await http.get(`/datasets/${row.id}`)
  drawer.show = true
}

async function patch(row, data) {
  await http.patch(`/datasets/${row.id}`, data)
  Object.assign(row, data)
  ElMessage.success('已更新')
}

async function remove(row) {
  await http.delete(`/datasets/${row.id}`)
  ElMessage.success('已删除')
  load()
}
</script>
