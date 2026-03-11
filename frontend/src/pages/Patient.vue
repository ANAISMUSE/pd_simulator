<template>
  <div class="page">
    <div class="header">
      <div class="title">患者信息</div>
      <div class="subtitle">管理患者基本信息、生化指标，并与后端患者库同步</div>
    </div>

    <div class="main">
      <div class="left">
        <div class="section-card">
          <h2>👤 患者基本信息</h2>

          <div class="patient-selector">
            <select v-model="selectedPatientId" @change="loadPatientData" class="patient-select">
              <option :value="null">+ 新建患者</option>
              <option v-for="p in patientsList" :key="p.id" :value="p.id">
                {{ p.name }} - {{ p.age }}岁 - {{ p.gender === 'male' ? '男' : '女' }}
              </option>
            </select>

            <div class="patient-actions" v-if="selectedPatientId">
              <button @click="savePatient" class="btn-save-patient">💾 保存</button>
              <button @click="deletePatient" class="btn-delete-patient">🗑️ 删除</button>
            </div>
            <button v-else @click="savePatient" class="btn-save-patient">➕ 保存为新患者</button>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label>姓名</label>
              <input v-model="patient.name" type="text" placeholder="张三" />
            </div>
            <div class="form-group">
              <label>性别</label>
              <select v-model="patient.gender">
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </div>
            <div class="form-group">
              <label>年龄 (岁)</label>
              <input v-model.number="patient.age" type="number" min="1" max="120" placeholder="45" />
            </div>
            <div class="form-group">
              <label>体重 (kg)</label>
              <input v-model.number="patient.weight" type="number" step="0.1" min="20" max="200" placeholder="65.0" />
            </div>
            <div class="form-group">
              <label>身高 (cm)</label>
              <input v-model.number="patient.height" type="number" min="100" max="250" placeholder="170" />
            </div>
            <div class="form-group">
              <label>体表面积 (m²)</label>
              <input v-model.number="patient.bsa" type="number" step="0.01" placeholder="1.75" readonly />
              <small>自动计算</small>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h2>🏥 透析相关信息</h2>
          <div class="form-grid">
            <div class="form-group">
              <label>透析龄 (月)</label>
              <input v-model.number="patient.dialysis_vintage" type="number" min="0" placeholder="12" />
            </div>
            <div class="form-group">
              <label>原发病</label>
              <select v-model="patient.primary_disease">
                <option value="chronic_glomerulonephritis">慢性肾小球肾炎</option>
                <option value="diabetic_nephropathy">糖尿病肾病</option>
                <option value="hypertensive_nephropathy">高血压肾病</option>
                <option value="polycystic_kidney">多囊肾</option>
                <option value="other">其他</option>
              </select>
            </div>
            <div class="form-group">
              <label>残余肾功能</label>
              <select v-model="patient.residual_kidney_function">
                <option value="none">无</option>
                <option value="minimal">少量 (&lt;100ml/天)</option>
                <option value="moderate">中等 (100-500ml/天)</option>
                <option value="good">较好 (&gt;500ml/天)</option>
              </select>
            </div>
            <div class="form-group">
              <label>腹膜转运类型</label>
              <select v-model="patient.peritoneal_transport">
                <option value="high">高转运</option>
                <option value="high_average">高平均转运</option>
                <option value="low_average">低平均转运</option>
                <option value="low">低转运</option>
                <option value="unknown">未知</option>
              </select>
            </div>
            <div class="form-group">
              <label>每日尿量 (ml)</label>
              <input v-model.number="patient.urine_volume" type="number" min="0" placeholder="500" />
            </div>
            <div class="form-group">
              <label>血压 (mmHg)</label>
              <div style="display: flex; gap: 8px">
                <input
                  v-model.number="patient.blood_pressure_systolic"
                  type="number"
                  placeholder="收缩压"
                  style="flex: 1"
                />
                <span style="line-height: 42px">/</span>
                <input
                  v-model.number="patient.blood_pressure_diastolic"
                  type="number"
                  placeholder="舒张压"
                  style="flex: 1"
                />
              </div>
            </div>
            <div class="form-group share-flag">
              <label>共享设置</label>
              <label class="share-label">
                <input v-model="patient.is_shared" type="checkbox" />
                <span>允许本院其他医生查看该患者</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="section-card">
          <h2>🧪 生化指标</h2>

          <div class="subsection">
            <h3 class="subsection-title">肾功能指标</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>血清肌酐 (μmol/L)</label>
                <input v-model.number="biomarkers.creatinine" type="number" step="0.1" placeholder="884" />
                <small>正常值: 44-133</small>
              </div>
              <div class="form-group">
                <label>尿素氮 (mmol/L)</label>
                <input v-model.number="biomarkers.bun" type="number" step="0.1" placeholder="25.3" />
                <small>正常值: 2.9-8.2</small>
              </div>
              <div class="form-group">
                <label>尿酸 (μmol/L)</label>
                <input v-model.number="biomarkers.uric_acid" type="number" step="0.1" placeholder="450" />
                <small>正常值: 208-428</small>
              </div>
              <div class="form-group">
                <label>β2微球蛋白 (mg/L)</label>
                <input v-model.number="biomarkers.beta2_microglobulin" type="number" step="0.1" placeholder="25" />
                <small>正常值: 0.8-2.4</small>
              </div>
            </div>
          </div>

          <div class="subsection">
            <h3 class="subsection-title">电解质</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>钾 (mmol/L)</label>
                <input v-model.number="biomarkers.potassium" type="number" step="0.1" placeholder="4.8" />
                <small>正常值: 3.5-5.5</small>
              </div>
              <div class="form-group">
                <label>钠 (mmol/L)</label>
                <input v-model.number="biomarkers.sodium" type="number" step="0.1" placeholder="138" />
                <small>正常值: 135-145</small>
              </div>
              <div class="form-group">
                <label>氯 (mmol/L)</label>
                <input v-model.number="biomarkers.chloride" type="number" step="0.1" placeholder="102" />
                <small>正常值: 96-108</small>
              </div>
              <div class="form-group">
                <label>钙 (mmol/L)</label>
                <input v-model.number="biomarkers.calcium" type="number" step="0.01" placeholder="2.25" />
                <small>正常值: 2.11-2.52</small>
              </div>
              <div class="form-group">
                <label>磷 (mmol/L)</label>
                <input v-model.number="biomarkers.phosphorus" type="number" step="0.01" placeholder="1.8" />
                <small>正常值: 0.87-1.45</small>
              </div>
              <div class="form-group">
                <label>镁 (mmol/L)</label>
                <input v-model.number="biomarkers.magnesium" type="number" step="0.01" placeholder="1.0" />
                <small>正常值: 0.75-1.02</small>
              </div>
            </div>
          </div>

          <div class="subsection">
            <h3 class="subsection-title">血液指标</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>血红蛋白 (g/L)</label>
                <input v-model.number="biomarkers.hemoglobin" type="number" step="0.1" placeholder="95" />
                <small>正常值: 120-160</small>
              </div>
              <div class="form-group">
                <label>白蛋白 (g/L)</label>
                <input v-model.number="biomarkers.albumin" type="number" step="0.1" placeholder="35" />
                <small>正常值: 40-55</small>
              </div>
              <div class="form-group">
                <label>总蛋白 (g/L)</label>
                <input v-model.number="biomarkers.total_protein" type="number" step="0.1" placeholder="65" />
                <small>正常值: 65-85</small>
              </div>
              <div class="form-group">
                <label>红细胞压积 (%)</label>
                <input v-model.number="biomarkers.hematocrit" type="number" step="0.1" placeholder="30" />
                <small>正常值: 40-50</small>
              </div>
            </div>
          </div>

          <div class="subsection">
            <h3 class="subsection-title">代谢与酸碱平衡</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>空腹血糖 (mmol/L)</label>
                <input v-model.number="biomarkers.glucose" type="number" step="0.1" placeholder="5.5" />
                <small>正常值: 3.9-6.1</small>
              </div>
              <div class="form-group">
                <label>糖化血红蛋白 (%)</label>
                <input v-model.number="biomarkers.hba1c" type="number" step="0.1" placeholder="6.5" />
                <small>正常值: &lt;6.5</small>
              </div>
              <div class="form-group">
                <label>总胆固醇 (mmol/L)</label>
                <input v-model.number="biomarkers.cholesterol" type="number" step="0.1" placeholder="5.2" />
                <small>正常值: &lt;5.2</small>
              </div>
              <div class="form-group">
                <label>甘油三酯 (mmol/L)</label>
                <input v-model.number="biomarkers.triglycerides" type="number" step="0.1" placeholder="1.7" />
                <small>正常值: &lt;1.7</small>
              </div>
              <div class="form-group">
                <label>pH值</label>
                <input v-model.number="biomarkers.ph" type="number" step="0.01" placeholder="7.35" />
                <small>正常值: 7.35-7.45</small>
              </div>
              <div class="form-group">
                <label>碳酸氢根 (mmol/L)</label>
                <input v-model.number="biomarkers.bicarbonate" type="number" step="0.1" placeholder="22" />
                <small>正常值: 22-28</small>
              </div>
              <div class="form-group">
                <label>二氧化碳分压 (mmHg)</label>
                <input v-model.number="biomarkers.pco2" type="number" step="0.1" placeholder="40" />
                <small>正常值: 35-45</small>
              </div>
              <div class="form-group">
                <label>阴离子间隙</label>
                <input v-model.number="biomarkers.anion_gap" type="number" step="0.1" placeholder="12" />
                <small>正常值: 8-16</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const API_BASE = 'http://localhost:5000/api'

