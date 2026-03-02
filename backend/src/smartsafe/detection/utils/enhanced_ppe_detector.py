#!/usr/bin/env python3
"""
Enhanced Hybrid PPE Detection System
Combines base YOLO detection with sector-specific PPE classification
"""

import cv2
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from ultralytics import YOLO
import json
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PPEDetection:
    """Enhanced PPE detection data structure"""
    bbox: Tuple[int, int, int, int]
    confidence: float
    base_class: str        # Temel model sınıfı (helmet, vest, mask, etc.)
    sector_class: str      # Sektörel sınıf (chemical_gloves, hygiene_mask, etc.)
    person_id: Optional[int] = None

@dataclass
class ComplianceResult:
    """PPE compliance analysis result"""
    person_count: int
    compliant_count: int
    violation_count: int
    detected_ppe: Dict[str, List[PPEDetection]]
    missing_ppe: List[str]
    compliance_rate: float
    sector_specific_analysis: Dict[str, bool]

class EnhancedPPEDetector:
    """Hibrit PPE Detection Sistemi"""
    
    def __init__(self):
        self.base_model = None
        self.sector_mappings = self.load_sector_mappings()
        self.enhanced_classes = self.load_enhanced_classes()
        
    def load_enhanced_classes(self) -> Dict[str, str]:
        """Genişletilmiş PPE sınıfları"""
        return {
            # Temel sınıflar (mevcut model)
            'person': 'person',
            'hard_hat': 'helmet',
            'helmet': 'helmet',
            'safety_vest': 'safety_vest',
            'vest': 'safety_vest',
            'mask': 'face_mask',
            'face_mask': 'face_mask',
            'gloves': 'gloves',
            'safety_shoes': 'safety_shoes',
            'glasses': 'glasses',
            'safety_glasses': 'glasses',
            'boots': 'safety_shoes',
            'shoes': 'safety_shoes',
            
            # Yeni Sektör Sınıfları
            'ear_protection': 'ear_protection',
            'harness': 'harness',
            'gas_mask': 'face_mask',
            'chemical_suit': 'safety_vest',
            'life_vest': 'safety_vest',
            'arc_flash_suit': 'safety_vest',
            'aviation_headset': 'ear_protection',
            'fall_protection': 'harness'
        }
    
    def load_sector_mappings(self) -> Dict[str, Dict[str, str]]:
        """Sektörel PPE haritalama sistemi"""
        return {
            'construction': {
                'helmet': 'construction_helmet',
                'safety_vest': 'high_visibility_vest',
                'gloves': 'work_gloves',
                'safety_shoes': 'steel_toe_boots',
                'glasses': 'safety_glasses'
            },
            'chemical': {
                'face_mask': 'chemical_respirator',
                'gloves': 'chemical_gloves',
                'safety_vest': 'chemical_suit',
                'glasses': 'chemical_goggles',
                'safety_shoes': 'chemical_boots'
            },
            'food': {
                'helmet': 'hair_net',
                'face_mask': 'hygiene_mask',
                'safety_vest': 'hygiene_apron',
                'gloves': 'hygiene_gloves',
                'safety_shoes': 'non_slip_shoes'
            },
            'manufacturing': {
                'helmet': 'industrial_helmet',
                'safety_vest': 'reflective_vest',
                'gloves': 'industrial_gloves',
                'safety_shoes': 'steel_toe_shoes',
                'glasses': 'safety_glasses'
            },
            'warehouse': {
                'safety_vest': 'visibility_vest',
                'safety_shoes': 'warehouse_shoes',
                'helmet': 'protective_helmet',
                'gloves': 'warehouse_gloves'
            },
            'general': {
                'helmet': 'safety_helmet',
                'safety_vest': 'safety_vest',
                'gloves': 'safety_gloves',
                'safety_shoes': 'safety_shoes',
                'glasses': 'safety_glasses'
            },
            'energy': {
                'helmet': 'dielectric_helmet',
                'gloves': 'insulated_gloves',
                'safety_vest': 'arc_flash_suit',
                'safety_shoes': 'insulated_boots',
                'glasses': 'arc_flash_visor'
            },
            'petrochemical': {
                'helmet': 'chem_helmet',
                'face_mask': 'gas_mask',
                'safety_vest': 'chemical_suit',
                'gloves': 'chemical_resistant_gloves',
                'safety_shoes': 'chemical_boots'
            },
            'shipyard': {
                'helmet': 'marine_helmet',
                'safety_vest': 'life_vest',
                'gloves': 'waterproof_gloves',
                'safety_shoes': 'marine_boots',
                'harness': 'fall_protection'
            },
            'aviation': {
                'helmet': 'aviation_helmet',
                'safety_vest': 'high_vis_vest',
                'ear_protection': 'aviation_headset',
                'safety_shoes': 'esd_shoes',
                'gloves': 'mechanic_gloves'
            }
        }
    
    def load_model(self, model_path: str = "yolov8n.pt") -> bool:
        """Base YOLO modelini yükle"""
        try:
            self.base_model = YOLO(model_path)
            self.base_model.to('cpu')
            logger.info(f"✅ Base model loaded: {model_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Model loading failed: {e}")
            return False
    
    def detect_base_ppe(self, image: np.ndarray, confidence: float = 0.3) -> List[PPEDetection]:
        """Temel PPE tespiti"""
        if self.base_model is None:
            logger.error("Model not loaded!")
            return []
        
        try:
            results = self.base_model(image, conf=confidence, verbose=False)
            detections = []
            
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Sınıf adını al
                        if hasattr(self.base_model, 'names'):
                            class_name = self.base_model.names[class_id]
                        else:
                            class_name = f"class_{class_id}"
                        
                        # Standardize class name
                        base_class = self.enhanced_classes.get(class_name, class_name)
                        
                        detections.append(PPEDetection(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            confidence=float(conf),
                            base_class=base_class,
                            sector_class=base_class  # Initially same as base
                        ))
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []
    
    def apply_sector_mapping(self, detections: List[PPEDetection], 
                           sector: str) -> List[PPEDetection]:
        """Sektörel PPE haritalama uygula"""
        if sector not in self.sector_mappings:
            sector = 'general'
        
        sector_map = self.sector_mappings[sector]
        
        for detection in detections:
            if detection.base_class in sector_map:
                detection.sector_class = sector_map[detection.base_class]
        
        return detections
    
    def analyze_compliance(self, detections: List[PPEDetection], 
                         required_ppe: List[str], 
                         sector: str) -> ComplianceResult:
        """PPE compliance analizi"""
        # Kişi sayısını bul
        people = [d for d in detections if d.base_class == 'person']
        person_count = len(people)
        
        if person_count == 0:
            return ComplianceResult(
                person_count=0,
                compliant_count=0,
                violation_count=0,
                detected_ppe={},
                missing_ppe=[],
                compliance_rate=0.0,
                sector_specific_analysis={}
            )
        
        # PPE'leri grupla
        detected_ppe = {}
        for detection in detections:
            if detection.base_class != 'person':
                if detection.sector_class not in detected_ppe:
                    detected_ppe[detection.sector_class] = []
                detected_ppe[detection.sector_class].append(detection)
        
        # Sektörel mapping uygula
        sector_map = self.sector_mappings.get(sector, {})
        mapped_required_ppe = []
        for ppe in required_ppe:
            mapped_ppe = sector_map.get(ppe, ppe)
            mapped_required_ppe.append(mapped_ppe)
        
        # Eksik PPE'leri bul
        missing_ppe = []
        sector_analysis = {}
        
        for required in mapped_required_ppe:
            has_ppe = required in detected_ppe and len(detected_ppe[required]) > 0
            sector_analysis[required] = has_ppe
            if not has_ppe:
                missing_ppe.append(required)
        
        # Compliance hesapla
        compliant_count = person_count if len(missing_ppe) == 0 else 0
        violation_count = person_count - compliant_count
        compliance_rate = compliant_count / person_count if person_count > 0 else 0.0
        
        return ComplianceResult(
            person_count=person_count,
            compliant_count=compliant_count,
            violation_count=violation_count,
            detected_ppe=detected_ppe,
            missing_ppe=missing_ppe,
            compliance_rate=compliance_rate,
            sector_specific_analysis=sector_analysis
        )
    
    def detect_and_analyze(self, image: np.ndarray, 
                          sector: str, 
                          required_ppe: List[str],
                          confidence: float = 0.3) -> ComplianceResult:
        """Tam hibrit detection ve analiz"""
        # 1. Temel PPE tespiti
        detections = self.detect_base_ppe(image, confidence)
        
        # 2. Sektörel haritalama
        detections = self.apply_sector_mapping(detections, sector)
        
        # 3. Compliance analizi
        result = self.analyze_compliance(detections, required_ppe, sector)
        
        return result
    
    def draw_results(self, image: np.ndarray, 
                    detections: List[PPEDetection],
                    result: ComplianceResult) -> np.ndarray:
        """Sonuçları görselleştir"""
        # Renk kodları
        colors = {
            'person': (255, 255, 255),
            'compliant': (0, 255, 0),
            'violation': (0, 0, 255),
            'ppe': (0, 255, 255)
        }
        
        # Detection kutularını çiz
        from src.smartsafe.detection.utils.visual_overlay import draw_styled_box
        
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox
            
            if detection.base_class == 'person':
                color = colors['person']
                label = f"Person {detection.confidence:.2f}"
            else:
                color = colors['ppe']
                label = f"{detection.sector_class} {detection.confidence:.2f}"
            
            # Profesyonel bounding box çiz
            image = draw_styled_box(image, x1, y1, x2, y2, label, color)
        
        # Compliance durumunu göster
        h, w = image.shape[:2]
        status_color = colors['compliant'] if result.compliance_rate > 0.8 else colors['violation']
        status_text = f"Compliance: {result.compliance_rate:.1%} ({result.compliant_count}/{result.person_count})"
        
        cv2.putText(image, status_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        
        # Eksik PPE'leri göster
        if result.missing_ppe:
            missing_text = f"Missing: {', '.join(result.missing_ppe)}"
            cv2.putText(image, missing_text, (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors['violation'], 1)
        
        return image

# Test fonksiyonu
def test_enhanced_detector():
    """Enhanced detector test"""
    detector = EnhancedPPEDetector()
    
    if not detector.load_model():
        print("❌ Model yüklenemedi!")
        return
    
    # Test image
    test_image = cv2.imread("demo_ppe_compliant.jpg")
    if test_image is None:
        print("❌ Test image bulunamadı!")
        return
    
    # Test different sectors
    sectors = ['construction', 'chemical', 'food']
    required_ppe_map = {
        'construction': ['helmet', 'safety_vest'],
        'chemical': ['face_mask', 'gloves', 'safety_vest'],
        'food': ['helmet', 'face_mask', 'safety_vest']
    }
    
    for sector in sectors:
        print(f"\n🔍 Testing {sector} sector:")
        
        result = detector.detect_and_analyze(
            test_image, 
            sector, 
            required_ppe_map[sector]
        )
        
        print(f"  People: {result.person_count}")
        print(f"  Compliance: {result.compliance_rate:.1%}")
        print(f"  Detected PPE: {list(result.detected_ppe.keys())}")
        print(f"  Missing PPE: {result.missing_ppe}")
        
        # Sonuçları kaydet
        result_image = detector.draw_results(test_image.copy(), [], result)
        cv2.imwrite(f"result_enhanced_{sector}.jpg", result_image)
        print(f"  ✅ Result saved: result_enhanced_{sector}.jpg")

if __name__ == "__main__":
    test_enhanced_detector() 