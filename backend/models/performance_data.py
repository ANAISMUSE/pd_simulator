# backend/models/performance_data.py

from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime

@dataclass
class SimulationPerformance:
    """单次模拟性能记录"""
    
    # 模拟参数
    dt: float                          # 时间步长（分钟）
    simulation_duration: float         # 模拟时长（分钟）
    total_steps: int                   # 总步数
    
    # 性能指标
    execution_time: float              # 执行时间（秒）
    memory_usage_mb: float             # 内存占用（MB）
    cpu_usage_percent: float           # CPU使用率（%）
    
    # 模拟配置
    transport_type: str                # 转运类型
    fill_volume: float                 # 灌注体积
    glucose_conc: float                # 葡萄糖浓度
    
    # 元数据
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error_message: str = ""

@dataclass
class PerformanceBenchmark:
    """性能基准测试结果集"""
    
    test_name: str                     # 测试名称
    test_description: str              # 测试描述
    test_date: str                     # 测试日期
    
    records: List[SimulationPerformance] = field(default_factory=list)
    
    # 统计结果
    avg_execution_time: float = 0.0
    min_execution_time: float = 0.0
    max_execution_time: float = 0.0
    std_execution_time: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'test_name': self.test_name,
            'test_description': self.test_description,
            'test_date': self.test_date,
            'summary': {
                'total_tests': len(self.records),
                'avg_execution_time': self.avg_execution_time,
                'min_execution_time': self.min_execution_time,
                'max_execution_time': self.max_execution_time,
                'std_execution_time': self.std_execution_time,
            },
            'records': [
                {
                    'dt': r.dt,
                    'execution_time': r.execution_time,
                    'memory_usage_mb': r.memory_usage_mb,
                    'success': r.success
                }
                for r in self.records
            ]
        }
