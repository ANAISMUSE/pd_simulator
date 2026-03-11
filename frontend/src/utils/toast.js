export function showToast(message, type = 'info', duration = 5000) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent('pd-toast', {
      detail: { message, type, duration },
    }),
  )
}

