<script setup>
defineProps({
  icon: { type: String, required: true },
  label: { type: String, required: true },
  value: { type: String, default: '' },
  pending: { type: Boolean, default: false },
  streaming: { type: Boolean, default: false },
})
</script>

<template>
  <div class="agent-trace__row">
    <div class="agent-trace__label">
      <span class="agent-trace__icon" aria-hidden="true">{{ icon }}</span>
      <span class="agent-trace__name">{{ label }}:</span>
    </div>
    <div class="agent-trace__value">
      <div v-if="pending" class="agent-trace__pending">
        <div class="typing-indicator">
          <span />
          <span />
          <span />
        </div>
      </div>
      <p v-else class="agent-trace__text">{{ value || '—' }}</p>
    </div>
  </div>
</template>
