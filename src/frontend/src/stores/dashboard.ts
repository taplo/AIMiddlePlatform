import { defineStore } from "pinia"
import { ref } from "vue"
import { getStats } from "../api/dashboard"
import type { SystemStats } from "../api/dashboard"

export const useDashboardStore = defineStore("dashboard", () => {
  const stats = ref<SystemStats | null>(null)
  const loading = ref(false)

  async function fetchStats() {
    loading.value = true
    try {
      stats.value = await getStats()
    } finally {
      loading.value = false
    }
  }

  return { stats, loading, fetchStats }
})
