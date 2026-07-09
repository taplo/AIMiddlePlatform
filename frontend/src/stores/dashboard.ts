import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchStats, type DashboardStats } from '@/api/dashboard'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      stats.value = await fetchStats()
    } finally {
      loading.value = false
    }
  }

  return { stats, loading, load }
})
