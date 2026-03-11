from experiments.collect_data import DataFormatter
from backend.models.parameters import ModelParameters
from backend.models.solver import RungeKuttaSolver

raw_messy_data = {
    "患者年龄": "三十五岁",
    "体重kg": "70公斤",
    "转运": "快",
    "灌注量": "2000 mL",
    "交换时间": None,
    "额外字段": "不相关的数据"
}

formatter = DataFormatter(default_exchange_time=240)
cleaned = formatter.clean_and_validate(raw_messy_data)
print("Cleaned:", cleaned)

params = ModelParameters.from_dict({
    'age': cleaned['age'],
    'weight': cleaned['weight'],
    'pet_d_p_crea': cleaned.get('pet_d_p_crea'),
    'plasma_values': cleaned['plasma_values'],
    'transport_type': cleaned['transport_type'],
    'fill_volume': cleaned['fill_volume'],
    'exchange_time': cleaned['exchange_time']
})
print('Params summary: fill_volume=', params.fill_volume, 'exchange_time=', params.exchange_time, 'transport=', params.transport_type)

solver = RungeKuttaSolver(params, dt=0.02)
state = solver.solve(total_time=5.0, record_interval=1.0)
print('Simulation finished. t_len=', len(state.history['t']))
