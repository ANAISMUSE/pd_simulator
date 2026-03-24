<template>
  <div class="page">
    <div class="header">
      <div class="title">优化算法模拟（可迭代对比）</div>
      <div class="subtitle">
        思路：先确定“基线指标”（原方案/原算法），然后每跑一轮优化就记录一次预测指标，并画在同一张坐标图里对比。
        你也可以在每一轮前手动收紧/放宽透析液与阶段范围，观察优化是否更容易达标。
      </div>
    </div>

    <div class="main">
      <div class="left">
        <div class="section-card">
          <h2>① 基线（原方案）</h2>
          <div class="hint">
            基线来自“方案模拟”页面最近一次模拟结果。请先在“方案模拟”跑一次你认为的原方案，再回来这里对比。
          </div>
          <button class="btn-secondary" @click="loadBaselineFromLastSim">从最近一次模拟载入基线</button>

          <div v-if="baseline" class="baseline-grid">
            <div class="kv"><span class="k">方案</span><span class="v">{{ baseline.regimenName }}</span></div>
            <div class="kv"><span class="k">Kt/V</span><span class="v">{{ baseline.summary.total_ktv }}</span></div>
            <div class="kv"><span class="k">UF(L)</span><span class="v">{{ baseline.summary.total_uf }}</span></div>
            <div class="kv">
              <span class="k">葡萄糖(g)</span><span class="v">{{ baseline.summary.total_glucose_absorbed }}</span>
            </div>
            <div class="kv">
              <span class="k">时长(h)</span><span class="v">{{ (Number(baseline.summary.total_duration) / 60).toFixed(1) }}</span>
            </div>
          </div>
          <div v-if="baseline" class="score-panel">
            <div class="score-head">
              <span>综合评分（0-100）</span>
              <strong>{{ baselineCompositeScore.toFixed(1) }}</strong>
            </div>
            <div class="score-bar">
              <div class="score-fill" :style="{ width: `${baselineCompositeScore}%` }"></div>
            </div>
            <div v-if="latestRound" class="score-sub">
              最新轮次评分：{{ latestCompositeScore.toFixed(1) }}
              <span :class="['delta', scoreDelta >= 0 ? 'up' : 'down']">
                {{ scoreDelta >= 0 ? '+' : '' }}{{ scoreDelta.toFixed(1) }}
              </span>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h2>② 目标与算法参数</h2>
          <div class="form-grid">
            <div class="form-group">
              <label>目标 Kt/V</label>
              <input v-model.number="targetKtV" type="number" step="0.1" min="1.0" max="3.0" />
            </div>
            <div class="form-group">
              <label>优化时长 (小时)</label>
              <input v-model.number="durationHours" type="number" step="1" min="4" max="48" />
            </div>
            <div class="form-group">
              <label>种群大小</label>
              <input v-model.number="populationSize" type="number" min="10" max="200" />
            </div>
            <div class="form-group">
              <label>迭代代数</label>
              <input v-model.number="generations" type="number" min="5" max="80" />
            </div>
          </div>
          <div class="weight-box">
            <div class="weight-title">综合评分权重（可调）</div>
            <div class="weight-row">
              <label>Kt/V</label>
              <input v-model.number="scoreWeights.ktv" type="range" min="0" max="100" step="1" />
              <span>{{ scoreWeights.ktv }}</span>
            </div>
            <div class="weight-row">
              <label>UF</label>
              <input v-model.number="scoreWeights.uf" type="range" min="0" max="100" step="1" />
              <span>{{ scoreWeights.uf }}</span>
            </div>
            <div class="weight-row">
              <label>葡萄糖</label>
              <input v-model.number="scoreWeights.glucose" type="range" min="0" max="100" step="1" />
              <span>{{ scoreWeights.glucose }}</span>
            </div>
            <div class="weight-hint">
              已自动归一化：Kt/V {{ normalizedWeights.ktv.toFixed(2) }}，UF {{ normalizedWeights.uf.toFixed(2) }}，葡萄糖 {{ normalizedWeights.glucose.toFixed(2) }}
            </div>
            <div class="weight-actions">
              <button class="btn-secondary" @click="resetScoreWeights">恢复默认权重(55/25/20)</button>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h2>③ 每轮可调：透析液/阶段范围（phase template）</h2>
          <div class="hint">
            这是给优化算法的“搜索范围”。你可以在每轮优化前调整（例如提高葡萄糖范围、增大灌注量范围、缩短/拉长留置时间范围），
            看是否更容易达到目标。
          </div>

          <div class="template-table">
            <div class="thead">
              <div>阶段</div>
              <div>留置(min)</div>
              <div>灌注(L)</div>
              <div>葡萄糖(%)</div>
              <div></div>
            </div>
            <div v-for="(t, idx) in phaseTemplate" :key="idx" class="trow">
              <div>
                <input v-model="t.phase_name" />
              </div>
              <div class="range">
                <input v-model.number="t.dwell_min[0]" type="number" step="10" min="30" />
                <span>~</span>
                <input v-model.number="t.dwell_min[1]" type="number" step="10" min="30" />
              </div>
              <div class="range">
                <input v-model.number="t.fill_volume_l[0]" type="number" step="0.1" min="0.5" />
                <span>~</span>
                <input v-model.number="t.fill_volume_l[1]" type="number" step="0.1" min="0.5" />
              </div>
              <div class="range">
                <input v-model.number="t.glucose_pct[0]" type="number" step="0.25" min="1.0" />
                <span>~</span>
                <input v-model.number="t.glucose_pct[1]" type="number" step="0.25" min="1.0" />
              </div>
              <div>
                <button class="btn-mini danger" :disabled="phaseTemplate.length <= 1" @click="removeTemplateRow(idx)">
                  删除
                </button>
              </div>
            </div>
          </div>

          <div class="row-actions">
            <button class="btn-secondary" @click="addTemplateRow">➕ 增加阶段</button>
            <button class="btn-secondary" @click="resetTemplate">重置默认范围</button>
          </div>

          <button class="btn-primary" :disabled="loading" @click="runOneRound">
            {{ loading ? '⏳ 优化中...' : '④ 运行一轮优化并记录' }}
          </button>
          <div v-if="loading" class="progress-wrap">
            <div class="progress-head">
              <span>优化进度</span>
              <span>{{ Math.round(progress * 100) }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: `${Math.round(progress * 100)}%` }"></div>
            </div>
            <div class="progress-sub">
              第 {{ progressGen }} / {{ progressTotal }} 代 · 当前最佳 fitness={{ progressBest.toFixed(4) }}
            </div>
          </div>

          <div class="row-actions">
            <button class="btn-secondary" :disabled="!rounds.length" @click="clearRounds">清空历史轮次</button>
          </div>
        </div>

        <div v-if="latestRound" class="section-card">
          <h2>⑤ 保存本轮最优方案</h2>
          <div class="form-group">
            <label>方案名称</label>
            <input v-model="saveName" placeholder="例如：第3轮-优化方案" />
          </div>
          <button class="btn-secondary" @click="saveLatestToCustom">💾 保存到“我的方案”</button>
        </div>
      </div>

      <div class="right">
        <div class="section-card">
          <h2>对比坐标图（基线 vs 每轮优化）</h2>
          <div class="chart-container">
            <canvas ref="historyChartCanvas"></canvas>
          </div>
          <div class="hint" style="margin-top: 8px">
            图里第 0 个点是“基线”，后面的点是你每次点“运行一轮优化并记录”得到的结果。
          </div>
        </div>

        <div class="section-card">
          <h2>完整曲线对比（基线 vs 某一轮）</h2>
          <div class="row-actions" style="margin-top: 0">
            <button class="btn-secondary" :disabled="!baselineResults" @click="renderCurveChart">
              刷新曲线图
            </button>
            <div style="margin-left: auto; display: flex; gap: 8px; align-items: center">
              <span style="font-size: 12px; color: rgba(31,35,64,.65)">选择轮次</span>
              <select v-model.number="selectedRound" class="select">
                <option :value="0">最新</option>
                <option v-for="r in rounds" :key="r.round" :value="r.round">第 {{ r.round }} 轮</option>
              </select>
            </div>
          </div>
          <div class="curve-chart">
            <canvas ref="curveChartCanvas"></canvas>
          </div>
          <div class="hint" style="margin-top: 8px">
            曲线来自后端 `simulate-regimen` 的 time-series（腹腔液体积、尿素/肌酐清除率等）。若基线没有曲线，请先去“方案模拟”重新跑一次。
          </div>
        </div>

        <div class="section-card">
          <h2>轮次记录</h2>
          <div v-if="!rounds.length" class="empty-state">暂无轮次记录</div>
          <div v-else class="round-list">
            <div v-for="r in rounds" :key="r.round" class="round-item">
              <div class="round-title">第 {{ r.round }} 轮</div>
              <div class="round-meta">
                <span>Kt/V={{ r.summary.total_ktv }}</span>
                <span>UF={{ r.summary.total_uf }}</span>
                <span>糖={{ r.summary.total_glucose_absorbed }}</span>
                <span>评分={{ calcCompositeScore(r.summary).toFixed(1) }}</span>
                <span>耗时={{ (Number(r.summary.total_duration) / 60).toFixed(1) }}h</span>
                <span :class="['tag', r.summary.total_ktv >= targetKtV ? 'ok' : 'bad']">
                  {{ r.summary.total_ktv >= targetKtV ? '达标' : '未达标' }}
                </span>
              </div>
              <div class="round-sub">
                <span>参数：pop={{ r.params.population_size }}, gen={{ r.params.generations }}, hours={{ r.params.duration_hours }}</span>
              </div>
              <div class="round-sub">
                <span>范围：{{ r.template.map(t => `${t.phase_name}[${t.dwell_min[0]}~${t.dwell_min[1]}]min`).join('；') }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Chart, registerables } from 'chart.js'
