数据格式说明（实验数据采集）

1) sim_time.csv
- 字段: `dt` (float, 分钟), `elapsed_sec` (float 或 null)

2) error_stats.json
- 顶层: 列表，每项为对象:
  - `params`: 参数组合对象（例如 `{transport_type, fill_volume, exchange_time}`）
  - `stats`: 如果成功则为每个溶质的误差统计对象，否则包含 `error` 字段
    - 每个溶质键下包含: `mean_abs_err` (float), `max_abs_err` (float), `samples` (int)

示例:
```
[
  {
    "params": {"transport_type": "average", "fill_volume": 2000, "exchange_time": 60},
    "stats": {"urea": {"mean_abs_err": 0.12, "max_abs_err": 0.8, "samples": 31}, ...}
  }
]
```

3) risk_assessment.json
- 顶层: 列表，每项为对象:
  - `regimen`: 输入的处方/参数对象
  - `risk`: 判定结果对象，例如 `{ risk: true/false, reasons: [...] }` 或 `{ error: ... }`

4) 结果目录
- 所有输出都保存在 `experiments/output/` 中，脚本会自动创建该目录。