const patientsList = ref([])
const selectedPatientId = ref(null)

const defaultPatient = () => ({
  name: '',
  gender: 'male',
  age: 45,
  weight: 65,
  height: 170,
  bsa: 1.75,
  dialysis_vintage: 12,
  primary_disease: 'chronic_glomerulonephritis',
  residual_kidney_function: 'minimal',
  peritoneal_transport: 'high_average',
  urine_volume: 500,
  blood_pressure_systolic: 140,
  blood_pressure_diastolic: 90,
  is_shared: false,
})

const defaultBiomarkers = () => ({
  creatinine: 884,
  bun: 25.3,
  uric_acid: 450,
  beta2_microglobulin: 25,
  potassium: 4.8,
  sodium: 138,
  chloride: 102,
  calcium: 2.25,
  phosphorus: 1.8,
  magnesium: 1.0,
  hemoglobin: 95,
  albumin: 35,
  total_protein: 65,
  hematocrit: 30,
  glucose: 5.5,
  hba1c: 6.5,
  cholesterol: 5.2,
  triglycerides: 1.7,
  ph: 7.35,
  bicarbonate: 22,
  pco2: 40,
  anion_gap: 12,
})

const patient = ref(defaultPatient())
const biomarkers = ref(defaultBiomarkers())

const saveCurrentToStorage = () => {
  try {
    localStorage.setItem(
      'pd_current_patient',
      JSON.stringify({
        patient: patient.value,
        biomarkers: biomarkers.value,
      }),
    )
  } catch (e) {
    console.error('保存患者到本地失败', e)
  }
}

