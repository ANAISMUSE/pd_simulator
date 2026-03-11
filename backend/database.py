from flask_sqlalchemy import SQLAlchemy  # type: ignore
from datetime import datetime
from sqlalchemy import inspect, text  # type: ignore

db = SQLAlchemy()

class User(db.Model):
    """用户表（用于鉴权）"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

class Patient(db.Model):
    """患者信息表"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 基本信息
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10))
    age = db.Column(db.Integer)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    bsa = db.Column(db.Float)
    
    # 透析信息
    dialysis_vintage = db.Column(db.Integer)
    primary_disease = db.Column(db.String(200))
    residual_kidney_function = db.Column(db.String(50))
    peritoneal_transport = db.Column(db.String(50))
    urine_volume = db.Column(db.Float)
    blood_pressure_systolic = db.Column(db.Float)
    blood_pressure_diastolic = db.Column(db.Float)
    
    # 生化指标
    creatinine = db.Column(db.Float)
    bun = db.Column(db.Float)
    uric_acid = db.Column(db.Float)
    beta2_microglobulin = db.Column(db.Float)
    potassium = db.Column(db.Float)
    sodium = db.Column(db.Float)
    chloride = db.Column(db.Float)
    calcium = db.Column(db.Float)
    phosphorus = db.Column(db.Float)
    magnesium = db.Column(db.Float)
    hemoglobin = db.Column(db.Float)
    albumin = db.Column(db.Float)
    total_protein = db.Column(db.Float)
    hematocrit = db.Column(db.Float)
    glucose = db.Column(db.Float)
    hba1c = db.Column(db.Float)
    cholesterol = db.Column(db.Float)
    triglycerides = db.Column(db.Float)
    ph = db.Column(db.Float)
    bicarbonate = db.Column(db.Float)
    pco2 = db.Column(db.Float)
    anion_gap = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'name': self.name,
            'gender': self.gender,
            'age': self.age,
            'weight': self.weight,
            'height': self.height,
            'bsa': self.bsa,
            'dialysis_vintage': self.dialysis_vintage,
            'primary_disease': self.primary_disease,
            'residual_kidney_function': self.residual_kidney_function,
            'peritoneal_transport': self.peritoneal_transport,
            'urine_volume': self.urine_volume,
            'blood_pressure_systolic': self.blood_pressure_systolic,
            'blood_pressure_diastolic': self.blood_pressure_diastolic,
            'biomarkers': {
                'creatinine': self.creatinine,
                'bun': self.bun,
                'uric_acid': self.uric_acid,
                'beta2_microglobulin': self.beta2_microglobulin,
                'potassium': self.potassium,
                'sodium': self.sodium,
                'chloride': self.chloride,
                'calcium': self.calcium,
                'phosphorus': self.phosphorus,
                'magnesium': self.magnesium,
                'hemoglobin': self.hemoglobin,
                'albumin': self.albumin,
                'total_protein': self.total_protein,
                'hematocrit': self.hematocrit,
                'glucose': self.glucose,
                'hba1c': self.hba1c,
                'cholesterol': self.cholesterol,
                'triglycerides': self.triglycerides,
                'ph': self.ph,
                'bicarbonate': self.bicarbonate,
                'pco2': self.pco2,
                'anion_gap': self.anion_gap
            },
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class RegimenTemplate(db.Model):
    """透析方案模板表"""
    __tablename__ = 'regimen_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # 'preset', 'custom', 'optimized'
    version = db.Column(db.Integer, default=1)
    parent_id = db.Column(db.Integer, db.ForeignKey('regimen_templates.id'))
    is_preset = db.Column(db.Boolean, default=False)
    schema_version = db.Column(db.Integer, default=1)
    metadata_json = db.Column('metadata', db.JSON, default=dict)
    
    # 方案定义（JSON格式）
    phases = db.Column(db.JSON, nullable=False)
    # 示例: [
    #   {
    #     "phase_name": "早晨",
    #     "start_time": "08:00",
    #     "duration": 6,
    #     "glucose_conc": 1.5,
    #     "fill_volume": 2.0,
    #     "solution_type": "standard"
    #   }
    # ]
    
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    parent = db.relationship('RegimenTemplate', remote_side=[id], backref='versions')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'version': self.version,
            'parent_id': self.parent_id,
            'is_preset': self.is_preset,
            'schema_version': self.schema_version,
            'phases': self.phases,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata_json or {}
        }


class SimulationHistory(db.Model):
    """模拟历史记录表"""
    __tablename__ = 'simulation_history'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    regimen_id = db.Column(db.Integer, db.ForeignKey('regimen_templates.id'))
    
    # 模拟结果（JSON格式）
    results = db.Column(db.JSON, nullable=False)
    
    # 时间序列数据
    time_series = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    patient = db.relationship('Patient', backref='simulations')
    regimen = db.relationship('RegimenTemplate', backref='simulations')
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient.name if self.patient else None,
            'regimen_id': self.regimen_id,
            'regimen_name': self.regimen.name if self.regimen else None,
            'results': self.results,
            'time_series': self.time_series,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PatientBiochemistrySnapshot(db.Model):
    """患者生化指标时间序列表"""
    __tablename__ = 'patient_biochemistry_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    biomarkers = db.Column(db.JSON, nullable=False, default=dict)
    note = db.Column(db.String(255))
    
    patient = db.relationship('Patient', backref='biochemistry_snapshots')
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'biomarkers': self.biomarkers,
            'note': self.note
        }


class RegimenAuditLog(db.Model):
    """方案操作审计记录"""
    __tablename__ = 'regimen_audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    regimen_id = db.Column(db.Integer, db.ForeignKey('regimen_templates.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    operator = db.Column(db.String(100))
    payload = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    regimen = db.relationship('RegimenTemplate', backref='audit_logs')
    
    def to_dict(self):
        return {
            'id': self.id,
            'regimen_id': self.regimen_id,
            'action': self.action,
            'operator': self.operator,
            'payload': self.payload,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    """检查指定列是否存在"""
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(col['name'] == column_name for col in columns)


def apply_schema_migrations(app):
    """
    轻量级迁移：在不依赖 Alembic 的情况下，确保新增列存在
    """
    with app.app_context():
        inspector = inspect(db.engine)
        
        alterations = []
        if not _column_exists(inspector, 'regimen_templates', 'version'):
            alterations.append("ALTER TABLE regimen_templates ADD COLUMN version INTEGER DEFAULT 1")
        if not _column_exists(inspector, 'regimen_templates', 'parent_id'):
            alterations.append("ALTER TABLE regimen_templates ADD COLUMN parent_id INTEGER REFERENCES regimen_templates(id)")
        if not _column_exists(inspector, 'regimen_templates', 'is_preset'):
            alterations.append("ALTER TABLE regimen_templates ADD COLUMN is_preset BOOLEAN DEFAULT 0")
        if not _column_exists(inspector, 'regimen_templates', 'schema_version'):
            alterations.append("ALTER TABLE regimen_templates ADD COLUMN schema_version INTEGER DEFAULT 1")
        if not _column_exists(inspector, 'regimen_templates', 'metadata'):
            alterations.append("ALTER TABLE regimen_templates ADD COLUMN metadata JSON")
        
        for statement in alterations:
            with db.engine.begin() as connection:
                connection.execute(text(statement))
