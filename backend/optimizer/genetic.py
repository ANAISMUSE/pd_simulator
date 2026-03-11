"""
遗传算法处方优化器
使用NSGA-II多目标优化算法
"""
import numpy as np
import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from .objectives import OptimizationObjectives

@dataclass
class PhaseGene:
    """自由模式下的阶段基因"""
    dwell_min: float
    fill_volume_l: float
    glucose_pct: float
    phase_name: str = ""
    tidal_ratio: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            'phase_name': self.phase_name,
            'dwell_min': self.dwell_min,
            'fill_volume_l': self.fill_volume_l,
            'glucose_pct': self.glucose_pct,
            'tidal_ratio': self.tidal_ratio
        }


@dataclass
class Prescription:
    """处方基因型"""
    exchange_time: float = 60.0  # min
    fill_volume: float = 2000.0  # mL
    glucose_conc: float = 1.5
    num_exchanges: int = 4
    mode: str = 'structured'
    phases: List[PhaseGene] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        if self.mode == 'freeform':
            return {
                'mode': 'freeform',
                'phases': [phase.to_dict() for phase in self.phases],
                'num_exchanges': len(self.phases)
            }
        return {
            'mode': 'structured',
            'exchange_time': self.exchange_time,
            'fill_volume': self.fill_volume,
            'glucose_conc': self.glucose_conc,
            'num_exchanges': self.num_exchanges
        }
    
    @staticmethod
    def random(mode: str = 'structured', phase_template: Optional[List[Dict]] = None):
        """生成随机处方"""
        if mode == 'freeform':
            template = phase_template or [{'phase_name': '阶段1'}]
            phases = []
            for idx, tpl in enumerate(template):
                dwell_range = tpl.get('dwell_range', [120, 360])
                volume_range = tpl.get('fill_volume_range', [1.5, 2.5])
                glucose_range = tpl.get('glucose_range', [1.5, 4.25])
                phases.append(PhaseGene(
                    dwell_min=random.uniform(*dwell_range),
                    fill_volume_l=random.uniform(*volume_range),
                    glucose_pct=random.uniform(*glucose_range),
                    phase_name=tpl.get('phase_name', f'阶段{idx+1}'),
                    tidal_ratio=tpl.get('tidal_ratio', 1.0)
                ))
            return Prescription(mode='freeform', phases=phases)
        
        return Prescription(
            exchange_time=random.uniform(30, 180),
            fill_volume=random.uniform(1000, 3000),
            glucose_conc=random.choice([1.5, 2.5, 4.25]),
            num_exchanges=random.randint(3, 6),
            mode='structured'
        )
    
    def mutate(self, mutation_rate: float = 0.2, phase_template: Optional[List[Dict]] = None):
        """变异操作"""
        if self.mode == 'freeform':
            template = phase_template or []
            for idx, phase in enumerate(self.phases):
                bounds = template[idx] if idx < len(template) else {}
                dwell_range = bounds.get('dwell_range', [60, 480])
                volume_range = bounds.get('fill_volume_range', [1.0, 3.5])
                glucose_range = bounds.get('glucose_range', [1.5, 4.25])
                
                if random.random() < mutation_rate:
                    phase.dwell_min += random.gauss(0, 15)
                    phase.dwell_min = float(np.clip(phase.dwell_min, dwell_range[0], dwell_range[1]))
                
                if random.random() < mutation_rate:
                    phase.fill_volume_l += random.gauss(0, 0.2)
                    phase.fill_volume_l = float(np.clip(phase.fill_volume_l, volume_range[0], volume_range[1]))
                
                if random.random() < mutation_rate:
                    phase.glucose_pct += random.gauss(0, 0.3)
                    phase.glucose_pct = float(np.clip(phase.glucose_pct, glucose_range[0], glucose_range[1]))
            return
        
        if random.random() < mutation_rate:
            self.exchange_time += random.gauss(0, 10)
            self.exchange_time = float(np.clip(self.exchange_time, 30, 180))
            
        if random.random() < mutation_rate:
            self.fill_volume += random.gauss(0, 200)
            self.fill_volume = float(np.clip(self.fill_volume, 1000, 3000))
            
        if random.random() < mutation_rate:
            self.glucose_conc = random.choice([1.5, 2.5, 4.25])
            
        if random.random() < mutation_rate:
            self.num_exchanges += random.choice([-1, 1])
            self.num_exchanges = int(np.clip(self.num_exchanges, 3, 6))


