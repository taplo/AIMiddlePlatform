<template>
  <div>
    <h2 style="margin-bottom:16px">流水线管理</h2>
    <el-button type="primary" style="margin-bottom:12px" @click="showCreate = true">新建流水线</el-button>

    <el-dialog v-model="showCreate" title="新建流水线" width="500px">
      <el-form>
        <el-form-item label="名称">
          <el-input v-model="newName" placeholder="pipeline_name" />
        </el-form-item>
        <el-form-item label="入口节点">
          <el-input v-model="newEntry" placeholder="entry_node_id" />
        </el-form-item>
        <el-form-item label="输出节点">
          <el-input v-model="newOutput" placeholder="output_node_id" />
        </el-form-item>
        <el-form-item label="节点列表 (JSON)">
          <el-input v-model="newNodesJson" type="textarea" :rows="6" placeholder='[{"node_id":"detect","node_type":"model_inference","config":{"model":"object_detection"},"depends_on":[]}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="store.saving" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-table :data="store.pipelines" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="node_count" label="节点数" width="100" />
      <el-table-column label="入口节点" width="200">
        <template #default="{ row }">{{ row.entry_nodes?.join(', ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="viewDAG(row.name)">查看 DAG</el-button>
          <el-button size="small" @click="handleEdit(row.name)">编辑</el-button>
          <el-popconfirm title="确定删除？" @confirm="store.remove(row.name)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDAG" title="DAG 编辑器" width="800px" top="5vh">
      <div v-if="store.currentDAG">
        <el-tag style="margin-bottom:12px">{{ store.currentDAG.name }}</el-tag>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
          <div v-for="(node, nid) in store.currentDAG.nodes" :key="nid" class="dag-node">
            <strong>{{ node.node_id }}</strong>
            <el-tag size="small" type="info" style="margin-left:6px">{{ node.node_type }}</el-tag>
            <div v-if="node.depends_on.length" style="font-size:12px;color:#909399;margin-top:4px">
              依赖: {{ node.depends_on.join(', ') }}
            </div>
          </div>
        </div>
        <canvas ref="dagCanvas" width="740" height="400" style="border:1px solid #dcdfe6;border-radius:4px;width:100%"></canvas>
      </div>
      <template #footer>
        <el-button @click="showDAG = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { usePipelineStore } from '@/stores/pipelines'

const store = usePipelineStore()
const showCreate = ref(false)
const showDAG = ref(false)
const newName = ref('')
const newEntry = ref('')
const newOutput = ref('')
const newNodesJson = ref('')
const dagCanvas = ref<HTMLCanvasElement | null>(null)

onMounted(() => store.load())

async function viewDAG(name: string) {
  await store.loadDAG(name)
  showDAG.value = true
  await nextTick()
  drawDAG()
}

async function handleEdit(name: string) {
  newName.value = name
  await store.loadDAG(name)
  if (store.currentDAG) {
    newEntry.value = store.currentDAG.entry_nodes.join(', ')
    newOutput.value = store.currentDAG.output_node
    newNodesJson.value = JSON.stringify(Object.values(store.currentDAG.nodes), null, 2)
  }
  showCreate.value = true
}

async function handleCreate() {
  let nodes: any[]
  try {
    nodes = JSON.parse(newNodesJson.value || '[]')
  } catch {
    ElMessage.error('节点 JSON 格式错误')
    return
  }
  const dag = {
    nodes,
    entry_nodes: newEntry.value ? newEntry.value.split(',').map(s => s.trim()).filter(Boolean) : [],
    output_node: newOutput.value,
  }
  const existing = store.pipelines.find(p => p.name === newName.value)
  if (existing) {
    await store.update(newName.value, dag)
    ElMessage.success('流水线已更新')
  } else {
    await store.create(newName.value, dag)
    ElMessage.success('流水线已创建')
  }
  showCreate.value = false
}

function drawDAG() {
  const canvas = dagCanvas.value
  if (!canvas || !store.currentDAG) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  const nodes = Object.values(store.currentDAG.nodes)
  if (!nodes.length) return
  const cols = Math.ceil(Math.sqrt(nodes.length))
  const boxW = 140
  const boxH = 50
  const gapX = 40
  const gapY = 60
  const startX = 30
  const startY = 30
  const positions: Record<string, { x: number; y: number }> = {}

  nodes.forEach((node, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const x = startX + col * (boxW + gapX)
    const y = startY + row * (boxH + gapY)
    positions[node.node_id] = { x, y }

    ctx.fillStyle = '#ecf5ff'
    ctx.strokeStyle = '#409eff'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.roundRect(x, y, boxW, boxH, 6)
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = '#303133'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(node.node_id, x + boxW / 2, y + boxH / 2)

    node.depends_on.forEach((depId) => {
      const from = positions[depId]
      if (!from) return
      const sx = from.x + boxW / 2
      const sy = from.y + boxH
      const ex = x + boxW / 2
      const ey = y
      ctx.strokeStyle = '#c0c4cc'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(ex, ey)
      ctx.stroke()
      const angle = Math.atan2(ey - sy, ex - sx)
      ctx.fillStyle = '#c0c4cc'
      ctx.beginPath()
      ctx.moveTo(ex, ey)
      ctx.lineTo(ex - 8 * Math.cos(angle - 0.4), ey - 8 * Math.sin(angle - 0.4))
      ctx.lineTo(ex - 8 * Math.cos(angle + 0.4), ey - 8 * Math.sin(angle + 0.4))
      ctx.closePath()
      ctx.fill()
    })
  })
}
</script>

<style scoped>
.dag-node {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 8px 12px;
  background: #fafafa;
}
</style>
