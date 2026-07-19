import client from "./client"

export interface AlertItem {
  id: number
  task_id: string
  camera_id: string | null
  alert_type: string
  label: string
  bbox: string | null
  confidence: number
  verified_by: string | null
  status: string
  created_at: string | null
}

export interface AlertPage {
  total: number
  page: number
  page_size: number
  items: AlertItem[]
}

export interface NotificationChannel {
  name: string
  type: string
  enabled: boolean
  config: {
    webhook_url: string
  }
}

export async function listAlerts(
  status?: string,
  alertType?: string,
  page = 1,
  pageSize = 50,
): Promise<AlertPage> {
  const params: any = { page, page_size: pageSize }
  if (status) params.status = status
  if (alertType) params.alert_type = alertType
  const { data } = await client.get<AlertPage>("/alerts", { params })
  return data
}

export async function listChannels(): Promise<NotificationChannel[]> {
  const { data } = await client.get<NotificationChannel[]>("/admin/notifications")
  return data
}

export async function updateChannel(name: string, enabled: boolean, config: Record<string, any>): Promise<NotificationChannel[]> {
  const { data } = await client.put<NotificationChannel[]>(`/admin/notifications/${name}`, { enabled, config })
  return data
}
