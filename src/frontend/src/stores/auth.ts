import { defineStore } from "pinia"
import { ref } from "vue"
import { login as apiLogin } from "../api/auth"

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem("token") || "")
  const isAuthenticated = ref(!!token.value)

  async function login(username: string, password: string) {
    const res = await apiLogin(username, password)
    token.value = res.access_token
    isAuthenticated.value = true
    localStorage.setItem("token", res.access_token)
  }

  function logout() {
    token.value = ""
    isAuthenticated.value = false
    localStorage.removeItem("token")
  }

  return { token, isAuthenticated, login, logout }
})
