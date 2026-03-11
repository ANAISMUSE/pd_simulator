"""
结果可视化模块
"""
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import numpy as np
from typing import Dict, List, cast
from matplotlib.axes import Axes
from models.solver import PDState
from models.parameters import ModelParameters

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class ResultVisualizer:
    """结果可视化器"""
    
    def __init__(self, state: PDState, params: ModelParameters):
        self.state = state
        self.params = params
        
    def plot_volume_dynamics(self, save_path: str = 'volume_dynamics.png'):
        """绘制体积动态变化"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        t_hours = np.array(self.state.history['t']) / 60  # 转换为小时
        
        # 腹腔内体积
        ax1.plot(t_hours, self.state.history['V_D'], 'b-', linewidth=2)
        ax1.set_xlabel('时间 (小时)', fontsize=12)
        ax1.set_ylabel('腹腔内体积 (mL)', fontsize=12)
        ax1.set_title('腹腔内体积动态变化', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        # 储液库体积
        ax2.plot(t_hours, self.state.history['V_B'], 'r-', linewidth=2)
        ax2.set_xlabel('时间 (小时)', fontsize=12)
        ax2.set_ylabel('储液库体积 (mL)', fontsize=12)
        ax2.set_title('储液库体积动态变化', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"体积动态图已保存: {save_path}")
        
    def plot_solute_concentrations(self, 
                                   solutes: list = ['urea', 'creatinine', 'glucose'],
                                   save_path: str = 'concentrations.png'):
        """绘制溶质浓度变化"""
        fig, axes = plt.subplots(len(solutes), 1, figsize=(12, 4*len(solutes)))
        # Ensure axes is always a list of Axes objects
        if len(solutes) == 1:
            axes_list: List[Axes] = [cast(Axes, axes)]
        else:
            axes_list = [cast(Axes, ax) for ax in axes.flatten()]
        
        t_hours = np.array(self.state.history['t']) / 60
        
        for i, solute_key in enumerate(solutes):
            solute = self.params.solutes[solute_key]
            ax = axes_list[i]  # Get the Axes object once
            
            # 腹腔内浓度
            C_D = self.state.history[f'C_D_{solute_key}']
            ax.plot(t_hours, C_D, 'b-', linewidth=2, label='腹腔内浓度')
            
            # 血浆浓度参考线
            C_P = float(solute.plasma_concentration)
            ax.axhline(y=C_P, color='r', linestyle='--', linewidth=2,  # type: ignore
                       label=f'血浆浓度 ({C_P:.2f})')
            
            ax.set_xlabel('时间 (小时)', fontsize=12)
            ax.set_ylabel(f'浓度 ({"mmol/L" if solute_key != "albumin" else "g/L"})', 
                          fontsize=12)
            ax.set_title(f'{solute.name}浓度动态', fontsize=14, fontweight='bold')
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"浓度动态图已保存: {save_path}")
        
    def calculate_clearance(self, solute_key: str) -> Dict[str, float]:
        """
        计算溶质清除率
        
        Clearance = (V_drain * C_drain) / (C_plasma * time)
        
        Returns:
            {'total_clearance': L, 'weekly_clearance': L, 'daily_average': L/day}
        """
        solute = self.params.solutes[solute_key]
        C_P = solute.plasma_concentration
        
        # 找到完整的透析周期
        total_time = self.state.history['t'][-1]  # min
        num_cycles = int(total_time / self.params.exchange_time)
        
        # 计算总清除量(简化:使用最终引流液浓度)
        C_D_final = self.state.history[f'C_D_{solute_key}'][-1]
        V_drain_total = self.params.fill_volume * num_cycles  # mL
        
        total_removed = V_drain_total * C_D_final / 1000  # mmol 或 g
        total_clearance = total_removed / C_P  # L
        
        # 标准化到每周
        time_days = total_time / (60 * 24)
        weekly_clearance = total_clearance / time_days * 7
        
        return {
            'total_clearance_L': total_clearance,
            'weekly_clearance_L': weekly_clearance,
            'daily_average_L': total_clearance / time_days,
            'num_cycles': num_cycles
        }
    
    def calculate_ultrafiltration(self) -> Dict[str, float]:
        """计算超滤量"""
        V_initial = self.state.history['V_D'][0]
        V_final = self.state.history['V_D'][-1]
        
        total_time = self.state.history['t'][-1]  # min
        num_cycles = int(total_time / self.params.exchange_time)
        
        # 每个周期的净超滤
        uf_per_cycle = (V_final - V_initial) / num_cycles
        
        # 24小时超滤量
        cycles_per_day = (24 * 60) / self.params.exchange_time
        uf_24h = uf_per_cycle * cycles_per_day
        
        return {
            'uf_per_cycle_mL': uf_per_cycle,
            'uf_24h_mL': uf_24h,
            'uf_24h_L': uf_24h / 1000
        }
    
    def generate_report(self, save_path: str = 'simulation_report.txt'):
        """生成模拟报告"""
        report = []
        report.append("=" * 60)
        report.append("腹膜透析三孔模型模拟报告")
        report.append("=" * 60)
        report.append(f"\n【模型参数】")
        report.append(f"转运类型: {self.params.transport_type.value}")
        report.append(f"总过滤系数 LpS: {self.params.LpS:.4f} mL/(min·mmHg)")
        report.append(f"灌注体积: {self.params.fill_volume} mL")
        report.append(f"交换周期: {self.params.exchange_time} min")
        report.append(f"葡萄糖浓度: {self.params.glucose_concentration}%")
        
        report.append(f"\n【超滤效果】")
        uf_results = self.calculate_ultrafiltration()
        report.append(f"单次交换超滤: {uf_results['uf_per_cycle_mL']:.1f} mL")
        report.append(f"24小时超滤: {uf_results['uf_24h_L']:.2f} L")
        
        report.append(f"\n【清除率】")
        for solute_key in ['urea', 'creatinine', 'beta2m']:
            clearance = self.calculate_clearance(solute_key)
            solute_name = self.params.solutes[solute_key].name
            report.append(f"\n{solute_name}:")
            report.append(f"  每周清除率: {clearance['weekly_clearance_L']:.2f} L/周")
            report.append(f"  日均清除率: {clearance['daily_average_L']:.2f} L/天")
        
        report.append("\n" + "=" * 60)
        
        report_text = "\n".join(report)
        print(report_text)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(f"\n报告已保存: {save_path}")
