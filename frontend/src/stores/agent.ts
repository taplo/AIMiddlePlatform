import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchAgentConfig, saveAgentConfig, type AgentConfig } from '@/api/agent'

export const useAgentStore = defineStore('agent', () => {
  const config = ref<AgentConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      config.value = await fetchAgentConfig()
    } finally {
      loading.value = false
    }
  }

  async function save(data: AgentConfig) {
    saving.value = true
    try {
      await saveAgentConfig(data)
      config.value = data
    } finally {
      saving.value = false
    }
  }

  return { config, loading, saving, load, save }
})