class GeneticOptimizer:
    """遗传算法优化器"""
    
    def __init__(self,
                 objectives: OptimizationObjectives,
                 population_size: int = 50,
                 generations: int = 30,
                 mutation_rate: float = 0.2,
                 crossover_rate: float = 0.8,
                 mode: str = 'structured',
                 phase_template: Optional[List[Dict]] = None):
        """
        Args:
            objectives: 目标函数评估器
            population_size: 种群大小
            generations: 迭代代数
            mutation_rate: 变异率
            crossover_rate: 交叉率
        """
        self.best_prescription: Optional[Prescription] = None
        self.best_fitness: float = 0.0
        self.objectives = objectives
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        
        self.population: List[Prescription] = []
        self.fitness_history: List[float] = []
        self.mode = mode
        self.phase_template = phase_template or []
        
    def initialize_population(self):
        """初始化种群"""
        self.population = [
            Prescription.random(mode=self.mode, phase_template=self.phase_template)
            for _ in range(self.population_size)
        ]
        print(f"已初始化种群，大小={self.population_size}")
        
    def evaluate_population(self) -> List[float]:
        """评估种群适应度"""
        fitness_scores = []
        for i, individual in enumerate(self.population):
            fitness = self.objectives.fitness_function(individual.to_dict())
            fitness_scores.append(fitness)
            
            # 更新最佳个体
            if fitness > self.best_fitness:
                self.best_fitness = fitness
                self.best_prescription = individual
                
            if (i + 1) % 10 == 0:
                print(f"  已评估 {i+1}/{self.population_size} 个体")
                
        return fitness_scores
    
    def selection(self, fitness_scores: List[float]) -> List[Prescription]:
        """锦标赛选择"""
        selected = []
        tournament_size = 3
        
        for _ in range(self.population_size):
            # 随机选择tournament_size个个体
            indices = random.sample(range(self.population_size), tournament_size)
            tournament_fitness = [fitness_scores[i] for i in indices]
            winner_idx = indices[np.argmax(tournament_fitness)]
            selected.append(self.population[winner_idx])
            
        return selected
    
    def crossover(self, parent1: Prescription, parent2: Prescription) -> Tuple[Prescription, Prescription]:
        """单点交叉"""
        if random.random() > self.crossover_rate:
            return parent1, parent2
        
        if self.mode == 'freeform':
            if not parent1.phases or not parent2.phases:
                return parent1, parent2
            min_len = min(len(parent1.phases), len(parent2.phases))
            if min_len < 2:
                return parent1, parent2
            pivot = random.randint(1, min_len - 1)
            child1_phases = parent1.phases[:pivot] + parent2.phases[pivot:]
            child2_phases = parent2.phases[:pivot] + parent1.phases[pivot:]
            return (
                Prescription(mode='freeform', phases=[copy_phase(p) for p in child1_phases]),
                Prescription(mode='freeform', phases=[copy_phase(p) for p in child2_phases])
            )
        
        child1 = Prescription(
            exchange_time=parent1.exchange_time if random.random() < 0.5 else parent2.exchange_time,
            fill_volume=parent1.fill_volume if random.random() < 0.5 else parent2.fill_volume,
            glucose_conc=parent1.glucose_conc if random.random() < 0.5 else parent2.glucose_conc,
            num_exchanges=parent1.num_exchanges if random.random() < 0.5 else parent2.num_exchanges,
            mode='structured'
        )
        
        child2 = Prescription(
            exchange_time=parent2.exchange_time if random.random() < 0.5 else parent1.exchange_time,
            fill_volume=parent2.fill_volume if random.random() < 0.5 else parent1.fill_volume,
            glucose_conc=parent2.glucose_conc if random.random() < 0.5 else parent1.glucose_conc,
            num_exchanges=parent2.num_exchanges if random.random() < 0.5 else parent1.num_exchanges,
            mode='structured'
        )
        
        return child1, child2
    
    def optimize(self, callback=None) -> Dict:
        """
        执行优化
        
        Args:
            callback: 可选的回调函数，用于报告进度
            
        Returns:
            最优处方及其性能指标
        """
        import time
        start_time = time.time()
        
        print("\n" + "="*70)
        print("🧬 开始遗传算法优化".center(70))
        print("="*70)
        
        # ✅ 打印初始化信息
        print(f"\n📊 算法配置:")
        print(f"   • 优化模式: {self.mode}")
        print(f"   • 种群大小: {self.population_size}")
        print(f"   • 迭代次数: {self.generations}")
        print(f"   • 变异率: {self.mutation_rate:.2%}")
        print(f"   • 交叉率: {self.crossover_rate:.2%}")
        
        if self.phase_template:
            print(f"   • 阶段模板: {len(self.phase_template)} 阶段")
        
        print(f"\n📋 优化目标:")
        print(f"   • 转运类型: {self.objectives.transport_type}")
        print(f"   • 模拟时长: {self.objectives.simulation_time / 60:.1f} 小时")
        
        # ✅ 初始化
        print(f"\n🔄 正在初始化种群...")
        self.initialize_population()
        print(f"✅ 种群初始化完成，共 {len(self.population)} 个个体")
        
        # ✅ 优化主循环
        for generation in range(self.generations):
            print(f"\n{'─'*70}")
            print(f"🧬 第 {generation+1}/{self.generations} 代".center(70))
            print(f"{'─'*70}")
        
            # 评估适应度
            print(f"⏳ 评估种群适应度...")
            fitness_scores = self.evaluate_population()
            avg_fitness = np.mean(fitness_scores)
            max_fitness = np.max(fitness_scores)
            min_fitness = np.min(fitness_scores)
            std_fitness = np.std(fitness_scores)
            
            self.fitness_history.append(self.best_fitness)
            
            # ✅ 详细统计
            print(f"\n📊 适应度统计:")
            print(f"   • 平均值: {avg_fitness:.4f}")
            print(f"   • 最大值: {max_fitness:.4f} {'🏆' if max_fitness > avg_fitness else ''}")
            print(f"   • 最小值: {min_fitness:.4f}")
            print(f"   • 标准差: {std_fitness:.4f}")
            print(f"   • 历史最佳: {self.best_fitness:.4f}")
            
            # ✅ 最佳个体详情
            if self.best_prescription:
                print(f"\n🏆 当前最佳处方:")
                if self.mode == 'freeform':
                    phases = self.best_prescription.phases
                    print(f"   • 模式: 自由阶段")
                    print(f"   • 阶段数: {len(phases)}")
                    print(f"   • 阶段详情:")
                    for i, phase in enumerate(phases, 1):
                        print(f"      {i}. 时长={phase.dwell_min/60:.1f}h, "
                              f"葡萄糖={phase.glucose_pct}%, "
                              f"体积={phase.fill_volume_l*1000:.0f}mL")
                else:
                    print(f"   • 模式: 结构化")
                    print(f"   • 交换周期: {self.best_prescription.exchange_time:.1f} min")
                    print(f"   • 灌注体积: {self.best_prescription.fill_volume:.0f} mL")
                    print(f"   • 葡萄糖浓度: {self.best_prescription.glucose_conc}%")
                    icodextrin_pct = getattr(self.best_prescription, 'icodextrin_percentage', None)
                    if icodextrin_pct is not None:
                        print(f"   • 艾考糊精比例: {icodextrin_pct:.1%}")
            
            # ✅ 种群多样性
            diversity = len(set(str(ind.to_dict()) for ind in self.population))
            print(f"\n🧬 种群多样性: {diversity}/{self.population_size} ({diversity/self.population_size:.1%})")
            
            # 回调
            if callback and self.best_prescription:
                callback({
                    'generation': generation + 1,
                    'avg_fitness': avg_fitness,
                    'best_fitness': self.best_fitness,
                    'best_prescription': self.best_prescription.to_dict(),
                    'diversity': diversity / self.population_size
                })
            
            # ✅ 选择
            print(f"\n🔄 执行选择操作...")
            selected = self.selection(fitness_scores)
            print(f"✅ 选择完成，保留 {len(selected)} 个个体")
            
            # ✅ 交叉和变异
            print(f"🔄 执行交叉和变异...")
            next_generation = []
            crossover_count = 0
            mutation_count = 0
            
            for i in range(0, self.population_size, 2):
                parent1 = selected[i]
                parent2 = selected[min(i+1, self.population_size-1)]
                
                # 交叉
                if np.random.random() < self.crossover_rate:
                    child1, child2 = self.crossover(parent1, parent2)
                    crossover_count += 1
                else:
                    child1, child2 = parent1, parent2
                
                # 变异
                if child1.mutate(self.mutation_rate, self.phase_template):
                    mutation_count += 1
                if child2.mutate(self.mutation_rate, self.phase_template):
                    mutation_count += 1
                
                next_generation.extend([child1, child2])
            
            print(f"   • 交叉次数: {crossover_count}")
            print(f"   • 变异次数: {mutation_count}")
            
            self.population = next_generation[:self.population_size]
            
            # ✅ 精英保留
            if self.best_prescription:
                self.population[0] = self.best_prescription
                print(f"✅ 精英保留：最佳个体已保留到下一代")
            
            # ✅ 收敛判断
            # 只有历史记录足够时才做收敛判断，避免越界
            if generation > 5 and len(self.fitness_history) >= 6:
                recent_improvement = self.fitness_history[-1] - self.fitness_history[-6]
                if abs(recent_improvement) < 0.0001:
                    print(f"\n⚠️  近 5 代适应度提升不明显 (Δ={recent_improvement:.6f})")
                    print(f"   建议：可能已收敛，或需调整变异率/交叉率")
    
        # ✅ 最终评估
        print("\n" + "="*70)
        print("🎯 优化完成！最终评估...".center(70))
        print("="*70)
        
        elapsed_time = time.time() - start_time
        
        if not self.best_prescription:
            raise ValueError("❌ 优化失败：未找到有效处方")
        
        print(f"\n⏱️  总耗时: {elapsed_time:.2f} 秒")
        print(f"🔄 总迭代次数: {self.generations}")
        if self.fitness_history:
            print(f"📈 适应度提升: {self.fitness_history[-1] - self.fitness_history[0]:.4f}")
        else:
            print("📈 适应度提升: N/A（无历史记录）")
        
        # ✅ 评估最优处方
        print(f"\n🔬 评估最优处方性能...")
        final_metrics = self.objectives.evaluate_prescription(self.best_prescription.to_dict())
        
        print(f"\n📊 最终性能指标:")
        for key, value in final_metrics.items():
            if isinstance(value, (int, float)):
                print(f"   • {key}: {value:.4f}")
            else:
                print(f"   • {key}: {value}")
        
        # ✅ 适应度历史摘要
        print(f"\n📈 适应度历史:")
        if self.fitness_history:
            initial = self.fitness_history[0]
            final = self.fitness_history[-1]
            print(f"   • 初始: {initial:.4f}")
            print(f"   • 最终: {final:.4f}")
            delta = final - initial
            if abs(initial) > 1e-12:
                pct = ((final / initial) - 1) * 100
                print(f"   • 提升: {delta:.4f} ({pct:.1f}%)")
            else:
                print(f"   • 提升: {delta:.4f}")
        else:
            print("   • 初始: N/A")
            print("   • 最终: N/A")
            print("   • 提升: N/A")
        
        print("\n" + "="*70)
        print("✅ 优化成功完成！".center(70))
        print("="*70 + "\n")
        
        return {
            'prescription': self.best_prescription.to_dict(),
            'metrics': final_metrics,
            'fitness': self.best_fitness,
            'fitness_history': self.fitness_history,
            'mode': self.mode,
            'elapsed_time': elapsed_time,
            'total_generations': self.generations,
            'final_diversity': len(set(str(ind.to_dict()) for ind in self.population)) / self.population_size
        }



def copy_phase(phase: PhaseGene) -> PhaseGene:
    """复制阶段基因"""
    return PhaseGene(
        dwell_min=phase.dwell_min,
        fill_volume_l=phase.fill_volume_l,
        glucose_pct=phase.glucose_pct,
        phase_name=phase.phase_name,
        tidal_ratio=phase.tidal_ratio
    )
