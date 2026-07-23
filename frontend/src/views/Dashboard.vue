<template>
  <div>
    <h2 style="margin-bottom:16px">系统总览</h2>
    <div class="cards" v-if="dash.stats">
      <StatCard label="实时 QPS" :value="dash.stats.qps" color="#409eff" />
      <StatCard label="摄像头在线" :value="`${dash.stats.cameras.online} / ${dash.stats.cameras.total}`" color="#67c23a" />
      <StatCard label="活跃模型" :value="`${dash.stats.models.active} / ${dash.stats.models.total}`" color="#e6a23c" />
      <StatCard label="平均延迟" :value="`${dash.stats.latency.avg_ms}ms`" color="#f56c6c" />
    </div>
    <el-skeleton :rows="4" animated v-else />
    <el-row :gutter="16" style="margin-top:20px">
      <el-col :span="12"><LineChart title="请求量 (最近 60s)" :data="qpsHistory" /></el-col>
      <el-col :span="12"><LineChart title="延迟 (最近 60s)" :data="latencyHistory" color="#67c23a" /></el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import StatCard from '@/components/StatCard.vue'
import LineChart from '@/components/LineChart.vue'

const dash = useDashboardStore()

onMounted(async () => {
  await Promise.all([dash.load(), dash.loadHistory()])
})

const qpsHistory = computed(() => dash.history?.qps ?? [])
const latencyHistory = computed(() => dash.history?.p50 ?? [])
</script>

<style scoped>
.cards { display:flex; gap:16px; flex-wrap:wrap; }
</style>
