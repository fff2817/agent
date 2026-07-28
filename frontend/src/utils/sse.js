/**
 * SSE 流式解析工具 — 供 chat / rag / memory 流式 API 复用。
 *
 * 为什么不用 EventSource？
 * - EventSource 只支持 GET，我们需要 POST JSON body
 * - 使用 fetch + ReadableStream 手动解析 SSE
 */

/**
 * 解析 fetch 返回的 SSE 流，逐事件回调 onEvent。
 *
 * @param {Response} response - fetch 响应（需 response.ok === true）
 * @param {{ onEvent?: (event: object) => void }} options
 */
export async function consumeSSEStream(response, { onEvent } = {}) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data: ')) continue;
      const payload = JSON.parse(line.slice(6));
      onEvent?.(payload);
    }
  }
}

/**
 * 通用 POST SSE 请求。
 *
 * @param {string} url - 完整 URL
 * @param {object} body - JSON 请求体
 * @param {{ signal?: AbortSignal, onEvent?: (event: object) => void }} options
 */
export async function postSSE(url, body, { signal, onEvent, headers = {} } = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = `请求失败 (${response.status})`;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      // ignore parse error
    }
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.response = { data: { detail } };
    throw error;
  }

  await consumeSSEStream(response, { onEvent });
}
