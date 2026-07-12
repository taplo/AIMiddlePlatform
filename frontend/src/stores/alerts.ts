import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchAlerts, type AlertItem } from '@/api/alerts'

export const useAlertStore = defineStore('alerts', () => {
  const items = ref<AlertItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const typeFilter = ref('')
  const statusFilter = ref('')
  const currentPage = ref(1)
  const pageSize = ref(20)

  async function load() {
    loading.value = true
    try {
      const params: any = { page: currentPage.value, page_size: pageSize.value }
      if (typeFilter.value) params.alert_type = typeFilter.value
      if (statusFilter.value) params.status = statusFilter.value
      const data = await fetchAlerts(params)
      items.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  return { items, total, loading, typeFilter, statusFilter, currentPage, pageSize, load }
})
