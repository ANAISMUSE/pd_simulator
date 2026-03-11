# backend/models/error_data.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np

@dataclass
class ErrorRecord:
    """单个参数组合的误差记录"""
    
    # 输入参数
    parameters: Dict[str, float]       # 参数组合
    
    # 模拟结果
    simulated_values: List[float]      # 模拟值序列
    
    # 实际值（可选，用于验证）
    actual_values: Optional[List[float]] = None
    
    # 误差统计
    errors: List[float] = field(default_factory=list)  # 误差序列
    mean_error: float = 0.0            # 平均误差
    max_error: float = 0.0             # 最大误差
    rmse: float = 0.0                  # 均方根误差
    
    def calculate_errors(self):
        """计算误差统计"""
        if self.actual_values and len(self.simulated_values) == len(self.actual_values):
            self.errors = [
                sim - actual 
                for sim, actual in zip(self.simulated_values, self.actual_values)
            ]
            self.mean_error = np.mean(np.abs(self.errors))
            self.max_error = np.max(np.abs(self.errors))
            self.rmse = np.sqrt(np.mean(np.array(self.errors) ** 2))

@dataclass
class ErrorAnalysis:
    """误差分析结果集"""
    
    analysis_name: str                 # 分析名称
    analysis_date: str                 # 分析日期
    variable_name: str                 # 变量名（如 'dt', 'glucose_conc'）
    
    records: List[ErrorRecord] = field(default_factory=list)
    
    # 汇总统计
    overall_mean_error: float = 0.0
    overall_max_error: float = 0.0
    overall_rmse: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'analysis_name': self.analysis_name,
            'analysis_date': self.analysis_date,
            'variable_name': self.variable_name,
            'summary': {
                'total_tests': len(self.records),
                'overall_mean_error': self.overall_mean_error,
                'overall_max_error': self.overall_max_error,
                'overall_rmse': self.overall_rmse,
            },
            'records': [
                {
                    'parameters': r.parameters,
                    'mean_error': r.mean_error,
                    'max_error': r.max_error,
                    'rmse': r.rmse
                }
                for r in self.records
            ]
        }
