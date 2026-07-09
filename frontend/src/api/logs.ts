import client from './client'

export interface LogEntry {
  timestamp: string
  level: string
  logger: string
  message: string
  module: string
  func: string
  line: number
}

export interface LogQueryResult {
  logs: LogEntry[]
  total: number
}

export async function queryLogs(params: {
  level?: string
  module?: string
  q?: string
  limit?: number
  offset?: number
}) {
  const res = await client.get<LogQueryResult>('/api/v1/logs', { params })
  return res.data
}

export async function clearLogs() {
  await client.delete('/api/v1/logs')
}
