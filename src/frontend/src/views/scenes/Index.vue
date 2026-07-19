<template>
  <div>
    <h2>Scene Configuration</h2>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="Pipelines" name="pipelines">
        <div style="margin-bottom: 12px">
          <el-button type="primary" @click="showPipelineForm = true">New Pipeline</el-button>
        </div>
        <el-table :data="store.pipelines" v-loading="store.pipelineLoading" stripe>
          <el-table-column prop="name" label="Name" />
          <el-table-column prop="node_count" label="Nodes" width="80" />
          <el-table-column label="Entry Nodes" min-width="200">
            <template #default="{ row }">
              <el-tag v-for="n in row.entry_nodes" :key="n" size="small" style="margin-right: 4px">{{ n }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="output_node" label="Output" width="180" />
          <el-table-column label="Actions" width="200">
            <template #default="{ row }">
              <el-button size="small" @click="viewDAG(row.name)">View DAG</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row.name)">Delete</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="Routing Rules" name="rules">
        <div style="margin-bottom: 12px">
          <el-button type="primary" @click="showRuleForm = true">New Rule</el-button>
        </div>
        <el-table :data="store.rules" v-loading="store.rulesLoading" stripe>
          <el-table-column prop="name" label="Name" />
          <el-table-column prop="rule_type" label="Type" width="120" />
          <el-table-column prop="severity" label="Severity" width="90">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'high' ? 'danger' : row.severity === 'medium' ? 'warning' : 'info'" size="small">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Enabled" width="80">
            <template #default="{ row }">
              <el-switch :modelValue="row.enabled" @change="toggleRule(row)" size="small" />
            </template>
          </el-table-column>
          <el-table-column prop="description" label="Description" min-width="200" show-overflow-tooltip />
          <el-table-column label="Actions" width="160">
            <template #default="{ row }">
              <el-button size="small" @click="editRule(row)">Edit</el-button>
              <el-button size="small" type="danger" @click="handleDeleteRule(row.id)">Delete</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showDAG" title="Pipeline DAG" width="700px">
      <div v-if="store.currentDAG">
        <h4>{{ store.currentDAG.name }}</h4>
        <el-table :data="dagNodes" stripe>
          <el-table-column prop="node_id" label="Node ID" width="160" />
          <el-table-column prop="node_type" label="Type" width="140" />
          <el-table-column prop="depends_on" label="Depends On" min-width="180">
            <template #default="{ row }">
              <span v-if="row.depends_on.length === 0" class="text-muted">—</span>
              <el-tag v-for="d in row.depends_on" :key="d" size="small" style="margin-right: 4px">{{ d }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <el-dialog v-model="showPipelineForm" :title="editingPipeline ? 'Edit Pipeline' : 'New Pipeline'" width="500px">
      <el-form :model="pipelineForm" label-width="120px">
        <el-form-item label="Name" required>
          <el-input v-model="pipelineForm.name" :disabled="!!editingPipeline" />
        </el-form-item>
        <el-form-item label="Entry Nodes">
          <el-input v-model="pipelineForm.entryNodes" placeholder="comma separated" />
        </el-form-item>
        <el-form-item label="Output Node">
          <el-input v-model="pipelineForm.outputNode" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPipelineForm = false">Cancel</el-button>
        <el-button type="primary" :loading="savingPipeline" @click="handleSavePipeline">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showRuleForm" :title="editingRule ? 'Edit Rule' : 'New Rule'" width="500px">
      <el-form :model="ruleForm" label-width="120px">
        <el-form-item label="Name" required>
          <el-input v-model="ruleForm.name" />
        </el-form-item>
        <el-form-item label="Type" required>
          <el-select v-model="ruleForm.rule_type" style="width: 100%">
            <el-option label="Scene Detection" value="scene_detection" />
            <el-option label="Motion Detection" value="motion_detection" />
            <el-option label="Face Recognition" value="face_recognition" />
            <el-option label="Object Detection" value="object_detection" />
            <el-option label="Custom" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="Severity">
          <el-select v-model="ruleForm.severity" style="width: 100%">
            <el-option label="Low" value="low" />
            <el-option label="Medium" value="medium" />
            <el-option label="High" value="high" />
          </el-select>
        </el-form-item>
        <el-form-item label="Config (JSON)">
          <el-input v-model="ruleForm.config" type="textarea" :rows="4" placeholder='{"threshold": 0.5}' />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="ruleForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRuleForm = false">Cancel</el-button>
        <el-button type="primary" :loading="savingRule" @click="handleSaveRule">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useSceneStore } from "../../stores/scenes"
