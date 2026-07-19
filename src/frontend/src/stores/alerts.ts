import { defineStore } from "pinia"
import { ref } from "vue"
import { listAlerts, listChannels, updateChannel } from "../api/alerts"
import type { AlertItem, NotificationChannel } from "../api/alerts"

export const useAlertStore = defineStore("alerts", () => {
  const alerts = ref<AlertItem[]>([])
  const total = ref(0)
  const loading = ref(false)

  const channels = ref<NotificationChannel[]>([])
  const channelsLoading = ref(false)

  async function fetchAlerts(status?: string, alertType?: string, page = 1, pageSize = 50) {
    loading.value = true
    try {
      const res = await listAlerts(status, alertType, page, pageSize)
      alerts.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function fetchChannels() {
    channelsLoading.value = true
    try {
      channels.value = await listChannels()
    } finally {
      channelsLoading.value = false
    }
  }

  async function toggleChannel(name: string, enabled: boolean, config: Record<string, any>) {
    await updateChannel(name, enabled, config)
    const c = channels.value.find((ch) => ch.name === name)
    if (c) c.enabled = enabled
  }

  async function saveChannel(name: string, enabled: boolean, config: Record<string, any>) {
    channels.value = await updateChannel(name, enabled, config)
  }

  return { alerts, total, loading, channels, channelsLoading, fetchAlerts, fetchChannels, toggleChannel, saveChannel }
})
