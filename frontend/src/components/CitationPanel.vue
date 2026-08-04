<script setup>
import { ref } from 'vue'

defineProps({
  citations: { type: Array, default: () => [] },
  pending: { type: Boolean, default: false },
  emptyHint: {
    type: String,
    default: '发送消息并触发文档检索后，这里会显示引用来源。',
  },
})

const expanded = ref(new Set())

function toggle(key) {
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

function citationKey(c, index) {
  return `${c.rank}-${c.source}-${c.page ?? 'x'}-${index}`
}

function scorePercent(score) {
  if (score == null || Number.isNaN(score)) return null
  return Math.round(Math.min(1, Math.max(0, score)) * 100)
}
</script>

<template>
  <div class="citation-panel">
    <div v-if="pending" class="citation-panel__pending">
      <div class="typing-indicator" aria-hidden="true">
        <span /><span /><span />
      </div>
      <span>正在检索文档…</span>
    </div>

    <p v-else-if="!citations.length" class="citation-panel__empty">{{ emptyHint }}</p>

    <ul v-else class="citation-panel__list">
      <li
        v-for="(c, index) in citations"
        :key="citationKey(c, index)"
        class="citation-card"
        :class="{ 'citation-card--empty': c.empty }"
      >
        <button
          type="button"
          class="citation-card__head"
          :disabled="c.empty || !c.snippet"
          @click="toggle(citationKey(c, index))"
        >
          <span class="citation-card__rank">[{{ c.rank || index + 1 }}]</span>
          <span class="citation-card__title">
            {{ c.source }}
            <template v-if="c.page != null"> · p.{{ c.page }}</template>
          </span>
          <span v-if="scorePercent(c.score) != null" class="citation-card__score">
            {{ scorePercent(c.score) }}%
          </span>
          <span
            v-if="c.snippet && !c.empty"
            class="citation-card__chevron"
            aria-hidden="true"
          >
            {{ expanded.has(citationKey(c, index)) ? '▾' : '▸' }}
          </span>
        </button>

        <div
          v-if="scorePercent(c.score) != null && !c.empty"
          class="citation-card__bar"
          aria-hidden="true"
        >
          <i :style="{ width: `${scorePercent(c.score)}%` }" />
        </div>

        <p
          v-if="c.snippet && (expanded.has(citationKey(c, index)) || c.empty)"
          class="citation-card__snippet"
        >
          {{ c.snippet }}
        </p>
        <p
          v-else-if="c.snippet && !expanded.has(citationKey(c, index))"
          class="citation-card__snippet citation-card__snippet--preview"
        >
          {{ c.snippet.slice(0, 120) }}{{ c.snippet.length > 120 ? '…' : '' }}
        </p>
      </li>
    </ul>
  </div>
</template>
