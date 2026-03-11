"""
四阶龙格-库塔数值求解器
用于求解腹膜透析三孔模型的常微分方程组
"""
import numpy as np
from typing import Tuple, Dict, Callable

# 绝对导入
from models.parameters import ModelParameters, DialysisMode
from models.physics import PhysicsCalculator


class PDState:
    """腹透系统状态"""
    def __init__(self, params: ModelParameters):
        self.t = 0.0  # 当前时间 (min)
        self.V_D = params.fill_volume  # 腹腔内体积 (mL)
        self.C_D = params.get_initial_dialysate_concentrations()  # 腹腔内浓度
        self.V_B = 0.0  # 储液库体积 (mL)
        self.C_B = {key: 0.0 for key in self.C_D}  # 储液库浓度
        
        # 历史记录
        self.history = {
            't': [0.0],
            'V_D': [self.V_D],
            'V_B': [self.V_B],
        }
        for key in self.C_D:
            self.history[f'C_D_{key}'] = [self.C_D[key]]
            self.history[f'C_B_{key}'] = [self.C_B[key]]
            
    def record_state(self):
        """记录当前状态到历史"""
        self.history['t'].append(self.t)
        self.history['V_D'].append(self.V_D)
        self.history['V_B'].append(self.V_B)
        for key in self.C_D:
            self.history[f'C_D_{key}'].append(self.C_D[key])
            self.history[f'C_B_{key}'].append(self.C_B[key])


