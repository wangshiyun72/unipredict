<template>
  <div>
    <div class="grid grid-2">
      <div>
        <div v-if="result.summary?.hist" class="muted mb" style="font-size: 12px">
          预测值统计：均值 {{ fmt(result.summary.mean) }}，标准差 {{ fmt(result.summary.std) }}，
          范围 {{ fmt(result.summary.min) }} ~ {{ fmt(result.summary.max) }}
        </div>
        <EChart v-if="result.summary?.hist" :option="histOption" height="260px" />
        <EChart v-else-if="result.summary?.class_counts" :option="pieOption" height="260px" />
      </div>
      <div>
        <template v-if="result.evaluation">
          <div class="muted mb" style="font-size: 12px">数据中包含真实值「{{ result.target }}」，自动对比评估：</div>
          <div class="flex" style="flex-wrap: wrap; gap: 10px">
            <el-tag v-for="m in metricEntries(result.evaluation)" :key="m.key" size="large" effect="plain">{{ m.label }}：{{ fmt(m.value) }}</el-tag>
          </div>
          <EChart v-if="result.scatter" class="mt" :option="scatterOption" height="220px" />
        </template>
        <div v-else class="muted" style="font-size: 13px; line-height: 1.8">
          左图为本批数据的预测结果分布。下方表格显示前 200 行，完整结果请点击右上角下载。
        </div>
      </div>
    </div>
    <el-table :data="result.rows" size="small" max-height="360" class="mt" border>
      <el-table-column v-for="c in result.columns" :key="c" :prop="c" :label="c" min-width="110"
                       :fixed="c.startsWith('预测_') ? 'right' : false" :class-name="c.startsWith('预测_') ? 'pred-col' : ''">
        <template #default="{ row }">{{ fmt(row[c]) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { fmt, metricEntries } from '../utils'

const props = defineProps({ result: { type: Object, required: true } })

const histOption = computed(() => {
  const h = props.result.summary.hist
  return {
    grid: { left: 40, right: 24, top: 16, bottom: 40, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: h.bins.map((b) => fmt(b, 2)), name: `预测${props.result.target}`, nameLocation: 'middle', nameGap: 28 },
    yAxis: { type: 'value', name: '样本数', nameLocation: 'middle', nameGap: 36, minInterval: 1 },
    series: [{ type: 'bar', data: h.counts, itemStyle: { color: '#0f766e' }, barWidth: '90%' }]
  }
})

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    data: Object.entries(props.result.summary.class_counts).map(([name, value]) => ({ name, value })),
    label: { formatter: '{b}: {c} ({d}%)' }
  }]
}))

const scatterOption = computed(() => {
  const pts = props.result.scatter || []
  const all = pts.flat()
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  return {
    grid: { left: 40, right: 24, top: 16, bottom: 40, containLabel: true },
    xAxis: { type: 'value', min: lo, max: hi, name: '真实值', nameLocation: 'middle', nameGap: 28, axisLabel: { formatter: (v) => fmt(v, 2) } },
    yAxis: { type: 'value', min: lo, max: hi, name: '预测值', nameLocation: 'middle', nameGap: 48, axisLabel: { formatter: (v) => fmt(v, 2) } },
    series: [
      { type: 'scatter', data: pts, symbolSize: 5, itemStyle: { color: '#0f766e', opacity: 0.6 } },
      { type: 'line', data: [[lo, lo], [hi, hi]], showSymbol: false, lineStyle: { type: 'dashed', color: '#ef4444' } }
    ]
  }
})
</script>

<style scoped>
:deep(.pred-col) { background: #f0fdfa !important; font-weight: 600; }
</style>
