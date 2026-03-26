"""
ODE 版 24小时连续透析模拟（Phase 2+3 兼容）

要求：
- 每个循环只积分留腹期（dwell_only），引流阶段不参与 ODE 交换
- 每个循环结束后将残余液体的溶质浓度传递给下一循环的初始条件（用于混入新鲜透析液）
- fitted_parameters 可选：用于覆盖 ODE 基础参数（Phase3）
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from models.ode_single_exchange import run_single_dwell_ode, _map_transport, _normalize_biomarkers
from models.parameters import DialysisMode, ModelParameters, TransportType


def _apply_fitted_parameters(params: ModelParameters, fitted_parameters: Optional[Dict[str, Any]]) -> None:
    if not fitted_parameters or not isinstance(fitted_parameters, dict):
        return
    lps_scale = fitted_parameters.get("LpS_scale", None)
    ps_scale = fitted_parameters.get("ps_scale", None)
    lymph_scale = fitted_parameters.get("lymph_flow_scale", None)
    if lps_scale is not None:
        params.LpS = float(params.LpS) * float(lps_scale)
    if ps_scale is not None:
        for sol in params.solutes.values():
            sol.ps_product = float(sol.ps_product) * float(ps_scale)
    if lymph_scale is not None and hasattr(params, "lymph_flow"):
        params.lymph_flow = float(params.lymph_flow) * float(lymph_scale)


def _set_dialysate_concentrations_for_solution(
    params: ModelParameters, solution_type: str, concentration_pct: float
) -> None:
    stype = (solution_type or "glucose").lower()
    conc = float(concentration_pct)

    params.amino_acid_concentration_mmol = 0.0
    params.icodextrin_concentration_mmol = 0.0

    if "amino" in stype:
        amino_mw_g_per_mol = 150.0
        params.glucose_concentration = 0.0
        params.amino_acid_concentration_mmol = (conc * 10.0 / amino_mw_g_per_mol) * 1000.0
    elif "icod" in stype or "ico" in stype:
        ico_mw_g_per_mol = 15000.0
        params.glucose_concentration = 0.0
        params.icodextrin_concentration_mmol = (conc * 10.0 / ico_mw_g_per_mol) * 1000.0
    else:
        params.glucose_concentration = max(conc, 0.0)


def simulate_continuous_24h_ode(
    *,
    patient: Optional[Dict[str, Any]],
    biomarkers: Optional[Dict[str, Any]],
    cycles: List[Dict[str, Any]],
    drain_minutes: float,
    fitted_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    返回值包含：
    - total_peritoneal_ktv
    - creatinine_clearance
    - beta2m_clearance
    - total_uf_small_pore / total_uf_ultrasmall_pore / total_uf
    - cycles（每个循环的明细，前端可选使用）
    - time_series（拼接后的曲线）
    """
    patient = patient or {}
    biomarkers = biomarkers or {}
    drain_minutes = float(drain_minutes or 7.0)
    drain_minutes = max(drain_minutes, 1.0)

    # ===== 1) base params（应用 fitted_parameters 与血浆浓度）=====
    transport_type = _map_transport(patient.get("peritoneal_transport"))
    base_params = ModelParameters(transport_type=transport_type)
    base_params.dialysis_mode = DialysisMode.CAPD
    base_params.tidal_ratio = 1.0
    _apply_fitted_parameters(base_params, fitted_parameters)

    normalized = _normalize_biomarkers(biomarkers)
    for solute_key in ("urea", "creatinine", "glucose", "sodium", "beta2m"):
        if solute_key in base_params.solutes and solute_key in normalized:
            base_params.solutes[solute_key].plasma_concentration = normalized[solute_key]

    # g/L -> mmol/L 修正（与 single 一致）
    if "beta2m" in base_params.solutes:
        beta2m_solute = base_params.solutes["beta2m"]
        base_params.solutes["beta2m"].plasma_concentration = (
            beta2m_solute.plasma_concentration / beta2m_solute.molecular_weight * 1000.0
        )
    if "albumin" in base_params.solutes:
        albumin_solute = base_params.solutes["albumin"]
        base_params.solutes["albumin"].plasma_concentration = (
            albumin_solute.plasma_concentration / albumin_solute.molecular_weight * 1000.0
        )

    # ===== 2) 扫描循环，进行 dwell-only 积分并做残余量混入 =====
    total_peritoneal_ktv = 0.0
    total_creatinine_clearance = 0.0
    total_beta2m_clearance = 0.0
    total_uf_small = 0.0
    total_uf_ultrasmall = 0.0

    current_time = 0.0
    cycle_results: List[Dict[str, Any]] = []

    ts: Dict[str, List[float]] = {
        "time_min": [],
        "volume_l": [],
        "urea_clearance_rate": [],
        "beta2m_clearance_rate": [],
        "uf_rate": [],
    }

    # 初始残余浓度：假设残余液体中溶质浓度为 0（dry start）
    # 由于每个循环的“新鲜透析液浓度”由 solution_type 决定，所以初始残余浓度先按第一次循环的溶质键建立。
    residual_conc: Optional[Dict[str, float]] = None

    for idx, c in enumerate(cycles):
        solution_type = c.get("solution_type", "glucose")
        concentration_pct = float(c.get("concentration_pct", c.get("concentration", 1.5)) or 1.5)
        dwell_minutes = float(c.get("dwell_minutes", c.get("dwell_hours", 6) * 60) or 360)
        dwell_minutes = max(dwell_minutes, 10.0)
        fill_volume_l = float(c.get("fill_volume_l", c.get("fill_volume", 2.0)) or 2.0)

        V_fill_mL = fill_volume_l * 1000.0
        V_res_mL = float(base_params.residual_volume)
        V_total_mL = V_fill_mL + V_res_mL

        cycle_params = copy.deepcopy(base_params)
        cycle_params.fill_volume = V_total_mL
        _set_dialysate_concentrations_for_solution(cycle_params, solution_type, concentration_pct)
        cycle_params.dialysis_mode = DialysisMode.CAPD
        cycle_params.tidal_ratio = 1.0

        # 新鲜透析液浓度（用于与残余混入）
        C_fresh = cycle_params.get_initial_dialysate_concentrations()

        if residual_conc is None:
            residual_conc = {k: 0.0 for k in C_fresh.keys()}

        # 混入后起始浓度：C_mix = (C_res*V_res + C_fresh*V_fill) / (V_res+V_fill)
        C_mix: Dict[str, float] = {}
        for k, Cfd in C_fresh.items():
            Cres = float(residual_conc.get(k, 0.0))
            C_mix[k] = (Cres * V_res_mL + float(Cfd) * V_fill_mL) / max(V_total_mL, 1e-9)

        single = run_single_dwell_ode(
            params=cycle_params,
            solution_type=solution_type,
            concentration_pct=concentration_pct,
            dwell_minutes=dwell_minutes,
            fill_volume_l=fill_volume_l,
            drain_minutes=drain_minutes,
            patient=patient,
            initial_C_D_override=C_mix,
            dt=1.0,
            return_final_state=True,
        )

        s = single["summary"]
        total_peritoneal_ktv += float(s.get("peritoneal_ktv", 0.0) or 0.0)
        total_creatinine_clearance += float(s.get("creatinine_clearance", 0.0) or 0.0)
        total_beta2m_clearance += float(s.get("beta2m_clearance", 0.0) or 0.0)
        total_uf_small += float(s.get("uf_small_pore", 0.0) or 0.0)
        total_uf_ultrasmall += float(s.get("uf_ultrasmall_pore", 0.0) or 0.0)

        # 聚合 time_series（留腹段时间轴向后拼接；drain 仅通过 current_time 间隔体现）
        tmin = single["time_series"]["time_min"]
        ts["time_min"].extend([float(current_time + t) for t in tmin])
        ts["volume_l"].extend([float(x) for x in single["time_series"]["volume_l"]])
        ts["urea_clearance_rate"].extend([float(x) for x in single["time_series"]["urea_clearance_rate"]])
        ts["beta2m_clearance_rate"].extend([float(x) for x in single["time_series"]["beta2m_clearance_rate"]])
        ts["uf_rate"].extend([float(x) for x in single["time_series"]["uf_rate"]])

        # 残余浓度更新：引流只改变体积（留存浓度不变），因此用 dwell 末浓度作为残余浓度
        residual_conc = single.get("final_C_D")

        cycle_results.append({"cycle": idx + 1, **single})

        current_time += float(dwell_minutes + drain_minutes)

    total_uf = total_uf_small + total_uf_ultrasmall

    return {
        "total_peritoneal_ktv": round(float(total_peritoneal_ktv), 4),
        "creatinine_clearance": round(float(total_creatinine_clearance), 3),
        "beta2m_clearance": round(float(total_beta2m_clearance), 6),
        "total_uf_small_pore": round(float(total_uf_small), 3),
        "total_uf_ultrasmall_pore": round(float(total_uf_ultrasmall), 3),
        "total_uf": round(float(total_uf), 3),
        "duration_total_min": float(current_time),
        "cycles": cycle_results,
        "time_series": ts,
    }

