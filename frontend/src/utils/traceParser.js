/**
 * 从 ReAct steps 与 Memory 数据构建一体化 Trace 摘要。
 */

function parseRagSources(observation) {
  if (!observation) return [];

  const sources = [];
  for (const line of observation.split('\n')) {
    const match = line.match(/^\[(\d+)\]\s+(\S+)/);
    if (match) {
      sources.push({ rank: Number(match[1]), source: match[2] });
    }
  }

  if (sources.length === 0) {
    if (observation.includes('知识库为空') || observation.includes('未在知识库')) {
      return [{ source: '未找到相关文档', empty: true }];
    }
  }

  return sources;
}

function formatRagLabel(source) {
  if (source.empty) return source.source;
  return `找到 ${source.source}`;
}

function formatMemoryLabel(retrievedMemories, memoryRetrievalSkipped, memorySkipReason) {
  if (memoryRetrievalSkipped) {
    return memorySkipReason ? `未检索（${memorySkipReason}）` : '未检索长期记忆';
  }
  if (!retrievedMemories.length) return '无';
  return retrievedMemories.map((m) => m.content).join('；');
}

function formatToolLabel(steps) {
  const actions = steps.map((s) => s.action).filter(Boolean);
  if (!actions.length) return '无';
  return actions.join('\n');
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
  const thoughts = steps.map((s) => s.thought).filter(Boolean);
  const thought = thoughts.length ? thoughts.join('\n\n') : null;

  const ragSources = [];
  let ragPending = false;
  for (const step of steps) {
    if (step.action?.includes('search_docs')) {
      if (step.observation) {
        ragSources.push(...parseRagSources(step.observation));
      } else {
        ragPending = true;
      }
    }
  }

  const uniqueRag = [];
  const seen = new Set();
  for (const item of ragSources) {
    const key = item.source;
    if (!seen.has(key)) {
      seen.add(key);
      uniqueRag.push(item);
    }
  }

  let rag = '无';
  if (uniqueRag.length) {
    rag = uniqueRag.map(formatRagLabel).join('、');
  } else if (ragPending) {
    rag = '检索中…';
  }

  const memory = formatMemoryLabel(retrievedMemories, memoryRetrievalSkipped, memorySkipReason);
  const tool = formatToolLabel(steps);

  return { thought, rag, memory, tool };
}

export function createEmptyTrace(loading = false) {
  return {
    steps: [],
    retrievedMemories: [],
    memoryRetrievalSkipped: false,
    memorySkipReason: '',
    contextReady: false,
    loading,
  };
}
