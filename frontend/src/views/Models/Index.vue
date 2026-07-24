<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <h2>模型管理</h2>
      <el-button type="primary" @click="importDialogRef?.open()">
        <el-icon style="margin-right:4px"><Plus /></el-icon>
        导入模型
      </el-button>
    </div>
    <el-table :data="store.list" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="model_id" label="模型 ID" width="180" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column prop="backend" label="后端" width="80" />
      <el-table-column label="状态" width="140">
        <template #default="{ row }">
          <el-switch
            :model-value="row.status === 'online'"
            :active-text="row.status === 'online' ? '在线' : '离线'"
            inactive-text="离线"
            @change="(val: boolean) => toggleStatus(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="标签" width="150">
        <template #default="{ row }">
          <el-tag v-for="tag in row.tags" :key="tag" size="small" style="margin-right:4px">{{ tag }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="dialogRef?.open(row.model_id)">统计</el-button>
          <el-popconfirm title="确定删除此模型？" @confirm="handleDelete(row)">
            <template #reference>
              <el-button text type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <StatsDialog ref="dialogRef" />
    <ImportDialog ref="importDialogRef" @done="store.load()" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useModelStore } from '@/stores/models'
import { updateModelStatus, deleteModel } from '@/api/models'
import StatsDialog from './StatsDialog.vue'
import ImportDialog from './ImportDialog.vue'

const store = useModelStore()
const dialogRef = ref<InstanceType<typeof StatsDialog>>()
const importDialogRef = ref<InstanceType<typeof ImportDialog>>()

onMounted(() => store.load())

async function toggleStatus(row: any, val: boolean) {
  const status = val ? 'online' : 'offline'
  try {
    await updateModelStatus(row.model_id, status)
    row.status = status
    ElMessage.success(`${row.model_id} 已${val ? '上线' : '下线'}`)
  } catch {
    ElMessage.error('状态更新失败')
  }
}

async function handleDelete(row: any) {
  try {
    await deleteModel(row.model_id)
    ElMessage.success(`模型 ${row.model_id} 已删除`)
    store.load()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
