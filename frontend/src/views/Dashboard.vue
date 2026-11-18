<template>
  <div class="page">
    <div class="hero">
      <div>
        <div class="hero-hello">你好，{{ auth.user?.display_name || auth.user?.username }}</div>
        <h2 class="hero-title">基于服务器端通用模型的可访问式深度学习预测服务</h2>
        <p class="hero-desc">上传数据 → 自动归一化 → 通用模型与轻量模型并行训练 → 一键发布 → 网页或 REST API 随时预测</p>
        <div class="flex flex-wrap" style="margin-top: 18px">
          <el-button type="primary" size="large" @click="$router.push('/quick')"><el-icon><MagicStick /></el-icon>&nbsp;一键预测</el-button>
          <el-button size="large" @click="$router.push('/templates')"><el-icon><Collection /></el-icon>&nbsp;从数据模板开始</el-button>
          <el-button size="large" text class="hero-link" @click="$router.push('/predict')">使用已发布模型 →</el-button>
        </div>
      </div>
      <div class="hero-device">
        <div class="device-row"><span>计算设备</span><b>{{ sys.gpu?.device === 'cuda' ? 'GPU' : 'CPU' }}</b></div>
        <div v-if="sys.gpu?.gpu_name" class="device-row"><span>显卡</span><b>{{ sys.gpu.gpu_name.replace('NVIDIA GeForce ', '') }}</b></div>
        <div v-if="sys.gpu?.memory_total_mb" class="device-row"><span>显存</span><b>{{ sys.gpu.memory_used_mb }} / {{ sys.gpu.memory_total_mb }} MB</b></div>
        <div class="device-row"><span>训练任务</span><b>运行 {{ sys.jobs?.running ?? 0 }} · 排队 {{ sys.jobs?.queued ?? 0 }}</b></div>
        <div class="device-row"><span>预测并发</span><b>{{ sys.predict_gate?.active ?? 0 }} / {{ sys.predict_gate?.limit ?? '-' }}</b></div>
      </div>
    </div>

    <div class="grid grid-4 mt">
      <div class="card stat"><span class="stat-icon"><el-icon><Files /></el-icon></span>
        <span class="label">数据集</span><span class="value">{{ ov.datasets ?? '-' }}</span><span class="hint">含团队共享与公开数据</span></div>
      <div class="card stat"><span class="stat-icon"><el-icon><Box /></el-icon></span>
        <span class="label">模型 / 已发布</span><span class="value">{{ ov.models ?? '-' }}<small class="muted"> / {{ ov.published_models ?? '-' }}</small></span><span class="hint">已发布模型可被 API 调用</span></div>
      <div class="card stat"><span class="stat-icon"><el-icon><Aim /></el-icon></span>
        <span class="label">累计预测调用</span><span class="value">{{ ov.totals?.calls ?? 0 }}</span><span class="hint">共 {{ ov.totals?.rows ?? 0 }} 条样本</span></div>
      <div class="card stat"><span class="stat-icon"><el-icon><Timer /></el-icon></span>
        <span class="label">平均响应时间</span><span class="value">{{ fmt(ov.totals?.avg_latency, 1) }}<small class="muted"> ms</small></span><span class="hint">服务端处理耗时</span></div>
    </div>

    <div class="grid grid-3 mt">
      <div class="card span-2">
        <div class="card-title">近 14 天预测调用 <span class="sub">网页调用 vs 外部 API 调用</span></div>
        <EChart :option="trendOption" height="280px" />
      </div>
      <div class="card">
        <div class="card-title">调用最多的模型</div>
        <el-empty v-if="!(ov.top_models || []).length" description="暂无调用记录" :image-size="80" />
        <div v-for="(m, i) in ov.top_models || []" :key="m.id" class="top-row">
          <span class="rank" :class="{ gold: i === 0 }">{{ i + 1 }}</span>
          <router-link :to="`/models/${m.id}`" class="top-name">{{ m.name }}</router-link>
          <span class="muted">{{ m.calls }} 次</span>
        </div>
      </div>
    </div>

    <div class="card mt">
      <div class="card-title">使用流程</div>
      <div class="flow">
        <div v-for="(s, i) in flow" :key="s.title" class="flow-step card-hover" @click="$router.push(s.to)">
          <div class="flow-num">{{ i + 1 }}</div>
          <div class="flow-body">
            <div class="flow-title"><el-icon><component :is="s.icon" /></el-icon> {{ s.title }}</div>
            <div class="muted flow-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import http from '../api/http'
