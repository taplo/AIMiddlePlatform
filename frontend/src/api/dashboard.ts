import client from './client'

export interface DashboardStats {
  qps: number
  cameras: { total: number; online: number; offline: number }
  models: { total: number; active: number }
  latency: { p50: number; p95: number; p99: number; avg_ms: number }
  requests_total: number
}

export async function fetchStats() {
  const res = await client.get<DashboardStats>('/api/v1/system/stats')
  return res.data
}
