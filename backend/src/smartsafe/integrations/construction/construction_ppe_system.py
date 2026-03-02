#!/usr/bin/env python3
"""
SmartSafe AI - İnşaat Sektörü Özelleştirilmiş PPE Detection Sistemi
v1.0 - İnşaat sektörü için optimize edilmiş güvenlik izleme sistemi
"""

import cv2
import numpy as np
from ultralytics import YOLO
import time
import json
import sqlite3
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import os

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ConstructionWorker:
    """İnşaat çalışanı veri modeli"""
    worker_id: str
    name: str
    position: str
    department: str
    violation_count: int = 0
    last_violation: Optional[datetime] = None


@dataclass
class PPEViolation:
    """PPE ihlal veri modeli"""
    timestamp: datetime
    worker_id: str
    camera_id: str
    missing_ppe: List[str]
    confidence_score: float
    image_path: str


class ConstructionPPEConfig:
    """İnşaat sektörü PPE konfigürasyonu"""
    
    # İnşaat sektörü zorunlu PPE
    MANDATORY_PPE = {
        'helmet': {
            'name': 'Baret/Kask',
            'critical': True,
            'detection_classes': ['helmet']
        },
        'safety_vest': {
            'name': 'Güvenlik Yeleği',
            'critical': True,
            'detection_classes': ['safety_vest', 'safety_suit']
        },
        'safety_shoes': {
            'name': 'Güvenlik Ayakkabısı',
            'critical': True,
            'detection_classes': ['shoes']
        }
    }
    
    # Opsiyonel PPE (bonus puanlar)
    OPTIONAL_PPE = {
        'gloves': {
            'name': 'Güvenlik Eldiveni',
            'bonus_points': 10,
            'detection_classes': ['gloves']
        },
        'glasses': {
            'name': 'Güvenlik Gözlüğü',
            'bonus_points': 15,
            'detection_classes': ['glasses']
        }
    }
    
    # Sistem ayarları
    DETECTION_SETTINGS = {
        'confidence_threshold': 0.6,
        'detection_interval': 3,  # saniye
        'violation_cooldown': 300  # 5 dakika
    }