import EChart from '../components/EChart.vue'
import { auth } from '../store'
import { fmt } from '../utils'

const ov = ref({})
const sys = ref({})
const flow = [
  { title: '准备数据', desc: '按「数据模板」整理表格，或直接上传 CSV / Excel', icon: 'Collection', to: '/templates' },
  { title: '一键训练', desc: '自动识别字段与归一化，并行训练通用模型与轻量模型，选出最优', icon: 'Cpu', to: '/quick' },
  { title: '查看结果', desc: '评估指标、预测 vs 真实、特征重要性、单样本解释', icon: 'DataAnalysis', to: '/models' },
  { title: '对外服务', desc: '发布模型、创建 API Key，任意终端通过 REST API 调用', icon: 'Connection', to: '/api' }
]

onMounted(async () => {
  ;[ov.value, sys.value] = await Promise.all([http.get('/stats/overview'), http.get('/stats/system')])
})

const trendOption = computed(() => {
  const days = []
  for (let i = 13; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000)
    days.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  }
  const pick = (src) => days.map((d) => (ov.value.trend || []).filter((t) => t.day === d && t.source === src).reduce((s, t) => s + t.calls, 0))
  return {
    grid: { left: 10, right: 20, top: 36, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { data: ['网页调用', 'API 调用'], top: 0 },
    xAxis: { type: 'category', data: days.map((d) => d.slice(5)) },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { type: 'dashed' } } },
    series: [
      { name: '网页调用', type: 'bar', stack: 'a', data: pick('web'), itemStyle: { color: '#0f766e' }, barMaxWidth: 28 },
      { name: 'API 调用', type: 'bar', stack: 'a', data: pick('api'), itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] }, barMaxWidth: 28 }
    ]
  }
})
</script>

<style scoped>
.hero {
  display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  padding: 28px 32px; border-radius: 16px; color: #e6f2f1;
  background: radial-gradient(circle at 85% 10%, rgba(45, 212, 191, 0.25), transparent 40%), linear-gradient(135deg, #0b1f24 0%, #134e4a 100%);
}
.hero-hello { color: #8fd3cb; font-size: 13px; }
.hero-title { color: #fff; font-size: 24px; margin: 6px 0 8px; font-weight: 650; }
.hero-desc { color: #a7c7c3; margin: 0; font-size: 13.5px; }
.hero-link { color: #99f6e4 !important; }
.hero-device {
  min-width: 260px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px; padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; align-self: center;
}
.device-row { display: flex; justify-content: space-between; gap: 16px; font-size: 13px; }
.device-row span { color: #8fb3b0; }
.device-row b { color: #fff; font-weight: 600; }
.top-row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px dashed var(--border); }
.top-row:last-child { border-bottom: none; }
.rank { width: 22px; height: 22px; border-radius: 6px; background: #f1f5f9; color: #475569; font-size: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.rank.gold { background: #fef3c7; color: #b45309; }
.top-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
@media (max-width: 1000px) { .flow { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.flow-step { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; cursor: pointer; background: #fbfcfd; }
.flow-num { width: 28px; height: 28px; border-radius: 50%; background: #0f766e; color: #fff; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.flow-title { font-weight: 600; display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.flow-desc { font-size: 12.5px; line-height: 1.6; }
</style>
