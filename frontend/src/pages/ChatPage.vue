<script setup>
import { computed, onMounted, ref } from 'vue'
import ChatBox from '../components/ChatBox.vue'
import ConversationSidebar from '../components/ConversationSidebar.vue'
import DebugInspector from '../components/DebugInspector.vue'
import ToastContainer from '../components/ToastContainer.vue'
import TopBar from '../components/TopBar.vue'
import {
  deleteConversationAPI,
  fetchConversation,
  fetchConversations,
  fetchMemoryOverview,
  getSessionId,
} from '../services/api'
import { extractCitations } from '../utils/traceParser'

const steps = ref([])
const executionLoading = ref(false)
const citations = ref([])
const citationsPending = ref(false)
const shortTerm = ref([])
const longTerm = ref([])
const retrievedMemories = ref([])
const memoryLoading = ref(false)
const memoryError = ref('')
const memoryRetrievalSkipped = ref(false)
const memorySkipReason = ref('')

const sessionId = ref(getSessionId())
const chatBoxRef = ref(null)
const inspectorRef = ref(null)
const activeTab = ref('trace')
const selectedMessageId = ref(null)

const conversations = ref([])
const conversationsLoading = ref(false)
const conversationsError = ref('')

const DESKTOP_MQ = '(min-width: 1100px)'
const inspectorOpen = ref(
  typeof window !== 'undefined' ? window.matchMedia(DESKTOP_MQ).matches : true,
)
const sidebarOpen = ref(
  typeof window !== 'undefined' ? window.matchMedia('(min-width: 900px)').matches : true,
)

onMounted(async () => {
  await refreshConversations()
  refreshMemoryOverview()
  if (sessionId.value) {
    try {
      // 等 ChatBox 挂载完成再恢复
      await restoreConversation(sessionId.value, { silent: true })
    } catch {
      /* 旧 session 可能尚无 conversation 记录，忽略 */
    }
  }
})

const selectedLabel = computed(() => {
  if (!selectedMessageId.value) return '当前对话'
  return `消息 #${selectedMessageId.value}`
})

async function refreshConversations() {
  conversationsLoading.value = true
  conversationsError.value = ''
  try {
    conversations.value = await fetchConversations()
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '无法加载聊天历史'
    conversationsError.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    conversationsLoading.value = false
  }
}

async function refreshMemoryOverview(sid = getSessionId()) {
  memoryLoading.value = true
  memoryError.value = ''
  try {
    const overview = await fetchMemoryOverview(sid)
    shortTerm.value = overview.shortTerm
    longTerm.value = overview.longTerm
    if (overview.sessionId) {
      sessionId.value = overview.sessionId
    }
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '无法加载 Memory 数据'
    memoryError.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    memoryLoading.value = false
  }
}

function handleExecutionChange({
  steps: newSteps,
  loading,
  citations: nextCitations,
  citationsPending: pending,
  messageId,
}) {
  steps.value = newSteps || []
  executionLoading.value = loading
  if (nextCitations) {
    citations.value = nextCitations
  } else {
    const extracted = extractCitations(newSteps || [])
    citations.value = extracted.citations
    citationsPending.value = extracted.pending
  }
  if (typeof pending === 'boolean') {
    citationsPending.value = pending
  }
  if (messageId != null) {
    selectedMessageId.value = messageId
  }
}

function handleMemoryChange({
  retrieved,
  retrievalSkipped,
  skipReason,
  sessionId: sid,
  skipRefresh,
}) {
  if (retrieved) {
    retrievedMemories.value = retrieved
  }
  if (typeof retrievalSkipped === 'boolean') {
    memoryRetrievalSkipped.value = retrievalSkipped
  }
  if (typeof skipReason === 'string') {
    memorySkipReason.value = skipReason
  }
  if (!skipRefresh) {
    refreshMemoryOverview(sid)
  }
}

function resetInspectorState() {
  retrievedMemories.value = []
  memoryRetrievalSkipped.value = false
  memorySkipReason.value = ''
  steps.value = []
  citations.value = []
  citationsPending.value = false
  selectedMessageId.value = null
  sessionId.value = null
  executionLoading.value = false
}

