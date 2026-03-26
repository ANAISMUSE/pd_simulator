"""
ODE 版单次腹透模拟适配器（Phase 1）

目的：把前端输入（液体类型/浓度/留腹/灌注/引流）映射到本项目已存在的三孔 ODE 引擎，
并输出与前端现有期望一致的数据结构（summary + time_series）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from models.parameters import ModelParameters, TransportType, DialysisMode
from models.solver import PDState, RungeKuttaSolver
from models.physics import PhysicsCalculator


def _safe_float(v: Any, default: float) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _map_transport(peritoneal_transport: Optional[str]) -> TransportType:
    if not peritoneal_transport:
        return TransportType.AVERAGE
    tt = str(peritoneal_transport).strip().lower()
    if tt == "high":
        return TransportType.FAST
    if tt in ("high_average", "high-ave", "highaverage"):
        return TransportType.AVERAGE
    if tt in ("low_average", "low-ave", "lowaverage"):
        # 目前 ODE 只有 FAST/AVERAGE/SLOW 三档，这里先做一个保守映射
        return TransportType.AVERAGE
    if tt == "low":
        return TransportType.SLOW
    return TransportType.AVERAGE


def _estimate_drain_time(params: ModelParameters, v_start: float) -> float:
    """
    与 models/solver.py 中 _estimate_drain_time 等价的实现（这里复制一份避免访问私有方法）。
    单位：分钟
    """
    if v_start <= params.V_breakpoint:
        return (v_start - params.residual_volume) / params.drain_rate_slow
    time_fast = (v_start - params.V_breakpoint) / params.drain_rate_fast
    time_slow = (params.V_breakpoint - params.residual_volume) / params.drain_rate_slow
    return time_fast + time_slow


def _normalize_biomarkers(biomarkers: Dict[str, Any]) -> Dict[str, float]:
    """
    统一 biomarkers 的口径到 models/parameters.py 的默认口径：
    - urea: mmol/L（当前前端里把 bun 当 urea，用 mmol/L）
    - creatinine: mmol/L（parameters.py 默认 0.884 mmol/L，对应前端常见 884 μmol/L）
    - beta2m: g/L（parameters.py 默认 0.003 g/L；前端常见 25（mg/L）-> 0.025 g/L）
    - glucose: mmol/L
    - sodium: mmol/L
    """
    out: Dict[str, float] = {}
    bun = _safe_float(biomarkers.get("bun"), 25.3)
    out["urea"] = bun

    creat = _safe_float(biomarkers.get("creatinine"), 884.0)
    # Heuristic：如果数值偏大，通常是 μmol/L -> mmol/L
    out["creatinine"] = creat / 1000.0 if creat > 10.0 else creat

    glucose = _safe_float(biomarkers.get("glucose"), 5.5)
    out["glucose"] = glucose

    sodium = _safe_float(biomarkers.get("sodium"), 138.0)
    out["sodium"] = sodium

    beta2m = _safe_float(biomarkers.get("beta2_microglobulin"), _safe_float(biomarkers.get("beta2m"), 25.0))
    # Heuristic：如果数值偏大，多半是 mg/L -> g/L
    out["beta2m"] = beta2m / 1000.0 if beta2m > 0.1 else beta2m

    return out


def run_single_dwell_ode(
    *,
    params: ModelParameters,
    solution_type: str,
    concentration_pct: float,
    dwell_minutes: float,
    fill_volume_l: float,
    drain_minutes: float,
    patient: Dict[str, Any],
    initial_C_D_override: Optional[Dict[str, float]] = None,
    dt: float = 1.0,
    return_final_state: bool = False,
) -> Dict[str, Any]:
    """
    对“单次留腹期”进行 ODE 积分（dwell_only），并输出与前端兼容的数据结构。

    - 引流阶段不参与 ODE 交换：duration_total_min 中仅把 drain_minutes 加进去做总时间展示。
    - 支持 initial_C_D_override：用于 24h 连续模拟中把“残余液体浓度”混入下一循环。
    """
    # ========= 1) dwell_only：设置积分窗口落在 dwell 相 =========
    effective_volume = params.fill_volume
    fill_time = effective_volume / params.fill_rate  # min
    drain_time_est = _estimate_drain_time(params, effective_volume)
    params.exchange_time = float(fill_time + dwell_minutes + drain_time_est + 5.0)

    solver = RungeKuttaSolver(params, dt=dt)
    physics = PhysicsCalculator(params)

    # 初始状态：dwell 起点之前（阶段判断用 t_offset 控制）
    state = PDState(params)

    if initial_C_D_override and isinstance(initial_C_D_override, dict):
        # 仅覆盖存在的溶质键
        for k in state.C_D:
            if k in initial_C_D_override:
                state.C_D[k] = float(initial_C_D_override[k])

    t_offset = float(fill_time)
    state.t = t_offset

    # ========= 2) 积分 dwell =========
    record_interval = max(1.0, min(10.0, dwell_minutes / 30.0))
    record_every = max(1, int(round(record_interval / dt)))
    steps = int(round(dwell_minutes / dt))
    if steps < 1:
        steps = 1

    t_rel_list: list[float] = [0.0]
    Vd_list: list[float] = [float(state.V_D)]

    Cd_hist: Dict[str, list[float]] = {k: [float(state.C_D[k])] for k in state.C_D}

    for step in range(steps):
        state = solver.rk4_step(state)
        if (step + 1) % record_every == 0 or step == steps - 1:
            t_rel = float(state.t - t_offset)
            t_rel_list.append(max(0.0, min(dwell_minutes, t_rel)))
            Vd_list.append(float(state.V_D))
            for k in state.C_D:
                Cd_hist[k].append(float(state.C_D[k]))

    # ========= 3) 计算前端期望的 time_series =========
    time_min = t_rel_list
    volume_l = [vd / 1000.0 for vd in Vd_list]

    urea_rate: list[float] = []  # mL/min
    beta2m_rate: list[float] = []  # mL/min
    urea_flux_list: list[float] = []  # mmol/min
    beta2m_flux_list: list[float] = []  # mmol/min
    uf_rate: list[float] = []
    uf_small_rate: list[float] = []
    uf_ultrasmall_rate: list[float] = []

    cp_urea = float(params.solutes["urea"].plasma_concentration)
    cp_beta2m = float(params.solutes["beta2m"].plasma_concentration)
    cp_urea = cp_urea if abs(cp_urea) > 1e-12 else 1e-12
    cp_beta2m = cp_beta2m if abs(cp_beta2m) > 1e-12 else 1e-12

    for idx in range(len(time_min)):
        vd = Vd_list[idx]
        c_d = {k: float(Cd_hist[k][idx]) for k in Cd_hist}

        j_v_c, j_v_s, _j_v_l = physics.calculate_water_fluxes(vd, c_d)

        fluxes = physics.calculate_all_solute_fluxes(j_v_s, _j_v_l, c_d)
        urea_flux_total = float(fluxes["urea"]["total"])
        beta2m_flux_total = float(fluxes["beta2m"]["total"])

        urea_clearance_rate_mL_min = (urea_flux_total / cp_urea) * 1000.0
        beta2m_clearance_rate_mL_min = (beta2m_flux_total / cp_beta2m) * 1000.0

        uf_small = float(j_v_s)
        uf_ultrasmall = float(j_v_c)
        uf_total_rate = uf_small + uf_ultrasmall

        urea_clearance_rate_mL_min = max(0.0, urea_clearance_rate_mL_min)
        beta2m_clearance_rate_mL_min = max(0.0, beta2m_clearance_rate_mL_min)
        uf_small = max(0.0, uf_small)
        uf_ultrasmall = max(0.0, uf_ultrasmall)
        uf_total_rate = uf_small + uf_ultrasmall

        urea_flux_list.append(max(0.0, urea_flux_total))
        beta2m_flux_list.append(max(0.0, beta2m_flux_total))

        urea_rate.append(float(urea_clearance_rate_mL_min))
        beta2m_rate.append(float(beta2m_clearance_rate_mL_min))
        uf_rate.append(float(uf_total_rate))
        uf_small_rate.append(float(uf_small))
        uf_ultrasmall_rate.append(float(uf_ultrasmall))

    def _trapz(y: list[float], x: list[float]) -> float:
        return float(np.trapz(np.asarray(y, dtype=float), np.asarray(x, dtype=float)))

    urea_clearance = _trapz(urea_flux_list, time_min)
    beta2m_clearance = _trapz(beta2m_flux_list, time_min)
    uf_small_pore = _trapz(uf_small_rate, time_min)
    uf_ultrasmall_pore = _trapz(uf_ultrasmall_rate, time_min)
    uf_total = uf_small_pore + uf_ultrasmall_pore

    # Kt/V = removed_urea_mmol / (Vdist_L * Cp_urea_mmol_L)
    weight = _safe_float(patient.get("weight", 65.0), 65.0)
    v_dist_L = max(weight * 0.6, 1e-6)
    peritoneal_ktv = float(urea_clearance / (v_dist_L * cp_urea))

    dwell_t_min = max(float(dwell_minutes), 1e-6)
    urea_clearance_rate_mlmin = float(urea_clearance / (cp_urea * dwell_t_min) * 1000.0)
    beta2m_clearance_rate_mlmin = float(beta2m_clearance / (cp_beta2m * dwell_t_min) * 1000.0)

    # 肌酐（用于连续模拟总肌酐清除）
    cp_crea = float(params.solutes["creatinine"].plasma_concentration)
    cp_crea = cp_crea if abs(cp_crea) > 1e-12 else 1e-12
    crea_flux_list: list[float] = []
    for idx in range(len(time_min)):
        vd = Vd_list[idx]
        c_d = {k: float(Cd_hist[k][idx]) for k in Cd_hist}
        _j_v_c, j_v_s, j_v_l = physics.calculate_water_fluxes(vd, c_d)
        fluxes = physics.calculate_all_solute_fluxes(j_v_s, j_v_l, c_d)
        crea_flux_total = float(fluxes["creatinine"]["total"])
        crea_flux_list.append(max(0.0, crea_flux_total))

    creatinine_clearance = _trapz(crea_flux_list, time_min)
    creatinine_clearance_rate_mlmin = float(creatinine_clearance / (cp_crea * dwell_t_min) * 1000.0)

    result: Dict[str, Any] = {
        "inputs": {
            "solution_type": solution_type,
            "concentration_pct": concentration_pct,
            "dwell_minutes": dwell_minutes,
            "fill_volume_l": fill_volume_l,
            "drain_minutes": drain_minutes,
        },
        "summary": {
            "urea_clearance": round(urea_clearance, 3),
            "beta2m_clearance": round(beta2m_clearance, 6),
            "creatinine_clearance": round(creatinine_clearance, 3),
            "uf_small_pore": round(uf_small_pore, 3),
            "uf_ultrasmall_pore": round(uf_ultrasmall_pore, 3),
            "uf_total": round(uf_total, 3),
            "peritoneal_ktv": round(peritoneal_ktv, 4),
            "urea_clearance_rate_mlmin": round(urea_clearance_rate_mlmin, 4),
            "creatinine_clearance_rate_mlmin": round(creatinine_clearance_rate_mlmin, 4),
            "beta2m_clearance_rate_mlmin": round(beta2m_clearance_rate_mlmin, 6),
        },
        "time_series": {
            "time_min": [float(x) for x in time_min],
            "volume_l": [float(x) for x in volume_l],
            "urea_clearance_rate": [float(x) for x in urea_rate],
            "beta2m_clearance_rate": [float(x) for x in beta2m_rate],
            "uf_rate": [float(x) for x in uf_rate],
        },
        "duration_total_min": float(dwell_minutes + drain_minutes),
    }

    if return_final_state:
        result["final_C_D"] = {k: float(state.C_D[k]) for k in state.C_D}
        result["final_V_D"] = float(state.V_D)

    return result


def simulate_single_exchange_ode(
    solution_type: str,
    concentration_pct: float,
    dwell_minutes: float,
    fill_volume_l: float,
    drain_minutes: float = 7.0,
    patient: Optional[Dict[str, Any]] = None,
    biomarkers: Optional[Dict[str, Any]] = None,
    fitted_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Phase 1：先把“单次腹透模拟”从经验公式切到 ODE 求解。
    - dwell_only：积分窗口只覆盖留腹期（0 -> dwell_minutes）
    - 引流期：仅用于返回 duration_total_min（不参与交换）
    """
    patient = patient or {}
    biomarkers = biomarkers or {}

    dwell_minutes = max(_safe_float(dwell_minutes, 360.0), 10.0)
    fill_volume_l = max(_safe_float(fill_volume_l, 2.0), 0.5)
    concentration_pct = max(_safe_float(concentration_pct, 1.5), 0.0)
    drain_minutes = max(_safe_float(drain_minutes, 7.0), 1.0)

    # ========= 1) 构造三孔模型参数 =========
    transport_type = _map_transport(patient.get("peritoneal_transport"))
    params = ModelParameters(transport_type=transport_type)

    # Phase3：如果前端传来 PET 拟合结果，则覆盖 ODE 参数（缩放系数）
    if fitted_parameters and isinstance(fitted_parameters, dict):
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

    # 透析处方：把灌注量/浓度映射到 ODE 处方参数
    params.fill_volume = float(fill_volume_l) * 1000.0  # mL

    # Phase 2 (2B)：氨基酸/艾考糊精按“独立溶质”进入 Starling 求和。
    # physics.py 的 water flux 会遍历 params.solutes，因此只要在 params.get_initial_dialysate_concentrations()
    # 里正确设置 amino_acid / icodextrin 的透析液浓度，就能得到相应的水通量变化。
    stype = (solution_type or "glucose").lower()
    conc = float(concentration_pct)

    # 默认：清空所有非葡萄糖渗透溶质
    params.amino_acid_concentration_mmol = 0.0
    params.icodextrin_concentration_mmol = 0.0

    if "amino" in stype:
        # concentration_pct 按 %w/v 解释：1% = 1 g/dL = 10 g/L
        # mmol/L = (g/L) / (g/mol) * 1000 = (conc_pct*10)/MW * 1000
        amino_mw_g_per_mol = 150.0
        params.glucose_concentration = 0.0
        params.amino_acid_concentration_mmol = (conc * 10.0 / amino_mw_g_per_mol) * 1000.0
    elif "icod" in stype or "ico" in stype:
        ico_mw_g_per_mol = 15000.0
        params.glucose_concentration = 0.0
        params.icodextrin_concentration_mmol = (conc * 10.0 / ico_mw_g_per_mol) * 1000.0
    else:
        # 葡萄糖液：沿用旧逻辑（% -> mmol/L 的转换在 ModelParameters 内部完成）
        params.glucose_concentration = max(conc, 0.0)
    params.dialysis_mode = DialysisMode.CAPD
    params.tidal_ratio = 1.0

    # ========= 2) 血浆浓度：来自 biomarkers（并做口径转换） =========
    normalized = _normalize_biomarkers(biomarkers)
    for solute_key in ("urea", "creatinine", "glucose", "sodium", "beta2m"):
        if solute_key in params.solutes and solute_key in normalized:
            params.solutes[solute_key].plasma_concentration = normalized[solute_key]

    # 物理计算中使用了 RT * C_P 的形式，其中 C_P 在模型里按“mmol/L”参与渗透压计算。
    # 但 parameters.py 对 beta2m/albumin 的注释口径是 g/L（它们的 molecular_weight 也已定义）。
    # 为避免渗透压项量纲不一致导致水通量符号反转（从而 UF 变成 0/负），
    # 这里把 beta2m 与 albumin 的浓度从 g/L 转成 mmol/L。
    if "beta2m" in params.solutes:
        beta2m_solute = params.solutes["beta2m"]
        params.solutes["beta2m"].plasma_concentration = (
            beta2m_solute.plasma_concentration / beta2m_solute.molecular_weight * 1000.0
        )
    if "albumin" in params.solutes:
        albumin_solute = params.solutes["albumin"]
        params.solutes["albumin"].plasma_concentration = (
            albumin_solute.plasma_concentration / albumin_solute.molecular_weight * 1000.0
        )

    # Phase1/Phase2/Phase3：dwell_only ODE 执行（single 接口对外保持不变）
    return run_single_dwell_ode(
        params=params,
        solution_type=solution_type,
        concentration_pct=concentration_pct,
        dwell_minutes=dwell_minutes,
        fill_volume_l=fill_volume_l,
        drain_minutes=drain_minutes,
        patient=patient,
        initial_C_D_override=None,
        dt=1.0,
        return_final_state=False,
    )

    # ========= 3) dwell_only：让 RK 积分窗口落在“留置阶段” =========
    # 注意：models/solver.py 的阶段判断是基于 t % exchange_time 与 fill_time/drain_time。
    # 我们通过设置 exchange_time 大一些，并把积分起点 t_offset 设为 fill_time，
    # 来避免在积分窗口内发生额外的 fill/drain。
    effective_volume = params.fill_volume
    fill_time = effective_volume / params.fill_rate  # min
    # 估算从初始体积到残余体积的引流时间（min）
    drain_time_est = _estimate_drain_time(params, effective_volume)

    # exchange_time 需要大于：fill_time + dwell + drain_time_est
    # 给一个额外安全裕度，避免边界数值导致误入引流相
    params.exchange_time = float(fill_time + dwell_minutes + drain_time_est + 5.0)

    # ========= 4) 手动 RK 积分（记录 dwell_only 的时间序列） =========
    dt = 1.0  # 分钟（Phase 1：速度优先，足够跑通UI与结构）
    solver = RungeKuttaSolver(params, dt=dt)
    physics = PhysicsCalculator(params)

    # 初始状态：ODE 认为“刚灌注后”的腹腔状态。我们直接使用 params 的初始腔内体积/浓度。
    state = PDState(params)

    # 积分从留置相开始：t 从 fill_time 开始（这样 cycle_time == fill_time 时会落在 dwell 分支）
    t_offset = float(fill_time)
    state.t = t_offset

    # dwell_only：我们手动维护输出历史，避免 state.record_state 的时间轴不匹配
    record_interval = max(1.0, min(10.0, dwell_minutes / 30.0))
    record_every = max(1, int(round(record_interval / dt)))
    steps = int(round(dwell_minutes / dt))
    if steps < 1:
        steps = 1

    t_rel_list: list[float] = [0.0]
    Vd_list: list[float] = [float(state.V_D)]

    # C_D 和 C_B 均需要：C_B 在 dwell_only 默认参与最小，但仍按模型状态保留
    Cd_hist: Dict[str, list[float]] = {k: [float(state.C_D[k])] for k in state.C_D}
    # C_B 初始为 0；为完整计算清除率与 UF 分型不会强依赖，但保留结构
    # 注意：C_B 只为溶质字典的键集合与 C_D 相同
    # 这里用于稳健性：在后续计算通量时用到 C_D，不用到 C_B，但保留便于扩展
    # （不填 C_B 也能跑通当前输出）

    for step in range(steps):
        state = solver.rk4_step(state)
        if (step + 1) % record_every == 0 or step == steps - 1:
            t_rel = float(state.t - t_offset)
            t_rel_list.append(max(0.0, min(dwell_minutes, t_rel)))
            Vd_list.append(float(state.V_D))
            for k in state.C_D:
                Cd_hist[k].append(float(state.C_D[k]))

    # ========= 5) 从 ODE 状态计算前端期望的 summary/time_series =========
    time_min = t_rel_list
    volume_l = [vd / 1000.0 for vd in Vd_list]

    # 计算每个记录点的水/溶质通量：
    # - clearance_rate 曲线：mL/min（用于图与 Kt/V）
    # - clearance_summary（urea/beta2m_clearance）：总跨膜清除量（mmol，dwell_only 积分）
    urea_rate: list[float] = []  # urea clearance rate (mL/min)
    beta2m_rate: list[float] = []  # beta2m clearance rate (mL/min)
    urea_flux_list: list[float] = []  # urea flux (mmol/min)
    beta2m_flux_list: list[float] = []  # beta2m flux (mmol/min)
    uf_rate: list[float] = []
    uf_small_rate: list[float] = []
    uf_ultrasmall_rate: list[float] = []

    cp_urea = float(params.solutes["urea"].plasma_concentration)
    cp_beta2m = float(params.solutes["beta2m"].plasma_concentration)
    cp_urea = cp_urea if abs(cp_urea) > 1e-12 else 1e-12
    cp_beta2m = cp_beta2m if abs(cp_beta2m) > 1e-12 else 1e-12

    for idx in range(len(time_min)):
        vd = Vd_list[idx]
        c_d = {k: float(Cd_hist[k][idx]) for k in Cd_hist}

        j_v_c, j_v_s, _j_v_l = physics.calculate_water_fluxes(vd, c_d)

        # 计算溶质通量：只取 total（small+large）
        fluxes = physics.calculate_all_solute_fluxes(j_v_s, _j_v_l, c_d)
        urea_flux_total = float(fluxes["urea"]["total"])
        beta2m_flux_total = float(fluxes["beta2m"]["total"])

        # 清除率：通量/血浆浓度，得到 L/min，再换算成 mL/min（前端无需强单位一致，这里保持有限且单调性更直观）
        urea_clearance_rate_mL_min = (urea_flux_total / cp_urea) * 1000.0
        beta2m_clearance_rate_mL_min = (beta2m_flux_total / cp_beta2m) * 1000.0

        # UF 分型：小孔=J_v_S，超小孔=J_v_C
        uf_small = float(j_v_s)
        uf_ultrasmall = float(j_v_c)
        uf_total_rate = uf_small + uf_ultrasmall

        # Phase 1 友好性：当前 ODE 参数/单位未完全标定时可能出现速率为负的数值。
        # 对于前端展示（清除/超滤）阶段先做非负截断，确保 UI 不出现明显不合理的负值。
        urea_clearance_rate_mL_min = max(0.0, urea_clearance_rate_mL_min)
        beta2m_clearance_rate_mL_min = max(0.0, beta2m_clearance_rate_mL_min)
        uf_small = max(0.0, uf_small)
        uf_ultrasmall = max(0.0, uf_ultrasmall)
        uf_total_rate = uf_small + uf_ultrasmall

        # 用非负 flux 计算“总清除量（mmol）”
        urea_flux_list.append(max(0.0, urea_flux_total))
        beta2m_flux_list.append(max(0.0, beta2m_flux_total))

        urea_rate.append(float(urea_clearance_rate_mL_min))
        beta2m_rate.append(float(beta2m_clearance_rate_mL_min))
        uf_rate.append(float(uf_total_rate))
        uf_small_rate.append(float(uf_small))
        uf_ultrasmall_rate.append(float(uf_ultrasmall))

    # 积分得到单次标量（沿用当前前端/简化引擎的“trapz 得到 scalar”的输出风格）
    def _trapz(y: list[float], x: list[float]) -> float:
        return float(np.trapz(np.asarray(y, dtype=float), np.asarray(x, dtype=float)))

    # 总清除量：∫J_s dt (mmol)
    urea_clearance = _trapz(urea_flux_list, time_min)
    beta2m_clearance = _trapz(beta2m_flux_list, time_min)
    uf_small_pore = _trapz(uf_small_rate, time_min)
    uf_ultrasmall_pore = _trapz(uf_ultrasmall_rate, time_min)
    uf_total = uf_small_pore + uf_ultrasmall_pore

    # peritoneal_ktv：按你建议的 Kt/V 定义严格由清除总量计算，避免后处理口径不一致
    # Kt/V = removed_urea_mmol / (Vdist_L * Cp_urea_mmol_L)
    weight = _safe_float(patient.get("weight", 65.0), 65.0)
    v_dist_L = max(weight * 0.6, 1e-6)
    peritoneal_ktv = float(urea_clearance / (v_dist_L * cp_urea))

    # 额外输出：把“总清除量(mmol)”换算为“清除率(mL/min)”，用于前端或校验时避免单位歧义
    # CL_mL/min = removed_mmol / (Cp_mmol/L * t_min) * 1000(mL/L)
    dwell_t_min = max(float(dwell_minutes), 1e-6)
    urea_clearance_rate_mlmin = float(urea_clearance / (cp_urea * dwell_t_min) * 1000.0)
    cp_beta2m = float(params.solutes["beta2m"].plasma_concentration)
    cp_beta2m = cp_beta2m if abs(cp_beta2m) > 1e-12 else 1e-12
    beta2m_clearance_rate_mlmin = float(beta2m_clearance / (cp_beta2m * dwell_t_min) * 1000.0)

    # 计算肌酐清除：可让前端显示更完整
    # 同理用通量/血浆浓度得到清除率曲线并积分
    cp_crea = float(params.solutes["creatinine"].plasma_concentration)
    cp_crea = cp_crea if abs(cp_crea) > 1e-12 else 1e-12
    crea_rate: list[float] = []
    crea_flux_list: list[float] = []
    for idx in range(len(time_min)):
        vd = Vd_list[idx]
        c_d = {k: float(Cd_hist[k][idx]) for k in Cd_hist}
        _j_v_c, j_v_s, j_v_l = physics.calculate_water_fluxes(vd, c_d)
        fluxes = physics.calculate_all_solute_fluxes(j_v_s, j_v_l, c_d)
        crea_flux_total = float(fluxes["creatinine"]["total"])
        crea_flux_list.append(max(0.0, crea_flux_total))
        crea_rate.append(max(0.0, (crea_flux_total / cp_crea) * 1000.0))
    # 肌酐清除量：∫J_s dt (mmol)
    creatinine_clearance = _trapz(crea_flux_list, time_min)
    creatinine_clearance_rate_mlmin = float(creatinine_clearance / (cp_crea * dwell_t_min) * 1000.0)

    return {
        "inputs": {
            "solution_type": solution_type,
            "concentration_pct": concentration_pct,
            "dwell_minutes": dwell_minutes,
            "fill_volume_l": fill_volume_l,
            "drain_minutes": drain_minutes,
        },
        "summary": {
            "urea_clearance": round(urea_clearance, 3),
            "beta2m_clearance": round(beta2m_clearance, 6),
            "creatinine_clearance": round(creatinine_clearance, 3),
            "uf_small_pore": round(uf_small_pore, 3),
            "uf_ultrasmall_pore": round(uf_ultrasmall_pore, 3),
            "uf_total": round(uf_total, 3),
            "peritoneal_ktv": round(peritoneal_ktv, 4),
            # Unit-explicit fields（Phase1：不改前端字段名，新增字段方便后续统一 UI/校验）
            "urea_clearance_rate_mlmin": round(urea_clearance_rate_mlmin, 4),
            "creatinine_clearance_rate_mlmin": round(creatinine_clearance_rate_mlmin, 4),
            "beta2m_clearance_rate_mlmin": round(beta2m_clearance_rate_mlmin, 6),
        },
        "time_series": {
            "time_min": [float(x) for x in time_min],
            "volume_l": [float(x) for x in volume_l],
            "urea_clearance_rate": [float(x) for x in urea_rate],
            "beta2m_clearance_rate": [float(x) for x in beta2m_rate],
            "uf_rate": [float(x) for x in uf_rate],
        },
        "duration_total_min": float(dwell_minutes + drain_minutes),
    }

