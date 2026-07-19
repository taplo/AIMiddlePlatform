import { defineStore } from "pinia"
import { ref } from "vue"
import { listCameras, deleteCamera } from "../api/cameras"
import type { Camera } from "../api/cameras"

export const useCameraStore = defineStore("cameras", () => {
  const cameras = ref<Camera[]>([])
  const loading = ref(false)

  async function fetchCameras() {
    loading.value = true
    try {
      cameras.value = await listCameras()
    } finally {
      loading.value = false
    }
  }

  async function removeCamera(cameraId: string) {
    await deleteCamera(cameraId)
    cameras.value = cameras.value.filter((c) => c.camera_id !== cameraId)
  }

  return { cameras, loading, fetchCameras, removeCamera }
})
