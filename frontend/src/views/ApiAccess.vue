<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">API 接入</h2>
        <p class="page-desc">外部终端（实验室工作站脚本、Excel/MATLAB、仪器上位机、手机 App 等）凭 API Key 通过 REST 接口调用已发布的模型。
          每个 Key 有独立的调用限额（令牌桶限流），超出返回 429。</p>
      </div>
      <el-button tag="a" href="/docs" target="_blank"><el-icon><Document /></el-icon>&nbsp;完整接口文档（Swagger）</el-button>
    </div>

    <div class="card">
      <div class="card-title flex-between">
        <span>我的 API Key</span>
        <el-button type="primary" size="small" @click="create.show = true"><el-icon><Plus /></el-icon>&nbsp;创建 API Key</el-button>
      </div>
      <el-table :data="keys" size="small" empty-text="还没有 API Key">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="Key" width="180"><template #default="{ row }"><span class="mono">{{ row.key_prefix }}…</span></template></el-table-column>
        <el-table-column label="限额" width="120"><template #default="{ row }">{{ row.rate_limit_per_min }} 次/分钟</template></el-table-column>
        <el-table-column prop="calls" label="累计调用" width="100" />
        <el-table-column label="最近使用" width="170"><template #default="{ row }">{{ row.last_used_at || '从未使用' }}</template></el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-switch :model-value="!!row.is_active" @change="(v) => toggle(row, v)" /></template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-popconfirm title="删除后使用该 Key 的程序将无法调用，确定？" @confirm="remove(row)">
              <template #reference><el-button size="small" text type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="card">
      <div class="card-title flex-between">
        <span>调用示例</span>
        <el-select v-model="modelId" filterable placeholder="选择模型生成示例" style="width: 380px" @change="loadSchema">
          <el-option v-for="m in models" :key="m.id" :label="`#${m.id} ${m.name}${m.status === 'published' ? '' : '（未发布）'}`" :value="m.id" />
        </el-select>
      </div>
      <el-alert v-if="schemaModel && schemaModel.status !== 'published'" type="warning" :closable="false" show-icon class="mb"
                title="该模型尚未发布，API Key 无法调用（模型创建者本人的 Key 除外）。请在模型仓库中点击「发布」。" />
      <el-descriptions :column="1" border size="small" class="mb">
        <el-descriptions-item label="服务地址"><span class="mono">{{ apiBase }}/api/v1</span>
          <span class="muted" style="margin-left: 8px; font-size: 12px">局域网内其他电脑请把 localhost 换成本服务器的 IP 地址</span></el-descriptions-item>
        <el-descriptions-item label="认证方式">请求头 <span class="mono">X-API-Key: upk_xxxxx</span></el-descriptions-item>
        <el-descriptions-item label="查询输入字段"><span class="mono">GET /api/v1/models/{{ modelId || '{id}' }}/schema</span></el-descriptions-item>
        <el-descriptions-item label="JSON 预测"><span class="mono">POST /api/v1/models/{{ modelId || '{id}' }}/predict</span>（一次可发送多条，<span class="mono">"explain": true</span> 返回特征贡献）</el-descriptions-item>
        <el-descriptions-item label="文件批量预测"><span class="mono">POST /api/v1/models/{{ modelId || '{id}' }}/predict-file</span>（multipart 上传 CSV/Excel，返回带预测列的 CSV）</el-descriptions-item>
      </el-descriptions>
      <el-tabs v-model="lang">
        <el-tab-pane v-for="(code, name) in samples" :key="name" :label="name" :name="name">
          <div class="flex-between mb"><span /><el-button size="small" @click="copy(code)"><el-icon><CopyDocument /></el-icon>&nbsp;复制</el-button></div>
          <pre class="code-block">{{ code }}</pre>
        </el-tab-pane>
      </el-tabs>
    </div>

    <div class="card">
      <div class="card-title">返回状态码</div>
      <el-table :data="codes" size="small">
        <el-table-column prop="code" label="状态码" width="90" />
        <el-table-column prop="meaning" label="含义" min-width="200" />
        <el-table-column prop="action" label="调用方应如何处理" min-width="260" />
      </el-table>
    </div>

    <el-dialog v-model="create.show" title="创建 API Key" width="460px" @closed="create.result = null">
      <template v-if="!create.result">
        <el-form label-width="90px">
          <el-form-item label="用途说明"><el-input v-model="create.name" placeholder="例如：反应釜监控脚本" /></el-form-item>
          <el-form-item v-if="auth.isAdmin" label="限额">
            <el-input-number v-model="create.rate" :min="1" :max="6000" /> <span class="muted" style="margin-left: 6px">次/分钟</span>
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <el-alert type="warning" :closable="false" show-icon title="请立即复制保存，关闭后无法再次查看完整 Key" class="mb" />
        <pre class="code-block">{{ create.result }}</pre>
      </template>
      <template #footer>
        <el-button v-if="!create.result" type="primary" @click="doCreate">创建</el-button>
        <template v-else>
          <el-button @click="copy(create.result)">复制</el-button>
          <el-button type="primary" @click="create.show = false">我已保存</el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { auth } from '../store'

