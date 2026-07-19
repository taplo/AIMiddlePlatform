<template>
  <div>
    <h2>Alerts</h2>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="Alert History" name="history">
        <div style="margin-bottom: 12px; display: flex; gap: 8px">
          <el-select v-model="filterStatus" placeholder="Status" clearable style="width: 140px" @change="refreshAlerts">
            <el-option label="Pending" value="pending" />
            <el-option label="Verified" value="verified" />
            <el-option label="Dismissed" value="dismissed" />
          </el-select>
          <el-select v-model="filterType" placeholder="Type" clearable style="width: 160px" @change="refreshAlerts">
            <el-option label="Object Detection" value="object_detection" />
            <el-option label="Face" value="face" />
            <el-option label="Motion" value="motion" />
            <el-option label="Anomaly" value="anomaly" />
          </el-select>
        </div>

        <el-table :data="store.alerts" v-loading="store.loading" stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="alert_type" label="Type" width="140" />
          <el-table-column prop="label" label="Label" min-width="160" show-overflow-tooltip />
          <el-table-column prop="confidence" label="Confidence" width="100">
            <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
          </el-table-column>
          <el-table-column prop="camera_id" label="Camera" width="140" />
          <el-table-column label="Status" width="110">
            <template #default="{ row }">
              <el-tag :type="row.status === 'pending' ? 'warning' : row.status === 'verified' ? 'success' : 'info'" size="small">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="Time" width="180" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="Notification Channels" name="channels">
        <el-table :data="store.channels" v-loading="store.channelsLoading" stripe>
          <el-table-column prop="name" label="Channel" width="160" />
          <el-table-column prop="type" label="Type" width="120" />
          <el-table-column label="Enabled" width="90">
            <template #default="{ row }">
              <el-switch :modelValue="row.enabled" @change="handleToggle(row)" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="Webhook URL" min-width="300">
            <template #default="{ row }">
              <el-input v-model="row.config.webhook_url" size="small" placeholder="https://..." @change="handleSave(row)" />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useAlertStore } from "../../stores/alerts"
import type { NotificationChannel } from "../../api/alerts"

const store = useAlertStore()
const activeTab = ref("history")
const filterStatus = ref("")
const filterType = ref("")

onMounted(() => {
  store.fetchAlerts()
  store.fetchChannels()
})

function refreshAlerts() {
  store.fetchAlerts(filterStatus.value || undefined, filterType.value || undefined)
}

async function handleToggle(row: NotificationChannel) {
  await store.toggleChannel(row.name, !row.enabled, row.config)
}

async function handleSave(row: NotificationChannel) {
  await store.saveChannel(row.name, row.enabled, row.config)
}
</script>
