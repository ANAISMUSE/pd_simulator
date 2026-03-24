from flask import Flask, request, jsonify, send_file
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
import threading
import time
import csv
import io
from datetime import datetime
from datetime import timedelta
import pandas as pd
from openpyxl import Workbook  # type: ignore

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from database import (
    db,
    User,
    Hospital,
    MedicalGroup,
    Patient,
    RegimenTemplate,
    SimulationHistory,
    PatientBiochemistrySnapshot,
    PatientCheckRecord,
    PatientRegimenUsage,
    StatisticalModelRun,
    DoctorAccessRequest,
    DoctorPatientAccessGrant,
    RegimenAuditLog,
    apply_schema_migrations,
)
from optimizer.genetic import GeneticOptimizer
from optimizer.objectives import OptimizationObjectives
from models.parameters import TransportType
from sqlalchemy import or_, and_  # type: ignore

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


def _patient_visibility_filter(user: User):
    """
    当前医生能看到的患者范围：
    - 自己创建的患者：owner_user_id == user.id
    - 同机构、已标记共享的患者：owner_org == user.org AND is_shared == True
    """
    base = (Patient.owner_user_id == user.id)
    grant_scope = and_(
        DoctorPatientAccessGrant.grantee_doctor_id == user.id,
        DoctorPatientAccessGrant.active.is_(True),
        or_(
            DoctorPatientAccessGrant.expires_at.is_(None),
            DoctorPatientAccessGrant.expires_at > datetime.utcnow(),
        ),
    )
    owner_granted = Patient.owner_user_id.in_(
        db.session.query(DoctorPatientAccessGrant.owner_doctor_id).filter(grant_scope)
    )
    merged_scope = or_(base, owner_granted)
    if user.org:
        # 仅共享标记为 True 的患者对同机构开放；
        # 对于历史数据，owner_org 为空但 is_shared=True 的，也允许同机构医生看到。
        shared_scope = or_(Patient.owner_org == user.org, Patient.owner_org.is_(None))
        return or_(merged_scope, Patient.is_shared.is_(True) & shared_scope)
    return merged_scope

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


@app.route('/api/auth/me/settings', methods=['PUT'])
@auth_required
def update_me_settings():
    """
    更新当前用户的一些设置：
    - org: 所在医院/科室（兼容旧字段）
    - hospital_id / medical_group_id: 新 ER 结构
    - allow_share_patients: 是否允许自己的患者对同机构医生可见
    """
    user: User = request.current_user  # type: ignore[attr-defined]
    payload = request.get_json(silent=True) or {}
    try:
        if 'org' in payload:
            org = (payload.get('org') or '').strip() or None
            user.org = org
        if 'hospital_id' in payload:
            hospital_id = payload.get('hospital_id')
            user.hospital_id = int(hospital_id) if hospital_id else None
        if 'medical_group_id' in payload:
            group_id = payload.get('medical_group_id')
            user.medical_group_id = int(group_id) if group_id else None
        if 'allow_share_patients' in payload:
            user.allow_share_patients = bool(payload.get('allow_share_patients'))
        db.session.commit()
        return jsonify({'success': True, 'user': user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


# ==================== 医院/医疗组/医生访问申请 API ====================

@app.route('/api/hospitals', methods=['GET'])
@auth_required
def get_hospitals():
    hospitals = Hospital.query.order_by(Hospital.name.asc()).all()
    return jsonify({'success': True, 'hospitals': [h.to_dict() for h in hospitals]})


@app.route('/api/hospitals', methods=['POST'])
@auth_required
def create_hospital():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'name required'}), 400
        item = Hospital(name=name, code=(data.get('code') or '').strip() or None)
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'hospital': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/medical-groups', methods=['GET'])
@auth_required
def get_medical_groups():
    hospital_id = request.args.get('hospital_id', type=int)
    q = MedicalGroup.query
    if hospital_id:
        q = q.filter(MedicalGroup.hospital_id == hospital_id)
    rows = q.order_by(MedicalGroup.id.desc()).all()
    return jsonify({'success': True, 'groups': [g.to_dict() for g in rows]})


