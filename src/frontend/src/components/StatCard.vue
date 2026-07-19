<template>
  <el-card shadow="hover">
    <div class="stat-card">
      <div class="stat-label">{{ label }}</div>
      <div class="stat-value">{{ value }}</div>
      <div v-if="sub" class="stat-sub">{{ sub }}</div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  sub?: string
}>()
</script>

<style scoped>
.stat-card { text-align: center; padding: 4px 0; }
.stat-label { font-size: 13px; color: #909399; margin-bottom: 4px; }
.stat-value { font-size: 28px; font-weight: 700; }
.stat-sub { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
