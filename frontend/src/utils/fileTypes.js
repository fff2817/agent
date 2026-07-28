/** 支持的文档扩展名 */
export const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown']

export const ACCEPT_ATTR =
  '.pdf,.docx,.txt,.md,.markdown,application/pdf,' +
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document,' +
  'text/plain,text/markdown'

const EXT_ICON = {
  pdf: '📄',
  docx: '📝',
  txt: '📃',
  markdown: '📃',
  md: '📃',
}

/** 根据文件名或 file_type 返回 emoji 图标 */
export function getFileIcon(filenameOrType) {
  const lower = filenameOrType.toLowerCase()
  if (EXT_ICON[lower]) return EXT_ICON[lower]

  const ext = lower.includes('.') ? lower.slice(lower.lastIndexOf('.')) : ''
  if (ext === '.pdf') return '📄'
  if (ext === '.docx') return '📝'
  if (ext === '.txt') return '📃'
  if (ext === '.md' || ext === '.markdown') return '📃'
  return '📎'
}

/** 根据文件名返回类型标签 */
export function getFileTypeLabel(filename) {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase()
  const map = {
    '.pdf': 'PDF',
    '.docx': 'DOCX',
    '.txt': 'TXT',
    '.md': 'MD',
    '.markdown': 'MD',
  }
  return map[ext] || ext.replace('.', '').toUpperCase()
}

/** 校验文件扩展名是否支持 */
export function isSupportedFile(file) {
  const name = file.name.toLowerCase()
  return SUPPORTED_EXTENSIONS.some((ext) => name.endsWith(ext))
}

/** 格式化文件大小 */
export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
