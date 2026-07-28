import axios from 'axios';
import { postSSE } from '../utils/sse';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
const SESSION_KEY = 'chat_session_id';
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
});

function getAuthHeaders() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

client.interceptors.request.use((config) => {
  const authHeaders = getAuthHeaders();
  Object.assign(config.headers, authHeaders);
  return config;
});

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getAuthUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setAuthSession({ accessToken, userId, username }) {
  if (accessToken) {
    localStorage.setItem(TOKEN_KEY, accessToken);
  }
  if (userId || username) {
    localStorage.setItem(USER_KEY, JSON.stringify({ userId, username }));
  }
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  clearSessionId();
}

/**
 * 从 localStorage 读取 session_id
 */
export function getSessionId() {
  return localStorage.getItem(SESSION_KEY);
}

/**
 * 保存 session_id 到 localStorage
 */
export function setSessionId(sessionId) {
  if (sessionId) {
    localStorage.setItem(SESSION_KEY, sessionId);
  }
}

/**
 * 清除 session（开始新对话）
 */
export function clearSessionId() {
  localStorage.removeItem(SESSION_KEY);
}

/**
 * 注册新用户
 */
export async function registerAPI(username, password) {
  const { data } = await client.post('/auth/register', { username, password });
  setAuthSession({
    accessToken: data.access_token,
    userId: data.user_id,
    username: data.username,
  });
  return data;
}

/**
 * 用户登录
 */
export async function loginAPI(username, password) {
  const { data } = await client.post('/auth/login', { username, password });
  setAuthSession({
    accessToken: data.access_token,
    userId: data.user_id,
    username: data.username,
  });
  return data;
}

/**
 * 确保已认证 — 开发模式下 auth_disabled 时无需 Token
 */
export async function ensureAuthenticated() {
  if (getAuthToken()) {
    return getAuthUser();
  }
  return null;
}

/**
 * Fetch memory overview for the Memory panel.
 * @param {string|null} sessionId
 * @returns {Promise<{ userId: string, sessionId: string, shortTerm: string[], longTerm: object[] }>}
 */
export async function fetchMemoryOverview(sessionId = getSessionId()) {
  const { data } = await client.get('/memory', {
    params: { session_id: sessionId || undefined },
  });
  if (data.session_id) {
    setSessionId(data.session_id);
  }
  return {
    userId: data.user_id,
    sessionId: data.session_id,
    shortTerm: data.short_term_memory || [],
    longTerm: data.long_term_memory || [],
  };
}

/**
 * Send a chat message to the backend (non-streaming, kept for compatibility).
 * @param {string} message
 * @param {string|null} sessionId
 * @returns {Promise<{ response: string, sessionId: string, userId: string, steps: array, retrievedMemories: array }>}
 */
export async function chatAPI(message, sessionId = getSessionId()) {
  const { data } = await client.post('/chat', {
    message,
    session_id: sessionId || null,
  });
  if (data.session_id) {
    setSessionId(data.session_id);
  }
  return {
    response: data.response,
    sessionId: data.session_id,
    userId: data.user_id,
    steps: data.steps || [],
    retrievedMemories: data.retrieved_memories || [],
    memoryRetrievalSkipped: data.memory_retrieval_skipped,
    memorySkipReason: data.memory_skip_reason || '',
  };
}

/**
 * Stream chat via SSE — supports AbortSignal for「停止生成」.
 * @param {string} message
 * @param {string|null} sessionId
 * @param {{ signal?: AbortSignal, onEvent: (event: object) => void }} options
 */
export async function chatStreamAPI(message, sessionId = getSessionId(), { signal, onEvent } = {}) {
  await postSSE(
    `${API_BASE_URL}/chat/stream`,
    { message, session_id: sessionId || null },
    { signal, onEvent, headers: getAuthHeaders() },
  );
}

/**
 * RAG 文档问答（含可选评估）
 */
export async function ragAskAPI(question, { sessionId = getSessionId(), topK = null, evaluate = true } = {}) {
  const { data } = await client.post('/rag/ask', {
    question,
    session_id: sessionId || null,
    top_k: topK,
    evaluate,
  })
  if (data.session_id) {
    setSessionId(data.session_id)
  }
  return {
    question: data.question,
    answer: data.answer,
    sessionId: data.session_id,
    userId: data.user_id,
    sources: data.sources || [],
    contextPreview: data.context_preview || '',
    evaluation: data.evaluation || null,
  }
}

export async function fetchRagEvaluations(limit = 20) {
  const { data } = await client.get('/rag/evaluations', { params: { limit } })
  return data
}

export async function fetchRagEvaluationStats() {
  const { data } = await client.get('/rag/evaluations/stats')
  return data
}

export async function fetchRagEvaluation(evaluationId) {
  const { data } = await client.get(`/rag/evaluations/${evaluationId}`)
  return data
}

/**
 * Stream RAG document QA via SSE.
 * @param {string} question
 * @param {{ sessionId?: string|null, topK?: number|null, signal?: AbortSignal, onEvent?: (event: object) => void }} options
 */
export async function ragStreamAPI(
  question,
  { sessionId = getSessionId(), topK = null, signal, onEvent } = {},
) {
  await postSSE(
    `${API_BASE_URL}/rag/ask/stream`,
    {
      question,
      session_id: sessionId || null,
      top_k: topK,
    },
    { signal, onEvent, headers: getAuthHeaders() },
  );
}

/**
 * Stream memory-augmented QA via SSE.
 * @param {string} question
 * @param {{ sessionId?: string|null, topK?: number|null, signal?: AbortSignal, onEvent?: (event: object) => void }} options
 */
export async function memoryStreamAPI(
  question,
  { sessionId = getSessionId(), topK = null, signal, onEvent } = {},
) {
  await postSSE(
    `${API_BASE_URL}/memory/ask/stream`,
    {
      question,
      session_id: sessionId || null,
      top_k: topK,
    },
    { signal, onEvent, headers: getAuthHeaders() },
  );
}

/**
 * Upload a document to the RAG knowledge base.
 * @param {File} file
 * @param {(percent: number) => void} [onProgress]
 * @returns {Promise<{ filename: string, fileType: string, chunksAdded: number, totalChunks: number }>}
 */
export async function uploadDocument(file, onProgress) {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await client.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      ...getAuthHeaders(),
    },
    timeout: 120000,
    onUploadProgress: (event) => {
      if (event.total && onProgress) {
        onProgress(Math.round((event.loaded * 100) / event.total));
      }
    },
  });

  return {
    filename: data.filename,
    fileType: data.file_type,
    chunksAdded: data.chunks_added,
    totalChunks: data.total_chunks,
  };
}

/**
 * List uploaded documents in the knowledge base.
 * @returns {Promise<Array<{ filename: string, fileType: string, size: number, uploadedAt: number }>>}
 */
export async function fetchDocuments() {
  const { data } = await client.get('/documents', {
    headers: getAuthHeaders(),
  });

  return (data.documents || []).map((doc) => ({
    filename: doc.filename,
    fileType: doc.file_type,
    size: doc.size,
    uploadedAt: doc.uploaded_at,
  }));
}

export { API_BASE_URL };
