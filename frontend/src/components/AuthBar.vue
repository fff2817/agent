<script setup>
import { ref } from 'vue';
import {
  clearAuthSession,
  getAuthUser,
  loginAPI,
  registerAPI,
} from '../services/api';

const emit = defineEmits(['auth-change']);

const mode = ref('login');
const username = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');

const currentUser = ref(getAuthUser());

function switchMode(next) {
  mode.value = next;
  error.value = '';
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请填写用户名和密码';
    return;
  }

  loading.value = true;
  error.value = '';

  try {
    const data =
      mode.value === 'login'
        ? await loginAPI(username.value.trim(), password.value)
        : await registerAPI(username.value.trim(), password.value);

    currentUser.value = { userId: data.user_id, username: data.username };
    password.value = '';
    emit('auth-change', currentUser.value);
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '操作失败';
    error.value = typeof detail === 'string' ? detail : JSON.stringify(detail);
  } finally {
    loading.value = false;
  }
}

function logout() {
  clearAuthSession();
  currentUser.value = null;
  username.value = '';
  password.value = '';
  emit('auth-change', null);
}

defineExpose({ currentUser });
</script>

<template>
  <div class="auth-bar">
    <template v-if="currentUser">
      <span class="auth-bar__user">
        用户: <strong>{{ currentUser.username }}</strong>
        <span class="auth-bar__id">({{ currentUser.userId.slice(0, 8) }}…)</span>
      </span>
      <button type="button" class="auth-bar__btn" @click="logout">退出</button>
    </template>

    <template v-else>
      <form class="auth-bar__form" @submit.prevent="submit">
        <input
          v-model="username"
          type="text"
          placeholder="用户名"
          class="auth-bar__input"
          autocomplete="username"
        />
        <input
          v-model="password"
          type="password"
          placeholder="密码"
          class="auth-bar__input"
          autocomplete="current-password"
        />
        <button type="submit" class="auth-bar__btn auth-bar__btn--primary" :disabled="loading">
          {{ loading ? '…' : mode === 'login' ? '登录' : '注册' }}
        </button>
        <button
          type="button"
          class="auth-bar__btn auth-bar__btn--link"
          @click="switchMode(mode === 'login' ? 'register' : 'login')"
        >
          {{ mode === 'login' ? '注册' : '登录' }}
        </button>
      </form>
      <p v-if="error" class="auth-bar__error">{{ error }}</p>
      <p class="auth-bar__hint">开发模式（AUTH_DISABLED=true）下可不登录直接使用</p>
    </template>
  </div>
</template>

<style scoped>
.auth-bar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.auth-bar__form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.auth-bar__input {
  padding: 0.4rem 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.875rem;
}

.auth-bar__btn {
  padding: 0.4rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 0.875rem;
}

.auth-bar__btn--primary {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}

.auth-bar__btn--link {
  border: none;
  background: transparent;
  color: #2563eb;
  text-decoration: underline;
}

.auth-bar__user {
  font-size: 0.875rem;
  color: #334155;
}

.auth-bar__id {
  color: #94a3b8;
  font-size: 0.75rem;
}

.auth-bar__error {
  color: #dc2626;
  font-size: 0.8125rem;
  margin: 0;
}

.auth-bar__hint {
  color: #94a3b8;
  font-size: 0.75rem;
  margin: 0;
}
</style>
