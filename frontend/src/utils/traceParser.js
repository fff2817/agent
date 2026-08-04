/**
 * 从 ReAct steps 与 Memory 数据构建 Trace 摘要与 RAG 引用。
 *
 * Observation 格式示例（search_docs）:
 *   [1] filename.pdf p.3 (score=0.850): preview text...
 */

const CITATION_LINE_RE =
  /^\[(\d+)\]\s+(\S+)\s+(?:p\.(\d+)\s+)?(?:\(score=([\d.]+)\))?\s*:?\s*(.*)$/i

/**
 * 解析单条 search_docs observation 文本为引用列表。
 * @param {string} observation
 * @returns {Array<{ rank: number, source: string, page: number|null, score: number|null, snippet: string, empty?: boolean }>}
 */
export function parseRagSources(observation) {
  if (!observation) return []

  if (observation.includes('知识库为空') || observation.includes('未在知识库')) {
    return [{ rank: 0, source: '未找到相关文档', page: null, score: null, snippet: '', empty: true }]
  }
  if (observation.includes('未在选定范围内找到')) {
    return [{ rank: 0, source: '选定范围内无结果', page: null, score: null, snippet: '', empty: true }]
  }

  const sources = []
  const blocks = observation.split(/\n\n+/)

  for (const block of blocks) {
    const lines = block.split('\n').map((l) => l.trim()).filter(Boolean)
    for (const line of lines) {
      if (line.startsWith('检索范围:')) continue

      const match = line.match(CITATION_LINE_RE)
      if (match) {
        sources.push({
          rank: Number(match[1]),
          source: match[2],
          page: match[3] != null ? Number(match[3]) : null,
          score: match[4] != null ? Number(match[4]) : null,
          snippet: (match[5] || '').trim(),
          empty: false,
        })
        continue
      }

      const simple = line.match(/^\[(\d+)\]\s+(\S+)/)
      if (simple) {
        sources.push({
          rank: Number(simple[1]),
          source: simple[2],
          page: null,
          score: null,
          snippet: line.replace(simple[0], '').replace(/^[:\s]+/, '').trim(),
          empty: false,
        })
      }
    }
  }

  return sources
}

/**
 * 从全部 ReAct steps 提取去重后的 RAG 引用。
 * @param {Array} steps
 * @returns {{ citations: Array, pending: boolean }}
 */
export function extractCitations(steps = []) {
  const citations = []
  let pending = false
  const seen = new Set()

  for (const step of steps) {
    if (!step.action?.includes('search_docs')) continue
    if (!step.observation) {
      pending = true
      continue
    }
    for (const item of parseRagSources(step.observation)) {
      const key = item.empty ? `empty:${item.source}` : `${item.rank}:${item.source}:${item.page}`
      if (seen.has(key)) continue
      seen.add(key)
      citations.push(item)
    }
  }

  return { citations, pending }
}

function formatRagLabel(source) {
  if (source.empty) return source.source
  const page = source.page != null ? ` p.${source.page}` : ''
  return `找到 ${source.source}${page}`
}

function formatMemoryLabel(retrievedMemories, memoryRetrievalSkipped, memorySkipReason) {
  if (memoryRetrievalSkipped) {
    return memorySkipReason ? `未检索（${memorySkipReason}）` : '未检索长期记忆'
  }
  if (!retrievedMemories.length) return '无'
  return retrievedMemories.map((m) => m.content).join('；')
}

function formatToolLabel(steps) {
  const actions = steps.map((s) => s.action).filter(Boolean)
  if (!actions.length) return '无'
  return actions.join('\n')
}

/**
 * 根据 trace 推导流式阶段文案。
 */
export function deriveStreamStatus(trace) {
  if (!trace?.loading) return ''
  if (!trace.contextReady) return '正在加载记忆…'
  const steps = trace.steps || []
  const last = steps[steps.length - 1]
  if (!last) return '正在推理…'
  if (last.action?.includes('search_docs') && !last.observation) return '正在检索文档…'
  if (last.action && !last.observation && !last.final_answer) return '正在调用工具…'
  if (last.final_answer) return '正在生成回答…'
  return '正在推理…'
}

/**
 * @param {object} params
 * @param {Array} params.steps
 * @param {Array} params.retrievedMemories
 * @param {boolean} params.memoryRetrievalSkipped
 * @param {string} params.memorySkipReason
 */
export function buildTraceSummary({
  steps = [],
  retrievedMemories = [],
  memoryRetrievalSkipped = false,
  memorySkipReason = '',
} = {}) {
  const thoughts = steps.map((s) => s.thought).filter(Boolean)
  const thought = thoughts.length ? thoughts.join('\n\n') : null

  const { citations, pending: ragPending } = extractCitations(steps)
  const uniqueRag = citations

  let rag = '无'
  if (uniqueRag.length) {
    rag = uniqueRag.map(formatRagLabel).join('、')
  } else if (ragPending) {
    rag = '检索中…'
  }

  const memory = formatMemoryLabel(retrievedMemories, memoryRetrievalSkipped, memorySkipReason)
  const tool = formatToolLabel(steps)

  return { thought, rag, memory, tool, citations: uniqueRag, ragPending }
}

export function createEmptyTrace(loading = false) {
  return {
    steps: [],
    retrievedMemories: [],
    memoryRetrievalSkipped: false,
    memorySkipReason: '',
    contextReady: false,
    loading,
  }
}
