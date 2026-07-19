<template>
  <div>
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6"><StatCard label="Cameras" :value="stats?.connected ?? '-'" sub="online" /></el-col>
      <el-col :span="6"><StatCard label="Total" :value="stats?.total_streams ?? '-'" sub="registered" /></el-col>
      <el-col :span="6"><StatCard label="Frames Kept" :value="stats?.total_frames_kept ?? '-'" sub="lifetime" /></el-col>
      <el-col :span="6"><StatCard label="Active Tasks" :value="stats?.active_tasks ?? '-'" sub="running" /></el-col>
    </el-row>
    <el-card>
      <LineChart
        title="System Metrics (last 5 min)"
        :xData="history?.timestamps ?? []"
        :series="chartSeries"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import StatCard from "../components/StatCard.vue"
import LineChart from "../components/LineChart.vue"
import { getStats, getStatsHistory } from "../api/dashboard"
import type { SystemStats, StatsHistory } from "../api/dashboard"

const stats = ref<SystemStats | null>(null)
const history = ref<StatsHistory | null>(null)

const chartSeries = computed(() => {
  if (!history.value) return []
  return [
    { name: "QPS", data: history.value.qps, color: "#409eff" },
    { name: "P50", data: history.value.p50, color: "#67c23a" },
    { name: "P95", data: history.value.p95, color: "#e6a23c" },
    { name: "P99", data: history.value.p99, color: "#f56c6c" },
  ]
})

let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  stats.value = await getStats()
  history.value = await getStatsHistory()
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
