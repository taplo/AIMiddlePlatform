import client from "./client"

export interface SystemStats {
  total_streams: number
  active_tasks: number
  connected: number
  total_frames_kept: number
  requests_total: number
  latency_p99_ms: number
  fast_path_pct: number
  agent_path_pct: number
  gpu_util_pct: number
  gpu_memory_pct: number
  streams: any[]
}

export interface StatsHistory {
  timestamps: string[]
  qps: number[]
  p50: number[]
  p95: number[]
  p99: number[]
  error_rate: number[]
}

export async function getStats(): Promise<SystemStats> {
  const { data } = await client.get<SystemStats>("/system/stats")
  return data
}

export async function getStatsHistory(range = "5m"): Promise<StatsHistory> {
  const { data } = await client.get<StatsHistory>("/system/stats/history", {
    params: { range },
  })
  return data
}
