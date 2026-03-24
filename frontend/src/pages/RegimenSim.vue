<template>
  <div class="page">
    <div class="header">
      <div class="title">方案模拟</div>
      <div class="subtitle">选择预设/自定义方案，对当前患者进行模拟并查看结果</div>
    </div>

    <div class="main">
      <div class="left">
        <div class="section-card">
          <h2>👤 选择患者</h2>
          <div class="hint">
            这里仅用于“方案模拟”选择模拟对象；患者的详细编辑请在左侧菜单的“患者管理”中完成。
          </div>
          <div class="patient-row">
            <select v-model="selectedPatientId" @change="loadPatientData" class="patient-select">
              <option :value="null">（请选择患者）</option>
              <option v-for="p in patientsList" :key="p.id" :value="p.id">
                {{ p.name }} - {{ p.age }}岁 - {{ p.gender === 'male' ? '男' : '女' }}
              </option>
            </select>
            <button class="btn-secondary" @click="reloadPatients">刷新列表</button>
          </div>
          <div v-if="activePatientName" class="patient-tip">当前模拟患者：{{ activePatientName }}</div>
        </div>

        <div class="section-card">
          <h2>📋 透析方案选择</h2>

          <div class="regimen-section">
            <h3 class="section-title">
              <span class="icon">🏥</span>
              <span>预设方案</span>
            </h3>
            <div class="preset-buttons">
              <div v-for="preset in presets" :key="preset.id" class="preset-item">
                <button
                  @click="selectRegimen('preset', preset.id)"
                  :class="['preset-btn', { active: selectedPresets.includes('preset_' + preset.id) }]"
                >
                  <span class="preset-name">{{ preset.name }}</span>
                  <span class="preset-badge">{{ preset.phases }} 阶段</span>
                </button>
                <button
                  @click="savePresetAsCustom(preset.id)"
                  class="save-presets-btn"
                  title="保存为自定义方案"
                >
                  💾
                </button>
              </div>
            </div>
          </div>

          <div class="regimen-section">
            <h3 class="section-title">
              <span class="icon">✨</span>
              <span>我的方案</span>
              <span class="count-badge">{{ customRegimens.length }}</span>
            </h3>

            <div class="custom-regimens-list" v-if="customRegimens.length">
              <div
                v-for="regimen in customRegimens"
                :key="regimen.id"
                :class="[
                  'custom-regimen-item',
                  { active: selectedPresets.includes('custom_' + regimen.id) },
                ]"
                @click="selectRegimen('custom', regimen.id)"
              >
                <div class="regimen-info">
                  <div class="regimen-name">{{ regimen.name }}</div>
                  <div class="regimen-meta">
                    <span class="phase-count">{{ regimen.phases.length }} 阶段</span>
                    <span class="created-time">{{ formatDate(regimen.createdAt) }}</span>
                  </div>
                </div>
                <div class="regimen-actions">
                  <button
                    @click.stop="editCustomRegimen(regimen)"
                    class="edit-btn"
                    title="编辑"
                  >
                    ✏️
                  </button>
                  <button
                    @click.stop="deleteCustomRegimen(regimen.id)"
                    class="delete-btn"
                    title="删除"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            </div>
            <div class="empty-custom" v-else>暂无自定义方案</div>

            <button @click="showCustomDialog = true" class="btn-add-custom">➕ 创建自定义方案</button>
          </div>

          <div class="section-card" style="margin-top: 10px">
            <h2>🎯 模拟操作</h2>
            <div class="action-buttons">
              <button
                class="btn-primary"
                :disabled="loading || !selectedPresets.length"
                @click="runSimulation"
              >
                {{ loading ? '⏳ 模拟中...' : '🚀 开始模拟' }}
              </button>
              <button
                class="btn-secondary"
                :disabled="loading || selectedPresets.length < 2"
                @click="compareRegimens"
              >
                📊 对比方案
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="section-card">
          <h2>📈 模拟结果</h2>

          <div v-if="!simulationResult && !comparisonResults.length" class="empty-state">
            <div class="empty-icon">📊</div>
            <p>请选择至少一个方案，然后点击“开始模拟”</p>
          </div>

          <template v-else>
            <div v-if="currentRegimen.name" class="regimen-name-display">
              <strong>当前方案：</strong>{{ currentRegimen.name }}
            </div>

            <div v-if="simulationResult" class="metrics-grid">
              <div class="metric-card">
                <div class="metric-icon">💧</div>
                <div class="metric-value">
                  {{ simulationResult.summary.total_uf.toFixed(2) }}
                </div>
                <div class="metric-label">总超滤量 (L)</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🎯</div>
                <div class="metric-value">
                  {{ simulationResult.summary.total_ktv.toFixed(2) }}
                </div>
                <div class="metric-label">总 Kt/V</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🍬</div>
                <div class="metric-value">
                  {{ simulationResult.summary.total_glucose_absorbed.toFixed(0) }}
                </div>
                <div class="metric-label">葡萄糖吸收 (g)</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">⏱️</div>
                <div class="metric-value">
                  {{
                    simulationResult.summary.total_duration &&
                    !isNaN(simulationResult.summary.total_duration)
                      ? (Number(simulationResult.summary.total_duration) / 60).toFixed(1)
                      : '0.0'
                  }}
                </div>
                <div class="metric-label">总时长 (小时)</div>
              </div>
            </div>

            <div v-if="simulationResult" class="chart-container" role="img" aria-label="模拟指标随时间变化图">
              <div ref="mainChartEl" class="chart-inner"></div>
            </div>

            <div v-if="comparisonResults.length" class="result-card">
              <h3>📊 方案对比</h3>
              <div class="comparison-chart-container">
                <div ref="compareChartEl" class="chart-inner"></div>
              </div>

              <div class="comparison-table-wrapper">
                <table class="comparison-table">
                  <thead>
                    <tr>
                      <th>方案名称</th>
                      <th>总 Kt/V</th>
                      <th>总超滤量 (L)</th>
                      <th>葡萄糖吸收 (g)</th>
                      <th>总时长 (小时)</th>
                      <th>预测肌酐 (μmol/L)</th>
                      <th>预测尿素氮 (mmol/L)</th>
                      <th>预测血钾 (mmol/L)</th>
                      <th>充分性评估</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in comparisonResults" :key="row.regimen_id">
                      <td>{{ row.regimen_name }}</td>
                      <td>{{ row.summary.total_ktv?.toFixed(2) ?? '-' }}</td>
                      <td>{{ row.summary.total_uf?.toFixed(1) ?? '-' }}</td>
                      <td>{{ row.summary.total_glucose_absorbed?.toFixed(0) ?? '-' }}</td>
                      <td>
                        {{
                          row.summary.total_duration != null
                            ? (Number(row.summary.total_duration) / 60).toFixed(1)
                            : '-'
                        }}
                      </td>
                      <td>{{ row.summary.predicted_creatinine ?? '-' }}</td>
                      <td>{{ row.summary.predicted_bun ?? '-' }}</td>
                      <td>{{ row.summary.predicted_potassium ?? '-' }}</td>
                      <td>
                        <span
                          :class="[
                            'adequacy-tag',
                            row.summary.adequacy_status === 'adequate' ? 'ok' : 'not-ok',
                          ]"
                        >
                          {{
                            row.summary.adequacy_status === 'adequate'
                              ? '达标'
                              : '不达标'
                          }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="section-card research-card">
      <h2>🧪 三孔模型研究</h2>
      <div class="research-grid">
        <div class="research-block">
          <h3>1) 个体化建模</h3>
          <div class="mini-grid">
            <input v-model.number="modelingInput.pet.d0.creatinine" type="number" placeholder="0h透析液肌酐" />
            <input v-model.number="modelingInput.pet.d0.glucose" type="number" placeholder="0h透析液葡萄糖" />
            <input v-model.number="modelingInput.pet.d0.urea" type="number" placeholder="0h透析液尿素" />
            <input v-model.number="modelingInput.pet.d2.creatinine" type="number" placeholder="2h透析液肌酐" />
            <input v-model.number="modelingInput.pet.d2.glucose" type="number" placeholder="2h透析液葡萄糖" />
            <input v-model.number="modelingInput.pet.d2.urea" type="number" placeholder="2h透析液尿素" />
            <input v-model.number="modelingInput.pet.d4.creatinine" type="number" placeholder="4h透析液肌酐" />
            <input v-model.number="modelingInput.pet.d4.glucose" type="number" placeholder="4h透析液葡萄糖" />
            <input v-model.number="modelingInput.pet.d4.urea" type="number" placeholder="4h透析液尿素" />
            <input v-model.number="modelingInput.blood_2h.creatinine" type="number" placeholder="2h血肌酐" />
            <input v-model.number="modelingInput.blood_2h.urea" type="number" placeholder="2h血尿素" />
            <input v-model.number="modelingInput.blood_2h.glucose" type="number" placeholder="2h血葡萄糖" />
            <input v-model.number="modelingInput.blood_2h.sodium" type="number" placeholder="2h血钠" />
            <input v-model.number="modelingInput.urine_24h.urine_volume_24h_ml" type="number" placeholder="24h尿量(ml)" />
            <input v-model.number="modelingInput.urine_24h.urine_urea" type="number" placeholder="24h尿尿素" />
            <input v-model.number="modelingInput.urine_24h.urine_creatinine" type="number" placeholder="24h尿肌酐" />
          </div>
          <button class="btn-primary" @click="runIndividualizedModeling">运行个体化建模</button>
          <div v-if="individualizedResult" class="research-chart-wrap">
            <div ref="individualizedChartEl" class="research-chart"></div>
          </div>
          <div v-if="individualizedResult" class="research-result">
            <div>转运类型：{{ individualizedResult.transport_type }}</div>
            <div>残肾Kt/V：{{ individualizedResult.renal_ktv }}</div>
            <div>残肾肌酐清除率(L/day)：{{ individualizedResult.renal_creatinine_clearance_l_day }}</div>
            <div>1h钠筛：{{ individualizedResult.sodium_sieving_1h }}</div>
            <div>腹腔残余液体量(ml)：{{ individualizedResult.residual_intraperitoneal_volume_ml }}</div>
          </div>
        </div>

        <div class="research-block">
          <h3>2) 单次腹透模拟</h3>
          <div class="mini-grid">
            <select v-model="singleInput.solution_type">
              <option value="glucose">葡萄糖</option>
              <option value="amino_acid">氨基酸</option>
              <option value="icodextrin">艾考糊精</option>
            </select>
            <input v-model.number="singleInput.concentration_pct" type="number" step="0.1" placeholder="浓度(%)" />
            <input v-model.number="singleInput.fill_volume_l" type="number" step="0.1" placeholder="灌注量(L)" />
            <input v-model.number="singleInput.dwell_minutes" type="number" placeholder="留腹时间(分钟)" />
            <input v-model.number="singleInput.drain_minutes" type="number" placeholder="引流时间(分钟)" />
          </div>
          <button class="btn-primary" @click="runSingleExchange">运行单次模拟</button>
          <div v-if="singleResult?.time_series" class="research-chart-wrap">
            <div ref="singleChartEl" class="research-chart"></div>
          </div>
          <div v-if="singleResult?.summary" class="research-result">
            <div>尿素清除：{{ singleResult.summary.urea_clearance }}</div>
            <div>β2M清除：{{ singleResult.summary.beta2m_clearance }}</div>
            <div>小孔超滤：{{ singleResult.summary.uf_small_pore }}</div>
            <div>超小孔超滤：{{ singleResult.summary.uf_ultrasmall_pore }}</div>
          </div>
        </div>

        <div class="research-block">
          <h3>3) 24小时连续透析</h3>
          <div class="cycle-list">
            <div class="cycle-item" v-for="(c, idx) in continuousInput.cycles" :key="idx">
              <span class="cycle-title">循环{{ idx + 1 }}</span>
              <select v-model="c.solution_type">
                <option value="glucose">葡萄糖</option>
                <option value="amino_acid">氨基酸</option>
                <option value="icodextrin">艾考糊精</option>
              </select>
              <input v-model.number="c.concentration_pct" type="number" step="0.1" placeholder="浓度(%)" />
              <input v-model.number="c.fill_volume_l" type="number" step="0.1" placeholder="灌注量(L)" />
              <input v-model.number="c.dwell_minutes" type="number" placeholder="留腹时间(分钟)" />
              <button class="btn-mini" @click="removeCycle(idx)" :disabled="continuousInput.cycles.length <= 1">删</button>
            </div>
          </div>
          <div class="cycle-actions">
            <input v-model.number="continuousInput.drain_minutes" type="number" placeholder="引流时间(分钟)" />
            <button class="btn-secondary" @click="addCycle">+ 添加循环</button>
            <button class="btn-primary" @click="runContinuous24h">运行24h模拟</button>
          </div>
          <div v-if="continuousResult?.cycles?.length" class="research-chart-wrap">
            <div ref="continuousChartEl" class="research-chart"></div>
          </div>
          <div v-if="continuousResult" class="research-result">
            <div>总腹腔Kt/V：{{ continuousResult.total_peritoneal_ktv }}</div>
            <div>总Kt/V：{{ continuousResult.total_ktv }}</div>
            <div>肌酐清除率：{{ continuousResult.creatinine_clearance }}</div>
            <div>β2M清除：{{ continuousResult.beta2m_clearance }}</div>
            <div>总超滤：{{ continuousResult.total_uf }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCustomDialog" class="modal-overlay" @click.self="showCustomDialog = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>✨ 创建自定义方案</h2>
          <button @click="showCustomDialog = false" class="close-btn">✕</button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label>方案名称</label>
            <input v-model="customRegimen.name" type="text" placeholder="例如：我的夜间方案" />
          </div>

          <div class="phases-section">
            <h3>透析阶段配置</h3>
            <div v-for="(phase, index) in customRegimen.phases" :key="index" class="phase-item">
              <div class="phase-header">
                <span class="phase-number">阶段 {{ index + 1 }}</span>
                <button
                  v-if="customRegimen.phases.length > 1"
                  @click="removePhase(index)"
                  class="btn-remove"
                >
                  🗑️
                </button>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label>阶段名称</label>
                  <input v-model="phase.phase_name" type="text" placeholder="例如：早晨" />
                </div>
                <div class="form-group">
                  <label>留置时间 (小时)</label>
                  <input v-model.number="phase.duration" type="number" step="0.5" min="0.5" />
                </div>
                <div class="form-group">
                  <label>葡萄糖浓度 (%)</label>
                  <select v-model.number="phase.glucose_conc">
                    <option :value="1.5">1.5%</option>
                    <option :value="2.5">2.5%</option>
                    <option :value="4.25">4.25%</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>灌注体积 (L)</label>
                  <input
                    v-model.number="phase.fill_volume"
                    type="number"
                    step="0.1"
                    min="1.0"
                    max="3.0"
                  />
                </div>
              </div>
            </div>

            <button @click="addPhase" class="btn-add-phase">➕ 添加阶段</button>
          </div>
        </div>

        <div class="modal-footer">
          <button @click="showCustomDialog = false" class="btn-cancel">取消</button>
          <button @click="saveCustomRegimen" class="btn-save">保存并使用</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { showToast } from '../utils/toast'

const API_BASE = 'http://localhost:5000/api'

const loading = ref(false)
const presets = ref([])
const customRegimens = ref([])
const selectedPresets = ref([])
const currentRegimen = ref({})
const simulationResult = ref(null)
const comparisonResults = ref([])
const showCustomDialog = ref(false)

const mainChartEl = ref(null)
const compareChartEl = ref(null)
const individualizedChartEl = ref(null)
const singleChartEl = ref(null)
const continuousChartEl = ref(null)
let mainChart = null
let compareChart = null
let individualizedChart = null
let singleChart = null
let continuousChart = null
let mainChartTimer = null

// 患者选择（仅用于本页模拟）
const patientsList = ref([])
const selectedPatientId = ref(null)
const activePatientName = ref('')
const patientPayload = ref(null) // {patient, biomarkers}

const customRegimen = ref({
  name: '',
  phases: [{ phase_name: '第1次', duration: 6, glucose_conc: 1.5, fill_volume: 2.0 }],
})
const editingRegimenId = ref(null)

const modelingInput = ref({
  pet: {
    d0: { creatinine: 120, glucose: 126, urea: 10 },
    d2: { creatinine: 380, glucose: 90, urea: 8 },
    d4: { creatinine: 520, glucose: 70, urea: 6 },
  },
  blood_2h: { creatinine: 884, urea: 25.3, glucose: 5.5, sodium: 138 },
  urine_24h: { urine_volume_24h_ml: 500, urine_urea: 12, urine_creatinine: 9 },
})
const individualizedResult = ref(null)

const singleInput = ref({
  solution_type: 'glucose',
  concentration_pct: 1.5,
  dwell_minutes: 360,
  fill_volume_l: 2.0,
  drain_minutes: 7,
})
const singleResult = ref(null)

const defaultCycle = () => ({
  solution_type: 'glucose',
  concentration_pct: 1.5,
  fill_volume_l: 2.0,
  dwell_minutes: 360,
})
const continuousInput = ref({
  drain_minutes: 7,
  cycles: [defaultCycle(), defaultCycle(), defaultCycle()],
})
const continuousResult = ref(null)

const loadPatientPayload = () => {
  // 严格要求：必须在本页上方明确选择一个患者
  if (patientPayload.value?.patient && patientPayload.value?.biomarkers) return patientPayload.value
  showToast('请先在左侧“选择患者”下拉框中选择一名患者，再进行模拟。', 'info')
  return null
}

onMounted(async () => {
  await loadPresets()
  loadCustomRegimens()
  await reloadPatients()
})

const reloadPatients = async () => {
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const resp = await fetch(`${API_BASE}/patients`, { headers })
    const data = await resp.json()
    if (data.success) patientsList.value = data.patients
  } catch (e) {
    console.error(e)
  }
}

