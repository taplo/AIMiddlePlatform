import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryLogs, clearLogs, type LogEntry } from '@/api/logs'

export const useLogStore = defineStore('logs', () => {
  const logs = ref<LogEntry[]>([])
  const total = ref(0)
  const loading = ref(false)
  const level = ref('')
  const module = ref('')
  const search = ref('')

  async function load() {
    loading.value = true
    try {
      const result = await queryLogs({
        level: level.value || undefined,
        module: module.value || undefined,
        q: search.value || undefined,
        limit: 200,
      })
      logs.value = result.logs
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function clear() {
    await clearLogs()
    await load()
  }

  return { logs, total, loading, level, module, search, load, clear }
})
