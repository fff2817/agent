<script setup>
import { ref } from 'vue'
import {
  clearAuthSession,
  getAuthUser,
  loginAPI,
  registerAPI,
} from '../services/api'

const props = defineProps({
  inspectorOpen: { type: Boolean, default: true },
})

const emit = defineEmits(['auth-change', 'new-chat', 'toggle-inspector'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const authOpen = ref(false)
const currentUser = ref(getAuthUser())

function switchMode(next) {
  mode.value = next
  error.value = ''
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data =
      mode.value === 'login'
        ? await loginAPI(username.value.trim(), password.value)
        : await registerAPI(username.value.trim(), password.value)
    currentUser.value = { userId: data.user_id, username: data.username }
    password.value = ''
    authOpen.value = false
    emit('auth-change', currentUser.value)
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '操作失败'
    error.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    loading.value = false
  }
}

function logout() {
  clearAuthSession()
  currentUser.value = null
  username.value = ''
  password.value = ''
  authOpen.value = false
  emit('auth-change', null)
}

defineExpose({ currentUser })
</script>

<template>
  <header class="top-bar">
    <div class="top-bar__left">
      <div class="top-bar__brand">
        <span class="top-bar__logo" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="brandLogoGrad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
                <stop stop-color="#3B82F6" />
                <stop offset="1" stop-color="#1D4ED8" />
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="9" fill="url(#brandLogoGrad)" />
            <path
              d="M16 7.2c.55 0 1 .36 1.12.88l.9 3.72a4.2 4.2 0 0 0 3.06 3.06l3.72.9c.52.12.88.57.88 1.12s-.36 1-.88 1.12l-3.72.9a4.2 4.2 0 0 0-3.06 3.06l-.9 3.72c-.12.52-.57.88-1.12.88s-1-.36-1.12-.88l-.9-3.72a4.2 4.2 0 0 0-3.06-3.06l-3.72-.9C7.56 17.88 7.2 17.43 7.2 16.88s.36-1 .88-1.12l3.72-.9a4.2 4.2 0 0 0 3.06-3.06l.9-3.72c.12-.52.57-.88 1.12-.88Z"
              fill="#fff"
            />
            <circle cx="23.2" cy="8.4" r="1.35" fill="#BFDBFE" />
            <circle cx="9.2" cy="23.2" r="1.05" fill="#93C5FD" opacity=".9" />
          </svg>
        </span>
        <div class="top-bar__brand-text">
          <h1 class="top-bar__title">AI 智能助手</h1>
          <p class="top-bar__subtitle">ReAct · RAG · Memory</p>
        </div>
      </div>
    </div>

    <div class="top-bar__center">
      <button type="button" class="top-bar__btn" @click="emit('new-chat')">新对话</button>
    </div>

    <div class="top-bar__right">
      <button
        type="button"
        class="top-bar__btn top-bar__btn--ghost"
        :aria-pressed="inspectorOpen"
        @click="emit('toggle-inspector')"
      >
        {{ inspectorOpen ? '隐藏调试' : '调试面板' }}
      </button>

      <template v-if="currentUser">
        <span class="top-bar__user" :title="currentUser.userId">
          {{ currentUser.username }}
        </span>
        <button type="button" class="top-bar__btn" @click="logout">退出</button>
      </template>

      <template v-else>
        <button type="button" class="top-bar__btn top-bar__btn--primary" @click="authOpen = !authOpen">
          登录
        </button>
      </template>
    </div>

    <div v-if="!currentUser && authOpen" class="top-bar__auth-popover">
      <form class="top-bar__auth-form" @submit.prevent="submit">
        <input
          v-model="username"
          type="text"
          placeholder="用户名"
          class="top-bar__input"
          autocomplete="username"
        />
        <input
          v-model="password"
          type="password"
          placeholder="密码"
          class="top-bar__input"
          autocomplete="current-password"
        />
        <button type="submit" class="top-bar__btn top-bar__btn--primary" :disabled="loading">
          {{ loading ? '…' : mode === 'login' ? '登录' : '注册' }}
        </button>
        <button
          type="button"
          class="top-bar__link"
          @click="switchMode(mode === 'login' ? 'register' : 'login')"
        >
          {{ mode === 'login' ? '注册账号' : '返回登录' }}
        </button>
      </form>
      <p v-if="error" class="top-bar__error">{{ error }}</p>
      <p class="top-bar__hint">开发模式（AUTH_DISABLED）可不登录直接使用</p>
    </div>
  </header>
</template>
