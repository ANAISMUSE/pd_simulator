"""
腹膜透析三孔模型主程序
"""
import sys
from models.parameters import ModelParameters, TransportType, PatientData
from models.solver import RungeKuttaSolver
from backend.utils.visualization import ResultVisualizer


def main():
    print("=" * 70)
    print("腹膜透析三孔模型生化指标模拟系统".center(70))
    print("Extended Three-Pore Model for Peritoneal Dialysis".center(70))
    print("=" * 70)
    
    # ============ 1. 初始化模型参数 ============
    print("\n[步骤1] 初始化模型参数...")
    
    # 创建平均转运类型的患者
    params = ModelParameters(transport_type=TransportType.AVERAGE)
    
    # 可选:根据患者数据个性化参数
    patient = PatientData(patient_id="CN_001")
    patient.pet_d_p_crea = 0.73  # PET D/Pcrea (4h)
    patient.plasma_values = {
        'urea': 25.0,  # 尿毒症患者
        'creatinine': 1.2,
        'glucose': 5.5,
        'sodium': 138.0,
        'beta2m': 0.005,
        'albumin': 38.0
    }
    
    params.update_from_patient_data(
        patient.pet_d_p_crea,
        patient.plasma_values
    )
    
    print(f"  - 转运类型: {params.transport_type.value}")
    print(f"  - LpS: {params.LpS:.4f} mL/(min·mmHg)")
    print(f"  - 血浆尿素: {params.solutes['urea'].plasma_concentration} mmol/L")
    
    # ============ 2. 配置透析处方 ============
    print("\n[步骤2] 配置透析处方...")
    
    params.exchange_time = 90.0  # 90分钟/周期
    params.fill_volume = 2000.0  # 2L
    params.glucose_concentration = 1.5  # 1.5%
    
    print(f"  - 交换周期: {params.exchange_time} min")
    print(f"  - 灌注体积: {params.fill_volume} mL")
    print(f"  - 葡萄糖浓度: {params.glucose_concentration}%")
    
    # ============ 3. 运行模拟 ============
    print("\n[步骤3] 开始数值模拟...")
    
    solver = RungeKuttaSolver(params, dt=0.001)
    
    # 模拟24小时
    total_time = 24 * 60  # 24小时 = 1440分钟
    state = solver.solve(total_time, record_interval=1.0)
    
    # ============ 4. 结果分析与可视化 ============
    print("\n[步骤4] 生成结果报告...")
    
    visualizer = ResultVisualizer(state, params)
    
    # 生成图表
    visualizer.plot_volume_dynamics('output/volume_dynamics.png')
    visualizer.plot_solute_concentrations(
        solutes=['urea', 'creatinine', 'glucose'],
        save_path='output/concentrations.png'
    )
    
    # 生成文本报告
    visualizer.generate_report('output/simulation_report.txt')
    
    print("\n" + "=" * 70)
    print("模拟完成!所有结果已保存到 output/ 目录".center(70))
    print("=" * 70)


if __name__ == "__main__":
    try:
        import os
        os.makedirs('output', exist_ok=True)
        main()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
