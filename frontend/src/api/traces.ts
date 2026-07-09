import client from './client'

export interface TraceSummary {
  trace_id: string
  start_time: number
  duration_ms: number
  span_count: number
  error: boolean
}

export interface SpanData {
  span_id: string
  name: string
  start_time: number
  duration_ms: number
  attributes: Record<string, any>
  error: boolean
}

export interface TraceDetail {
  trace_id: string
  duration_ms: number
  span_count: number
  error: boolean
  spans: SpanData[]
}

export async function fetchTraces(params: {
  min_duration_ms?: number
  error_only?: boolean
  limit?: number
}) {
  const res = await client.get<{ traces: TraceSummary[] }>('/api/v1/traces', { params })
  return res.data.traces
}

export async function fetchTraceDetail(traceId: string) {
  const res = await client.get<TraceDetail>(`/api/v1/traces/${traceId}`)
  return res.data
}
