<template>
  <div v-if="job" class="job">
    <div class="flex-between">
      <div class="flex">
        <el-tag :type="JOB_STATUS[job.status]?.type">{{ JOB_STATUS[job.status]?.label }}</el-tag>
        <span class="muted">任务 #{{ job.id }}</span>
        <span v-if="job.status === 'queued' && job.queue_position" class="muted">· 前面还有 {{ job.queue_position - 1 }} 个任务</span>
      </div>
      <el-button v-if="['queued', 'running'].includes(job.status)" size="small" @click="cancel">取消任务</el-button>
    </div>
    <el-progress class="mt" :percentage="Math.round((job.progress || 0) * 100)"
                 :status="job.status === 'succeeded' ? 'success' : job.status === 'failed' ? 'exception' : ''" :stroke-width="10" />
    <div class="msg">{{ job.message }}</div>
    <el-collapse v-if="job.log && job.log.length" class="mt">
      <el-collapse-item title="运行日志">
        <pre class="code-block" style="max-height: 240px; overflow: auto">{{ job.log.join('\n') }}</pre>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import http from '../api/http'
import { JOB_STATUS } from '../utils'

const props = defineProps({ jobId: { type: Number, required: true } })
const emit = defineEmits(['done', 'update'])
const job = ref(null)
let timer = null
let stopped = false

async function poll() {
  try {
    job.value = await http.get(`/jobs/${props.jobId}`, { silent: true })
    emit('update', job.value)
    if (['succeeded', 'failed', 'cancelled'].includes(job.value.status)) {
      emit('done', job.value)
      return
    }
  } catch (e) { /* 网络抖动时继续轮询 */ }
  if (!stopped) timer = setTimeout(poll, 1200)
}

async function cancel() {
  await http.post(`/jobs/${props.jobId}/cancel`)
}

watch(() => props.jobId, () => {
  clearTimeout(timer)
  job.value = null
  poll()
}, { immediate: true })

onBeforeUnmount(() => {
  stopped = true
  clearTimeout(timer)
})
</script>

<style scoped>
.msg { margin-top: 8px; color: var(--text-2); font-size: 13px; }
</style>
