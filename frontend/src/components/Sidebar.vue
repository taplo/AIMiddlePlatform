<template>
  <el-menu :default-active="route.path" router style="height:100%;border-right:none">
    <el-menu-item index="/dashboard">
      <el-icon><Odometer /></el-icon><span>系统总览</span>
    </el-menu-item>
    <el-menu-item index="/cameras">
      <el-icon><VideoCamera /></el-icon><span>视频源管理</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Odometer, VideoCamera } from '@element-plus/icons-vue'
const route = useRoute()
</script>
