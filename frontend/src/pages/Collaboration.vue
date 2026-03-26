<template>
  <div class="page">
    <div class="header">
      <div class="title">协作与记录中心</div>
      <div class="subtitle">按步骤完成导入、协作申请和患者记录，避免“填了但不知道下一步”</div>
    </div>

    <section class="card guide">
      <h3>推荐操作顺序</h3>
      <div class="steps">
        <div class="step"><span>1</span> 先下载模板并填写</div>
        <div class="step"><span>2</span> 上传文件并先校验</div>
        <div class="step"><span>3</span> 无严重错误后再导入</div>
        <div class="step"><span>4</span> 导入后进行协作申请和记录维护</div>
      </div>
    </section>

    <div class="grid">
      <section class="card">
        <h3>① 医生表格导入（Excel/CSV）</h3>
        <div class="hint">此处仅导入医生数据；患者导入已移动到“患者管理”页面。</div>
        <div class="row">
          <select v-model="importEntity">
            <option value="doctors">导入医生</option>
          </select>
          <select v-model="importFormat">
            <option value="xlsx">xlsx</option>
            <option value="csv">csv</option>
          </select>
          <button class="btn ghost" :disabled="busy" @click="downloadTemplate">下载模板</button>
        </div>
        <div class="row">
          <input type="file" @change="onImportFileChange" accept=".xlsx,.xls,.csv" />
          <button class="btn ghost" :disabled="!importFile || busy" @click="validateTable">先校验</button>
          <button class="btn" :disabled="!importFile || busy" @click="uploadTable">上传并导入</button>
        </div>
        <div class="hint">支持 `.xlsx/.xls/.csv`，字段支持中英文别名。</div>
        <div class="result-box" v-if="validateSummary">{{ validateSummary }}</div>

        <div class="row" v-if="validateErrors.length">
          <button class="btn ghost" @click="downloadErrorReport('xlsx')">导出错误清单(xlsx)</button>
          <button class="btn ghost" @click="downloadErrorReport('csv')">导出错误清单(csv)</button>
        </div>
        <div class="error-preview" v-if="validateErrors.length">
          <div class="list-title">校验错误预览（前20条）</div>
          <div class="error-item" v-for="(item, idx) in validateErrors.slice(0, 20)" :key="idx">
            第 {{ item.row || '-' }} 行：{{ item.error || '未知错误' }}
          </div>
        </div>
      </section>

      <section class="card">
        <h3>② 医院与医疗组维护</h3>
        <div class="hint">先维护组织结构，再进行医生筛选和协作申请会更准确。</div>
        <div class="row">
          <input v-model.trim="newHospitalName" placeholder="新增医院名称" />
          <button class="btn" :disabled="busy" @click="createHospital">新增医院</button>
        </div>
        <div class="row">
          <select v-model.number="groupHospitalId">
            <option :value="0">选择医院</option>
            <option v-for="h in hospitals" :key="h.id" :value="h.id">{{ h.name }}</option>
          </select>
          <input v-model.trim="newGroupName" placeholder="新增医疗组名称" />
          <button class="btn" :disabled="busy" @click="createGroup">新增医疗组</button>
        </div>
      </section>

      <section class="card">
        <h3>③ 跨医生访问申请</h3>
        <div class="row">
          <select v-model.number="doctorFilterHospitalId" @change="onFilterHospitalChange">
            <option :value="0">按医院筛选医生</option>
            <option v-for="h in hospitals" :key="h.id" :value="h.id">{{ h.name }}</option>
          </select>
          <select v-model.number="doctorFilterGroupId" @change="loadDoctors">
            <option :value="0">按医疗组筛选</option>
            <option v-for="g in filterGroups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </div>
        <div class="row">
          <select v-model.number="requestDoctorId">
            <option :value="0">选择目标医生</option>
            <option v-for="d in doctors" :key="d.id" :value="d.id">
              #{{ d.id }} {{ d.display_name || d.username }}
            </option>
          </select>
          <input v-model.trim="requestReason" placeholder="申请理由（可选）" />
          <button class="btn" @click="submitRequest">发起申请</button>
        </div>
        <div class="list">
          <div class="list-title">我发起的申请</div>
          <div v-for="r in sentRequests" :key="`sent-${r.id}`" class="list-item">
            <span>#{{ r.id }} 目标医生 {{ r.owner_doctor_id }}（{{ r.status }}）</span>
          </div>
          <div v-if="!sentRequests.length" class="list-empty">暂无你发起的申请</div>
        </div>
        <div class="list">
          <div class="list-title">当前授权有效期说明：默认 30 天，填 0 为长期授权</div>
          <div class="list-title">我收到的申请</div>
          <div v-for="r in receivedRequests" :key="r.id" class="list-item">
            <span>#{{ r.id }} 来自医生 {{ r.requester_doctor_id }}（{{ r.status }}）</span>
            <div class="item-actions" v-if="r.status === 'pending'">
              <input
                v-model.number="approveDaysByRequest[r.id]"
                class="days"
                type="number"
                min="0"
                placeholder="授权天数(0=长期)"
              />
              <button class="btn ghost" @click="decideRequest(r.id, 'approve')">同意并授权</button>
              <button class="btn ghost" @click="decideRequest(r.id, 'reject')">拒绝</button>
            </div>
          </div>
        </div>
        <div class="list">
          <div class="list-title">我授予他人的访问权限（可撤销）</div>
          <div v-for="g in ownerGrants" :key="`owner-${g.id}`" class="list-item">
            <span>
              授权给医生 {{ g.grantee_doctor_id }} · {{ grantStatusText(g) }} · {{ grantExpireText(g) }}
            </span>
            <div class="item-actions">
              <button class="btn ghost" :disabled="!g.active" @click="revokeGrant(g.id)">撤销访问权</button>
            </div>
          </div>
          <div v-if="!ownerGrants.length" class="list-empty">暂无你发出的授权</div>
        </div>
        <div class="list">
          <div class="list-title">我获得的访问权限</div>
          <div v-for="g in granteeGrants" :key="`grantee-${g.id}`" class="list-item">
            <span>
              来自医生 {{ g.owner_doctor_id }} · {{ grantStatusText(g) }} · {{ grantExpireText(g) }}
            </span>
          </div>
          <div v-if="!granteeGrants.length" class="list-empty">暂无你收到的授权</div>
        </div>
      </section>

      <section class="card">
        <h3>④ 患者记录维护</h3>
        <div class="row">
          <select v-model.number="selectedPatientId" @change="loadPatientRecords">
            <option :value="0">选择患者</option>
            <option v-for="p in patients" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
          <input v-model.trim="checkForm.project_name" placeholder="检查项目" />
          <input v-model.trim="checkForm.result_value" placeholder="结果值" />
          <input v-model.trim="checkForm.unit" placeholder="单位" />
          <button class="btn" @click="addCheck">新增检查</button>
        </div>
        <div class="list mini">
          <div v-for="c in checks" :key="c.id" class="list-item">
            {{ c.checked_at }} | {{ c.project_name }}: {{ c.result_value || '-' }} {{ c.unit || '' }}
          </div>
        </div>
        <div class="row">
          <select v-model.number="usageTemplateId">
            <option :value="0">模板（可选）</option>
            <option v-for="r in regimens" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
          <label class="inline">
            <input v-model="promoteAsTemplate" type="checkbox" />
            改动升级为新模板
          </label>
          <button class="btn" @click="addUsage">新增方案使用记录</button>
        </div>
        <textarea
          v-model="usageSnapshotText"
          class="json"
          placeholder='方案快照 JSON，例如 {"phases":[{"phase_name":"夜间","duration":8,"glucose_conc":1.5,"fill_volume":2.0}]}'
        />
        <div class="list mini">
          <div v-for="u in usages" :key="u.id" class="list-item">
            记录#{{ u.id }} 模板: {{ u.template_id || '无' }} 升级模板: {{ u.promoted_template_id || '无' }}
          </div>
        </div>
        <div class="row">
          <input v-model.trim="modelName" placeholder="统计模型名称" />
          <button class="btn" @click="runModel">记录模型运行</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast } from '../utils/toast'
