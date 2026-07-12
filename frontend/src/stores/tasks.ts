import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTasks, type TaskItem } from '@/api/tasks'

export const useTaskStore = defineStore('tasks', () => {
  const items = ref<TaskItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const statusFilter = ref('')
  const cameraFilter = ref('')
  const currentPage = ref(1)
  const pageSize = ref(20)

  async function load() {
    loading.value = true
    try {
      const params: any = { page: currentPage.value, page_size: pageSize.value }
      if (statusFilter.value) params.status = statusFilter.value
      if (cameraFilter.value) params.camera_id = cameraFilter.value
      const data = await fetchTasks(params)
      items.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  return { items, total, loading, statusFilter, cameraFilter, currentPage, pageSize, load }
})
