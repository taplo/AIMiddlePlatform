import { defineStore } from "pinia"
import { ref } from "vue"
import { listModels, getModelStats, updateModelStatus } from "../api/models"
import type { ModelSpec, ModelStats } from "../api/models"

export const useModelStore = defineStore("models", () => {
  const models = ref<ModelSpec[]>([])
  const loading = ref(false)
  const stats = ref<Record<string, ModelStats>>({})

  async function fetchModels(status?: string) {
    loading.value = true
    try {
      models.value = await listModels(status)
    } finally {
      loading.value = false
    }
  }

  async function fetchStats(modelId: string) {
    try {
      stats.value[modelId] = await getModelStats(modelId)
    } catch {
      // stats may not be available
    }
  }

  async function toggleStatus(modelId: string, version: string, status: string) {
    await updateModelStatus(modelId, version, status)
    const m = models.value.find((x) => x.model_id === modelId && x.version === version)
    if (m) m.status = status
  }

  return { models, loading, stats, fetchModels, fetchStats, toggleStatus }
})