import { createPipeline, updatePipeline, createRule, updateRule, getRule } from "../../api/scenes"
import type { Rule } from "../../api/scenes"

const store = useSceneStore()
const activeTab = ref("pipelines")

onMounted(() => {
  store.fetchPipelines()
  store.fetchRules()
})

const showDAG = ref(false)
const dagNodes = computed(() => {
  if (!store.currentDAG) return []
  return Object.entries(store.currentDAG.nodes).map(([, v]) => v)
})

async function viewDAG(name: string) {
  await store.fetchDAG(name)
  showDAG.value = true
}

async function handleDelete(name: string) {
  await store.removePipeline(name)
}

const showPipelineForm = ref(false)
const editingPipeline = ref(false)
const savingPipeline = ref(false)
const pipelineForm = ref({ name: "", entryNodes: "", outputNode: "" })

async function handleSavePipeline() {
  savingPipeline.value = true
  try {
    const entryNodes = pipelineForm.value.entryNodes ? pipelineForm.value.entryNodes.split(",").map((s: string) => s.trim()).filter(Boolean) : []
    if (editingPipeline.value) {
      await updatePipeline(pipelineForm.value.name, [], entryNodes, pipelineForm.value.outputNode)
    } else {
      await createPipeline(pipelineForm.value.name, [], entryNodes, pipelineForm.value.outputNode)
    }
    showPipelineForm.value = false
    await store.fetchPipelines()
  } finally {
    savingPipeline.value = false
  }
}

const showRuleForm = ref(false)
const editingRule = ref(false)
const savingRule = ref(false)
const ruleForm = ref<{ name: string; rule_type: string; severity: string; config: string; description: string; id?: number }>({
  name: "", rule_type: "scene_detection", severity: "medium", config: "{}", description: "", id: undefined,
})

async function editRule(row: Rule) {
  editingRule.value = true
  ruleForm.value = {
    id: row.id,
    name: row.name,
    rule_type: row.rule_type,
    severity: row.severity,
    config: row.config,
    description: row.description,
  }
  showRuleForm.value = true
}

async function handleSaveRule() {
  savingRule.value = true
  try {
    if (editingRule.value && ruleForm.value.id) {
      await updateRule(ruleForm.value.id, {
        name: ruleForm.value.name,
        rule_type: ruleForm.value.rule_type,
        severity: ruleForm.value.severity,
        config: ruleForm.value.config,
        description: ruleForm.value.description,
      })
    } else {
      await createRule({
        name: ruleForm.value.name,
        rule_type: ruleForm.value.rule_type,
        severity: ruleForm.value.severity,
        config: ruleForm.value.config,
        description: ruleForm.value.description,
      })
    }
    showRuleForm.value = false
    ruleForm.value = { name: "", rule_type: "scene_detection", severity: "medium", config: "{}", description: "" }
    editingRule.value = false
    await store.fetchRules()
  } finally {
    savingRule.value = false
  }
}

async function toggleRule(row: Rule) {
  await updateRule(row.id, { enabled: !row.enabled })
  row.enabled = !row.enabled
}

async function handleDeleteRule(id: number) {
  await store.removeRule(id)
}
</script>

<style scoped>
.text-muted { color: #999; }
</style>
