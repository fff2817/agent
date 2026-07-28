<script setup>
import { onMounted, ref } from 'vue'
import AuthBar from '../components/AuthBar.vue'
import ChatBox from '../components/ChatBox.vue'
import ExecutionViewer from '../components/ExecutionViewer.vue'
import MemoryPanel from '../components/MemoryPanel.vue'
import ToastContainer from '../components/ToastContainer.vue'
import UploadPanel from '../components/UploadPanel.vue'
import RagEvalPanel from '../components/RagEvalPanel.vue'
import { fetchMemoryOverview, getSessionId } from '../services/api'

const steps = ref([])
const executionLoading = ref(false)
const shortTerm = ref([])
const longTerm = ref([])
const retrievedMemories = ref([])
const memoryLoading = ref(false)
const memoryError = ref('')
const memoryRetrievalSkipped = ref(false)
const memorySkipReason = ref('')
const uploadPanelRef = ref(null)

async function refreshMemoryOverview(sessionId = getSessionId()) {
  memoryLoading.value = true
  memoryError.value = ''
  try {
    const overview = await fetchMemoryOverview(sessionId)
    shortTerm.value = overview.shortTerm
    longTerm.value = overview.longTerm
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '无法加载 Memory 数据'
    memoryError.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    memoryLoading.value = false
  }
}

onMounted(() => {
  refreshMemoryOverview()
})

function handleExecutionChange({ steps: newSteps, loading }) {
  steps.value = newSteps
  executionLoading.value = loading
}

function handleMemoryChange({ retrieved, retrievalSkipped, skipReason, sessionId }) {
  if (retrieved) {
    retrievedMemories.value = retrieved
  }
  if (typeof retrievalSkipped === 'boolean') {
    memoryRetrievalSkipped.value = retrievalSkipped
  }
  if (typeof skipReason === 'string') {
    memorySkipReason.value = skipReason
  }
  refreshMemoryOverview(sessionId)
}

function handleNewChat() {
  retrievedMemories.value = []
  memoryRetrievalSkipped.value = false
  memorySkipReason.value = ''
  refreshMemoryOverview(null)
}

function handleAuthChange() {
  retrievedMemories.value = []
  refreshMemoryOverview(null)
  uploadPanelRef.value?.refresh()
}
</script>

<template>
  <div class="chat-page">
    <AuthBar @auth-change="handleAuthChange" />
    <ToastContainer />
    <div class="chat-page__body">
      <div class="chat-page__content">
        <header class="chat-page__header">
          <h1>AI 智能助手</h1>
          <p>ReAct Agent + RAG 文档检索 + 会话记忆</p>
        </header>

        <UploadPanel ref="uploadPanelRef" />
        <RagEvalPanel />

        <main class="chat-page__main">
          <ChatBox
            @execution-change="handleExecutionChange"
            @memory-change="handleMemoryChange"
            @new-chat="handleNewChat"
          />
        </main>
      </div>

      <aside class="chat-page__sidebar" aria-label="Agent 执行与 Memory">
        <MemoryPanel
          :short-term="shortTerm"
          :long-term="longTerm"
          :retrieved="retrievedMemories"
          :loading="memoryLoading"
          :retrieval-skipped="memoryRetrievalSkipped"
          :skip-reason="memorySkipReason"
          :error="memoryError"
        />
        <ExecutionViewer :steps="steps" :loading="executionLoading" />
      </aside>
    </div>
  </div>
</template>
