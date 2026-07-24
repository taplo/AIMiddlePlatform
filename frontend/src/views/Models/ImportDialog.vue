<template>
  <el-dialog v-model="visible" title="导入模型" width="560px" :close-on-click-modal="false">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="模型文件" prop="file">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :show-file-list="true"
          :limit="1"
          :on-change="onFileChange"
          :on-remove="() => (form.file = null)"
          accept=".onnx,.aimp,.pt,.pth,.bin"
          drag
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">将模型文件拖到此处或<em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 .onnx / .aimp / .pt / .pth / .bin 格式</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="模型 ID" prop="model_id">
        <el-input v-model="form.model_id" placeholder="唯一标识，如 face_detection" />
      </el-form-item>

      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="显示名称，留空则使用模型 ID" />
      </el-form-item>

      <el-form-item label="版本" prop="version">
        <el-input v-model="form.version" placeholder="1.0.0" />
      </el-form-item>

      <el-form-item label="后端" prop="backend">
        <el-select v-model="form.backend" style="width:200px">
          <el-option label="ONNX" value="onnx" />
          <el-option label="PyTorch" value="pytorch" />
          <el-option label="TensorFlow" value="tensorflow" />
          <el-option label="OpenVINO" value="openvino" />
        </el-select>
      </el-form-item>

      <el-form-item label="标签">
        <el-input v-model="form.tags" placeholder="逗号分隔，如 face,detection,yolo" />
      </el-form-item>

      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="uploading" @click="handleUpload">
        {{ uploading ? '上传中...' : '导入' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type UploadInstance, type UploadFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { uploadModel } from '@/api/models'

const emit = defineEmits<{ done: [] }>()

const visible = ref(false)
const uploading = ref(false)
const formRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()

const form = reactive({
  file: null as File | null,
  model_id: '',
  name: '',
  version: '1.0.0',
  backend: 'onnx',
  tags: '',
  description: '',
})

const rules = {
  file: [{ required: true, message: '请选择模型文件', trigger: 'change' }],
  model_id: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
  backend: [{ required: true, message: '请选择后端类型', trigger: 'change' }],
}

function open() {
  visible.value = true
  form.file = null
  form.model_id = ''
  form.name = ''
  form.version = '1.0.0'
  form.backend = 'onnx'
  form.tags = ''
  form.description = ''
  uploadRef.value?.clearFiles()
}

function onFileChange(uploadFile: UploadFile) {
  form.file = uploadFile.raw || null
}

async function handleUpload() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid || !form.file) return

  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', form.file)
    fd.append('model_id', form.model_id)
    fd.append('name', form.name || form.model_id)
    fd.append('version', form.version)
    fd.append('backend', form.backend)
    fd.append('tags', form.tags)
    fd.append('description', form.description)

    await uploadModel(fd)
    ElMessage.success(`模型 ${form.model_id} 导入成功`)
    visible.value = false
    emit('done')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    uploading.value = false
  }
}

defineExpose({ open })
</script>