const loadPatientData = async () => {
  activePatientName.value = ''
  patientPayload.value = null
  if (!selectedPatientId.value) {
    simulationResult.value = null
    comparisonResults.value = []
    return
  }
  try {
    const token = localStorage.getItem('pd_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const resp = await fetch(`${API_BASE}/patients/${selectedPatientId.value}`, { headers })
    const data = await resp.json()
    if (!data.success) {
      showToast(data.error || '加载患者失败', 'error')
      return
    }
    const p = data.patient
    activePatientName.value = p.name
    patientPayload.value = {
      patient: {
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
      },
      biomarkers: p.biomarkers || {
        creatinine: 884,
        bun: 25.3,
        potassium: 4.8,
        sodium: 138
      },
    }
    // 同步写入“当前患者”，让优化页也能直接用
    try {
      localStorage.setItem('pd_current_patient', JSON.stringify(patientPayload.value))
    } catch (e) {
      console.error(e)
    }
    // 切换患者后清空上次模拟结果，避免界面仍显示上一名患者的数据
    simulationResult.value = null
    comparisonResults.value = []
  } catch (e) {
    console.error(e)
    showToast('加载患者失败', 'error')
  }
}

const loadPresets = async () => {
  try {
    const response = await fetch(`${API_BASE}/presets`)
    const data = await response.json()
    if (data.success) {
      presets.value = data.presets
    }
  } catch (error) {
    console.error('加载预设方案失败:', error)
  }
}

const loadCustomRegimens = () => {
  const saved = localStorage.getItem('customRegimens')
  if (saved) {
    try {
      customRegimens.value = JSON.parse(saved)
    } catch (error) {
      console.error('加载自定义方案失败:', error)
      customRegimens.value = []
    }
  }
}

const persistCustomRegimens = () => {
  localStorage.setItem('customRegimens', JSON.stringify(customRegimens.value))
}

const selectRegimen = (type, id) => {
  const fullId = `${type}_${id}`
  const index = selectedPresets.value.indexOf(fullId)
  if (index > -1) {
    selectedPresets.value.splice(index, 1)
  } else {
    selectedPresets.value.push(fullId)
  }
}

const savePresetAsCustom = async (presetId) => {
  try {
    const response = await fetch(`${API_BASE}/preset/${presetId}`)
    const data = await response.json()

    if (data.success) {
      const presetDetail = data.regimen
      const newRegimen = {
        id: Date.now().toString(),
        name: presetDetail.name,
        phases: [...presetDetail.phases],
        createdAt: new Date().toISOString(),
      }
      customRegimens.value.push(newRegimen)
      persistCustomRegimens()
      selectedPresets.value = [`custom_${newRegimen.id}`]
      showToast('预设方案已保存为自定义方案', 'success')
    } else {
      showToast('获取预设方案失败: ' + data.error, 'error')
    }
  } catch (error) {
    console.error('保存预设方案为自定义方案失败:', error)
    showToast('保存预设方案为自定义方案失败', 'error')
  }
}

const addPhase = () => {
  customRegimen.value.phases.push({
    phase_name: `第${customRegimen.value.phases.length + 1}次`,
    duration: 6,
    glucose_conc: 1.5,
    fill_volume: 2.0,
  })
}

const removePhase = (index) => {
  customRegimen.value.phases.splice(index, 1)
}

const saveCustomRegimen = () => {
  if (!customRegimen.value.name.trim()) {
    showToast('请输入方案名称', 'info')
    return
  }
  if (!customRegimen.value.phases.length) {
    showToast('请至少添加一个透析阶段', 'info')
    return
  }
  const now = new Date().toISOString()
  if (editingRegimenId.value) {
    // 编辑已有方案
    const idx = customRegimens.value.findIndex((r) => r.id === editingRegimenId.value)
    if (idx !== -1) {
      customRegimens.value[idx] = {
        ...customRegimens.value[idx],
        name: customRegimen.value.name,
        phases: customRegimen.value.phases,
        updatedAt: now,
      }
    }
  } else {
    // 新建方案
    const newRegimen = {
      id: Date.now().toString(),
      name: customRegimen.value.name,
      phases: customRegimen.value.phases,
      createdAt: now,
    }
    customRegimens.value.push(newRegimen)
  }
  persistCustomRegimens()
  // 默认选中当前方案
  if (editingRegimenId.value) {
    selectedPresets.value = [`custom_${editingRegimenId.value}`]
  } else {
    const last = customRegimens.value[customRegimens.value.length - 1]
    if (last) selectedPresets.value = [`custom_${last.id}`]
  }
  showCustomDialog.value = false
  showToast(`自定义方案 "${customRegimen.value.name}" 已保存`, 'success')
  customRegimen.value = {
    name: '',
    phases: [{ phase_name: '第1次', duration: 6, glucose_conc: 1.5, fill_volume: 2.0 }],
  }
  editingRegimenId.value = null
}

const editCustomRegimen = (regimen) => {
  editingRegimenId.value = regimen.id
  customRegimen.value = {
    name: regimen.name,
    phases: regimen.phases.map((p) => ({
      phase_name: p.phase_name,
      duration: p.duration,
      glucose_conc: p.glucose_conc,
      fill_volume: p.fill_volume,
    })),
  }
  showCustomDialog.value = true
}

const runIndividualizedModeling = async () => {
  const payload = loadPatientPayload()
  if (!payload) return
  try {
    const resp = await fetch(`${API_BASE}/modeling/individualized`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: payload.patient,
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
    await nextTick()
    renderIndividualizedChart()
    showToast('个体化建模完成', 'success')
  } catch (e) {
    console.error(e)
    showToast('个体化建模失败', 'error')
  }
}

const runSingleExchange = async () => {
  const payload = loadPatientPayload()
  if (!payload) return
  try {
    const resp = await fetch(`${API_BASE}/simulate/single-exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: payload.patient,
        biomarkers: payload.biomarkers,
        ...singleInput.value,
      }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!data.success) {
      showToast(data.error || '单次模拟失败', 'error')
      return
    }
    singleResult.value = data.result || null
    await nextTick()
    renderSingleExchangeChart()
    showToast('单次模拟完成', 'success')
  } catch (e) {
    console.error(e)
    showToast('单次模拟失败', 'error')
  }
}

const addCycle = () => {
  continuousInput.value.cycles.push(defaultCycle())
}

const removeCycle = (idx) => {
  if (continuousInput.value.cycles.length <= 1) return
  continuousInput.value.cycles.splice(idx, 1)
}

const runContinuous24h = async () => {
  const payload = loadPatientPayload()
  if (!payload) return
  try {
    const resp = await fetch(`${API_BASE}/simulate/continuous-24h`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: payload.patient,
        biomarkers: payload.biomarkers,
        drain_minutes: continuousInput.value.drain_minutes,
        cycles: continuousInput.value.cycles,
        urine_24h: modelingInput.value.urine_24h,
      }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!data.success) {
      showToast(data.error || '24小时模拟失败', 'error')
      return
    }
    continuousResult.value = data.result || null
    await nextTick()
    renderContinuousChart()
    showToast('24小时连续模拟完成', 'success')
  } catch (e) {
    console.error(e)
    showToast('24小时模拟失败', 'error')
  }
}

const renderIndividualizedChart = () => {
  if (!individualizedChartEl.value || !individualizedResult.value) return
  if (!individualizedChart) individualizedChart = echarts.init(individualizedChartEl.value)

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
}

const renderSingleExchangeChart = () => {
  if (!singleChartEl.value || !singleResult.value?.time_series) return
  if (!singleChart) singleChart = echarts.init(singleChartEl.value)

  const ts = singleResult.value.time_series
  const time = (ts.time_min || []).map((t) => Number(t).toFixed(0))
  const volume = ts.volume_l || []
  const urea = ts.urea_clearance_rate || []
  const beta2 = ts.beta2m_clearance_rate || []

  let reveal = 1
  const total = time.length
  const step = Math.max(1, Math.floor(total / 150))

  const optionFor = (count) => ({
    backgroundColor: '#fff',
    tooltip: { trigger: 'axis' },
    grid: { left: 45, right: 55, top: 30, bottom: 36 },
    xAxis: {
      type: 'category',
      data: time.slice(0, count),
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#64748b' } },
      axisLabel: { color: '#64748b' },
      name: '分钟',
    },
    yAxis: [
      {
        type: 'value',
        name: '体积(L)',
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
        splitLine: { lineStyle: { color: '#e2e8f0' } },
      },
      {
        type: 'value',
        name: '清除率',
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
        splitLine: { show: false },
      },
    ],
    series: [
      { name: '腹腔液体积', type: 'line', smooth: true, showSymbol: false, data: volume.slice(0, count), lineStyle: { width: 2, color: '#4f46e5' } },
      { name: '尿素清除率', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: urea.slice(0, count), lineStyle: { width: 2, color: '#06b6d4' } },
      { name: 'β2M清除率', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: beta2.slice(0, count), lineStyle: { width: 2, color: '#f97316' } },
    ],
  })

  singleChart.setOption(optionFor(reveal), true)
  const timer = setInterval(() => {
    if (!singleChart) return clearInterval(timer)
    reveal += step
    if (reveal >= total) {
      reveal = total
      clearInterval(timer)
    }
    singleChart.setOption(optionFor(reveal), false)
  }, 35)
}

const renderContinuousChart = () => {
  if (!continuousChartEl.value || !continuousResult.value?.cycles?.length) return
  if (!continuousChart) continuousChart = echarts.init(continuousChartEl.value)

  const cycles = continuousResult.value.cycles || []
  const labels = cycles.map((c) => `循环${c.cycle}`)
  const ktv = cycles.map((c) => Number(c.summary?.peritoneal_ktv || 0))
  const uf = cycles.map((c) => Number(c.summary?.uf_total || 0))
  const beta2 = cycles.map((c) => Number(c.summary?.beta2m_clearance || 0))

  continuousChart.setOption(
    {
      backgroundColor: '#fff',
      tooltip: { trigger: 'axis' },
      legend: { top: 6, data: ['循环Kt/V', '循环超滤', 'β2M清除'] },
      grid: { left: 45, right: 45, top: 34, bottom: 36 },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#64748b' }, axisLine: { lineStyle: { color: '#64748b' } } },
      yAxis: { type: 'value', axisLabel: { color: '#64748b' }, axisLine: { lineStyle: { color: '#64748b' } }, splitLine: { lineStyle: { color: '#e2e8f0' } } },
      series: [
        { name: '循环Kt/V', type: 'bar', data: ktv, itemStyle: { color: '#4f46e5' } },
        { name: '循环超滤', type: 'bar', data: uf, itemStyle: { color: '#06b6d4' } },
        { name: 'β2M清除', type: 'line', smooth: true, showSymbol: false, data: beta2, lineStyle: { color: '#f97316', width: 2 } },
      ],
    },
    true,
  )
}

const deleteCustomRegimen = (id) => {
  if (!window.confirm('确定要删除这个方案吗？')) return
  customRegimens.value = customRegimens.value.filter((r) => r.id !== id)
  persistCustomRegimens()
  selectedPresets.value = selectedPresets.value.filter((p) => p !== `custom_${id}`)
  showToast('方案已删除', 'success')
}

const formatDate = (isoString) => {
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const runSimulation = async () => {
  if (!selectedPresets.value.length) {
    showToast('请先选择一个透析方案', 'info')
    return
  }
  const payload = loadPatientPayload()
  if (!payload) return

  loading.value = true
  simulationResult.value = null

  try {
    const selectedId = selectedPresets.value[0]
    const [type, id] = selectedId.split('_')
    let regimenData

    if (type === 'custom') {
      const regimen = customRegimens.value.find((r) => r.id === id)
      if (!regimen) {
        showToast('找不到该自定义方案', 'error')
        loading.value = false
        return
      }
      regimenData = { name: regimen.name, phases: regimen.phases }
    } else {
      const response = await fetch(`${API_BASE}/preset/${id}`)
      const data = await response.json()
      regimenData = data.regimen || {}
      if (!regimenData.name) regimenData.name = '预设方案'
    }

    currentRegimen.value = regimenData

    const response = await fetch(`${API_BASE}/simulate-regimen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: payload.patient,
        biomarkers: payload.biomarkers || {
          creatinine: 884,
          bun: 25.3,
          potassium: 4.8,
          sodium: 138
        },
        regimen: regimenData,
      }),
    })

    const data = await response.json()
    if (data.success) {
      simulationResult.value = data.results
      try {
        localStorage.setItem(
          'pd_last_simulation',
          JSON.stringify({
            at: new Date().toISOString(),
            regimen: regimenData,
            summary: data.results?.summary,
            results: data.results,
          }),
        )
      } catch (e) {
        console.error('保存最近一次模拟结果失败', e)
      }
      await nextTick()
      await nextTick()
      setTimeout(() => renderMainChart(), 30)
    } else {
      showToast('模拟失败: ' + data.error, 'error')
    }
  } catch (error) {
    console.error('模拟失败:', error)
    showToast('模拟失败，请检查后端是否正常运行', 'error')
  } finally {
    loading.value = false
  }
}

