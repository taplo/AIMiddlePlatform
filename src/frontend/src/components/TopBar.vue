<template>
  <el-header class="topbar">
    <span class="topbar-title">AIMP Admin</span>
    <el-button type="danger" size="small" @click="handleLogout">Logout</el-button>
  </el-header>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"

const router = useRouter()
const auth = useAuthStore()

function handleLogout() {
  auth.logout()
  router.push("/login")
}
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #409eff;
  color: #fff;
  padding: 0 20px;
}
.topbar-title {
  font-size: 18px;
  font-weight: 600;
}
</style>
