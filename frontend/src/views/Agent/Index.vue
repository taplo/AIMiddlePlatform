<template>
  <div>
    <h2 style="margin-bottom:16px">Agent 配置</h2>
    <div v-loading="store.loading">
      <el-form v-if="store.config" label-width="140px" style="max-width:800px">
        <el-divider content-position="left">LLM 端点</el-divider>
        <el-form-item label="Provider">
          <el-select v-model="form.llm.provider" style="width:320px" @change="onProviderChange">
            <el-option
              v-for="p in store.providers"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="URL">
          <el-input v-model="form.llm.url" :placeholder="defaultUrl" />
        </el-form-item>
        <el-form-item v-if="showApiKey" label="API Key">
          <el-input v-model="form.llm.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.llm.model_name" :placeholder="defaultModel" />
        </el-form-item>

        <el-divider content-position="left">系统提示词</el-divider>
        <el-form-item label="System Prompt">
          <el-input v-model="form.system_prompt" type="textarea" :rows="4" />
        </el-form-item>

        <el-divider content-position="left">置信度阈值</el-divider>
        <el-form-item v-for="(val, key) in form.thresholds" :key="key">
          <template #label>
            <span>{{ key }}</span>
            <el-tooltip :content="thresholdHints[key] || ''" placement="top" :offset="10">
              <el-icon style="margin-left:4px;color:var(--el-color-info);cursor:pointer"><WarningFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-slider v-model="form.thresholds[key]" :min="0" :max="1" :step="0.05" style="width:300px" />
          <span style="margin-left:12px;min-width:40px">{{ val }}</span>
        </el-form-item>

        <el-divider content-position="left">路由规则</el-divider>
        <el-table :data="form.routing_rules" style="width:100%" stripe>
          <el-table-column prop="scene_id" label="场景 ID" />
          <el-table-column prop="pipeline" label="流水线" />
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button text type="danger" @click="form.routing_rules.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display:flex;gap:8px;margin:12px 0">
          <el-input v-model="newRule.scene_id" placeholder="场景 ID" style="width:200px" />
          <el-input v-model="newRule.pipeline" placeholder="流水线" style="width:200px" />
          <el-button @click="addRule">添加规则</el-button>
        </div>

        <el-divider />
        <el-button type="primary" :loading="store.saving" @click="handleSave">保存配置</el-button>
      </el-form>
      <el-skeleton :rows="6" animated v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { useAgentStore } from '@/stores/agent'

const store = useAgentStore()
const form = reactive({
  llm: { provider: 'openai', url: '', api_key: '', model_name: '' },
  system_prompt: '',
  thresholds: {} as Record<string, number>,
  routing_rules: [] as { scene_id: string; pipeline: string }[],
})
const newRule = reactive({ scene_id: '', pipeline: '' })

const thresholdHints: Record<string, string> = {
  parking_lot: '停车场场景下，检测结果置信度低于此值将交由 LLM Agent 二次确认',
  entrance: '出入口场景下，检测结果置信度低于此值将交由 LLM Agent 二次确认',
  street: '街道场景下，检测结果置信度低于此值将交由 LLM Agent 二次确认',
  indoor: '室内场景下，检测结果置信度低于此值将交由 LLM Agent 二次确认',
}

const showApiKey = computed(() => form.llm.provider !== 'ollama')

const defaultUrl = computed(() => {
  const p = store.providers.find(p => p.id === form.llm.provider)
  return p?.default_url || ''
})

const defaultModel = computed(() => {
  const map: Record<string, string> = {
    openai: 'Qwen/Qwen2.5-VL-7B-Instruct',
    ollama: 'llama3.2-vision',
    lm_studio: '（自动检测）',
  }
  return map[form.llm.provider] || ''
})

onMounted(async () => {
  await store.load()
  if (store.config) {
    Object.assign(form, JSON.parse(JSON.stringify(store.config)))
  }
})

function onProviderChange(provider: string) {
  const p = store.providers.find(p => p.id === provider)
  if (p) {
    form.llm.url = p.default_url
  }
  if (provider === 'ollama') {
    form.llm.api_key = ''
  }
  if (!form.llm.model_name) {
    const map: Record<string, string> = {
      openai: 'Qwen/Qwen2.5-VL-7B-Instruct',
      ollama: 'llama3.2-vision',
      lm_studio: '',
    }
    form.llm.model_name = map[provider] || ''
  }
}

function addRule() {
  if (!newRule.scene_id || !newRule.pipeline) return
  form.routing_rules.push({ scene_id: newRule.scene_id, pipeline: newRule.pipeline })
  newRule.scene_id = ''
  newRule.pipeline = ''
}

async function handleSave() {
  await store.save({ ...form } as any)
  ElMessage.success('配置已保存')
}
</script>
