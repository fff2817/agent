<script setup>
import { computed, ref, watch } from 'vue'
import CitationPanel from './CitationPanel.vue'
import ExecutionViewer from './ExecutionViewer.vue'
import MemoryPanel from './MemoryPanel.vue'
import UploadPanel from './UploadPanel.vue'
import RagEvalPanel from './RagEvalPanel.vue'
import { extractCitations } from '../utils/traceParser'

const props = defineProps({
  open: { type: Boolean, default: true },
  activeTab: { type: String, default: 'trace' },
  steps: { type: Array, default: () => [] },
  executionLoading: { type: Boolean, default: false },
  citations: { type: Array, default: () => [] },
  citationsPending: { type: Boolean, default: false },
  shortTerm: { type: Array, default: () => [] },
  longTerm: { type: Array, default: () => [] },
  retrieved: { type: Array, default: () => [] },
  memoryLoading: { type: Boolean, default: false },
  memoryRetrievalSkipped: { type: Boolean, default: false },
  memorySkipReason: { type: String, default: '' },
  memoryError: { type: String, default: '' },
  selectedLabel: { type: String, default: '' },
})

const emit = defineEmits(['update:open', 'update:activeTab', 'close'])

const uploadPanelRef = ref(null)
const evalOpen = ref(false)

const tabs = [
  { id: 'trace', label: 'Trace' },
  { id: 'citations', label: 'Citations' },
  { id: 'memory', label: 'Memory' },
  { id: 'knowledge', label: 'Knowledge' },
]

const derivedCitations = computed(() => {
  if (props.citations?.length) return { citations: props.citations, pending: props.citationsPending }
  return extractCitations(props.steps)
})

watch(
  () => props.activeTab,
  (tab) => {
    if (tab === 'knowledge') {
      uploadPanelRef.value?.refresh?.()
    }
  },
)

function setTab(id) {
  emit('update:activeTab', id)
}

function close() {
  emit('update:open', false)
  emit('close')
}

defineExpose({
  refreshUpload: () => uploadPanelRef.value?.refresh?.(),
})
</script>

<template>
  <aside
    class="debug-inspector"
    :class="{ 'debug-inspector--closed': !open }"
    aria-label="Agent 调试面板"
  >
    <header class="debug-inspector__header">
      <div class="debug-inspector__title-row">
        <h2 class="debug-inspector__title">调试面板</h2>
        <button type="button" class="debug-inspector__close" aria-label="关闭调试面板" @click="close">
          ✕
        </button>
      </div>
      <p v-if="selectedLabel" class="debug-inspector__selected">{{ selectedLabel }}</p>

      <nav class="debug-inspector__tabs" aria-label="调试视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="debug-inspector__tab"
          :class="{ 'debug-inspector__tab--active': activeTab === tab.id }"
          @click="setTab(tab.id)"
        >
          {{ tab.label }}
          <span
            v-if="tab.id === 'citations' && derivedCitations.citations.filter((c) => !c.empty).length"
            class="debug-inspector__badge"
          >
            {{ derivedCitations.citations.filter((c) => !c.empty).length }}
          </span>
          <span v-if="tab.id === 'trace' && steps.length" class="debug-inspector__badge">
            {{ steps.length }}
          </span>
        </button>
      </nav>
    </header>

    <div class="debug-inspector__body">
      <div v-show="activeTab === 'trace'" class="debug-inspector__pane debug-inspector__pane--trace">
        <ExecutionViewer :steps="steps" :loading="executionLoading" />
      </div>

      <div v-show="activeTab === 'citations'" class="debug-inspector__pane">
        <CitationPanel
          :citations="derivedCitations.citations"
          :pending="derivedCitations.pending || citationsPending"
        />
      </div>

      <div v-show="activeTab === 'memory'" class="debug-inspector__pane">
        <MemoryPanel
          :short-term="shortTerm"
          :long-term="longTerm"
          :retrieved="retrieved"
          :loading="memoryLoading"
          :retrieval-skipped="memoryRetrievalSkipped"
          :skip-reason="memorySkipReason"
          :error="memoryError"
        />
      </div>

      <div v-show="activeTab === 'knowledge'" class="debug-inspector__pane debug-inspector__pane--kb">
        <UploadPanel ref="uploadPanelRef" />
        <div class="debug-inspector__eval">
          <button
            type="button"
            class="debug-inspector__eval-toggle"
            @click="evalOpen = !evalOpen"
          >
            {{ evalOpen ? '收起' : '展开' }} RAG 问答评估
          </button>
          <RagEvalPanel v-if="evalOpen" />
        </div>
      </div>
    </div>
  </aside>
</template>
