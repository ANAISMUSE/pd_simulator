const KEY = 'pd_individualized_models'

export function defaultModelingInput() {
  return {
    pet: {
      d0: { creatinine: 120, glucose: 126, urea: 10, sodium: 132 },
      d2: { creatinine: 380, glucose: 90, urea: 8, sodium: 132 },
      d4: { creatinine: 520, glucose: 70, urea: 6, sodium: 132 },
    },
    blood_2h: { creatinine: 884, urea: 25.3, glucose: 5.5, sodium: 138 },
    urine_24h: { urine_volume_24h_ml: 500, urine_urea: 12, urine_creatinine: 9 },
  }
}

export function loadModelingForPatient(patientId) {
  if (patientId == null) return null
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const all = JSON.parse(raw)
    return all[String(patientId)] || null
  } catch {
    return null
  }
}

export function saveModelingForPatient(patientId, { modelingInput, result }) {
  if (patientId == null) return false
  try {
    const raw = localStorage.getItem(KEY)
    const all = raw ? JSON.parse(raw) : {}
    all[String(patientId)] = {
      modelingInput,
      result,
      updatedAt: new Date().toISOString(),
    }
    localStorage.setItem(KEY, JSON.stringify(all))
    return true
  } catch {
    return false
  }
}

export function clearModelingForPatient(patientId) {
  if (patientId == null) return
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return
    const all = JSON.parse(raw)
    delete all[String(patientId)]
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    /* ignore */
  }
}
