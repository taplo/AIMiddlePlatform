import client from './client'

export interface AlertItem {
  id: number
  task_id: string
  camera_id: string | null
  alert_type: string
  label: string
  bbox: string | null
  confidence: number
  verified_by: string
  status: string
  created_at: string | null
}

export interface AlertListResponse {
  total: number
  page: number
  page_size: number
  items: AlertItem[]
}

export async function fetchAlerts(params: {
  status?: string
  alert_type?: string
  task_id?: string
  page?: number
  page_size?: number
}) {
  const res = await client.get<AlertListResponse>('/api/v1/alerts', { params })
  return res.data
}

export async function fetchAlertDetail(alertId: number) {
  const res = await client.get<AlertItem>(`/api/v1/alerts/${alertId}`)
  return res.data
}
