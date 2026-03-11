"""实验数据收集脚本

运行三类自动化实验并将结果写入 `experiments/output/`:
1) 模拟耗时随时间步长 dt 的变化
2) 不同参数组合下与高精度基准的误差统计
3) 简单的方案判定（基于时间序列的启发式风险规则）

说明：本脚本依赖项目内的 `backend.models` 模块（已在仓库中）。
"""
import os
import json
import csv
import time
from typing import Tuple
import itertools
import argparse
import random
from typing import Dict, Any, List, Tuple

import numpy as np
try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None

# 引入项目内模拟器和参数
from backend.models.parameters import ModelParameters, TransportType
from backend.models.solver import RungeKuttaSolver


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_simulation(params: ModelParameters, dt: float, total_time: float = 60.0,
                   record_interval: float = 1.0) -> Tuple[Any, float]:
    """运行一次模拟并返回 (state, elapsed_seconds)"""
    solver = RungeKuttaSolver(params, dt=dt)
    start = time.perf_counter()
    state = solver.solve(total_time, record_interval=record_interval)
    elapsed = time.perf_counter() - start
    return state, elapsed


def experiment_sim_time(dt_list: List[float], total_time: float = 60.0):
    """测量不同 dt 下的模拟耗时，结果写入 CSV。"""
    rows = []
    params = ModelParameters(transport_type=TransportType.AVERAGE)
    for dt in dt_list:
        print(f"Running sim_time experiment dt={dt}")
        try:
            _, elapsed = run_simulation(params, dt, total_time=total_time)
        except Exception as e:
            elapsed = None
            print(f"Error for dt={dt}: {e}")
        rows.append({'dt': dt, 'elapsed_sec': elapsed})

    csv_path = os.path.join(OUTPUT_DIR, 'sim_time.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['dt', 'elapsed_sec'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"Wrote sim time results to {csv_path}")


def interpolate_series(base_t: List[float], base_y: List[float], query_t: List[float]) -> np.ndarray:
    return np.interp(query_t, base_t, base_y)


def compute_error_stats(ground: Any, test: Any, solutes: List[str]) -> Dict[str, Any]:
    """计算每个溶质的误差序列，并返回 mean 和 max"""
    gt_t = np.array(ground.history['t'])
    res = {}
    for s in solutes:
        gt_key = f'C_D_{s}'
        if gt_key not in ground.history or f'C_D_{s}' not in test.history:
            continue
        gt_y = np.array(ground.history[gt_key])
        test_t = np.array(test.history['t'])
        test_y = np.array(test.history[gt_key])
        # 将基准插值到测试时间点
        gt_interp = interpolate_series(gt_t, gt_y, test_t)
        abs_err = np.abs(gt_interp - test_y)
        res[s] = {
            'mean_abs_err': float(np.mean(abs_err)),
            'max_abs_err': float(np.max(abs_err)),
            'samples': len(abs_err)
        }
    return res


def experiment_error_stats(param_grid: Dict[str, List[Any]], dt_test: float = 0.1,
                           dt_truth: float = 0.001, total_time: float = 60.0):
    """在参数网格上计算误差统计，基准使用高精度 dt_truth。"""
    keys = list(param_grid.keys())
    combos = list(itertools.product(*(param_grid[k] for k in keys)))
    print(f"Running error stats for {len(combos)} combos")
    errors = []
    solutes = ['urea', 'creatinine', 'glucose', 'sodium']

    for combo in combos:
        combo_dict = dict(zip(keys, combo))
        print(f"Combo: {combo_dict}")
        # 支持传入 TransportType 或字符串
        tp = combo_dict.get('transport_type', TransportType.AVERAGE)
        if isinstance(tp, str):
            tp_enum = TransportType(tp)
        else:
            tp_enum = tp
        params = ModelParameters(transport_type=tp_enum)
        # apply simple params if provided
        if 'fill_volume' in combo_dict:
            params.fill_volume = float(combo_dict['fill_volume'])
        if 'exchange_time' in combo_dict:
            params.exchange_time = float(combo_dict['exchange_time'])

        # ground truth (高精度)
        try:
            ground, _ = run_simulation(params, dt_truth, total_time=total_time)
            test, _ = run_simulation(params, dt_test, total_time=total_time)
            stats = compute_error_stats(ground, test, solutes)
        except Exception as e:
            print(f"Error in combo {combo_dict}: {e}")
            stats = {'error': str(e)}

        # 将不可序列化的枚举值转为可序列化形式
        combo_serial = {k: (v.value if isinstance(v, TransportType) else v) for k, v in combo_dict.items()}
        errors.append({'params': combo_serial, 'stats': stats})

    out_path = os.path.join(OUTPUT_DIR, 'error_stats.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    print(f"Wrote error stats to {out_path}")


def assess_risk_from_state(state: Any) -> Dict[str, Any]:
    """基于时间序列进行简单的风险判定，返回判定结果与命中规则。"""
    # 可配置的临床阈值（可根据真实临床/文献调整）
    THRESHOLDS = {
        # 腹腔白蛋白浓度突然增加/减少幅度 (g/L)
        'albumin_jump_g_per_L': 0.5,
        # 腹腔体积波动阈值 (mL)
        'volume_variation_mL': 2000,
        # 尿素在腹腔内浓度的标准差阈值 (mmol/L)
        'urea_std_mmol_per_L': 5.0,
    }

    res = {'risk': False, 'reasons': []}
    t = np.array(state.history['t'])

    # albumin 判定（示例阈值）
    key_alb = 'C_D_albumin'
    if key_alb in state.history:
        alb = np.array(state.history[key_alb])
        # 使用相对或绝对变化判断
        delta_alb = np.max(alb) - alb[0]
        if delta_alb > THRESHOLDS['albumin_jump_g_per_L']:
            res['risk'] = True
            res['reasons'].append(f'albumin_jump={float(delta_alb):.3f}g/L')

    # 体积波动判定
    V = np.array(state.history['V_D'])
    if np.max(V) - np.min(V) > THRESHOLDS['volume_variation_mL']:
        res['risk'] = True
        res['reasons'].append('large_volume_variation')

    # 尿素波动判定
    key_urea = 'C_D_urea'
    if key_urea in state.history:
        urea = np.array(state.history[key_urea])
        if np.std(urea) > THRESHOLDS['urea_std_mmol_per_L']:
            res['risk'] = True
            res['reasons'].append('urea_high_variability')

    return res


def experiment_risk_assessment(regimen_params: List[Dict[str, Any]], dt: float = 0.01, total_time: float = 60.0):
    """基于多组透析处方/参数运行模拟并判定风险，结果写入 JSON。"""
    out = []
    for rp in regimen_params:
        params = ModelParameters(transport_type=rp.get('transport_type', TransportType.AVERAGE))
        params.fill_volume = rp.get('fill_volume', params.fill_volume)
        params.exchange_time = rp.get('exchange_time', params.exchange_time)
        print(f"Assess regimen: {rp}")
        try:
            state, _ = run_simulation(params, dt, total_time=total_time)
            risk = assess_risk_from_state(state)
        except Exception as e:
            risk = {'error': str(e)}
        # 序列化 regimen 中的 TransportType
        rp_serial = {k: (v.value if isinstance(v, TransportType) else v) for k, v in rp.items()}
        out.append({'regimen': rp_serial, 'risk': risk})

    out_path = os.path.join(OUTPUT_DIR, 'risk_assessment.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote risk assessment to {out_path}")


def plot_sim_time(csv_path: str, plots_dir: str):
    if plt is None:
        print('matplotlib not available; skipping sim_time plot')
        return
    import pandas as pd
    df = pd.read_csv(csv_path)
    df = df.dropna()
    plt.figure()
    plt.plot(df['dt'], df['elapsed_sec'], marker='o')
    plt.xlabel('dt (min)')
    plt.ylabel('elapsed (sec)')
    plt.title('Simulation time vs dt')
    plt.grid(True)
    os.makedirs(plots_dir, exist_ok=True)
    out = os.path.join(plots_dir, 'sim_time.png')
    plt.savefig(out)
    plt.close()
    print(f'Wrote plot {out}')


def summarize_state(state: Any) -> Dict[str, Any]:
    """从 PDState 中抽取简单 summary 指标"""
    out = {}
    t = np.array(state.history['t'])
    out['duration_min'] = float(t[-1]) if len(t) > 0 else 0.0
    V = np.array(state.history['V_D'])
    out['V_max'] = float(np.max(V))
    out['V_min'] = float(np.min(V))
    out['V_mean'] = float(np.mean(V))

    # 溶质 summary: final concentration & mean
    solutes = []
    for k in state.history.keys():
        if k.startswith('C_D_'):
            solutes.append(k.replace('C_D_', ''))
    out['solutes'] = {}
    for s in solutes:
        key = f'C_D_{s}'
        arr = np.array(state.history[key])
        out['solutes'][s] = {
            'final': float(arr[-1]) if len(arr) > 0 else None,
            'mean': float(np.mean(arr)) if len(arr) > 0 else None,
            'std': float(np.std(arr)) if len(arr) > 0 else None
        }

    return out


def generate_random_input(seed: int = None) -> Dict[str, Any]:
    """生成一个随机患者 + 处方输入，变化较大以覆盖边界"""
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    # 患者属性（大范围变化）
    age = int(np.clip(int(np.random.normal(50, 20)), 18, 90))
    weight = float(np.clip(np.random.normal(70, 25), 35.0, 140.0))
    pet = float(np.clip(np.random.uniform(0.4, 1.1), 0.3, 1.2))

    # 血浆生化：以模型默认值为基准，加大扰动 +/-50%
    base = ModelParameters().solutes
    plasma_values = {}
    for s, sol in base.items():
        base_val = sol.plasma_concentration
        factor = float(np.random.uniform(0.5, 1.5))
        plasma_values[s] = float(max(0.0, base_val * factor))

    # 处方（范围较大）
    fill_volume = int(np.random.choice([1000, 1500, 2000, 2500, 3000]))
    exchange_time = int(np.random.choice([30, 45, 60, 90, 120]))
    # transport type inferred from pet
    if pet > 0.81:
        tt = TransportType.FAST
    elif pet < 0.65:
        tt = TransportType.SLOW
    else:
        tt = TransportType.AVERAGE

    regimen = {
        'fill_volume': fill_volume,
        'exchange_time': exchange_time,
        'transport_type': tt
    }

    patient = {
        'age': age,
        'weight': weight,
        'pet_d_p_crea': pet,
        'plasma_values': plasma_values
    }

    return {'patient': patient, 'regimen': regimen}


class DataFormatter:
    """将杂乱的原始输入清洗并格式化为模型能够接受的结构。

    使用场景示例：
        raw = { '患者年龄': '三十五岁', '体重kg': '70公斤', '转运': '快', '灌注量': '2000 mL', '交换时间': None }
        fmt = DataFormatter()
        cleaned = fmt.clean_and_validate(raw)
    返回结构参考：
        {
            'age': 35,
            'weight': 70.0,
            'pet_d_p_crea': 0.73,
            'plasma_values': {...},
            'transport_type': 'fast',
            'fill_volume': 2000,
            'exchange_time': 240
        }
    """

    TRANSPORT_MAP = {
        '快': 'fast', '快速': 'fast', 'f': 'fast', 'fast': 'fast',
        '中': 'average', '平均': 'average', 'average': 'average',
        '慢': 'slow', '慢速': 'slow', 's': 'slow', 'slow': 'slow'
    }

    def __init__(self, default_exchange_time: int = 240):
        self.default_exchange_time = default_exchange_time

    @staticmethod
    def _parse_number_with_unit(value: Any) -> float:
        """尝试从字符串中解析数字（会去掉非数字和小数点字符）。"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value)
        # extract digits, decimal point and minus
        import re
        m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s.replace(',', '.'))
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
        # try parsing simple Chinese numerals (e.g., 三十五 -> 35)
        chinese_map = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        if any(ch in s for ch in chinese_map.keys()) or '十' in s:
            total = 0
            if '十' in s:
                parts = s.split('十')
                left = parts[0]
                right = parts[1] if len(parts) > 1 else ''
                if left == '':
                    total += 10
                else:
                    total += chinese_map.get(left[-1], 0) * 10
                if right != '':
                    total += chinese_map.get(right[0], 0)
            else:
                # simple sequence of digits in chinese
                for ch in s:
                    if ch in chinese_map:
                        total = total * 10 + chinese_map[ch]
            return float(total)
        return None

    def clean_and_validate(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        # map common Chinese/variant keys to canonical names
        mapping = {
            '患者年龄': 'age', 'age': 'age', '年龄': 'age',
            '体重kg': 'weight', '体重': 'weight', 'weight': 'weight',
            '转运': 'transport_type', 'transport_type': 'transport_type', 'transport': 'transport_type',
            '灌注量': 'fill_volume', 'fill_volume': 'fill_volume', '灌注体积': 'fill_volume',
            '交换时间': 'exchange_time', 'exchange_time': 'exchange_time'
        }

        out = {
            'age': None,
            'weight': None,
            'pet_d_p_crea': None,
            'plasma_values': {},
            'transport_type': None,
            'fill_volume': None,
            'exchange_time': None
        }

        # first-pass field mapping
        for k, v in raw.items():
            key = mapping.get(k, None)
            if key:
                if key == 'age':
                    val = self._parse_number_with_unit(v)
                    out['age'] = int(val) if val is not None else None
                elif key == 'weight':
                    val = self._parse_number_with_unit(v)
                    out['weight'] = float(val) if val is not None else None
                elif key == 'transport_type':
                    s = str(v).strip()
                    out['transport_type'] = self.TRANSPORT_MAP.get(s, s.lower())
                elif key == 'fill_volume':
                    val = self._parse_number_with_unit(v)
                    out['fill_volume'] = int(val) if val is not None else None
                elif key == 'exchange_time':
                    val = self._parse_number_with_unit(v)
                    out['exchange_time'] = int(val) if val is not None else None
            else:
                # try to detect plasma values by known solute names
                lk = k.lower()
                if '尿素' in k or 'urea' in lk:
                    out['plasma_values']['urea'] = self._parse_number_with_unit(v)
                elif '肌酐' in k or 'creat' in lk:
                    out['plasma_values']['creatinine'] = self._parse_number_with_unit(v)
                elif '葡萄糖' in k or 'glucose' in lk:
                    out['plasma_values']['glucose'] = self._parse_number_with_unit(v)
                elif '钠' in k or 'sodium' in lk:
                    out['plasma_values']['sodium'] = self._parse_number_with_unit(v)
                elif '白蛋白' in k or 'albumin' in lk:
                    out['plasma_values']['albumin'] = self._parse_number_with_unit(v)
                elif 'beta' in lk or 'β' in k:
                    out['plasma_values']['beta2m'] = self._parse_number_with_unit(v)
                else:
                    # ignore unrelated fields
                    pass

        # fill defaults
        if out['transport_type'] is None:
            out['transport_type'] = 'average'
        if out['fill_volume'] is None:
            out['fill_volume'] = 2000
        if out['exchange_time'] is None:
            out['exchange_time'] = self.default_exchange_time

        # ensure plasma keys present (use ModelParameters defaults if absent)
        base_mp = ModelParameters()
        base_keys = list(base_mp.solutes.keys())
        for sk in base_keys:
            if sk not in out['plasma_values'] or out['plasma_values'][sk] is None:
                # use model default plasma concentration
                out['plasma_values'][sk] = float(base_mp.solutes[sk].plasma_concentration)

        # pet_d_p_crea might be provided separately; default to average
        if out.get('pet_d_p_crea') is None:
            out['pet_d_p_crea'] = 0.73

        return out


def normalize_input(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将任意输入标准化为规范格式，便于保存与下游处理。

    规范化规则：
    - `transport_type` 始终为字符串（'fast'|'average'|'slow'）
    - `plasma_values` 保证包含模型中定义的所有溶质键，缺失时填 None
    - 数值字段转为基本 Python 数字类型（int/float）
    - 去除不可序列化的对象（比如枚举实例）
    """
    out = {}
    patient = raw.get('patient', {})
    regimen = raw.get('regimen', {})

    # normalize patient
    out_patient = {}
    out_patient['age'] = int(patient.get('age')) if patient.get('age') is not None else None
    out_patient['weight'] = float(patient.get('weight')) if patient.get('weight') is not None else None
    out_patient['pet_d_p_crea'] = float(patient.get('pet_d_p_crea')) if patient.get('pet_d_p_crea') is not None else None

    # plasma values: ensure all solutes exist
    base_params = ModelParameters()
    solute_keys = [k for k in base_params.solutes.keys()]
    raw_plasma = patient.get('plasma_values', {}) or {}
    out_plasma = {}
    for k in solute_keys:
        v = raw_plasma.get(k)
        out_plasma[k] = float(v) if v is not None else None

    out_patient['plasma_values'] = out_plasma

    # normalize regimen
    out_regimen = {}
    tp = regimen.get('transport_type')
    if isinstance(tp, TransportType):
        out_regimen['transport_type'] = tp.value
    else:
        out_regimen['transport_type'] = str(tp) if tp is not None else None

    out_regimen['fill_volume'] = int(regimen.get('fill_volume')) if regimen.get('fill_volume') is not None else None
    out_regimen['exchange_time'] = int(regimen.get('exchange_time')) if regimen.get('exchange_time') is not None else None

    return {'patient': out_patient, 'regimen': out_regimen}


# Load JSON schema for inputs (used for validation)
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'input_schema.json')
try:
    with open(_SCHEMA_PATH, 'r', encoding='utf-8') as _f:
        INPUT_SCHEMA = json.load(_f)
except Exception:
    INPUT_SCHEMA = None


def validate_input_schema(data: Dict[str, Any]) -> Tuple[bool, Any]:
    """使用 JSON Schema 校验输入；如果没有安装 jsonschema 库，则回退到轻量级检查。

    返回 (is_valid, errors)。errors 为 None 或错误描述。
    """
    # 首先尝试使用 jsonschema（如果可用）
    try:
        import jsonschema
        from jsonschema import ValidationError
    except Exception:
        jsonschema = None

    if INPUT_SCHEMA is None:
        return False, 'input_schema.json 未找到'

    if jsonschema is not None:
        try:
            jsonschema.validate(instance=data, schema=INPUT_SCHEMA)
            return True, None
        except Exception as e:
            return False, str(e)

    # 回退到轻量级检查：确保必需键存在并且 plasma_values 包含模型溶质键
    try:
        if 'patient' not in data or 'regimen' not in data:
            return False, '缺少 patient 或 regimen 字段'
        patient = data['patient']
        regimen = data['regimen']
        for req in ['age', 'weight', 'pet_d_p_crea', 'plasma_values']:
            if req not in patient:
                return False, f'patient 缺少字段 {req}'
        if not isinstance(patient.get('plasma_values', {}), dict):
            return False, 'patient.plasma_values 必须是对象'

        base_params = ModelParameters()
        for key in base_params.solutes.keys():
            # allowed to be None, but key must exist
            if key not in patient['plasma_values']:
                return False, f'plasma_values 缺少溶质键 {key}'

        for req in ['transport_type', 'fill_volume', 'exchange_time']:
            if req not in regimen:
                return False, f'regimen 缺少字段 {req}'

        return True, None
    except Exception as e:
        return False, str(e)


def generate_random_runs(n: int, dt: float = 0.01, total_time: float = 30.0, save_time_series: bool = True):
    """生成 n 个随机输入并运行模拟，保存每次的 JSON 与可选 NPZ time_series

    输出路径： `experiments/output/runs/run_<i>.json` 和 `runs/run_<i>.npz`
    同时生成 `experiments/output/runs_summary.json` 与 `runs_summary.csv`
    """
    runs_dir = os.path.join(OUTPUT_DIR, 'runs')
    plots_dir = os.path.join(OUTPUT_DIR, 'plots')
    os.makedirs(runs_dir, exist_ok=True)
    os.makedirs(plots_dir, exist_ok=True)

    summaries = []
    for i in range(1, n + 1):
        seed = int(time.time() * 1000) % (2**31 - 1)
        inp = generate_random_input(seed)
        # prepare ModelParameters
        tp = inp['regimen']['transport_type']
        if isinstance(tp, str):
            tp_enum = TransportType(tp)
        else:
            tp_enum = tp

        params = ModelParameters(transport_type=tp_enum)
        params.update_from_patient_data(inp['patient']['pet_d_p_crea'], inp['patient']['plasma_values'])
        params.fill_volume = inp['regimen']['fill_volume']
        params.exchange_time = inp['regimen']['exchange_time']

        print(f"[run {i}/{n}] seed={seed} tp={tp_enum} fill={params.fill_volume} exch={params.exchange_time}")
        start = time.perf_counter()
        state = RungeKuttaSolver(params, dt=dt).solve(total_time, record_interval=1.0)
        elapsed = time.perf_counter() - start

        # save time_series as npz if requested
        ts_filename = None
        if save_time_series:
            arrays = {}
            for k, v in state.history.items():
                arrays[k] = np.array(v)
            ts_filename = os.path.join(runs_dir, f'run_{i:04d}.npz')
            try:
                np.savez_compressed(ts_filename, **arrays)
            except Exception:
                ts_filename = None

        summary = summarize_state(state)
        normalized = normalize_input(inp)
        run_record = {
            'id': i,
            'seed': seed,
            'input': normalized,
            'elapsed_sec': float(elapsed),
            'summary': summary,
            'time_series_path': os.path.relpath(ts_filename, start=os.path.dirname(OUTPUT_DIR)) if ts_filename else None
        }

        # write per-run JSON
        # validate normalized input against schema and record any errors
        valid, errors = validate_input_schema(normalized)
        run_record['validation_valid'] = bool(valid)
        run_record['validation_errors'] = errors

        run_json_path = os.path.join(runs_dir, f'run_{i:04d}.json')
        with open(run_json_path, 'w', encoding='utf-8') as f:
            json.dump(run_record, f, ensure_ascii=False, indent=2)

        summaries.append(run_record)

    # write aggregated summaries
    summary_json = os.path.join(runs_dir, 'runs_summary.json')
    with open(summary_json, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)

    # also write CSV summary (one row per run)
    csv_path = os.path.join(runs_dir, 'runs_summary.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['id', 'seed', 'tp', 'fill_volume', 'exchange_time', 'elapsed_sec', 'V_max', 'V_min', 'V_mean']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in summaries:
            row = {
                'id': r['id'],
                'seed': r['seed'],
                'tp': r['input']['regimen']['transport_type'],
                'fill_volume': r['input']['regimen']['fill_volume'],
                'exchange_time': r['input']['regimen']['exchange_time'],
                'elapsed_sec': r['elapsed_sec'],
                'V_max': r['summary'].get('V_max'),
                'V_min': r['summary'].get('V_min'),
                'V_mean': r['summary'].get('V_mean')
            }
            writer.writerow(row)

    print(f"Wrote {len(summaries)} runs to {runs_dir}")


def plot_error_stats_json(json_path: str, plots_dir: str):
    if plt is None:
        print('matplotlib not available; skipping error plots')
        return


    

    import pandas as pd
    with open(json_path, 'r', encoding='utf-8') as f:
        errors = json.load(f)

    # 展平为 DataFrame: params_str, solute, mean_abs_err, max_abs_err
    rows = []
    for item in errors:
        params = item.get('params', {})
        stats = item.get('stats', {})
        params_str = json.dumps(params, ensure_ascii=False)
        if isinstance(stats, dict) and 'error' in stats:
            continue
        for solute, svals in stats.items():
            rows.append({'params': params_str, 'solute': solute,
                         'mean_abs_err': svals.get('mean_abs_err'),
                         'max_abs_err': svals.get('max_abs_err')})

    if not rows:
        print('No error stats rows to plot')
        return

    df = pd.DataFrame(rows)
    os.makedirs(plots_dir, exist_ok=True)

    # CSV 导出
    csv_out = os.path.join(plots_dir, 'error_stats_flat.csv')
    df.to_csv(csv_out, index=False, encoding='utf-8')
    print(f'Wrote flattened error CSV to {csv_out}')

    # 按溶质绘制条形图（mean & max）
    grouped = df.groupby('solute')
    for solute, g in grouped:
        plt.figure(figsize=(8,4))
        x = np.arange(len(g))
        plt.bar(x - 0.15, g['mean_abs_err'].astype(float), width=0.3, label='mean_abs_err')
        plt.bar(x + 0.15, g['max_abs_err'].astype(float), width=0.3, label='max_abs_err')
        plt.xticks(x, [p[:60] + '...' if len(p) > 60 else p for p in g['params']], rotation=45, ha='right')
        plt.ylabel('Error')
        plt.title(f'Error stats for {solute}')
        plt.legend()
        plt.tight_layout()
        out = os.path.join(plots_dir, f'error_{solute}.png')
        plt.savefig(out)
        plt.close()
        print(f'Wrote plot {out}')


def main():
    parser = argparse.ArgumentParser(description='Run experiments for PD simulator')
    parser.add_argument('--random', '-r', type=int, default=0,
                        help='Generate N random runs (saves runs/run_<i>.json and compressed time-series)')
    parser.add_argument('--nprocs', type=int, default=1, help='Not used - placeholder for parallelism')
    parser.add_argument('--dt', type=float, default=0.01, help='dt to use for random runs (min)')
    parser.add_argument('--total_time', type=float, default=30.0, help='Total simulation time (min)')
    args = parser.parse_args()

    # default experiments
    dt_list = [0.5, 0.1, 0.05, 0.01, 0.005]
    experiment_sim_time(dt_list, total_time=30.0)

    param_grid = {
        'transport_type': [TransportType.AVERAGE, TransportType.FAST],
        'fill_volume': [1500, 2000],
        'exchange_time': [60, 90]
    }
    experiment_error_stats(param_grid, dt_test=0.05, dt_truth=0.001, total_time=30.0)

    regimen_params = [
        {'transport_type': TransportType.AVERAGE, 'fill_volume': 2000, 'exchange_time': 60},
        {'transport_type': TransportType.FAST, 'fill_volume': 2500, 'exchange_time': 45},
        {'transport_type': TransportType.SLOW, 'fill_volume': 1500, 'exchange_time': 120}
    ]
    experiment_risk_assessment(regimen_params, dt=0.01, total_time=30.0)

    # 如果指定了随机运行则执行
    if args.random and args.random > 0:
        generate_random_runs(args.random, dt=args.dt, total_time=args.total_time, save_time_series=True)


if __name__ == '__main__':
    main()
