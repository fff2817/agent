import { ref } from 'vue'
import { deleteDocument, fetchDocuments, uploadDocument } from '../services/api'
import { getFileTypeLabel, isImageFile, isSupportedFile } from '../utils/fileTypes'
import { useToast } from './useToast'

/**
 * 知识库上传 composable：附件引用、上传进度、校验
 */
export function useUpload() {
  const documents = ref([])
  const loadingList = ref(false)
  /** @type {import('vue').Ref<Array>} 当前 Composer 中的附件引用（含上传中/成功/失败） */
  const attachments = ref([])
  const { showToast } = useToast()

  async function loadDocuments() {
    loadingList.value = true
    try {
      documents.value = await fetchDocuments()
    } catch {
      documents.value = []
    } finally {
      loadingList.value = false
    }
  }

  /** 不可变更新，确保 Vue 能追踪到 status/progress 变化（否则发送按钮会卡死） */
  function patchAttachment(id, patch) {
    attachments.value = attachments.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
  }

  function revokePreview(item) {
    if (item?.previewUrl) {
      URL.revokeObjectURL(item.previewUrl)
    }
  }

  function removeAttachment(id) {
    const item = attachments.value.find((a) => a.id === id)
    if (item) revokePreview(item)
    attachments.value = attachments.value.filter((a) => a.id !== id)
  }

  function clearAttachments() {
    for (const item of attachments.value) {
      revokePreview(item)
    }
    attachments.value = []
  }

  function takeReadyAttachments() {
    const ready = attachments.value
      .filter((a) => a.status === 'success')
      .map((a) => ({
        id: a.id,
        filename: a.filename,
        fileType: a.fileType,
        previewUrl: a.previewUrl || '',
        isImage: a.isImage,
        chunksAdded: a.chunksAdded || 0,
      }))

    // 发送后清空 Composer；预览 URL 交由消息气泡持有，此处不再 revoke
    attachments.value = []
    return ready
  }

  async function uploadFiles(files) {
    const validFiles = files.filter(isSupportedFile)
    if (validFiles.length === 0) {
      showToast('请上传 PDF、DOCX、TXT、MD 或图片（PNG/JPG/WEBP/GIF）', 'error')
      return []
    }

    if (validFiles.length < files.length) {
      showToast('部分文件格式不支持，已跳过', 'error')
    }

    const createdIds = []

    for (const file of validFiles) {
      const isImage = isImageFile(file)
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}-${file.name}`
      const item = {
        id,
        filename: file.name,
        fileType: getFileTypeLabel(file.name),
        progress: 0,
        status: 'uploading',
        error: '',
        isImage,
        previewUrl: isImage ? URL.createObjectURL(file) : '',
        chunksAdded: 0,
      }
      attachments.value = [...attachments.value, item]
      createdIds.push(id)

      try {
        const result = await uploadDocument(file, (percent) => {
          patchAttachment(id, { progress: percent })
        })
        patchAttachment(id, {
          progress: 100,
          status: 'success',
          chunksAdded: result.chunksAdded,
          filename: result.filename || file.name,
        })
        showToast(`「${result.filename}」已加入知识库（${result.chunksAdded} 个片段）`)
        await loadDocuments()
      } catch (err) {
        const detail =
          err.response?.data?.detail ||
          err.message ||
          '上传失败，请确认后端服务是否已启动。'
        const errorText = typeof detail === 'string' ? detail : JSON.stringify(detail)
        patchAttachment(id, { status: 'error', error: errorText })
        const short = errorText.length > 80 ? `${errorText.slice(0, 80)}…` : errorText
        showToast(`「${file.name}」上传失败：${short}`, 'error')
      }
    }

    return createdIds
  }

  async function removeDocument(filename) {
    try {
      await deleteDocument(filename)
      documents.value = documents.value.filter((d) => d.filename !== filename)
      showToast(`「${filename}」已从知识库删除`)
      return true
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || '删除失败'
      showToast(typeof detail === 'string' ? detail : JSON.stringify(detail), 'error')
      return false
    }
  }

  const isUploading = () => attachments.value.some((item) => item.status === 'uploading')

  // 兼容旧 UploadPanel：uploadQueue 别名
  const uploadQueue = attachments

  return {
    documents,
    loadingList,
    attachments,
    uploadQueue,
    loadDocuments,
    uploadFiles,
    isUploading,
    removeAttachment,
    clearAttachments,
    takeReadyAttachments,
    removeDocument,
  }
}