const compareRegimens = async () => {
  if (selectedPresets.value.length < 2) {
    showToast('请至少选择两个方案进行对比', 'info')
    return
  }
  const payload = loadPatientPayload()
  if (!payload) return

  loading.value = true
  comparisonResults.value = []

  try {
    for (const selectedId of selectedPresets.value) {
      const [type, id] = selectedId.split('_')
      let regimenData

      if (type === 'custom') {
        const regimen = customRegimens.value.find((r) => r.id === id)
        if (regimen) {
          regimenData = { name: regimen.name, phases: regimen.phases }
        }
      } else {
        const response = await fetch(`${API_BASE}/preset/${id}`)
        const data = await response.json()
        regimenData = data.regimen
      }

      if (regimenData) {
        const response = await fetch(`${API_BASE}/simulate-regimen`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            patient: payload.patient,
            biomarkers: payload.biomarkers,
            regimen: regimenData,
          }),
        })
        const data = await response.json()
        if (data.success) {
          comparisonResults.value.push({
            regimen_id: selectedId,
            regimen_name: regimenData.name,
            summary: data.results.summary,
          })
        }
      }
    }
    await nextTick()
    renderComparisonChart()
  } catch (error) {
    console.error('对比失败:', error)
  } finally {
    loading.value = false
  }
}

