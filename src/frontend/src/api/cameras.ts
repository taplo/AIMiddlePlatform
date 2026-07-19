import client from "./client"

export interface Camera {
  camera_id: string
  url: string
  protocol: string
  connected: boolean
  running: boolean
  frames_read: number
  frames_kept: number
  fps_output: number
  fps_target: number
  reconnects: number
  uptime_seconds: number
  last_error: string
}

export interface CameraCreate {
  camera_id: string
  stream_url: string
  protocol: string
  target_fps?: number
}

export async function listCameras(): Promise<Camera[]> {
  const { data } = await client.get<Camera[]>("/streams")
  return data
}

export async function createCamera(req: CameraCreate): Promise<Camera> {
  const { data } = await client.post<Camera>("/analyze/stream", req)
  return data
}

export async function deleteCamera(cameraId: string): Promise<void> {
  await client.delete(`/streams/${cameraId}`)
}
