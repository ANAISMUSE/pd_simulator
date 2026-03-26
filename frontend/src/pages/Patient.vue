<template>
  <div class="page">
    <div class="header">
      <div class="title">患者管理</div>
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

          <div class="import-card">
            <div class="import-title">患者表格导入（Excel/CSV）</div>
            <div class="import-row">
              <select v-model="patientImportFormat">
                <option value="xlsx">xlsx</option>
                <option value="csv">csv</option>
              </select>
              <button class="btn-import ghost" @click="downloadPatientTemplate">下载患者模板</button>
            </div>
            <div class="import-row">
              <input type="file" accept=".xlsx,.xls,.csv" @change="onPatientImportFileChange" />
              <button class="btn-import ghost" :disabled="!patientImportFile" @click="validatePatientTable">先校验</button>
              <button class="btn-import" :disabled="!patientImportFile" @click="uploadPatientTable">上传并导入</button>
            </div>
            <div class="import-hint">建议先校验再导入；导入后会自动刷新患者列表。</div>
            <div class="import-result" v-if="patientValidateSummary">{{ patientValidateSummary }}</div>
            <div class="import-row" v-if="patientValidateErrors.length">
              <button class="btn-import ghost" @click="downloadPatientErrorReport('xlsx')">导出错误清单(xlsx)</button>
              <button class="btn-import ghost" @click="downloadPatientErrorReport('csv')">导出错误清单(csv)</button>
            </div>
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

        <div class="section-card modeling-card">
          <h2>📐 三孔个体化建模</h2>
          <p class="modeling-intro">
            在上方填写患者基本信息（年龄、性别、身高、体重、血压）与生化后，录入单次腹膜平衡试验（PET）数据并运行建模。结果会绑定到当前患者，进入「方案模拟」时将自动采用该患者的转运类型与
            24h 尿相关参数。
          </p>
          <div class="modeling-summary">
            <span>当前患者：{{ patient.name || '（未命名）' }}</span>
            <span v-if="selectedPatientId">ID：{{ selectedPatientId }}</span>
            <span v-else class="warn">请先保存患者档案后再「保存建模到患者」</span>
          </div>

          <h3 class="subsection-title">单次腹膜平衡试验（腹透液）</h3>
          <div class="modeling-grid">
            <div class="modeling-group">
              <div class="mg-title">0 小时</div>
              <div class="mg-label">肌酐</div>
              <input v-model.number="modelingInput.pet.d0.creatinine" type="number" placeholder="肌酐" />
              <div class="mg-label">葡萄糖</div>
              <input v-model.number="modelingInput.pet.d0.glucose" type="number" placeholder="葡萄糖" />
              <div class="mg-label">尿素</div>
              <input v-model.number="modelingInput.pet.d0.urea" type="number" placeholder="尿素" />
            </div>
            <div class="modeling-group">
              <div class="mg-title">2 小时</div>
              <div class="mg-label">肌酐</div>
              <input v-model.number="modelingInput.pet.d2.creatinine" type="number" placeholder="肌酐" />
              <div class="mg-label">葡萄糖</div>
              <input v-model.number="modelingInput.pet.d2.glucose" type="number" placeholder="葡萄糖" />
              <div class="mg-label">尿素</div>
              <input v-model.number="modelingInput.pet.d2.urea" type="number" placeholder="尿素" />
            </div>
            <div class="modeling-group">
              <div class="mg-title">4 小时</div>
              <div class="mg-label">肌酐</div>
              <input v-model.number="modelingInput.pet.d4.creatinine" type="number" placeholder="肌酐" />
              <div class="mg-label">葡萄糖</div>
              <input v-model.number="modelingInput.pet.d4.glucose" type="number" placeholder="葡萄糖" />
              <div class="mg-label">尿素</div>
              <input v-model.number="modelingInput.pet.d4.urea" type="number" placeholder="尿素" />
            </div>
          </div>

          <h3 class="subsection-title">2 小时血液</h3>
          <div class="form-grid">
            <div class="form-group">
              <label>血肌酐</label>
              <input v-model.number="modelingInput.blood_2h.creatinine" type="number" step="0.1" />
            </div>
            <div class="form-group">
              <label>血尿素</label>
              <input v-model.number="modelingInput.blood_2h.urea" type="number" step="0.1" />
            </div>
            <div class="form-group">
              <label>血葡萄糖</label>
              <input v-model.number="modelingInput.blood_2h.glucose" type="number" step="0.1" />
            </div>
            <div class="form-group">
              <label>血钠</label>
              <input v-model.number="modelingInput.blood_2h.sodium" type="number" step="0.1" />
            </div>
          </div>

          <h3 class="subsection-title">24 小时尿液</h3>
          <div class="form-grid">
            <div class="form-group">
              <label>尿量 (ml)</label>
              <input v-model.number="modelingInput.urine_24h.urine_volume_24h_ml" type="number" />
            </div>
            <div class="form-group">
              <label>尿尿素</label>
              <input v-model.number="modelingInput.urine_24h.urine_urea" type="number" step="0.1" />
            </div>
            <div class="form-group">
              <label>尿肌酐</label>
              <input v-model.number="modelingInput.urine_24h.urine_creatinine" type="number" step="0.1" />
            </div>
          </div>

          <div class="modeling-actions">
            <button type="button" class="btn-modeling primary" @click="runIndividualizedModeling">运行个体化建模</button>
            <button type="button" class="btn-modeling" :disabled="!selectedPatientId" @click="persistIndividualizedModel">保存建模到患者</button>
          </div>
          <p v-if="modelingSavedAt" class="modeling-saved">已保存：{{ modelingSavedAt }}</p>

          <div v-if="individualizedResult" class="modeling-chart-wrap">
            <div ref="individualizedChartEl" class="modeling-chart"></div>
          </div>
          <div v-if="individualizedResult" class="modeling-result">
            <div><strong>腹膜转运类型：</strong>{{ individualizedResult.transport_type }}</div>
            <div><strong>残余肾 Kt/V：</strong>{{ individualizedResult.renal_ktv }}</div>
            <div><strong>残余肾肌酐清除率 (L/天)：</strong>{{ individualizedResult.renal_creatinine_clearance_l_day }}</div>
            <div><strong>模拟 1h 钠筛：</strong>{{ individualizedResult.sodium_sieving_1h }}</div>
            <div><strong>腹腔残余液体量 (ml)：</strong>{{ individualizedResult.residual_intraperitoneal_volume_ml }}</div>
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
import { ref, watch, onMounted, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { showToast } from '../utils/toast'
import { confirm } from '../utils/confirm'
import {
  defaultModelingInput,
  loadModelingForPatient,
  saveModelingForPatient,
} from '../utils/individualizedModelingStorage.js'

const API_BASE = 'http://localhost:5000/api'

const patientsList = ref([])
const selectedPatientId = ref(null)

const modelingInput = ref(defaultModelingInput())
const individualizedResult = ref(null)
const individualizedChartEl = ref(null)
let individualizedChart = null
const modelingSavedAt = ref('')

const getAuthHeaders = (json = false) => {
  const token = localStorage.getItem('pd_token') || ''
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

const syncModelingFromPatientForm = () => {
  const b = biomarkers.value
  const p = patient.value
  modelingInput.value.blood_2h.creatinine = b.creatinine ?? modelingInput.value.blood_2h.creatinine
  modelingInput.value.blood_2h.urea = b.bun ?? modelingInput.value.blood_2h.urea
  modelingInput.value.blood_2h.glucose = b.glucose ?? modelingInput.value.blood_2h.glucose
  modelingInput.value.blood_2h.sodium = b.sodium ?? modelingInput.value.blood_2h.sodium
  if (p.urine_volume != null) {
    modelingInput.value.urine_24h.urine_volume_24h_ml = p.urine_volume
  }
}

const mergeStoredModelingInput = (stored) => {
  const d = defaultModelingInput()
  if (!stored?.modelingInput) return d
  const m = stored.modelingInput
  return {
    pet: {
      d0: { ...d.pet.d0, ...(m.pet?.d0 || {}) },
      d2: { ...d.pet.d2, ...(m.pet?.d2 || {}) },
      d4: { ...d.pet.d4, ...(m.pet?.d4 || {}) },
    },
    blood_2h: { ...d.blood_2h, ...(m.blood_2h || {}) },
    urine_24h: { ...d.urine_24h, ...(m.urine_24h || {}) },
  }
}

const loadPersistedIndividualizedModel = async () => {
  individualizedResult.value = null
  modelingSavedAt.value = ''
  if (!selectedPatientId.value) {
    modelingInput.value = mergeStoredModelingInput(null)
    syncModelingFromPatientForm()
    if (individualizedChart) {
      individualizedChart.dispose()
      individualizedChart = null
    }
    return
  }
  try {
    const resp = await fetch(`${API_BASE}/patients/${selectedPatientId.value}/individualized-modeling`, {
      headers: getAuthHeaders(),
    })
    const data = await resp.json().catch(() => ({}))
    const backendModeling = data?.success ? (data.modeling || null) : null
    const localModeling = loadModelingForPatient(selectedPatientId.value)
    const stored = backendModeling || localModeling
    modelingInput.value = mergeStoredModelingInput(stored)
    if (!stored?.modelingInput) {
      syncModelingFromPatientForm()
    }
    if (stored?.result) {
      individualizedResult.value = stored.result
      modelingSavedAt.value = stored.updatedAt || ''
      await nextTick()
      renderIndividualizedChart()
    } else if (individualizedChart) {
      individualizedChart.dispose()
      individualizedChart = null
    }
  } catch (e) {
    console.error('读取后端建模失败，回退本地存储:', e)
    const stored = loadModelingForPatient(selectedPatientId.value)
    modelingInput.value = mergeStoredModelingInput(stored)
    if (!stored?.modelingInput) {
      syncModelingFromPatientForm()
    }
    if (stored?.result) {
      individualizedResult.value = stored.result
      modelingSavedAt.value = stored.updatedAt || ''
      await nextTick()
      renderIndividualizedChart()
    } else if (individualizedChart) {
      individualizedChart.dispose()
      individualizedChart = null
    }
  }
}

const renderIndividualizedChart = () => {
  if (!individualizedChartEl.value || !individualizedResult.value) return
  if (!individualizedChart || individualizedChart.getDom() !== individualizedChartEl.value) {
    if (individualizedChart) individualizedChart.dispose()
    individualizedChart = echarts.init(individualizedChartEl.value)
  }
  const r = individualizedResult.value
  const values = [
    Number(r.renal_ktv || 0),
    Number(r.renal_creatinine_clearance_l_day || 0),
    Number(r.sodium_sieving_1h || 0),
    Number((r.residual_intraperitoneal_volume_ml || 0) / 100),
  ]
  const indicator = [
    { name: '残肾Kt/V', max: 2 },
    { name: '残肾肌酐清除', max: 20 },
    { name: '1h钠筛', max: 20 },
    { name: '残余液体量/100', max: 10 },
  ]
  individualizedChart.setOption(
    {
      backgroundColor: '#fff',
      tooltip: {},
      radar: {
        indicator,
        splitLine: { lineStyle: { color: '#e2e8f0' } },
        splitArea: { areaStyle: { color: ['#fff', '#f8fafc'] } },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      series: [
        {
          type: 'radar',
          data: [{ value: values, name: '个体化评估' }],
          lineStyle: { color: '#4f46e5', width: 2 },
          areaStyle: { color: 'rgba(79,70,229,0.18)' },
          symbol: 'circle',
          symbolSize: 6,
        },
      ],
    },
    true,
  )
  individualizedChart.resize()
}
const patientImportFormat = ref('xlsx')
const patientImportFile = ref(null)
const patientValidateSummary = ref('')
const patientValidateErrors = ref([])

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

const safeJson = async (resp) => {
  try {
    return await resp.json()
  } catch {
    return {}
  }
}

const loadPatientData = async () => {
  if (!selectedPatientId.value) {
    patient.value = defaultPatient()
    biomarkers.value = defaultBiomarkers()
    saveCurrentToStorage()
    await loadPersistedIndividualizedModel()
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
        is_shared: !!p.is_shared,
      }
      biomarkers.value = p.biomarkers
      saveCurrentToStorage()
      await loadPersistedIndividualizedModel()
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
  if (!(await confirm('确定要删除这个患者吗？', { title: '删除确认' }))) return

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

const buildModelingPatientBody = () => ({
  name: patient.value.name,
  gender: patient.value.gender,
  age: patient.value.age,
  weight: patient.value.weight,
  height: patient.value.height,
  bsa: patient.value.bsa,
  blood_pressure_systolic: patient.value.blood_pressure_systolic,
  blood_pressure_diastolic: patient.value.blood_pressure_diastolic,
})

const runIndividualizedModeling = async () => {
  if (!patient.value.name?.trim()) {
    showToast('请先填写患者姓名', 'info')
    return
  }
  try {
    const resp = await fetch(`${API_BASE}/modeling/individualized`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: buildModelingPatientBody(),
        pet: modelingInput.value.pet,
        blood_2h: modelingInput.value.blood_2h,
        urine_24h: modelingInput.value.urine_24h,
      }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!data.success) {
      showToast(data.error || '个体化建模失败', 'error')
      return
    }
    individualizedResult.value = data.result || null
    const tt = individualizedResult.value?.transport_type
    if (tt) {
      patient.value.peritoneal_transport = tt
    }
    await nextTick()
    renderIndividualizedChart()
    showToast('个体化建模完成，腹膜转运类型已写入当前表单（保存患者可同步到服务器）', 'success')
  } catch (e) {
    console.error(e)
    showToast('个体化建模失败', 'error')
  }
}

const persistIndividualizedModel = async () => {
  if (!selectedPatientId.value) {
    showToast('请先保存患者档案，再保存建模', 'info')
    return
  }
  if (!individualizedResult.value) {
    showToast('请先运行个体化建模', 'info')
    return
  }
  const localSaved = saveModelingForPatient(selectedPatientId.value, {
    modelingInput: JSON.parse(JSON.stringify(modelingInput.value)),
    result: JSON.parse(JSON.stringify(individualizedResult.value)),
  })
  if (!localSaved) {
    showToast('本地缓存建模失败，将继续尝试后端保存', 'info')
  }

  try {
    const response = await fetch(`${API_BASE}/patients/${selectedPatientId.value}/individualized-modeling`, {
      method: 'PUT',
      headers: getAuthHeaders(true),
      body: JSON.stringify({
        modelingInput: JSON.parse(JSON.stringify(modelingInput.value)),
        result: JSON.parse(JSON.stringify(individualizedResult.value)),
      }),
    })
    const data = await response.json().catch(() => ({}))
    if (!data.success) {
      showToast(data.error || '后端保存建模失败', 'error')
      return
    }
    if (data.modeling?.updatedAt) {
      modelingSavedAt.value = data.modeling.updatedAt
    } else {
      modelingSavedAt.value = new Date().toISOString()
    }
    showToast('建模已绑定到该患者（后端已保存），方案模拟页将自动读取', 'success')
  } catch (e) {
    console.error(e)
    showToast('后端保存建模失败', 'error')
  }
}

const onPatientImportFileChange = (event) => {
  patientImportFile.value = event?.target?.files?.[0] || null
}

const downloadPatientTemplate = async () => {
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const resp = await fetch(
      `${API_BASE}/import/template?entity=patients&format=${patientImportFormat.value}`,
      { headers },
    )
    if (!resp.ok) return showToast('下载患者模板失败', 'error')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `patients_import_template.${patientImportFormat.value}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载患者模板失败:', error)
    showToast('下载患者模板失败', 'error')
  }
}

const validatePatientTable = async () => {
  if (!patientImportFile.value) return showToast('请先选择文件', 'info')
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const form = new FormData()
    form.append('file', patientImportFile.value)
    const resp = await fetch(`${API_BASE}/import/tabular/validate?entity=patients`, {
      method: 'POST',
      headers,
      body: form,
    })
    if (resp.status === 401) return showToast('登录已失效，请重新登录', 'error')
    const data = await safeJson(resp)
    if (!data.success) return showToast(data.error || '预校验失败', 'error')
    patientValidateSummary.value = `预校验：预计新增 ${data.would_create}，跳过 ${data.would_skip}，错误 ${data.errors?.length || 0}`
    patientValidateErrors.value = Array.isArray(data.errors) ? data.errors : []
    showToast('患者导入预校验完成', 'success')
  } catch (error) {
    console.error('患者导入预校验失败:', error)
    showToast('患者导入预校验失败', 'error')
  }
}

const uploadPatientTable = async () => {
  if (!patientImportFile.value) return showToast('请先选择文件', 'info')
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const form = new FormData()
    form.append('file', patientImportFile.value)
    const resp = await fetch(`${API_BASE}/import/tabular?entity=patients`, {
      method: 'POST',
      headers,
      body: form,
    })
    if (resp.status === 401) return showToast('登录已失效，请重新登录', 'error')
    const data = await safeJson(resp)
    if (!data.success) return showToast(data.error || '患者导入失败', 'error')
    showToast(`导入完成：新增${data.created}，跳过${data.skipped}`, 'success')
    patientImportFile.value = null
    patientValidateSummary.value = ''
    patientValidateErrors.value = []
    await loadPatientsList()
  } catch (error) {
    console.error('患者导入失败:', error)
    showToast('患者导入失败', 'error')
  }
}

const downloadPatientErrorReport = async (fmt) => {
  if (!patientValidateErrors.value.length) return showToast('当前没有错误清单', 'info')
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    const resp = await fetch(`${API_BASE}/import/errors/export`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        entity: 'patients',
        format: fmt,
        errors: patientValidateErrors.value,
      }),
    })
    if (!resp.ok) return showToast('导出错误清单失败', 'error')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `patients_import_errors.${fmt}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('导出错误清单失败:', error)
    showToast('导出错误清单失败', 'error')
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

onBeforeUnmount(() => {
  if (individualizedChart) {
    individualizedChart.dispose()
    individualizedChart = null
  }
})
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
.modeling-card .subsection-title {
  margin-top: 12px;
}
.modeling-intro {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  margin-bottom: 10px;
}
.modeling-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #334155;
  margin-bottom: 8px;
}
.modeling-summary .warn {
  color: #b45309;
}
.modeling-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 8px;
}
.modeling-group {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.modeling-group .mg-title {
  font-size: 12px;
  font-weight: 800;
  color: #667eea;
}
.modeling-group .mg-label {
  font-size: 11px;
  font-weight: 800;
  color: rgba(31, 35, 64, 0.7);
  margin-top: -2px;
}
.modeling-group input {
  padding: 8px 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  font-size: 13px;
}
.modeling-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.btn-modeling {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
  font-weight: 700;
  cursor: pointer;
}
.btn-modeling.primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: none;
}
.btn-modeling:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.modeling-saved {
  font-size: 12px;
  color: #059669;
  margin-top: 6px;
}
.modeling-chart-wrap {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px;
  background: #fff;
}
.modeling-chart {
  width: 100%;
  height: 260px;
}
.modeling-result {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: #1e293b;
}
.patient-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.import-card {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px dashed rgba(102, 126, 234, 0.35);
  border-radius: 10px;
  background: rgba(238, 242, 255, 0.45);
}
.import-title {
  font-size: 13px;
  font-weight: 800;
  color: #3730a3;
  margin-bottom: 8px;
}
.import-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.import-row input,
.import-row select {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
}
.btn-import {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}
.btn-import.ghost {
  background: #f8fafc;
}
.btn-import:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.import-hint {
  font-size: 12px;
  color: #475569;
}
.import-result {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  font-size: 12px;
  color: #3730a3;
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
  .import-row {
    flex-wrap: wrap;
  }
  .modeling-grid {
    grid-template-columns: 1fr;
  }
}
</style>

