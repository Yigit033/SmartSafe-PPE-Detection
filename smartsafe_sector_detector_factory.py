#!/usr/bin/env python3
"""
SmartSafe AI - Enhanced Sektörel Detection Factory
Hibrit PPE detection sistemi ile entegre edilmiş sektörel detector factory
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import cv2
import logging
from smartsafe_sector_manager import SmartSafeSectorManager
from smartsafe_construction_system import ConstructionPPEDetector, ConstructionPPEConfig

# Hibrit sistem import
try:
    from utils.hybrid_ppe_system import HybridPPESystem
    HYBRID_SYSTEM_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("✅ Hibrit PPE sistemi yüklendi")
except ImportError as e:
    HYBRID_SYSTEM_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ Hibrit PPE sistemi yüklenemedi: {e}")

class BaseSectorDetector(ABC):
    """Sektörel detector için temel sınıf"""
    
    def __init__(self, sector_id: str, company_id: str = None):
        self.sector_id = sector_id
        self.company_id = company_id
        self.sector_manager = SmartSafeSectorManager()
        self.sector_config = self.sector_manager.get_sector_config(sector_id)
        self.model = None
        
        # Hibrit sistem entegrasyonu
        if HYBRID_SYSTEM_AVAILABLE:
            self.hybrid_system = HybridPPESystem()
            self.hybrid_system.initialize_system()
            self.use_hybrid = True
            logger.info(f"✅ Hibrit sistem aktif - Sektör: {sector_id}")
        else:
            self.use_hybrid = False
            logger.info(f"⚠️ Hibrit sistem devre dışı - Sektör: {sector_id}")
        
        self.load_model()
    
    @abstractmethod
    def load_model(self):
        """Sektöre özel model yükle"""
        pass
    
    def detect_ppe(self, image: np.ndarray, camera_id: str) -> Dict:
        """PPE tespiti yap - Hibrit sistem ile entegre"""
        if self.use_hybrid and self.company_id:
            # Hibrit sistem kullan
            try:
                result = self.hybrid_system.process_detection(
                    image=image,
                    company_id=self.company_id,
                    camera_id=camera_id,
                    confidence=0.3
                )
                
                # Mevcut format'a çevir
                return self.convert_hybrid_to_legacy_format(result)
                
            except Exception as e:
                logger.error(f"❌ Hibrit sistem hatası: {e}, fallback kullanılacak")
                return self.detect_ppe_fallback(image, camera_id)
        else:
            # Eski sistemi kullan
            return self.detect_ppe_fallback(image, camera_id)
    
    @abstractmethod
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """Fallback PPE tespiti (eski sistem)"""
        pass
    
    def convert_hybrid_to_legacy_format(self, hybrid_result) -> Dict:
        """Hibrit sonucu eski format'a çevir"""
        try:
            # Hibrit detection'ları eski format'a çevir
            detections = []
            for detection in hybrid_result.sector_detections:
                detections.append({
                    'bbox': detection.bbox,
                    'confidence': detection.confidence,
                    'class_name': detection.sector_class  # Sektörel sınıf kullan
                })
            
            # Compliance analizi
            compliance = hybrid_result.compliance_result
            
            analysis = {
                'total_people': compliance.person_count,
                'compliant_people': compliance.compliant_count,
                'violation_people': compliance.violation_count,
                'compliance_rate': compliance.compliance_rate * 100,  # Yüzde olarak
                'violations': [],
                'sector_specific': {
                    f'{self.sector_id}_violations': [],
                    'critical_violations': [],
                    'penalty_amount': 0.0,
                    'detected_ppe': list(compliance.detected_ppe.keys()),
                    'missing_ppe': compliance.missing_ppe
                }
            }
            
            # İhlal detayları
            if compliance.violation_count > 0:
                for i in range(compliance.violation_count):
                    violation = {
                        'person_id': f'{self.sector_id.upper()[0]}W{i+1:03d}',
                        'missing_ppe': compliance.missing_ppe,
                        'risk_level': 'HIGH' if len(compliance.missing_ppe) >= 2 else 'MEDIUM'
                    }
                    analysis['violations'].append(violation)
                    analysis['sector_specific'][f'{self.sector_id}_violations'].append({
                        'type': f'{self.sector_id.title()} Güvenlik İhlali',
                        'details': f"Eksik PPE: {', '.join(compliance.missing_ppe)}",
                        'risk_level': violation['risk_level']
                    })
            
            return {
                'timestamp': hybrid_result.timestamp,
                'camera_id': hybrid_result.camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': hybrid_result.success,
                'sector': hybrid_result.sector,
                'hybrid_enhanced': True,  # Hibrit sistem kullanıldığını belirt
                'performance_metrics': hybrid_result.performance_metrics
            }
            
        except Exception as e:
            logger.error(f"❌ Hibrit format çevirme hatası: {e}")
            return self.create_fallback_result(None, hybrid_result.camera_id)
    
    def get_company_ppe_config(self, company_id: str) -> Dict:
        """Şirketin PPE konfigürasyonunu al"""
        try:
            from smartsafe_multitenant_system import MultiTenantDatabase
            db = MultiTenantDatabase()
            
            import sqlite3
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT required_ppe FROM companies WHERE company_id = ?
            ''', (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                import json
                ppe_config = json.loads(result[0])
                
                # Yeni format kontrolü
                if isinstance(ppe_config, dict) and 'required' in ppe_config:
                    return ppe_config
                else:
                    # Eski format - geriye uyumluluk
                    return {'required': ppe_config, 'optional': []}
            else:
                # Varsayılan sektör PPE'leri
                return self.get_default_sector_ppe()
                
        except Exception as e:
            logger.error(f"PPE config alma hatası: {e}")
            return self.get_default_sector_ppe()
    
    def get_default_sector_ppe(self) -> Dict:
        """Sektörün varsayılan PPE konfigürasyonu"""
        defaults = {
            'construction': {
                'required': ['helmet', 'safety_vest', 'safety_shoes'],
                'optional': ['gloves', 'glasses']
            },
            'food': {
                'required': ['hairnet', 'face_mask', 'apron'],
                'optional': ['gloves', 'safety_shoes']
            },
            'chemical': {
                'required': ['gloves', 'glasses', 'face_mask', 'safety_suit'],
                'optional': []
            },
            'manufacturing': {
                'required': ['helmet', 'safety_vest', 'gloves', 'safety_shoes'],
                'optional': []
            },
            'warehouse': {
                'required': ['safety_vest', 'safety_shoes'],
                'optional': ['helmet', 'gloves']
            }
        }
        
        return defaults.get(self.sector_id, {'required': [], 'optional': []})
    
    def create_fallback_result(self, image: np.ndarray, camera_id: str) -> Dict:
        """Model yüklenemediğinde fallback sonuç"""
        return {
            'timestamp': datetime.now(),
            'camera_id': camera_id,
            'detections': [],
            'analysis': {
                'total_people': 0,
                'compliant_people': 0,
                'violation_people': 0,
                'compliance_rate': 0.0,
                'violations': [],
                'sector_specific': {
                    f'{self.sector_id}_violations': [],
                    'critical_violations': [],
                    'penalty_amount': 0.0
                }
            },
            'success': False,
            'sector': self.sector_id,
            'error': 'Model yüklenemedi'
        }
    
    def boxes_overlap(self, box1, box2, threshold=0.1):
        """İki kutunun örtüşüp örtüşmediğini kontrol et"""
        x1, y1, x2, y2 = box1
        x3, y3, x4, y4 = box2
        
        # Örtüşme alanı hesapla
        overlap_x = max(0, min(x2, x4) - max(x1, x3))
        overlap_y = max(0, min(y2, y4) - max(y1, y3))
        overlap_area = overlap_x * overlap_y
        
        # Box1 alanı
        box1_area = (x2 - x1) * (y2 - y1)
        
        return overlap_area > threshold * box1_area if box1_area > 0 else False

class ConstructionSectorDetector(BaseSectorDetector):
    """İnşaat sektörü PPE detector"""
    
    def __init__(self, company_id: str = None):
        super().__init__('construction', company_id)
    
    def load_model(self):
        """İnşaat sektörü modeli yükle"""
        try:
            config = ConstructionPPEConfig()
            self.detector = ConstructionPPEDetector(config)
            logger.info("✅ İnşaat sektörü detector yüklendi")
        except Exception as e:
            logger.error(f"❌ İnşaat detector yüklenemedi: {e}")
            self.detector = None
    
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """İnşaat sektörü PPE tespiti - eski sistem"""
        if self.detector:
            return self.detector.detect_construction_ppe(image, camera_id)
        else:
            return self.create_fallback_result(image, camera_id)

class FoodSectorDetector(BaseSectorDetector):
    """Gıda sektörü PPE detector"""
    
    def __init__(self, company_id: str = None):
        super().__init__('food', company_id)
    
    def load_model(self):
        """Gıda sektörü modeli yükle"""
        try:
            # Gıda sektörü için YOLOv8 modeli
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            logger.info("✅ Gıda sektörü detector yüklendi")
        except Exception as e:
            logger.error(f"❌ Gıda detector yüklenemedi: {e}")
            self.model = None
    
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """Gıda sektörü PPE tespiti - eski sistem"""
        try:
            if self.model is None:
                return self.create_fallback_result(image, camera_id)
            
            # Model ile tespit
            results = self.model(image, conf=0.65, verbose=False)
            
            # Tespit edilen nesneleri işle
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Sınıf adını al
                        if hasattr(self.model, 'names'):
                            class_name = self.model.names[class_id]
                        else:
                            # Gıda sektörü sınıf mapping
                            food_classes = {
                                0: 'person', 1: 'hairnet', 2: 'face_mask_medical', 
                                3: 'apron', 4: 'gloves', 5: 'shoes'
                            }
                            class_name = food_classes.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            # Gıda sektörü analizi
            analysis = self.analyze_food_compliance(detections, camera_id)
            
            return {
                'timestamp': datetime.now(),
                'camera_id': camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': True,
                'sector': 'food'
            }
            
        except Exception as e:
            logger.error(f"Gıda detection hatası: {e}")
            return self.create_fallback_result(image, camera_id)
    
    def analyze_food_compliance(self, detections: List[Dict], camera_id: str) -> Dict:
        """Gıda sektörü uygunluk analizi"""
        people = [d for d in detections if d['class_name'] == 'person']
        
        # PPE'leri kategorize et
        detected_ppe = {
            'hairnet': [d for d in detections if 'hairnet' in d['class_name']],
            'face_mask': [d for d in detections if 'face_mask' in d['class_name'] or 'mask' in d['class_name']],
            'apron': [d for d in detections if 'apron' in d['class_name']],
            'gloves': [d for d in detections if 'gloves' in d['class_name']],
            'shoes': [d for d in detections if 'shoes' in d['class_name']]
        }
        
        analysis = {
            'total_people': len(people),
            'compliant_people': 0,
            'violation_people': 0,
            'compliance_rate': 0.0,
            'violations': [],
            'sector_specific': {
                'hygiene_violations': [],
                'critical_violations': [],
                'penalty_amount': 0.0
            }
        }
        
        if not people:
            return analysis
        
        for i, person in enumerate(people):
            person_bbox = person['bbox']
            
            # Gıda sektörü zorunlu PPE kontrolü
            has_hairnet = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['hairnet'])
            has_face_mask = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['face_mask'])
            has_apron = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['apron'])
            
            # Opsiyonel PPE
            has_gloves = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['gloves'])
            has_shoes = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['shoes'])
            
            missing_ppe = []
            if not has_hairnet:
                missing_ppe.append('hairnet')
            if not has_face_mask:
                missing_ppe.append('face_mask')
            if not has_apron:
                missing_ppe.append('apron')
            
            # Uygunluk kontrolü
            is_compliant = len(missing_ppe) == 0
            
            if is_compliant:
                analysis['compliant_people'] += 1
            else:
                analysis['violation_people'] += 1
                
                # Gıda sektörü özel ihlal türleri
                violation_details = {
                    'person_id': f'FW{i+1:03d}',
                    'missing_ppe': missing_ppe,
                    'hygiene_risk': 'HIGH' if len(missing_ppe) >= 2 else 'MEDIUM',
                    'penalty': sum(self.sector_config.mandatory_ppe[ppe]['penalty_per_violation'] 
                                 for ppe in missing_ppe if ppe in self.sector_config.mandatory_ppe)
                }
                
                analysis['violations'].append(violation_details)
                analysis['sector_specific']['hygiene_violations'].append({
                    'type': 'Hijyen İhlali',
                    'details': f"Eksik PPE: {', '.join(missing_ppe)}",
                    'risk_level': violation_details['hygiene_risk']
                })
                
                analysis['sector_specific']['penalty_amount'] += violation_details['penalty']
        
        # Uygunluk oranı hesapla
        analysis['compliance_rate'] = (analysis['compliant_people'] / analysis['total_people']) * 100
        
        return analysis

class ChemicalSectorDetector(BaseSectorDetector):
    """Kimya sektörü PPE detector"""
    
    def __init__(self, company_id: str = None):
        super().__init__('chemical', company_id)
    
    def load_model(self):
        """Kimya sektörü modeli yükle"""
        try:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            logger.info("✅ Kimya sektörü detector yüklendi")
        except Exception as e:
            logger.error(f"❌ Kimya detector yüklenemedi: {e}")
            self.model = None
    
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """Kimya sektörü PPE tespiti - eski sistem"""
        try:
            if self.model is None:
                return self.create_fallback_result(image, camera_id)
            
            # Model ile tespit
            results = self.model(image, conf=0.7, verbose=False)
            
            # Tespit edilen nesneleri işle
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Kimya sektörü sınıf mapping
                        chemical_classes = {
                            0: 'person', 1: 'gloves', 2: 'glasses', 
                            3: 'face_mask_medical', 4: 'safety_suit', 
                            5: 'helmet', 6: 'shoes'
                        }
                        class_name = chemical_classes.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            # Kimya sektörü analizi
            analysis = self.analyze_chemical_compliance(detections, camera_id)
            
            return {
                'timestamp': datetime.now(),
                'camera_id': camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': True,
                'sector': 'chemical'
            }
            
        except Exception as e:
            logger.error(f"Kimya detection hatası: {e}")
            return self.create_fallback_result(image, camera_id)
    
    def analyze_chemical_compliance(self, detections: List[Dict], camera_id: str) -> Dict:
        """Kimya sektörü uygunluk analizi"""
        people = [d for d in detections if d['class_name'] == 'person']
        
        # PPE'leri kategorize et
        detected_ppe = {
            'gloves': [d for d in detections if 'gloves' in d['class_name']],
            'glasses': [d for d in detections if 'glasses' in d['class_name']],
            'face_mask': [d for d in detections if 'face_mask' in d['class_name'] or 'mask' in d['class_name']],
            'safety_suit': [d for d in detections if 'safety_suit' in d['class_name'] or 'suit' in d['class_name']],
            'helmet': [d for d in detections if 'helmet' in d['class_name']],
            'shoes': [d for d in detections if 'shoes' in d['class_name']]
        }
        
        analysis = {
            'total_people': len(people),
            'compliant_people': 0,
            'violation_people': 0,
            'compliance_rate': 0.0,
            'violations': [],
            'sector_specific': {
                'chemical_violations': [],
                'critical_violations': [],
                'penalty_amount': 0.0
            }
        }
        
        if not people:
            return analysis
        
        for i, person in enumerate(people):
            person_bbox = person['bbox']
            
            # Kimya sektörü zorunlu PPE kontrolü (tümü kritik)
            has_gloves = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['gloves'])
            has_glasses = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['glasses'])
            has_face_mask = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['face_mask'])
            has_safety_suit = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['safety_suit'])
            
            missing_ppe = []
            if not has_gloves:
                missing_ppe.append('gloves')
            if not has_glasses:
                missing_ppe.append('glasses')
            if not has_face_mask:
                missing_ppe.append('face_mask')
            if not has_safety_suit:
                missing_ppe.append('safety_suit')
            
            # Uygunluk kontrolü - kimya sektöründe tüm PPE zorunlu
            is_compliant = len(missing_ppe) == 0
            
            if is_compliant:
                analysis['compliant_people'] += 1
            else:
                analysis['violation_people'] += 1
                
                # Kimya sektörü özel ihlal türleri
                violation_details = {
                    'person_id': f'CW{i+1:03d}',
                    'missing_ppe': missing_ppe,
                    'chemical_risk': 'CRITICAL' if len(missing_ppe) >= 2 else 'HIGH',
                    'penalty': sum(self.sector_config.mandatory_ppe[ppe]['penalty_per_violation'] 
                                 for ppe in missing_ppe if ppe in self.sector_config.mandatory_ppe)
                }
                
                analysis['violations'].append(violation_details)
                analysis['sector_specific']['chemical_violations'].append({
                    'type': 'Kimyasal Güvenlik İhlali',
                    'details': f"Eksik PPE: {', '.join(missing_ppe)}",
                    'risk_level': violation_details['chemical_risk']
                })
                
                analysis['sector_specific']['penalty_amount'] += violation_details['penalty']
        
        # Uygunluk oranı hesapla
        analysis['compliance_rate'] = (analysis['compliant_people'] / analysis['total_people']) * 100
        
        return analysis

class ManufacturingSectorDetector(BaseSectorDetector):
    """İmalat sektörü PPE detector"""
    
    def __init__(self, company_id: str = None):
        super().__init__('manufacturing', company_id)
    
    def load_model(self):
        """İmalat sektörü modeli yükle"""
        try:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            logger.info("✅ İmalat sektörü detector yüklendi")
        except Exception as e:
            logger.error(f"❌ İmalat detector yüklenemedi: {e}")
            self.model = None
    
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """İmalat sektörü PPE tespiti - eski sistem"""
        try:
            if self.model is None:
                return self.create_fallback_result(image, camera_id)
            
            # Model ile tespit
            results = self.model(image, conf=0.65, verbose=False)
            
            # Tespit edilen nesneleri işle
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # İmalat sektörü sınıf mapping
                        manufacturing_classes = {
                            0: 'person', 1: 'helmet', 2: 'safety_vest', 
                            3: 'gloves', 4: 'shoes', 5: 'glasses', 6: 'earmuffs'
                        }
                        class_name = manufacturing_classes.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            # İmalat sektörü analizi
            analysis = self.analyze_manufacturing_compliance(detections, camera_id)
            
            return {
                'timestamp': datetime.now(),
                'camera_id': camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': True,
                'sector': 'manufacturing'
            }
            
        except Exception as e:
            logger.error(f"İmalat detection hatası: {e}")
            return self.create_fallback_result(image, camera_id)
    
    def analyze_manufacturing_compliance(self, detections: List[Dict], camera_id: str) -> Dict:
        """İmalat sektörü uygunluk analizi"""
        people = [d for d in detections if d['class_name'] == 'person']
        
        # PPE'leri kategorize et
        detected_ppe = {
            'helmet': [d for d in detections if 'helmet' in d['class_name']],
            'safety_vest': [d for d in detections if 'safety_vest' in d['class_name'] or 'vest' in d['class_name']],
            'gloves': [d for d in detections if 'gloves' in d['class_name']],
            'shoes': [d for d in detections if 'shoes' in d['class_name']],
            'glasses': [d for d in detections if 'glasses' in d['class_name']],
            'earmuffs': [d for d in detections if 'earmuffs' in d['class_name']]
        }
        
        analysis = {
            'total_people': len(people),
            'compliant_people': 0,
            'violation_people': 0,
            'compliance_rate': 0.0,
            'violations': [],
            'sector_specific': {
                'manufacturing_violations': [],
                'critical_violations': [],
                'penalty_amount': 0.0
            }
        }
        
        if not people:
            return analysis
        
        for i, person in enumerate(people):
            person_bbox = person['bbox']
            
            # İmalat sektörü zorunlu PPE kontrolü
            has_helmet = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['helmet'])
            has_safety_vest = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['safety_vest'])
            has_gloves = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['gloves'])
            has_shoes = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['shoes'])
            
            missing_ppe = []
            if not has_helmet:
                missing_ppe.append('helmet')
            if not has_safety_vest:
                missing_ppe.append('safety_vest')
            if not has_gloves:
                missing_ppe.append('gloves')
            if not has_shoes:
                missing_ppe.append('shoes')
            
            # Uygunluk kontrolü
            is_compliant = len(missing_ppe) == 0
            
            if is_compliant:
                analysis['compliant_people'] += 1
            else:
                analysis['violation_people'] += 1
                
                # İmalat sektörü özel ihlal türleri
                violation_details = {
                    'person_id': f'MW{i+1:03d}',
                    'missing_ppe': missing_ppe,
                    'manufacturing_risk': 'HIGH' if len(missing_ppe) >= 3 else 'MEDIUM',
                    'penalty': sum(self.sector_config.mandatory_ppe[ppe]['penalty_per_violation'] 
                                 for ppe in missing_ppe if ppe in self.sector_config.mandatory_ppe)
                }
                
                analysis['violations'].append(violation_details)
                analysis['sector_specific']['manufacturing_violations'].append({
                    'type': 'İmalat Güvenlik İhlali',
                    'details': f"Eksik PPE: {', '.join(missing_ppe)}",
                    'risk_level': violation_details['manufacturing_risk']
                })
                
                analysis['sector_specific']['penalty_amount'] += violation_details['penalty']
        
        # Uygunluk oranı hesapla
        analysis['compliance_rate'] = (analysis['compliant_people'] / analysis['total_people']) * 100
        
        return analysis

class WarehouseSectorDetector(BaseSectorDetector):
    """Depo/Lojistik sektörü PPE detector"""
    
    def __init__(self, company_id: str = None):
        super().__init__('warehouse', company_id)
    
    def load_model(self):
        """Depo sektörü modeli yükle"""
        try:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            logger.info("✅ Depo sektörü detector yüklendi")
        except Exception as e:
            logger.error(f"❌ Depo detector yüklenemedi: {e}")
            self.model = None
    
    def detect_ppe_fallback(self, image: np.ndarray, camera_id: str) -> Dict:
        """Depo sektörü PPE tespiti - eski sistem"""
        try:
            if self.model is None:
                return self.create_fallback_result(image, camera_id)
            
            # Model ile tespit
            results = self.model(image, conf=0.6, verbose=False)
            
            # Tespit edilen nesneleri işle
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Depo sektörü sınıf mapping
                        warehouse_classes = {
                            0: 'person', 1: 'helmet', 2: 'safety_vest', 
                            3: 'shoes', 4: 'gloves'
                        }
                        class_name = warehouse_classes.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            # Depo sektörü analizi
            analysis = self.analyze_warehouse_compliance(detections, camera_id)
            
            return {
                'timestamp': datetime.now(),
                'camera_id': camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': True,
                'sector': 'warehouse'
            }
            
        except Exception as e:
            logger.error(f"Depo detection hatası: {e}")
            return self.create_fallback_result(image, camera_id)
    
    def analyze_warehouse_compliance(self, detections: List[Dict], camera_id: str) -> Dict:
        """Depo sektörü uygunluk analizi"""
        people = [d for d in detections if d['class_name'] == 'person']
        
        # PPE'leri kategorize et
        detected_ppe = {
            'helmet': [d for d in detections if 'helmet' in d['class_name']],
            'safety_vest': [d for d in detections if 'safety_vest' in d['class_name'] or 'vest' in d['class_name']],
            'shoes': [d for d in detections if 'shoes' in d['class_name']],
            'gloves': [d for d in detections if 'gloves' in d['class_name']]
        }
        
        analysis = {
            'total_people': len(people),
            'compliant_people': 0,
            'violation_people': 0,
            'compliance_rate': 0.0,
            'violations': [],
            'sector_specific': {
                'warehouse_violations': [],
                'critical_violations': [],
                'penalty_amount': 0.0
            }
        }
        
        if not people:
            return analysis
        
        for i, person in enumerate(people):
            person_bbox = person['bbox']
            
            # Depo sektörü zorunlu PPE kontrolü (yelek ve ayakkabı)
            has_safety_vest = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['safety_vest'])
            has_shoes = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['shoes'])
            
            # Opsiyonel PPE
            has_helmet = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['helmet'])
            has_gloves = any(self.boxes_overlap(person_bbox, ppe['bbox']) for ppe in detected_ppe['gloves'])
            
            missing_ppe = []
            if not has_safety_vest:
                missing_ppe.append('safety_vest')
            if not has_shoes:
                missing_ppe.append('shoes')
            
            # Uygunluk kontrolü - sadece yelek ve ayakkabı zorunlu
            is_compliant = len(missing_ppe) == 0
            
            if is_compliant:
                analysis['compliant_people'] += 1
            else:
                analysis['violation_people'] += 1
                
                # Depo sektörü özel ihlal türleri
                violation_details = {
                    'person_id': f'WW{i+1:03d}',
                    'missing_ppe': missing_ppe,
                    'warehouse_risk': 'MEDIUM' if len(missing_ppe) >= 2 else 'LOW',
                    'penalty': sum(self.sector_config.mandatory_ppe[ppe]['penalty_per_violation'] 
                                 for ppe in missing_ppe if ppe in self.sector_config.mandatory_ppe)
                }
                
                analysis['violations'].append(violation_details)
                analysis['sector_specific']['warehouse_violations'].append({
                    'type': 'Depo Güvenlik İhlali',
                    'details': f"Eksik PPE: {', '.join(missing_ppe)}",
                    'risk_level': violation_details['warehouse_risk']
                })
                
                analysis['sector_specific']['penalty_amount'] += violation_details['penalty']
        
        # Uygunluk oranı hesapla
        analysis['compliance_rate'] = (analysis['compliant_people'] / analysis['total_people']) * 100
        
        return analysis

class SectorDetectorFactory:
    """Sektöre göre doğru detector'ı döndüren factory"""
    
    _detectors = {}
    
    @classmethod
    def get_detector(cls, sector_id: str, company_id: str = None) -> Optional[BaseSectorDetector]:
        """Sektöre göre detector getir"""
        # Şirket bazlı cache key
        cache_key = f"{sector_id}_{company_id}" if company_id else sector_id
        
        if cache_key not in cls._detectors:
            try:
                if sector_id == 'construction':
                    cls._detectors[cache_key] = ConstructionSectorDetector(company_id)
                elif sector_id == 'food':
                    cls._detectors[cache_key] = FoodSectorDetector(company_id)
                elif sector_id == 'chemical':
                    cls._detectors[cache_key] = ChemicalSectorDetector(company_id)
                elif sector_id == 'manufacturing':
                    cls._detectors[cache_key] = ManufacturingSectorDetector(company_id)
                elif sector_id == 'warehouse':
                    cls._detectors[cache_key] = WarehouseSectorDetector(company_id)
                else:
                    logger.warning(f"Bilinmeyen sektör: {sector_id}, construction detector kullanılacak")
                    cls._detectors[cache_key] = ConstructionSectorDetector(company_id)
            except Exception as e:
                logger.error(f"Detector oluşturma hatası ({sector_id}): {e}")
                return None
        
        return cls._detectors[cache_key]
    
    @classmethod
    def list_supported_sectors(cls) -> List[str]:
        """Desteklenen sektörleri listele"""
        return ['construction', 'food', 'chemical', 'manufacturing', 'warehouse']
    
    @classmethod
    def clear_cache(cls):
        """Detector cache'ini temizle"""
        cls._detectors.clear()
        logger.info("Detector cache temizlendi")

# Kullanım örneği
if __name__ == "__main__":
    # Test
    factory = SectorDetectorFactory()
    
    # Gıda sektörü detector
    food_detector = factory.get_detector('food')
    if food_detector:
        print("✅ Gıda sektörü detector hazır")
    
    # Kimya sektörü detector
    chemical_detector = factory.get_detector('chemical')
    if chemical_detector:
        print("✅ Kimya sektörü detector hazır")
    
    # Desteklenen sektörler
    print(f"Desteklenen sektörler: {factory.list_supported_sectors()}") 