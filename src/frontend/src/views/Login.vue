<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <h2 style="text-align: center; margin-bottom: 20px">AIMP Admin</h2>
      <el-form @submit.prevent="handleLogin" label-width="80px">
        <el-form-item label="Username">
          <el-input v-model="username" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="password" type="password" @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleLogin" style="width: 100%">
            Login
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="error" style="color: #f56c6c; text-align: center; font-size: 13px">{{ error }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"

const router = useRouter()
const auth = useAuthStore()
const username = ref("")
const password = ref("")
const loading = ref(false)
const error = ref("")

async function handleLogin() {
  loading.value = true
  error.value = ""
  try {
    await auth.login(username.value, password.value)
    router.push("/")
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Login failed"
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}
.login-card {
  width: 380px;
}
</style>
