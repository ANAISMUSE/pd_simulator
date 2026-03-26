<template>
  <div class="page">
    <div class="header">
      <div class="title">用户基本信息</div>
      <div class="subtitle">机构与共享设置会同步到后端；换账号后各自独立保存。</div>
    </div>

    <div class="card">
      <div class="grid">
        <div class="field">
          <label>头像</label>
          <div class="avatar-editor">
            <div v-if="profile.avatarUrl" class="avatar-preview">
              <img :src="profile.avatarUrl" alt="医生头像" />
            </div>
            <div v-else class="avatar-placeholder">无头像</div>
            <div class="avatar-actions">
              <input type="file" accept="image/png,image/jpeg,image/webp" @change="onAvatarChange" />
              <button class="btn ghost btn-avatar-clear" type="button" @click="clearAvatar">移除头像</button>
            </div>
          </div>
        </div>
        <div class="field">
          <label>姓名</label>
          <input v-model.trim="profile.name" placeholder="例如：王医生" />
        </div>
        <div class="field">
          <label>单位/科室</label>
          <input v-model.trim="profile.org" placeholder="例如：XX医院 肾内科" />
        </div>
        <div class="field">
          <label>医院</label>
          <select v-model.number="profile.hospitalId" @change="onHospitalChange">
            <option :value="0">请选择医院</option>
            <option v-for="h in hospitals" :key="h.id" :value="h.id">{{ h.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>医疗组</label>
          <select v-model.number="profile.medicalGroupId">
            <option :value="0">请选择医疗组</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
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

      <div class="share-row">
        <label class="share-label">
          <input v-model="profile.allowSharePatients" type="checkbox" />
          <span>同意将自己名下患者在本院内共享给其他医生</span>
        </label>
        <div class="share-tip">（仅同一“单位/科室”的医生可见，仍保留原始归属医生）</div>
      </div>

      <div class="actions">
        <button class="btn" @click="save">保存</button>
        <button class="btn ghost" @click="reset">重置</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { showToast } from '../utils/toast'

const LEGACY_KEY = 'pd_user_profile'
const API_BASE = 'http://localhost:5000/api'
const hospitals = ref([])
const groups = ref([])

const baseProfile = () => ({
  name: '',
  avatarUrl: '',
  org: '',
  phone: '',
  note: '',
  allowSharePatients: false,
  hospitalId: 0,
  medicalGroupId: 0,
})

const profileStorageKey = () => {
  const uid = localStorage.getItem('pd_user_id') || 'anon'
  return `${LEGACY_KEY}_${uid}`
}

const load = () => {
  const base = baseProfile()
  const key = profileStorageKey()
  try {
    const raw = localStorage.getItem(key)
    if (raw) return Object.assign(base, JSON.parse(raw))
    // 仅从旧全局 key 迁移一次到当前账号（避免换账号沿用上一人资料）
    const legacy = localStorage.getItem(LEGACY_KEY)
    if (legacy) {
      const parsed = Object.assign(base, JSON.parse(legacy))
      localStorage.setItem(key, JSON.stringify(parsed))
      return parsed
    }
  } catch {
    /* ignore */
  }
  return base
}

const profile = reactive(baseProfile())

const persistLocal = () => {
  try {
    localStorage.setItem(profileStorageKey(), JSON.stringify(profile))
    localStorage.setItem('pd_display_name', profile.name || localStorage.getItem('pd_username') || '用户')
    localStorage.setItem('pd_avatar_url', profile.avatarUrl || '')
    window.dispatchEvent(new CustomEvent('pd-user-updated'))
    if (localStorage.getItem(LEGACY_KEY)) localStorage.removeItem(LEGACY_KEY)
  } catch (e) {
    console.error(e)
  }
}

const authHeaders = () => {
  const token = localStorage.getItem('pd_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const loadHospitals = async () => {
  try {
    const resp = await fetch(`${API_BASE}/hospitals`, { headers: authHeaders() })
    const data = await resp.json().catch(() => ({}))
    hospitals.value = data.hospitals || []
  } catch {
    hospitals.value = []
  }
}

const loadGroups = async (hospitalId) => {
  if (!hospitalId) {
    groups.value = []
    return
  }
  try {
    const resp = await fetch(`${API_BASE}/medical-groups?hospital_id=${hospitalId}`, { headers: authHeaders() })
    const data = await resp.json().catch(() => ({}))
    groups.value = data.groups || []
  } catch {
    groups.value = []
  }
}

const onHospitalChange = async () => {
  profile.medicalGroupId = 0
  await loadGroups(profile.hospitalId)
}

const save = async () => {
  try {
    persistLocal()

    const token = localStorage.getItem('pd_token')
    if (token) {
      await fetch(`${API_BASE}/auth/me/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          display_name: profile.name || null,
          avatar_url: profile.avatarUrl || null,
          org: profile.org,
          hospital_id: profile.hospitalId || null,
          medical_group_id: profile.medicalGroupId || null,
          allow_share_patients: profile.allowSharePatients,
        }),
      }).catch(() => null)
    }
    showToast('用户信息已保存', 'success')
  } catch (e) {
    console.error(e)
    showToast('保存用户信息失败', 'error')
  }
}

const reset = () => {
  const next = load()
  profile.name = next.name
  profile.avatarUrl = next.avatarUrl || ''
  profile.org = next.org
  profile.phone = next.phone
  profile.note = next.note
  profile.allowSharePatients = !!next.allowSharePatients
  profile.hospitalId = next.hospitalId || 0
  profile.medicalGroupId = next.medicalGroupId || 0
}

const applyServerUser = (user) => {
  if (!user) return
  if (user.display_name != null) profile.name = user.display_name || ''
  if (user.avatar_url != null) profile.avatarUrl = user.avatar_url || ''
  if (user.org != null) profile.org = user.org || ''
  profile.allowSharePatients = !!user.allow_share_patients
  profile.hospitalId = user.hospital_id || 0
  profile.medicalGroupId = user.medical_group_id || 0
}

const syncFromServer = async () => {
  const token = localStorage.getItem('pd_token')
  if (!token) return false
  try {
    const resp = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
    const data = await resp.json().catch(() => ({}))
    if (data.success && data.user) {
      if (data.user.id != null) localStorage.setItem('pd_user_id', String(data.user.id))
      applyServerUser(data.user)
      persistLocal()
      return true
    }
  } catch (e) {
    console.error(e)
  }
  return false
}

const onAvatarChange = (e) => {
  const file = e?.target?.files?.[0]
  if (!file) return
  if (!file.type?.startsWith('image/')) {
    showToast('请上传图片文件', 'info')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    showToast('头像图片请小于 2MB', 'info')
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const result = typeof reader.result === 'string' ? reader.result : ''
    if (!result) return
    profile.avatarUrl = result
    persistLocal()
  }
  reader.readAsDataURL(file)
}

const clearAvatar = () => {
  profile.avatarUrl = ''
  persistLocal()
}

onMounted(async () => {
  await loadHospitals()
  const ok = await syncFromServer()
  if (!ok) {
    Object.assign(profile, load())
  } else {
    const local = load()
    profile.phone = local.phone || profile.phone
    profile.note = local.note || profile.note
    persistLocal()
  }
  if (profile.hospitalId) {
    await loadGroups(profile.hospitalId)
  }
})
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
.share-row {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.share-label {
  font-size: 13px;
  color: rgba(31, 35, 64, 0.9);
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.share-label input {
  width: 14px;
  height: 14px;
}
.share-tip {
  font-size: 12px;
  color: rgba(31, 35, 64, 0.55);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.avatar-editor {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar-preview,
.avatar-placeholder {
  width: 56px;
  height: 56px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
  font-size: 12px;
  color: rgba(31, 35, 64, 0.6);
}
.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.avatar-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.btn-avatar-clear {
  padding: 8px 10px;
  font-size: 12px;
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
select {
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
select:focus {
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

