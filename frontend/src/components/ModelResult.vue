<template>
  <div>
    <!-- 指标 -->
    <div class="grid grid-4">
      <div v-for="m in metricEntries(model.metrics)" :key="m.key" class="card stat" :class="{ primary: m.primary }">
        <span class="label">{{ m.label }}<el-tag v-if="m.primary" size="small" style="margin-left: 6px">主指标</el-tag></span>
        <span class="value">{{ fmt(m.value) }}</span>
      </div>
      <div v-if="!metricEntries(model.metrics).length" class="card muted">外部接入模型没有平台内评估指标</div>
    </div>

    <!-- 排行榜 -->
    <div v-if="leaderboard.length" class="card mt">
      <div class="card-title">模型排行榜 <span class="sub">同一数据、同一测试集上的对比（{{ model.metrics?.primary_label }}，越高越好）</span></div>
      <div class="grid grid-2">
        <EChart :option="leaderOption" :height="Math.max(180, leaderboard.length * 36 + 40) + 'px'" />
        <el-table :data="leaderboard" size="small">
          <el-table-column label="模型" min-width="160">
            <template #default="{ row }">
              <div class="flex">
                <el-tag size="small" :class="FAMILY[row.family]?.cls">{{ FAMILY[row.family]?.label }}</el-tag>
                <router-link v-if="row.model_id" :to="`/models/${row.model_id}`">{{ row.name }}</router-link>
                <span v-else>{{ row.name }}</span>
                <el-icon v-if="row.is_best" color="#f59e0b"><Trophy /></el-icon>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="model.metrics?.primary_label || '主指标'" width="110">
            <template #default="{ row }">
              <span v-if="row.status === 'succeeded'">{{ fmt(row.metrics?.primary_value) }}</span>
              <el-tooltip v-else :content="row.error"><el-tag type="danger" size="small">失败</el-tag></el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="训练耗时" width="90">
            <template #default="{ row }">{{ row.train_seconds ? row.train_seconds + ' s' : '-' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="grid grid-2 mt">
      <!-- 回归：预测 vs 真实 -->
      <div v-if="charts.scatter" class="card">
        <div class="card-title">预测值 vs 真实值 <span class="sub">测试集，越靠近对角线越准</span></div>
        <EChart :option="scatterOption" height="320px" />
      </div>
      <div v-if="charts.residual_hist" class="card">
        <div class="card-title">残差分布 <span class="sub">预测值 − 真实值</span></div>
        <EChart :option="residOption" height="320px" />
      </div>
      <!-- 分类：混淆矩阵 -->
      <div v-if="charts.confusion_matrix" class="card">
        <div class="card-title">混淆矩阵 <span class="sub">行 = 真实类别，列 = 预测类别</span></div>
        <EChart :option="cmOption" height="320px" />
      </div>
      <!-- 特征重要性 -->
      <div v-if="importance.length" class="card">
        <div class="card-title">全局特征重要性 <span class="sub">置换重要性：打乱该特征后指标下降多少</span></div>
        <EChart :option="impOption" :height="Math.max(220, importance.length * 26 + 40) + 'px'" />
      </div>
      <!-- 训练曲线 -->
      <div v-if="history && history.train_loss && history.train_loss.length" class="card">
        <div class="card-title">训练曲线 <span class="sub">深度学习模型的训练/验证损失（早停）</span></div>
        <EChart :option="historyOption" height="320px" />
      </div>
    </div>

    <!-- 自动归一化报告 -->
    <div v-if="prep" class="card mt">
      <div class="card-title">自动预处理与归一化报告</div>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="缩放方式">{{ prep.scaler_name }}</el-descriptions-item>
        <el-descriptions-item label="选择依据" :span="2">{{ prep.scaler_reason }}</el-descriptions-item>
        <el-descriptions-item label="输出特征维度">{{ prep.n_features_out }}</el-descriptions-item>
        <el-descriptions-item label="自动剔除的列" :span="2">
          <span v-if="!Object.keys(prep.dropped_columns || {}).length" class="muted">无</span>
          <div v-for="(why, col) in prep.dropped_columns" :key="col"><b>{{ col }}</b>：{{ why }}</div>
        </el-descriptions-item>
      </el-descriptions>
      <el-table :data="prep.report" size="small" class="mt" max-height="320">
        <el-table-column prop="column" label="字段" min-width="140" />
        <el-table-column prop="method" label="处理方式" min-width="160" />
        <el-table-column label="缺失填充" width="110">
          <template #default="{ row }">{{ row.missing_filled ? `${row.missing_filled} 个 → ${fmt(row.fill_value ?? '众数')}` : '无缺失' }}</template>
        </el-table-column>
        <el-table-column label="原始均值" width="110"><template #default="{ row }">{{ fmt(row.before_mean) }}</template></el-table-column>
        <el-table-column label="原始标准差" width="110"><template #default="{ row }">{{ fmt(row.before_std) }}</template></el-table-column>
        <el-table-column label="原始范围" min-width="150">
          <template #default="{ row }">{{ row.categories ? `${row.categories} 个类别` : `${fmt(row.before_min)} ~ ${fmt(row.before_max)}` }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { FAMILY, fmt, metricEntries } from '../utils'

