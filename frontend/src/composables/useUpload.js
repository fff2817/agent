import { ref } from 'vue'
import { fetchDocuments, uploadDocument } from '../services/api'
import { getFileTypeLabel, isSupportedFile } from '../utils/fileTypes'
import { useToast } from './useToast'

/**
 * 知识库上传 composable：文件列表、上传进度、校验
 */
export function useUpload() {
  const documents = ref([])
  const loadingList = ref(false)
  const uploadQueue = ref([])
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

  async function uploadFiles(files) {
    const validFiles = files.filter(isSupportedFile)
    if (validFiles.length === 0) {
      showToast('请上传 PDF、DOCX、TXT 或 MD 文件', 'error')
      return
    }

    if (validFiles.length < files.length) {
      showToast('部分文件格式不支持，已跳过', 'error')
    }

    for (const file of validFiles) {
      const item = {
        id: `${Date.now()}-${file.name}`,
        file,
        filename: file.name,
        fileType: getFileTypeLabel(file.name),
        progress: 0,
        status: 'uploading',
        error: '',
      }
      uploadQueue.value.push(item)

      try {
        const result = await uploadDocument(file, (percent) => {
          item.progress = percent
        })
        item.progress = 100
        item.status = 'success'
        showToast(`「${result.filename}」上传成功，新增 ${result.chunksAdded} 个片段`)
        await loadDocuments()
      } catch (err) {
        const detail =
          err.response?.data?.detail ||
          err.message ||
          '上传失败，请确认后端服务是否已启动。'
        item.status = 'error'
        item.error = typeof detail === 'string' ? detail : JSON.stringify(detail)
        showToast(`「${file.name}」上传失败`, 'error')
      }
    }

    setTimeout(() => {
      uploadQueue.value = uploadQueue.value.filter((item) => item.status === 'uploading')
    }, 3000)
  }

  const isUploading = () => uploadQueue.value.some((item) => item.status === 'uploading')

  return {
    documents,
    loadingList,
    uploadQueue,
    loadDocuments,
    uploadFiles,
    isUploading,
  }
}
