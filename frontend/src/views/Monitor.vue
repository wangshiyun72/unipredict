<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">运行监控</h2>
        <p class="page-desc">实时查看预测服务的并发、排队、限流与 GPU 使用情况（每 2 秒刷新）。运行 <span class="mono">scripts/benchmark.py</span> 压测时可在这里观察并发控制效果。</p>
      </div>
      <el-switch v-model="live" active-text="实时刷新" />
    </div>

    <div class="grid grid-4">
      <div class="card stat">
        <span class="label">正在执行的预测</span>
        <span class="value">{{ gate.active ?? 0 }}<small class="muted"> / {{ gate.limit ?? '-' }}</small></span>
        <span class="hint">排队 {{ gate.waiting ?? 0 }} · 峰值 {{ gate.peak_active ?? 0 }}</span>
      </div>
      <div class="card stat">
        <span class="label">预测延迟 P50 / P95</span>
        <span class="value">{{ fmt(gate.latency_p50_ms, 1) }}<small class="muted"> / {{ fmt(gate.latency_p95_ms, 1) }} ms</small></span>
        <span class="hint">最近 500 次请求，累计完成 {{ gate.completed ?? 0 }}</span>
      </div>
      <div class="card stat">
        <span class="label">限流拦截（429）</span>
        <span class="value">{{ sys.rate_limiter?.rejected ?? 0 }}</span>
        <span class="hint">放行 {{ sys.rate_limiter?.allowed ?? 0 }} 次</span>
      </div>
      <div class="card stat">
        <span class="label">并发闸门拒绝（503）</span>
        <span class="value">{{ gate.rejected ?? 0 }}</span>
        <span class="hint">排队超过 {{ sys.config?.predict_queue_timeout }} 秒即拒绝</span>
      </div>
    </div>

    <div class="grid grid-3 mt">
      <div class="card" style="grid-column: span 2">
        <div class="card-title">实时并发曲线 <span class="sub">本页打开期间采样</span></div>
        <EChart :option="liveOption" height="280px" />
      </div>
      <div class="card">
        <div class="card-title">并发控制配置</div>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="预测并发上限">{{ sys.config?.predict_concurrency }}</el-descriptions-item>
          <el-descriptions-item label="排队超时">{{ sys.config?.predict_queue_timeout }} 秒</el-descriptions-item>
          <el-descriptions-item label="GPU 并发上限">{{ sys.config?.gpu_concurrency }}（当前占用 {{ sys.gpu?.gpu_active ?? 0 }}，等待 {{ sys.gpu?.gpu_waiting ?? 0 }}）</el-descriptions-item>
          <el-descriptions-item label="网页用户限额">{{ sys.config?.rate_limit_user_per_min }} 次/分钟</el-descriptions-item>
          <el-descriptions-item label="API Key 默认限额">{{ sys.config?.rate_limit_key_per_min }} 次/分钟</el-descriptions-item>
          <el-descriptions-item label="训练线程 / 每人任务上限">{{ sys.jobs?.workers }} / {{ sys.jobs?.max_jobs_per_user }}</el-descriptions-item>
          <el-descriptions-item label="单次预测最大行数">{{ sys.config?.max_predict_rows }}</el-descriptions-item>
          <el-descriptions-item label="模型缓存">{{ sys.model_cache?.loaded?.length }} / {{ sys.model_cache?.size }}（命中 {{ sys.model_cache?.hits }}，加载 {{ sys.model_cache?.misses }}）</el-descriptions-item>
          <el-descriptions-item label="计算设备">{{ sys.gpu?.device === 'cuda' ? `GPU：${sys.gpu.gpu_name}` : 'CPU' }}
            <span v-if="sys.gpu?.memory_total_mb">（显存 {{ sys.gpu.memory_used_mb }} / {{ sys.gpu.memory_total_mb }} MB）</span></el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="card mt">
      <div class="card-title">最近调用记录</div>
      <el-table :data="calls" size="small" max-height="400">
        <el-table-column prop="created_at" label="时间" width="165" />
        <el-table-column prop="username" label="用户" width="110" />
        <el-table-column label="来源" width="80"><template #default="{ row }"><el-tag size="small" :type="row.source === 'api' ? 'warning' : ''">{{ row.source === 'api' ? 'API' : '网页' }}</el-tag></template></el-table-column>
        <el-table-column prop="model_name" label="模型" min-width="200" show-overflow-tooltip />
        <el-table-column prop="n_rows" label="样本数" width="80" />
        <el-table-column label="耗时" width="100"><template #default="{ row }">{{ fmt(row.latency_ms, 1) }} ms</template></el-table-column>
        <el-table-column label="状态" width="80"><template #default="{ row }"><el-tag size="small" :type="row.status_code === 200 ? 'success' : 'danger'">{{ row.status_code }}</el-tag></template></el-table-column>
        <el-table-column prop="error" label="错误信息" min-width="160" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import http from '../api/http'
import EChart from '../components/EChart.vue'
import { fmt } from '../utils'

const sys = ref({})
const calls = ref([])
const live = ref(true)
const samples = ref([])
const gate = computed(() => sys.value.predict_gate || {})
let timer = null
let tick = 0

async function poll() {
  try {
    sys.value = await http.get('/stats/system', { silent: true })
    const now = new Date()
    samples.value.push({
      t: `${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`,
      active: gate.value.active || 0,
      waiting: gate.value.waiting || 0,
      p95: gate.value.latency_p95_ms || 0
    })
    if (samples.value.length > 90) samples.value.shift()
    if (tick++ % 3 === 0) calls.value = await http.get('/stats/calls', { params: { limit: 50 }, silent: true })
  } catch (e) { /* ignore */ }
  if (live.value) timer = setTimeout(poll, 2000)
}

onMounted(poll)
watch(live, (v) => { clearTimeout(timer); if (v) poll() })
onBeforeUnmount(() => { live.value = false; clearTimeout(timer) })

const liveOption = computed(() => ({
  grid: { left: 10, right: 20, top: 30, bottom: 10, containLabel: true },
  tooltip: { trigger: 'axis' },
  legend: { data: ['执行中', '排队中', 'P95 延迟 (ms)'] },
  xAxis: { type: 'category', data: samples.value.map((s) => s.t) },
  yAxis: [
    { type: 'value', name: '请求数', minInterval: 1, splitLine: { lineStyle: { type: 'dashed' } } },
    { type: 'value', name: 'ms', splitLine: { show: false } }
  ],
  series: [
    { name: '执行中', type: 'line', step: 'end', data: samples.value.map((s) => s.active), areaStyle: { opacity: 0.15 }, itemStyle: { color: '#0f766e' }, showSymbol: false },
    { name: '排队中', type: 'line', step: 'end', data: samples.value.map((s) => s.waiting), itemStyle: { color: '#f59e0b' }, showSymbol: false },
    { name: 'P95 延迟 (ms)', type: 'line', yAxisIndex: 1, data: samples.value.map((s) => s.p95), itemStyle: { color: '#ef4444' }, lineStyle: { type: 'dashed' }, showSymbol: false }
  ]
}))
</script>
