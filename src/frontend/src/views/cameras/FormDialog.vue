<template>
  <el-dialog v-model="visible" title="Add Camera" width="500px" @update:model-value="$emit('update:visible', $event)">
    <el-form :model="form" label-width="100px">
      <el-form-item label="Camera ID" required>
        <el-input v-model="form.camera_id" />
      </el-form-item>
      <el-form-item label="Stream URL" required>
        <el-input v-model="form.stream_url" placeholder="rtsp://..." />
      </el-form-item>
      <el-form-item label="Protocol">
        <el-select v-model="form.protocol" style="width: 100%">
          <el-option label="RTSP" value="rtsp" />
          <el-option label="GB28181" value="gb28181" />
        </el-select>
      </el-form-item>
      <el-form-item label="Target FPS">
        <el-input-number v-model="form.target_fps" :min="0.1" :max="30" :step="0.5" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">Submit</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from "vue"
import { ElMessage } from "element-plus"
import { createCamera } from "../../api/cameras"

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ "update:visible": [v: boolean]; done: [] }>()

const visible = ref(props.visible)
watch(() => props.visible, (v) => { visible.value = v })
watch(visible, (v) => emit("update:visible", v))

const submitting = ref(false)
const form = reactive({
  camera_id: "",
  stream_url: "",
  protocol: "rtsp",
  target_fps: 2.0,
})

async function handleSubmit() {
  if (!form.camera_id || !form.stream_url) {
    ElMessage.warning("Camera ID and Stream URL are required")
    return
  }
  submitting.value = true
  try {
    await createCamera(form)
    ElMessage.success("Camera added")
    visible.value = false
    emit("done")
  } catch {
    ElMessage.error("Failed to add camera")
  } finally {
    submitting.value = false
  }
}
</script>
