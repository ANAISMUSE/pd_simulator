from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import copy
import os
import sys
from functools import wraps

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired  # type: ignore
from werkzeug.security import generate_password_hash, check_password_hash  # type: ignore
import traceback

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from database import (
    db,
    User,
    Patient,
    RegimenTemplate,
    SimulationHistory,
    PatientBiochemistrySnapshot,
    RegimenAuditLog,
    apply_schema_migrations,
)
from optimizer.genetic import GeneticOptimizer
from optimizer.objectives import OptimizationObjectives
from models.parameters import TransportType
from sqlalchemy import or_  # type: ignore

app = Flask(__name__)
CORS(app)

# ==================== 数据库配置 ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///patients.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('PD_SECRET_KEY', os.getenv('SECRET_KEY', 'pd-simulator-dev-secret'))
db.init_app(app)

# 创建数据库表
with app.app_context():
    db.create_all()
    apply_schema_migrations(app)

# ==================== 鉴权（Token）====================

_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='pd-auth')

def _make_token(user_id: int) -> str:
    return _serializer.dumps({'uid': user_id})

def _verify_token(token: str, max_age_seconds: int = 7 * 24 * 3600) -> Optional[int]:
    try:
        data = _serializer.loads(token, max_age=max_age_seconds)
        uid = data.get('uid')
        return int(uid) if uid is not None else None
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None

def _get_bearer_token() -> Optional[str]:
    auth = request.headers.get('Authorization', '')
    if not auth:
        return None
    parts = auth.split(' ', 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != 'bearer':
        return None
    return token.strip() or None

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_bearer_token()
        uid = _verify_token(token) if token else None
        if not uid:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        user = User.query.get(uid)
        if not user:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        request.current_user = user  # type: ignore[attr-defined]
        return fn(*args, **kwargs)
    return wrapper

# ==================== 异常输出（打印 Traceback）====================

def _error_response(e: Exception, status_code: int = 500):
    """
    统一错误返回：
    - 总是在后端终端打印完整 traceback（便于定位 index out of range 等问题）
    - debug 模式下可选择把 traceback 放到返回体里（默认开启）
    """
    tb = traceback.format_exc()
    try:
        app.logger.exception("Unhandled exception: %s", e)
    except Exception:
        pass
    print(tb, file=sys.stderr)
    payload = {'success': False, 'error': str(e)}
    if app.debug:
        payload['traceback'] = tb
    return jsonify(payload), status_code

# ==================== 鉴权接口 ====================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password') or ''
    display_name = (payload.get('display_name') or '').strip() or None
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'username/password required'}), 400
    if len(username) < 3:
        return jsonify({'success': False, 'error': 'username too short'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'password too short'}), 400
    
    existing = User.query.filter_by(username=username).first()
    if existing:
        return jsonify({'success': False, 'error': 'username already exists'}), 409
    
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        display_name=display_name,
    )
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)
    
    token = _make_token(user.id)
    return jsonify({'success': True, 'token': token, 'user': user.to_dict()})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password') or ''
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'username/password required'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'success': False, 'error': 'invalid credentials'}), 401
    
    token = _make_token(user.id)
    return jsonify({'success': True, 'token': token, 'user': user.to_dict()})


@app.route('/api/auth/me', methods=['GET'])
@auth_required
def auth_me():
    user = request.current_user  # type: ignore[attr-defined]
    return jsonify({'success': True, 'user': user.to_dict()})

# ==================== 数据结构定义 ====================

@dataclass
class DwellPhase:
    """单个留置阶段配置"""
    duration: float
    glucose_conc: float
    fill_volume: float
    phase_name: str = ""

@dataclass
class DialysisRegimen:
    """完整透析方案"""
    name: str
    phases: List[Dict]
    
    def get_total_time(self) -> float:
        """计算总时间"""
        return sum(phase['duration'] for phase in self.phases)


# ==================== 工具函数 ====================

def normalize_phase_schema(phase: Dict[str, Any], idx: int, default_start_min: float) -> Dict[str, Any]:
    """统一阶段字段格式，兼容旧字段"""
    phase_data = copy.deepcopy(phase or {})
    
    dwell_min = (
        phase_data.pop('dwell_min', None)
        or phase_data.pop('dwell_minutes', None)
        or phase_data.pop('duration_minutes', None)
    )
    if dwell_min is None:
        duration_hours = phase_data.get('duration_hours')
        if duration_hours is not None:
            dwell_min = float(duration_hours) * 60
        else:
            duration = phase_data.get('duration')
            if duration is not None:
                dwell_min = float(duration) * 60
            else:
                dwell_min = 360.0
    dwell_min = max(float(dwell_min), 1.0)
    
    fill_volume_l = (
        phase_data.get('fill_volume_l')
        or phase_data.get('fill_volume')
        or (phase_data.get('fill_volume_ml', 0) / 1000.0)
    )
    if not fill_volume_l:
        fill_volume_l = 2.0
    fill_volume_l = max(float(fill_volume_l), 0.1)
    
    solution_config = copy.deepcopy(phase_data.get('solution') or {})
    glucose_pct = solution_config.get('glucose_pct', phase_data.get('glucose_conc', 1.5))
    solution_config['glucose_pct'] = float(glucose_pct)
    solution_config.setdefault('amino_acids_pct', phase_data.get('amino_acids_pct', 0.0))
    solution_config.setdefault('icodextrin_pct', phase_data.get('icodextrin_pct', 0.0))
    solution_config.setdefault('buffers', phase_data.get('buffers', {'lactate': 35}))
    solution_config.setdefault('components', phase_data.get('components', {}))
    
    start_min = phase_data.get('start_min', default_start_min)
    end_min = phase_data.get('end_min', start_min + dwell_min)
    
    return {
        'phase_id': phase_data.get('phase_id') or phase_data.get('id') or f'p_{idx}',
        'phase_name': phase_data.get('phase_name', f'阶段{idx + 1}'),
        'sequence_index': idx,
        'dwell_min': dwell_min,
        'duration': dwell_min / 60.0,
        'fill_volume': fill_volume_l,
        'glucose_conc': solution_config['glucose_pct'],
        'solution': solution_config,
        'start_min': start_min,
        'end_min': end_min,
        'tidal_ratio': phase_data.get('tidal_ratio', solution_config.get('tidal_ratio', 1.0)),
        'flags': phase_data.get('flags', {}),
    }