import { confirm } from '../utils/confirm'

const API_BASE = 'http://localhost:5000/api'
const token = () => localStorage.getItem('pd_token') || ''
const authHeaders = () => ({ Authorization: `Bearer ${token()}` })
const jsonHeaders = () => ({ 'Content-Type': 'application/json', ...authHeaders() })

const hospitals = ref([])
const filterGroups = ref([])
const doctors = ref([])
const patients = ref([])
const regimens = ref([])
const checks = ref([])
const usages = ref([])
const receivedRequests = ref([])
const sentRequests = ref([])
const accessGrants = ref([])

const newHospitalName = ref('')
const groupHospitalId = ref(0)
const newGroupName = ref('')

const requestDoctorId = ref(0)
const requestReason = ref('')
const doctorFilterHospitalId = ref(0)
const doctorFilterGroupId = ref(0)
const approveDays = ref(30)
const approveDaysByRequest = ref({})

const selectedPatientId = ref(0)
const checkForm = ref({ project_name: '', result_value: '', unit: '' })

const usageTemplateId = ref(0)
const promoteAsTemplate = ref(false)
const usageSnapshotText = ref('{"phases":[]}')
const modelName = ref('PD-Stats-v1')
const importEntity = ref('doctors')
const importFormat = ref('xlsx')
const importFile = ref(null)
const validateSummary = ref('')
const validateErrors = ref([])
const busy = ref(false)

