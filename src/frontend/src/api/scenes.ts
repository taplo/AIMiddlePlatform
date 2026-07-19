import client from "./client"

export interface PipelineSummary {
  name: string
  node_count: number
  entry_nodes: string[]
  output_node: string
}

export interface PipelineDAG {
  name: string
  nodes: Record<string, { node_id: string; node_type: string; config: any; depends_on: string[] }>
  entry_nodes: string[]
  output_node: string
}

export interface DAGNodeInput {
  node_id: string
  node_type: string
  config?: Record<string, any>
  depends_on?: string[]
}

export interface Rule {
  id: number
  name: string
  rule_type: string
  config: string
  severity: string
  enabled: boolean
  description: string
  created_at: string | null
  updated_at: string | null
}

export interface RulePage {
  total: number
  page: number
  page_size: number
  items: Rule[]
}

export async function listPipelines(): Promise<PipelineSummary[]> {
  const { data } = await client.get<{ pipelines: PipelineSummary[] }>("/pipelines")
  return data.pipelines
}

export async function getPipeline(name: string): Promise<PipelineDAG> {
  const { data } = await client.get<PipelineDAG>(`/pipelines/${name}`)
  return data
}

export async function createPipeline(name: string, nodes: DAGNodeInput[], entryNodes: string[], outputNode: string): Promise<void> {
  await client.post("/pipelines", { name, nodes, entry_nodes: entryNodes, output_node: outputNode })
}

export async function updatePipeline(name: string, nodes: DAGNodeInput[], entryNodes: string[], outputNode: string): Promise<void> {
  await client.put(`/pipelines/${name}`, { nodes, entry_nodes: entryNodes, output_node: outputNode })
}

export async function deletePipeline(name: string): Promise<void> {
  await client.delete(`/pipelines/${name}`)
}

export async function listRules(ruleType?: string, enabled?: boolean, page = 1, pageSize = 50): Promise<RulePage> {
  const params: any = { page, page_size: pageSize }
  if (ruleType) params.rule_type = ruleType
  if (enabled !== undefined) params.enabled = enabled
  const { data } = await client.get<RulePage>("/admin/rules", { params })
  return data
}

export async function getRule(id: number): Promise<Rule> {
  const { data } = await client.get<Rule>(`/admin/rules/${id}`)
  return data
}

export async function createRule(req: { name: string; rule_type: string; config: string; severity?: string; enabled?: boolean; description?: string }): Promise<Rule> {
  const { data } = await client.post<Rule>("/admin/rules", req)
  return data
}

export async function updateRule(id: number, req: Partial<{ name: string; rule_type: string; config: string; severity: string; enabled: boolean; description: string }>): Promise<Rule> {
  const { data } = await client.put<Rule>(`/admin/rules/${id}`, req)
  return data
}

export async function deleteRule(id: number): Promise<void> {
  await client.delete(`/admin/rules/${id}`)
}
