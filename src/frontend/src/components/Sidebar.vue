<template>
  <el-menu :default-active="route.path" router style="height: 100%; border-right: none">
    <el-menu-item index="/dashboard">
      <el-icon><Monitor /></el-icon>
      <span>Dashboard</span>
    </el-menu-item>
    <el-menu-item index="/cameras">
      <el-icon><VideoCamera /></el-icon>
      <span>Cameras</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute } from "vue-router"
import { Monitor, VideoCamera } from "@element-plus/icons-vue"
const route = useRoute()
</script>
