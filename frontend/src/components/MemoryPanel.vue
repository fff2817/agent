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
</script>

<template>
  <div class="memory-panel">
    <header class="memory-panel__header">
      <h2>🧠 Memory</h2>
      <p>短期会话记忆 + 长期 FAISS 记忆</p>
    </header>

    <div class="memory-panel__body">
      <div v-if="loading" class="memory-panel__status">
        <div class="typing-indicator">
          <span />
          <span />
          <span />
        </div>
        <span>加载记忆中...</span>
      </div>

      <p v-if="error" class="memory-panel__error">{{ error }}</p>

      <template v-if="!loading">
        <section class="memory-panel__section">
          <h3>Short-term Memory</h3>
          <p v-if="!shortTerm.length" class="memory-panel__empty">
            暂无短期记忆，发送消息后开始积累。
          </p>
          <ul v-else class="memory-panel__list">
            <li
              v-for="(item, index) in shortTerm"
              :key="`${index}-${item.slice(0, 24)}`"
              class="memory-panel__item"
            >
              {{ item }}
            </li>
          </ul>
        </section>

        <section class="memory-panel__section">
          <h3>Long-term Memory</h3>
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

        <section class="memory-panel__section">
          <h3>Retrieved Memories</h3>
          <p v-if="retrievalSkipped" class="memory-panel__hint">
            本轮未检索长期记忆{{ skipReason ? `（${skipReason}）` : '' }}
          </p>
          <p v-else-if="!retrieved.length" class="memory-panel__empty">
            发送消息后，这里展示 FAISS 检索命中的记忆。
          </p>
          <ol v-else class="memory-panel__retrieved-list">
            <li v-for="memory in retrieved" :key="`${memory.rank}-${memory.content}`" class="memory-panel__retrieved">
              <div class="memory-panel__retrieved-row">
                <span class="memory-panel__retrieved-label">内容</span>
                <p class="memory-panel__retrieved-value">{{ memory.content }}</p>
              </div>
              <div class="memory-panel__retrieved-row">
                <span class="memory-panel__retrieved-label">相似度</span>
                <span class="memory-panel__score">{{ memory.score.toFixed(2) }}</span>
              </div>
              <div class="memory-panel__retrieved-row">
                <span class="memory-panel__retrieved-label">来源</span>
                <span class="memory-panel__source">{{ memory.source || memory.memory_type }}</span>
              </div>
            </li>
          </ol>
        </section>
      </template>
    </div>
  </div>
</template>
