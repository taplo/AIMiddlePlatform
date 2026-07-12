<template>
  <div>
    <h2 style="margin-bottom:16px">任务列表</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
      <el-select v-model="store.statusFilter" placeholder="状态" clearable style="width:140px" @change="store.load()">
        <el-option label="已完成" value="completed" />
        <el-option label="已拒绝" value="rejected" />
        <el-option label="已跳过" value="skipped" />
        <el-option label="队列中" value="queued" />
      </el-select>
      <el-input v-model="store.cameraFilter" placeholder="摄像头 ID" style="width:160px" clearable @change="store.load()" />
      <el-button @click="store.load()" :loading="store.loading">刷新</el-button>
    </div>
    <el-table :data="store.items" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="task_id" label="Task ID" width="280">
        <template #default="{ row }">
          <span style="font-family:monospace;font-size:13px">{{ row.task_id.substring(0, 16) }}...</span>
        </template>
      </el-table-column>
      <el-table-column prop="camera_id" label="摄像头" width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="path_taken" label="路径" width="80" />
      <el-table-column prop="latency_ms" label="耗时 (ms)" width="100">
        <template #default="{ row }">{{ row.latency_ms ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="alert_count" label="告警" width="60" />
      <el-table-column prop="rejection_reason" label="拒绝原因" min-width="140" />
      <el-table-column prop="created_at" label="时间" width="170" />
    </el-table>
    <div style="display:flex;justify-content:center;margin-top:16px">
      <el-pagination
        v-model:current-page="store.currentPage"
        :page-size="store.pageSize"
        :total="store.total"
        layout="prev, pager, next"
        @current-change="store.load()"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTaskStore } from '@/stores/tasks'

const store = useTaskStore()
onMounted(() => store.load())

function statusType(s: string): string {
  if (s === 'completed') return 'success'
  if (s === 'rejected') return 'danger'
  if (s === 'skipped') return 'warning'
  return 'info'
}

function statusLabel(s: string): string {
  if (s === 'completed') return '完成'
  if (s === 'rejected') return '拒绝'
  if (s === 'skipped') return '跳过'
  return s
}
</script>
