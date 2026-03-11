# backend/models/risk_data.py

from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum

class RiskLevel(Enum):
    """风险等级"""
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "严重风险"

@dataclass
class BiomarkerTimeSeries:
    """生化指标时间序列"""
    
    biomarker_name: str                # 指标名称（如 'urea', 'creatinine'）
    time_points: List[float]           # 时间点（分钟）
    values: List[float]                # 指标值序列
    
    # 安全阈值
    upper_threshold: float             # 上限阈值
    lower_threshold: float             # 下限阈值
    
    # 风险分析
    violations: List[Dict] = field(default_factory=list)  # 违规记录
    risk_level: RiskLevel = RiskLevel.LOW
    
    def detect_violations(self):
        """检测阈值违规"""
        self.violations = []
        for t, v in zip(self.time_points, self.values):
            if v > self.upper_threshold:
                self.violations.append({
                    'time': t,
                    'value': v,
                    'type': 'upper_violation',
                    'severity': (v - self.upper_threshold) / self.upper_threshold
                })
            elif v < self.lower_threshold:
                self.violations.append({
                    'time': t,
                    'value': v,
                    'type': 'lower_violation',
                    'severity': (self.lower_threshold - v) / self.lower_threshold
                })
        
        # 根据违规数量和严重程度评估风险等级
        if not self.violations:
            self.risk_level = RiskLevel.LOW
        elif len(self.violations) <= 2:
            self.risk_level = RiskLevel.MEDIUM
        elif len(self.violations) <= 5:
            self.risk_level = RiskLevel.HIGH
        else:
            self.risk_level = RiskLevel.CRITICAL

@dataclass
class PrescriptionRiskAssessment:
    """透析方案风险评估"""
    
    prescription_id: str               # 方案ID
    prescription: Dict                 # 方案详情
    assessment_date: str               # 评估日期
    
    biomarker_series: List[BiomarkerTimeSeries] = field(default_factory=list)
    
    # 综合风险评估
    overall_risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = 0.0            # 风险评分（0-100）
    recommendations: List[str] = field(default_factory=list)  # 改进建议
    
    def calculate_overall_risk(self):
        """计算综合风险"""
        risk_scores = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 30,
            RiskLevel.HIGH: 60,
            RiskLevel.CRITICAL: 90
        }
        
        if not self.biomarker_series:
            return
        
        # 计算平均风险分数
        total_score = sum(risk_scores[bs.risk_level] for bs in self.biomarker_series)
        self.risk_score = total_score / len(self.biomarker_series)
        
        # 确定整体风险等级（取最高）
        max_risk = max(bs.risk_level for bs in self.biomarker_series)
        self.overall_risk_level = max_risk
        
        # 生成建议
        self.recommendations = self._generate_recommendations()
    
    def _generate_recommendations(self) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        for bs in self.biomarker_series:
            if bs.risk_level == RiskLevel.CRITICAL:
                recommendations.append(
                    f"⚠️ {bs.biomarker_name} 存在严重风险，建议调整治疗方案"
                )
            elif bs.risk_level == RiskLevel.HIGH:
                recommendations.append(
                    f"⚠️ {bs.biomarker_name} 存在高风险，需密切监测"
                )
        
        return recommendations
    
    def to_dict(self) -> Dict:
        return {
            'prescription_id': self.prescription_id,
            'assessment_date': self.assessment_date,
            'overall_risk': {
                'level': self.overall_risk_level.value,
                'score': self.risk_score,
            },
            'biomarkers': [
                {
                    'name': bs.biomarker_name,
                    'risk_level': bs.risk_level.value,
                    'violations_count': len(bs.violations),
                    'violations': bs.violations
                }
                for bs in self.biomarker_series
            ],
            'recommendations': self.recommendations
        }
