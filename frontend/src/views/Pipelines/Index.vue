<template>
  <div>
    <h2 style="margin-bottom:16px">流水线管理</h2>
    <el-button type="primary" style="margin-bottom:12px" @click="openNew">新建流水线</el-button>

    <el-table :data="store.pipelines" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="node_count" label="节点数" width="100" />
      <el-table-column label="入口节点" width="200">
        <template #default="{ row }">{{ row.entry_nodes?.join(', ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="openEditor(row.name)">编辑 DAG</el-button>
          <el-popconfirm title="确定删除？" @confirm="store.remove(row.name)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showEditor" :title="editorTitle" width="900px" top="3vh" :close-on-click-modal="false">
      <div v-if="editorDag" style="display:flex;gap:12px;height:520px">
        <div style="width:180px;flex-shrink:0">
          <div style="font-weight:600;margin-bottom:8px">节点类型</div>
          <div v-for="nt in nodeTypes" :key="nt.type" draggable="true" @dragstart="onDragStart($event, nt)" class="palette-item">
            <el-tag size="small" :type="nt.tagType" style="margin-right:4px">{{ nt.label }}</el-tag>
            <span style="font-size:12px">{{ nt.type }}</span>
          </div>
          <el-divider />
          <el-form label-width="60px" label-position="top" style="font-size:12px">
            <el-form-item label="名称">
              <el-input v-model="editorDag.name" size="small" />
            </el-form-item>
            <el-form-item label="入口节点">
              <el-select v-model="editorDag.entry_nodes" multiple size="small" placeholder="选择入口" style="width:100%">
                <el-option v-for="n in editorDag.nodes" :key="n.node_id" :label="n.node_id" :value="n.node_id" />
              </el-select>
            </el-form-item>
            <el-form-item label="输出节点">
              <el-select v-model="editorDag.output_node" size="small" placeholder="选择输出" style="width:100%">
                <el-option v-for="n in editorDag.nodes" :key="n.node_id" :label="n.node_id" :value="n.node_id" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>
        <div style="flex:1;border:1px solid #dcdfe6;border-radius:4px;position:relative">
          <div class="vue-flow-wrapper">
            <VueFlow v-model:nodes="flowNodes" v-model:edges="flowEdges" @drop="onDrop" @dragover.prevent="onDragOver" @node-click="onNodeClick" @connect="onConnect" :default-edge-options="{ animated: true, style: { stroke: '#409eff' } }" fit-view-on-init>
              <template #node-custom="props">
                <div class="vf-node" :style="{ borderColor: nodeColor(props.data.type) }">
                  <div class="vf-node-header" :style="{ background: nodeColor(props.data.type) }">
                    <strong>{{ props.data.label }}</strong>
                    <el-tag size="small" style="margin-left:4px">{{ props.data.type }}</el-tag>
                  </div>
                  <div class="vf-node-body">
                    <div v-if="props.data.type==='model_inference'" style="font-size:12px">模型: {{ props.data.model || '未设置' }}</div>
                    <div v-else style="font-size:12px;color:#909399">{{ props.data.config?.description || '无配置' }}</div>
                  </div>
                  <Handle type="target" :position="Position.Top" />
                  <Handle type="source" :position="Position.Bottom" />
                  <div class="vf-node-close" @click.stop="removeNode(props.id)" title="删除节点">✕</div>
                </div>
              </template>
              <Background :gap="20" />
              <Controls />
            </VueFlow>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" :loading="store.saving" @click="saveEditor">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showConfig" title="节点配置" width="400px">
      <el-form label-width="80px" v-if="configNode">
        <el-form-item label="节点 ID">
          <el-input v-model="configNode.node_id" size="small" />
        </el-form-item>
        <el-form-item label="节点类型">
          <el-tag size="small">{{ configNode.node_type }}</el-tag>
        </el-form-item>
        <template v-if="configNode.node_type === 'model_inference'">
          <el-form-item label="模型">
            <el-select v-model="configNode.config.model" size="small" placeholder="选择模型" style="width:100%">
              <el-option v-for="m in modelStore.list" :key="m.model_id" :label="m.name || m.model_id" :value="m.model_id" />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="configNode.node_type === 'condition'">
          <el-form-item label="条件">
            <el-input v-model="configNode.config.expression" size="small" placeholder="count > 0" />
          </el-form-item>
        </template>
        <el-form-item label="其他配置">
          <el-input v-model="configJson" type="textarea" :rows="4" size="small" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showConfig = false">关闭</el-button>
        <el-button type="primary" @click="saveConfig">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { VueFlow, Handle, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { useModelStore } from '@/stores/models'
import { usePipelineStore } from '@/stores/pipelines'
import type { PipelineNode } from '@/api/pipelines'

const modelStore = useModelStore()
const store = usePipelineStore()
const showEditor = ref(false)
const showConfig = ref(false)
const editorDag = ref<{ name: string; nodes: PipelineNode[]; entry_nodes: string[]; output_node: string } | null>(null)
const configNode = ref<PipelineNode | null>(null)
const configJson = ref('')
const editingName = ref('')
const nodeIdCounter = ref(0)

const flowNodes = ref<any[]>([])
const flowEdges = ref<any[]>([])

const nodeTypes = [
  { type: 'model_inference', label: '模型推理', tagType: 'primary' },
  { type: 'condition', label: '条件分支', tagType: 'warning' },
  { type: 'aggregate', label: '聚合', tagType: 'success' },
  { type: 'verify', label: '验证', tagType: 'danger' },
  { type: 'output', label: '输出', tagType: 'info' },
]

const nodeColorMap: Record<string, string> = {
  model_inference: '#409eff',
  condition: '#e6a23c',
  aggregate: '#67c23a',
  verify: '#f56c6c',
  output: '#909399',
}

function nodeColor(type: string): string {
  return nodeColorMap[type] || '#409eff'
}

const editorTitle = computed(() => editingName.value ? `编辑 DAG: ${editingName.value}` : '新建 DAG')

onMounted(() => store.load())

function openNew() {
  editingName.value = ''
  nodeIdCounter.value = 0
  editorDag.value = { name: '', nodes: [], entry_nodes: [], output_node: '' }
  flowNodes.value = []
  flowEdges.value = []
  modelStore.load()
  showEditor.value = true
}

async function openEditor(name: string) {
  await store.loadDAG(name)
  if (!store.currentDAG) return
  editingName.value = name
  const dag = store.currentDAG
  const nodes: PipelineNode[] = dag.nodes ? Object.values(dag.nodes) : []
  editorDag.value = {
    name: dag.name,
    nodes: nodes,
    entry_nodes: dag.entry_nodes,
    output_node: dag.output_node,
  }
  nodeIdCounter.value = nodes.length
  flowNodes.value = dagToFlow(nodes)
  flowEdges.value = dagToEdges(nodes)
  modelStore.load()
  showEditor.value = true
}

function dagToFlow(nodes: PipelineNode[]): any[] {
  const cols = Math.ceil(Math.sqrt(nodes.length))
  return nodes.map((n, i) => ({
    id: n.node_id,
    type: 'custom',
    position: { x: 30 + (i % cols) * 200, y: 30 + Math.floor(i / cols) * 120 },
    data: { label: n.node_id, type: n.node_type, ...n.config },
  }))
}

function dagToEdges(nodes: PipelineNode[]): any[] {
  const edges: any[] = []
  for (const n of nodes) {
    for (const dep of n.depends_on) {
      edges.push({ id: `${dep}->${n.node_id}`, source: dep, target: n.node_id })
    }
  }
  return edges
}

function onDragStart(event: DragEvent, nt: { type: string; label: string }) {
  event.dataTransfer?.setData('application/vnd.aimp.node', JSON.stringify(nt))
}

let _dropCounter = 0

function onDragOver(event: DragEvent) {
  event.dataTransfer!.dropEffect = 'move'
}

function onDrop(event: DragEvent) {
  const raw = event.dataTransfer?.getData('application/vnd.aimp.node')
  if (!raw || !editorDag.value) return
  const nt = JSON.parse(raw)
  _dropCounter++
  const nid = `${nt.type}-${_dropCounter}`
  const rect = (event.target as HTMLElement).closest('.vue-flow-wrapper')?.getBoundingClientRect()
  const x = rect ? event.clientX - rect.left - 60 : 100
  const y = rect ? event.clientY - rect.top - 20 : 100

  const node: PipelineNode = { node_id: nid, node_type: nt.type, config: {}, depends_on: [] }
  editorDag.value.nodes.push(node)
  flowNodes.value.push({
    id: nid,
    type: 'custom',
    position: { x, y },
    data: { label: nid, type: nt.type },
  })
}

function onNodeClick({ node }: { node: any }) {
  openConfig(node.id)
}

function onConnect(connection: { source: string; target: string }) {
  const source = editorDag.value?.nodes.find(n => n.node_id === connection.source)
  const target = editorDag.value?.nodes.find(n => n.node_id === connection.target)
  if (!source || !target) return
  if (!target.depends_on.includes(connection.source)) {
    target.depends_on.push(connection.source)
  }
}

function removeNode(nodeId: string) {
  if (!editorDag.value) return
  editorDag.value.nodes = editorDag.value.nodes.filter(n => n.node_id !== nodeId)
  const idx = flowNodes.value.findIndex((n: any) => n.id === nodeId)
  if (idx >= 0) flowNodes.value.splice(idx, 1)
  flowEdges.value = flowEdges.value.filter((e: any) => e.source !== nodeId && e.target !== nodeId)
}

function openConfig(nodeId: string) {
  const n = editorDag.value?.nodes.find(n => n.node_id === nodeId)
  if (!n) return
  configNode.value = n
  configJson.value = JSON.stringify(n.config, null, 2)
  showConfig.value = true
}

function saveConfig() {
  if (!configNode.value) return
  try {
    const parsed = JSON.parse(configJson.value || '{}')
    configNode.value.config = parsed
    ElMessage.success('配置已更新')
  } catch {
    if (configJson.value.trim()) {
      ElMessage.error('JSON 格式错误')
      return
    }
    configNode.value.config = {}
  }
  showConfig.value = false
}

function collectEdges(): PipelineNode[] {
  return editorDag.value!.nodes.map(n => ({
    node_id: n.node_id,
    node_type: n.node_type,
    config: n.config,
    depends_on: n.depends_on,
  }))
}

async function saveEditor() {
  if (!editorDag.value) return
  const name = editorDag.value.name.trim()
  if (!name) { ElMessage.error('请输入流水线名称'); return }
  const nodes = collectEdges()
  const body = { nodes, entry_nodes: editorDag.value.entry_nodes, output_node: editorDag.value.output_node }

  try {
    if (editingName.value) {
      await store.update(editingName.value, body)
      ElMessage.success('流水线已更新')
    } else {
      await store.create(name, body)
      ElMessage.success('流水线已创建')
    }
    showEditor.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存流水线失败')
  }
}
</script>

<style scoped>
.palette-item {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  margin-bottom: 4px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: grab;
  background: #fafafa;
  transition: background 0.15s;
}
.palette-item:hover {
  background: #ecf5ff;
}
.vue-flow-wrapper {
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.vf-node {
  border: 2px solid #409eff;
  border-radius: 6px;
  background: #fff;
  min-width: 150px;
  font-size: 13px;
  cursor: pointer;
}
.vf-node-header {
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px 4px 0 0;
  display: flex;
  align-items: center;
}
.vf-node-body {
  padding: 6px 8px;
}
.vf-node {
  position: relative;
}
.vf-node-close {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.vf-node:hover .vf-node-close {
  opacity: 1;
}
</style>
