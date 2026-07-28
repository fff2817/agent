<script setup>
const props = defineProps({
  modelValue: { type: String, default: '' },
  isGenerating: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'send', 'stop'])

function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (props.isGenerating) return
    emit('send')
  }
}

function handlePrimaryClick() {
  if (props.isGenerating) {
    emit('stop')
    return
  }
  emit('send')
}
</script>

<template>
  <div class="input-box">
    <textarea
      class="input-box__textarea"
      placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
      :value="modelValue"
      rows="1"
      :disabled="disabled"
      @input="emit('update:modelValue', $event.target.value)"
      @keydown="handleKeyDown"
    />
    <button
      type="button"
      class="input-box__send"
      :class="{ 'input-box__send--stop': isGenerating }"
      :disabled="!isGenerating && (disabled || !modelValue.trim())"
      :aria-label="isGenerating ? '停止生成' : '发送'"
      @click="handlePrimaryClick"
    >
      {{ isGenerating ? '停止生成' : '发送' }}
    </button>
  </div>
</template>