@app.route('/api/medical-groups', methods=['POST'])
@auth_required
def create_medical_group():
    try:
        data = request.get_json(silent=True) or {}
        hospital_id = data.get('hospital_id')
        name = (data.get('name') or '').strip()
        if not hospital_id or not name:
            return jsonify({'success': False, 'error': 'hospital_id/name required'}), 400
        group = MedicalGroup(hospital_id=int(hospital_id), name=name)
        db.session.add(group)
        db.session.commit()
        return jsonify({'success': True, 'group': group.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/doctors', methods=['GET'])
@auth_required
def list_doctors():
    """医生列表（默认同院）"""
    user: User = request.current_user  # type: ignore[attr-defined]
    hospital_id = request.args.get('hospital_id', type=int)
    medical_group_id = request.args.get('medical_group_id', type=int)
    q = User.query
    if hospital_id:
        q = q.filter(User.hospital_id == hospital_id)
    elif user.hospital_id:
        q = q.filter(User.hospital_id == user.hospital_id)
    if medical_group_id:
        q = q.filter(User.medical_group_id == medical_group_id)
    rows = q.order_by(User.id.desc()).all()
    return jsonify({'success': True, 'doctors': [r.to_dict() for r in rows]})


@app.route('/api/access-requests', methods=['POST'])
@auth_required
def create_access_request():
    """申请查看其他医生名下患者"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        data = request.get_json(silent=True) or {}
        owner_doctor_id = int(data.get('owner_doctor_id') or 0)
        if not owner_doctor_id or owner_doctor_id == user.id:
            return jsonify({'success': False, 'error': 'invalid owner_doctor_id'}), 400
        owner = User.query.get(owner_doctor_id)
        if not owner:
            return jsonify({'success': False, 'error': 'owner doctor not found'}), 404

        # 限制同院申请（可按需放开）
        if user.hospital_id and owner.hospital_id and user.hospital_id != owner.hospital_id:
            return jsonify({'success': False, 'error': 'cross-hospital request not allowed'}), 403

        existing = DoctorAccessRequest.query.filter_by(
            requester_doctor_id=user.id,
            owner_doctor_id=owner_doctor_id,
            status='pending',
        ).first()
        if existing:
            return jsonify({'success': False, 'error': 'pending request already exists'}), 409

        req = DoctorAccessRequest(
            requester_doctor_id=user.id,
            owner_doctor_id=owner_doctor_id,
            hospital_id=user.hospital_id or owner.hospital_id,
            reason=(data.get('reason') or '').strip() or None,
            status='pending',
        )
        db.session.add(req)
        db.session.commit()
        return jsonify({'success': True, 'request': req.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/access-requests', methods=['GET'])
@auth_required
def list_access_requests():
    user: User = request.current_user  # type: ignore[attr-defined]
    mode = (request.args.get('mode') or 'received').strip().lower()  # received/sent/all
    q = DoctorAccessRequest.query
    if mode == 'sent':
        q = q.filter(DoctorAccessRequest.requester_doctor_id == user.id)
    elif mode == 'all':
        q = q.filter(
            or_(
                DoctorAccessRequest.requester_doctor_id == user.id,
                DoctorAccessRequest.owner_doctor_id == user.id,
            )
        )
    else:
        q = q.filter(DoctorAccessRequest.owner_doctor_id == user.id)
    rows = q.order_by(DoctorAccessRequest.created_at.desc()).all()
    return jsonify({'success': True, 'requests': [r.to_dict() for r in rows]})


@app.route('/api/access-requests/<int:request_id>/decision', methods=['POST'])
@auth_required
def decide_access_request(request_id: int):
    """审批申请：approve / reject"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        data = request.get_json(silent=True) or {}
        action = (data.get('action') or '').strip().lower()
        expires_days = int(data.get('expires_days') or 0)
        if action not in ('approve', 'reject'):
            return jsonify({'success': False, 'error': 'action must be approve/reject'}), 400
        req = DoctorAccessRequest.query.get_or_404(request_id)
        if req.owner_doctor_id != user.id:
            return jsonify({'success': False, 'error': 'no permission'}), 403
        if req.status != 'pending':
            return jsonify({'success': False, 'error': 'request already decided'}), 409

        req.status = 'approved' if action == 'approve' else 'rejected'
        req.decided_at = datetime.utcnow()
        grant_obj = None
        if action == 'approve':
            grant_obj = DoctorPatientAccessGrant(
                grantee_doctor_id=req.requester_doctor_id,
                owner_doctor_id=req.owner_doctor_id,
                hospital_id=req.hospital_id,
                granted_by=user.id,
                expires_at=(datetime.utcnow() + timedelta(days=expires_days)) if expires_days > 0 else None,
                active=True,
            )
            db.session.add(grant_obj)
        db.session.commit()
        return jsonify({
            'success': True,
            'request': req.to_dict(),
            'grant': grant_obj.to_dict() if grant_obj else None
        })
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/access-grants', methods=['GET'])
@auth_required
def list_access_grants():
    user: User = request.current_user  # type: ignore[attr-defined]
    q = DoctorPatientAccessGrant.query.filter(
        or_(
            DoctorPatientAccessGrant.grantee_doctor_id == user.id,
            DoctorPatientAccessGrant.owner_doctor_id == user.id,
        )
    )
    rows = q.order_by(DoctorPatientAccessGrant.created_at.desc()).all()
    return jsonify({'success': True, 'grants': [g.to_dict() for g in rows]})


@app.route('/api/access-grants/<int:grant_id>/revoke', methods=['POST'])
@auth_required
def revoke_access_grant(grant_id: int):
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        grant = DoctorPatientAccessGrant.query.get_or_404(grant_id)
        if grant.owner_doctor_id != user.id:
            return jsonify({'success': False, 'error': 'no permission'}), 403
        grant.active = False
        db.session.commit()
        return jsonify({'success': True, 'grant': grant.to_dict()})
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)

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

    def classify_transport_from_pet(self, pet: Dict[str, Any]) -> str:
        """
        根据 PET 粗略判断腹膜转运类型（示意规则）：
        主要参考 4h D/P 肌酐（dialysate/plasma）。
        """
        d4_cr = float((pet.get('d4', {}) or {}).get('creatinine', 0) or 0)
        p2_cr = float((pet.get('p2', {}) or {}).get('creatinine', 0) or 0)
        ratio = (d4_cr / p2_cr) if p2_cr > 0 else 0.0
        if ratio >= 0.82:
            return 'high'
        if ratio >= 0.66:
            return 'high_average'
        if ratio >= 0.50:
            return 'low_average'
        return 'low'

    def estimate_residual_renal_metrics(self, renal: Dict[str, Any], plasma: Dict[str, Any]) -> Dict[str, float]:
        """
        估算残余肾功能贡献：
        - 残肾 Kt/V（按日）
        - 肌酐清除率（L/day）
        """
        urine_24h_ml = float(renal.get('urine_24h_ml', 0) or 0)
        urine_urea = float(renal.get('urine_urea', 0) or 0)
        urine_creatinine = float(renal.get('urine_creatinine', 0) or 0)
        plasma_urea = float(plasma.get('urea', 0) or 0)
        plasma_creatinine = float(plasma.get('creatinine', 0) or 0)
        weight = float(plasma.get('weight', 65) or 65)

        # 24h 尿量换算为 L/day
        urine_24h_l = urine_24h_ml / 1000.0
        # 粗略的“去除量比例”作为残肾 Kt/V 估计
        # 防止除零与异常值
        renal_ktv = 0.0
        if plasma_urea > 0 and weight > 0:
            renal_ktv = max(min((urine_urea / plasma_urea) * (urine_24h_l / (weight * 0.6)), 3.0), 0.0)

        renal_crcl_l_day = 0.0
        if plasma_creatinine > 0:
            renal_crcl_l_day = max((urine_creatinine / plasma_creatinine) * urine_24h_l, 0.0)

        return {
            'renal_ktv': float(round(renal_ktv, 3)),
            'renal_creatinine_clearance_l_day': float(round(renal_crcl_l_day, 3)),
        }

    def simulate_single_exchange(
        self,
        solution_type: str,
        concentration_pct: float,
        dwell_minutes: float,
        fill_volume_l: float,
        drain_minutes: float = 7.0,
        patient: Optional[Dict[str, Any]] = None,
        biomarkers: Optional[Dict[str, Any]] = None,
        current_time: float = 0.0,
    ) -> Dict[str, Any]:
        """
        模拟单次腹透（一次留腹+引流）：
        输出尿素清除、β2M 清除、超滤（小孔/超小孔分解）。
        """
        patient = patient or {}
        biomarkers = biomarkers or {}
        weight = float(self._safe_get(patient, 'weight', 65))
        age = float(self._safe_get(patient, 'age', 45))
        bun = float(self._safe_get(biomarkers, 'bun', 25.3))
        beta2m = float(self._safe_get(biomarkers, 'beta2_microglobulin', 25))
        creatinine = float(self._safe_get(biomarkers, 'creatinine', 884))

        dwell_minutes = max(float(dwell_minutes or 0), 10.0)
        fill_volume_l = max(float(fill_volume_l or 0), 0.5)
        concentration_pct = max(float(concentration_pct or 0), 0.0)
        drain_minutes = max(float(drain_minutes or 0), 1.0)

        # 方案类型对渗透与中大分子通量的影响（示意）
        stype = (solution_type or 'glucose').lower()
        if 'ico' in stype:
            osmotic_factor = 0.85
            beta2_factor = 1.15
            ultrasmall_ratio = 0.35
        elif 'amino' in stype:
            osmotic_factor = 0.65
            beta2_factor = 1.05
            ultrasmall_ratio = 0.25
        else:
            osmotic_factor = 1.0 + (concentration_pct - 1.5) * 0.08
            beta2_factor = 1.0
            ultrasmall_ratio = min(max(0.45 + concentration_pct * 0.05, 0.35), 0.75)

        # 个体系数
        patient_factor = 0.8 + (age / 100.0) * 0.2 + (weight / 100.0) * 0.2
        creatinine_factor = max(0.7, min(1.3, 1.0 - (creatinine - 884) / 8840))
        clearance_factor = patient_factor * creatinine_factor

        t = np.linspace(0, dwell_minutes, max(int(dwell_minutes / 5) + 1, 3))
        # 将分钟用于指数衰减，保证曲线平滑
        uf_rate = (concentration_pct * 5.0 * 0.015 * np.exp(-0.01 * t) * osmotic_factor * patient_factor)
        urea_clearance = (8.5 * (1 - np.exp(-0.008 * t)) * clearance_factor) * (bun / max(bun, 1e-6))
        beta2_clearance = (2.8 * (1 - np.exp(-0.004 * t)) * clearance_factor * beta2_factor) * (beta2m / max(beta2m, 1e-6))
        creatinine_clearance = (7.0 * (1 - np.exp(-0.006 * t)) * clearance_factor)

        total_uf = float(np.trapz(uf_rate, t))
        uf_ultrasmall = total_uf * ultrasmall_ratio
        uf_small = total_uf - uf_ultrasmall
        urea_removed = float(np.trapz(urea_clearance, t))
        beta2_removed = float(np.trapz(beta2_clearance, t))
        creatinine_removed = float(np.trapz(creatinine_clearance, t))

        v_dist = max(weight * 0.6 * 1000.0, 1.0)
        peritoneal_ktv = (float(np.mean(urea_clearance)) * dwell_minutes) / v_dist

        time_points = [float(current_time + m) for m in t.tolist()]
        volume_curve = [(fill_volume_l * 1000.0 + float(uf_rate[i]) * float(t[i])) / 1000.0 for i in range(len(t))]

        return {
            'inputs': {
                'solution_type': solution_type,
                'concentration_pct': concentration_pct,
                'dwell_minutes': dwell_minutes,
                'fill_volume_l': fill_volume_l,
                'drain_minutes': drain_minutes,
            },
            'summary': {
                'urea_clearance': round(urea_removed, 3),
                'beta2m_clearance': round(beta2_removed, 3),
                'creatinine_clearance': round(creatinine_removed, 3),
                'uf_small_pore': round(uf_small, 3),
                'uf_ultrasmall_pore': round(uf_ultrasmall, 3),
                'uf_total': round(total_uf, 3),
                'peritoneal_ktv': round(peritoneal_ktv, 4),
            },
            'time_series': {
                'time_min': time_points,
                'volume_l': volume_curve,
                'urea_clearance_rate': [float(x) for x in urea_clearance.tolist()],
                'beta2m_clearance_rate': [float(x) for x in beta2_clearance.tolist()],
                'uf_rate': [float(x) for x in uf_rate.tolist()],
            },
            'duration_total_min': float(dwell_minutes + drain_minutes),
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
@auth_required
def get_patients():
    """获取当前医生可见的患者列表（包含自己 + 同机构共享患者）"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        q = Patient.query
        q = q.filter(_patient_visibility_filter(user))
        patients = q.order_by(Patient.created_at.desc()).all()
        return jsonify(
            {
                'success': True,
                'patients': [p.to_dict() for p in patients],
            }
        )
    except Exception as e:
        return _error_response(e, 500)

@app.route('/api/patients/<int:patient_id>', methods=['GET'])
@auth_required
def get_patient(patient_id):
    """获取单个患者信息（访问控制）"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, _patient_visibility_filter(user)
        ).first()
        if not patient:
            return jsonify({'success': False, 'error': 'patient not found'}), 404
        return jsonify({'success': True, 'patient': patient.to_dict()})
    except Exception as e:
        return _error_response(e, 500)

@app.route('/api/patients', methods=['POST'])
@auth_required
def create_patient():
    """创建新患者：自动绑定当前医生和机构"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        data = request.json or {}  # ✅ 防止 None

        is_shared = bool(data.get('is_shared', False))

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
            anion_gap=data.get('biomarkers', {}).get('anion_gap', 12),
            owner_user_id=user.id,
            owner_org=user.org,
            is_shared=is_shared,
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
@auth_required
def update_patient(patient_id):
    """更新患者信息（只能修改自己有权限的患者）"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, _patient_visibility_filter(user)
        ).first()
        if not patient:
            return jsonify({'success': False, 'error': 'patient not found'}), 404

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
        # 是否共享标识（仅拥有者医生可修改）
        if 'is_shared' in data and patient.owner_user_id == user.id:
            patient.is_shared = bool(data['is_shared'])

        db.session.commit()
        
        return jsonify({
            'success': True,
            'patient': patient.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
@auth_required
def delete_patient(patient_id):
    """删除患者（仅限创建该患者的医生自己）"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, Patient.owner_user_id == user.id
        ).first()
        if not patient:
            return jsonify({'success': False, 'error': 'patient not found or no permission'}), 403
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
@auth_required
def get_patient_biochemistry(patient_id: int):
    """获取患者历史生化指标（需对该患者有访问权限）"""
    user: User = request.current_user  # type: ignore[attr-defined]
    patient = Patient.query.filter(
        Patient.id == patient_id, _patient_visibility_filter(user)
    ).first_or_404()
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
@auth_required
def create_patient_biochemistry(patient_id: int):
    """新增一条生化指标记录（需要对该患者有访问权限）"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, _patient_visibility_filter(user)
        ).first_or_404()
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


@app.route('/api/patients/<int:patient_id>/checks', methods=['GET'])
@auth_required
def list_patient_checks(patient_id: int):
    user: User = request.current_user  # type: ignore[attr-defined]
    patient = Patient.query.filter(
        Patient.id == patient_id, _patient_visibility_filter(user)
    ).first_or_404()
    rows = (PatientCheckRecord.query
            .filter_by(patient_id=patient.id)
            .order_by(PatientCheckRecord.checked_at.desc())
            .all())
    return jsonify({'success': True, 'checks': [r.to_dict() for r in rows]})


@app.route('/api/patients/<int:patient_id>/checks', methods=['POST'])
@auth_required
def create_patient_check(patient_id: int):
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, _patient_visibility_filter(user)
        ).first_or_404()
        data = request.get_json(silent=True) or {}
        item = PatientCheckRecord(
            patient_id=patient.id,
            checked_at=datetime.fromisoformat(data['checked_at']) if data.get('checked_at') else datetime.utcnow(),
            project_name=(data.get('project_name') or '').strip() or '未命名检查',
            result_value=(data.get('result_value') or '').strip() or None,
            unit=(data.get('unit') or '').strip() or None,
            note=(data.get('note') or '').strip() or None,
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'check': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/patients/<int:patient_id>/regimen-usages', methods=['GET'])
@auth_required
def list_patient_regimen_usages(patient_id: int):
    user: User = request.current_user  # type: ignore[attr-defined]
    patient = Patient.query.filter(
        Patient.id == patient_id, _patient_visibility_filter(user)
    ).first_or_404()
    rows = (PatientRegimenUsage.query
            .filter_by(patient_id=patient.id)
            .order_by(PatientRegimenUsage.created_at.desc())
            .all())
    return jsonify({'success': True, 'usages': [r.to_dict() for r in rows]})


@app.route('/api/patients/<int:patient_id>/regimen-usages', methods=['POST'])
@auth_required
def create_patient_regimen_usage(patient_id: int):
    """
    新增患者实际使用方案记录。
    可选 promote_as_template=true 自动把快照写入新模板。
    """
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        patient = Patient.query.filter(
            Patient.id == patient_id, _patient_visibility_filter(user)
        ).first_or_404()
        data = request.get_json(silent=True) or {}
        snapshot = data.get('regimen_snapshot') or {}
        template_id = data.get('template_id')
        usage = PatientRegimenUsage(
            patient_id=patient.id,
            doctor_id=user.id,
            template_id=int(template_id) if template_id else None,
            regimen_snapshot=snapshot,
            can_promote_to_template=bool(data.get('can_promote_to_template', True)),
        )
        db.session.add(usage)
        db.session.flush()

        created_template = None
        if data.get('promote_as_template'):
            name = (data.get('template_name') or f"{patient.name}-个体化方案-{usage.id}").strip()
            created_template = RegimenTemplate(
                name=name,
                description=(data.get('template_description') or '由患者实际方案生成'),
                category='custom',
                phases=normalize_regimen_phases(snapshot.get('phases', [])),
                created_by=user.username,
                metadata_json={'source_usage_id': usage.id, 'patient_id': patient.id},
                schema_version=2,
            )
            db.session.add(created_template)
            db.session.flush()
            usage.promoted_template_id = created_template.id
        db.session.commit()
        return jsonify({
            'success': True,
            'usage': usage.to_dict(),
            'created_template': serialize_regimen_model(created_template) if created_template else None,
        }), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/model-runs', methods=['POST'])
@auth_required
def create_statistical_model_run():
    """统计模型运行记录落库"""
    try:
        user: User = request.current_user  # type: ignore[attr-defined]
        data = request.get_json(silent=True) or {}
        run = StatisticalModelRun(
            patient_id=data.get('patient_id'),
            doctor_id=user.id,
            model_name=(data.get('model_name') or '').strip() or 'unnamed-model',
            model_version=(data.get('model_version') or '').strip() or None,
            input_payload=data.get('input_payload') or {},
            output_payload=data.get('output_payload') or {},
        )
        db.session.add(run)
        db.session.commit()
        return jsonify({'success': True, 'run': run.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/model-runs', methods=['GET'])
@auth_required
def list_statistical_model_runs():
    user: User = request.current_user  # type: ignore[attr-defined]
    patient_id = request.args.get('patient_id', type=int)
    q = StatisticalModelRun.query.filter(StatisticalModelRun.doctor_id == user.id)
    if patient_id:
        q = q.filter(StatisticalModelRun.patient_id == patient_id)
    rows = q.order_by(StatisticalModelRun.created_at.desc()).all()
    return jsonify({'success': True, 'runs': [r.to_dict() for r in rows]})

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


@app.route('/api/modeling/individualized', methods=['POST'])
def individualized_modeling():
    """
    三孔模型-个体化建模：
    输入 PET、2h 血液、24h 尿液等，输出转运类型、残肾贡献、钠筛、腹腔残余液体量估计。
    """
    try:
        data = request.get_json(silent=True) or {}
        patient = data.get('patient', {}) or {}
        pet = data.get('pet', {}) or {}
        blood_2h = data.get('blood_2h', {}) or {}
        urine_24h = data.get('urine_24h', {}) or {}

        transport_type = simulator.classify_transport_from_pet(pet)
        renal = simulator.estimate_residual_renal_metrics(
            {
                'urine_24h_ml': urine_24h.get('urine_volume_24h_ml', urine_24h.get('volume_ml', 0)),
                'urine_urea': urine_24h.get('urine_urea', 0),
                'urine_creatinine': urine_24h.get('urine_creatinine', 0),
            },
            {
                'urea': blood_2h.get('urea', 0),
                'creatinine': blood_2h.get('creatinine', 0),
                'weight': patient.get('weight', 65),
            },
        )

        # 1小时钠筛（简化估算）：2h 血钠与 0h/2h 透析液钠的偏移
        d0_na = float((pet.get('d0', {}) or {}).get('sodium', blood_2h.get('sodium', 140)) or 140)
        d2_na = float((pet.get('d2', {}) or {}).get('sodium', d0_na) or d0_na)
        plasma_na = float(blood_2h.get('sodium', 140) or 140)
        sodium_sieving_1h = max((plasma_na - ((d0_na + d2_na) / 2.0)) * 0.6, 0.0)

        # 腹腔残余液体量（简化估算）
        # 用 4h 葡萄糖下降幅度和尿量粗估 residual volume
        d0_glu = float((pet.get('d0', {}) or {}).get('glucose', 126) or 126)
        d4_glu = float((pet.get('d4', {}) or {}).get('glucose', d0_glu * 0.5) or (d0_glu * 0.5))
        glucose_drop_ratio = max(min((d0_glu - d4_glu) / max(d0_glu, 1e-6), 1.0), 0.0)
        urine_24h_ml = float(urine_24h.get('urine_volume_24h_ml', urine_24h.get('volume_ml', 0)) or 0)
        residual_intraperitoneal_ml = max(100.0, 350.0 - glucose_drop_ratio * 180.0 + max(0.0, 800 - urine_24h_ml) * 0.03)

        return jsonify({
            'success': True,
            'result': {
                'transport_type': transport_type,
                'renal_ktv': renal['renal_ktv'],
                'renal_creatinine_clearance_l_day': renal['renal_creatinine_clearance_l_day'],
                'sodium_sieving_1h': round(float(sodium_sieving_1h), 3),
                'residual_intraperitoneal_volume_ml': round(float(residual_intraperitoneal_ml), 1),
            },
        })
    except Exception as e:
        return _error_response(e, 500)


@app.route('/api/simulate/single-exchange', methods=['POST'])
def simulate_single_exchange_api():
    """
    三孔模型-单次腹透模拟：
    输入：液体类型、浓度、留腹时间、灌注量、引流时间
    输出：尿素清除、β2M 清除、超滤（小孔/超小孔）
    """
    try:
        data = request.get_json(silent=True) or {}
        patient = data.get('patient', {}) or {}
        biomarkers = data.get('biomarkers', {}) or {}
        solution_type = data.get('solution_type', 'glucose')
        concentration_pct = float(data.get('concentration_pct', data.get('concentration', 1.5)) or 1.5)
        dwell_minutes = float(data.get('dwell_minutes', data.get('dwell_hours', 6) * 60) or 360)
        fill_volume_l = float(data.get('fill_volume_l', data.get('fill_volume', 2.0)) or 2.0)
        drain_minutes = float(data.get('drain_minutes', 7) or 7)

        result = simulator.simulate_single_exchange(
            solution_type=solution_type,
            concentration_pct=concentration_pct,
            dwell_minutes=dwell_minutes,
            fill_volume_l=fill_volume_l,
            drain_minutes=drain_minutes,
            patient=patient,
            biomarkers=biomarkers,
            current_time=0.0,
        )
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return _error_response(e, 500)


@app.route('/api/simulate/continuous-24h', methods=['POST'])
def simulate_continuous_24h_api():
    """
    三孔模型-24小时连续透析模拟：
    输入 cycles（每循环的液体类型/浓度/灌注量/留腹时间）和统一引流时间。
    输出：总腹腔 Kt/V、总 Kt/V、肌酐清除、β2M 清除、总超滤（小孔/超小孔）。
    """
    try:
        data = request.get_json(silent=True) or {}
        patient = data.get('patient', {}) or {}
        biomarkers = data.get('biomarkers', {}) or {}
        cycles = data.get('cycles', []) or []
        drain_minutes = float(data.get('drain_minutes', 7) or 7)
        urine_24h = data.get('urine_24h', {}) or {}

        if not cycles:
            return jsonify({'success': False, 'error': 'cycles required'}), 400

        total_peritoneal_ktv = 0.0
        total_creatinine_clearance = 0.0
        total_beta2m_clearance = 0.0
        total_uf_small = 0.0
        total_uf_ultrasmall = 0.0
        current_time = 0.0
        cycle_results = []
        ts = {
            'time_min': [],
            'volume_l': [],
            'urea_clearance_rate': [],
            'beta2m_clearance_rate': [],
            'uf_rate': [],
        }

        for idx, c in enumerate(cycles):
            single = simulator.simulate_single_exchange(
                solution_type=c.get('solution_type', 'glucose'),
                concentration_pct=float(c.get('concentration_pct', c.get('concentration', 1.5)) or 1.5),
                dwell_minutes=float(c.get('dwell_minutes', c.get('dwell_hours', 6) * 60) or 360),
                fill_volume_l=float(c.get('fill_volume_l', c.get('fill_volume', 2.0)) or 2.0),
                drain_minutes=drain_minutes,
                patient=patient,
                biomarkers=biomarkers,
                current_time=current_time,
            )
            cycle_results.append({'cycle': idx + 1, **single})
            s = single['summary']
            total_peritoneal_ktv += float(s.get('peritoneal_ktv', 0))
            total_creatinine_clearance += float(s.get('creatinine_clearance', 0))
            total_beta2m_clearance += float(s.get('beta2m_clearance', 0))
            total_uf_small += float(s.get('uf_small_pore', 0))
            total_uf_ultrasmall += float(s.get('uf_ultrasmall_pore', 0))

            tss = single.get('time_series', {})
            ts['time_min'].extend(tss.get('time_min', []))
            ts['volume_l'].extend(tss.get('volume_l', []))
            ts['urea_clearance_rate'].extend(tss.get('urea_clearance_rate', []))
            ts['beta2m_clearance_rate'].extend(tss.get('beta2m_clearance_rate', []))
            ts['uf_rate'].extend(tss.get('uf_rate', []))
            current_time += float(single.get('duration_total_min', 0))

        renal = simulator.estimate_residual_renal_metrics(
            {
                'urine_24h_ml': urine_24h.get('urine_volume_24h_ml', urine_24h.get('volume_ml', 0)),
                'urine_urea': urine_24h.get('urine_urea', 0),
                'urine_creatinine': urine_24h.get('urine_creatinine', 0),
            },
            {
                'urea': biomarkers.get('bun', 0),
                'creatinine': biomarkers.get('creatinine', 0),
                'weight': patient.get('weight', 65),
            },
        )

        total_ktv = total_peritoneal_ktv + float(renal.get('renal_ktv', 0))

        return jsonify({
            'success': True,
            'result': {
                'total_peritoneal_ktv': round(total_peritoneal_ktv, 4),
                'total_ktv': round(total_ktv, 4),
                'creatinine_clearance': round(total_creatinine_clearance, 3),
                'beta2m_clearance': round(total_beta2m_clearance, 3),
                'total_uf_small_pore': round(total_uf_small, 3),
                'total_uf_ultrasmall_pore': round(total_uf_ultrasmall, 3),
                'total_uf': round(total_uf_small + total_uf_ultrasmall, 3),
                'renal_ktv': renal['renal_ktv'],
                'renal_creatinine_clearance_l_day': renal['renal_creatinine_clearance_l_day'],
                'duration_total_min': round(current_time, 1),
                'cycles': cycle_results,
                'time_series': ts,
            },
        })
    except Exception as e:
        return _error_response(e, 500)

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
            plasma_values=plasma_values,
        )
        # 注意：GeneticOptimizer 的签名在实现中支持 target_ktv，
        # 这里通过 type: ignore 避免静态类型检查误报。
        optimizer = GeneticOptimizer(objectives=objectives)  # type: ignore[call-arg]
        
        # 执行遗传算法优化
        best_prescription = optimizer.optimize()
        phases = getattr(best_prescription, "phases", None)
        if phases is None:
            phases = best_prescription.get("phases", [])  # type: ignore[union-attr]
        
        # 模拟最优方案以获取预测的 Kt/V 值
        best_regimen = {
            'name': '优化方案',
            'phases': phases,
        }
        
        results = simulator.simulate_full_regimen(best_regimen, patient, biomarkers)
        predicted_ktv = results['summary']['total_ktv']
        
        # 准备返回结果
        optimal_regimen = {
            'regimen_id': 'optimized',
            'regimen_name': '智能优化方案',
            'predicted_ktv': predicted_ktv,
            'phases': phases,
        }
        
        return jsonify({
            'success': True,
            'optimal_regimen': optimal_regimen
        })
    
    except Exception as e:
        return _error_response(e, 500)


@app.route('/api/patients/import/csv', methods=['POST'])
def import_patients_csv():
    """
    批量导入患者信息（CSV 表格）。
    - 接受 multipart/form-data，字段名为 file
    - 表头示例：name,gender,age,weight,height,bsa,dialysis_vintage,primary_disease,residual_kidney_function,peritoneal_transport,urine_volume,blood_pressure_systolic,blood_pressure_diastolic
    - 允许多余列，未识别列会忽略
    """
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'missing file'}), 400
    try:
        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        count = 0
        for row in reader:
            name = (row.get('name') or '').strip()
            if not name:
                continue
            patient = Patient(
                name=name,
                gender=row.get('gender') or None,
                age=int(row['age']) if row.get('age') else None,
                weight=float(row['weight']) if row.get('weight') else None,
                height=float(row['height']) if row.get('height') else None,
                bsa=float(row['bsa']) if row.get('bsa') else None,
                dialysis_vintage=int(row['dialysis_vintage']) if row.get('dialysis_vintage') else None,
                primary_disease=row.get('primary_disease') or None,
                residual_kidney_function=row.get('residual_kidney_function') or None,
                peritoneal_transport=row.get('peritoneal_transport') or None,
                urine_volume=float(row['urine_volume']) if row.get('urine_volume') else None,
                blood_pressure_systolic=float(row['blood_pressure_systolic']) if row.get('blood_pressure_systolic') else None,
                blood_pressure_diastolic=float(row['blood_pressure_diastolic']) if row.get('blood_pressure_diastolic') else None,
            )
            db.session.add(patient)
            count += 1
        db.session.commit()
        return jsonify({'success': True, 'imported': count})
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/patients/batch', methods=['POST'])
def import_patients_batch():
    """
    批量导入/互通接口：接受 JSON 数组 [{patient...}, ...]，
    用于外部数据库/系统通过 API 推送患者数据。
    """
    data = request.get_json(silent=True) or {}
    patients = data.get('patients') or []
    if not isinstance(patients, list):
        return jsonify({'success': False, 'error': 'patients must be a list'}), 400
    created = 0
    try:
        for p in patients:
            name = (p.get('name') or '').strip()
            if not name:
                continue
            patient = Patient(
                name=name,
                gender=p.get('gender'),
                age=p.get('age'),
                weight=p.get('weight'),
                height=p.get('height'),
                bsa=p.get('bsa'),
                dialysis_vintage=p.get('dialysis_vintage'),
                primary_disease=p.get('primary_disease'),
                residual_kidney_function=p.get('residual_kidney_function'),
                peritoneal_transport=p.get('peritoneal_transport'),
                urine_volume=p.get('urine_volume'),
                blood_pressure_systolic=p.get('blood_pressure_systolic'),
                blood_pressure_diastolic=p.get('blood_pressure_diastolic'),
            )
            db.session.add(patient)
            created += 1
        db.session.commit()
        return jsonify({'success': True, 'created': created})
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in ('1', 'true', 'yes', 'y', '是', '同意')


