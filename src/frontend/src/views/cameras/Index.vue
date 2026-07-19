<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; justify-content: space-between">
      <h2>Camera Management</h2>
      <el-button type="primary" @click="showCreate = true">+ Add Camera</el-button>
    </div>
    <el-table :data="store.cameras" v-loading="store.loading" stripe style="width: 100%">
      <el-table-column prop="camera_id" label="ID" width="180" />
      <el-table-column label="Status" width="100">
        <template #default="{ row }">
          <StatusBadge :status="row.connected ? 'connected' : 'error'" />
        </template>
      </el-table-column>
      <el-table-column prop="protocol" label="Protocol" width="90" />
      <el-table-column prop="fps_output" label="FPS" width="80">
        <template #default="{ row }">{{ row.fps_output?.toFixed(1) }}</template>
      </el-table-column>
      <el-table-column prop="frames_kept" label="Kept" width="80" />
      <el-table-column prop="reconnects" label="Reconnects" width="100" />
      <el-table-column prop="uptime_seconds" label="Uptime" width="90">
        <template #default="{ row }">{{ Math.floor(row.uptime_seconds) }}s</template>
      </el-table-column>
      <el-table-column prop="last_error" label="Last Error" min-width="200" show-overflow-tooltip />
      <el-table-column label="Actions" width="100">
        <template #default="{ row }">
          <el-button type="danger" size="small" @click="handleDelete(row.camera_id)">Delete</el-button>
        </template>
      </el-table-column>
    </el-table>

    <FormDialog v-model:visible="showCreate" @done="store.fetchCameras()" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { ElMessageBox } from "element-plus"
import { useCameraStore } from "../../stores/cameras"
import StatusBadge from "../../components/StatusBadge.vue"
import FormDialog from "./FormDialog.vue"

const store = useCameraStore()
const showCreate = ref(false)

onMounted(() => store.fetchCameras())

async function handleDelete(cameraId: string) {
  try {
    await ElMessageBox.confirm(`Delete camera "${cameraId}"?`, "Confirm", { type: "warning" })
    await store.removeCamera(cameraId)
  } catch {}
}
</script>
