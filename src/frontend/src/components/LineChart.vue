<template>
  <v-chart :option="option" autoresize style="height: 300px" />
</template>

<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "echarts"

const props = defineProps<{
  title: string
  xData: string[]
  series: { name: string; data: number[]; color?: string }[]
}>()

const option = computed(() => ({
  title: { text: props.title, left: "center", textStyle: { fontSize: 14 } },
  tooltip: { trigger: "axis" },
  legend: { bottom: 0, data: props.series.map((s) => s.name) },
  grid: { left: 50, right: 20, top: 40, bottom: 30 },
  xAxis: { type: "category", data: props.xData, boundaryGap: false },
  yAxis: { type: "value" },
  series: props.series.map((s) => ({
    name: s.name,
    type: "line",
    data: s.data,
    smooth: true,
    lineStyle: { color: s.color },
    itemStyle: { color: s.color },
  })),
}))
</script>
