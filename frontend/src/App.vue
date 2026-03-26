<template>
  <router-view />

  <div
    v-if="toast.visible"
    class="custom-alert"
    :class="{ success: toast.type === 'success', error: toast.type === 'error', info: toast.type === 'info' }"
  >
    <div class="alert-content">
      <span class="alert-icon" v-if="toast.type === 'success'">✅</span>
      <span class="alert-icon" v-else-if="toast.type === 'error'">❌</span>
      <span class="alert-icon" v-else-if="toast.type === 'info'">ℹ️</span>
      <span class="alert-message">{{ toast.message }}</span>
    </div>
    <button class="alert-close" @click="hideToast">×</button>
  </div>

  <div v-if="confirmState.visible" class="confirm-overlay" @click.self="onCancelConfirm">
    <div class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="confirmState.title">
      <div class="confirm-title">{{ confirmState.title }}</div>
      <div class="confirm-message">{{ confirmState.message }}</div>
      <div class="confirm-actions">
        <button class="confirm-btn confirm-btn-primary" @click="onOkConfirm">{{ confirmState.confirmText }}</button>
        <button class="confirm-btn" @click="onCancelConfirm">{{ confirmState.cancelText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive } from 'vue'
import { confirmState, resolveConfirm } from './utils/confirm'

const toast = reactive({
  visible: false,
  message: '',
  type: 'info',
})

let timer = null

const show = ({ message, type = 'info', duration = 5000 } = {}) => {
  if (!message) return
  toast.message = message
  toast.type = type
  toast.visible = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    toast.visible = false
    timer = null
  }, duration)
}

const hideToast = () => {
  toast.visible = false
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

const onOkConfirm = () => resolveConfirm(true)
const onCancelConfirm = () => resolveConfirm(false)

const onKeydown = (e) => {
  if (e.key === 'Escape' && confirmState.visible) resolveConfirm(false)
}

const handleEvent = (e) => {
  show(e.detail || {})
}

onMounted(() => {
  window.addEventListener('pd-toast', handleEvent)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('pd-toast', handleEvent)
  window.removeEventListener('keydown', onKeydown)
  if (timer) clearTimeout(timer)
})
</script>

<style>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(15, 23, 42, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.confirm-dialog {
  width: min(560px, 100%);
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.3);
  border: 1px solid rgba(99, 102, 241, 0.14);
  padding: 22px 24px 18px;
}
.confirm-title {
  font-size: 24px;
  font-weight: 800;
  color: #1f2340;
}
.confirm-message {
  margin-top: 14px;
  font-size: 20px;
  color: #2f3557;
  line-height: 1.45;
}
.confirm-actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.confirm-btn {
  border: 0;
  border-radius: 999px;
  padding: 10px 26px;
  font-size: 18px;
  font-weight: 700;
  cursor: pointer;
  background: #e9d8fd;
  color: #4c1d95;
}
.confirm-btn-primary {
  background: #6d28d9;
  color: #fff;
}
</style>