import { showToast } from '../utils/toast'

Chart.register(...registerables)

const API_BASE = 'http://localhost:5000/api'

const targetKtV = ref(1.7)
const durationHours = ref(24)
const populationSize = ref(40)
const generations = ref(25)
const loading = ref(false)
const progress = ref(0)
const progressGen = ref(0)
const progressTotal = ref(0)
const progressBest = ref(0)

const baseline = ref(null) // { regimenName, summary }
const baselineResults = ref(null) // full results for curves
const rounds = ref([]) // [{round, summary, params, template, phases}]
const saveName = ref('')

const historyChartCanvas = ref(null)
const curveChartCanvas = ref(null)
const selectedRound = ref(0)

const latestRound = computed(() => (rounds.value.length ? rounds.value[rounds.value.length - 1] : null))
const scoreWeights = ref({
  ktv: 55,
  uf: 25,
  glucose: 20,
})
const normalizedWeights = computed(() => {
  const k = Number(scoreWeights.value.ktv || 0)
  const u = Number(scoreWeights.value.uf || 0)
  const g = Number(scoreWeights.value.glucose || 0)
  const sum = Math.max(k + u + g, 1)
  return {
    ktv: k / sum,
    uf: u / sum,
    glucose: g / sum,
  }
})
const resetScoreWeights = () => {
  scoreWeights.value.ktv = 55
  scoreWeights.value.uf = 25
  scoreWeights.value.glucose = 20
}
const calcCompositeScore = (summary) => {
  if (!summary) return 0
  const ktv = Number(summary.total_ktv || 0)
  const uf = Number(summary.total_uf || 0)
  const glucose = Number(summary.total_glucose_absorbed || 0)

  // Kt/V 越接近目标越好；达标后仍保留分差（避免“一刀切”）
  const ktvScore = Math.max(0, 100 - Math.abs(ktv - Number(targetKtV.value || 1.7)) * 120)
  // UF 目标区间粗设为 80~150（与当前模型量级匹配）
  const ufCenter = 115
  const ufScore = Math.max(0, 100 - Math.abs(uf - ufCenter) * 1.2)
  // 葡萄糖吸收越低越好
  const glucoseScore = Math.max(0, 100 - glucose * 0.8)

  return (
    ktvScore * normalizedWeights.value.ktv +
    ufScore * normalizedWeights.value.uf +
    glucoseScore * normalizedWeights.value.glucose
  )
}
const baselineCompositeScore = computed(() => calcCompositeScore(baseline.value?.summary))
const latestCompositeScore = computed(() => calcCompositeScore(latestRound.value?.summary))
const scoreDelta = computed(() => latestCompositeScore.value - baselineCompositeScore.value)

