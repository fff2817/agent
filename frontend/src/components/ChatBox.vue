<script setup>
import { computed, ref } from 'vue'
import { chatStreamAPI, clearSessionId, getSessionId, setSessionId } from '../services/api'
import { createEmptyTrace, deriveStreamStatus, extractCitations } from '../utils/traceParser'
import InputBox from './InputBox.vue'
import MessageList from './MessageList.vue'

const emit = defineEmits([
  'execution-change',
  'memory-change',
  'new-chat',
  'select-inspect',
  'session-change',
  'conversation-updated',
  'uploaded',
])

let messageId = 0
function createMessage(role, content, { id = null, trace = null, attachments = [] } = {}) {
  messageId += 1
  return { id: id || `local-${messageId}`, role, content, trace, attachments }
}

const messages = ref([])
const input = ref('')
const loading = ref(false)
const error = ref('')
const sessionId = ref(getSessionId())
const abortControllerRef = ref(null)
const selectedMessageId = ref(null)

const statusText = computed(() => {
  if (!loading.value) return ''
  const last = [...messages.value].reverse().find((m) => m.role === 'assistant')
  return deriveStreamStatus(last?.trace) || '正在生成…'
})

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

function publishExecution(steps, isLoading, messageIdForSelect = null) {
  const { citations, pending } = extractCitations(steps)
  emit('execution-change', {
    steps,
    loading: isLoading,
    citations,
    citationsPending: pending,
    messageId: messageIdForSelect,
  })
}

function handleStop() {
  abortControllerRef.value?.abort()
}

function handleSuggest(text) {
  input.value = text
}

function handleSelectInspect(payload) {
  selectedMessageId.value = payload.messageId
  const msg = messages.value.find((m) => m.id === payload.messageId)
  if (msg?.trace) {
    publishExecution(msg.trace.steps || [], Boolean(msg.trace.loading), msg.id)
    emit('memory-change', {
      retrieved: msg.trace.retrievedMemories || [],
      retrievalSkipped: Boolean(msg.trace.memoryRetrievalSkipped),
      skipReason: msg.trace.memorySkipReason || '',
      sessionId: sessionId.value,
      skipRefresh: true,
    })
  }
  emit('select-inspect', payload)
}

function applySessionId(id) {
  if (!id) return
  setSessionId(id)
  sessionId.value = id
  emit('session-change', id)
}

