<template>
  <div ref="el" :style="{ width: '100%', height }" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '300px' }
})
const el = ref(null)
let chart = null
let ro = null

function render() {
  if (!chart) return
  chart.setOption({ textStyle: { fontFamily: 'PingFang SC, Microsoft YaHei, sans-serif' }, ...props.option }, true)
}

onMounted(async () => {
  await nextTick()
  chart = echarts.init(el.value)
  render()
  ro = new ResizeObserver(() => chart && chart.resize())
  ro.observe(el.value)
})
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => {
  ro && ro.disconnect()
  chart && chart.dispose()
  chart = null
})
</script>
