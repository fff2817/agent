<script setup>
import { computed, ref, watch } from 'vue'
import { deriveStreamStatus, extractCitations } from '../utils/traceParser'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  selectedMessageId: { type: [Number, String], default: null },
})

const emit = defineEmits(['select-inspect', 'suggest'])

const bottomRef = ref(null)

const SUGGESTIONS = [
  '总结一下知识库里关于报销流程的要点',
  '我上次提到的偏好是什么？',
  '帮我用计算器算一下 128 * 36',
  '搜索文档中与入职相关的内容',
]

watch(
  () => [props.messages, props.loading, props.error],
  () => {
    requestAnimationFrame(() => {
      bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
    })
  },
  { deep: true },
)

function citationCount(msg) {
  const { citations } = extractCitations(msg.trace?.steps || [])
  return citations.filter((c) => !c.empty).length
}

function stepCount(msg) {
  return msg.trace?.steps?.length || 0
}

function memoryCount(msg) {
  return msg.trace?.retrievedMemories?.length || 0
}

function streamStatus(msg) {
  if (!msg.trace?.loading) return ''
  return deriveStreamStatus(msg.trace)
}

function inspect(msg, tab) {
  emit('select-inspect', { messageId: msg.id, tab })
}

const isEmpty = computed(() => props.messages.length === 0 && !props.loading)
</script>

<template>
  <div class="message-list">
    <div v-if="isEmpty" class="message-list__empty">
      <h2 class="message-list__welcome">有什么可以帮你？</h2>
      <p class="message-list__welcome-sub">
        支持文档检索、工具调用与跨会话记忆的企业级 Agent 助手
      </p>
      <div class="message-list__suggestions">
        <button
          v-for="s in SUGGESTIONS"
          :key="s"
          type="button"
          class="message-list__chip"
          @click="emit('suggest', s)"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <template v-for="msg in messages" :key="msg.id">
      <div
        v-if="msg.role === 'user'"
        class="message-row message-row--user"
      >
        <div class="message-bubble message-bubble--user">
          <ul
            v-if="msg.attachments?.length"
            class="message-attachments"
            aria-label="引用附件"
          >
            <li
              v-for="att in msg.attachments"
              :key="att.id"
              class="message-attach"
              :class="{ 'message-attach--image': att.isImage }"
            >
              <img
                v-if="att.isImage && att.previewUrl"
                :src="att.previewUrl"
                :alt="att.filename"
                class="message-attach__img"
              />
              <span v-else class="message-attach__icon" aria-hidden="true">📎</span>
              <span class="message-attach__name" :title="att.filename">{{ att.filename }}</span>
            </li>
          </ul>
          <p v-if="msg.content" class="message-content">{{ msg.content }}</p>
        </div>
      </div>

      <div
        v-else
        class="message-row message-row--assistant"
        :class="{ 'message-row--selected': selectedMessageId === msg.id }"
      >
        <div class="message-bubble message-bubble--assistant">
          <div class="message-assistant__meta">
            <span class="message-role">助手</span>
            <span v-if="streamStatus(msg)" class="message-stream-status">
              {{ streamStatus(msg) }}
            </span>
          </div>

          <div v-if="!msg.content && msg.trace?.loading" class="typing-indicator message-typing">
            <span /><span /><span />
          </div>
          <p v-else-if="msg.content" class="message-content">{{ msg.content }}</p>
          <p v-else-if="!msg.trace?.loading" class="message-content message-content--muted">
            （无回复内容）
          </p>

          <div
            v-if="msg.trace && (stepCount(msg) || citationCount(msg) || memoryCount(msg) || !msg.trace.loading)"
            class="message-actions"
          >
            <button
              type="button"
              class="message-action"
              :disabled="!stepCount(msg) && msg.trace.loading"
              @click="inspect(msg, 'trace')"
            >
              推理步骤{{ stepCount(msg) ? ` · ${stepCount(msg)}` : '' }}
            </button>
            <button
              type="button"
              class="message-action"
              :disabled="!citationCount(msg)"
              @click="inspect(msg, 'citations')"
            >
              引用来源{{ citationCount(msg) ? ` · ${citationCount(msg)}` : '' }}
            </button>
            <button
              type="button"
              class="message-action"
              @click="inspect(msg, 'memory')"
            >
              本轮记忆{{ memoryCount(msg) ? ` · ${memoryCount(msg)}` : '' }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <div v-if="error" class="message-list__error" role="alert">
      {{ error }}
    </div>

    <div ref="bottomRef" />
  </div>
</template>