def normalize_regimen_phases(phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量规范化阶段列表"""
    normalized: List[Dict[str, Any]] = []
    current_start = 0.0
    for idx, phase in enumerate(phases or []):
        normalized_phase = normalize_phase_schema(phase, idx, current_start)
        normalized.append(normalized_phase)
        current_start = normalized_phase['end_min']
    return normalized


def normalize_regimen_payload(regimen: Dict[str, Any]) -> Dict[str, Any]:
    """确保方案整体符合统一格式"""
    payload = copy.deepcopy(regimen or {})
    payload['schema_version'] = payload.get('schema_version', 2)
    payload['phases'] = normalize_regimen_phases(payload.get('phases', []))
    return payload


def serialize_regimen_model(regimen: RegimenTemplate) -> Dict[str, Any]:
    """模型转 dict 并规范化阶段"""
    payload = regimen.to_dict()
    payload['phases'] = normalize_regimen_phases(payload.get('phases', []))
    return payload


def log_regimen_action(regimen_id: int, action: str, operator: Optional[str] = None, payload: Optional[Dict[str, Any]] = None):
    """写入方案操作日志"""
    audit = RegimenAuditLog(
        regimen_id=regimen_id,
        action=action,
        operator=operator or 'system',
        payload=payload or {}
    )
    db.session.add(audit)


TRANSPORT_TYPE_MAPPING = {
    'high': TransportType.FAST,
    'high_average': TransportType.AVERAGE,
    'low_average': TransportType.AVERAGE,
    'low': TransportType.SLOW,
}


def resolve_transport_type(patient: Dict[str, Any]) -> TransportType:
    """根据患者资料推断腹膜转运类型"""
    transport_key = (patient or {}).get('peritoneal_transport', '').lower()
    return TRANSPORT_TYPE_MAPPING.get(transport_key, TransportType.AVERAGE)


def extract_plasma_values(biomarkers: Dict[str, Any]) -> Dict[str, float]:
    """提取优化需要的血浆值"""
    defaults = {
        'urea': 20.0,
        'creatinine': 0.884,
        'glucose': 5.5,
        'sodium': 140.0,
        'beta2m': 0.003,
        'albumin': 40.0,
    }
    biomarkers = biomarkers or {}
    raw_creatinine = biomarkers.get('creatinine')
    if raw_creatinine is None:
        creatinine_value = defaults['creatinine']
    elif raw_creatinine > 20:
        creatinine_value = raw_creatinine / 1000
    else:
        creatinine_value = raw_creatinine
    
    mapping = {
        'urea': biomarkers.get('bun', defaults['urea']),
        'creatinine': creatinine_value,
        'glucose': biomarkers.get('glucose', defaults['glucose']),
        'sodium': biomarkers.get('sodium', defaults['sodium']),
        'beta2m': biomarkers.get('beta2_microglobulin', defaults['beta2m']),
        'albumin': biomarkers.get('albumin', defaults['albumin']),
    }
    return mapping


def find_phase_by_minute(phases: List[Dict[str, Any]], minute: float) -> Optional[Dict[str, Any]]:
    """根据时间(分钟)查找对应阶段"""
    for phase in phases:
        if phase['start_min'] <= minute < phase['end_min']:
            return phase
    if phases and minute >= phases[-1]['end_min']:
        return phases[-1]
    return None


def calculate_next_version(parent_id: int) -> int:
    """计算同一方案族的下一个版本号"""
    if not parent_id:
        return 1
    candidates = RegimenTemplate.query.filter(
        or_(RegimenTemplate.parent_id == parent_id, RegimenTemplate.id == parent_id)
    ).all()
    if not candidates:
        return 1
    return max((c.version or 1) for c in candidates) + 1

# ==================== 预设方案库 ====================

PRESET_REGIMENS = {
    "standard": {
        "name": "标准CAPD方案",
        "phases": [
            {"duration": 6, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "早晨"},
            {"duration": 6, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "中午"},
            {"duration": 6, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "晚间"},
            {"duration": 6, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "夜间"}
        ]
    },
    "bimodal": {
        "name": "双峰方案",
        "phases": [
            {"duration": 2, "glucose_conc": 4.25, "fill_volume": 2.0, "phase_name": "高浓度短时1"},
            {"duration": 6, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "低浓度长时1"},
            {"duration": 2, "glucose_conc": 4.25, "fill_volume": 2.0, "phase_name": "高浓度短时2"},
            {"duration": 6, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "低浓度长时2"},
            {"duration": 8, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "夜间"}
        ]
    },
    "tidal": {
        "name": "潮汐方案",
        "phases": [
            {"duration": 1, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "潮汐1"},
            {"duration": 1, "glucose_conc": 1.5, "fill_volume": 1.0, "phase_name": "潮汐2"},
            {"duration": 1, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "潮汐3"},
            {"duration": 1, "glucose_conc": 1.5, "fill_volume": 1.0, "phase_name": "潮汐4"},
            {"duration": 1, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "潮汐5"},
            {"duration": 1, "glucose_conc": 1.5, "fill_volume": 1.0, "phase_name": "潮汐6"}
        ]
    },
    "apd": {
        "name": "APD夜间方案",
        "phases": [
            {"duration": 2, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "循环1"},
            {"duration": 2, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "循环2"},
            {"duration": 2, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "循环3"},
            {"duration": 2, "glucose_conc": 2.5, "fill_volume": 2.0, "phase_name": "循环4"},
            {"duration": 14, "glucose_conc": 1.5, "fill_volume": 2.0, "phase_name": "日间留腹"}
        ]
    }
}

# ==================== 三孔模型模拟引擎 ====================

class ThreePoreSimulator:
    """基于三孔模型的透析模拟器"""
    
    def __init__(self):
        self.SMALL_PORE_AREA = 0.85
        self.LARGE_PORE_AREA = 0.05
        self.ULTRA_SMALL_PORE_AREA = 0.10
    
    def _safe_get(self, data: Optional[Dict], key: str, default: Any) -> Any:
        """✅ 安全获取字典值，处理 None 情况"""
        if data is None:
            return default
        return data.get(key, default)
    
    def simulate_phase(self, phase: Dict[str, Any], patient: Optional[Dict[str, Any]], 
                       biomarkers: Optional[Dict[str, Any]], current_time: float) -> Dict:
        """模拟单个透析阶段"""
        
        # ✅ 使用安全获取方法
        weight = self._safe_get(patient, 'weight', 65)
        V_dist = weight * 0.6
        age = self._safe_get(patient, 'age', 45)
        
        # 透析参数 - 使用安全获取
        dwell_time = self._safe_get(phase, 'duration', self._safe_get(phase, 'dwell_min', 360) / 60)
        solution_profile = phase.get('solution') or {}
        glucose_conc = solution_profile.get('glucose_pct', self._safe_get(phase, 'glucose_conc', 1.5))
        fill_volume = self._safe_get(phase, 'fill_volume', 2.0)
        
        # 生化指标 - 使用安全获取
        creatinine_plasma = self._safe_get(biomarkers, 'creatinine', 884)
        bun_plasma = self._safe_get(biomarkers, 'bun', 25.3)
        potassium_plasma = self._safe_get(biomarkers, 'potassium', 4.8)
        
        # ✅ 防止 dwell_time 为 0 或负数
        if dwell_time <= 0:
            dwell_time = 6
        
        # 时间步长（分钟）
        time_steps = np.linspace(0, dwell_time * 60, max(int(dwell_time * 60 / 5) + 1, 2))
        
        # 初始化结果数组
        results = {
            'time': [],
            'volume': [],
            'urea_clearance': [],
            'creatinine_clearance': [],
            'glucose_absorption': [],
            'uf_volume': [],
            'potassium_clearance': [],
            'protein_loss': []
        }
        
        # 计算患者转运特性系数
        # 基于患者年龄和体重的综合系数（0.8-1.2范围）
        patient_factor = 0.8 + (age / 100) * 0.2 + (weight / 100) * 0.2
        
        # 基于肌酐水平调整清除率（肌酐越高，清除率可能越低）
        creatinine_factor = max(0.7, min(1.3, 1.0 - (creatinine_plasma - 884) / 8840))
        
        # 基于葡萄糖浓度的超滤系数调整
        glucose_factor = 1.0 + (glucose_conc - 1.5) * 0.1
        
        # 综合患者因素
        clearance_factor = patient_factor * creatinine_factor
        uf_factor = patient_factor * glucose_factor
        
        # 模拟每个时间点
        for t in time_steps:
            osmotic_pressure = glucose_conc * 5.5
            uf_rate = osmotic_pressure * 0.015 * np.exp(-0.01 * t) * uf_factor
            
            small_solute_clearance = 8.5 * (1 - np.exp(-0.008 * t)) * clearance_factor
            mid_solute_clearance = 3.2 * (1 - np.exp(-0.005 * t)) * clearance_factor
            large_solute_loss = 0.05 * (1 - np.exp(-0.003 * t)) * patient_factor
            glucose_abs_rate = glucose_conc * 0.08 * np.exp(-0.012 * t) * patient_factor
            
            results['time'].append(float(current_time + t))  # ✅ 确保是 float
            results['volume'].append(float(fill_volume * 1000 + uf_rate * t))
            results['urea_clearance'].append(float(small_solute_clearance))
            results['creatinine_clearance'].append(float(small_solute_clearance * 0.9))
            results['glucose_absorption'].append(float(glucose_abs_rate))
            results['uf_volume'].append(float(uf_rate))
            results['potassium_clearance'].append(float(small_solute_clearance * 0.85))
            results['protein_loss'].append(float(large_solute_loss))
        
        # 计算阶段总结 - 使用 numpy 但转换为 Python 原生类型
        total_uf = float(np.trapz(results['uf_volume'], results['time']))
        total_glucose_absorbed = float(np.trapz(results['glucose_absorption'], results['time']))
        avg_clearance = float(np.mean(results['urea_clearance']))
        
        # ✅ 防止除零错误
        if V_dist > 0:
            ktv_contribution = float((avg_clearance * dwell_time * 60) / (V_dist * 1000))
        else:
            ktv_contribution = 0.0
        
        return {
            'time_series': results,
            'summary': {
                'total_uf': total_uf,
                'total_glucose_absorbed': total_glucose_absorbed,
                'avg_clearance': avg_clearance,
                'ktv_contribution': ktv_contribution,
                'phase_duration': float(dwell_time)
            }
        }
    
    def simulate_full_regimen(self, regimen: Optional[Dict], patient: Optional[Dict], 
                              biomarkers: Optional[Dict]) -> Dict:
        """模拟完整透析方案"""
        
        # ✅ 防御性编程：处理 None 输入
        if regimen is None:
            regimen = PRESET_REGIMENS['standard']
        
        if patient is None:
            patient = {'weight': 65, 'age': 45, 'gender': 'male'}
        
        if biomarkers is None:
            biomarkers = {
                'creatinine': 884,
                'bun': 25.3,
                'potassium': 4.8,
                'sodium': 138
            }
        
        all_results = {
            'time': [],
            'volume': [],
            'urea_clearance': [],
            'creatinine_clearance': [],
            'glucose_absorption': [],
            'uf_volume': [],
            'potassium_clearance': [],
            'protein_loss': [],
            'phase_markers': []
        }
        
        total_ktv = 0.0
        total_uf = 0.0
        total_glucose = 0.0
        current_time = 0.0
        
        normalized_regimen = normalize_regimen_payload(regimen)
        phases = normalized_regimen.get('phases')
        
        # ✅ 确保 phases 不为空
        if not phases or len(phases) == 0:
            phases = normalize_regimen_phases(PRESET_REGIMENS['standard']['phases'])
        
        for idx, phase in enumerate(phases):
            phase_result = self.simulate_phase(phase, patient, biomarkers, current_time)
            
            for key in all_results.keys():
                if key != 'phase_markers' and key in phase_result['time_series']:
                    all_results[key].extend(phase_result['time_series'][key])
            
            phase_duration = self._safe_get(phase, 'duration', 6)
            phase_start = phase.get('start_min', current_time)
            phase_end = phase.get('end_min', phase_start + phase_duration * 60)
            
            all_results['phase_markers'].append({
                'phase_index': idx,
                'phase_name': self._safe_get(phase, 'phase_name', f'阶段{idx+1}'),
                'start_time': float(phase_start),
                'end_time': float(phase_end),
                'glucose_conc': float(self._safe_get(phase, 'glucose_conc', 1.5)),
                'solution': phase.get('solution', {}),
                'tidal_ratio': phase.get('tidal_ratio', 1.0)
            })
            
            total_ktv += phase_result['summary']['ktv_contribution']
            total_uf += phase_result['summary']['total_uf']
            total_glucose += phase_result['summary']['total_glucose_absorbed']
            current_time = phase_end
        
        # ✅ 生化指标预测 - 使用安全获取
        weight = self._safe_get(patient, 'weight', 65)
        creatinine = self._safe_get(biomarkers, 'creatinine', 884)
        bun = self._safe_get(biomarkers, 'bun', 25.3)
        potassium = self._safe_get(biomarkers, 'potassium', 4.8)
        
        creatinine_reduction = min(creatinine * 0.3, 400)
        bun_reduction = min(bun * 0.35, 10)
        potassium_reduction = max(potassium - 4.0, 0) * 0.5
        
        return {
            'time_series': all_results,
            'summary': {
                'total_ktv': round(float(total_ktv), 2),
                'total_uf': round(float(total_uf), 1),
                'total_glucose_absorbed': round(float(total_glucose), 1),
                'total_duration': round(float(current_time), 1),
                'predicted_creatinine': round(float(creatinine - creatinine_reduction), 0),
                'predicted_bun': round(float(bun - bun_reduction), 1),
                'predicted_potassium': round(float(potassium - potassium_reduction), 1),
                'adequacy_status': 'adequate' if total_ktv >= 1.7 else 'inadequate',
                'recommendations': self._generate_recommendations(total_ktv, total_uf, total_glucose)
            }
        }
    
    def _generate_recommendations(self, ktv: float, uf: float, glucose: float) -> List[str]:
        """生成临床建议"""
        recommendations = []
        
        if ktv >= 1.7:
            recommendations.append("✓ Kt/V达标，透析充分性良好")
        else:
            recommendations.append("✗ Kt/V不达标，建议增加透析次数或延长留腹时间")
        
        if uf < 500:
            recommendations.append("⚠ 超滤量偏低，注意液体平衡")
        elif uf > 2000:
            recommendations.append("⚠ 超滤量偏高，注意血容量状态")
        else:
            recommendations.append("✓ 超滤量适中")
        
        if glucose > 100:
            recommendations.append("⚠ 葡萄糖吸收较多，注意血糖控制")
        
        return recommendations

# ==================== 初始化模拟器 ====================

simulator = ThreePoreSimulator()

# ==================== 患者管理 API ====================

@app.route('/api/patients', methods=['GET'])
def get_patients():
    """获取所有患者列表"""
    try:
        patients = Patient.query.all()
        return jsonify({
            'success': True,
            'patients': [p.to_dict() for p in patients]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patients/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    """获取单个患者信息"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        return jsonify({
            'success': True,
            'patient': patient.to_dict()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 404

@app.route('/api/patients', methods=['POST'])
def create_patient():
    """创建新患者"""
    try:
        data = request.json or {}  # ✅ 防止 None
        
        patient = Patient(
            name=data.get('name', '未命名患者'),
            gender=data.get('gender', 'male'),
            age=data.get('age', 45),
            weight=data.get('weight', 65),
            height=data.get('height', 170),
            bsa=data.get('bsa', 1.75),
            dialysis_vintage=data.get('dialysis_vintage', 12),
            primary_disease=data.get('primary_disease', 'chronic_glomerulonephritis'),
            residual_kidney_function=data.get('residual_kidney_function', 'minimal'),
            peritoneal_transport=data.get('peritoneal_transport', 'high_average'),
            urine_volume=data.get('urine_volume', 500),
            blood_pressure_systolic=data.get('blood_pressure_systolic', 140),
            blood_pressure_diastolic=data.get('blood_pressure_diastolic', 90),
            creatinine=data.get('biomarkers', {}).get('creatinine', 884),
            bun=data.get('biomarkers', {}).get('bun', 25.3),
            uric_acid=data.get('biomarkers', {}).get('uric_acid', 450),
            beta2_microglobulin=data.get('biomarkers', {}).get('beta2_microglobulin', 25),
            potassium=data.get('biomarkers', {}).get('potassium', 4.8),
            sodium=data.get('biomarkers', {}).get('sodium', 138),
            chloride=data.get('biomarkers', {}).get('chloride', 102),
            calcium=data.get('biomarkers', {}).get('calcium', 2.25),
            phosphorus=data.get('biomarkers', {}).get('phosphorus', 1.8),
            magnesium=data.get('biomarkers', {}).get('magnesium', 1.0),
            hemoglobin=data.get('biomarkers', {}).get('hemoglobin', 95),
            albumin=data.get('biomarkers', {}).get('albumin', 35),
            total_protein=data.get('biomarkers', {}).get('total_protein', 65),
            hematocrit=data.get('biomarkers', {}).get('hematocrit', 30),
            glucose=data.get('biomarkers', {}).get('glucose', 5.5),
            hba1c=data.get('biomarkers', {}).get('hba1c', 6.5),
            cholesterol=data.get('biomarkers', {}).get('cholesterol', 5.2),
            triglycerides=data.get('biomarkers', {}).get('triglycerides', 1.7),
            ph=data.get('biomarkers', {}).get('ph', 7.35),
            bicarbonate=data.get('biomarkers', {}).get('bicarbonate', 22),
            pco2=data.get('biomarkers', {}).get('pco2', 40),
            anion_gap=data.get('biomarkers', {}).get('anion_gap', 12)
        )
        
        db.session.add(patient)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'patient': patient.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """更新患者信息"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json or {}  # ✅ 防止 None
        
        for field in ['name', 'gender', 'age', 'weight', 'height', 'bsa',
                      'dialysis_vintage', 'primary_disease', 'residual_kidney_function',
                      'peritoneal_transport', 'urine_volume', 
                      'blood_pressure_systolic', 'blood_pressure_diastolic']:
            if field in data:
                setattr(patient, field, data[field])
        
        if 'biomarkers' in data:
            for field in ['creatinine', 'bun', 'uric_acid', 'beta2_microglobulin',
                          'potassium', 'sodium', 'chloride', 'calcium', 'phosphorus', 
                          'magnesium', 'hemoglobin', 'albumin', 'total_protein', 
                          'hematocrit', 'glucose', 'hba1c', 'cholesterol', 
                          'triglycerides', 'ph', 'bicarbonate', 'pco2', 'anion_gap']:
                if field in data['biomarkers']:
                    setattr(patient, field, data['biomarkers'][field])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'patient': patient.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """删除患者"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        db.session.delete(patient)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '患者已删除'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/patients/<int:patient_id>/biochemistry', methods=['GET'])
def get_patient_biochemistry(patient_id: int):
    """获取患者历史生化指标"""
    patient = Patient.query.get_or_404(patient_id)
    snapshots = (PatientBiochemistrySnapshot
                 .query
                 .filter_by(patient_id=patient.id)
                 .order_by(PatientBiochemistrySnapshot.recorded_at.desc())
                 .all())
    return jsonify({
        'success': True,
        'patient_id': patient.id,
        'snapshots': [s.to_dict() for s in snapshots]
    })


@app.route('/api/patients/<int:patient_id>/biochemistry', methods=['POST'])
def create_patient_biochemistry(patient_id: int):
    """新增一条生化指标记录"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.json or {}
        snapshot = PatientBiochemistrySnapshot(
            patient_id=patient.id,
            biomarkers=data.get('biomarkers', {}),
            note=data.get('note')
        )
        db.session.add(snapshot)
        db.session.commit()
        return jsonify({'success': True, 'snapshot': snapshot.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== 方案管理 API ====================

@app.route('/api/regimens', methods=['GET'])
def get_regimens():
    """获取所有方案"""
    try:
        category = request.args.get('category')
        
        query = RegimenTemplate.query
        if category:
            query = query.filter_by(category=category)
        
        regimens = query.all()
        
        return jsonify({
            'success': True,
            'regimens': [serialize_regimen_model(r) for r in regimens]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/regimens/<int:regimen_id>', methods=['GET'])
def get_regimen(regimen_id):
    """获取单个方案详情"""
    try:
        regimen = RegimenTemplate.query.get_or_404(regimen_id)
        return jsonify({
            'success': True,
            'regimen': serialize_regimen_model(regimen)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 404

@app.route('/api/regimens', methods=['POST'])
def create_regimen():
    """创建新方案"""
    try:
        data = request.json or {}  # ✅ 防止 None
        
        if not data.get('name'):
            return jsonify({'success': False, 'error': '方案名称不能为空'}), 400
        
        existing = RegimenTemplate.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'success': False, 'error': '方案名称已存在'}), 400
        
        normalized_phases = normalize_regimen_phases(data.get('phases', []))
        
        regimen = RegimenTemplate(
            name=data['name'],
            description=data.get('description', ''),
            category=data.get('category', 'custom'),
            phases=normalized_phases,
            created_by=data.get('created_by', 'user'),
            metadata_json=data.get('metadata', {}),
            version=data.get('version', 1),
            parent_id=data.get('parent_id'),
            schema_version=2,
            is_preset=data.get('is_preset', False)
        )
        
        db.session.add(regimen)
        db.session.flush()
        log_regimen_action(regimen.id, 'create', operator=regimen.created_by, payload={'name': regimen.name})
        db.session.commit()
        
        return jsonify({
            'success': True,
            'regimen': serialize_regimen_model(regimen)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/regimens/<int:regimen_id>', methods=['PUT'])
def update_regimen(regimen_id):
    """更新方案"""
    try:
        regimen = RegimenTemplate.query.get_or_404(regimen_id)
        data = request.json or {}  # ✅ 防止 None
        
        if 'name' in data and data['name'] != regimen.name:
            existing = RegimenTemplate.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'success': False, 'error': '方案名称已存在'}), 400
        
        if 'phases' in data:
            regimen.phases = normalize_regimen_phases(data['phases'])
        
        for field in ['name', 'description', 'category', 'version', 'parent_id', 'is_preset']:
            if field in data:
                setattr(regimen, field, data[field])
        if 'metadata' in data:
            regimen.metadata_json = data['metadata']
        
        log_regimen_action(regimen.id, 'update', operator=data.get('updated_by'), payload={'fields': list(data.keys())})
        db.session.commit()
        
        return jsonify({
            'success': True,
            'regimen': serialize_regimen_model(regimen)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/regimens/<int:regimen_id>', methods=['DELETE'])
def delete_regimen(regimen_id):
    """删除方案"""
    try:
        regimen = RegimenTemplate.query.get_or_404(regimen_id)
        
        if regimen.category == 'preset':
            return jsonify({'success': False, 'error': '预设方案不能删除'}), 400
        
        log_regimen_action(regimen.id, 'delete', operator=request.args.get('operator'))
        db.session.delete(regimen)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '方案已删除'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/regimens/<int:regimen_id>/duplicate', methods=['POST'])
def duplicate_regimen(regimen_id):
    """复制方案"""
    try:
        original = RegimenTemplate.query.get_or_404(regimen_id)
        data = request.json or {}  # ✅ 防止 None
        
        new_name = data.get('name', f"{original.name} - 副本")
        
        counter = 1
        while RegimenTemplate.query.filter_by(name=new_name).first():
            new_name = f"{original.name} - 副本 {counter}"
            counter += 1
        
        base_id = original.parent_id or original.id
        duplicate = RegimenTemplate(
            name=new_name,
            description=original.description,
            category='custom',
            phases=normalize_regimen_phases(original.phases),
            created_by=data.get('created_by', 'user'),
            parent_id=base_id,
            version=calculate_next_version(base_id),
            metadata_json=original.metadata_json,
            schema_version=original.schema_version or 2
        )
        
        db.session.add(duplicate)
        db.session.flush()
        log_regimen_action(duplicate.id, 'duplicate', operator=duplicate.created_by, payload={'source_id': regimen_id})
        db.session.commit()
        
        return jsonify({
            'success': True,
            'regimen': serialize_regimen_model(duplicate)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/regimens/<int:regimen_id>/versions', methods=['GET'])
def list_regimen_versions(regimen_id: int):
    """查询同一方案族的所有版本"""
    regimen = RegimenTemplate.query.get_or_404(regimen_id)
    base_id = regimen.parent_id or regimen.id
    versions = (RegimenTemplate.query
                .filter(or_(RegimenTemplate.parent_id == base_id, RegimenTemplate.id == base_id))
                .order_by(RegimenTemplate.version.asc(), RegimenTemplate.created_at.asc())
                .all())
    return jsonify({
        'success': True,
        'family_root': base_id,
        'versions': [serialize_regimen_model(r) for r in versions]
    })


@app.route('/api/regimens/<int:regimen_id>/save-as', methods=['POST'])
def save_regimen_as(regimen_id: int):
    """将当前方案另存为新版本"""
    try:
        regimen = RegimenTemplate.query.get_or_404(regimen_id)
        data = request.json or {}
        new_name = data.get('name')
        if not new_name:
            return jsonify({'success': False, 'error': '新方案名称不能为空'}), 400
        if RegimenTemplate.query.filter_by(name=new_name).first():
            return jsonify({'success': False, 'error': '方案名称已存在'}), 400
        
        base_id = regimen.parent_id or regimen.id
        new_version = calculate_next_version(base_id)
        duplicate = RegimenTemplate(
            name=new_name,
            description=data.get('description', regimen.description),
            category=data.get('category', regimen.category),
            phases=normalize_regimen_phases(data.get('phases', regimen.phases)),
            created_by=data.get('created_by', 'user'),
            parent_id=base_id,
            version=new_version,
            metadata_json=data.get('metadata', regimen.metadata_json),
            schema_version=regimen.schema_version or 2,
            is_preset=False
        )
        db.session.add(duplicate)
        db.session.flush()
        log_regimen_action(duplicate.id, 'save_as', operator=duplicate.created_by, payload={'source_id': regimen_id})
        db.session.commit()
        return jsonify({'success': True, 'regimen': serialize_regimen_model(duplicate)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/regimens/<int:regimen_id>/rename', methods=['PUT'])
def rename_regimen(regimen_id: int):
    """重命名方案"""
    try:
        regimen = RegimenTemplate.query.get_or_404(regimen_id)
        data = request.json or {}
        new_name = data.get('name')
        if not new_name:
            return jsonify({'success': False, 'error': '新名称不能为空'}), 400
        existing = RegimenTemplate.query.filter_by(name=new_name).first()
        if existing and existing.id != regimen_id:
            return jsonify({'success': False, 'error': '方案名称已存在'}), 400
        old_name = regimen.name
        regimen.name = new_name
        log_regimen_action(regimen.id, 'rename', operator=data.get('operator'), payload={'old_name': old_name, 'new_name': new_name})
        db.session.commit()
        return jsonify({'success': True, 'regimen': serialize_regimen_model(regimen)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/regimens/<int:regimen_id>/phase-at', methods=['GET'])
def get_regimen_phase_at(regimen_id: int):
    """根据时间查询方案阶段"""
    regimen = RegimenTemplate.query.get_or_404(regimen_id)
    minute = request.args.get('minute', type=float, default=0.0)
    serialized = serialize_regimen_model(regimen)
    phase = find_phase_by_minute(serialized['phases'], minute)
    if not phase:
        return jsonify({'success': False, 'error': '未找到对应的阶段'}), 404
    return jsonify({
        'success': True,
        'phase': phase,
        'regimen': {'id': regimen.id, 'name': regimen.name},
        'query_minute': minute
    })


@app.route('/api/preset/<preset_id>/phase-at', methods=['GET'])
def get_preset_phase_at(preset_id: str):
    """预设方案时间查询"""
    preset = PRESET_REGIMENS.get(preset_id)
    if not preset:
        return jsonify({'success': False, 'error': '预设方案不存在'}), 404
    minute = request.args.get('minute', type=float, default=0.0)
    normalized = normalize_regimen_phases(preset.get('phases', []))
    phase = find_phase_by_minute(normalized, minute)
    if not phase:
        return jsonify({'success': False, 'error': '未找到对应的阶段'}), 404
    return jsonify({'success': True, 'phase': phase, 'preset_id': preset_id, 'query_minute': minute})


@app.route('/api/regimens/generate', methods=['POST'])
def generate_regimen():
    """根据段定义快速生成统一格式方案"""
    try:
        data = request.get_json(silent=True) or {}
        segments = data.get('segments', [])
        if not segments:
            return jsonify({'success': False, 'error': 'segments 不能为空'}), 400
        
        default_fill_volume = data.get('default_fill_volume_l', 2.0)
        default_glucose = data.get('default_glucose_pct', 1.5)
        current_start = data.get('start_min', 0.0)
        raw_phases: List[Dict[str, Any]] = []
        
        for idx, segment in enumerate(segments):
            dwell_min = segment.get('dwell_min') or segment.get('duration_minutes') or data.get('default_dwell_min', 360)
            dwell_min = max(float(dwell_min), 1.0)
            fill_volume = segment.get('fill_volume_l', default_fill_volume)
            solution = {
                'glucose_pct': segment.get('glucose_pct', default_glucose),
                'amino_acids_pct': segment.get('amino_acids_pct', 0.0),
                'icodextrin_pct': segment.get('icodextrin_pct', 0.0),
                'buffers': segment.get('buffers', data.get('default_buffers', {'lactate': 35})),
                'components': segment.get('components', {})
            }
            raw_phases.append({
                'phase_name': segment.get('phase_name', f'阶段{idx+1}'),
                'dwell_min': dwell_min,
                'fill_volume': fill_volume,
                'solution': solution,
                'start_min': current_start,
                'end_min': current_start + dwell_min,
                'tidal_ratio': segment.get('tidal_ratio', 1.0)
            })
            current_start += dwell_min
        
        normalized_phases = normalize_regimen_phases(raw_phases)
        regimen_payload = {
            'name': data.get('name', '生成方案'),
            'description': data.get('description', ''),
            'category': data.get('category', 'generated'),
            'schema_version': 2,
            'phases': normalized_phases
        }
        
        if data.get('persist'):
            regimen = RegimenTemplate(
                name=regimen_payload['name'],
                description=regimen_payload['description'],
                category=regimen_payload['category'],
                phases=normalized_phases,
                created_by=data.get('created_by', 'user'),
                metadata_json=data.get('metadata', {}),
                schema_version=2,
                version=data.get('version', 1)
            )
            db.session.add(regimen)
            db.session.flush()
            log_regimen_action(regimen.id, 'generate', operator=regimen.created_by, payload={'segments': len(segments)})
            db.session.commit()
            regimen_payload.update({'id': regimen.id})
        
        return jsonify({'success': True, 'regimen': regimen_payload})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== 模拟历史 API ====================

@app.route('/api/simulations', methods=['GET'])
def get_simulations():
    """获取模拟历史"""
    try:
        patient_id = request.args.get('patient_id', type=int)
        
        query = SimulationHistory.query
        if patient_id:
            query = query.filter_by(patient_id=patient_id)
        
        simulations = query.order_by(SimulationHistory.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'simulations': [s.to_dict() for s in simulations]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/simulations', methods=['POST'])
def save_simulation():
    """保存模拟结果"""
    try:
        data = request.json or {}  # ✅ 防止 None
        
        simulation = SimulationHistory(
            patient_id=data.get('patient_id'),
            regimen_id=data.get('regimen_id'),
            results=data.get('results', {}),
            time_series=data.get('time_series', {})
        )
        
        db.session.add(simulation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'simulation': simulation.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== 原有 API 路由 ====================

@app.route('/api/presets', methods=['GET'])
def get_presets():
    """获取预设方案列表"""
    return jsonify({
        'success': True,
        'presets': [
            {'id': key, 'name': value['name'], 'phases': len(value['phases'])}
            for key, value in PRESET_REGIMENS.items()
        ]
    })

@app.route('/api/preset/<preset_id>', methods=['GET'])
def get_preset_detail(preset_id):
    """获取预设方案详情"""
    if preset_id in PRESET_REGIMENS:
        return jsonify({
            'success': True,
            'regimen': PRESET_REGIMENS[preset_id]
        })
    else:
        return jsonify({'success': False, 'error': '方案不存在'}), 404

@app.route('/api/simulate-regimen', methods=['POST'])
def simulate_regimen():
    """模拟透析方案"""
    try:
        data = request.get_json(silent=True) or {}  # ✅ 防止 None
        
        patient = data.get('patient', {})
        biomarkers = data.get('biomarkers', {})
        regimen = data.get('regimen', {})
        
        results = simulator.simulate_full_regimen(regimen, patient, biomarkers)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/compare-regimens', methods=['POST'])
def compare_regimens():
    """比较多个方案"""
    try:
        data = request.get_json(silent=True) or {}  # ✅ 防止 None
        
        patient = data.get('patient', {})
        biomarkers = data.get('biomarkers', {})
        regimen_ids = data.get('regimen_ids', [])
        
        comparison_results = []
        
        for regimen_id in regimen_ids:
            if regimen_id in PRESET_REGIMENS:
                regimen = normalize_regimen_payload(PRESET_REGIMENS[regimen_id])
                results = simulator.simulate_full_regimen(regimen, patient, biomarkers)
                
                comparison_results.append({
                    'regimen_id': regimen_id,
                    'regimen_name': regimen['name'],
                    'summary': results['summary']
                })
        
        return jsonify({
            'success': True,
            'comparisons': comparison_results
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/optimize', methods=['POST'])
def optimize_regimen():
    """优化透析方案"""
    try:
        data = request.get_json(silent=True) or {}  # ✅ 防止 None
        patient = data.get('patient', {})
        biomarkers = data.get('biomarkers', {})
        target_ktv = data.get('target_ktv', 1.7)
        
        # 解析患者信息和生物标志物以获取传输类型和血浆值
        transport_type = resolve_transport_type(patient)
        plasma_values = extract_plasma_values(biomarkers)
        
        # 初始化优化目标和遗传优化器
        objectives = OptimizationObjectives(
            transport_type=transport_type,
            plasma_values=plasma_values
        )
        
        optimizer = GeneticOptimizer(
            objectives=objectives,
            target_ktv=target_ktv
        )
        
        # 执行遗传算法优化
        best_prescription = optimizer.optimize()
        
        # 模拟最优方案以获取预测的Kt/V值
        best_regimen = {
            'name': '优化方案',
            'phases': best_prescription.phases
        }
        
        results = simulator.simulate_full_regimen(best_regimen, patient, biomarkers)
        predicted_ktv = results['summary']['total_ktv']
        
        # 准备返回结果
        optimal_regimen = {
            'regimen_id': 'optimized',
            'regimen_name': '智能优化方案',
            'predicted_ktv': predicted_ktv,
            'phases': best_prescription.phases
        }
        
        return jsonify({
            'success': True,
            'optimal_regimen': optimal_regimen
        })
    
    except Exception as e:
        return _error_response(e, 500)


def run_genetic_optimization(mode: str):
    """封装新的遗传算法优化入口"""
    try:
        data = request.get_json(silent=True) or {}
        patient = data.get('patient', {})
        biomarkers = data.get('biomarkers', {})
        objectives = OptimizationObjectives(
            transport_type=resolve_transport_type(patient),
            plasma_values=extract_plasma_values(biomarkers),
            simulation_time=data.get('simulation_minutes', 24 * 60)
        )
        optimizer = GeneticOptimizer(
            objectives=objectives,
            population_size=data.get('population_size', 40),
            generations=data.get('generations', 25),
            mutation_rate=data.get('mutation_rate', 0.2),
            crossover_rate=data.get('crossover_rate', 0.8),
            mode=mode,
            phase_template=data.get('phase_template')
        )
        result = optimizer.optimize()

        # 附加“预测指标”：把优化后的处方转为方案，再走一次 simulator 得到可解释的 summary（Kt/V、UF、葡萄糖等）
        try:
            prescription = result.get('prescription') if isinstance(result, dict) else None
            if mode == 'freeform' and prescription and isinstance(prescription, dict):
                phases = prescription.get('phases') or []
                regimen_payload = normalize_regimen_payload({
                    'name': 'GA Optimized',
                    'phases': phases
                })
                sim_results = simulator.simulate_full_regimen(regimen_payload, patient, biomarkers)
                if isinstance(sim_results, dict) and sim_results.get('summary'):
                    result['predicted'] = {
                        'summary': sim_results.get('summary'),
                    }
        except Exception as e:
            # 不让“预测指标计算”影响优化主流程
            app.logger.exception("Failed to compute predicted summary: %s", e)

        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return _error_response(e, 500)


@app.route('/api/optimize/structured', methods=['POST'])
def optimize_regimen_structured():
    """固定格式优化"""
    return run_genetic_optimization('structured')


@app.route('/api/optimize/freeform', methods=['POST'])
def optimize_regimen_freeform():
    """任意阶段优化"""
    return run_genetic_optimization('freeform')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