async function handleSend(payload = {}) {
  const text = typeof payload === 'string' ? payload.trim() : (payload.text || '').trim()
  const refs = typeof payload === 'object' && payload ? payload.attachments || [] : []
  if (loading.value) return
  if (!text && !refs.length) return

  abortControllerRef.value?.abort()
  const abortController = new AbortController()
  abortControllerRef.value = abortController

  const displayContent = text || '请结合我刚上传的附件回答'
  const apiMessage = refs.length
    ? `${displayContent}\n\n请优先使用 search_docs 检索这些刚上传的文件：${refs.map((r) => r.filename).join('、')}`
    : displayContent

  const userMessage = createMessage('user', displayContent, { attachments: refs })
  const assistantMessage = createMessage('assistant', '', { trace: createEmptyTrace(true) })
  const assistantId = assistantMessage.id

  input.value = ''
  error.value = ''
  messages.value = [...messages.value, userMessage, assistantMessage]
  loading.value = true
  selectedMessageId.value = assistantId
  publishExecution([], true, assistantId)
  emit('select-inspect', { messageId: assistantId, tab: 'trace' })

  let streamedSteps = []
  let receivedTokens = false

  try {
    await chatStreamAPI(apiMessage, sessionId.value, {
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
          emit('memory-change', {
            retrieved: event.retrieved_memories || [],
            retrievalSkipped: Boolean(event.memory_retrieval_skipped),
            skipReason: event.memory_skip_reason || '',
            sessionId: sessionId.value,
            skipRefresh: true,
          })
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
          if (selectedMessageId.value === assistantId) {
            publishExecution(streamedSteps, true, assistantId)
          }
        }

        if (event.type === 'done') {
          const cid = event.conversation_id || event.session_id
          if (cid) applySessionId(cid)
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
          if (selectedMessageId.value === assistantId) {
            publishExecution(streamedSteps, false, assistantId)
          }
          emit('memory-change', {
            retrieved: event.retrieved_memories || [],
            retrievalSkipped: Boolean(event.memory_retrieval_skipped),
            skipReason: event.memory_skip_reason || '',
            sessionId: cid,
          })
          emit('conversation-updated', cid)
        }

        if (event.type === 'cancelled') {
          const cid = event.conversation_id || event.session_id
          if (cid) applySessionId(cid)
          updateAssistantTrace(assistantId, (prev) => ({
            ...prev,
            steps: streamedSteps,
            loading: false,
          }))
          if (selectedMessageId.value === assistantId) {
            publishExecution(streamedSteps, false, assistantId)
          }
          emit('conversation-updated', cid)
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
      publishExecution(streamedSteps, false, assistantId)
      updateAssistantTrace(assistantId, (prev) => (prev ? { ...prev, loading: false } : prev))
    } else {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        '无法连接服务器，请确认后端是否已启动。'
      error.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
      publishExecution(streamedSteps, false, assistantId)
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
  selectedMessageId.value = null
  publishExecution([], false, null)
  emit('session-change', null)
  emit('new-chat')
}

/**
 * 从后端 Conversation 详情恢复消息列表与 session。
 */
function loadConversation(detail) {
  abortControllerRef.value?.abort()
  abortControllerRef.value = null
  loading.value = false
  error.value = ''
  selectedMessageId.value = null

  const cid = detail?.conversationId || null
  if (cid) {
    setSessionId(cid)
    sessionId.value = cid
    emit('session-change', cid)
  } else {
    clearSessionId()
    sessionId.value = null
    emit('session-change', null)
  }

  const restored = (detail?.messages || []).map((m) => {
    const meta = m.meta || {}
    const isAssistant = m.role === 'assistant'
    return createMessage(m.role, m.content || '', {
      id: m.id,
      attachments: meta.attachments || [],
      trace: isAssistant
        ? {
            steps: meta.steps || [],
            retrievedMemories: meta.retrieved_memories || [],
            memoryRetrievalSkipped: Boolean(meta.memory_retrieval_skipped),
            memorySkipReason: meta.memory_skip_reason || '',
            contextReady: true,
            loading: false,
          }
        : null,
    })
  })
  messages.value = restored

  const lastAssistant = [...restored].reverse().find((m) => m.role === 'assistant')
  if (lastAssistant?.trace) {
    selectedMessageId.value = lastAssistant.id
    publishExecution(lastAssistant.trace.steps || [], false, lastAssistant.id)
    emit('memory-change', {
      retrieved: lastAssistant.trace.retrievedMemories || [],
      retrievalSkipped: Boolean(lastAssistant.trace.memoryRetrievalSkipped),
      skipReason: lastAssistant.trace.memorySkipReason || '',
      sessionId: cid,
    })
  } else {
    publishExecution([], false, null)
    emit('memory-change', {
      retrieved: [],
      retrievalSkipped: false,
      skipReason: '',
      sessionId: cid,
    })
  }
}

defineExpose({ handleNewChat, loadConversation, sessionId, selectedMessageId, messages })
</script>

<template>
  <div class="chat-box">
    <MessageList
      :messages="messages"
      :loading="loading"
      :error="error"
      :selected-message-id="selectedMessageId"
      @select-inspect="handleSelectInspect"
      @suggest="handleSuggest"
    />

    <div class="chat-box__composer">
      <InputBox
        v-model="input"
        :is-generating="loading"
        :disabled="loading"
        :status-text="statusText"
        @send="handleSend"
        @stop="handleStop"
        @uploaded="emit('uploaded')"
      />
    </div>
  </div>
</template>
