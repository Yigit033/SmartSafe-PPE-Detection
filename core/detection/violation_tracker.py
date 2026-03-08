"""
SmartSafe AI - Violation Tracker System
Event-based intelligent violation tracking with person identification
"""

import time
import logging
import threading
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
    
    def __init__(self, cooldown_period: int = 60, iou_threshold: float = 0.3, person_timeout: float = 5.0):
        """
        Args:
            cooldown_period: İhlal bitmiş sayılması için gereken süre (saniye)
            iou_threshold: IoU eşik değeri (0.0-1.0), person matching için minimum overlap
            person_timeout: Person görünmezse kaç saniye sonra silinecek
        """
        self.cooldown_period = cooldown_period
        self.iou_threshold = iou_threshold
        self.person_timeout = person_timeout
        self._lock = threading.Lock()
        
        # Aktif ihlaller: {camera_id: {person_hash: {violation_type: start_time}}}
        self.active_violations: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        
        # İhlal geçmişi (memory cache): {event_id: event_data}
        self.violation_history: Dict[str, Dict] = {}
        
        # IoU-based person tracking state
        # {camera_id: {person_id: {'bbox': bbox, 'last_seen': timestamp}}}
        self.person_tracking: Dict[str, Dict[str, Dict]] = defaultdict(dict)
        
        # Person ID counter (yeni person'lar için fallback)
        self.next_person_id_counter: Dict[str, int] = defaultdict(int)
        
        # Frame bazlı matching state (aynı frame'deki person'ların çakışmasını önlemek için)
        # {camera_id: {frame_id: {matched_person_id: True}}}
        self.frame_matches: Dict[str, Dict[str, Dict[str, bool]]] = defaultdict(lambda: defaultdict(dict))
        
        # Son kontrol zamanı
        self.last_cleanup_time = time.time()
        
        logger.info("✅ ViolationTracker initialized with cooldown: %d seconds, IoU threshold: %.2f", 
                   cooldown_period, iou_threshold)
    
    def calculate_iou(self, bbox1: List[float], bbox2: List[float]) -> float:
        """
        Intersection over Union (IoU) hesapla
        
        Args:
            bbox1: [x1, y1, x2, y2]
            bbox2: [x1, y1, x2, y2]
            
        Returns:
            IoU değeri (0.0-1.0)
        """
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Intersection hesapla
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Union hesapla
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def match_person_with_iou(self, person_bbox: List[float], camera_id: str, current_time: float, frame_id: Optional[str] = None) -> str:
        """
        IoU-based person matching - Önceki frame'deki person'larla eşleştir
        Greedy matching: Aynı frame'deki person'lar birbirleriyle çakışmaz
        
        Args:
            person_bbox: Mevcut frame'deki person bbox [x1, y1, x2, y2]
            camera_id: Kamera ID
            current_time: Mevcut zaman (timestamp)
            frame_id: Frame ID (aynı frame'deki person'ları ayırt etmek için, opsiyonel)
            
        Returns:
            Person ID (eşleşme varsa mevcut, yoksa yeni)
        """
        camera_tracking = self.person_tracking[camera_id]
        
        # Frame ID yoksa timestamp kullan (yaklaşık frame bazlı gruplama)
        if frame_id is None:
            frame_id = f"frame_{int(current_time * 10)}"  # 0.1 saniye hassasiyet
        
        # Bu frame'de daha önce match edilmiş person'ları al
        matched_in_frame = self.frame_matches[camera_id][frame_id]
        
        # Eğer önceki frame'de person yoksa, yeni person oluştur
        if not camera_tracking:
            person_id = self._generate_new_person_id(camera_id)
            camera_tracking[person_id] = {
                'bbox': person_bbox.copy(),
                'last_seen': current_time
            }
            matched_in_frame[person_id] = True
            return person_id
        
        # En yüksek IoU'yu bul (daha önce match edilmemiş person'larla)
        best_match_id = None
        best_iou = 0.0
        
        for person_id, tracking_data in camera_tracking.items():
            # Eğer bu frame'de zaten match edilmişse, skip et
            if person_id in matched_in_frame:
                continue
            
            prev_bbox = tracking_data['bbox']
            iou = self.calculate_iou(person_bbox, prev_bbox)
            
            if iou > best_iou and iou >= self.iou_threshold:
                best_iou = iou
                best_match_id = person_id
        
        # Eşleşme bulundu
        if best_match_id:
            # Tracking state'i güncelle
            camera_tracking[best_match_id]['bbox'] = person_bbox.copy()
            camera_tracking[best_match_id]['last_seen'] = current_time
            matched_in_frame[best_match_id] = True
            logger.debug(f"✅ Person matched via IoU: {best_match_id} (IoU: {best_iou:.3f})")
            return best_match_id
        
        # Eşleşme yok - yeni person
        person_id = self._generate_new_person_id(camera_id)
        camera_tracking[person_id] = {
            'bbox': person_bbox.copy(),
            'last_seen': current_time
        }
        matched_in_frame[person_id] = True
        logger.debug(f"🆕 New person created: {person_id} (camera: {camera_id}, IoU threshold not met)")
        return person_id
    
    def _generate_new_person_id(self, camera_id: str) -> str:
        """
        Yeni person ID oluştur (fallback - hash-based)
        
        Args:
            camera_id: Kamera ID
            
        Returns:
            Yeni person ID (örn: "PERSON_ABC123")
        """
        self.next_person_id_counter[camera_id] += 1
        counter = self.next_person_id_counter[camera_id]
        
        # Hash-based ID (backward compatibility için)
        import hashlib
        hash_input = f"{camera_id}_{counter}_{time.time()}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()
        
        return f"PERSON_{hash_value}"
    
    def generate_person_hash(self, person_bbox: List[float], camera_id: str) -> str:
        """
        Kişi için unique hash oluştur (bbox konumuna göre) - FALLBACK METOD
        IoU-based matching kullanılamazsa bu metod kullanılır
        
        Args:
            person_bbox: [x1, y1, x2, y2]
            camera_id: Kamera ID
            
        Returns:
            Person hash (örn: "PERSON_ABC123")
        """
        # Bbox merkez noktası
        center_x = (person_bbox[0] + person_bbox[2]) / 2
        center_y = (person_bbox[1] + person_bbox[3]) / 2
        
        # Hash oluştur (kamera + konum) - Daha toleranslı grid (100 piksel)
        hash_input = f"{camera_id}_{int(center_x/100)}_{int(center_y/100)}"
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
        IoU-based person tracking kullanarak aynı kişiyi takip eder
        
        Args:
            camera_id: Kamera ID
            company_id: Şirket ID
            person_bbox: Kişi bounding box [x1, y1, x2, y2]
            violations: İhlal listesi ['Baret eksik', 'Yelek eksik']
            frame_snapshot: Frame görüntüsü (opsiyonel)
            
        Returns:
            (new_violations, ended_violations)
        """
        with self._lock:
            return self._process_detection_locked(
                camera_id, company_id, person_bbox, violations, frame_snapshot
            )

    def _process_detection_locked(
        self,
        camera_id: str,
        company_id: str,
        person_bbox: List[float],
        violations: List[str],
        frame_snapshot: Optional[bytes] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        current_time = time.time()
        
        try:
            person_id = self.match_person_with_iou(person_bbox, camera_id, current_time)
            logger.debug(f"🎯 Person matched: {person_id} (camera: {camera_id})")
        except Exception as e:
            logger.warning(f"⚠️ IoU matching failed, using hash-based fallback: {e}")
            person_id = self.generate_person_hash(person_bbox, camera_id)
            logger.debug(f"📝 Fallback person ID: {person_id}")
        
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
        
        # ── YENİ İHLALLERİ GRUPLAYARAK KONTROL ET ──
        newly_detected_types = []
        for v_type in current_violations:
            if v_type not in person_violations:
                newly_detected_types.append(v_type)
                person_violations[v_type] = current_time

        if newly_detected_types:
            # Tespit edilen tüm YENİ ihlalleri tek bir event olarak kaydet
            # Eğer kişi zaten bir ihlal içindeyse (person_violations'da eskiler varsa), 
            # kullanıcı hepsini birden mi görmek istiyor yoksa sadece yeni başlayanları mı?
            # Kullanıcı "1 tane screenshot" dediği için tüm AKTİF (yeni+eski) ihlalleri birleştiriyoruz.
            all_active_types = sorted(list(person_violations.keys()))
            combined_type = ",".join(all_active_types)
            
            # Event ID: VIO_CAM_PERSON_TIMESTAMP
            event_id = f"VIO_{camera_id}_{person_id}_{int(current_time)}"
            
            # Şiddeti belirle (içlerindeki en yükseği)
            top_severity = 'info'
            for t in all_active_types:
                s = self._calculate_severity(t)
                if s == 'critical': top_severity = 'critical'; break
                if s == 'warning': top_severity = 'warning'

            event_data = {
                'event_id': event_id,
                'company_id': company_id,
                'camera_id': camera_id,
                'person_id': person_id,
                'violation_type': combined_type, # Virgülle birleştirilmiş
                'start_time': current_time,
                'start_timestamp': datetime.fromtimestamp(current_time).isoformat(),
                'person_bbox': person_bbox,
                'status': 'active',
                'severity': top_severity
            }
            
            self.violation_history[event_id] = event_data
            new_violations.append(event_data)
            logger.info(f"🚨 GROUPED VIOLATION: {combined_type} for {person_id} on {camera_id}")
        
        # ── BİTEN İHLALLERİ KONTROL ET ──
        # Bu kısımda her bir ihlal tipinin ayrı ayrı bitmesini takip ediyoruz.
        # Eğer hepsi biterse event 'resolved' olur gibi bir mantık kurabiliriz 
        # ama şimdilik mevcut bitiş mantığını minimum değişiklikle koruyorum.
        for violation_type in list(person_violations.keys()):
            if violation_type not in current_violations:
                start_time = person_violations[violation_type]
                duration = current_time - start_time
                
                # Bu tipe ait aktif event'i bul (artık combined_type içinde olabilir)
                for eid, event in self.violation_history.items():
                    if (event['person_id'] == person_id and 
                        violation_type in event['violation_type'].split(',') and
                        event['status'] == 'active'):
                        
                        # Eğer bu event içindeki TÜM tipler bittiyse kapat
                        remaining_types = [t for t in event['violation_type'].split(',') if t in current_violations]
                        if not remaining_types:
                            event['end_time'] = current_time
                            event['end_timestamp'] = datetime.fromtimestamp(current_time).isoformat()
                            event['duration_seconds'] = int(current_time - event['start_time'])
                            event['status'] = 'resolved'
                            ended_violations.append(event)
                            logger.info(f"✅ GROUPED VIOLATION RESOLVED: {event['violation_type']} for {person_id}")
                
                del person_violations[violation_type]
        
        # Periyodik cleanup (her 60 saniyede bir)
        if current_time - self.last_cleanup_time > 60:
            self._cleanup_stale_violations()
            self._cleanup_stale_persons(current_time)
            self._cleanup_old_frame_matches(current_time)
            self.last_cleanup_time = current_time
        
        return new_violations, ended_violations
    
    def _cleanup_stale_violations(self):
        """Uzun süredir güncellenmemiş ihlalleri temizle (lock already held by caller or standalone)"""
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
    
    def _cleanup_stale_persons(self, current_time: float):
        """
        Uzun süredir görünmeyen person'ları tracking state'den temizle
        
        Args:
            current_time: Mevcut zaman (timestamp)
        """
        cleanup_count = 0
        
        for camera_id in list(self.person_tracking.keys()):
            camera_tracking = self.person_tracking[camera_id]
            
            for person_id in list(camera_tracking.keys()):
                tracking_data = camera_tracking[person_id]
                last_seen = tracking_data.get('last_seen', 0)
                
                # Person timeout süresinden uzun süredir görünmüyorsa sil
                if current_time - last_seen > self.person_timeout:
                    # Eğer aktif violation varsa, person'ı silme (violation devam edebilir)
                    has_active_violations = (
                        camera_id in self.active_violations and
                        person_id in self.active_violations[camera_id] and
                        len(self.active_violations[camera_id][person_id]) > 0
                    )
                    
                    if not has_active_violations:
                        del camera_tracking[person_id]
                        cleanup_count += 1
            
            # Kamera için hiç person kalmadıysa temizle
            if not camera_tracking:
                del self.person_tracking[camera_id]
        
        if cleanup_count > 0:
            logger.debug(f"🧹 Cleaned up {cleanup_count} stale persons from tracking")
    
    def _cleanup_old_frame_matches(self, current_time: float):
        """
        Eski frame match kayıtlarını temizle (memory leak önleme)
        
        Args:
            current_time: Mevcut zaman (timestamp)
        """
        # Frame ID'ler timestamp bazlı olduğu için, 10 saniyeden eski olanları temizle
        cleanup_count = 0
        
        for camera_id in list(self.frame_matches.keys()):
            camera_frames = self.frame_matches[camera_id]
            
            for frame_id in list(camera_frames.keys()):
                # Frame ID'den timestamp çıkar (format: "frame_123456789")
                try:
                    if frame_id.startswith("frame_"):
                        frame_timestamp = int(frame_id.split("_")[1]) / 10.0  # 0.1 saniye birimine geri çevir
                        if current_time - frame_timestamp > 10.0:  # 10 saniyeden eski
                            del camera_frames[frame_id]
                            cleanup_count += 1
                except (ValueError, IndexError):
                    # Format hatası varsa direkt sil
                    del camera_frames[frame_id]
                    cleanup_count += 1
            
            # Kamera için hiç frame kalmadıysa temizle
            if not camera_frames:
                del self.frame_matches[camera_id]
        
        if cleanup_count > 0:
            logger.debug(f"🧹 Cleaned up {cleanup_count} old frame match records")
    
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
        with self._lock:
            return self._get_active_violations_locked(camera_id)

    def _get_active_violations_locked(self, camera_id: Optional[str] = None) -> List[Dict]:
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
