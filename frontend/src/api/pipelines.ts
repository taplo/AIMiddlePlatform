import client from './client'

export interface PipelineNode {
  node_id: string
  node_type: string
  config: Record<string, any>
  depends_on: string[]
}

export interface PipelineDAG {
  name: string
  nodes: Record<string, PipelineNode>
  entry_nodes: string[]
  output_node: string
}

export interface PipelineCreateBody {
  nodes: { node_id: string; node_type: string; config: Record<string, any>; depends_on: string[] }[]
  entry_nodes: string[]
  output_node: string
}

export interface PipelineSummary {
  name: string
  node_count: number
  entry_nodes: string[]
  output_node: string
}

export async function fetchPipelines() {
  const res = await client.get<{ pipelines: PipelineSummary[] }>('/api/v1/pipelines')
  return res.data.pipelines
}

export async function fetchPipelineDAG(name: string) {
  const res = await client.get<PipelineDAG>(`/api/v1/pipelines/${name}`)
  return res.data
}

export async function createPipeline(name: string, dag: PipelineCreateBody) {
  const res = await client.post('/api/v1/pipelines', { name, ...dag })
  return res.data
}

export async function updatePipeline(name: string, dag: PipelineCreateBody) {
  const res = await client.put(`/api/v1/pipelines/${name}`, dag)
  return res.data
}

export async function deletePipeline(name: string) {
  const res = await client.delete(`/api/v1/pipelines/${name}`)
  return res.data
}
