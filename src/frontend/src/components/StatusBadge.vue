<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{ status: string }>()

const tagType = computed(() => {
  if (props.status === "online" || props.status === "connected" || props.status === "streaming") return "success"
  if (props.status === "error") return "danger"
  return "warning"
})

const label = computed(() => {
  if (props.status === "connected") return "Online"
  if (props.status === "streaming") return "Streaming"
  return props.status.charAt(0).toUpperCase() + props.status.slice(1)
})
</script>
