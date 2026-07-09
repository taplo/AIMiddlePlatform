<template>
  <v-chart :option="option" style="height:280px" autoresize />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart as ELineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'

use([CanvasRenderer, ELineChart, GridComponent, TooltipComponent])

const props = defineProps<{ title: string; data: number[]; color?: string }>()

const option = computed(() => ({
  title: { text: props.title, textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'axis' as const },
  grid: { left: 40, right: 20, bottom: 30 },
  xAxis: { type: 'category' as const, data: Array(props.data.length).fill('').map((_, i) => `${i}s`) },
  yAxis: { type: 'value' as const, min: 0 },
  series: [{ type: 'line' as const, data: props.data, smooth: true, lineStyle: { color: props.color || '#409eff' }, areaStyle: { color: props.color || '#409eff', opacity: 0.1 } }],
})) as any
</script>
