import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchAgentConfig, saveAgentConfig, fetchProviders, type AgentConfig, type ProviderInfo } from '@/api/agent'

export const useAgentStore = defineStore('agent', () => {
  const config = ref<AgentConfig | null>(null)
  const providers = ref<ProviderInfo[]>([])
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      const [cfg, prov] = await Promise.all([fetchAgentConfig(), fetchProviders()])
      config.value = cfg
      providers.value = prov
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

  return { config, providers, loading, saving, load, save }
})
