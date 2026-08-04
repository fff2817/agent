<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const collapsed = ref(new Set())
const obsExpanded = ref(new Set())

watch(
  () => props.steps.map((s) => s.step).join(','),
  () => {
    // 新步骤默认展开；Observation 默认折叠长文本
  },
)

const isRunning = computed(() => props.loading)

function toggleStep(stepNum) {
  const next = new Set(collapsed.value)
  if (next.has(stepNum)) next.delete(stepNum)
  else next.add(stepNum)
  collapsed.value = next
}

function toggleObs(stepNum) {
  const next = new Set(obsExpanded.value)
  if (next.has(stepNum)) next.delete(stepNum)
  else next.add(stepNum)
  obsExpanded.value = next
}

function isObsLong(text) {
  return (text || '').length > 280
}

function obsPreview(text) {
  if (!text) return ''
  return text.length > 280 ? `${text.slice(0, 280)}…` : text
}

function stepKind(step) {
  if (step.final_answer) return 'final'
  if (step.action && !step.observation) return 'running'
  return 'done'
}
</script>

<template>
  <div class="execution-viewer">
    <div v-if="isRunning && !steps.length" class="execution-viewer__status">
      <div class="typing-indicator" aria-hidden="true">
        <span /><span /><span />
      </div>
      <span>Agent 推理中…</span>
    </div>

    <div v-else-if="!steps.length" class="execution-viewer__empty">
      <p>发送消息后，这里展示 Thought → Action → Observation 推理链路。</p>
    </div>

    <template v-else>
      <div class="execution-viewer__meta">
        <span>{{ steps.length }} 步</span>
        <span v-if="isRunning" class="execution-viewer__live">运行中</span>
        <span v-else class="execution-viewer__done">已完成</span>
      </div>

      <ol class="execution-viewer__timeline">
        <li
          v-for="step in steps"
          :key="step.step"
          class="execution-viewer__step"
          :class="{
            'execution-viewer__step--final': step.final_answer,
            'execution-viewer__step--running': stepKind(step) === 'running',
            'execution-viewer__step--collapsed': collapsed.has(step.step),
          }"
        >
          <button
            type="button"
            class="execution-viewer__step-header"
            @click="toggleStep(step.step)"
          >
            <span class="execution-viewer__step-num">Step {{ step.step }}</span>
            <span v-if="step.final_answer" class="execution-viewer__step-badge">Final</span>
            <span
              v-else-if="stepKind(step) === 'running'"
              class="execution-viewer__step-badge execution-viewer__step-badge--run"
            >
              Running
            </span>
            <span v-else-if="step.action" class="execution-viewer__tool-hint">
              {{ step.action.split('(')[0].trim() }}
            </span>
            <span class="execution-viewer__chevron" aria-hidden="true">
              {{ collapsed.has(step.step) ? '▸' : '▾' }}
            </span>
          </button>

          <div v-if="!collapsed.has(step.step)" class="execution-viewer__fields">
            <div v-if="step.thought" class="execution-viewer__field execution-viewer__field--thought">
              <span class="execution-viewer__field-label">Thought</span>
              <pre class="execution-viewer__field-value">{{ step.thought }}</pre>
            </div>

            <div v-if="step.action" class="execution-viewer__field execution-viewer__field--action">
              <span class="execution-viewer__field-label">Action</span>
              <pre class="execution-viewer__field-value execution-viewer__field-value--mono">{{ step.action }}</pre>
            </div>

            <div
              v-if="step.observation"
              class="execution-viewer__field execution-viewer__field--observation"
            >
              <div class="execution-viewer__field-label-row">
                <span class="execution-viewer__field-label">Observation</span>
                <button
                  v-if="isObsLong(step.observation)"
                  type="button"
                  class="execution-viewer__expand-btn"
                  @click="toggleObs(step.step)"
                >
                  {{ obsExpanded.has(step.step) ? '收起' : '展开' }}
                </button>
              </div>
              <pre class="execution-viewer__field-value">{{
                obsExpanded.has(step.step) || !isObsLong(step.observation)
                  ? step.observation
                  : obsPreview(step.observation)
              }}</pre>
            </div>

            <div
              v-else-if="step.action && isRunning"
              class="execution-viewer__field execution-viewer__field--observation"
            >
              <span class="execution-viewer__field-label">Observation</span>
              <div class="execution-viewer__waiting">
                <div class="typing-indicator"><span /><span /><span /></div>
                <span>等待工具返回…</span>
              </div>
            </div>

            <div
              v-if="step.final_answer"
              class="execution-viewer__field execution-viewer__field--final"
            >
              <span class="execution-viewer__field-label">Final Answer</span>
              <pre class="execution-viewer__field-value">{{ step.final_answer }}</pre>
            </div>
          </div>
        </li>
      </ol>
    </template>
  </div>
</template>
