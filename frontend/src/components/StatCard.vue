<template>
  <el-card shadow="hover" class="stat-card">
    <div class="label">{{ label }}</div>
    <div class="value" :style="{ color }">{{ value }}</div>
    <div v-if="unit" class="unit">{{ unit }}</div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{ label: string; value: string | number; color?: string; unit?: string }>()
</script>

<style scoped>
.stat-card { text-align:center; min-width:160px; }
.label { font-size:13px; color:#909399; margin-bottom:8px; }
.value { font-size:28px; font-weight:700; }
.unit { font-size:12px; color:#909399; margin-top:4px; }
</style>