const safeJson = async (resp) => {
  try {
    return await resp.json()
  } catch {
    return { success: false, error: 'bad response' }
  }
}

const requestJson = async (url, options = {}, fallback = '请求失败') => {
  try {
    const resp = await fetch(url, options)
    if (resp.status === 401) {
      showToast('登录已失效，请重新登录', 'error')
      return { success: false, error: 'unauthorized' }
    }
    const data = await safeJson(resp)
    if (!data.success && data.error) {
      showToast(data.error, 'error')
    }
    return data
  } catch (e) {
    console.error(e)
    showToast(`${fallback}（后端可能未启动）`, 'error')
    return { success: false, error: fallback }
  }
}

const loadBase = async () => {
  const [h, p, r, reqReceived, reqSent, grants] = await Promise.all([
    fetch(`${API_BASE}/hospitals`, { headers: authHeaders() }).then(safeJson),
    fetch(`${API_BASE}/patients`, { headers: authHeaders() }).then(safeJson),
    fetch(`${API_BASE}/regimens`).then(safeJson),
    fetch(`${API_BASE}/access-requests?mode=received`, { headers: authHeaders() }).then(safeJson),
    fetch(`${API_BASE}/access-requests?mode=sent`, { headers: authHeaders() }).then(safeJson),
    fetch(`${API_BASE}/access-grants`, { headers: authHeaders() }).then(safeJson),
  ])
  hospitals.value = h.hospitals || []
  patients.value = p.patients || []
  regimens.value = r.regimens || []
  receivedRequests.value = reqReceived.requests || []
  sentRequests.value = reqSent.requests || []
  accessGrants.value = grants.grants || []
  const nextApproveDaysByRequest = {}
  for (const r of receivedRequests.value) {
    if (r.status === 'pending') nextApproveDaysByRequest[r.id] = 30
  }
  approveDaysByRequest.value = nextApproveDaysByRequest
  if (!doctorFilterHospitalId.value && hospitals.value.length) {
    doctorFilterHospitalId.value = hospitals.value[0].id
  }
  await loadGroupsForFilter()
  await loadDoctors()
}

