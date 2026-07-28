import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

/**
 * 全局 Toast 状态（模块级 singleton，无需 provide/inject）
 */
export function useToast() {
  function showToast(message, type = 'success', duration = 3500) {
    const id = ++nextId
    toasts.value = [...toasts.value, { id, message, type }]
    setTimeout(() => removeToast(id), duration)
  }

  function removeToast(id) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return { toasts, showToast, removeToast }
}
