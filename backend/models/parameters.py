"""
腹膜透析三孔模型参数定义模块
基于扩展三孔模型(TPM)的参数体系
"""
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum


class TransportType(Enum):
    """腹膜转运类型"""
    FAST = "fast"
    AVERAGE = "average"
    SLOW = "slow"


class DialysisMode(Enum):
    """透析模式"""
    IPD = "intermittent"  # 间歇性腹膜透析
    TPD = "tidal"         # 潮式腹膜透析
    CAPD = "continuous"   # 持续性腹膜透析


@dataclass
class Solute:
    """溶质属性"""
    name: str
    molecular_weight: float  # 分子量 (Da)
    reflection_coef_small: float  # 小孔反射系数 σ_S
    reflection_coef_large: float  # 大孔反射系数 σ_L
    osmotic_coef: float  # 渗透系数 φ
    plasma_concentration: float  # 血浆浓度 (mmol/L or g/L)
    ps_product: float  # 渗透性-表面积系数 PS (mL/min)


class ModelParameters:
    """三孔模型核心参数集"""
    
    # 物理常数
    R = 8.314  # 气体常数 (J/(mol·K))
    T = 310.15  # 体温 (K, 37°C)
    
    def __init__(self, transport_type: TransportType = TransportType.AVERAGE):
        self.transport_type = transport_type
        
        # ============ 腹膜结构参数 ============
        self._initialize_membrane_params()
        
        # ============ 溶质参数 ============
        self._initialize_solutes()
        
        # ============ 血流动力学参数 ============
        self.MAP = 90.0  # 平均动脉压 (mmHg)
        self.PTP_ratio = 8.0  # 前/后毛细血管阻力比
        
        # ============ 透析处方参数 ============
        self.exchange_time = 60.0  # 交换周期 (min)
        self.fill_volume = 2000.0  # 灌注体积 (mL)
        self.fill_rate = 200.0  # 灌注速率 (mL/min)
        self.drain_rate_fast = 350.0  # 引流快速相 (mL/min)
        self.drain_rate_slow = 36.0  # 引流慢速相 (mL/min)
        self.V_breakpoint = 381.0  # 引流速率转换点 (mL)
        self.residual_volume = 50.0  # 残余体积 (mL)
        
        # ============ 透析液参数 ============
        self.glucose_concentration = 1.5  # 葡萄糖浓度 (%)
        self.dialysate_sodium = 132.0  # 钠浓度 (mmol/L)
        
        # ============ 淋巴回流 ============
        self.lymph_flow = 0.3  # 淋巴回流速率 (mL/min)
        
        # ============ 模式控制 ============
        self.dialysis_mode = DialysisMode.CAPD
        self.tidal_ratio = 1.0
        
    def _initialize_membrane_params(self):
        """初始化腹膜结构参数"""
        # 孔道水力传导分数
        self.alpha_C = 0.02  # 超小孔
        self.alpha_S = 0.90  # 小孔
        self.alpha_L = 0.08  # 大孔
        
        # 基础A₀/Δx值 (根据转运类型调整)
        base_A0_dx = {
            TransportType.SLOW: 9820,
            TransportType.AVERAGE: 17030,
            TransportType.FAST: 24240
        }
        self.A0_dx = base_A0_dx[self.transport_type]  # cm
        
        # 总过滤系数 LpS (mL/(min·mmHg))
        lps_values = {
            TransportType.SLOW: 0.050,
            TransportType.AVERAGE: 0.074,
            TransportType.FAST: 0.098
        }
        self.LpS = lps_values[self.transport_type]
        
        # 孔道半径
        self.radius_small = 43e-8  # 小孔半径 (cm)
        self.radius_large = 250e-8  # 大孔半径 (cm)
        
    def _initialize_solutes(self):
        """初始化溶质参数体系"""
        # PS值根据转运类型缩放
        ps_scale = {
            TransportType.SLOW: 0.577,
            TransportType.AVERAGE: 1.0,
            TransportType.FAST: 1.423
        }[self.transport_type]
        
        self.solutes: Dict[str, Solute] = {
            'urea': Solute(
                name='尿素',
                molecular_weight=60,
                reflection_coef_small=0.0,
                reflection_coef_large=0.0,
                osmotic_coef=1.0,
                plasma_concentration=20.0,  # mmol/L
                ps_product=17.4 * ps_scale
            ),
            'creatinine': Solute(
                name='肌酐',
                molecular_weight=113,
                reflection_coef_small=0.0,
                reflection_coef_large=0.0,
                osmotic_coef=1.0,
                plasma_concentration=0.884,  # mmol/L (约10 mg/dL)
                ps_product=10.3 * ps_scale
            ),
            'glucose': Solute(
                name='葡萄糖',
                molecular_weight=180,
                reflection_coef_small=0.03,
                reflection_coef_large=0.0,
                osmotic_coef=1.0,
                plasma_concentration=5.5,  # mmol/L
                ps_product=15.8 * ps_scale
            ),
            'sodium': Solute(
                name='钠',
                molecular_weight=23,
                reflection_coef_small=0.0,
                reflection_coef_large=0.0,
                osmotic_coef=2.0,  # 电解质渗透系数加倍
                plasma_concentration=140.0,  # mmol/L
                ps_product=25.0 * ps_scale
            ),
            'beta2m': Solute(
                name='β₂-微球蛋白',
                molecular_weight=11800,
                reflection_coef_small=0.85,
                reflection_coef_large=0.0,
                osmotic_coef=1.0,
                plasma_concentration=0.003,  # g/L
                ps_product=1.2 * ps_scale
            ),
            'albumin': Solute(
                name='白蛋白',
                molecular_weight=66000,
                reflection_coef_small=1.0,
                reflection_coef_large=0.74,
                osmotic_coef=1.0,
                plasma_concentration=40.0,  # g/L
                ps_product=0.08 * ps_scale
            )
        }
        
    def get_initial_dialysate_concentrations(self) -> Dict[str, float]:
        """获取初始透析液浓度"""
        glucose_mmol = self.glucose_concentration * 10 * 5.55  # %转为mmol/L
        return {
            'urea': 0.0,
            'creatinine': 0.0,
            'glucose': glucose_mmol,
            'sodium': self.dialysate_sodium,
            'beta2m': 0.0,
            'albumin': 0.0
        }
    
    def update_from_patient_data(self, pet_result: float, plasma_values: Dict[str, float]):
        """
        根据患者数据更新参数
        
        Args:
            pet_result: PET试验D/Pcrea值 (4小时)
            plasma_values: 患者血浆溶质浓度字典
        """
        # 根据PET结果判断转运类型
        if pet_result > 0.81:
            self.transport_type = TransportType.FAST
        elif pet_result < 0.65:
            self.transport_type = TransportType.SLOW
        else:
            self.transport_type = TransportType.AVERAGE
            
        # 重新初始化参数
        self._initialize_membrane_params()
        self._initialize_solutes()
        
        # 更新血浆浓度
        for solute_key, concentration in plasma_values.items():
            if solute_key in self.solutes:
                self.solutes[solute_key].plasma_concentration = concentration


    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从清洗后的字典创建 ModelParameters 实例。

        预期字典结构（示例）：
        {
            'age': 35,
            'weight': 70.0,
            'pet_d_p_crea': 0.72,
            'plasma_values': { 'urea': 15.0, ... },
            'transport_type': 'fast',
            'fill_volume': 2000,
            'exchange_time': 240
        }
        """
        tp = data.get('transport_type')
        if isinstance(tp, str):
            try:
                tp_enum = TransportType(tp)
            except Exception:
                tp_enum = TransportType.AVERAGE
        elif isinstance(tp, TransportType):
            tp_enum = tp
        else:
            tp_enum = TransportType.AVERAGE

        params = cls(transport_type=tp_enum)

        # apply simple prescription fields
        if 'fill_volume' in data and data['fill_volume'] is not None:
            params.fill_volume = float(data['fill_volume'])
        if 'exchange_time' in data and data['exchange_time'] is not None:
            params.exchange_time = float(data['exchange_time'])

        # patient-derived updates
        pet = data.get('pet_d_p_crea')
        plasma = data.get('plasma_values', {})
        try:
            if pet is not None:
                # update membrane and solute concentrations based on patient data
                params.update_from_patient_data(float(pet), plasma)
            else:
                # update only plasma concentrations
                for k, v in plasma.items():
                    if k in params.solutes and v is not None:
                        params.solutes[k].plasma_concentration = v
        except Exception:
            # fallback: try to update only concentrations
            for k, v in plasma.items():
                if k in params.solutes and v is not None:
                    params.solutes[k].plasma_concentration = v

        # if transport_type was explicitly provided in input dict, override the one inferred from PET
        provided_tp = data.get('transport_type')
        if provided_tp is not None:
            if isinstance(provided_tp, str):
                try:
                    params.transport_type = TransportType(provided_tp)
                except Exception:
                    pass
            elif isinstance(provided_tp, TransportType):
                params.transport_type = provided_tp
            # re-init membrane params to reflect explicit transport_type
            params._initialize_membrane_params()

        return params


class PatientData:
    """患者数据类"""
    def __init__(self, patient_id: str):
        self.patient_id = patient_id
        self.age: int = 50
        self.weight: float = 70.0  # kg
        self.height: float = 170.0  # cm
        self.pet_d_p_crea: float = 0.73  # PET D/Pcrea (4h)
        
        # 血浆生化指标
        self.plasma_values = {
            'urea': 20.0,  # mmol/L
            'creatinine': 0.884,  # mmol/L
            'glucose': 5.5,  # mmol/L
            'sodium': 140.0,  # mmol/L
            'beta2m': 0.003,  # g/L
            'albumin': 40.0  # g/L
        }
        
    def get_bsa(self) -> float:
        """计算体表面积 (Mosteller公式)"""
        return np.sqrt(self.height * self.weight / 3600)