const loadGroupsForFilter = async () => {
  if (!doctorFilterHospitalId.value) {
    filterGroups.value = []
    doctorFilterGroupId.value = 0
    return
  }
  const data = await fetch(
    `${API_BASE}/medical-groups?hospital_id=${doctorFilterHospitalId.value}`,
    { headers: authHeaders() },
  ).then(safeJson)
  filterGroups.value = data.groups || []
  if (!filterGroups.value.some((g) => g.id === doctorFilterGroupId.value)) {
    doctorFilterGroupId.value = 0
  }
}

const loadDoctors = async () => {
  const qs = new URLSearchParams()
  if (doctorFilterHospitalId.value) qs.set('hospital_id', String(doctorFilterHospitalId.value))
  if (doctorFilterGroupId.value) qs.set('medical_group_id', String(doctorFilterGroupId.value))
  const endpoint = qs.toString() ? `${API_BASE}/doctors?${qs}` : `${API_BASE}/doctors`
  const data = await fetch(endpoint, { headers: authHeaders() }).then(safeJson)
  doctors.value = (data.doctors || []).filter((x) => x.id !== Number(localStorage.getItem('pd_user_id')))
}

const onFilterHospitalChange = async () => {
  await loadGroupsForFilter()
  await loadDoctors()
}

const createHospital = async () => {
  if (!newHospitalName.value) return showToast('请填写医院名称', 'info')
  busy.value = true
  try {
    const data = await requestJson(
      `${API_BASE}/hospitals`,
      {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ name: newHospitalName.value }),
      },
      '新增医院失败',
    )
    if (!data.success) return
    newHospitalName.value = ''
    await loadBase()
    showToast('医院已新增', 'success')
  } finally {
    busy.value = false
  }
}

const createGroup = async () => {
  if (!groupHospitalId.value || !newGroupName.value) return showToast('请选择医院并填写医疗组', 'info')
  const data = await requestJson(
    `${API_BASE}/medical-groups`,
    {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ hospital_id: groupHospitalId.value, name: newGroupName.value }),
    },
    '新增医疗组失败',
  )
  if (!data.success) return
  newGroupName.value = ''
  showToast('医疗组已新增', 'success')
}

const submitRequest = async () => {
  if (!requestDoctorId.value) return showToast('请选择目标医生', 'info')
  const resp = await fetch(`${API_BASE}/access-requests`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ owner_doctor_id: requestDoctorId.value, reason: requestReason.value }),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '申请失败', 'error')
  requestReason.value = ''
  showToast('申请已提交', 'success')
}

const decideRequest = async (id, action) => {
  const days = Number(approveDaysByRequest.value[id] ?? approveDays.value ?? 30)
  if (action === 'approve' && (Number.isNaN(days) || days < 0)) {
    return showToast('授权天数必须 >= 0', 'info')
  }
  const resp = await fetch(`${API_BASE}/access-requests/${id}/decision`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ action, expires_days: action === 'approve' ? days : undefined }),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '审批失败', 'error')
  await loadBase()
  showToast(`已${action === 'approve' ? '同意' : '拒绝'}申请`, 'success')
}

const currentUserId = () => Number(localStorage.getItem('pd_user_id') || 0)

const ownerGrants = computed(() => {
  const uid = currentUserId()
  return (accessGrants.value || []).filter((g) => Number(g.owner_doctor_id) === uid)
})

const granteeGrants = computed(() => {
  const uid = currentUserId()
  return (accessGrants.value || []).filter((g) => Number(g.grantee_doctor_id) === uid)
})

const grantStatusText = (grant) => {
  if (!grant?.active) return '已撤销'
  if (grant?.expires_at && new Date(grant.expires_at).getTime() <= Date.now()) return '已过期'
  return '生效中'
}