const route = useRoute()
const keys = ref([])
const models = ref([])
const modelId = ref(null)
const schema = ref(null)
const schemaModel = computed(() => models.value.find((m) => m.id === modelId.value))
const lang = ref('Python')
const create = reactive({ show: false, name: '', rate: 60, result: null })
const apiBase = location.port === '5173' ? `${location.protocol}//${location.hostname}:8000` : location.origin

const codes = [
  { code: 200, meaning: '成功', action: '读取 predictions（分类任务还有 probabilities）' },
  { code: 400, meaning: '输入数据有误（缺少字段、格式不对）', action: '按 /schema 返回的字段检查请求体' },
  { code: 401, meaning: 'API Key 无效或已停用', action: '检查请求头 X-API-Key' },
  { code: 404, meaning: '模型不存在或未发布', action: '确认模型 ID，并在网页中发布该模型' },
  { code: 413, meaning: '单次请求条数超过上限', action: '分批发送' },
  { code: 429, meaning: '超过该 Key 的调用限额（限流）', action: '按响应头 Retry-After 等待后重试' },
  { code: 503, meaning: '服务器预测并发已满，排队超时', action: '稍后重试（可指数退避）' }
]

onMounted(async () => {
  ;[keys.value, models.value] = await Promise.all([http.get('/keys'), http.get('/models')])
  const q = Number(route.query.model)
  modelId.value = q || models.value.find((m) => m.status === 'published')?.id || models.value[0]?.id || null
  if (modelId.value) loadSchema()
})

async function loadSchema() {
  schema.value = await http.get(`/models/${modelId.value}/schema`)
}

const samples = computed(() => {
  const id = modelId.value || 1
  const body = schema.value ? { ...schema.value.example_request, explain: false } : { records: [{ '特征1': 1.0 }] }
  const json = JSON.stringify(body, null, 2)
  const url = `${apiBase}/api/v1/models/${id}/predict`
  const firstRec = JSON.stringify(body.records[0])
  return {
    Python: `import requests

API_KEY = "upk_你的API Key"
url = "${url}"
data = ${json}

r = requests.post(url, json=data, headers={"X-API-Key": API_KEY}, timeout=60)
r.raise_for_status()
result = r.json()
print(result["predictions"])          # 预测值列表
print(r.headers.get("X-RateLimit-Remaining"))  # 本分钟剩余调用次数`,
    'Python（文件批量）': `import requests

API_KEY = "upk_你的API Key"
url = "${apiBase}/api/v1/models/${id}/predict-file"
with open("待预测数据.csv", "rb") as f:
    r = requests.post(url, files={"file": f}, headers={"X-API-Key": API_KEY}, timeout=300)
r.raise_for_status()
open("预测结果.csv", "wb").write(r.content)`,
    curl: `curl -X POST "${url}" \\
  -H "X-API-Key: upk_你的API Key" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(body)}'`,
    MATLAB: `opts = weboptions('MediaType','application/json', ...
    'HeaderFields', {'X-API-Key','upk_你的API Key'}, 'Timeout', 60);
data = struct('records', {{ jsondecode('${firstRec.replace(/'/g, "''")}') }});
result = webwrite('${url}', data, opts);
disp(result.predictions)`,
    JavaScript: `const res = await fetch("${url}", {
  method: "POST",
  headers: { "X-API-Key": "upk_你的API Key", "Content-Type": "application/json" },
  body: JSON.stringify(${json.replace(/\n/g, '\n  ')})
})
const result = await res.json()
console.log(result.predictions)`
  }
})

async function doCreate() {
  if (!create.name) return ElMessage.warning('请填写用途说明')
  const res = await http.post('/keys', { name: create.name, rate_limit_per_min: auth.isAdmin ? create.rate : null })
  create.result = res.api_key
  keys.value = await http.get('/keys')
}

async function toggle(row, v) {
  await http.patch(`/keys/${row.id}`, { is_active: v })
  row.is_active = v ? 1 : 0
}

async function remove(row) {
  await http.delete(`/keys/${row.id}`)
  keys.value = await http.get('/keys')
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch (e) {
    ElMessage.warning('浏览器不允许自动复制，请手动选中复制')
  }
}
</script>
