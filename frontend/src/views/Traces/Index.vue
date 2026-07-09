<template>
  <div>
    <h2 style="margin-bottom:16px">链路追踪</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px">
      <el-checkbox v-model="store.errorOnly" label="仅显示错误" @change="store.load()" />
      <el-input v-model.number="store.minDuration" placeholder="最小耗时 (ms)" style="width:160px" clearable @change="store.load()" />
      <el-button @click="store.load()" :loading="store.loading">刷新</el-button>
    </div>
    <el-table :data="store.traces" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="trace_id" label="Trace ID" width="280">
        <template #default="{ row }">
          <router-link :to="`/traces/${row.trace_id}`" style="font-family:monospace;font-size:13px">{{ row.trace_id.substring(0, 16) }}...</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时 (ms)" width="120">
        <template #default="{ row }">{{ row.duration_ms.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="span_count" label="Span 数" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.error ? 'danger' : 'success'" size="small">{{ row.error ? '异常' : '正常' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTraceStore } from '@/stores/traces'

const store = useTraceStore()
onMounted(() => store.load())
</script>