const renderMainChart = () => {
  if (!mainChartEl.value || !simulationResult.value) return

  const ts = simulationResult.value.time_series || {}
  const time = ts.time || []
  if (!time.length) return

  const allLabels = time.map((t) => Number(t).toFixed(0))
  const volumeL = (ts.volume || []).map((v) => (typeof v === 'number' ? v / 1000 : v))
  const crea = ts.creatinine_clearance || []
  const urea = ts.urea_clearance || []

  // v-if 切换后 DOM 会重建，旧实例需要重建绑定
  if (!mainChart || mainChart.getDom() !== mainChartEl.value) {
    if (mainChart) mainChart.dispose()
    mainChart = echarts.init(mainChartEl.value)
  }
  mainChart.resize()

  let reveal = 1
  const total = allLabels.length
  const step = Math.max(1, Math.floor(total / 200))

  const buildOption = (count) => ({
    backgroundColor: '#ffffff',
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 60, top: 35, bottom: 40 },
    xAxis: {
      type: 'category',
      data: allLabels.slice(0, count),
      name: '时间 (分钟)',
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#64748b' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: [
      {
        type: 'value',
        name: '液体积 (L)',
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
        splitLine: { lineStyle: { color: '#e2e8f0' } },
      },
      {
        type: 'value',
        name: '清除率 (μmol/min)',
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '腹腔液体积 (L)',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#4f46e5' },
        areaStyle: { color: '#e0e7ff' },
        data: volumeL.slice(0, count),
      },
      {
        name: '肌酐清除率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#06b6d4' },
        data: crea.slice(0, count),
      },
      {
        name: '尿素清除率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#f97316' },
        data: urea.slice(0, count),
      },
    ],
  })

  mainChart.setOption(buildOption(reveal), true)

  if (mainChartTimer) {
    clearInterval(mainChartTimer)
    mainChartTimer = null
  }
  mainChartTimer = setInterval(() => {
    if (!mainChart) {
      clearInterval(mainChartTimer)
      mainChartTimer = null
      return
    }
    reveal += step
    if (reveal >= total) {
      reveal = total
      clearInterval(mainChartTimer)
      mainChartTimer = null
    }
    mainChart.setOption(buildOption(reveal), false)
  }, 40)
}

