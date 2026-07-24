import client from './client'

export interface Camera {
  task_id: string
  camera_id: string
  stream_url: string
  protocol: string
  status: string
  config: { fps: number; roi?: string }
  created_at?: string
}

export async function fetchCameras() {
  const res = await client.get<Camera[]>('/api/v1/streams')
  return res.data
}

export async function createCamera(data: { stream_url: string; protocol: string; fps: number }) {
  const res = await client.post<Camera>('/api/v1/analyze/stream', data)
  return res.data
}

export async function deleteCamera(taskId: string) {
  await client.delete(`/api/v1/streams/${taskId}`)
}
