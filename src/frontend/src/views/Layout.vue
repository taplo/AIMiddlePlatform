<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background: #304156">
      <Sidebar />
    </el-aside>
    <el-container>
      <TopBar />
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import Sidebar from "../components/Sidebar.vue"
import TopBar from "../components/TopBar.vue"
</script>
