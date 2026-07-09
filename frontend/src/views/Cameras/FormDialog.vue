<template>
  <el-dialog v-model="visible" :title="edit ? '编辑摄像头' : '添加摄像头'" width="500px">
    <el-form ref="formRef" :model="form" label-width="100px">
      <el-form-item label="流地址" prop="stream_url" :rules="[{ required: true }]">
        <el-input v-model="form.stream_url" placeholder="rtsp://..." />
      </el-form-item>
      <el-form-item label="协议" prop="protocol" :rules="[{ required: true }]">
        <el-select v-model="form.protocol" style="width:100%">
          <el-option label="RTSP" value="rtsp" />
          <el-option label="GB28181" value="gb28181" />
        </el-select>
      </el-form-item>
      <el-form-item label="FPS" prop="fps" :rules="[{ required: true }]">
        <el-input-number v-model="form.fps" :min="1" :max="30" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { createCamera } from '@/api/cameras'

const emit = defineEmits<{ created: [] }>()
const visible = ref(false)
const submitting = ref(false)
const edit = ref(false)

const form = reactive({ stream_url: '', protocol: 'rtsp', fps: 1 })

function open() { visible.value = true }

async function handleSubmit() {
  submitting.value = true
  try {
    await createCamera({ ...form })
    ElMessage.success('添加成功')
    visible.value = false
    emit('created')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>
