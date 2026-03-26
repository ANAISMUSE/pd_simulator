"""
腹膜透析物理过程计算模块
实现Starling方程、Patlak方程等核心物理模型
"""
import numpy as np
from typing import Tuple, Dict, List

# 绝对导入
from models.parameters import ModelParameters, Solute

class PhysicsCalculator:
    """物理过程计算器"""
    
    def __init__(self, params: ModelParameters):
        self.params = params
        
    def calculate_ipp(self, V_D: float) -> float:
        """
        计算腹腔内压力 (Intraperitoneal Pressure)
        
        基于Twardowski公式的修改版:
        IPP = 4.7 + V_D / 690
        
        Args:
            V_D: 腹腔内体积 (mL)
            
        Returns:
            IPP (mmHg)
        """
        return 4.7 + V_D / 690.0
    
    def calculate_capillary_pressure(self, ipp: float) -> float:
        """
        计算毛细血管压力 Pc
        
        基于血流动力学模型:
        Pc = f_Rv * MAP + f_Ra * Pv
        其中 Pv ≈ IPP (假设大静脉压力等于腹腔内压力)
        
        Args:
            ipp: 腹腔内压力 (mmHg)
            
        Returns:
            Pc (mmHg)
        """
        f_Rv = 1.0 / (self.params.PTP_ratio + 1.0)
        f_Ra = self.params.PTP_ratio / (self.params.PTP_ratio + 1.0)
        Pv = ipp
        Pc = f_Rv * self.params.MAP + f_Ra * Pv
        return Pc
    
    def calculate_delta_P(self, V_D: float) -> float:
        """
        计算跨膜静水压梯度
        
        Args:
            V_D: 腹腔内体积 (mL)
            
        Returns:
            ΔP = Pc - IPP (mmHg)
        """
        ipp = self.calculate_ipp(V_D)
        pc = self.calculate_capillary_pressure(ipp)
        return pc - ipp
    
    def calculate_osmotic_pressure(self, 
                                   C_D: Dict[str, float],
                                   solute_key: str,
                                   sigma: float) -> float:
        """
        计算单个溶质的渗透压贡献
        
        Δπ = σ * φ * R * T * (C_P - C_D)
        
        Args:
            C_D: 腹腔内浓度字典
            solute_key: 溶质名称
            sigma: 反射系数
            
        Returns:
            渗透压差 (mmHg)
        """
        solute = self.params.solutes[solute_key]
        C_P = solute.plasma_concentration
        C_D_val = C_D.get(solute_key, 0.0)
        
        # R*T = 8.314 * 310.15 ≈ 2578 J/mol
        # 转换为 mmHg: 1 J/L = 7.5 mmHg
        # 因此 R*T ≈ 19335 mmHg·L/mol
        RT_mmHg = 19.335  # mmHg·L/mmol
        
        delta_pi = sigma * solute.osmotic_coef * RT_mmHg * (C_P - C_D_val)
        return delta_pi
    
    def calculate_water_fluxes(self, 
                               V_D: float,
                               C_D: Dict[str, float]) -> Tuple[float, float, float]:
        """
        计算三种孔道的水流量 (Starling方程)
        
        J_v,k = α_k * LpS * (ΔP - Σ(σ_k,i * Δπ_i))
        
        Args:
            V_D: 腹腔内体积 (mL)
            C_D: 腹腔内浓度字典
            
        Returns:
            (J_v_C, J_v_S, J_v_L) 超小孔、小孔、大孔水流量 (mL/min)
        """
        delta_P = self.calculate_delta_P(V_D)
        
        # 计算各孔道的总渗透压差
        osmotic_small = 0.0
        osmotic_large = 0.0
        
        for solute_key in self.params.solutes:
            solute = self.params.solutes[solute_key]
            osmotic_small += self.calculate_osmotic_pressure(
                C_D, solute_key, solute.reflection_coef_small
            )
            osmotic_large += self.calculate_osmotic_pressure(
                C_D, solute_key, solute.reflection_coef_large
            )
        
        # 超小孔水流量 (使用小孔的渗透压,因为超小孔完全排斥大分子)
        J_v_C = self.params.alpha_C * self.params.LpS * (delta_P - osmotic_small)
        
        # 小孔水流量
        J_v_S = self.params.alpha_S * self.params.LpS * (delta_P - osmotic_small)
        
        # 大孔水流量
        J_v_L = self.params.alpha_L * self.params.LpS * (delta_P - osmotic_large)
        
        return J_v_C, J_v_S, J_v_L
    
    def calculate_solute_flux_small_pore(self,
                                         solute_key: str,
                                         J_v_S: float,
                                         C_D: float) -> float:
        """
        计算小孔溶质流量 (Patlak方程)
        
        J_s,S = PS * (C_P - C_D) + (1 - σ_S) * J_v,S * C_mean
        其中 C_mean = (C_P + C_D) / 2
        
        Args:
            solute_key: 溶质名称
            J_v_S: 小孔水流量 (mL/min)
            C_D: 腹腔内浓度
            
        Returns:
            J_s,S 小孔溶质流量 (mmol/min 或 g/min)
        """
        solute = self.params.solutes[solute_key]
        C_P = solute.plasma_concentration
        C_mean = (C_P + C_D) / 2.0
        
        # 扩散项
        # 单位检查：
        # - ps_product: mL/min
        # - (C_P - C_D): mmol/L
        # => (mL/min)*(mmol/L) = mmol/min * (mL/L) = mmol/min * (1/1000)
        # 因此需要除以 1000，把 L<->mL 口径对齐
        diffusive = solute.ps_product * (C_P - C_D) / 1000.0
        
        # 对流项
        convective = (1.0 - solute.reflection_coef_small) * J_v_S * C_mean / 1000.0
        # 除以1000: mL→L转换
        
        return diffusive + convective
    
    def calculate_solute_flux_large_pore(self,
                                         solute_key: str,
                                         J_v_L: float,
                                         C_D: float) -> float:
        """
        计算大孔溶质流量
        
        大孔主要靠对流,扩散贡献很小
        J_s,L ≈ (1 - σ_L) * J_v,L * C_mean
        
        Args:
            solute_key: 溶质名称
            J_v_L: 大孔水流量 (mL/min)
            C_D: 腹腔内浓度
            
        Returns:
            J_s,L 大孔溶质流量 (mmol/min 或 g/min)
        """
        solute = self.params.solutes[solute_key]
        C_P = solute.plasma_concentration
        C_mean = (C_P + C_D) / 2.0
        
        # 大孔对流项
        convective = (1.0 - solute.reflection_coef_large) * J_v_L * C_mean / 1000.0
        
        return convective
    
    def calculate_all_solute_fluxes(self,
                                    J_v_S: float,
                                    J_v_L: float,
                                    C_D: Dict[str, float]) -> Dict[str, Dict[str, float]]:
        """
        计算所有溶质的跨膜流量
        
        Returns:
            字典: {solute_key: {'small': J_s_S, 'large': J_s_L, 'total': J_s_total}}
        """
        fluxes = {}
        
        for solute_key in self.params.solutes:
            C_D_val = C_D.get(solute_key, 0.0)
            
            J_s_small = self.calculate_solute_flux_small_pore(
                solute_key, J_v_S, C_D_val
            )
            J_s_large = self.calculate_solute_flux_large_pore(
                solute_key, J_v_L, C_D_val
            )
            
            fluxes[solute_key] = {
                'small': J_s_small,
                'large': J_s_large,
                'total': J_s_small + J_s_large
            }
        
        return fluxes