class RungeKuttaSolver:
    """四阶龙格-库塔求解器"""
    
    def __init__(self, params: ModelParameters, dt: float = 0.001):
        """
        Args:
            params: 模型参数
            dt: 时间步长 (min), 默认0.001分钟(0.06秒)
        """
        self.params = params
        self.dt = dt
        self.physics = PhysicsCalculator(params)
        
        # 透析循环控制
        self.cycle_time = 0.0
        self.current_phase = 'fill'  # fill, dwell, drain
        
    def get_fill_drain_rates(self, t: float, V_D: float) -> Tuple[float, float]:
        """
        获取当前时刻的灌注/引流流速
        
        Returns:
            (J_fill, J_drain) 单位: mL/min
        """
        self.cycle_time = t % self.params.exchange_time
        tidal_ratio = max(self.params.tidal_ratio, 0.1)
        effective_volume = self.params.fill_volume
        if self.params.dialysis_mode == DialysisMode.TPD:
            effective_volume *= tidal_ratio
        
        fill_time = effective_volume / self.params.fill_rate
        
        # 计算引流时间(需要迭代,这里简化处理)
        drain_time_estimate = self._estimate_drain_time(effective_volume)
        
        if self.cycle_time < fill_time:
            # 灌注阶段
            self.current_phase = 'fill'
            return self.params.fill_rate, 0.0
            
        elif self.cycle_time < self.params.exchange_time - drain_time_estimate:
            # 留置阶段
            self.current_phase = 'dwell'
            return 0.0, 0.0
            
        else:
            # 引流阶段
            self.current_phase = 'drain'
            drain_rate = self._get_current_drain_rate(V_D)
            return 0.0, drain_rate
    
    def _estimate_drain_time(self, V_start: float) -> float:
        """估算引流所需时间"""
        if V_start <= self.params.V_breakpoint:
            return (V_start - self.params.residual_volume) / self.params.drain_rate_slow
        else:
            time_fast = (V_start - self.params.V_breakpoint) / self.params.drain_rate_fast
            time_slow = (self.params.V_breakpoint - self.params.residual_volume) / \
                       self.params.drain_rate_slow
            return time_fast + time_slow
    
    def _get_current_drain_rate(self, V_D: float) -> float:
        """根据当前体积获取引流速率"""
        if V_D > self.params.V_breakpoint:
            return self.params.drain_rate_fast
        elif V_D > self.params.residual_volume:
            return self.params.drain_rate_slow
        else:
            return 0.0
    
    def calculate_derivatives(self,
                             t: float,
                             V_D: float,
                             C_D: Dict[str, float],
                             V_B: float,
                             C_B: Dict[str, float]) -> Tuple:
        """
        计算所有状态变量的导数(变化率)
        
        Returns:
            (dV_D_dt, dC_D_dt, dV_B_dt, dC_B_dt, J_fill, J_drain)
        """
        # 1. 计算水流量
        J_v_C, J_v_S, J_v_L = self.physics.calculate_water_fluxes(V_D, C_D)
        
        # 2. 计算淋巴回流
        L = self.params.lymph_flow
        
        # 3. 获取灌注/引流流速
        J_fill, J_drain = self.get_fill_drain_rates(t, V_D)
        
        # 4. 计算体积变化率
        dV_D_dt = J_v_C + J_v_S + J_v_L - L + J_fill - J_drain
        dV_B_dt = J_drain - J_fill
        
        # 5. 计算溶质流量
        solute_fluxes = self.physics.calculate_all_solute_fluxes(J_v_S, J_v_L, C_D)
        
        # 6. 计算腹腔内浓度变化率
        dC_D_dt = {}
        for solute_key in self.params.solutes:
            J_s_total = solute_fluxes[solute_key]['total']
            C_D_i = C_D[solute_key]
            C_B_i = C_B.get(solute_key, 0.0)
            
            # 初始透析液浓度(灌注时使用)
            C_fresh = self.params.get_initial_dialysate_concentrations()[solute_key]
            
            if V_D > 1.0:  # 避免除零
                term1 = J_s_total / V_D
                term2 = -C_D_i * (J_v_C + J_v_S + J_v_L - J_drain) / V_D
                term3 = (C_fresh * J_fill) / V_D
                dC_D_dt[solute_key] = term1 + term2 + term3
            else:
                dC_D_dt[solute_key] = 0.0
        
        # 7. 计算储液库浓度变化率
        dC_B_dt = {}
        for solute_key in self.params.solutes:
            C_D_i = C_D[solute_key]
            C_B_i = C_B.get(solute_key, 0.0)
            
            if V_B > 1.0:
                term1 = (J_drain * C_D_i - J_fill * C_B_i) / V_B
                term2 = -C_B_i * dV_B_dt / V_B
                dC_B_dt[solute_key] = term1 + term2
            else:
                dC_B_dt[solute_key] = 0.0
        
        return dV_D_dt, dC_D_dt, dV_B_dt, dC_B_dt, J_fill, J_drain
    
    def rk4_step(self, state: PDState) -> PDState:
        """
        执行一步四阶龙格-库塔积分
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        t = state.t
        V_D = state.V_D
        C_D = state.C_D.copy()
        V_B = state.V_B
        C_B = state.C_B.copy()
        dt = self.dt
        
        # ========== K1, L1, M1 ==========
        dV_D_1, dC_D_1, dV_B_1, dC_B_1, _, _ = self.calculate_derivatives(
            t, V_D, C_D, V_B, C_B
        )
        
        # ========== K2, L2, M2 ==========
        t_mid = t + dt / 2
        V_D_2 = V_D + dV_D_1 * dt / 2
        C_D_2 = {k: C_D[k] + dC_D_1[k] * dt / 2 for k in C_D}
        V_B_2 = V_B + dV_B_1 * dt / 2
        C_B_2 = {k: C_B[k] + dC_B_1[k] * dt / 2 for k in C_B}
        
        dV_D_2, dC_D_2, dV_B_2, dC_B_2, _, _ = self.calculate_derivatives(
            t_mid, V_D_2, C_D_2, V_B_2, C_B_2
        )
        
        # ========== K3, L3, M3 ==========
        V_D_3 = V_D + dV_D_2 * dt / 2
        C_D_3 = {k: C_D[k] + dC_D_2[k] * dt / 2 for k in C_D}
        V_B_3 = V_B + dV_B_2 * dt / 2
        C_B_3 = {k: C_B[k] + dC_B_2[k] * dt / 2 for k in C_B}
        
        dV_D_3, dC_D_3, dV_B_3, dC_B_3, _, _ = self.calculate_derivatives(
            t_mid, V_D_3, C_D_3, V_B_3, C_B_3
        )
        
        # ========== K4, L4, M4 ==========
        t_end = t + dt
        V_D_4 = V_D + dV_D_3 * dt
        C_D_4 = {k: C_D[k] + dC_D_3[k] * dt for k in C_D}
        V_B_4 = V_B + dV_B_3 * dt
        C_B_4 = {k: C_B[k] + dC_B_3[k] * dt for k in C_B}
        
        dV_D_4, dC_D_4, dV_B_4, dC_B_4, _, _ = self.calculate_derivatives(
            t_end, V_D_4, C_D_4, V_B_4, C_B_4
        )
        
        # ========== 加权平均更新 ==========
        state.V_D = V_D + dt * (dV_D_1 + 2*dV_D_2 + 2*dV_D_3 + dV_D_4) / 6
        state.V_B = V_B + dt * (dV_B_1 + 2*dV_B_2 + 2*dV_B_3 + dV_B_4) / 6
        
        for key in C_D:
            state.C_D[key] = C_D[key] + dt * (
                dC_D_1[key] + 2*dC_D_2[key] + 2*dC_D_3[key] + dC_D_4[key]
            ) / 6
            state.C_B[key] = C_B[key] + dt * (
                dC_B_1[key] + 2*dC_B_2[key] + 2*dC_B_3[key] + dC_B_4[key]
            ) / 6
        
        state.t = t_end
        
        # 边界约束
        state.V_D = max(state.V_D, self.params.residual_volume)
        state.V_B = max(state.V_B, 0.0)
        
        return state
    
    def solve(self, total_time: float, record_interval: float = 1.0) -> PDState:
        """
        求解整个模拟周期
        
        Args:
            total_time: 总模拟时间 (min)
            record_interval: 记录间隔 (min)
            
        Returns:
            最终状态(包含完整历史记录)
        """
        state = PDState(self.params)
        steps = int(total_time / self.dt)
        record_every = int(record_interval / self.dt)
        
        print(f"开始模拟: 总时长={total_time}分钟, 时间步长={self.dt}分钟")
        print(f"总步数={steps}, 记录间隔={record_interval}分钟")
        
        for step in range(steps):
            state = self.rk4_step(state)
            
            # 定期记录
            if step % record_every == 0:
                state.record_state()
                
            # 进度显示
            if step % (steps // 10) == 0:
                progress = 100 * step / steps
                print(f"进度: {progress:.1f}% | 时间={state.t:.2f}min | "
                      f"V_D={state.V_D:.1f}mL | 阶段={self.current_phase}")
        
        # 记录最终状态
        state.record_state()
        print("模拟完成!")
        
        return state
