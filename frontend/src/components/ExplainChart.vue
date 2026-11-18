<template>
  <div>
    <div class="muted" style="font-size: 12px; margin-bottom: 6px">
      {{ explanation.score_meaning }}：<b>{{ fmt(explanation.score) }}</b>。
      条形表示把该特征换成训练集典型值（中位数/众数）后，{{ explanation.score_meaning }}的变化：
      <span style="color: #dc2626">红色 = 推高</span>，<span style="color: #2563eb">蓝色 = 拉低</span>。
      取值恰好等于典型值的特征，贡献为 0。
    </div>
    <EChart :option="option" :height="Math.max(160, items.length * 28 + 40) + 'px'" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { fmt } from '../utils'

const props = defineProps({ explanation: { type: Object, required: true }, top: { type: Number, default: 12 } })
const items = computed(() => (props.explanation.contributions || []).slice(0, props.top).reverse())
const option = computed(() => ({
  grid: { left: 10, right: 50, top: 10, bottom: 10, containLabel: true },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (ps) => {
      const c = items.value[ps[0].dataIndex]
      return `${c.feature}<br/>当前值：${fmt(c.value)}<br/>典型值：${fmt(c.baseline)}<br/>贡献：${fmt(c.contribution)}`
    }
  },
  xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
  yAxis: {
    type: 'category',
    data: items.value.map((c) => `${c.feature} = ${fmt(c.value, 3)}`),
    axisLabel: { width: 180, overflow: 'truncate' }
  },
  series: [{
    type: 'bar',
    data: items.value.map((c) => ({
      value: c.contribution,
      itemStyle: { color: c.contribution >= 0 ? '#ef4444' : '#3b82f6', borderRadius: 3 }
    })),
    label: { show: true, position: 'right', formatter: (p) => fmt(p.value, 3), fontSize: 11 }
  }]
}))
</script>
