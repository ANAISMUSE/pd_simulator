import { reactive } from 'vue'

export const confirmState = reactive({
  visible: false,
  title: '请确认',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  _resolver: null,
})

export function showConfirm({
  title = '请确认',
  message = '',
  confirmText = '确定',
  cancelText = '取消',
} = {}) {
  return new Promise((resolve) => {
    confirmState.title = title
    confirmState.message = message
    confirmState.confirmText = confirmText
    confirmState.cancelText = cancelText
    confirmState.visible = true
    confirmState._resolver = resolve
  })
}

export function resolveConfirm(result) {
  if (typeof confirmState._resolver === 'function') {
    confirmState._resolver(!!result)
  }
  confirmState.visible = false
  confirmState._resolver = null
}

export async function confirm(message, options = {}) {
  return showConfirm({ message, ...options })
}