const grantExpireText = (grant) => {
  if (!grant?.expires_at) return '长期'
  const dt = new Date(grant.expires_at)
  if (Number.isNaN(dt.getTime())) return '到期时间无效'
  return `到期：${dt.toLocaleString('zh-CN')}`
}

const revokeGrant = async (grantId) => {
  if (!(await confirm('确认撤销该医生对你名下患者的访问权吗？', { title: '撤销确认' }))) return
  const resp = await fetch(`${API_BASE}/access-grants/${grantId}/revoke`, {
    method: 'POST',
    headers: jsonHeaders(),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '撤销授权失败', 'error')
  await loadBase()
  showToast('访问权已撤销', 'success')
}

const loadPatientRecords = async () => {
  if (!selectedPatientId.value) return
  const [c, u] = await Promise.all([
    fetch(`${API_BASE}/patients/${selectedPatientId.value}/checks`, { headers: authHeaders() }).then(safeJson),
    fetch(`${API_BASE}/patients/${selectedPatientId.value}/regimen-usages`, { headers: authHeaders() }).then(safeJson),
  ])
  checks.value = c.checks || []
  usages.value = u.usages || []
}

const addCheck = async () => {
  if (!selectedPatientId.value) return showToast('请先选择患者', 'info')
  if (!checkForm.value.project_name) return showToast('请填写检查项目', 'info')
  const resp = await fetch(`${API_BASE}/patients/${selectedPatientId.value}/checks`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(checkForm.value),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '新增检查失败', 'error')
  checkForm.value = { project_name: '', result_value: '', unit: '' }
  await loadPatientRecords()
  showToast('检查已记录', 'success')
}

const addUsage = async () => {
  if (!selectedPatientId.value) return showToast('请先选择患者', 'info')
  let parsed = {}
  try {
    parsed = JSON.parse(usageSnapshotText.value || '{}')
  } catch {
    return showToast('方案快照 JSON 格式错误', 'error')
  }
  const resp = await fetch(`${API_BASE}/patients/${selectedPatientId.value}/regimen-usages`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({
      template_id: usageTemplateId.value || null,
      regimen_snapshot: parsed,
      promote_as_template: promoteAsTemplate.value,
    }),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '新增方案使用记录失败', 'error')
  await loadPatientRecords()
  showToast('方案使用记录已新增', 'success')
}

const runModel = async () => {
  if (!selectedPatientId.value) return showToast('请先选择患者', 'info')
  const resp = await fetch(`${API_BASE}/model-runs`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({
      patient_id: selectedPatientId.value,
      model_name: modelName.value || 'PD-Stats-v1',
      input_payload: { checks_count: checks.value.length, usages_count: usages.value.length },
      output_payload: { risk_score: Math.min(100, checks.value.length * 5 + usages.value.length * 3) },
    }),
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '模型记录失败', 'error')
  showToast('统计模型运行已记录', 'success')
}

const onImportFileChange = (event) => {
  importFile.value = event?.target?.files?.[0] || null
}

const uploadTable = async () => {
  if (!importFile.value) return showToast('请先选择文件', 'info')
  const form = new FormData()
  form.append('file', importFile.value)
  const resp = await fetch(`${API_BASE}/import/tabular?entity=${importEntity.value}`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '导入失败', 'error')
  showToast(`导入完成：新增${data.created}，更新${data.updated}，跳过${data.skipped}`, 'success')
  importFile.value = null
  validateSummary.value = ''
  validateErrors.value = []
  await loadBase()
}

const validateTable = async () => {
  if (!importFile.value) return showToast('请先选择文件', 'info')
  const form = new FormData()
  form.append('file', importFile.value)
  const resp = await fetch(`${API_BASE}/import/tabular/validate?entity=${importEntity.value}`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  const data = await safeJson(resp)
  if (!data.success) return showToast(data.error || '预校验失败', 'error')
  validateSummary.value = `预校验：预计新增 ${data.would_create}，更新 ${data.would_update}，跳过 ${data.would_skip}，错误 ${data.errors?.length || 0}`
  validateErrors.value = Array.isArray(data.errors) ? data.errors : []
  showToast('预校验完成', 'success')
}

const downloadTemplate = async () => {
  const url = `${API_BASE}/import/template?entity=${importEntity.value}&format=${importFormat.value}`
  const resp = await fetch(url, { headers: authHeaders() })
  if (!resp.ok) return showToast('下载模板失败', 'error')
  const blob = await resp.blob()
  const link = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  link.href = objectUrl
  link.download = `${importEntity.value}_import_template.${importFormat.value}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

const downloadErrorReport = async (fmt) => {
  if (!validateErrors.value.length) return showToast('当前没有错误清单', 'info')
  const resp = await fetch(`${API_BASE}/import/errors/export`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({
      entity: importEntity.value,
      format: fmt,
      errors: validateErrors.value,
    }),
  })
  if (!resp.ok) return showToast('导出错误清单失败', 'error')
  const blob = await resp.blob()
  const link = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  link.href = objectUrl
  link.download = `${importEntity.value}_import_errors.${fmt}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

onMounted(loadBase)
</script>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; }
.header { margin-bottom: 14px; }
.title { font-size: 20px; font-weight: 900; color: #1f2340; }
.subtitle { margin-top: 6px; font-size: 13px; color: rgba(31, 35, 64, 0.65); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.card { background: #fff; border: 1px solid rgba(0,0,0,0.08); border-radius: 12px; padding: 14px; }
.guide { margin-bottom: 14px; }
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.step { background: #f8fafc; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; padding: 8px 10px; font-size: 12px; color: #334155; }
.step span { display: inline-flex; width: 18px; height: 18px; align-items: center; justify-content: center; border-radius: 999px; background: #4f46e5; color: #fff; font-size: 11px; margin-right: 6px; }
.hint { font-size: 12px; color: #64748b; margin-bottom: 8px; }
.result-box { margin: 8px 0; padding: 8px 10px; border-radius: 8px; background: #eef2ff; border: 1px solid #c7d2fe; font-size: 12px; color: #3730a3; }
.row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.row input, .row select { flex: 1; min-width: 0; padding: 8px 10px; border: 1px solid rgba(0,0,0,0.12); border-radius: 8px; }
.btn { padding: 8px 10px; border: 1px solid rgba(0,0,0,0.14); border-radius: 8px; background: #fff; cursor: pointer; font-weight: 700; white-space: nowrap; }
.btn.ghost { background: #f8fafc; }
.inline { display: flex; align-items: center; gap: 6px; white-space: nowrap; font-size: 12px; }
.list { max-height: 210px; overflow: auto; border-top: 1px dashed rgba(0,0,0,0.08); padding-top: 8px; }
.list.mini { max-height: 130px; }
.list-title { font-size: 12px; color: #475569; margin-bottom: 6px; }
.list-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; padding: 6px 0; border-bottom: 1px dashed rgba(0,0,0,0.06); }
.item-actions { display: flex; gap: 6px; }
.list-empty { font-size: 12px; color: #64748b; padding: 6px 0; }
.days { width: 130px; flex: 0 0 130px !important; }
.json { width: 100%; min-height: 80px; margin-bottom: 8px; padding: 8px 10px; border: 1px solid rgba(0,0,0,0.12); border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; }
.error-preview { margin-top: 8px; padding-top: 8px; border-top: 1px dashed rgba(0,0,0,0.08); }
.error-item { font-size: 12px; color: #9f1239; padding: 4px 0; }
@media (max-width: 1200px) {
  .grid { grid-template-columns: 1fr; }
  .steps { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 780px) {
  .row { flex-wrap: wrap; }
  .steps { grid-template-columns: 1fr; }
}
</style>