def _to_int(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _to_float(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return float(value)
    except Exception:
        return None


def _pick(row: Dict[str, Any], *keys: str):
    for key in keys:
        if key in row and row[key] is not None and str(row[key]).strip() != '':
            return row[key]
    return None


def _read_table_rows(upload_file) -> List[Dict[str, Any]]:
    filename = (upload_file.filename or '').lower()
    raw = upload_file.read()
    if not raw:
        return []
    if filename.endswith('.xlsx') or filename.endswith('.xls'):
        df = pd.read_excel(io.BytesIO(raw))
    else:
        df = pd.read_csv(io.BytesIO(raw))
    rows = df.to_dict(orient='records')
    cleaned = []
    for row in rows:
        item = {}
        for k, v in row.items():
            if pd.isna(v):  # type: ignore[arg-type]
                item[str(k).strip()] = None
            else:
                item[str(k).strip()] = v
        cleaned.append(item)
    return cleaned


def _parse_tabular_rows(entity: str, rows: List[Dict[str, Any]], current_user: User, dry_run: bool = False):
    """
    统一解析逻辑：
    - dry_run=True: 只校验与统计，不写库
    - dry_run=False: 解析并写库
    """
    created = 0
    updated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows, start=2):
        try:
            if entity == 'patients':
                name = _pick(row, 'name', '姓名')
                if not name:
                    skipped += 1
                    continue
                if dry_run:
                    created += 1
                    continue
                patient = Patient(
                    name=str(name).strip(),
                    gender=str(_pick(row, 'gender', '性别') or '').strip() or None,
                    age=_to_int(_pick(row, 'age', '年龄')),
                    weight=_to_float(_pick(row, 'weight', '体重')),
                    height=_to_float(_pick(row, 'height', '身高')),
                    bsa=_to_float(_pick(row, 'bsa', '体表面积')),
                    dialysis_vintage=_to_int(_pick(row, 'dialysis_vintage', '透析龄')),
                    primary_disease=str(_pick(row, 'primary_disease', '原发病') or '').strip() or None,
                    residual_kidney_function=str(_pick(row, 'residual_kidney_function', '残余肾功能') or '').strip() or None,
                    peritoneal_transport=str(_pick(row, 'peritoneal_transport', '腹膜转运') or '').strip() or None,
                    urine_volume=_to_float(_pick(row, 'urine_volume', '尿量')),
                    blood_pressure_systolic=_to_float(_pick(row, 'blood_pressure_systolic', '收缩压')),
                    blood_pressure_diastolic=_to_float(_pick(row, 'blood_pressure_diastolic', '舒张压')),
                    owner_user_id=current_user.id,
                    owner_org=current_user.org,
                    is_shared=_to_bool(_pick(row, 'is_shared', '是否共享', '共享'), False),
                )
                db.session.add(patient)
                created += 1
            else:
                username = _pick(row, 'username', '用户名')
                if not username:
                    skipped += 1
                    continue
                username_text = str(username).strip()
                if not username_text:
                    skipped += 1
                    continue
                existing = User.query.filter_by(username=username_text).first()
                if dry_run:
                    if existing:
                        updated += 1
                    else:
                        created += 1
                    continue
                pwd = str(_pick(row, 'password', '密码') or '123456')
                display_name = str(_pick(row, 'display_name', 'name', '姓名') or '').strip() or None
                org = str(_pick(row, 'org', '单位', '科室') or '').strip() or None
                hospital_id = _to_int(_pick(row, 'hospital_id', '医院ID'))
                medical_group_id = _to_int(_pick(row, 'medical_group_id', '医疗组ID'))
                allow_share_patients = _to_bool(_pick(row, 'allow_share_patients', '允许共享', '是否共享患者'), False)
                role = str(_pick(row, 'role', '角色') or 'doctor').strip() or 'doctor'

                if existing:
                    existing.display_name = display_name or existing.display_name
                    existing.org = org if org is not None else existing.org
                    existing.hospital_id = hospital_id if hospital_id is not None else existing.hospital_id
                    existing.medical_group_id = medical_group_id if medical_group_id is not None else existing.medical_group_id
                    existing.allow_share_patients = allow_share_patients
                    existing.role = role
                    updated += 1
                else:
                    user = User(
                        username=username_text,
                        password_hash=generate_password_hash(pwd),
                        display_name=display_name,
                        org=org,
                        hospital_id=hospital_id,
                        medical_group_id=medical_group_id,
                        allow_share_patients=allow_share_patients,
                        role=role,
                    )
                    db.session.add(user)
                    created += 1
        except Exception as row_err:
            skipped += 1
            errors.append({'row': idx, 'error': str(row_err)})

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
    }


