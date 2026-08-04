<script setup>
import { computed } from 'vue'

const props = defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  loading: { type: Boolean, default: false },
  open: { type: Boolean, default: true },
})

const emit = defineEmits(['select', 'delete', 'toggle'])

const items = computed(() => props.conversations || [])

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function onDelete(event, id) {
  event.stopPropagation()
  emit('delete', id)
}
</script>

<template>
  <aside class="conv-sidebar" :class="{ 'conv-sidebar--collapsed': !open }" aria-label="聊天历史">
    <div class="conv-sidebar__inner">
      <div class="conv-sidebar__header">
        <h2 class="conv-sidebar__heading">历史对话</h2>
      </div>

      <div class="conv-sidebar__list" role="list">
        <p v-if="loading" class="conv-sidebar__hint">加载中…</p>
        <p v-else-if="!items.length" class="conv-sidebar__hint">暂无历史对话</p>

        <button
          v-for="item in items"
          :key="item.conversationId"
          type="button"
          role="listitem"
          class="conv-sidebar__item"
          :class="{ 'conv-sidebar__item--active': item.conversationId === activeId }"
          :title="item.title"
          @click="emit('select', item.conversationId)"
        >
          <span class="conv-sidebar__item-title">{{ item.title || '新对话' }}</span>
          <span class="conv-sidebar__item-meta">
            <span>{{ formatTime(item.updatedAt) }}</span>
            <button
              type="button"
              class="conv-sidebar__delete"
              title="删除对话"
              aria-label="删除对话"
              @click="onDelete($event, item.conversationId)"
            >
              ×
            </button>
          </span>
        </button>
      </div>
    </div>

    <button
      type="button"
      class="conv-sidebar__rail"
      :title="open ? '收起历史' : '展开历史'"
      :aria-expanded="open"
      @click="emit('toggle')"
    >
      {{ open ? '‹' : '›' }}
    </button>
  </aside>
</template>