const props = defineProps({ model: { type: Object, required: true } })
const detail = computed(() => props.model.detail || {})
const charts = computed(() => detail.value.charts || {})
const importance = computed(() => (detail.value.importance || []).slice(0, 20))
const prep = computed(() => detail.value.preprocessing)
const history = computed(() => detail.value.history)
const leaderboard = computed(() => props.model.leaderboard || [])

const leaderOption = computed(() => {
  const rows = leaderboard.value.filter((r) => r.status === 'succeeded').slice().reverse()
  return {
    grid: { left: 10, right: 50, top: 10, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name), axisLabel: { width: 150, overflow: 'truncate' } },
    series: [{
      type: 'bar',
      data: rows.map((r) => ({ value: r.metrics?.primary_value, itemStyle: { color: r.is_best ? '#0f766e' : '#94a3b8', borderRadius: 3 } })),
      label: { show: true, position: 'right', formatter: (p) => fmt(p.value, 3) }
    }]
  }
})

const scatterOption = computed(() => {
  const pts = charts.value.scatter || []
  const all = pts.flat().filter((v) => v !== null)
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const target = props.model.target || ''
  return {
    grid: { left: 40, right: 24, top: 16, bottom: 40, containLabel: true },
    tooltip: { formatter: (p) => (p.seriesType === 'scatter' ? `真实：${fmt(p.value[0])}<br/>预测：${fmt(p.value[1])}` : '') },
    xAxis: { name: `真实${target}`, nameLocation: 'middle', nameGap: 28, type: 'value', min: lo, max: hi, axisLabel: { formatter: (v) => fmt(v, 2) }, splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: { name: `预测${target}`, nameLocation: 'middle', nameGap: 48, type: 'value', min: lo, max: hi, axisLabel: { formatter: (v) => fmt(v, 2) }, splitLine: { lineStyle: { type: 'dashed' } } },
    series: [
      { type: 'scatter', data: pts, symbolSize: 6, itemStyle: { color: '#0f766e', opacity: 0.65 } },
      { type: 'line', data: [[lo, lo], [hi, hi]], showSymbol: false, lineStyle: { type: 'dashed', color: '#ef4444' }, silent: true }
    ]
  }
})

const residOption = computed(() => {
  const h = charts.value.residual_hist || { bins: [], counts: [] }
  return {
    grid: { left: 40, right: 24, top: 16, bottom: 40, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: h.bins.map((b) => fmt(b, 2)), name: '残差（预测值 − 真实值）', nameLocation: 'middle', nameGap: 28 },
    yAxis: { type: 'value', name: '样本数', nameLocation: 'middle', nameGap: 36, minInterval: 1 },
    series: [{ type: 'bar', data: h.counts, itemStyle: { color: '#64748b' }, barWidth: '90%' }]
  }
})

const cmOption = computed(() => {
  const cm = charts.value.confusion_matrix || { labels: [], matrix: [] }
  const data = []
  let max = 1
  cm.matrix.forEach((row, i) => row.forEach((v, j) => { data.push([j, i, v]); max = Math.max(max, v) }))
  return {
    grid: { left: 10, right: 20, top: 10, bottom: 40, containLabel: true },
    tooltip: { formatter: (p) => `真实：${cm.labels[p.value[1]]}<br/>预测：${cm.labels[p.value[0]]}<br/>数量：${p.value[2]}` },
    xAxis: { type: 'category', data: cm.labels, name: '预测', splitArea: { show: true } },
    yAxis: { type: 'category', data: cm.labels, name: '真实', inverse: true, splitArea: { show: true } },
    visualMap: { min: 0, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, itemHeight: 120, inRange: { color: ['#f0fdfa', '#0f766e'] } },
    series: [{ type: 'heatmap', data, label: { show: true } }]
  }
})

const impOption = computed(() => {
  const rows = importance.value.slice().reverse()
  return {
    grid: { left: 10, right: 50, top: 10, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps) => `${ps[0].name}<br/>重要性：${fmt(ps[0].value)}` },
    xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.feature), axisLabel: { width: 140, overflow: 'truncate' } },
    series: [{
      type: 'bar',
      data: rows.map((r) => r.importance),
      itemStyle: { color: '#0f766e', borderRadius: 3 },
      label: { show: true, position: 'right', formatter: (p) => fmt(p.value, 3), fontSize: 11 }
    }]
  }
})

const historyOption = computed(() => {
  const h = history.value || {}
  const n = (h.train_loss || []).length
  return {
    grid: { left: 10, right: 20, top: 30, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { data: ['训练损失', '验证损失'] },
    xAxis: { type: 'category', data: Array.from({ length: n }, (_, i) => i + 1), name: 'Epoch' },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { type: 'dashed' } } },
    series: [
      { name: '训练损失', type: 'line', data: h.train_loss, showSymbol: false, lineStyle: { color: '#0f766e' }, itemStyle: { color: '#0f766e' } },
      { name: '验证损失', type: 'line', data: h.val_loss, showSymbol: false, lineStyle: { color: '#f59e0b' }, itemStyle: { color: '#f59e0b' } }
    ]
  }
})
</script>

<style scoped>
.stat.primary { border-color: #0f766e; background: #f0fdfa; }
</style>
