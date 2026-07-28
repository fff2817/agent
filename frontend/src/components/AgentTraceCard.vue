<script setup>
import { computed } from 'vue'
import { buildTraceSummary } from '../utils/traceParser'
import TraceRow from './TraceRow.vue'

const props = defineProps({
  trace: { type: Object, default: null },
  answer: { type: String, default: '' },
  answerPending: { type: Boolean, default: false },
})

const summary = computed(() => (props.trace ? buildTraceSummary(props.trace) : null))

const thoughtPending = computed(() => {
  if (!props.trace?.loading || !summary.value) return false
  return !summary.value.thought
})

const ragPending = computed(() => {
  if (!props.trace?.loading) return false
  const steps = props.trace.steps || []
  return steps.some((s) => s.action?.includes('search_docs') && !s.observation)
})

const memoryPending = computed(() => props.trace?.loading && !props.trace?.contextReady)

const toolPending = computed(() => props.trace?.loading && !(props.trace?.steps?.length > 0))
</script>

<template>
  <div v-if="trace" class="agent-trace">
    <header class="agent-trace__header">Agent Trace + Memory + RAG</header>

    <TraceRow
      icon="🧠"
      label="Thought"
      :value="summary?.thought"
      :pending="thoughtPending"
    />
    <TraceRow icon="🔍" label="RAG" :value="summary?.rag" :pending="ragPending" />
    <TraceRow
      icon="💾"
      label="Memory"
      :value="summary?.memory"
      :pending="memoryPending"
    />
    <TraceRow icon="🛠" label="Tool" :value="summary?.tool" :pending="toolPending" />

    <TraceRow
      v-if="answer || answerPending"
      icon="🤖"
      label="Answer"
      :value="answer"
      :pending="answerPending && !answer"
      :streaming="answerPending && !!answer"
    />
  </div>
</template>
