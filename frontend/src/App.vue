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
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive } from 'vue'

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

const handleEvent = (e) => {
  show(e.detail || {})
}

onMounted(() => {
  window.addEventListener('pd-toast', handleEvent)
})

onBeforeUnmount(() => {
  window.removeEventListener('pd-toast', handleEvent)
  if (timer) clearTimeout(timer)
})
</script>

<style>
</style>