const loadFromStorage = () => {
  try {
    const raw = localStorage.getItem('pd_current_patient')
    if (!raw) return
    const data = JSON.parse(raw)
    if (data.patient) patient.value = { ...patient.value, ...data.patient }
    if (data.biomarkers) biomarkers.value = { ...biomarkers.value, ...data.biomarkers }
  } catch (e) {
    console.error('读取本地患者信息失败', e)
  }
}

onMounted(async () => {
  loadFromStorage()
  await loadPatientsList()
})

const loadPatientsList = async () => {
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const response = await fetch(`${API_BASE}/patients`, { headers })
    const data = await response.json()
    if (data.success) {
      patientsList.value = data.patients
    }
  } catch (error) {
    console.error('加载患者列表失败:', error)
  }
}

import { showToast } from '../utils/toast'

const loadPatientData = async () => {
  if (!selectedPatientId.value) {
    patient.value = defaultPatient()
    biomarkers.value = defaultBiomarkers()
    saveCurrentToStorage()
    return
  }

  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const response = await fetch(`${API_BASE}/patients/${selectedPatientId.value}`, { headers })
    const data = await response.json()
    if (data.success) {
      const p = data.patient
      patient.value = {
        name: p.name,
        gender: p.gender,
        age: p.age,
        weight: p.weight,
        height: p.height,
        bsa: p.bsa,
        dialysis_vintage: p.dialysis_vintage,
        primary_disease: p.primary_disease,
        residual_kidney_function: p.residual_kidney_function,
        peritoneal_transport: p.peritoneal_transport,
        urine_volume: p.urine_volume,
        blood_pressure_systolic: p.blood_pressure_systolic,
        blood_pressure_diastolic: p.blood_pressure_diastolic,
      }
      biomarkers.value = p.biomarkers
      saveCurrentToStorage()
      showToast(`已加载患者：${p.name}`, 'success')
    }
  } catch (error) {
    console.error('加载患者数据失败:', error)
    showToast('加载患者数据失败', 'error')
  }
}

