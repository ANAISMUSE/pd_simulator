<template>
  <div class="page">
    <div class="header">
      <div class="title">用户基本信息</div>
      <div class="subtitle">先做前端保存，占位后续可接后端用户系统</div>
    </div>

    <div class="card">
      <div class="grid">
        <div class="field">
          <label>姓名</label>
          <input v-model.trim="profile.name" placeholder="例如：王医生" />
        </div>
        <div class="field">
          <label>单位/科室</label>
          <input v-model.trim="profile.org" placeholder="例如：XX医院 肾内科" />
        </div>
        <div class="field">
          <label>手机号</label>
          <input v-model.trim="profile.phone" placeholder="可选" />
        </div>
        <div class="field">
          <label>备注</label>
          <input v-model.trim="profile.note" placeholder="可选" />
        </div>
      </div>

      <div class="actions">
        <button class="btn" @click="save">保存</button>
        <button class="btn ghost" @click="reset">重置</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'

const KEY = 'pd_user_profile'

const load = () => {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : { name: '', org: '', phone: '', note: '' }
  } catch {
    return { name: '', org: '', phone: '', note: '' }
  }
}

const profile = reactive(load())

const save = () => {
  localStorage.setItem(KEY, JSON.stringify(profile))
  window.alert('用户信息已保存（本地浏览器）')
}

const reset = () => {
  const next = load()
  profile.name = next.name
  profile.org = next.org
  profile.phone = next.phone
  profile.note = next.note
}
</script>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
}
.header {
  margin-bottom: 14px;
}
.title {
  font-size: 20px;
  font-weight: 900;
  color: #1f2340;
}
.subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: rgba(31, 35, 64, 0.65);
}
.card {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 14px;
  padding: 18px;
  box-shadow: 0 10px 30px rgba(31, 35, 64, 0.08);
  backdrop-filter: blur(10px);
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
label {
  font-size: 13px;
  font-weight: 750;
  color: rgba(31, 35, 64, 0.85);
}
input {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  outline: none;
  background: white;
}
input:focus {
  border-color: rgba(102, 126, 234, 0.55);
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.14);
}
.actions {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}
.btn {
  padding: 10px 12px;
  border-radius: 10px;
  border: 0;
  cursor: pointer;
  font-weight: 850;
  color: white;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.btn.ghost {
  background: white;
  color: rgba(31, 35, 64, 0.9);
  border: 1px solid rgba(0, 0, 0, 0.10);
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>

