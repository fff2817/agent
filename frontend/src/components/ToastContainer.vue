<script setup>
import { useToast } from '../composables/useToast'

const { toasts, removeToast } = useToast()
</script>

<template>
  <div
    class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(100vw-2rem,22rem)] sm:bottom-6 sm:right-6"
    aria-live="polite"
  >
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="flex items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-lg border"
        :class="
          toast.type === 'success'
            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
            : 'bg-red-50 text-red-800 border-red-200'
        "
      >
        <span class="shrink-0">{{ toast.type === 'success' ? '✓' : '✕' }}</span>
        <p class="flex-1 leading-snug">{{ toast.message }}</p>
        <button
          type="button"
          class="shrink-0 opacity-60 hover:opacity-100"
          aria-label="关闭"
          @click="removeToast(toast.id)"
        >
          ×
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(1rem);
}
</style>
