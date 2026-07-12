import client from './client'

export interface TaskItem {
  task_id: string
  camera_id: string
  status: string
  path_taken: string
  latency_ms: number | null
  error_msg: string | null
  rejection_reason: string | null
  alert_count: number
  created_at: string | null
}

export interface TaskListResponse {
  total: number
  page: number
  page_size: number
  items: TaskItem[]
}

export interface TaskResult {
  task_id: string
  status: string
  camera_id: string
  path_taken: string
  result: any
  latency_ms: number | null
  error: string | null
  rejection_reason: string | null
  alert_count: number
  created_at: string | null
}

export async function fetchTasks(params: {
  status?: string
  camera_id?: string
  page?: number
  page_size?: number
}) {
  const res = await client.get<TaskListResponse>('/api/v1/tasks', { params })
  return res.data
}

export async function fetchTaskResult(taskId: string) {
  const res = await client.get<TaskResult>(`/api/v1/tasks/${taskId}/results`)
  return res.data
}
