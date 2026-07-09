<template>
  <el-dialog v-model="visible" :title="`${modelId} 统计`" width="500px">
    <div v-if="stats">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="请求总数">{{ stats.requests_total }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ stats.status }}</el-descriptions-item>
        <el-descriptions-item label="平均延迟">{{ stats.latency.avg_ms }}ms</el-descriptions-item>
        <el-descriptions-item label="P50">{{ stats.latency.p50 }}ms</el-descriptions-item>
        <el-descriptions-item label="P95">{{ stats.latency.p95 }}ms</el-descriptions-item>
        <el-descriptions-item label="P99">{{ stats.latency.p99 }}ms</el-descriptions-item>
      </el-descriptions>
    </div>
    <el-skeleton :rows="4" animated v-else />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { fetchModelStats, type ModelStats } from '@/api/models'

const visible = ref(false)
const modelId = ref('')
const stats = ref<ModelStats | null>(null)

async function open(id: string) {
  modelId.value = id
  visible.value = true
  stats.value = null
  try {
    stats.value = await fetchModelStats(id)
  } catch { /* stats unavailable */ }
}

defineExpose({ open })
</script>
