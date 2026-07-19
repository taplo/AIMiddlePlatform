<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2>Models</h2>
      <el-button type="primary" @click="showRegister = true">Register Model</el-button>
    </div>

    <el-table :data="store.models" v-loading="store.loading" stripe>
      <el-table-column prop="model_id" label="ID" width="180" />
      <el-table-column prop="name" label="Name" width="180" />
      <el-table-column prop="version" label="Version" width="100" />
      <el-table-column prop="backend" label="Backend" width="100" />
      <el-table-column prop="cost_estimate" label="Cost" width="90" />
      <el-table-column label="Status" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'online' ? 'success' : row.status === 'offline' ? 'danger' : 'warning'" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Latency" width="120">
        <template #default="{ row }">
          <span v-if="store.stats[row.model_id]">{{ store.stats[row.model_id].latency.avg_ms }}ms</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="Actions" min-width="160">
        <template #default="{ row }">
          <el-button size="small" @click="refreshStats(row.model_id)">Stats</el-button>
          <el-button
            size="small"
            :type="row.status === 'online' ? 'warning' : 'success'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'online' ? 'Offline' : 'Online' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showRegister" title="Register Model" width="500px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="Model ID" required>
          <el-input v-model="form.model_id" />
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Version">
          <el-input v-model="form.version" placeholder="1.0.0" />
        </el-form-item>
        <el-form-item label="Backend">
          <el-select v-model="form.backend">
            <el-option label="ONNX" value="onnx" />
            <el-option label="OpenVINO" value="openvino" />
            <el-option label="TensorRT" value="tensorrt" />
          </el-select>
        </el-form-item>
        <el-form-item label="Cost">
          <el-select v-model="form.cost_estimate">
            <el-option label="Low" value="low" />
            <el-option label="Medium" value="medium" />
            <el-option label="High" value="high" />
          </el-select>
        </el-form-item>
        <el-form-item label="Tags">
          <el-input v-model="form.tags" placeholder="comma separated" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRegister = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="handleRegister">Register</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useModelStore } from "../../stores/models"
import { registerModel } from "../../api/models"

const store = useModelStore()
const showRegister = ref(false)
const saving = ref(false)
const form = ref({
  model_id: "",
  name: "",
  version: "1.0.0",
  backend: "onnx",
  cost_estimate: "medium",
  tags: "",
  description: "",
})

onMounted(() => {
  store.fetchModels()
})

async function refreshStats(modelId: string) {
  await store.fetchStats(modelId)
}

async function toggleStatus(row: any) {
  const newStatus = row.status === "online" ? "offline" : "online"
  await store.toggleStatus(row.model_id, row.version, newStatus)
}

async function handleRegister() {
  saving.value = true
  try {
    const tags = form.value.tags
      ? form.value.tags.split(",").map((t: string) => t.trim()).filter(Boolean)
      : []
    await registerModel({
      model_id: form.value.model_id,
      name: form.value.name || form.value.model_id,
      version: form.value.version,
      backend: form.value.backend,
      cost_estimate: form.value.cost_estimate,
      tags,
      description: form.value.description,
    })
    showRegister.value = false
    form.value = { model_id: "", name: "", version: "1.0.0", backend: "onnx", cost_estimate: "medium", tags: "", description: "" }
    await store.fetchModels()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.text-muted { color: #999; }
</style>
