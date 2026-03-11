# backend/evaluation/data_collector.py

import time
import psutil
import numpy as np
from typing import Dict, List
from datetime import datetime
from pathlib import Path
import json

from core.solver import RungeKuttaSolver
from core.model_parameters import ModelParameters, TransportType
from models.performance_data import SimulationPerformance, PerformanceBenchmark
from models.error_data import ErrorRecord, ErrorAnalysis
from models.risk_data import (
    BiomarkerTimeSeries, PrescriptionRiskAssessment, RiskLevel
)

class AutomatedDataCollector:
    """自动化数据收集器"""
    
    def __init__(self, output_dir: str = "evaluation_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    # ============ 1. 性能基准测试 ============
    
    def benchmark_simulation_speed(
        self, 
        dt_values: List[float] = None,
        num_runs: int = 5
    ) -> PerformanceBenchmark:
        """
        测试不同时间步长下的模拟性能
        
        Args:
            dt_values: 时间步长列表（分钟），默认 [0.01, 0.05, 0.1, 0.5, 1.0]
            num_runs: 每个配置重复运行次数
        """
        if dt_values is None:
            dt_values = [0.01, 0.05, 0.1, 0.5, 1.0]
        
        print("🚀 开始性能基准测试...")
        print(f"测试时间步长: {dt_values}")
        print(f"每个配置运行 {num_runs} 次")
        
        benchmark = PerformanceBenchmark(
            test_name="simulation_speed_benchmark",
            test_description="不同时间步长下的三孔模型模拟性能测试",
            test_date=datetime.now().isoformat()
        )
        
        for dt in dt_values:
            for run in range(num_runs):
                print(f"\n📊 测试 dt={dt}min, 运行 {run+1}/{num_runs}")
                
                # 创建参数
                params = ModelParameters(transport_type=TransportType.AVERAGE)
                params.exchange_time = 240  # 固定4小时
                params.fill_volume = 2000   # 固定2L
                params.glucose_concentration = 1.5
                
                # 性能监控
                process = psutil.Process()
                mem_before = process.memory_info().rss / 1024 / 1024  # MB
                cpu_before = process.cpu_percent(interval=0.1)
                
                start_time = time.time()
                
                try:
                    # 执行模拟
                    solver = RungeKuttaSolver(params, dt=dt)
                    state = solver.solve(
                        total_minutes=1440,  # 24小时
                        record_interval=10
                    )
                    
                    execution_time = time.time() - start_time
                    mem_after = process.memory_info().rss / 1024 / 1024
                    cpu_after = process.cpu_percent(interval=0.1)
                    
                    # 记录结果
                    record = SimulationPerformance(
                        dt=dt,
                        simulation_duration=1440,
                        total_steps=int(1440 / dt),
                        execution_time=execution_time,
                        memory_usage_mb=mem_after - mem_before,
                        cpu_usage_percent=(cpu_after + cpu_before) / 2,
                        transport_type=params.transport_type.name,
                        fill_volume=params.fill_volume,
                        glucose_conc=params.glucose_concentration,
                        success=True
                    )
                    
                    print(f"✅ 完成: {execution_time:.2f}秒")
                    
                except Exception as e:
                    print(f"❌ 失败: {e}")
                    record = SimulationPerformance(
                        dt=dt,
                        simulation_duration=1440,
                        total_steps=int(1440 / dt),
                        execution_time=0,
                        memory_usage_mb=0,
                        cpu_usage_percent=0,
                        transport_type=params.transport_type.name,
                        fill_volume=params.fill_volume,
                        glucose_conc=params.glucose_concentration,
                        success=False,
                        error_message=str(e)
                    )
                
                benchmark.records.append(record)
        
        # 计算统计
        execution_times = [r.execution_time for r in benchmark.records if r.success]
        if execution_times:
            benchmark.avg_execution_time = np.mean(execution_times)
            benchmark.min_execution_time = np.min(execution_times)
            benchmark.max_execution_time = np.max(execution_times)
            benchmark.std_execution_time = np.std(execution_times)
        
        # 保存结果
        output_file = self.output_dir / f"performance_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(benchmark.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 基准测试完成，结果已保存到: {output_file}")
        return benchmark
    
    # ============ 2. 误差分析 ============
    
    def analyze_parameter_errors(
        self,
        parameter_name: str,
        parameter_values: List[float],
        baseline_value: float = None
    ) -> ErrorAnalysis:
        """
        分析不同参数值下的模拟误差
        
        Args:
            parameter_name: 参数名（如 'glucose_conc', 'fill_volume'）
            parameter_values: 参数值列表
            baseline_value: 基准值（用于计算相对误差）
        """
        print(f"🔬 开始误差分析: {parameter_name}")
        print(f"测试值: {parameter_values}")
        
        analysis = ErrorAnalysis(
            analysis_name=f"{parameter_name}_error_analysis",
            analysis_date=datetime.now().isoformat(),
            variable_name=parameter_name
        )
        
        # 如果没有基准值，使用第一个值
        if baseline_value is None:
            baseline_value = parameter_values[0]
        
        # 运行基准模拟
        print(f"\n📍 运行基准模拟 ({parameter_name}={baseline_value})")
        baseline_results = self._run_simulation_with_parameter(
            parameter_name, baseline_value
        )
        
        # 测试其他参数值
        for value in parameter_values:
            print(f"\n📊 测试 {parameter_name}={value}")
            
            results = self._run_simulation_with_parameter(parameter_name, value)
            
            # 创建误差记录
            record = ErrorRecord(
                parameters={parameter_name: value},
                simulated_values=results['kt_v_urea_series'],
                actual_values=baseline_results['kt_v_urea_series']  # 使用基准作为"实际值"
            )
            record.calculate_errors()
            
            print(f"  平均误差: {record.mean_error:.4f}")
            print(f"  最大误差: {record.max_error:.4f}")
            
            analysis.records.append(record)
        
        # 计算整体统计
        if analysis.records:
            analysis.overall_mean_error = np.mean([r.mean_error for r in analysis.records])
            analysis.overall_max_error = np.max([r.max_error for r in analysis.records])
            analysis.overall_rmse = np.mean([r.rmse for r in analysis.records])
        
        # 保存结果
        output_file = self.output_dir / f"error_analysis_{parameter_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(analysis.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 误差分析完成，结果已保存到: {output_file}")
        return analysis
    
    # ============ 3. 方案风险评估 ============
    
    def assess_prescription_risk(
        self,
        prescription: Dict,
        safety_thresholds: Dict[str, Dict[str, float]] = None
    ) -> PrescriptionRiskAssessment:
        """
        评估透析方案的安全性风险
        
        Args:
            prescription: 透析方案
            safety_thresholds: 安全阈值，格式:
                {
                    'urea': {'upper': 30, 'lower': 5},
                    'creatinine': {'upper': 1200, 'lower': 400}
                }
        """
        if safety_thresholds is None:
            # 默认阈值（示例）
            safety_thresholds = {
                'urea': {'upper': 25, 'lower': 8},
                'creatinine': {'upper': 1000, 'lower': 500},
                'volume': {'upper': 2500, 'lower': 0}
            }
        
        print("⚠️ 开始方案风险评估...")
        
        assessment = PrescriptionRiskAssessment(
            prescription_id=f"prescription_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            prescription=prescription,
            assessment_date=datetime.now().isoformat()
        )
        
        # 运行模拟获取时间序列
        print("🔄 运行模拟...")
        params = self._prescription_to_params(prescription)
        solver = RungeKuttaSolver(params, dt=0.1)
        state = solver.solve(total_minutes=1440, record_interval=10)
        
        # 分析各生化指标
        for biomarker, thresholds in safety_thresholds.items():
            print(f"\n📊 分析指标: {biomarker}")
            
            # 提取时间序列
            time_points = [r['time'] for r in state.history]
            
            if biomarker == 'volume':
                values = [r['V_D'] for r in state.history]
            else:
                # 从血浆浓度计算（简化）
                values = [
                    params.plasma_values.get(biomarker, 20) * (1 - r['clearance_ratio'])
                    for r in state.history
                ]
            
            # 创建时间序列对象
            series = BiomarkerTimeSeries(
                biomarker_name=biomarker,
                time_points=time_points,
                values=values,
                upper_threshold=thresholds['upper'],
                lower_threshold=thresholds['lower']
            )
            series.detect_violations()
            
            print(f"  风险等级: {series.risk_level.value}")
            print(f"  违规次数: {len(series.violations)}")
            
            assessment.biomarker_series.append(series)
        
        # 计算综合风险
        assessment.calculate_overall_risk()
        
        # 保存结果
        output_file = self.output_dir / f"risk_assessment_{assessment.prescription_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(assessment.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 风险评估完成")
        print(f"综合风险等级: {assessment.overall_risk_level.value}")
        print(f"风险评分: {assessment.risk_score:.1f}/100")
        print(f"结果已保存到: {output_file}")
        
        return assessment
    
    # ============ 辅助方法 ============
    
    def _run_simulation_with_parameter(
        self, 
        param_name: str, 
        param_value: float
    ) -> Dict:
        """使用指定参数运行模拟"""
        params = ModelParameters(transport_type=TransportType.AVERAGE)
        
        # 设置参数
        if param_name == 'glucose_conc':
            params.glucose_concentration = param_value
        elif param_name == 'fill_volume':
            params.fill_volume = param_value
        elif param_name == 'exchange_time':
            params.exchange_time = param_value
        
        # 运行模拟
        solver = RungeKuttaSolver(params, dt=0.1)
        state = solver.solve(total_minutes=1440, record_interval=60)
        
        # 提取 Kt/V 时间序列
        kt_v_series = [
            r.get('kt_v_urea', 0) 
            for r in state.history
        ]
        
        return {
            'kt_v_urea_series': kt_v_series,
            'final_kt_v': kt_v_series[-1] if kt_v_series else 0
        }
    
    def _prescription_to_params(self, prescription: Dict) -> ModelParameters:
        """将处方转换为模型参数"""
        params = ModelParameters(transport_type=TransportType.AVERAGE)
        params.exchange_time = prescription.get('exchange_time', 240)
        params.fill_volume = prescription.get('fill_volume', 2000)
        params.glucose_concentration = prescription.get('glucose_conc', 1.5)
        return params
