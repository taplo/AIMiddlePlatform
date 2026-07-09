<template>
  <div>
    <el-button text @click="$router.push('/traces')">&lt; 返回列表</el-button>
    <div v-if="store.detail" v-loading="store.loading" style="margin-top:12px">
      <el-card>
        <template #header>
          <span>Trace: <code style="font-size:13px">{{ store.detail.trace_id }}</code></span>
          <el-tag :type="store.detail.error ? 'danger' : 'success'" size="small" style="margin-left:12px">
            {{ store.detail.error ? '异常' : '正常' }}
          </el-tag>
        </template>
        <div>总耗时: <strong>{{ store.detail.duration_ms.toFixed(2) }} ms</strong></div>
        <div>Span 数量: <strong>{{ store.detail.span_count }}</strong></div>
      </el-card>

      <h3 style="margin:16px 0 8px">Span 详情</h3>
      <el-table :data="store.detail.spans" stripe style="width:100%">
        <el-table-column prop="span_id" label="Span ID" width="200">
          <template #default="{ row }"><code>{{ row.span_id.substring(0, 12) }}...</code></template>
        </el-table-column>
        <el-table-column prop="name" label="操作" width="200" />
        <el-table-column label="耗时" width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px">
              <div :style="{ width: (row.duration_ms / store.detail!.duration_ms * 200) + 'px', height:'16px', background: row.error ? '#f56c6c' : '#409eff', borderRadius:'3px', minWidth:'4px' }"></div>
              <span>{{ row.duration_ms.toFixed(2) }}ms</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.error ? 'danger' : 'success'" size="small">{{ row.error ? 'ERR' : 'OK' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTraceStore } from '@/stores/traces'

const route = useRoute()
const store = useTraceStore()

onMounted(async () => {
  await store.loadDetail(route.params.traceId as string)
})
</script>