@app.route('/api/import/tabular', methods=['POST'])
@auth_required
def import_tabular():
    """
    统一表格导入接口（CSV / Excel）：
    - multipart/form-data，字段：file
    - query 参数：entity=patients | doctors

    patients 常用列（支持中英文别名）：
    - name/姓名, gender/性别, age/年龄, weight/体重, height/身高, bsa/体表面积
    - dialysis_vintage/透析龄, primary_disease/原发病, residual_kidney_function/残余肾功能
    - peritoneal_transport/腹膜转运, urine_volume/尿量, blood_pressure_systolic/收缩压, blood_pressure_diastolic/舒张压
    - is_shared/是否共享

    doctors 常用列：
    - username/用户名, password/密码(可选，默认123456), display_name/姓名
    - org/单位, hospital_id/医院ID, medical_group_id/医疗组ID
    - allow_share_patients/允许共享, role/角色
    """
    entity = (request.args.get('entity') or '').strip().lower()
    file = request.files.get('file')
    if entity not in ('patients', 'doctors'):
        return jsonify({'success': False, 'error': 'entity must be patients or doctors'}), 400
    if not file:
        return jsonify({'success': False, 'error': 'missing file'}), 400

    try:
        current_user: User = request.current_user  # type: ignore[attr-defined]
        rows = _read_table_rows(file)
        parsed = _parse_tabular_rows(entity, rows, current_user, dry_run=False)
        db.session.commit()
        return jsonify({
            'success': True,
            'entity': entity,
            'total_rows': len(rows),
            'created': parsed['created'],
            'updated': parsed['updated'],
            'skipped': parsed['skipped'],
            'errors': parsed['errors'][:50],
        })
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 500)


