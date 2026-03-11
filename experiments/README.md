自动化实验与数据收集说明

本目录包含用于对腹膜透析三孔模型进行批量实验并采集指标的脚本。

主要文件：
- `collect_data.py`：可直接运行的实验脚本，包含三类实验：
  1. 模拟时间随步长 `dt` 的变化（性能指标）
  2. 不同参数组合下与高精度基准的误差统计（平均误差与最大误差）
  3. 方案判定（基于时间序列的简单风险检测）

输出：
- `experiments/output/sim_time.csv`：记录每次模拟的 `dt` 与耗时（秒）
- `experiments/output/error_stats.json`：对参数组合的误差统计
- `experiments/output/risk_assessment.json`：方案判定结果

运行方式（在仓库根目录）：
```
python experiments/collect_data.py
```

说明：脚本使用项目内的 `backend.models` 中的 `ModelParameters` 与 `RungeKuttaSolver`，默认会生成随机或合成数据用于演示。