const renderComparisonChart = () => {
  if (!compareChartEl.value || !comparisonResults.value.length) return

  const labels = comparisonResults.value.map((r) => r.regimen_name)
  const ktvData = comparisonResults.value.map((r) => r.summary.total_ktv)
  const ufData = comparisonResults.value.map((r) => r.summary.total_uf)
  const glucoseData = comparisonResults.value.map((r) => r.summary.total_glucose_absorbed)

  if (!compareChart || compareChart.getDom() !== compareChartEl.value) {
    if (compareChart) compareChart.dispose()
    compareChart = echarts.init(compareChartEl.value)
  }
  compareChart.resize()

  compareChart.setOption(
    {
      backgroundColor: '#ffffff',
      tooltip: { trigger: 'axis' },
      legend: { data: ['Kt/V', '超滤量 (L)', '葡萄糖吸收 (g)'], top: 8 },
      grid: { left: 50, right: 40, top: 40, bottom: 40 },
      xAxis: {
        type: 'category',
        data: labels,
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#64748b' } },
        axisLabel: { color: '#64748b' },
        splitLine: { lineStyle: { color: '#e2e8f0' } },
      },
      series: [
        {
          name: 'Kt/V',
          type: 'bar',
          data: ktvData,
          itemStyle: { color: '#4f46e5' },
        },
        {
          name: '超滤量 (L)',
          type: 'bar',
          data: ufData,
          itemStyle: { color: '#0ea5e9' },
        },
        {
          name: '葡萄糖吸收 (g)',
          type: 'line',
          data: glucoseData,
          smooth: true,
          lineStyle: { width: 2, color: '#f97316' },
          showSymbol: false,
        },
      ],
    },
    true,
  )
}

