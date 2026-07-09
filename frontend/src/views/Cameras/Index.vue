<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <h2>视频源管理</h2>
      <el-button type="primary" @click="dialogRef?.open()">添加摄像头</el-button>
    </div>
    <el-table :data="store.list" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="camera_id" label="摄像头 ID" width="200" />
      <el-table-column prop="stream_url" label="流地址" min-width="300" show-overflow-tooltip />
      <el-table-column prop="protocol" label="协议" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="FPS" width="80">
        <template #default="{ row }">{{ row.config?.fps || '-' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ row.created_at || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <FormDialog ref="dialogRef" @created="store.load()" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCameraStore } from '@/stores/cameras'
import StatusBadge from '@/components/StatusBadge.vue'
import FormDialog from './FormDialog.vue'

const store = useCameraStore()
const dialogRef = ref<InstanceType<typeof FormDialog>>()

onMounted(() => store.load())

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除摄像头 ${row.camera_id}?`)
  ElMessage.success('删除成功')
  store.load()
}
</script>