class ConstructionPPEDetector:
    """İnşaat sektörü özelleştirilmiş PPE detector"""
    
    def __init__(self, config: ConstructionPPEConfig):
        self.config = config
        self.model = None
        self.db_path = "construction_safety.db"
        self.last_detection_time = {}
        self.worker_violations = {}
        
        # Veritabanı kurulumu
        self.setup_database()
        
        # Model yükleme
        self.load_construction_model()
    
    def setup_database(self):
        """Veritabanı tablolarını oluştur"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Çalışanlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                position TEXT,
                department TEXT,
                violation_count INTEGER DEFAULT 0,

                created_date TEXT,
                last_violation TEXT
            )
        ''')
        
        # İhlaller tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                worker_id TEXT,
                camera_id TEXT,
                missing_ppe TEXT,
                confidence_score REAL,
                image_path TEXT,

                processed BOOLEAN DEFAULT 0,
                FOREIGN KEY (worker_id) REFERENCES workers (worker_id)
            )
        ''')
        
        # Günlük raporlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_reports (
                date TEXT PRIMARY KEY,
                total_detections INTEGER,
                total_violations INTEGER,
                compliance_rate REAL,

                active_workers INTEGER
            )
        ''')
        
        # Demo çalışanları ekle
        demo_workers = [
            ('CW001', 'Ahmet Yılmaz', 'İnşaat İşçisi', 'Yapı'),
            ('CW002', 'Mehmet Kaya', 'Foreman', 'Yapı'),
            ('CW003', 'Ali Demir', 'İnşaat İşçisi', 'Altyapı'),
            ('CW004', 'Hasan Özkan', 'Güvenlik Sorumlusu', 'Güvenlik'),
            ('CW005', 'Fatma Şahin', 'Mühendis', 'Teknik')
        ]
        
        for worker_id, name, position, department in demo_workers:
            cursor.execute('''
                INSERT OR IGNORE INTO workers 
                (worker_id, name, position, department, created_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (worker_id, name, position, department, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info("✅ Veritabanı kurulumu tamamlandı")
    
    def load_construction_model(self):
        """İnşaat sektörü için optimize edilmiş model yükle"""
        try:
            # Önce SH17 PPE modelini dene
            try:
                self.model = YOLO('data/models/yolo9e.pt')
                model_type = "SH17 PPE Model"
                logger.info(f"✅ {model_type} yüklendi")
            except:
                # Fallback olarak genel model
                self.model = YOLO('yolov8n.pt')
                model_type = "YOLOv8n (Genel)"
                logger.info(f"⚠️ PPE model bulunamadı, {model_type} kullanılıyor")
            
            self.model.to('cpu')
            return True
            
        except Exception as e:
            logger.error(f"❌ Model yükleme hatası: {e}")
            return False
    
    def detect_construction_ppe(self, image: np.ndarray, camera_id: str) -> Dict:
        """İnşaat sahası PPE tespiti"""
        try:
            # Model ile tespit
            results = self.model(image, conf=self.config.DETECTION_SETTINGS['confidence_threshold'], verbose=False)
            
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
                            # SH17 classes mapping
                            sh17_classes = {
                                0: 'person', 14: 'helmet', 12: 'safety_vest', 
                                11: 'shoes', 9: 'gloves', 3: 'glasses'
                            }
                            class_name = sh17_classes.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            # İnşaat sektörü analizi
            analysis = self.analyze_construction_compliance(detections, camera_id)
            
            return {
                'timestamp': datetime.now(),
                'camera_id': camera_id,
                'detections': detections,
                'analysis': analysis,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Tespit hatası: {e}")
            return {'success': False, 'error': str(e)}
    
    def analyze_construction_compliance(self, detections: List[Dict], camera_id: str) -> Dict:
        """İnşaat sektörü uygunluk analizi"""
        # İnsanları ve PPE'leri ayır
        people = [d for d in detections if d['class_name'] == 'person']
        
        # PPE tespit kategorileri
        detected_ppe = {
            'helmet': [d for d in detections if d['class_name'] in ['helmet']],
            'safety_vest': [d for d in detections if d['class_name'] in ['safety_vest', 'safety_suit']],
            'safety_shoes': [d for d in detections if d['class_name'] in ['shoes']],
            'gloves': [d for d in detections if d['class_name'] in ['gloves']],
            'glasses': [d for d in detections if d['class_name'] in ['glasses']]
        }
        
        compliance_results = []
        
        for i, person in enumerate(people):
            person_bbox = person['bbox']
            
            # Her PPE için kontrol
            ppe_status = {}
            missing_ppe = []
            
            # Zorunlu PPE kontrolü
            for ppe_type, ppe_config in self.config.MANDATORY_PPE.items():
                has_ppe = any(
                    self.boxes_overlap(person_bbox, ppe['bbox'], threshold=0.1) 
                    for ppe in detected_ppe.get(ppe_type, [])
                )
                ppe_status[ppe_type] = has_ppe
                if not has_ppe:
                    missing_ppe.append(ppe_type)
            
            # Opsiyonel PPE kontrolü
            for ppe_type, ppe_config in self.config.OPTIONAL_PPE.items():
                has_ppe = any(
                    self.boxes_overlap(person_bbox, ppe['bbox'], threshold=0.1) 
                    for ppe in detected_ppe.get(ppe_type, [])
                )
                ppe_status[ppe_type] = has_ppe
            
            # Uygunluk hesaplama
            is_compliant = len(missing_ppe) == 0
            compliance_score = self.calculate_compliance_score(ppe_status)
            

            
            compliance_results.append({
                'person_id': f"Person_{i+1}",
                'worker_id': self.assign_worker_id(camera_id, i),  # Demo için
                'bbox': person_bbox,
                'ppe_status': ppe_status,
                'missing_ppe': missing_ppe,
                'compliant': is_compliant,
                'compliance_score': compliance_score,

                'violation_level': self.get_violation_level(missing_ppe)
            })
        
        # Genel istatistikler
        total_people = len(people)
        compliant_people = sum(1 for r in compliance_results if r['compliant'])
        
        return {
            'total_people': total_people,
            'compliant_people': compliant_people,
            'violation_people': total_people - compliant_people,
            'compliance_rate': (compliant_people / total_people * 100) if total_people > 0 else 0,
            'individual_results': compliance_results,
            'detected_ppe_summary': {k: len(v) for k, v in detected_ppe.items()},

        }
    
    def calculate_compliance_score(self, ppe_status: Dict[str, bool]) -> float:
        """Uygunluk skoru hesapla (0-100)"""
        mandatory_count = len(self.config.MANDATORY_PPE)
        mandatory_present = sum(
            1 for ppe_type in self.config.MANDATORY_PPE.keys() 
            if ppe_status.get(ppe_type, False)
        )
        
        base_score = (mandatory_present / mandatory_count) * 80 if mandatory_count > 0 else 0
        
        # Opsiyonel PPE bonus
        optional_bonus = sum(
            self.config.OPTIONAL_PPE[ppe_type]['bonus_points']
            for ppe_type in self.config.OPTIONAL_PPE.keys()
            if ppe_status.get(ppe_type, False)
        )
        
        return min(100.0, base_score + (optional_bonus / 5))  # Max 20 bonus
    
    def get_violation_level(self, missing_ppe: List[str]) -> str:
        """İhlal seviyesi belirleme"""
        if not missing_ppe:
            return "UYGUN"
        elif len(missing_ppe) == 1:
            return "DÜŞÜK RİSK"
        elif len(missing_ppe) == 2:
            return "ORTA RİSK"
        else:
            return "YÜKSEK RİSK"
    
    def assign_worker_id(self, camera_id: str, person_index: int) -> str:
        """Demo için çalışan ID ataması"""
        # Gerçek sistemde face recognition ile yapılacak
        demo_workers = ['CW001', 'CW002', 'CW003', 'CW004', 'CW005']
        return demo_workers[person_index % len(demo_workers)]
    
    def boxes_overlap(self, box1: Tuple, box2: Tuple, threshold: float = 0.1) -> bool:
        """İki kutunun kesişim kontrolü"""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Kesişim hesaplama
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i <= x1_i or y2_i <= y1_i:
            return False
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        iou = intersection / union if union > 0 else 0
        return iou > threshold
    
    def save_violation(self, violation_data: Dict):
        """İhlali veritabanına kaydet"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO violations 
                (timestamp, worker_id, camera_id, missing_ppe, confidence_score, image_path)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                violation_data['timestamp'].isoformat(),
                violation_data['worker_id'],
                violation_data['camera_id'],
                json.dumps(violation_data['missing_ppe']),
                violation_data['confidence_score'],
                violation_data.get('image_path', '')
            ))
            
            # Çalışan ihlal sayısını güncelle
            cursor.execute('''
                UPDATE workers 
                SET violation_count = violation_count + 1,
                    last_violation = ?
                WHERE worker_id = ?
            ''', (
                violation_data['timestamp'].isoformat(),
                violation_data['worker_id']
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ İhlal kaydedildi: {violation_data['worker_id']}")
            
        except Exception as e:
            logger.error(f"❌ İhlal kaydetme hatası: {e}")
    
    def draw_detection_results(self, image: np.ndarray, detection_result: Dict) -> np.ndarray:
        """Detection sonuçlarını görüntü üzerine çiz"""
        try:
            # Görüntüyü kopyala
            annotated_image = image.copy()
            height, width = annotated_image.shape[:2]
            
            # Başlık bilgileri
            title_text = f"İnşaat Güvenlik İzleme - Kamera: {detection_result.get('camera_id', 'Unknown')}"
            cv2.putText(annotated_image, title_text, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            # Genel bilgiler
            analysis = detection_result.get('analysis', {})
            compliance_rate = analysis.get('compliance_rate', 0)
            total_people = analysis.get('total_people', 0)
            
            # Uyum oranı
            compliance_color = (
                (0, 255, 0) if compliance_rate >= 80 
                else (0, 165, 255) if compliance_rate >= 60 
                else (0, 0, 255)
            )
            cv2.putText(annotated_image, f"Uyum Oranı: {compliance_rate:.1f}%", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, compliance_color, 2)
            
            # Toplam kişi sayısı
            cv2.putText(annotated_image, f"Toplam Kişi: {total_people}", 
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Detection sonuçları
            detections = detection_result.get('detections', [])
            for i, detection in enumerate(detections):
                # Çalışan kimliği
                worker_id = detection.get('worker_id', f'Person_{i+1}')
                label = f"{worker_id}"

                # Bounding box koordinatları (x1, y1, x2, y2)
                bbox = detection.get('bbox', [0, 0, 0, 0])
                x1, y1, x2, y2 = map(int, bbox)
                
                # Renk belirleme (örnek olarak yeşil)
                box_color = (0, 255, 0)

                # Profesyonel bounding box çiz
                annotated_image = draw_styled_box(annotated_image, x1, y1, x2, y2, label, box_color)

                # PPE durumu
                ppe_status = detection.get('ppe_status', {})
                y_offset = y1 + 20
                for ppe_type, status in ppe_status.items():
                    if ppe_type in ['helmet', 'safety_vest', 'safety_shoes']:
                        ppe_name = {
                            'helmet': 'Baret',
                            'safety_vest': 'Yelek',
                            'safety_shoes': 'Ayakkabı'
                        }.get(ppe_type, ppe_type)
                        
                        status_color = (0, 255, 0) if status else (0, 0, 255)
                        status_text = "✓" if status else "✗"
                        
                        cv2.putText(
                            annotated_image,
                            f"{ppe_name}: {status_text}",
                            (x1, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,
                            status_color,
                            1
                        )
                        y_offset += 15
            
            # İhlal listesi (sağ üst köşe)
            violations = analysis.get('individual_results', [])
            if violations:
                cv2.putText(annotated_image, "İHLALLER:", (width - 200, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
                for i, violation in enumerate(violations[:5]):  # Maksimum 5 ihlal göster
                    violation_text = f"• {violation.get('missing_ppe', ['Unknown'])[0]}"
                    cv2.putText(annotated_image, violation_text, 
                                (width - 200, 55 + i * 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(annotated_image, timestamp, (10, height - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            return annotated_image

        except Exception as e:
            logger.error(f"❌ Görüntü çizim hatası: {e}")
            return image  # Hata durumunda orijinal görüntüyü döndür
    
    def generate_daily_report(self, date: str = None) -> Dict:
        """Günlük rapor oluştur"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Günlük istatistikler
            cursor.execute('''
                SELECT COUNT(*) FROM violations 
                WHERE date(timestamp) = ?
            ''', (date,))
            total_violations = cursor.fetchone()[0]
            

            
            cursor.execute('SELECT COUNT(*) FROM workers')
            active_workers = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'date': date,
                'total_violations': total_violations,
                'active_workers': active_workers,
                'compliance_rate': max(0, 100 - (total_violations / active_workers * 10)) if active_workers > 0 else 100
            }
            
        except Exception as e:
            logger.error(f"❌ Rapor oluşturma hatası: {e}")
            return {}

def main():
    """Demo çalıştırma"""
    print("🏗️ SmartSafe AI - İnşaat Sektörü PPE Detection Sistemi")
    print("=" * 60)
    
    # Konfigürasyon
    config = ConstructionPPEConfig()
    
    # Detector başlat
    detector = ConstructionPPEDetector(config)
    
    # Sistem bilgileri
    print("\n📋 İnşaat Sektörü PPE Kuralları:")
    for ppe_type, ppe_info in config.MANDATORY_PPE.items():
        print(f"  ✅ {ppe_info['name']}")
    
    print(f"\n⚙️ Sistem Ayarları:")
    print(f"  - Tespit Eşiği: {config.DETECTION_SETTINGS['confidence_threshold']}")
    print(f"  - Tespit Aralığı: {config.DETECTION_SETTINGS['detection_interval']} saniye")
    
    # Demo test
    print(f"\n🎯 Test için demo fotoğrafları yükleniyor...")
    test_images = ['people1.jpg', 'people2.jpg', 'people3.jpg']
    
    for image_path in test_images:
        if os.path.exists(image_path):
            print(f"\n📷 Test: {image_path}")
            
            # Resmi yükle
            image = cv2.imread(image_path)
            if image is not None:
                # PPE analizi
                result = detector.detect_construction_ppe(image, f"Camera-{image_path}")
                
                if result['success']:
                    analysis = result['analysis']
                    print(f"  👥 Toplam Kişi: {analysis['total_people']}")
                    print(f"  ✅ Uyumlu: {analysis['compliant_people']}")
                    print(f"  ❌ İhlal: {analysis['violation_people']}")
                    print(f"  📊 Uyum Oranı: {analysis['compliance_rate']:.1f}%")

                    
                    # İhlal detayları
                    for person_result in analysis['individual_results']:
                        if not person_result['compliant']:
                            missing = ', '.join(person_result['missing_ppe'])
                            print(f"    🚨 {person_result['worker_id']}: {missing} eksik")
    
    # Günlük rapor
    print(f"\n📊 Günlük Rapor:")
    daily_report = detector.generate_daily_report()
    print(f"  📅 Tarih: {daily_report.get('date', 'N/A')}")
    print(f"  🚨 Toplam İhlal: {daily_report.get('total_violations', 0)}")

    print(f"  👥 Aktif Çalışan: {daily_report.get('active_workers', 0)}")
    print(f"  📈 Uyum Oranı: {daily_report.get('compliance_rate', 0):.1f}%")

if __name__ == "__main__":
    main() 