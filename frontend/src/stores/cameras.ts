import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCameras, type Camera } from '@/api/cameras'

export const useCameraStore = defineStore('cameras', () => {
  const list = ref<Camera[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      list.value = await fetchCameras()
    } finally {
      loading.value = false
    }
  }

  return { list, loading, load }
})
