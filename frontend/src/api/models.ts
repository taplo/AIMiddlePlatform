import client from './client'

export interface ModelSpec {
  model_id: string
  name: string
  version: string
  status: string
  backend: string
  description: string
  tags: string[]
  cost_estimate: string
}

export interface ModelStats {
  model_id: string
  requests_total: number
  status: string
  latency: { avg_ms: number; p50: number; p95: number; p99: number }
}

export async function fetchModels() {
  const res = await client.get<ModelSpec[]>('/api/v1/models/')
  return res.data
}

export async function fetchActiveModels() {
  const res = await client.get<ModelSpec[]>('/api/v1/models/active')
  return res.data
}

export async function updateModelStatus(modelId: string, status: string) {
  const res = await client.post(`/api/v1/models/${modelId}/status`, { version: '', status })
  return res.data
}

export async function fetchModelStats(modelId: string) {
  const res = await client.get<ModelStats>(`/api/v1/models/${modelId}/stats`)
  return res.data
}
