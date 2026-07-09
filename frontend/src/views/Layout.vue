<template>
  <div class="layout">
    <aside class="sidebar"><Sidebar /></aside>
    <div class="main">
      <TopBar />
      <div class="content"><router-view /></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
import TopBar from '@/components/TopBar.vue'
</script>

<style scoped>
.layout { display:flex; height:100vh; }
.sidebar { width:200px; background:#001529; }
.main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.content { flex:1; padding:20px; overflow-y:auto; background:#f5f7fa; }
</style>
