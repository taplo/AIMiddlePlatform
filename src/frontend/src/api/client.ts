import axios from "axios"
import type { AxiosInstance, InternalAxiosRequestConfig } from "axios"

const client: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
})

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("token")
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token")
      window.location.href = "/login"
    }
    return Promise.reject(err)
  },
)

export default client
