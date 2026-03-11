<template>
  <div class="auth-shell">
    <div class="card">
      <div class="title">注册</div>
      <div class="sub">使用后端接口 `POST /api/auth/register`</div>

      <div class="form">
        <label class="label">用户名</label>
        <input v-model.trim="username" class="input" placeholder="请输入用户名" />

        <label class="label">密码</label>
        <input v-model="password" class="input" type="password" placeholder="请输入密码" />

        <label class="label">确认密码</label>
        <input v-model="confirmPassword" class="input" type="password" placeholder="再次输入密码" />

        <button class="btn" :disabled="loading" @click="doRegister">
          {{ loading ? '注册中...' : '注册并登录' }}
        </button>

        <div class="links">
          <RouterLink to="/login">已有账号？去登录</RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const API_BASE = 'http://localhost:5000/api'

const doRegister = async () => {
  if (!username.value) return
  if (!password.value) return
  if (password.value !== confirmPassword.value) return
  loading.value = true
  try {
    const resp = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!data.success) {
      window.alert(data.error || '注册失败，请稍后重试')
      return
    }
    localStorage.setItem('pd_token', data.token)
    localStorage.setItem('pd_username', data.user?.username || username.value)
    router.push('/app/user')
  } catch (e) {
    console.error(e)
    window.alert('无法连接后端服务，请确认后端已在 5000 端口启动')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: radial-gradient(1200px 800px at 10% 0%, #e7ecff 0%, #f7f7fb 50%, #ffffff 100%);
  padding: 20px;
}
.card {
  width: min(420px, 100%);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 14px;
  padding: 18px;
  box-shadow: 0 10px 30px rgba(31, 35, 64, 0.10);
  backdrop-filter: blur(10px);
}
.title {
  font-weight: 850;
  font-size: 20px;
  color: #1f2340;
}
.sub {
  margin-top: 6px;
  font-size: 13px;
  color: rgba(31, 35, 64, 0.65);
}
.form {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.label {
  font-size: 13px;
  font-weight: 700;
  color: rgba(31, 35, 64, 0.85);
}
.input {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  outline: none;
  background: white;
}
.input:focus {
  border-color: rgba(102, 126, 234, 0.55);
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.14);
}
.btn {
  margin-top: 4px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 0;
  cursor: pointer;
  font-weight: 800;
  color: white;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn:hover {
  transform: translateY(-1px);
}
.links {
  margin-top: 8px;
  font-size: 13px;
}
</style>

