#!/usr/bin/env python3
"""
Hybrid PPE Detection System
Combines base YOLO detection with sector-specific intelligent mapping
"""

import cv2
import numpy as np
import logging
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import sqlite3
from pathlib import Path

# Import our custom modules
try:
    from src.smartsafe.detection.utils.enhanced_ppe_detector import EnhancedPPEDetector, PPEDetection, ComplianceResult
except ImportError:
    # Fallback: utils klasöründen dene
    try:
        import sys
        from pathlib import Path
        utils_path = Path(__file__).resolve().parents[4] / 'utils'
        if str(utils_path) not in sys.path:
            sys.path.insert(0, str(utils_path))
        from enhanced_ppe_detector import EnhancedPPEDetector, PPEDetection, ComplianceResult
    except ImportError as e:
        logger.warning(f"⚠️ EnhancedPPEDetector import edilemedi: {e}")
        # Dummy classes oluştur
        class EnhancedPPEDetector:
            pass
        class PPEDetection:
            pass
        class ComplianceResult:
            pass

from .sector_ppe_mapper import SectorPPEMapper, SectorPPERule

logger = logging.getLogger(__name__)

@dataclass
class HybridDetectionResult:
    """Hibrit detection sonucu"""
    timestamp: datetime
    camera_id: str
    company_id: str
    sector: str
    base_detections: List[PPEDetection]
    sector_detections: List[PPEDetection]
    compliance_result: ComplianceResult
    performance_metrics: Dict[str, float]
    success: bool
    error_message: Optional[str] = None

