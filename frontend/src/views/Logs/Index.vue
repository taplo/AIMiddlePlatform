<template>
  <div>
    <h2 style="margin-bottom:16px">日志查询</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">
      <el-select v-model="store.level" clearable placeholder="日志级别" style="width:140px" @change="store.load()">
        <el-option label="DEBUG" value="DEBUG" />
        <el-option label="INFO" value="INFO" />
        <el-option label="WARNING" value="WARNING" />
        <el-option label="ERROR" value="ERROR" />
      </el-select>
      <el-input v-model="store.module" placeholder="模块名" style="width:200px" clearable @change="store.load()" />
      <el-input v-model="store.search" placeholder="搜索关键词" style="width:240px" clearable @change="store.load()" />
      <el-button @click="store.load()" :loading="store.loading">查询</el-button>
      <el-button @click="store.clear()">清空日志</el-button>
    </div>
    <el-table :data="store.logs" v-loading="store.loading" stripe style="width:100%" max-height="700px" size="small">
      <el-table-column prop="timestamp" label="时间" width="180" />
      <el-table-column prop="level" label="级别" width="90">
        <template #default="{ row }">
          <el-tag :type="levelType(row.level)" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="logger" label="Logger" width="200" />
      <el-table-column prop="message" label="消息" min-width="300" show-overflow-tooltip />
    </el-table>
    <div style="margin-top:8px;color:#909399;font-size:13px">共 {{ store.total }} 条日志</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useLogStore } from '@/stores/logs'

const store = useLogStore()
onMounted(() => store.load())

function levelType(level: string) {
  if (level === 'ERROR') return 'danger'
  if (level === 'WARNING') return 'warning'
  if (level === 'DEBUG') return 'info'
  return ''
}
</script>