const phaseTemplate = ref([])

const defaultTemplate = () => [
  {
    phase_name: '阶段1',
    dwell_min: [120, 360],
    fill_volume_l: [1.5, 2.5],
    glucose_pct: [1.5, 4.25],
  },
]

const persistRounds = () => {
  try {
    localStorage.setItem('pd_opt_rounds', JSON.stringify(rounds.value))
  } catch (e) {
    console.error(e)
  }
}

const loadRounds = () => {
  try {
    const raw = localStorage.getItem('pd_opt_rounds')
    rounds.value = raw ? JSON.parse(raw) : []
  } catch {
    rounds.value = []
  }
}

const loadBaselineFromLastSim = () => {
  try {
    const raw = localStorage.getItem('pd_last_simulation')
    if (!raw) {
      showToast('没有找到最近一次模拟结果。请先去“方案模拟”跑一次模拟。')
      return
    }
    const data = JSON.parse(raw)
    if (!data?.summary) {
      showToast('最近一次模拟结果不完整，请重新模拟一次。')
      return
    }
    baseline.value = {
      regimenName: data?.regimen?.name || '基线方案',
      summary: data.summary,
    }
    baselineResults.value = data?.results || null
    renderHistoryChart()
    renderCurveChart()
  } catch (e) {
    console.error(e)
    showToast('读取基线失败，请重新模拟一次。')
  }
}

