"""
Phase 3：基于 PET 数据的参数拟合（最小实现）

当前目标：拟合 ODE 三孔模型中的两个缩放系数，用于尽量匹配 PET
在 0/2/4 小时的透析液浓度变化（主要拟合 urea/creatinine/glucose）。

输出 fitted_parameters 将在 single-exchange 中透传并用于覆盖 ODE 参数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
from scipy.optimize import least_squares

from models.parameters import ModelParameters, TransportType
from models.solver import PDState, RungeKuttaSolver
from models.physics import PhysicsCalculator


def _safe_float(v: Any, default: float) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _convert_creatinine_to_mmol_per_l(x: Any) -> float:
    """
    PET 输入创氨酸口径不明确：
    - 前端 common 默认 creatinine = 120/380/520/884（通常是 umol/L）
    - ODE 内置默认 creatinine plasma 期望 mmol/L
    策略：若数值较大（>10），按 umol/L -> mmol/L（/1000）。
    """
    v = _safe_float(x, 0.0)
    if abs(v) > 10.0:
        return v / 1000.0
    return v


def _pet_get_block(pet: Dict[str, Any], key: str) -> Dict[str, Any]:
    return dict(pet.get(key, {}) or {})


@dataclass
class PetSimResult:
    # 透析液浓度在 t=0/120/240min 的模拟值
    urea: List[float]
    creatinine: List[float]
    glucose: List[float]


def simulate_pet_dwell(
    params: ModelParameters,
    pet: Dict[str, Any],
    plasma: Dict[str, float],
    total_minutes: float = 240.0,
    dt_minutes: float = 2.0,
) -> PetSimResult:
    """
    以“留置阶段”近似 PET 的 0->4h 动力学（不包含 fill/drain 的显式过程）。
    通过设置 exchange_time 足够大，保证积分期间处于 dwell。
    """
    d0 = _pet_get_block(pet, "d0")
    d2 = _pet_get_block(pet, "d2")
    d4 = _pet_get_block(pet, "d4")

    # 设置血浆浓度（常数）
    if "urea" in params.solutes:
        params.solutes["urea"].plasma_concentration = float(plasma.get("urea", params.solutes["urea"].plasma_concentration))
    if "creatinine" in params.solutes:
        params.solutes["creatinine"].plasma_concentration = float(plasma.get("creatinine", params.solutes["creatinine"].plasma_concentration))
    if "glucose" in params.solutes:
        params.solutes["glucose"].plasma_concentration = float(plasma.get("glucose", params.solutes["glucose"].plasma_concentration))
    if "sodium" in params.solutes:
        params.solutes["sodium"].plasma_concentration = float(plasma.get("sodium", params.solutes["sodium"].plasma_concentration))
    if "beta2m" in params.solutes:
        params.solutes["beta2m"].plasma_concentration = float(plasma.get("beta2m", params.solutes["beta2m"].plasma_concentration))
    if "albumin" in params.solutes:
        params.solutes["albumin"].plasma_concentration = float(plasma.get("albumin", params.solutes["albumin"].plasma_concentration))

    # 用 PET 的 d0 作为初始透析液浓度
    state = PDState(params)
    if "urea" in state.C_D:
        state.C_D["urea"] = _safe_float(d0.get("urea"), state.C_D["urea"])
    if "creatinine" in state.C_D:
        state.C_D["creatinine"] = _convert_creatinine_to_mmol_per_l(d0.get("creatinine"))
    if "glucose" in state.C_D:
        state.C_D["glucose"] = _safe_float(d0.get("glucose"), state.C_D["glucose"])
    if "sodium" in state.C_D:
        state.C_D["sodium"] = _safe_float(d0.get("sodium", params.dialysate_sodium), state.C_D["sodium"])

    # dwell-only 近似：设置 exchange_time 足够大，使得整个 [0, total_minutes] 内不进入 fill/drain
    effective_volume = params.fill_volume
    fill_time = effective_volume / params.fill_rate  # min
    # drain 时间估计：沿用 solver 的简化近似（在 parameters 内可用）
    if effective_volume <= params.V_breakpoint:
        drain_time_est = (effective_volume - params.residual_volume) / params.drain_rate_slow
    else:
        time_fast = (effective_volume - params.V_breakpoint) / params.drain_rate_fast
        time_slow = (params.V_breakpoint - params.residual_volume) / params.drain_rate_slow
        drain_time_est = time_fast + time_slow
    params.exchange_time = float(fill_time + total_minutes + drain_time_est + 5.0)

    # 从 dwell 阶段开始积分
    state.t = float(fill_time)

    solver = RungeKuttaSolver(params, dt=dt_minutes)
    _physics = PhysicsCalculator(params)
    # 初始记录（t_rel=0）
    record_points = [0.0, 120.0, 240.0]
    record_indices = {rp: int(round(rp / dt_minutes)) for rp in record_points}

    urea_vals: Dict[float, float] = {}
    crea_vals: Dict[float, float] = {}
    glu_vals: Dict[float, float] = {}

    urea_vals[0.0] = float(state.C_D.get("urea", 0.0))
    crea_vals[0.0] = float(state.C_D.get("creatinine", 0.0))
    glu_vals[0.0] = float(state.C_D.get("glucose", 0.0))

    total_steps = int(round(total_minutes / dt_minutes))
    for step in range(1, total_steps + 1):
        state = solver.rk4_step(state)
        t_rel = step * dt_minutes
        # 只在需要的点记录
        for rp in record_points:
            if abs(t_rel - rp) < 1e-9 or step == record_indices[rp]:
                if rp not in urea_vals:
                    urea_vals[rp] = float(state.C_D.get("urea", 0.0))
                    crea_vals[rp] = float(state.C_D.get("creatinine", 0.0))
                    glu_vals[rp] = float(state.C_D.get("glucose", 0.0))
        if len(urea_vals) >= 3:
            break

    return PetSimResult(
        urea=[urea_vals.get(rp, 0.0) for rp in record_points],
        creatinine=[crea_vals.get(rp, 0.0) for rp in record_points],
        glucose=[glu_vals.get(rp, 0.0) for rp in record_points],
    )


def fit_pet_parameters(
    patient: Dict[str, Any],
    pet: Dict[str, Any],
    blood_2h: Dict[str, Any],
    transport_type: TransportType,
    initial_guess: Tuple[float, float] = (1.0, 1.0),
    max_nfev: int = 20,
) -> Dict[str, Any]:
    """
    拟合参数（最小实现）
    x = [LpS_scale, ps_scale]
    """
    # plasma 常数（按前端/参数口径）
    plasma = {
        "urea": _safe_float(blood_2h.get("urea"), 0.0),
        "creatinine": _convert_creatinine_to_mmol_per_l(blood_2h.get("creatinine")),
        "glucose": _safe_float(blood_2h.get("glucose"), 0.0),
        "sodium": _safe_float(blood_2h.get("sodium"), 140.0),
        # 缺省不参与拟合
        "beta2m": 0.0,
        "albumin": 0.0,
    }

    d0 = _pet_get_block(pet, "d0")
    d2 = _pet_get_block(pet, "d2")
    d4 = _pet_get_block(pet, "d4")

    # 拟合使用 PET 常用的“比值”指标，减少绝对浓度量纲带来的缩放歧义
    eps = 1e-8

    obs_crea_d2 = _convert_creatinine_to_mmol_per_l(d2.get("creatinine"))
    obs_crea_d4 = _convert_creatinine_to_mmol_per_l(d4.get("creatinine"))
    obs_urea_d2 = _safe_float(d2.get("urea"), 0.0)
    obs_urea_d4 = _safe_float(d4.get("urea"), 0.0)
    obs_glu_d0 = _safe_float(d0.get("glucose"), 0.0)
    obs_glu_d2 = _safe_float(d2.get("glucose"), 0.0)
    obs_glu_d4 = _safe_float(d4.get("glucose"), 0.0)

    plasma_crea = float(plasma.get("creatinine", 0.0))
    plasma_urea = float(plasma.get("urea", 0.0))

    # D/Pcrea、D/Purea；以及 D/D0glucose
    obs_crea_dp_d2 = obs_crea_d2 / (plasma_crea + eps)
    obs_crea_dp_d4 = obs_crea_d4 / (plasma_crea + eps)
    obs_urea_dp_d2 = obs_urea_d2 / (plasma_urea + eps)
    obs_urea_dp_d4 = obs_urea_d4 / (plasma_urea + eps)

    obs_glu_dd0_d2 = obs_glu_d2 / (obs_glu_d0 + eps)
    obs_glu_dd0_d4 = obs_glu_d4 / (obs_glu_d0 + eps)

    def residuals(x: np.ndarray) -> np.ndarray:
        lps_scale = float(x[0])
        ps_scale = float(x[1])

        params = ModelParameters(transport_type=transport_type)
        # apply scales
        params.LpS = params.LpS * lps_scale
        for sol in params.solutes.values():
            sol.ps_product = sol.ps_product * ps_scale

        sim = simulate_pet_dwell(params=params, pet=pet, plasma=plasma, total_minutes=240.0, dt_minutes=2.0)

        sim_urea = np.asarray(sim.urea, dtype=float)
        sim_crea = np.asarray(sim.creatinine, dtype=float)
        sim_glu = np.asarray(sim.glucose, dtype=float)

        # 只取 t=2h 与 t=4h（索引 1 与 2），模拟比值
        sim_crea_dp_d2 = sim_crea[1] / (plasma_crea + eps)
        sim_crea_dp_d4 = sim_crea[2] / (plasma_crea + eps)
        sim_urea_dp_d2 = sim_urea[1] / (plasma_urea + eps)
        sim_urea_dp_d4 = sim_urea[2] / (plasma_urea + eps)
        sim_glu_dd0_d2 = sim_glu[1] / (obs_glu_d0 + eps)
        sim_glu_dd0_d4 = sim_glu[2] / (obs_glu_d0 + eps)

        # 归一化残差：用观测比值做尺度，避免某项量级过大
        def norm_err(sim_val: float, obs_val: float) -> float:
            return (sim_val - obs_val) / (abs(obs_val) + eps)

        r_crea_d2 = norm_err(sim_crea_dp_d2, obs_crea_dp_d2)
        r_crea_d4 = norm_err(sim_crea_dp_d4, obs_crea_dp_d4)
        r_urea_d2 = norm_err(sim_urea_dp_d2, obs_urea_dp_d2)
        r_urea_d4 = norm_err(sim_urea_dp_d4, obs_urea_dp_d4)
        r_glu_d2 = norm_err(sim_glu_dd0_d2, obs_glu_dd0_d2)
        r_glu_d4 = norm_err(sim_glu_dd0_d4, obs_glu_dd0_d4)

        # 正则：避免参数离 1 太远（工程稳定性优先）
        reg_lambda = 0.05
        r_reg_lps = np.sqrt(reg_lambda) * (lps_scale - 1.0)
        r_reg_ps = np.sqrt(reg_lambda) * (ps_scale - 1.0)

        return np.array([r_crea_d2, r_crea_d4, r_urea_d2, r_urea_d4, r_glu_d2, r_glu_d4, r_reg_lps, r_reg_ps], dtype=float)

    # 非负约束：保证缩放系数在合理范围（避免 overfit 放大 Kt/V）
    lower = np.array([0.2, 0.2], dtype=float)
    upper = np.array([5.0, 5.0], dtype=float)

    # least_squares 支持 bounds
    res = least_squares(
        residuals,
        x0=np.array(initial_guess, dtype=float),
        bounds=(lower, upper),
        max_nfev=max_nfev,
        ftol=1e-6,
        xtol=1e-6,
        gtol=1e-6,
    )

    fitted = {
        "LpS_scale": float(res.x[0]),
        "ps_scale": float(res.x[1]),
        "transport_type": transport_type.value,
        "cost": float(res.cost),
        "nfev": int(res.nfev),
        "status": int(res.status),
    }
    return fitted

