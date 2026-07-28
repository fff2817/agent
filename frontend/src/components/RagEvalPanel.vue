<script setup>
import { computed, ref } from 'vue'
import { fetchRagEvaluation, ragAskAPI } from '../services/api'

const question = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)

const overallPercent = computed(() => {
  const score = result.value?.evaluation?.answer?.overall_score
  return score != null ? Math.round(score * 100) : null
})

const verdictLabel = computed(() => {
  const v = result.value?.evaluation?.answer?.verdict
  if (v === 'good') return '良好'
  if (v === 'poor') return '较差'
  return '一般'
})

function labelClass(label) {
  if (label === 'high') return 'rag-eval__label--high'
  if (label === 'medium') return 'rag-eval__label--medium'
  if (label === 'low') return 'rag-eval__label--low'
  return 'rag-eval__label--irrelevant'
}

function scoreBarWidth(score) {
  return `${Math.round(Math.min(1, Math.max(0, score)) * 100)}%`
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q || loading.value) return

  loading.value = true
  error.value = ''
  result.value = null

  try {
    result.value = await ragAskAPI(q, { evaluate: true })
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || 'RAG 问答失败'
    error.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    loading.value = false
  }
}

async function reloadDetail() {
  const id = result.value?.evaluation?.evaluation_id
  if (!id) return
  try {
    const detail = await fetchRagEvaluation(id)
    result.value = {
      ...result.value,
      sources: detail.sources,
      evaluation: {
        evaluation_id: detail.id,
        retrieval: detail.retrieval,
        answer: detail.answer_eval,
        citation: detail.citation,
        latency_ms: detail.latency_ms,
      },
    }
  } catch {
    /* 列表摘要已足够展示 */
  }
}
</script>

<template>
  <section class="rag-eval" aria-label="RAG 评估">
    <header class="rag-eval__header">
      <h2>RAG 问答评估</h2>
      <p>记录：问题 → 检索 → 回答 → 质量评分</p>
    </header>

    <div class="rag-eval__form">
      <textarea
        v-model="question"
        class="rag-eval__input"
        rows="2"
        placeholder="输入文档相关问题…"
        :disabled="loading"
        @keydown.enter.exact.prevent="handleAsk"
      />
      <button type="button" class="rag-eval__submit" :disabled="loading || !question.trim()" @click="handleAsk">
        {{ loading ? '评估中…' : '提问并评估' }}
      </button>
    </div>

    <p v-if="error" class="rag-eval__error" role="alert">{{ error }}</p>

    <div v-if="result" class="rag-eval__result">
      <div class="rag-eval__block">
        <h3>用户问题</h3>
        <p>{{ result.question }}</p>
      </div>

      <div class="rag-eval__block">
        <h3>
          AI 回答
          <span v-if="overallPercent != null" class="rag-eval__overall">
            综合 {{ overallPercent }} · {{ verdictLabel }}
          </span>
        </h3>
        <p class="rag-eval__answer">{{ result.answer }}</p>
      </div>

      <div v-if="result.evaluation" class="rag-eval__scores">
        <h3>评估详情</h3>
        <div class="rag-eval__score-grid">
          <div class="rag-eval__score-item">
            <span>检索均分</span>
            <div class="rag-eval__bar"><i :style="{ width: scoreBarWidth(result.evaluation.retrieval.avg_relevance_score) }" /></div>
            <em>{{ Math.round(result.evaluation.retrieval.avg_relevance_score * 100) }} · {{ result.evaluation.retrieval.hit_quality }}</em>
          </div>
          <div class="rag-eval__score-item">
            <span>忠实度</span>
            <div class="rag-eval__bar"><i :style="{ width: scoreBarWidth(result.evaluation.answer.faithfulness) }" /></div>
            <em>{{ Math.round(result.evaluation.answer.faithfulness * 100) }}</em>
          </div>
          <div class="rag-eval__score-item">
            <span>相关性</span>
            <div class="rag-eval__bar"><i :style="{ width: scoreBarWidth(result.evaluation.answer.answer_relevance) }" /></div>
            <em>{{ Math.round(result.evaluation.answer.answer_relevance * 100) }}</em>
          </div>
          <div class="rag-eval__score-item">
            <span>完整性</span>
            <div class="rag-eval__bar"><i :style="{ width: scoreBarWidth(result.evaluation.answer.completeness) }" /></div>
            <em>{{ Math.round(result.evaluation.answer.completeness * 100) }}</em>
          </div>
        </div>
        <ul v-if="result.evaluation.answer.issues?.length" class="rag-eval__issues">
          <li v-for="(issue, idx) in result.evaluation.answer.issues" :key="idx">{{ issue }}</li>
        </ul>
        <button type="button" class="rag-eval__link" @click="reloadDetail">刷新评估详情</button>
      </div>

      <div class="rag-eval__block">
        <h3>引用来源</h3>
        <ul class="rag-eval__sources">
          <li
            v-for="src in result.sources"
            :key="src.rank"
            class="rag-eval__source"
            :class="labelClass(src.relevance_label)"
          >
            <div class="rag-eval__source-head">
              <strong>[{{ src.rank }}]</strong>
              {{ src.source }} · p.{{ src.page }}
              <span v-if="src.relevance_label" class="rag-eval__label" :class="labelClass(src.relevance_label)">
                {{ src.relevance_label }}
              </span>
              <span class="rag-eval__score-num">{{ (src.relevance_score ?? src.score).toFixed(2) }}</span>
            </div>
            <p>{{ src.text }}</p>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