const loadPatientPayload = () => {
  const raw = localStorage.getItem('pd_current_patient')
  if (!raw) {
    showToast('请先在“患者信息”页面填写并保存患者，再进行优化。')
    return null
  }
  try {
    const data = JSON.parse(raw)
    return { patient: data.patient, biomarkers: data.biomarkers }
  } catch (e) {
    console.error(e)
    showToast('本地患者信息损坏，请重新在“患者信息”页保存。')
    return null
  }
}

const toBackendPhaseTemplate = () =>
  phaseTemplate.value.map((t) => ({
    phase_name: t.phase_name,
    dwell_range: [Number(t.dwell_min[0]), Number(t.dwell_min[1])],
    fill_volume_range: [Number(t.fill_volume_l[0]), Number(t.fill_volume_l[1])],
    glucose_range: [Number(t.glucose_pct[0]), Number(t.glucose_pct[1])],
  }))

const runOneRound = async () => {
  const payload = loadPatientPayload()
  if (!payload) return

  if (!baseline.value) {
    window.alert('建议先载入基线（原方案指标），否则无法直观看出优化效果。')
  }

  loading.value = true
  progress.value = 0
  progressGen.value = 0
  progressTotal.value = generations.value
  progressBest.value = 0
  try {
    // 先启动异步任务
    const startResp = await fetch(`${API_BASE}/optimize/freeform/async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: payload.patient,
        biomarkers: payload.biomarkers,
        target_ktv: targetKtV.value,
        simulation_minutes: durationHours.value * 60,
        population_size: populationSize.value,
        generations: generations.value,
        phase_template: toBackendPhaseTemplate(),
      }),
    })
    const startData = await startResp.json().catch(() => ({}))
    if (!startData.success || !startData.job_id) {
      window.alert(startData.error || '启动优化失败')
      return
    }
    const jobId = startData.job_id

    // 轮询进度
    const poll = async () => {
      const r = await fetch(`${API_BASE}/optimize/jobs/${jobId}`)
      const d = await r.json().catch(() => ({}))
      if (!d.success || !d.job) throw new Error(d.error || '获取进度失败')
      const job = d.job
      progress.value = Number(job.progress || 0)
      progressGen.value = Number(job.current_generation || 0)
      progressTotal.value = Number(job.total_generations || generations.value)
      progressBest.value = Number(job.best_fitness || 0)
      return job
    }

    let job = await poll()
    while (job.status === 'running') {
      await new Promise((res) => setTimeout(res, 400))
      job = await poll()
    }
    if (job.status !== 'done') {
      window.alert(job.error || '优化失败')
      return
    }

    const result = job.result
    if (!result) {
      window.alert('优化结果为空')
      return
    }

    const predicted = result.predicted?.summary
    if (!predicted) {
      window.alert('后端没有返回可对比的预测 summary（请确认后端已更新）。')
      return
    }

    const prescription = result.prescription || {}
    const phases = prescription.phases || []

    // 再跑一次完整模拟，拿到 time-series（用于曲线对比）
    let simResults = null
    try {
      const simResp = await fetch(`${API_BASE}/simulate-regimen`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient: payload.patient,
          biomarkers: payload.biomarkers,
          regimen: { name: `Round`, phases },
        }),
      })
      const simData = await simResp.json().catch(() => ({}))
      if (simData.success) simResults = simData.results
    } catch (e) {
      console.error('run simulate-regimen failed', e)
    }

    const nextRound = rounds.value.length ? rounds.value[rounds.value.length - 1].round + 1 : 1
    const entry = {
      round: nextRound,
      at: new Date().toISOString(),
      summary: predicted,
      params: {
        target_ktv: targetKtV.value,
        duration_hours: durationHours.value,
        population_size: populationSize.value,
        generations: generations.value,
      },
      template: JSON.parse(JSON.stringify(phaseTemplate.value)),
      phases,
      simResults,
    }
    rounds.value.push(entry)
    persistRounds()

    if (!saveName.value) saveName.value = `第${nextRound}轮-优化方案`

    renderHistoryChart()
    renderCurveChart()
  } catch (e) {
    console.error(e)
    window.alert('优化失败，请检查后端是否正常运行')
  } finally {
    loading.value = false
  }
}

const saveLatestToCustom = () => {
  const r = latestRound.value
  if (!r) return

  const name = (saveName.value || `第${r.round}轮-优化方案`).trim()
  const phases = (r.phases || []).map((p, idx) => ({
    phase_name: p.phase_name || `阶段${idx + 1}`,
    duration: (p.dwell_min || 0) / 60,
    glucose_conc: p.glucose_pct,
    fill_volume: p.fill_volume_l,
  }))
  if (!phases.length) {
    window.alert('没有阶段数据，无法保存为方案')
    return
  }

  let list = []
  try {
    const raw = localStorage.getItem('customRegimens')
    list = raw ? JSON.parse(raw) : []
  } catch {
    list = []
  }
  list.push({ id: Date.now().toString(), name, phases, createdAt: new Date().toISOString() })
  localStorage.setItem('customRegimens', JSON.stringify(list))
  window.alert('已保存到“我的方案”（去“方案模拟”页选择使用）')
}

const addTemplateRow = () => {
  const n = phaseTemplate.value.length + 1
  phaseTemplate.value.push({
    phase_name: `阶段${n}`,
    dwell_min: [120, 360],
    fill_volume_l: [1.5, 2.5],
    glucose_pct: [1.5, 4.25],
  })
}

const removeTemplateRow = (idx) => {
  if (phaseTemplate.value.length <= 1) return
  phaseTemplate.value.splice(idx, 1)
}

const resetTemplate = () => {
  phaseTemplate.value = defaultTemplate()
}

const clearRounds = () => {
  if (!window.confirm('确定清空所有轮次记录吗？')) return
  rounds.value = []
  persistRounds()
  renderHistoryChart()
}

const renderHistoryChart = () => {
  if (!historyChartCanvas.value) return
  const ctx = historyChartCanvas.value.getContext('2d')
  if (!ctx) return

  const labels = []
  const ktv = []
  const uf = []
  const glucose = []

  if (baseline.value?.summary) {
    labels.push('基线')
    ktv.push(Number(baseline.value.summary.total_ktv))
    uf.push(Number(baseline.value.summary.total_uf))
    glucose.push(Number(baseline.value.summary.total_glucose_absorbed))
  }

  for (const r of rounds.value) {
    labels.push(`第${r.round}轮`)
    ktv.push(Number(r.summary.total_ktv))
    uf.push(Number(r.summary.total_uf))
    glucose.push(Number(r.summary.total_glucose_absorbed))
  }

  if (historyChartCanvas.value.chart) historyChartCanvas.value.chart.destroy()

  const targetLine = labels.map(() => Number(targetKtV.value))

  historyChartCanvas.value.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Kt/V',
          data: ktv,
          borderColor: 'rgb(54, 162, 235)',
          backgroundColor: 'rgba(54, 162, 235, 0.12)',
          yAxisID: 'y',
          tension: 0.25,
        },
        {
          label: '目标 Kt/V',
          data: targetLine,
          borderColor: 'rgba(244, 67, 54, 0.9)',
          backgroundColor: 'rgba(244, 67, 54, 0.0)',
          yAxisID: 'y',
          borderDash: [6, 6],
          pointRadius: 0,
          tension: 0,
        },
        {
          label: 'UF (L)',
          data: uf,
          borderColor: 'rgb(75, 192, 192)',
          backgroundColor: 'rgba(75, 192, 192, 0.12)',
          yAxisID: 'y1',
          tension: 0.25,
        },
        {
          label: '葡萄糖吸收 (g)',
          data: glucose,
          borderColor: 'rgb(255, 159, 64)',
          backgroundColor: 'rgba(255, 159, 64, 0.12)',
          yAxisID: 'y2',
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top' },
      },
      scales: {
        y: {
          position: 'left',
          title: { display: true, text: 'Kt/V' },
        },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          title: { display: true, text: 'UF (L)' },
        },
        y2: {
          position: 'right',
          grid: { drawOnChartArea: false },
          title: { display: true, text: '葡萄糖吸收 (g)' },
          offset: true,
        },
      },
    },
  })
}

const renderCurveChart = () => {
  if (!curveChartCanvas.value) return
  const ctx = curveChartCanvas.value.getContext('2d')
  if (!ctx) return
  if (!baselineResults.value?.time_series) return

  // 选择轮次：0=最新
  const roundEntry =
    selectedRound.value === 0
      ? latestRound.value
      : rounds.value.find((r) => r.round === selectedRound.value)

  const roundResults = roundEntry?.simResults
  if (!roundResults?.time_series) {
    // 没有本轮 time-series，就只画基线
  }

  const baseTs = baselineResults.value.time_series
  const baseLabels = (baseTs.time || []).map((t) => Number(t).toFixed(0))

  const datasets = [
    {
      label: '基线：腹腔液体积(L)',
      data: baseTs.volume || [],
      borderColor: 'rgba(54, 162, 235, 0.9)',
      backgroundColor: 'rgba(54, 162, 235, 0.08)',
      yAxisID: 'y',
      pointRadius: 0,
      tension: 0.2,
    },
    {
      label: '基线：尿素清除率',
      data: baseTs.urea_clearance || [],
      borderColor: 'rgba(255, 159, 64, 0.9)',
      backgroundColor: 'rgba(255, 159, 64, 0.08)',
      yAxisID: 'y1',
      pointRadius: 0,
      tension: 0.2,
    },
  ]

  if (roundResults?.time_series) {
    const ts = roundResults.time_series
    datasets.push(
      {
        label: `第${roundEntry.round}轮：腹腔液体积(L)`,
        data: ts.volume || [],
        borderColor: 'rgba(153, 102, 255, 0.9)',
        backgroundColor: 'rgba(153, 102, 255, 0.06)',
        yAxisID: 'y',
        pointRadius: 0,
        tension: 0.2,
      },
      {
        label: `第${roundEntry.round}轮：尿素清除率`,
        data: ts.urea_clearance || [],
        borderColor: 'rgba(75, 192, 192, 0.9)',
        backgroundColor: 'rgba(75, 192, 192, 0.06)',
        yAxisID: 'y1',
        pointRadius: 0,
        tension: 0.2,
      },
    )
  }

  if (curveChartCanvas.value.chart) curveChartCanvas.value.chart.destroy()
  curveChartCanvas.value.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: baseLabels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top' } },
      scales: {
        y: { position: 'left', title: { display: true, text: '腹腔液体积 (L)' } },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          title: { display: true, text: '尿素清除率' },
        },
      },
    },
  })
}

onMounted(() => {
  phaseTemplate.value = defaultTemplate()
  loadRounds()
  // 尝试自动载入基线（如果你刚在“方案模拟”跑过）
  loadBaselineFromLastSim()
  // 初次渲染
  setTimeout(renderHistoryChart, 0)
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
  line-height: 1.6;
}
.main {
  display: grid;
  grid-template-columns: 1.2fr 1.3fr;
  gap: 16px;
}
.section-card {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
  margin-bottom: 12px;
}
.section-card h2 {
  font-size: 16px;
  margin-bottom: 10px;
  border-bottom: 2px solid #667eea;
  padding-bottom: 6px;
}
.hint {
  font-size: 13px;
  color: rgba(31, 35, 64, 0.7);
  margin-bottom: 10px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
label {
  font-size: 13px;
  font-weight: 700;
}
input {
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}
.btn-primary {
  width: 100%;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 0;
  cursor: pointer;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-secondary {
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
  cursor: pointer;
  font-weight: 700;
}
.baseline-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 10px;
}
.kv {
  display: flex;
  justify-content: space-between;
  background: #f8f9fa;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
}
.k {
  color: #666;
  font-weight: 700;
}
.v {
  color: #1f2340;
  font-weight: 800;
}
.score-panel {
  margin-top: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
  background: #f8fafc;
}
.score-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #1f2937;
}
.score-head strong {
  font-size: 16px;
  color: #4f46e5;
}
.score-bar {
  height: 8px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;
  margin-top: 6px;
}
.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa 0%, #4f46e5 100%);
  transition: width 0.35s ease;
}
.score-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #475569;
}
.delta {
  margin-left: 6px;
  font-weight: 700;
}
.delta.up {
  color: #16a34a;
}
.delta.down {
  color: #dc2626;
}
.weight-box {
  margin-top: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  padding: 10px;
  background: #f8fafc;
}
.weight-title {
  font-size: 13px;
  font-weight: 800;
  color: #1f2340;
  margin-bottom: 8px;
}
.weight-row {
  display: grid;
  grid-template-columns: 56px 1fr 36px;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}
.weight-row input[type='range'] {
  width: 100%;
}
.weight-hint {
  margin-top: 4px;
  font-size: 11px;
  color: #64748b;
}
.weight-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}
.template-table {
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  overflow: hidden;
}
.thead,
.trow {
  display: grid;
  grid-template-columns: 1.1fr 1.3fr 1.2fr 1.2fr 0.6fr;
  gap: 8px;
  align-items: center;
  padding: 10px;
}
.thead {
  background: #f4f6ff;
  font-size: 12px;
  font-weight: 800;
  color: #1f2340;
}
.trow {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}
.range {
  display: flex;
  align-items: center;
  gap: 6px;
}
.range input {
  width: 100%;
}
.btn-mini {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: white;
  cursor: pointer;
  font-weight: 700;
  font-size: 12px;
}
.btn-mini.danger {
  border-color: rgba(244, 67, 54, 0.35);
  color: #c62828;
}
.row-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}
.progress-wrap {
  margin-top: 12px;
  padding: 10px;
  border-radius: 12px;
  background: #f8f9fa;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.progress-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 900;
  color: rgba(31, 35, 64, 0.8);
  margin-bottom: 8px;
}
.progress-bar {
  height: 10px;
  background: rgba(102, 126, 234, 0.12);
  border-radius: 999px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  width: 0%;
  transition: width 0.3s ease;
}
.progress-sub {
  margin-top: 8px;
  font-size: 12px;
  color: rgba(31, 35, 64, 0.65);
}
.chart-container {
  height: 420px;
}
.curve-chart {
  height: 420px;
  margin-top: 10px;
}
.select {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: white;
}
.empty-state {
  padding: 20px;
  color: #999;
}
.round-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.round-item {
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  padding: 10px;
  background: white;
}
.round-title {
  font-weight: 900;
  margin-bottom: 6px;
}
.round-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: rgba(31, 35, 64, 0.85);
  margin-bottom: 4px;
}
.round-sub {
  font-size: 12px;
  color: rgba(31, 35, 64, 0.65);
  margin-top: 4px;
}
.tag {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 800;
}
.tag.ok {
  background: rgba(76, 175, 80, 0.12);
  color: #2e7d32;
}
.tag.bad {
  background: rgba(244, 67, 54, 0.12);
  color: #c62828;
}
@media (max-width: 1024px) {
  .main {
    grid-template-columns: 1fr;
  }
  .thead,
  .trow {
    grid-template-columns: 1fr;
  }
}
</style>