@app.route('/api/import/tabular/validate', methods=['POST'])
@auth_required
def validate_tabular():
    """
    导入预校验（只检查不入库）：
    - multipart/form-data: file
    - query: entity=patients|doctors
    """
    entity = (request.args.get('entity') or '').strip().lower()
    file = request.files.get('file')
    if entity not in ('patients', 'doctors'):
        return jsonify({'success': False, 'error': 'entity must be patients or doctors'}), 400
    if not file:
        return jsonify({'success': False, 'error': 'missing file'}), 400
    try:
        current_user: User = request.current_user  # type: ignore[attr-defined]
        rows = _read_table_rows(file)
        parsed = _parse_tabular_rows(entity, rows, current_user, dry_run=True)
        return jsonify({
            'success': True,
            'entity': entity,
            'total_rows': len(rows),
            'would_create': parsed['created'],
            'would_update': parsed['updated'],
            'would_skip': parsed['skipped'],
            'errors': parsed['errors'][:50],
        })
    except Exception as e:
        return _error_response(e, 500)


@app.route('/api/import/template', methods=['GET'])
@auth_required
def download_import_template():
    """
    下载导入模板：
    - query: entity=patients|doctors
    - query: format=xlsx|csv (默认 xlsx)
    """
    entity = (request.args.get('entity') or '').strip().lower()
    fmt = (request.args.get('format') or 'xlsx').strip().lower()
    if entity not in ('patients', 'doctors'):
        return jsonify({'success': False, 'error': 'entity must be patients or doctors'}), 400
    if fmt not in ('xlsx', 'csv'):
        return jsonify({'success': False, 'error': 'format must be xlsx or csv'}), 400

    if entity == 'patients':
        columns = [
            'name', 'gender', 'age', 'weight', 'height', 'bsa',
            'dialysis_vintage', 'primary_disease', 'residual_kidney_function',
            'peritoneal_transport', 'urine_volume', 'blood_pressure_systolic',
            'blood_pressure_diastolic', 'is_shared'
        ]
        sample = [[
            '张三', 'male', 52, 63.5, 168, 1.72,
            24, 'diabetic_nephropathy', 'minimal', 'high_average',
            600, 145, 88, True
        ]]
    else:
        columns = [
            'username', 'password', 'display_name', 'org',
            'hospital_id', 'medical_group_id', 'allow_share_patients', 'role'
        ]
        sample = [[
            'doctor_lee', '123456', '李医生', 'XX医院 肾内科',
            1, 1, True, 'doctor'
        ]]

    df = pd.DataFrame(sample, columns=columns)

    if fmt == 'csv':
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        mem = io.BytesIO(csv_buf.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        return send_file(
            mem,
            as_attachment=True,
            download_name=f'{entity}_import_template.csv',
            mimetype='text/csv',
        )

    out = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError('failed to create worksheet')
    ws.title = 'template'
    ws.append(columns)
    for row in sample:
        ws.append(row)
    wb.save(out)
    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name=f'{entity}_import_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@app.route('/api/import/errors/export', methods=['POST'])
@auth_required
def export_import_errors():
    """
    导出导入错误清单：
    body: { entity, format, errors: [{row, error}] }
    format: xlsx|csv
    """
    data = request.get_json(silent=True) or {}
    entity = (data.get('entity') or 'unknown').strip().lower()
    fmt = (data.get('format') or 'xlsx').strip().lower()
    errors = data.get('errors') or []
    if fmt not in ('xlsx', 'csv'):
        return jsonify({'success': False, 'error': 'format must be xlsx or csv'}), 400
    if not isinstance(errors, list):
        return jsonify({'success': False, 'error': 'errors must be list'}), 400

    rows = []
    for idx, item in enumerate(errors, start=1):
        row_no = None
        message = ''
        if isinstance(item, dict):
            row_no = item.get('row')
            message = str(item.get('error') or '')
        else:
            message = str(item)
        rows.append({'index': idx, 'row': row_no, 'error': message})
    if not rows:
        rows.append({'index': 1, 'row': None, 'error': '无错误明细（空列表）'})

    df = pd.DataFrame(rows, columns=['index', 'row', 'error'])
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    if fmt == 'csv':
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        mem = io.BytesIO(buf.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        return send_file(
            mem,
            as_attachment=True,
            download_name=f'{entity}_import_errors_{timestamp}.csv',
            mimetype='text/csv',
        )

    out = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError('failed to create worksheet')
    ws.title = 'errors'
    ws.append(['index', 'row', 'error'])
    for item in rows:
        ws.append([item['index'], item['row'], item['error']])
    wb.save(out)
    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name=f'{entity}_import_errors_{timestamp}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


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


# ==================== 异步优化 + 进度查询 ====================

_opt_jobs: Dict[str, Dict[str, Any]] = {}
_opt_jobs_lock = threading.Lock()

def _job_set(job_id: str, patch: Dict[str, Any]):
    with _opt_jobs_lock:
        job = _opt_jobs.get(job_id, {})
        job.update(patch)
        _opt_jobs[job_id] = job

def _job_get(job_id: str) -> Optional[Dict[str, Any]]:
    with _opt_jobs_lock:
        job = _opt_jobs.get(job_id)
        return copy.deepcopy(job) if job else None

def _compute_optimization_result(mode: str, data: Dict[str, Any], progress_cb=None) -> Dict[str, Any]:
    patient = data.get('patient', {}) or {}
    biomarkers = data.get('biomarkers', {}) or {}
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
    result = optimizer.optimize(callback=progress_cb)

    # predicted summary
    prescription = result.get('prescription') if isinstance(result, dict) else None
    if mode == 'freeform' and prescription and isinstance(prescription, dict):
        phases = prescription.get('phases') or []
        regimen_payload = normalize_regimen_payload({'name': 'GA Optimized', 'phases': phases})
        sim_results = simulator.simulate_full_regimen(regimen_payload, patient, biomarkers)
        if isinstance(sim_results, dict) and sim_results.get('summary'):
            result['predicted'] = {'summary': sim_results.get('summary')}
    return result

def _start_opt_job(mode: str, data: Dict[str, Any]) -> str:
    job_id = f"job_{int(time.time() * 1000)}"
    total_generations = int(data.get('generations', 25) or 25)
    _job_set(job_id, {
        'status': 'running',
        'progress': 0.0,
        'current_generation': 0,
        'total_generations': total_generations,
        'best_fitness': 0.0,
        'started_at': time.time(),
    })

    def progress_cb(payload: Dict[str, Any]):
        gen = int(payload.get('generation', 0) or 0)
        best = float(payload.get('best_fitness', 0.0) or 0.0)
        total = int(payload.get('total_generations') or total_generations)
        progress = min(max(gen / max(total, 1), 0.0), 1.0)
        _job_set(job_id, {
            'current_generation': gen,
            'total_generations': total,
            'best_fitness': best,
            'progress': progress,
            'updated_at': time.time(),
        })

    def runner():
        try:
            result = _compute_optimization_result(mode, data, progress_cb=progress_cb)
            _job_set(job_id, {
                'status': 'done',
                'progress': 1.0,
                'result': result,
                'ended_at': time.time(),
            })
        except Exception as e:
            tb = traceback.format_exc()
            _job_set(job_id, {
                'status': 'error',
                'error': str(e),
                'traceback': tb,
                'ended_at': time.time(),
            })

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return job_id

@app.route('/api/optimize/freeform/async', methods=['POST'])
def optimize_regimen_freeform_async():
    data = request.get_json(silent=True) or {}
    job_id = _start_opt_job('freeform', data)
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/api/optimize/jobs/<job_id>', methods=['GET'])
def get_opt_job(job_id: str):
    job = _job_get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'job not found'}), 404
    return jsonify({'success': True, 'job': job})


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
