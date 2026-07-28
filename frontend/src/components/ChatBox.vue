<script setup>
import { ref } from 'vue'
import { chatStreamAPI, clearSessionId, getSessionId, setSessionId } from '../services/api'
import { createEmptyTrace } from '../utils/traceParser'
import InputBox from './InputBox.vue'
import MessageList from './MessageList.vue'

const emit = defineEmits(['execution-change', 'memory-change', 'new-chat'])

let messageId = 0
function createMessage(role, content, trace = null) {
  messageId += 1
  return { id: messageId, role, content, trace }
}

const messages = ref([])
const input = ref('')
const loading = ref(false)
const error = ref('')
const sessionId = ref(getSessionId())
const abortControllerRef = ref(null)

function updateAssistantMessage(assistantId, updater) {
  messages.value = messages.value.map((msg) => {
    if (msg.id !== assistantId) return msg
    const nextContent = typeof updater === 'function' ? updater(msg.content) : updater
    return { ...msg, content: nextContent }
  })
}

function updateAssistantTrace(assistantId, updater) {
  messages.value = messages.value.map((msg) => {
    if (msg.id !== assistantId) return msg
    const nextTrace = typeof updater === 'function' ? updater(msg.trace) : updater
    return { ...msg, trace: nextTrace }
  })
}

function handleStop() {
  abortControllerRef.value?.abort()
}

async function handleSend() {
  const text = input.value.trim()
  if (!text || loading.value) return

  abortControllerRef.value?.abort()
  const abortController = new AbortController()
  abortControllerRef.value = abortController

  const userMessage = createMessage('user', text)
  const assistantMessage = createMessage('assistant', '', createEmptyTrace(true))
  const assistantId = assistantMessage.id

  input.value = ''
  error.value = ''
  messages.value = [...messages.value, userMessage, assistantMessage]
  loading.value = true
  emit('execution-change', { steps: [], loading: true })

  let streamedSteps = []
  let receivedTokens = false

  try {
    await chatStreamAPI(text, sessionId.value, {
      signal: abortController.signal,
      onEvent: (event) => {
        if (event.type === 'context') {
          updateAssistantTrace(assistantId, (prev) => ({
            ...prev,
            retrievedMemories: event.retrieved_memories || [],
            memoryRetrievalSkipped: Boolean(event.memory_retrieval_skipped),
            memorySkipReason: event.memory_skip_reason || '',
            contextReady: true,
          }))
        }

        if (event.type === 'token') {
          receivedTokens = true
          updateAssistantMessage(assistantId, (prev) => prev + event.content)
        }

        if (event.type === 'step') {
          streamedSteps = [
            ...streamedSteps.filter((s) => s.step !== event.step.step),
            event.step,
          ]
          updateAssistantTrace(assistantId, (prev) => ({
            ...prev,
            steps: streamedSteps,
          }))
          emit('execution-change', { steps: streamedSteps, loading: true })
        }

        if (event.type === 'done') {
          if (event.session_id) {
            setSessionId(event.session_id)
            sessionId.value = event.session_id
          }
          if (event.response) {
            updateAssistantMessage(assistantId, event.response)
          }
          streamedSteps = event.steps || streamedSteps
          updateAssistantTrace(assistantId, (prev) => ({
            ...prev,
            steps: streamedSteps,
            retrievedMemories: event.retrieved_memories || prev?.retrievedMemories || [],
            memoryRetrievalSkipped: Boolean(event.memory_retrieval_skipped),
            memorySkipReason: event.memory_skip_reason || '',
            contextReady: true,
            loading: false,
          }))
          emit('execution-change', { steps: streamedSteps, loading: false })
          emit('memory-change', {
            retrieved: event.retrieved_memories || [],
            retrievalSkipped: Boolean(event.memory_retrieval_skipped),
            skipReason: event.memory_skip_reason || '',
            sessionId: event.session_id,
          })
        }

        if (event.type === 'cancelled') {
          if (event.session_id) {
            setSessionId(event.session_id)
            sessionId.value = event.session_id
          }
          updateAssistantTrace(assistantId, (prev) => ({
            ...prev,
            steps: streamedSteps,
            loading: false,
          }))
          emit('execution-change', { steps: streamedSteps, loading: false })
        }

        if (event.type === 'error') {
          throw new Error(event.detail || '生成失败，请稍后重试。')
        }
      },
    })
  } catch (err) {
    if (err.name === 'AbortError') {
      if (!receivedTokens) {
        messages.value = messages.value.filter((msg) => msg.id !== assistantId)
      }
      emit('execution-change', { steps: streamedSteps, loading: false })
      updateAssistantTrace(assistantId, (prev) => (prev ? { ...prev, loading: false } : prev))
    } else {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        '无法连接服务器，请确认后端是否已启动。'
      error.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
      emit('execution-change', { steps: streamedSteps, loading: false })
      updateAssistantTrace(assistantId, (prev) => (prev ? { ...prev, loading: false } : prev))

      if (!receivedTokens) {
        messages.value = messages.value.filter((msg) => msg.id !== assistantId)
      }
    }
  } finally {
    if (abortControllerRef.value === abortController) {
      abortControllerRef.value = null
    }
    loading.value = false
  }
}

function handleNewChat() {
  abortControllerRef.value?.abort()
  abortControllerRef.value = null
  clearSessionId()
  sessionId.value = null
  messages.value = []
  error.value = ''
  loading.value = false
  emit('execution-change', { steps: [], loading: false })
  emit('new-chat')
}
</script>

<template>
  <div class="chat-box">
    <div class="chat-box__toolbar">
      <button type="button" class="chat-box__new-btn" @click="handleNewChat">
        新对话
      </button>
      <span v-if="sessionId" class="chat-box__session" :title="sessionId">
        会话：{{ sessionId.slice(0, 8) }}...
      </span>
    </div>

    <MessageList :messages="messages" :loading="loading" :error="error" />

    <InputBox
      v-model="input"
      :is-generating="loading"
      :disabled="loading"
      @send="handleSend"
      @stop="handleStop"
    />
  </div>
</template>
