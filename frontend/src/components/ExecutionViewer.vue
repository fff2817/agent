<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
</script>

<template>
  <div class="execution-viewer">
    <header class="execution-viewer__header">
      <h2>Agent 执行过程</h2>
      <p>Thought → Action → Observation → Final Answer</p>
    </header>

    <div class="execution-viewer__body">
      <div v-if="loading" class="execution-viewer__status execution-viewer__status--loading">
        <div class="typing-indicator">
          <span />
          <span />
          <span />
        </div>
        <span>Agent 推理中...</span>
      </div>

      <div v-else-if="!steps.length" class="execution-viewer__empty">
        <p>发送消息后，这里会展示 ReAct 推理链路。</p>
      </div>

      <ol v-else class="execution-viewer__timeline">
        <li
          v-for="step in steps"
          :key="step.step"
          class="execution-viewer__step"
          :class="{ 'execution-viewer__step--final': step.final_answer }"
        >
          <div class="execution-viewer__step-header">
            <span class="execution-viewer__step-num">Step {{ step.step }}</span>
            <span v-if="step.final_answer" class="execution-viewer__step-badge">Final Answer</span>
          </div>

          <div v-if="step.thought" class="execution-viewer__field execution-viewer__field--thought">
            <span class="execution-viewer__field-label">Thought</span>
            <pre class="execution-viewer__field-value">{{ step.thought }}</pre>
          </div>
          <div v-if="step.action" class="execution-viewer__field execution-viewer__field--action">
            <span class="execution-viewer__field-label">Action</span>
            <pre class="execution-viewer__field-value">{{ step.action }}</pre>
          </div>
          <div v-if="step.observation" class="execution-viewer__field execution-viewer__field--observation">
            <span class="execution-viewer__field-label">Observation</span>
            <pre class="execution-viewer__field-value">{{ step.observation }}</pre>
          </div>
          <div v-if="step.final_answer" class="execution-viewer__field execution-viewer__field--final">
            <span class="execution-viewer__field-label">Final Answer</span>
            <pre class="execution-viewer__field-value">{{ step.final_answer }}</pre>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>