class HybridPPESystem:
    """Ana Hibrit PPE Detection Sistemi"""
    
    def __init__(self, db_path: str = "logs/hybrid_ppe_system.db"):
        self.enhanced_detector = EnhancedPPEDetector()
        self.sector_mapper = SectorPPEMapper()
        self.db_path = db_path
        self.setup_database()
        
        # Performance tracking
        self.detection_times = []
        self.mapping_times = []
        
    def setup_database(self):
        """Veritabanını kurulum"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Hibrit detection results tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hybrid_detection_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    camera_id TEXT,
                    company_id TEXT,
                    sector TEXT,
                    person_count INTEGER,
                    compliance_rate REAL,
                    detected_ppe TEXT,
                    missing_ppe TEXT,
                    base_detection_count INTEGER,
                    sector_detection_count INTEGER,
                    detection_time_ms REAL,
                    mapping_time_ms REAL,
                    success BOOLEAN,
                    error_message TEXT
                )
            ''')
            
            # Şirket PPE konfigürasyonları
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS company_ppe_configs (
                    company_id TEXT PRIMARY KEY,
                    sector TEXT,
                    required_ppe TEXT,
                    optional_ppe TEXT,
                    custom_mapping TEXT,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Hybrid PPE database setup completed")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
    
    def initialize_system(self, model_path: str = "yolov8n.pt") -> bool:
        """Sistemi başlat"""
        try:
            # Enhanced detector'ı başlat
            if not self.enhanced_detector.load_model(model_path):
                return False
            
            # Sector mapper config'i kaydet
            config_path = Path("configs/sector_ppe_mapping.json")
            config_path.parent.mkdir(exist_ok=True)
            self.sector_mapper.save_mapping_config(str(config_path))
            
            logger.info("✅ Hybrid PPE System initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ System initialization failed: {e}")
            return False
    
    def get_company_ppe_config(self, company_id: str) -> Optional[Dict]:
        """Şirket PPE konfigürasyonunu getir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT sector, required_ppe, optional_ppe, custom_mapping 
                FROM company_ppe_configs 
                WHERE company_id = ?
            ''', (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'sector': result[0],
                    'required_ppe': json.loads(result[1]) if result[1] else [],
                    'optional_ppe': json.loads(result[2]) if result[2] else [],
                    'custom_mapping': json.loads(result[3]) if result[3] else {}
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Config retrieval failed: {e}")
            return None
    
    def save_company_ppe_config(self, company_id: str, sector: str, 
                               required_ppe: List[str], optional_ppe: List[str],
                               custom_mapping: Dict[str, str] = None):
        """Şirket PPE konfigürasyonunu kaydet"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.now()
            
            cursor.execute('''
                INSERT OR REPLACE INTO company_ppe_configs 
                (company_id, sector, required_ppe, optional_ppe, custom_mapping, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                company_id,
                sector,
                json.dumps(required_ppe),
                json.dumps(optional_ppe),
                json.dumps(custom_mapping or {}),
                now,
                now
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ PPE config saved for company {company_id}")
            
        except Exception as e:
            logger.error(f"❌ Config save failed: {e}")
    
    def process_detection(self, image: np.ndarray, company_id: str, 
                         camera_id: str, confidence: float = 0.3) -> HybridDetectionResult:
        """Ana detection işlemi"""
        start_time = datetime.now()
        
        try:
            # Şirket konfigürasyonunu al
            company_config = self.get_company_ppe_config(company_id)
            if not company_config:
                # Varsayılan konfigürasyon
                company_config = {
                    'sector': 'general',
                    'required_ppe': ['helmet', 'safety_vest'],
                    'optional_ppe': ['gloves', 'glasses'],
                    'custom_mapping': {}
                }
            
            sector = company_config['sector']
            required_ppe = company_config['required_ppe']
            
            # 1. Base detection
            detection_start = datetime.now()
            base_detections = self.enhanced_detector.detect_base_ppe(image, confidence)
            detection_time = (datetime.now() - detection_start).total_seconds() * 1000
            
            # 2. Sector mapping
            mapping_start = datetime.now()
            sector_detections = self.enhanced_detector.apply_sector_mapping(base_detections, sector)
            mapping_time = (datetime.now() - mapping_start).total_seconds() * 1000
            
            # 3. Compliance analysis
            compliance_result = self.enhanced_detector.analyze_compliance(
                sector_detections, required_ppe, sector
            )
            
            # Performance metrics
            total_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_metrics = {
                'total_time_ms': total_time,
                'detection_time_ms': detection_time,
                'mapping_time_ms': mapping_time,
                'base_detection_count': len(base_detections),
                'sector_detection_count': len(sector_detections),
                'fps_estimate': 1000 / total_time if total_time > 0 else 0
            }
            
            # Sonuç oluştur
            result = HybridDetectionResult(
                timestamp=start_time,
                camera_id=camera_id,
                company_id=company_id,
                sector=sector,
                base_detections=base_detections,
                sector_detections=sector_detections,
                compliance_result=compliance_result,
                performance_metrics=performance_metrics,
                success=True
            )
            
            # Veritabanına kaydet
            self.save_detection_result(result)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Detection processing failed: {e}")
            
            return HybridDetectionResult(
                timestamp=start_time,
                camera_id=camera_id,
                company_id=company_id,
                sector='unknown',
                base_detections=[],
                sector_detections=[],
                compliance_result=ComplianceResult(0, 0, 0, {}, [], 0.0, {}),
                performance_metrics={'total_time_ms': 0, 'detection_time_ms': 0, 'mapping_time_ms': 0},
                success=False,
                error_message=str(e)
            )
    
    def save_detection_result(self, result: HybridDetectionResult):
        """Detection sonucunu veritabanına kaydet"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO hybrid_detection_results 
                (timestamp, camera_id, company_id, sector, person_count, compliance_rate,
                 detected_ppe, missing_ppe, base_detection_count, sector_detection_count,
                 detection_time_ms, mapping_time_ms, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.timestamp,
                result.camera_id,
                result.company_id,
                result.sector,
                result.compliance_result.person_count,
                result.compliance_result.compliance_rate,
                json.dumps(list(result.compliance_result.detected_ppe.keys())),
                json.dumps(result.compliance_result.missing_ppe),
                len(result.base_detections),
                len(result.sector_detections),
                result.performance_metrics.get('detection_time_ms', 0),
                result.performance_metrics.get('mapping_time_ms', 0),
                result.success,
                result.error_message
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Result save failed: {e}")
    
    def get_detection_statistics(self, company_id: str, 
                               hours: int = 24) -> Dict[str, any]:
        """Detection istatistiklerini getir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_detections,
                    AVG(compliance_rate) as avg_compliance,
                    AVG(person_count) as avg_people,
                    AVG(detection_time_ms) as avg_detection_time,
                    AVG(mapping_time_ms) as avg_mapping_time,
                    COUNT(CASE WHEN success = 1 THEN 1 END) as successful_detections
                FROM hybrid_detection_results 
                WHERE company_id = ? 
                AND timestamp >= datetime('now', '-{} hours')
            '''.format(hours), (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'total_detections': result[0],
                    'avg_compliance_rate': result[1] or 0,
                    'avg_people_count': result[2] or 0,
                    'avg_detection_time_ms': result[3] or 0,
                    'avg_mapping_time_ms': result[4] or 0,
                    'success_rate': (result[5] / result[0]) if result[0] > 0 else 0,
                    'estimated_fps': 1000 / (result[3] or 1000)
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Statistics retrieval failed: {e}")
            return {}
    
    def draw_hybrid_results(self, image: np.ndarray, 
                           result: HybridDetectionResult) -> np.ndarray:
        """Hibrit sonuçları çiz"""
        if not result.success:
            # Hata durumunu göster
            cv2.putText(image, f"ERROR: {result.error_message}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return image
        
        # Enhanced detector'ın draw metodunu kullan
        result_image = self.enhanced_detector.draw_results(
            image, result.sector_detections, result.compliance_result
        )
        
        # Ek bilgiler ekle
        h, w = result_image.shape[:2]
        
        # Sector bilgisi
        sector_text = f"Sector: {result.sector.upper()}"
        cv2.putText(result_image, sector_text, (10, h-60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Performance bilgisi
        fps_text = f"FPS: {result.performance_metrics.get('fps_estimate', 0):.1f}"
        cv2.putText(result_image, fps_text, (10, h-40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Detection count
        count_text = f"Detections: {len(result.sector_detections)}"
        cv2.putText(result_image, count_text, (10, h-20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        return result_image
    
    def create_sector_ppe_options_for_ui(self, sector: str) -> Dict[str, List[Dict]]:
        """UI için sektör PPE seçeneklerini oluştur"""
        return self.sector_mapper.generate_sector_ppe_options(sector)
    
    def validate_company_ppe_selection(self, company_ppe: List[str], 
                                     sector: str) -> Dict[str, any]:
        """Şirket PPE seçimini doğrula"""
        return self.sector_mapper.validate_company_ppe_config(company_ppe, sector)

# Test fonksiyonu
def test_hybrid_system():
    """Hibrit sistem test"""
    print("🚀 Testing Hybrid PPE System...")
    
    # Sistemi başlat
    system = HybridPPESystem()
    if not system.initialize_system():
        print("❌ System initialization failed!")
        return
    
    # Test image
    test_image = cv2.imread("demo_ppe_compliant.jpg")
    if test_image is None:
        print("❌ Test image not found!")
        return
    
    # Test company config
    company_id = "test_company_001"
    system.save_company_ppe_config(
        company_id=company_id,
        sector="construction",
        required_ppe=["helmet", "safety_vest"],
        optional_ppe=["gloves", "glasses"]
    )
    
    # Test detection
    result = system.process_detection(
        image=test_image,
        company_id=company_id,
        camera_id="test_camera_001"
    )
    
    if result.success:
        print(f"✅ Detection successful!")
        print(f"  Sector: {result.sector}")
        print(f"  People: {result.compliance_result.person_count}")
        print(f"  Compliance: {result.compliance_result.compliance_rate:.1%}")
        print(f"  Performance: {result.performance_metrics['fps_estimate']:.1f} FPS")
        
        # Sonucu kaydet
        result_image = system.draw_hybrid_results(test_image.copy(), result)
        cv2.imwrite("result_hybrid_test.jpg", result_image)
        print(f"  ✅ Result saved: result_hybrid_test.jpg")
        
        # İstatistikleri göster
        stats = system.get_detection_statistics(company_id)
        print(f"  Statistics: {stats}")
        
    else:
        print(f"❌ Detection failed: {result.error_message}")

if __name__ == "__main__":
    test_hybrid_system() 