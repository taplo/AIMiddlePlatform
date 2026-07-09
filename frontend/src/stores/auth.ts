import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const user = ref('')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('access_token', t)
  }

  function clear() {
    token.value = ''
    user.value = ''
    localStorage.removeItem('access_token')
  }

  return { token, user, setToken, clear }
})
