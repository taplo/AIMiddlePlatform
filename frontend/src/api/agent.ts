import client from './client'

export interface LLMConfig {
  provider: string
  url: string
  api_key: string
  model_name: string
}

export interface AgentConfig {
  llm: LLMConfig
  system_prompt: string
  thresholds: Record<string, number>
  routing_rules: { scene_id: string; pipeline: string }[]
}

export interface ProviderInfo {
  id: string
  name: string
  default_url: string
}

export async function fetchAgentConfig() {
  const res = await client.get<AgentConfig>('/api/v1/agent/config')
  return res.data
}

export async function fetchProviders() {
  const res = await client.get<ProviderInfo[]>('/api/v1/agent/providers')
  return res.data
}

export async function saveAgentConfig(config: AgentConfig) {
  const res = await client.post('/api/v1/agent/config', config)
  return res.data
}
