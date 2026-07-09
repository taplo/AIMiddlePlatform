<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()
const tagType = computed(() => {
  switch (props.status) {
    case 'active': case 'online': return 'success'
    case 'offline': return 'danger'
    case 'error': return 'warning'
    default: return 'info'
  }
})
const label = computed(() => {
  switch (props.status) {
    case 'active': case 'online': return '在线'
    case 'offline': return '离线'
    case 'error': return '异常'
    default: return props.status
  }
})
</script>