onBeforeUnmount(() => {
  if (mainChartTimer) {
    clearInterval(mainChartTimer)
    mainChartTimer = null
  }
  if (mainChart) {
    mainChart.dispose()
    mainChart = null
  }
  if (compareChart) {
    compareChart.dispose()
    compareChart = null
  }
  if (individualizedChart) {
    individualizedChart.dispose()
    individualizedChart = null
  }
  if (singleChart) {
    singleChart.dispose()
    singleChart = null
  }
  if (continuousChart) {
    continuousChart.dispose()
    continuousChart = null
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
  grid-template-columns: 1fr 1.8fr;
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
.hint {
  font-size: 12px;
  color: rgba(31, 35, 64, 0.65);
  margin-bottom: 10px;
  line-height: 1.6;
}
.patient-row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.patient-select {
  flex: 1;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: white;
}
.patient-tip {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 800;
  color: rgba(31, 35, 64, 0.9);
}
.section-card h2 {
  font-size: 18px;
  margin-bottom: 14px;
  border-bottom: 2px solid #667eea;
  padding-bottom: 6px;
}
.regimen-section {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 10px;
}
.section-title .icon {
  font-size: 18px;
}
.count-badge {
  margin-left: auto;
  padding: 2px 10px;
  background: #667eea;
  color: white;
  border-radius: 12px;
  font-size: 12px;
}
.preset-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.preset-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.preset-btn {
  width: 100%;
  background: #f8f9fa;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
}
.preset-btn.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-color: #667eea;
}
.preset-name {
  font-size: 14px;
  font-weight: 600;
}
.preset-badge {
  font-size: 12px;
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 8px;
  border-radius: 10px;
}
.save-presets-btn {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 0;
  cursor: pointer;
  background: #4caf50;
  color: white;
}
.custom-regimens-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}
.custom-regimen-item {
  background: #f8f9fa;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.regimen-actions {
  display: flex;
  gap: 6px;
}
.edit-btn {
  border: 0;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
}
.custom-regimen-item.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
  color: white;
}
.regimen-info {
  flex: 1;
}
.regimen-name {
  font-size: 14px;
  font-weight: 600;
}
.regimen-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
  opacity: 0.8;
}
.phase-count::before {
  content: '📋 ';
}
.created-time::before {
  content: '🕐 ';
}
.delete-btn {
  border: 0;
  background: rgba(244, 67, 54, 0.1);
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
}
.empty-custom {
  text-align: center;
  padding: 14px;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 13px;
  color: #999;
}
.btn-add-custom {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: 2px dashed #667eea;
  background: white;
  color: #667eea;
  cursor: pointer;
  font-weight: 600;
}
.action-buttons {
  display: flex;
  gap: 10px;
}
.btn-primary,
.btn-secondary {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: 0;
  cursor: pointer;
  font-weight: 700;
}
.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}
.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-secondary {
  background: white;
  color: #667eea;
  border: 2px solid #667eea;
}
.regimen-name-display {
  background: #f8f9fa;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 10px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.metric-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 10px 8px;
  border-radius: 8px;
  color: white;
  text-align: center;
}
.metric-icon {
  font-size: 20px;
}
.metric-value {
  font-size: 18px;
  font-weight: 700;
}
.metric-label {
  font-size: 11px;
  opacity: 0.9;
}
.chart-container {
  min-height: 420px;
  height: 420px;
  position: relative;
  width: 100%;
}
.chart-inner {
  display: block;
  width: 100% !important;
  height: 100% !important;
  max-height: 420px;
}
.comparison-chart-container {
  min-height: 360px;
  height: 360px;
}
.comparison-table-wrapper {
  margin-top: 14px;
  overflow-x: auto;
}
.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.comparison-table thead {
  background: #f8fafc;
}
.comparison-table th,
.comparison-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #e2e8f0;
  text-align: center;
  white-space: nowrap;
}
.comparison-table th {
  font-weight: 700;
  color: #1f2937;
}
.adequacy-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.adequacy-tag.ok {
  background: #dcfce7;
  color: #15803d;
}
.adequacy-tag.not-ok {
  background: #fee2e2;
  color: #b91c1c;
}
.research-card {
  margin-top: 14px;
}
.research-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.research-block {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px;
  background: #fff;
}
.research-block h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
.mini-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}
.mini-grid input,
.mini-grid select {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  width: 100%;
}
.research-result {
  margin-top: 8px;
  font-size: 12px;
  color: #1f2937;
  line-height: 1.6;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
}
.research-chart-wrap {
  margin-top: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}
