import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchModels, type ModelSpec } from '@/api/models'

export const useModelStore = defineStore('models', () => {
  const list = ref<ModelSpec[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      list.value = await fetchModels()
    } finally {
      loading.value = false
    }
  }

  return { list, loading, load }
})
