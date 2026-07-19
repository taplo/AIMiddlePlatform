import client from "./client"

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
  latency: {
    avg_ms: number
    p50: number
    p95: number
    p99: number
  }
}

export interface RegisterRequest {
  model_id: string
  name: string
  version: string
  backend?: string
  description?: string
  tags?: string[]
  cost_estimate?: string
}

export async function listModels(status?: string): Promise<ModelSpec[]> {
  const params = status ? { status } : undefined
  const { data } = await client.get<ModelSpec[]>("/models/", { params })
  return data
}

export async function getModel(modelId: string): Promise<ModelSpec> {
  const { data } = await client.get<ModelSpec>(`/models/${modelId}`)
  return data
}

export async function getModelStats(modelId: string): Promise<ModelStats> {
  const { data } = await client.get<ModelStats>(`/models/${modelId}/stats`)
  return data
}

export async function registerModel(req: RegisterRequest): Promise<ModelSpec> {
  const { data } = await client.post<ModelSpec>("/models/", req)
  return data
}

export async function updateModelStatus(modelId: string, version: string, status: string): Promise<void> {
  await client.post(`/models/${modelId}/status`, { version, status })
}
