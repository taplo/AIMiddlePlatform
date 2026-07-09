import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTraces, fetchTraceDetail, type TraceSummary, type TraceDetail } from '@/api/traces'

export const useTraceStore = defineStore('traces', () => {
  const traces = ref<TraceSummary[]>([])
  const detail = ref<TraceDetail | null>(null)
  const loading = ref(false)
  const errorOnly = ref(false)
  const minDuration = ref(0)

  async function load() {
    loading.value = true
    try {
      traces.value = await fetchTraces({
        error_only: errorOnly.value,
        min_duration_ms: minDuration.value || undefined,
        limit: 50,
      })
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(traceId: string) {
    loading.value = true
    try {
      detail.value = await fetchTraceDetail(traceId)
    } finally {
      loading.value = false
    }
  }

  return { traces, detail, loading, errorOnly, minDuration, load, loadDetail }
})
