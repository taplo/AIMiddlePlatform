<template>
  <div class="topbar">
    <span class="title">AI 算法调度中台 v0.1.0</span>
    <div class="right">
      <el-dropdown trigger="click">
        <span class="user-btn">{{ username }}</span>
        <template #dropdown>
          <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = 'admin'

function logout() {
  auth.clear()
  router.push('/login')
}
</script>

<style scoped>
.topbar { display:flex; align-items:center; justify-content:space-between; height:50px;
  padding:0 20px; background:#fff; border-bottom:1px solid #eee; }
.title { font-size:16px; font-weight:600; color:#303133; }
.user-btn { cursor:pointer; color:#409eff; }
</style>
