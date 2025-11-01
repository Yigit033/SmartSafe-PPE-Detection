"""
SmartSafe AI - Violation Tracker System
Event-based intelligent violation tracking with person identification
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


class ViolationTracker:
    """
    Akıllı ihlal takip sistemi
    - Event-based: Sadece ihlal başladığında ve bittiğinde kayıt
    - Person tracking: Kişi bazlı ihlal takibi
    - Cooldown: Aynı ihlal tekrar sayılmaz (60 saniye)
    """
    
    def __init__(self, cooldown_period: int = 60):
        """
        Args:
            cooldown_period: İhlal bitmiş sayılması için gereken süre (saniye)
        """
        self.cooldown_period = cooldown_period
        
        # Aktif ihlaller: {camera_id: {person_hash: {violation_type: start_time}}}
        self.active_violations: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        
        # İhlal geçmişi (memory cache): {event_id: event_data}
        self.violation_history: Dict[str, Dict] = {}
        
        # Son kontrol zamanı
        self.last_cleanup_time = time.time()
        
        logger.info("✅ ViolationTracker initialized with cooldown: %d seconds", cooldown_period)
    
    def generate_person_hash(self, person_bbox: List[float], camera_id: str) -> str:
        """
        Kişi için unique hash oluştur (bbox konumuna göre)
        Gelecekte yüz tanıma ile değiştirilecek
        
        Args:
            person_bbox: [x1, y1, x2, y2]
            camera_id: Kamera ID
            
        Returns:
            Person hash (örn: "PERSON_ABC123")
        """
        # Bbox merkez noktası
        center_x = (person_bbox[0] + person_bbox[2]) / 2
        center_y = (person_bbox[1] + person_bbox[3]) / 2
        
        # Hash oluştur (kamera + konum)
        hash_input = f"{camera_id}_{int(center_x/50)}_{int(center_y/50)}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()
        
        return f"PERSON_{hash_value}"
    
    def process_detection(
        self, 
        camera_id: str, 
        company_id: str,
        person_bbox: List[float], 
        violations: List[str],
        frame_snapshot: Optional[bytes] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Detection sonucunu işle ve yeni/biten ihlalleri tespit et
        
        Args:
            camera_id: Kamera ID
            company_id: Şirket ID
            person_bbox: Kişi bounding box
            violations: İhlal listesi ['Baret eksik', 'Yelek eksik']
            frame_snapshot: Frame görüntüsü (opsiyonel)
            
        Returns:
            (new_violations, ended_violations)
        """
        person_id = self.generate_person_hash(person_bbox, camera_id)
        current_time = time.time()
        
        new_violations = []
        ended_violations = []
        
        # Violation type mapping (Türkçe -> İngilizce)
        violation_map = {
            'Baret eksik': 'no_helmet',
            'Yelek eksik': 'no_vest',
            'Güvenlik ayakkabısı eksik': 'no_shoes'
        }
        
        # Mevcut ihlalleri normalize et
        current_violations = set()
        for v in violations:
            violation_type = violation_map.get(v, v.lower().replace(' ', '_'))
            current_violations.add(violation_type)
        
        # Kamera için aktif ihlalleri al
        camera_violations = self.active_violations[camera_id]
        person_violations = camera_violations[person_id]
        
        # YENİ İHLALLERİ KONTROL ET
        for violation_type in current_violations:
            if violation_type not in person_violations:
                # ✅ YENİ İHLAL BAŞLADI
                event_id = f"VIO_{camera_id}_{person_id}_{violation_type}_{int(current_time)}"
                
                event_data = {
                    'event_id': event_id,
                    'company_id': company_id,
                    'camera_id': camera_id,
                    'person_id': person_id,
                    'violation_type': violation_type,
                    'start_time': current_time,
                    'start_timestamp': datetime.fromtimestamp(current_time).isoformat(),
                    'person_bbox': person_bbox,
                    'status': 'active',
                    'severity': self._calculate_severity(violation_type)
                }
                
                person_violations[violation_type] = current_time
                self.violation_history[event_id] = event_data
                new_violations.append(event_data)
                
                logger.info(f"🚨 NEW VIOLATION: {violation_type} for {person_id} on {camera_id}")
        
        # BİTEN İHLALLERİ KONTROL ET
        for violation_type in list(person_violations.keys()):
            if violation_type not in current_violations:
                # ✅ İHLAL BİTTİ
                start_time = person_violations[violation_type]
                duration = current_time - start_time
                
                # Event ID'yi bul
                event_id = None
                for eid, event in self.violation_history.items():
                    if (event['person_id'] == person_id and 
                        event['violation_type'] == violation_type and
                        event['status'] == 'active'):
                        event_id = eid
                        break
                
                if event_id:
                    event_data = self.violation_history[event_id]
                    event_data['end_time'] = current_time
                    event_data['end_timestamp'] = datetime.fromtimestamp(current_time).isoformat()
                    event_data['duration_seconds'] = int(duration)
                    event_data['status'] = 'resolved'
                    
                    ended_violations.append(event_data)
                    logger.info(f"✅ VIOLATION RESOLVED: {violation_type} for {person_id} (duration: {int(duration)}s)")
                
                del person_violations[violation_type]
        
        # Periyodik cleanup (her 60 saniyede bir)
        if current_time - self.last_cleanup_time > 60:
            self._cleanup_stale_violations()
            self.last_cleanup_time = current_time
        
        return new_violations, ended_violations
    
    def _cleanup_stale_violations(self):
        """Uzun süredir güncellenmemiş ihlalleri temizle"""
        current_time = time.time()
        cleanup_count = 0
        
        for camera_id in list(self.active_violations.keys()):
            for person_id in list(self.active_violations[camera_id].keys()):
                person_violations = self.active_violations[camera_id][person_id]
                
                for violation_type in list(person_violations.keys()):
                    start_time = person_violations[violation_type]
                    
                    # Cooldown süresinden uzun süredir güncellenmemiş
                    if current_time - start_time > self.cooldown_period:
                        # İhlali bitmiş say
                        duration = current_time - start_time
                        
                        # Event'i bul ve güncelle
                        for eid, event in self.violation_history.items():
                            if (event['person_id'] == person_id and 
                                event['violation_type'] == violation_type and
                                event['status'] == 'active'):
                                event['end_time'] = current_time
                                event['end_timestamp'] = datetime.fromtimestamp(current_time).isoformat()
                                event['duration_seconds'] = int(duration)
                                event['status'] = 'auto_resolved'
                                break
                        
                        del person_violations[violation_type]
                        cleanup_count += 1
                
                # Kişinin hiç ihlali kalmadıysa sil
                if not person_violations:
                    del self.active_violations[camera_id][person_id]
            
            # Kamerada hiç aktif ihlal kalmadıysa sil
            if not self.active_violations[camera_id]:
                del self.active_violations[camera_id]
        
        if cleanup_count > 0:
            logger.debug(f"🧹 Cleaned up {cleanup_count} stale violations")
    
    def _calculate_severity(self, violation_type: str) -> str:
        """İhlal şiddetini hesapla"""
        critical_violations = ['no_helmet']
        warning_violations = ['no_vest', 'no_shoes']
        
        if violation_type in critical_violations:
            return 'critical'
        elif violation_type in warning_violations:
            return 'warning'
        else:
            return 'info'
    
    def get_active_violations(self, camera_id: Optional[str] = None) -> List[Dict]:
        """
        Aktif ihlalleri getir
        
        Args:
            camera_id: Belirli bir kamera için (None ise tümü)
            
        Returns:
            Aktif ihlal listesi
        """
        active = []
        
        if camera_id:
            # Belirli kamera
            if camera_id in self.active_violations:
                for person_id, violations in self.active_violations[camera_id].items():
                    for violation_type, start_time in violations.items():
                        # Event'i bul
                        for event in self.violation_history.values():
                            if (event['person_id'] == person_id and
                                event['violation_type'] == violation_type and
                                event['status'] == 'active'):
                                active.append(event)
                                break
        else:
            # Tüm kameralar
            for event in self.violation_history.values():
                if event['status'] == 'active':
                    active.append(event)
        
        return active
    
    def get_violation_stats(self, camera_id: str, hours: int = 24) -> Dict:
        """
        İhlal istatistiklerini getir
        
        Args:
            camera_id: Kamera ID
            hours: Son kaç saat
            
        Returns:
            İstatistik dict
        """
        cutoff_time = time.time() - (hours * 3600)
        
        total_violations = 0
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        total_duration = 0
        
        for event in self.violation_history.values():
            if event['camera_id'] == camera_id and event['start_time'] >= cutoff_time:
                total_violations += 1
                by_type[event['violation_type']] += 1
                by_severity[event['severity']] += 1
                
                if 'duration_seconds' in event:
                    total_duration += event['duration_seconds']
        
        return {
            'total_violations': total_violations,
            'by_type': dict(by_type),
            'by_severity': dict(by_severity),
            'total_duration_seconds': total_duration,
            'avg_duration_seconds': total_duration / max(total_violations, 1)
        }


# Global instance
_violation_tracker = None


def get_violation_tracker() -> ViolationTracker:
    """Global violation tracker instance'ı al"""
    global _violation_tracker
    if _violation_tracker is None:
        _violation_tracker = ViolationTracker(cooldown_period=60)
    return _violation_tracker