.research-chart {
  width: 100%;
  height: 240px;
}
.cycle-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}
.cycle-item {
  display: grid;
  grid-template-columns: 56px 1fr 1fr 1fr 1fr 36px;
  gap: 6px;
  align-items: center;
}
.cycle-title {
  font-size: 12px;
  color: #475569;
}
.cycle-item input,
.cycle-item select {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  width: 100%;
}
.cycle-actions {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 6px;
  align-items: center;
}
.cycle-actions input {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
}
.btn-mini {
  border: 0;
  border-radius: 6px;
  background: #fee2e2;
  color: #b91c1c;
  padding: 5px 0;
  cursor: pointer;
}
.btn-mini:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.empty-state {
  text-align: center;
  padding: 40px 10px;
  color: #999;
}
.empty-icon {
  font-size: 50px;
  margin-bottom: 10px;
}
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: white;
  border-radius: 12px;
  width: min(800px, 100%);
  max-height: 90vh;
  overflow: auto;
}
.modal-header {
  padding: 16px 18px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-body {
  padding: 16px 18px;
}
.modal-footer {
  padding: 16px 18px;
  border-top: 1px solid #eee;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.close-btn {
  border: 0;
  background: none;
  font-size: 20px;
  cursor: pointer;
}
.phases-section {
  margin-top: 14px;
}
.phase-item {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.phase-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.phase-number {
  font-weight: 700;
  color: #667eea;
}
.btn-remove {
  border: 0;
  background: rgba(244, 67, 54, 0.1);
  border-radius: 6px;
  padding: 4px 8px;
  cursor: pointer;
}
.btn-add-phase {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: 2px dashed #667eea;
  background: white;
  color: #667eea;
  cursor: pointer;
  font-weight: 600;
}
.btn-cancel,
.btn-save {
  padding: 8px 14px;
  border-radius: 8px;
  border: 0;
  cursor: pointer;
  font-weight: 700;
}
.btn-cancel {
  background: #f0f0f0;
}
.btn-save {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}
@media (max-width: 1024px) {
  .main {
    grid-template-columns: 1fr;
  }
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .preset-buttons {
    grid-template-columns: 1fr;
  }
  .research-grid {
    grid-template-columns: 1fr;
  }
  .cycle-item {
    grid-template-columns: 1fr;
  }
  .cycle-actions {
    grid-template-columns: 1fr;
  }
}
</style>

