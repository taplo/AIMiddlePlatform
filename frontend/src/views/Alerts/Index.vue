<template>
  <div>
    <h2 style="margin-bottom:16px">告警列表</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
      <el-select v-model="store.typeFilter" placeholder="告警类型" clearable style="width:160px" @change="store.load()">
        <el-option label="人物检测" value="person_detected" />
        <el-option label="车辆检测" value="vehicle_detected" />
        <el-option label="质量异常" value="quality_rejected" />
      </el-select>
      <el-select v-model="store.statusFilter" placeholder="状态" clearable style="width:120px" @change="store.load()">
        <el-option label="待处理" value="pending" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已忽略" value="ignored" />
      </el-select>
      <el-button @click="store.load()" :loading="store.loading">刷新</el-button>
    </div>
    <el-table :data="store.items" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="camera_id" label="摄像头" width="120" />
      <el-table-column prop="alert_type" label="类型" width="140" />
      <el-table-column prop="label" label="标签" width="120" />
      <el-table-column prop="confidence" label="置信度" width="90">
        <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column prop="verified_by" label="验证方" width="80" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'confirmed' ? 'success' : row.status === 'pending' ? 'warning' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="task_id" label="Task ID" width="200">
        <template #default="{ row }">
          <span style="font-family:monospace;font-size:12px">{{ row.task_id.substring(0, 16) }}...</span>
        </template>
      </el-table-column>
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
import { useAlertStore } from '@/stores/alerts'

const store = useAlertStore()
onMounted(() => store.load())
</script>
