import client from './client'

export interface AgentConfig {
  llm: { provider: string; url: string; api_key: string }
  system_prompt: string
  thresholds: Record<string, number>
  routing_rules: { scene_id: string; pipeline: string }[]
}

export async function fetchAgentConfig() {
  const res = await client.get<AgentConfig>('/api/v1/agent/config')
  return res.data
}

export async function saveAgentConfig(config: AgentConfig) {
  const res = await client.post('/api/v1/agent/config', config)
  return res.data
}