function handleNewChat() {
  // 当前对话已在每轮结束后持久化；此处只清空 UI，开启新 conversation
  resetInspectorState()
  refreshMemoryOverview(null)
}

function handleTopNewChat() {
  chatBoxRef.value?.handleNewChat?.()
}

async function handleAuthChange() {
  retrievedMemories.value = []
  await refreshConversations()
  refreshMemoryOverview(null)
  inspectorRef.value?.refreshUpload?.()
}

function handleSelectInspect({ messageId, tab }) {
  selectedMessageId.value = messageId
  if (tab) activeTab.value = tab
  inspectorOpen.value = true
}

function handleSessionChange(id) {
  sessionId.value = id
}

async function handleConversationUpdated() {
  await refreshConversations()
}

async function restoreConversation(id, { silent = false } = {}) {
  if (!id) return
  try {
    const detail = await fetchConversation(id)
    // ChatBox 可能尚未就绪（首屏）
    let tries = 0
    while (!chatBoxRef.value?.loadConversation && tries < 20) {
      await new Promise((r) => setTimeout(r, 25))
      tries += 1
    }
    chatBoxRef.value?.loadConversation?.(detail)
    sessionId.value = detail.conversationId
    if (!silent && typeof window !== 'undefined' && window.matchMedia('(max-width: 899px)').matches) {
      sidebarOpen.value = false
    }
  } catch (err) {
    if (silent) throw err
    const detail = err.response?.data?.detail || err.message || '无法打开对话'
    conversationsError.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
}

async function handleDeleteConversation(id) {
  if (!id) return
  if (typeof window !== 'undefined' && !window.confirm('确定删除该对话？此操作不可撤销。')) {
    return
  }
  try {
    await deleteConversationAPI(id)
    if (sessionId.value === id) {
      chatBoxRef.value?.handleNewChat?.()
    }
    await refreshConversations()
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '删除失败'
    conversationsError.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
}

function toggleInspector() {
  inspectorOpen.value = !inspectorOpen.value
}

function closeInspector() {
  inspectorOpen.value = false
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}
</script>

<template>
  <div
    class="chat-page"
    :class="{
      'chat-page--inspector-open': inspectorOpen,
      'chat-page--sidebar-open': sidebarOpen,
    }"
  >
    <TopBar
      :inspector-open="inspectorOpen"
      @auth-change="handleAuthChange"
      @new-chat="handleTopNewChat"
      @toggle-inspector="toggleInspector"
    />
    <ToastContainer />

    <div class="chat-page__body">
      <ConversationSidebar
        :conversations="conversations"
        :active-id="sessionId"
        :loading="conversationsLoading"
        :open="sidebarOpen"
        @select="restoreConversation"
        @delete="handleDeleteConversation"
        @toggle="toggleSidebar"
      />

      <main class="chat-page__main">
        <p v-if="conversationsError" class="chat-page__banner">{{ conversationsError }}</p>
        <ChatBox
          ref="chatBoxRef"
          @execution-change="handleExecutionChange"
          @memory-change="handleMemoryChange"
          @new-chat="handleNewChat"
          @select-inspect="handleSelectInspect"
          @session-change="handleSessionChange"
          @conversation-updated="handleConversationUpdated"
          @uploaded="inspectorRef?.refreshUpload?.()"
        />
      </main>

      <div
        v-if="inspectorOpen"
        class="chat-page__inspector-backdrop"
        aria-hidden="true"
        @click="closeInspector"
      />

      <DebugInspector
        ref="inspectorRef"
        v-model:open="inspectorOpen"
        v-model:active-tab="activeTab"
        :steps="steps"
        :execution-loading="executionLoading"
        :citations="citations"
        :citations-pending="citationsPending"
        :short-term="shortTerm"
        :long-term="longTerm"
        :retrieved="retrievedMemories"
        :memory-loading="memoryLoading"
        :memory-retrieval-skipped="memoryRetrievalSkipped"
        :memory-skip-reason="memorySkipReason"
        :memory-error="memoryError"
        :selected-label="selectedLabel"
        @close="closeInspector"
      />
    </div>
  </div>
</template>
