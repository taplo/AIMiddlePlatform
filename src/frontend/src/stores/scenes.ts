import { defineStore } from "pinia"
import { ref } from "vue"
import { listPipelines, getPipeline, deletePipeline, listRules, getRule, deleteRule } from "../api/scenes"
import type { PipelineSummary, PipelineDAG, Rule, RulePage } from "../api/scenes"

export const useSceneStore = defineStore("scenes", () => {
  const pipelines = ref<PipelineSummary[]>([])
  const pipelineLoading = ref(false)
  const currentDAG = ref<PipelineDAG | null>(null)

  const rules = ref<Rule[]>([])
  const rulesTotal = ref(0)
  const rulesLoading = ref(false)

  async function fetchPipelines() {
    pipelineLoading.value = true
    try {
      pipelines.value = await listPipelines()
    } finally {
      pipelineLoading.value = false
    }
  }

  async function fetchDAG(name: string) {
    currentDAG.value = await getPipeline(name)
  }

  async function removePipeline(name: string) {
    await deletePipeline(name)
    pipelines.value = pipelines.value.filter((p) => p.name !== name)
  }

  async function fetchRules(ruleType?: string, enabled?: boolean, page = 1, pageSize = 50) {
    rulesLoading.value = true
    try {
      const res: RulePage = await listRules(ruleType, enabled, page, pageSize)
      rules.value = res.items
      rulesTotal.value = res.total
    } finally {
      rulesLoading.value = false
    }
  }

  async function removeRule(id: number) {
    await deleteRule(id)
    rules.value = rules.value.filter((r) => r.id !== id)
  }

  return {
    pipelines, pipelineLoading, currentDAG, rules, rulesTotal, rulesLoading,
    fetchPipelines, fetchDAG, removePipeline,
    fetchRules, removeRule,
  }
})