const savePatient = async () => {
  if (!patient.value.name.trim()) {
    showToast('请输入患者姓名', 'info')
    return
  }

  const patientData = {
    ...patient.value,
    biomarkers: biomarkers.value,
  }

  try {
    let response

    const token = localStorage.getItem('pd_token') || ''
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }

    if (selectedPatientId.value) {
      response = await fetch(`${API_BASE}/patients/${selectedPatientId.value}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(patientData),
      })
    } else {
      response = await fetch(`${API_BASE}/patients`, {
        method: 'POST',
        headers,
        body: JSON.stringify(patientData),
      })
    }

    const data = await response.json()

    if (data.success) {
      selectedPatientId.value = data.patient.id
      await loadPatientsList()
      saveCurrentToStorage()
      showToast(selectedPatientId.value ? '患者信息已更新' : '新患者已保存', 'success')
    } else {
      showToast('保存失败: ' + data.error, 'error')
    }
  } catch (error) {
    console.error('保存患者失败:', error)
    showToast('保存患者失败', 'error')
  }
}

const deletePatient = async () => {
  if (!selectedPatientId.value) return
  if (!window.confirm('确定要删除这个患者吗？')) return

  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const response = await fetch(`${API_BASE}/patients/${selectedPatientId.value}`, {
      method: 'DELETE',
      headers,
    })
    const data = await response.json()

    if (data.success) {
      showToast('患者已删除', 'success')
      selectedPatientId.value = null
      await loadPatientsList()
      await loadPatientData()
    } else {
      showToast('删除失败: ' + data.error, 'error')
    }
  } catch (error) {
    console.error('删除患者失败:', error)
    showToast('删除患者失败', 'error')
  }
}

watch(
  () => [patient.value.weight, patient.value.height],
  ([weight, height]) => {
    if (weight > 0 && height > 0) {
      patient.value.bsa = Number(Math.sqrt((weight * height) / 3600).toFixed(2))
    }
  },
)

watch(
  () => ({ ...patient.value, biomarkers: biomarkers.value }),
  () => {
    saveCurrentToStorage()
  },
  { deep: true },
)
</script>

<style scoped>
.page {
  max-width: 1400px;
  margin: 0 auto;
}
.header {
  margin-bottom: 16px;
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
.main {
  display: grid;
  grid-template-columns: 1.1fr 1.2fr;
  gap: 16px;
}
.left,
.right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-card {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
}
.section-card h2 {
  font-size: 18px;
  margin-bottom: 14px;
  border-bottom: 2px solid #667eea;
  padding-bottom: 6px;
}
.patient-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.patient-select {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}
.patient-actions {
  display: flex;
  gap: 10px;
}
.btn-save-patient,
.btn-delete-patient {
  flex: 1;
  padding: 8px 10px;
  border-radius: 8px;
  border: 0;
  cursor: pointer;
  font-weight: 700;
  color: #fff;
}
.btn-save-patient {
  background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
}
.btn-delete-patient {
  background: linear-gradient(135deg, #f44336 0%, #e53935 100%);
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-group label {
  font-size: 13px;
  font-weight: 700;
  color: rgba(31, 35, 64, 0.85);
}
.form-group input,
.form-group select {
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  outline: none;
}
.form-group input:focus,
.form-group select:focus {
  border-color: rgba(102, 126, 234, 0.55);
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.14);
}
.form-group small {
  font-size: 11px;
  color: #999;
}
.share-flag .share-label {
  margin-top: 4px;
  font-size: 13px;
  color: rgba(31, 35, 64, 0.9);
  display: flex;
  align-items: center;
  gap: 6px;
}
.share-flag input[type='checkbox'] {
  width: 14px;
  height: 14px;
}
.subsection {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}
.subsection-title {
  font-size: 14px;
  font-weight: 800;
  color: #667eea;
  margin-bottom: 10px;
}
@media (max-width: 1024px) {
  .main {
    grid-template-columns: 1fr;
  }
}
</style>

