<script setup>
import { computed, ref, watch } from 'vue'
import AgentTraceCard from './AgentTraceCard.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const bottomRef = ref(null)

watch(
  () => [props.messages, props.loading, props.error],
  () => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  },
  { deep: true },
)

const showLoadingBubble = computed(() => {
  return props.loading && props.messages[props.messages.length - 1]?.role !== 'assistant'
})
</script>

<template>
  <div class="message-list">
    <div v-if="messages.length === 0 && !loading" class="message-list__empty">
      <p>输入问题开始对话。</p>
    </div>

    <template v-for="msg in messages" :key="msg.id">
      <!-- 用户消息 -->
      <div v-if="msg.role === 'user'" class="message-row message-row--user">
        <div class="message-bubble message-bubble--user">
          <span class="message-role">你</span>
          <p class="message-content">{{ msg.content }}</p>
        </div>
      </div>

      <!-- 助手：带 Trace 卡片 -->
      <div v-else-if="msg.trace" class="message-row message-row--assistant">
        <div class="message-bubble message-bubble--assistant message-bubble--trace">
          <span class="message-role">助手</span>
          <AgentTraceCard
            :trace="msg.trace"
            :answer="msg.content"
            :answer-pending="msg.trace.loading"
          />
        </div>
      </div>

      <!-- 助手：无内容 loading -->
      <div v-else-if="!msg.content" class="message-row message-row--assistant">
        <div class="message-bubble message-bubble--assistant message-bubble--loading">
          <span class="message-role">助手</span>
          <div class="typing-indicator">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>

      <!-- 助手：普通文本 -->
      <div v-else class="message-row message-row--assistant">
        <div class="message-bubble message-bubble--assistant">
          <span class="message-role">助手</span>
          <p class="message-content">{{ msg.content }}</p>
        </div>
      </div>
    </template>

    <div v-if="showLoadingBubble" class="message-row message-row--assistant">
      <div class="message-bubble message-bubble--assistant message-bubble--loading">
        <span class="message-role">助手</span>
        <div class="typing-indicator">
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>

    <div v-if="error" class="message-list__error" role="alert">
      {{ error }}
    </div>

    <div ref="bottomRef" />
  </div>
</template>
