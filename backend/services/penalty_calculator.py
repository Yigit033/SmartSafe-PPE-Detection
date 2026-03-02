"""
SmartSafe AI - Penalty Calculator
Monthly penalty calculation system for PPE violations
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


# CEZA KURALLARI
PENALTY_RULES = {
    'no_helmet': {
        'per_violation': 500,  # TL - Her ihlal için sabit ceza
        'duration_penalty': 10,  # TL/dakika - Süre bazlı ceza
        'monthly_limit': 3,  # Aylık limit (aşarsa ağır ceza)
        'critical_multiplier': 2.0,  # Limit aşıldığında çarpan
        'severity': 'critical',
        'name_tr': 'Baret Eksikliği'
    },
    'no_vest': {
        'per_violation': 300,
        'duration_penalty': 5,
        'monthly_limit': 5,
        'critical_multiplier': 1.5,
        'severity': 'warning',
        'name_tr': 'Yelek Eksikliği'
    },
    'no_shoes': {
        'per_violation': 200,
        'duration_penalty': 3,
        'monthly_limit': 5,
        'critical_multiplier': 1.5,
        'severity': 'warning',
        'name_tr': 'Güvenlik Ayakkabısı Eksikliği'
    }
}


class PenaltyCalculator:
    """
    Aylık ceza hesaplama sistemi
    - Violation-based: İhlal sayısı ve süresine göre
    - Progressive: Tekrar ihlal daha ağır ceza
    - Monthly tracking: Aylık bazda takip
    """
    
    def __init__(self):
        """Initialize penalty calculator"""
        logger.info("✅ PenaltyCalculator initialized")
    
    def calculate_violation_penalty(
        self,
        violation_type: str,
        duration_seconds: int,
        monthly_violation_count: int = 1
    ) -> Dict:
        """
        Tek bir ihlal için ceza hesapla
        
        Args:
            violation_type: İhlal tipi ('no_helmet', 'no_vest', 'no_shoes')
            duration_seconds: İhlal süresi (saniye)
            monthly_violation_count: Bu ay bu kişinin aynı tipte kaç ihlali var
            
        Returns:
            Ceza detayları dict
        """
        if violation_type not in PENALTY_RULES:
            logger.warning(f"⚠️ Unknown violation type: {violation_type}")
            return {
                'violation_type': violation_type,
                'base_penalty': 0,
                'duration_penalty': 0,
                'total_penalty': 0,
                'multiplier': 1.0,
                'severity': 'unknown'
            }
        
        rule = PENALTY_RULES[violation_type]
        
        # 1. Temel ceza
        base_penalty = rule['per_violation']
        
        # 2. Süre bazlı ceza (dakika)
        duration_minutes = duration_seconds / 60
        duration_penalty = duration_minutes * rule['duration_penalty']
        
        # 3. Tekrar ihlal kontrolü
        multiplier = 1.0
        if monthly_violation_count > rule['monthly_limit']:
            multiplier = rule['critical_multiplier']
            logger.warning(
                f"⚠️ Monthly limit exceeded for {violation_type}: "
                f"{monthly_violation_count} > {rule['monthly_limit']}"
            )
        
        # Toplam ceza
        total_penalty = (base_penalty + duration_penalty) * multiplier
        
        return {
            'violation_type': violation_type,
            'violation_name': rule['name_tr'],
            'base_penalty': round(base_penalty, 2),
            'duration_penalty': round(duration_penalty, 2),
            'duration_minutes': round(duration_minutes, 2),
            'multiplier': multiplier,
            'total_penalty': round(total_penalty, 2),
            'severity': rule['severity'],
            'monthly_count': monthly_violation_count,
            'monthly_limit': rule['monthly_limit'],
            'limit_exceeded': monthly_violation_count > rule['monthly_limit']
        }
    
    def calculate_monthly_penalty(
        self,
        person_id: str,
        violations: List[Dict],
        month: str
    ) -> Dict:
        """
        Kişi için aylık toplam ceza hesapla
        
        Args:
            person_id: Kişi ID
            violations: İhlal listesi (violation_events)
            month: Ay (format: '2025-10')
            
        Returns:
            Aylık ceza raporu
        """
        # İhlalleri tipe göre grupla
        by_type = defaultdict(list)
        for violation in violations:
            v_type = violation.get('violation_type')
            if v_type:
                by_type[v_type].append(violation)
        
        # Her tip için ceza hesapla
        penalties_by_type = {}
        total_penalty = 0
        total_violations = 0
        total_duration = 0
        
        for v_type, v_list in by_type.items():
            type_penalty = 0
            type_duration = 0
            
            for i, violation in enumerate(v_list, 1):
                duration = violation.get('duration_seconds', 0)
                type_duration += duration
                
                # İhlal cezası hesapla (aylık sayı ile)
                penalty_info = self.calculate_violation_penalty(
                    v_type,
                    duration,
                    monthly_violation_count=i
                )
                
                type_penalty += penalty_info['total_penalty']
            
            penalties_by_type[v_type] = {
                'violation_name': PENALTY_RULES.get(v_type, {}).get('name_tr', v_type),
                'count': len(v_list),
                'total_duration_seconds': type_duration,
                'total_duration_minutes': round(type_duration / 60, 2),
                'total_penalty': round(type_penalty, 2),
                'severity': PENALTY_RULES.get(v_type, {}).get('severity', 'unknown')
            }
            
            total_penalty += type_penalty
            total_violations += len(v_list)
            total_duration += type_duration
        
        return {
            'person_id': person_id,
            'month': month,
            'total_violations': total_violations,
            'total_duration_seconds': total_duration,
            'total_duration_minutes': round(total_duration / 60, 2),
            'total_penalty': round(total_penalty, 2),
            'penalties_by_type': penalties_by_type,
            'calculated_at': datetime.now().isoformat()
        }
    
    def calculate_company_monthly_penalty(
        self,
        company_id: str,
        person_violations: Dict[str, List[Dict]],
        month: str
    ) -> Dict:
        """
        Şirket için aylık toplam ceza hesapla
        
        Args:
            company_id: Şirket ID
            person_violations: {person_id: [violations]}
            month: Ay (format: '2025-10')
            
        Returns:
            Şirket aylık ceza raporu
        """
        person_penalties = {}
        total_company_penalty = 0
        total_company_violations = 0
        
        for person_id, violations in person_violations.items():
            penalty_info = self.calculate_monthly_penalty(person_id, violations, month)
            person_penalties[person_id] = penalty_info
            
            total_company_penalty += penalty_info['total_penalty']
            total_company_violations += penalty_info['total_violations']
        
        return {
            'company_id': company_id,
            'month': month,
            'total_people': len(person_violations),
            'total_violations': total_company_violations,
            'total_penalty': round(total_company_penalty, 2),
            'person_penalties': person_penalties,
            'calculated_at': datetime.now().isoformat()
        }
    
    def get_penalty_summary(self, penalty_report: Dict) -> str:
        """
        Ceza raporunu özetleyen metin oluştur
        
        Args:
            penalty_report: calculate_monthly_penalty() sonucu
            
        Returns:
            Özet metin
        """
        summary_lines = []
        summary_lines.append(f"📊 AYLIK CEZA RAPORU - {penalty_report['month']}")
        summary_lines.append(f"Kişi: {penalty_report['person_id']}")
        summary_lines.append(f"Toplam İhlal: {penalty_report['total_violations']}")
        summary_lines.append(f"Toplam Süre: {penalty_report['total_duration_minutes']:.1f} dakika")
        summary_lines.append(f"Toplam Ceza: {penalty_report['total_penalty']:.2f} TL")
        summary_lines.append("")
        summary_lines.append("İhlal Detayları:")
        
        for v_type, info in penalty_report['penalties_by_type'].items():
            summary_lines.append(
                f"  • {info['violation_name']}: "
                f"{info['count']} ihlal, "
                f"{info['total_duration_minutes']:.1f} dk, "
                f"{info['total_penalty']:.2f} TL"
            )
        
        return "\n".join(summary_lines)


# Global instance
_penalty_calculator = None


def get_penalty_calculator() -> PenaltyCalculator:
    """Global penalty calculator instance'ı al"""
    global _penalty_calculator
    if _penalty_calculator is None:
        _penalty_calculator = PenaltyCalculator()
    return _penalty_calculator
