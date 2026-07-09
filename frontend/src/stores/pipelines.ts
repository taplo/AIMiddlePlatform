import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchPipelines,
  fetchPipelineDAG,
  createPipeline,
  updatePipeline,
  deletePipeline,
  type PipelineSummary,
  type PipelineDAG,
  type PipelineCreateBody,
} from '@/api/pipelines'

export const usePipelineStore = defineStore('pipelines', () => {
  const pipelines = ref<PipelineSummary[]>([])
  const currentDAG = ref<PipelineDAG | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      pipelines.value = await fetchPipelines()
    } finally {
      loading.value = false
    }
  }

  async function loadDAG(name: string) {
    loading.value = true
    try {
      currentDAG.value = await fetchPipelineDAG(name)
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, dag: PipelineCreateBody) {
    saving.value = true
    try {
      await createPipeline(name, dag)
      await load()
    } finally {
      saving.value = false
    }
  }

  async function update(name: string, dag: PipelineCreateBody) {
    saving.value = true
    try {
      await updatePipeline(name, dag)
      await loadDAG(name)
    } finally {
      saving.value = false
    }
  }

  async function remove(name: string) {
    saving.value = true
    try {
      await deletePipeline(name)
      if (currentDAG.value?.name === name) currentDAG.value = null
      await load()
    } finally {
      saving.value = false
    }
  }

  return { pipelines, currentDAG, loading, saving, load, loadDAG, create, update, remove }
})
