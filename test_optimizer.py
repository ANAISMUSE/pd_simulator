#!/usr/bin/env python3
"""
测试优化算法修复
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.optimizer.genetic import GeneticOptimizer
from backend.optimizer.objectives import OptimizationObjectives
from backend.models.parameters import TransportType

def test_optimizer():
    """测试优化器是否能正常运行"""
    print("开始测试优化器...")
    
    # 创建目标函数实例
    objectives = OptimizationObjectives(
        transport_type=TransportType.FAST,
        plasma_values={'urea': 28, 'creatinine': 1000, 'beta2m': 20},
        simulation_time=480
    )
    
    # 创建优化器实例
    optimizer = GeneticOptimizer(
        objectives=objectives,
        population_size=10,
        generations=5,
        mutation_rate=0.2,
        crossover_rate=0.8,
        mode='structured'
    )
    
    try:
        # 运行优化
        result = optimizer.optimize()
        print("✅ 结构化模式优化成功!")
        print(f"   最佳适应度: {result['fitness']:.4f}")
        print(f"   优化代数: {result['total_generations']}")
    except Exception as e:
        print(f"❌ 结构化模式优化失败: {e}")
        return False
    
    # 测试自由模式
    try:
        optimizer_freeform = GeneticOptimizer(
            objectives=objectives,
            population_size=10,
            generations=5,
            mutation_rate=0.2,
            crossover_rate=0.8,
            mode='freeform',
            phase_template=[
                {'phase_name': '阶段1', 'dwell_range': [120, 360]},
                {'phase_name': '阶段2', 'dwell_range': [120, 360]}
            ]
        )
        
        result_freeform = optimizer_freeform.optimize()
        print("✅ 自由模式优化成功!")
        print(f"   最佳适应度: {result_freeform['fitness']:.4f}")
        print(f"   优化代数: {result_freeform['total_generations']}")
    except Exception as e:
        print(f"❌ 自由模式优化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = test_optimizer()
    if success:
        print("\n🎉 所有测试通过！优化器修复成功!")
        sys.exit(0)
    else:
        print("\n💥 测试失败！优化器仍有问题.")
        sys.exit(1)