<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAuthToken } from '../services/api'
import { useUpload } from '../composables/useUpload'
import { ACCEPT_ATTR, formatFileSize, getFileIcon, getFileTypeLabel } from '../utils/fileTypes'

const emit = defineEmits(['documents-change'])

const inputRef = ref(null)
const { documents, loadingList, uploadQueue, loadDocuments, uploadFiles, isUploading, removeDocument } =
  useUpload()

const uploading = computed(() => isUploading())
const deletingName = ref('')

onMounted(() => {
  if (getAuthToken()) {
    loadDocuments()
  }
})

function handleSelect() {
  inputRef.value?.click()
}

async function handleFileChange(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (files.length === 0) return

  await uploadFiles(files)
  emit('documents-change')
}

async function handleDelete(filename) {
  if (!filename || deletingName.value) return
  if (!window.confirm(`确定从知识库删除「${filename}」？此操作不可恢复。`)) return
  deletingName.value = filename
  try {
    const ok = await removeDocument(filename)
    if (ok) emit('documents-change')
  } finally {
    deletingName.value = ''
  }
}

/** 供父组件在登录/登出后刷新列表 */
async function refresh() {
  if (getAuthToken()) {
    await loadDocuments()
  } else {
    documents.value = []
  }
}

defineExpose({ refresh })
</script>

<template>
  <section class="upload-panel-embed border-b border-gray-200 bg-white px-3 py-3">
    <div class="mb-3">
      <h2 class="text-sm font-semibold text-gray-900">知识库</h2>
      <p class="mt-1 text-xs text-gray-500">
        上传 PDF、DOCX、TXT、MD 或图片（PNG/JPG/WEBP/GIF），供 Agent 检索
      </p>
    </div>

    <input
      ref="inputRef"
      type="file"
      multiple
      :accept="ACCEPT_ATTR"
      class="hidden"
      @change="handleFileChange"
    />

    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
      :disabled="uploading"
      @click="handleSelect"
    >
      <span aria-hidden="true">📁</span>
      {{ uploading ? '上传中...' : '选择文件' }}
    </button>

    <!-- 上传进度 -->
    <ul v-if="uploadQueue.length" class="mt-3 space-y-2">
      <li
        v-for="item in uploadQueue"
        :key="item.id"
        class="rounded-md border border-gray-200 bg-white px-3 py-2 text-xs sm:text-sm"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate">
            {{ getFileIcon(item.filename) }}
            {{ item.filename }}
            <span class="ml-1 text-gray-400">({{ item.fileType }})</span>
          </span>
          <span
            class="shrink-0 text-xs"
            :class="{
              'text-emerald-600': item.status === 'success',
              'text-red-600': item.status === 'error',
              'text-blue-600': item.status === 'uploading',
            }"
          >
            {{
              item.status === 'success'
                ? '完成'
                : item.status === 'error'
                  ? '失败'
                  : `${item.progress}%`
            }}
          </span>
        </div>
        <div
          v-if="item.status === 'uploading'"
          class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-gray-200"
        >
          <div
            class="h-full rounded-full bg-blue-500 transition-all duration-200"
            :style="{ width: `${item.progress}%` }"
          />
        </div>
        <p v-if="item.error" class="mt-1 text-xs text-red-600">{{ item.error }}</p>
      </li>
    </ul>

    <!-- 文件列表 -->
    <div class="mt-4">
      <h3 class="mb-2 text-xs font-medium text-gray-700 sm:text-sm">我的知识库：</h3>

      <p v-if="loadingList" class="text-xs text-gray-400">加载中...</p>

      <p
        v-else-if="!getAuthToken()"
        class="text-xs text-gray-400"
      >
        登录后可查看已上传文档
      </p>

      <p
        v-else-if="documents.length === 0"
        class="text-xs text-gray-400"
      >
        暂无文档，点击「选择文件」上传
      </p>

      <ul v-else class="space-y-1">
        <li
          v-for="doc in documents"
          :key="doc.filename"
          class="flex items-center justify-between gap-2 rounded px-1 py-0.5 text-xs hover:bg-gray-100 sm:text-sm"
        >
          <span class="min-w-0 truncate">
            {{ getFileIcon(doc.fileType || doc.filename) }}
            {{ doc.filename }}
          </span>
          <span class="flex shrink-0 items-center gap-2">
            <span class="text-[10px] text-gray-400 sm:text-xs">
              {{ getFileTypeLabel(doc.filename) }} · {{ formatFileSize(doc.size) }}
            </span>
            <button
              type="button"
              class="rounded px-1.5 py-0.5 text-[10px] text-red-600 hover:bg-red-50 disabled:opacity-50 sm:text-xs"
              :disabled="deletingName === doc.filename"
              :aria-label="`删除 ${doc.filename}`"
              @click="handleDelete(doc.filename)"
            >
              {{ deletingName === doc.filename ? '…' : '删除' }}
            </button>
          </span>
        </li>
      </ul>
    </div>
  </section>
</template>
