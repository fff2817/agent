<script setup>
import { computed, ref } from 'vue'
import { useUpload } from '../composables/useUpload'
import { ACCEPT_ATTR, getFileIcon } from '../utils/fileTypes'

const props = defineProps({
  modelValue: { type: String, default: '' },
  isGenerating: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  statusText: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'send', 'stop', 'uploaded'])

const fileInputRef = ref(null)
const {
  attachments,
  uploadFiles,
  isUploading,
  removeAttachment,
  takeReadyAttachments,
} = useUpload()

const uploading = computed(() => isUploading())
const hasAttachments = computed(() => attachments.value.length > 0)
const readyCount = computed(
  () => attachments.value.filter((a) => a.status === 'success').length,
)

const canSend = computed(() => {
  if (props.isGenerating) return true
  if (uploading.value) return false
  const hasText = Boolean(props.modelValue.trim())
  const hasReady = readyCount.value > 0
  return hasText || hasReady
})

function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (props.isGenerating || uploading.value) return
    if (!canSend.value) return
    doSend()
  }
}

function handlePrimaryClick() {
  if (props.isGenerating) {
    emit('stop')
    return
  }
  if (!canSend.value) return
  doSend()
}

function doSend() {
  if (uploading.value) return
  const text = props.modelValue.trim()
  const refs = takeReadyAttachments()
  if (!text && !refs.length) return
  emit('send', { text, attachments: refs })
}

function autoGrow(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  emit('update:modelValue', el.value)
}

function openFilePicker() {
  if (uploading.value) return
  fileInputRef.value?.click()
}

async function handleFileChange(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  await uploadFiles(files)
  emit('uploaded')
}
</script>

<template>
  <div class="composer">
    <p v-if="statusText" class="composer__status">{{ statusText }}</p>

    <div class="composer__shell" :class="{ 'composer__shell--with-files': hasAttachments }">
      <input
        ref="fileInputRef"
        type="file"
        multiple
        :accept="ACCEPT_ATTR"
        class="composer__file-input"
        @change="handleFileChange"
      />

      <!-- ChatGPT 风格：刚上传的文件引用卡片 -->
      <ul v-if="hasAttachments" class="composer__attachments" aria-label="已引用附件">
        <li
          v-for="item in attachments"
          :key="item.id"
          class="attach-chip"
          :class="{
            'attach-chip--uploading': item.status === 'uploading',
            'attach-chip--error': item.status === 'error',
            'attach-chip--image': item.isImage,
          }"
        >
          <div class="attach-chip__thumb">
            <img
              v-if="item.isImage && item.previewUrl"
              :src="item.previewUrl"
              :alt="item.filename"
              class="attach-chip__img"
            />
            <span v-else class="attach-chip__icon" aria-hidden="true">
              {{ getFileIcon(item.filename) }}
            </span>
            <div
              v-if="item.status === 'uploading'"
              class="attach-chip__progress"
              :style="{ '--p': `${item.progress}%` }"
            />
          </div>
          <div class="attach-chip__meta">
            <span class="attach-chip__name" :title="item.filename">{{ item.filename }}</span>
            <span class="attach-chip__sub">
              <template v-if="item.status === 'uploading'">上传中 {{ item.progress }}%</template>
              <template v-else-if="item.status === 'error'">失败</template>
              <template v-else>{{ item.fileType }} · 已引用</template>
            </span>
          </div>
          <button
            type="button"
            class="attach-chip__remove"
            :aria-label="`移除 ${item.filename}`"
            @click="removeAttachment(item.id)"
          >
            ×
          </button>
        </li>
      </ul>

      <div class="composer__row">
        <button
          type="button"
          class="composer__attach"
          :disabled="uploading"
          title="上传文档或图片"
          aria-label="上传文档或图片"
          @click="openFilePicker"
        >
          <svg
            class="composer__attach-icon"
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path
              d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"
            />
          </svg>
        </button>
        <textarea
          class="composer__textarea"
          :placeholder="
            hasAttachments
              ? '询问刚上传的文件…（Enter 发送）'
              : '输入消息…（Enter 发送，Shift+Enter 换行）'
          "
          :value="modelValue"
          rows="1"
          :disabled="disabled && !isGenerating"
          @input="autoGrow"
          @keydown="handleKeyDown"
        />
        <button
          type="button"
          class="composer__send"
          :class="{ 'composer__send--stop': isGenerating }"
          :disabled="!isGenerating && !canSend"
          :aria-label="isGenerating ? '停止生成' : '发送'"
          @click="handlePrimaryClick"
        >
          {{ isGenerating ? '停止' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>
