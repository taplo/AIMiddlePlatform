import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchStats, fetchStatsHistory, type DashboardStats, type StatsHistory } from '@/api/dashboard'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const history = ref<StatsHistory | null>(null)
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      stats.value = await fetchStats()
    } finally {
      loading.value = false
    }
  }

  async function loadHistory() {
    try {
      history.value = await fetchStatsHistory()
    } catch {
      history.value = null
    }
  }

  return { stats, history, loading, load, loadHistory }
})
