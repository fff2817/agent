<script setup>
defineProps({
  shortTerm: { type: Array, default: () => [] },
  longTerm: { type: Array, default: () => [] },
  retrieved: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  retrievalSkipped: { type: Boolean, default: false },
  skipReason: { type: String, default: '' },
  error: { type: String, default: '' },
})

function scorePercent(score) {
  if (score == null || Number.isNaN(score)) return 0
  return Math.round(Math.min(1, Math.max(0, score)) * 100)
}

function roleFromLine(line) {
  const t = String(line || '')
  if (/^(user|人类|你)[:：]/i.test(t)) return 'user'
  if (/^(assistant|ai|助手)[:：]/i.test(t)) return 'assistant'
  return 'neutral'
}

function stripRolePrefix(line) {
  return String(line || '').replace(/^(user|assistant|人类|你|ai|助手)[:：]\s*/i, '')
}
</script>

<template>
  <div class="memory-panel">
    <div v-if="loading" class="memory-panel__status">
      <div class="typing-indicator" aria-hidden="true">
        <span /><span /><span />
      </div>
      <span>加载记忆中…</span>
    </div>

    <p v-if="error" class="memory-panel__error" role="alert">{{ error }}</p>

    <template v-if="!loading">
      <section class="memory-panel__section memory-panel__section--retrieved">
        <h3 class="memory-panel__heading">
          <span>本轮检索</span>
          <span v-if="retrieved.length" class="memory-panel__count">{{ retrieved.length }}</span>
        </h3>

        <p v-if="retrievalSkipped" class="memory-panel__hint">
          本轮未检索长期记忆{{ skipReason ? `（${skipReason}）` : '' }}
        </p>
        <p v-else-if="!retrieved.length" class="memory-panel__empty">
          发送消息后，这里展示命中的长期记忆。
        </p>
        <ul v-else class="memory-panel__retrieved-list">
          <li
            v-for="memory in retrieved"
            :key="`${memory.rank}-${memory.content}`"
            class="memory-retrieved"
          >
            <p class="memory-retrieved__text">{{ memory.content }}</p>
            <div class="memory-retrieved__bar" aria-hidden="true">
              <i :style="{ width: `${scorePercent(memory.score)}%` }" />
            </div>
            <div class="memory-retrieved__meta">
              <span class="memory-panel__tag">{{ memory.memory_type }}</span>
              <span class="memory-panel__source">{{ memory.source || '—' }}</span>
              <span class="memory-retrieved__score">{{ scorePercent(memory.score) }}%</span>
            </div>
          </li>
        </ul>
      </section>

      <section class="memory-panel__section">
        <h3 class="memory-panel__heading">
          <span>短期记忆</span>
          <span v-if="shortTerm.length" class="memory-panel__count">{{ shortTerm.length }}</span>
        </h3>
        <p v-if="!shortTerm.length" class="memory-panel__empty">
          暂无短期会话记忆，发送消息后开始积累。
        </p>
        <ul v-else class="memory-panel__turns">
          <li
            v-for="(item, index) in shortTerm"
            :key="`${index}-${String(item).slice(0, 24)}`"
            class="memory-turn"
            :class="`memory-turn--${roleFromLine(item)}`"
          >
            <span v-if="roleFromLine(item) !== 'neutral'" class="memory-turn__role">
              {{ roleFromLine(item) === 'user' ? 'User' : 'Assistant' }}
            </span>
            <p class="memory-turn__text">{{ stripRolePrefix(item) }}</p>
          </li>
        </ul>
      </section>

      <section class="memory-panel__section">
        <h3 class="memory-panel__heading">
          <span>长期记忆</span>
          <span v-if="longTerm.length" class="memory-panel__count">{{ longTerm.length }}</span>
        </h3>
        <p v-if="!longTerm.length" class="memory-panel__empty">
          暂无长期记忆，对话中的关键事实会自动入库。
        </p>
        <ul v-else class="memory-panel__list">
          <li
            v-for="memory in longTerm"
            :key="memory.content + memory.created_at"
            class="memory-panel__item memory-panel__item--longterm"
          >
            <p class="memory-panel__item-text">{{ memory.content }}</p>
            <div class="memory-panel__meta">
              <span class="memory-panel__tag">{{ memory.memory_type }}</span>
              <span v-if="memory.source" class="memory-panel__source">{{ memory.source }}</span>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
