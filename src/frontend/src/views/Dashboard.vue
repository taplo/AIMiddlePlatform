<template>
  <div>
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6"><StatCard label="Cameras Online" :value="stats?.connected ?? '-'" sub="connected" /></el-col>
      <el-col :span="6"><StatCard label="Total Requests" :value="stats?.requests_total ?? '-'" sub="lifetime" /></el-col>
      <el-col :span="6"><StatCard label="P99 Latency" :value="stats ? stats.latency_p99_ms + 'ms' : '-'" sub="last 5 min" /></el-col>
      <el-col :span="6"><StatCard label="Active Tasks" :value="stats?.active_tasks ?? '-'" sub="running" /></el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="8">
        <el-card>
          <template #header>Path Distribution</template>
          <div v-if="stats" style="display: flex; gap: 16px; align-items: center">
            <el-progress type="circle" :percentage="stats.fast_path_pct" color="#67c23a" :width="80">
              <span>Fast {{ stats.fast_path_pct }}%</span>
            </el-progress>
            <el-progress type="circle" :percentage="stats.agent_path_pct" color="#e6a23c" :width="80">
              <span>Agent {{ stats.agent_path_pct }}%</span>
            </el-progress>
          </div>
          <div v-else class="text-muted">No data</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>GPU Usage</template>
          <div v-if="stats" style="display: flex; gap: 16px; align-items: center">
            <el-progress type="circle" :percentage="stats.gpu_util_pct" :width="80" :status="stats.gpu_util_pct > 80 ? 'exception' : 'success'" />
            <el-progress type="circle" :percentage="stats.gpu_memory_pct" :width="80" :status="stats.gpu_memory_pct > 80 ? 'exception' : 'success'" />
          </div>
          <div v-else class="text-muted">No data (GPU metrics require nvidia-smi)</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Streams</template>
          <div style="text-align: center; padding: 12px 0">
            <div style="font-size: 32px; font-weight: 700; color: #409eff">{{ stats?.connected ?? 0 }} / {{ stats?.total_streams ?? 0 }}</div>
            <div class="text-muted" style="font-size: 13px">online / registered</div>
          </div>
        </el-card>
      </el-col>
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
  const s: { name: string; data: number[]; color: string }[] = [
    { name: "QPS", data: history.value.qps, color: "#409eff" },
    { name: "P50 Latency (ms)", data: history.value.p50, color: "#67c23a" },
    { name: "P95 Latency (ms)", data: history.value.p95, color: "#e6a23c" },
    { name: "P99 Latency (ms)", data: history.value.p99, color: "#f56c6c" },
  ]
  if (history.value.error_rate?.some((v) => v > 0)) {
    s.push({ name: "Error Rate", data: history.value.error_rate, color: "#909399" })
  }
  return s
})

let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  try {
    stats.value = await getStats()
    history.value = await getStatsHistory()
  } catch {
    // ignore
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.text-muted { color: #999; font-size: 13px; }
</style>
