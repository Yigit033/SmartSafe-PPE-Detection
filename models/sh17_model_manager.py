#!/usr/bin/env python3
"""
SH17 Model Manager
SmartSafe AI - PPE Detection Model Integration
"""

import os
import yaml
import torch
import numpy as np
from pathlib import Path
from ultralytics import YOLO
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class SH17ModelManager:
    def __init__(self, models_dir='models'):
        self.models_dir = models_dir
        # CUDA sorunları nedeniyle CPU kullan
        self.device = 'cpu'
        self.models = {}
        self.fallback_model = None
        
        # 🚀 PERFORMANCE OPTIMIZATION - Model caching ve inference hızlandırma
        self.model_cache = {}  # Model cache
        self.last_detection_time = {}  # Son detection zamanları
        self.detection_throttle = 0.05  # Detection throttle (50ms - daha hızlı)
        
        self.sector_mapping = {
            'construction': ['helmet', 'safety_vest', 'safety_shoes', 'gloves'],
            'manufacturing': ['helmet', 'safety_vest', 'gloves', 'safety_glasses'],
            'chemical': ['helmet', 'respirator', 'gloves', 'safety_glasses', 'medical_suit'],
            'food_beverage': ['helmet', 'safety_vest', 'gloves', 'safety_glasses', 'face_mask_medical'],
            'warehouse_logistics': ['helmet', 'safety_vest', 'gloves', 'safety_shoes'],
            'energy': ['helmet', 'safety_vest', 'safety_shoes', 'gloves', 'safety_suit'],
            'petrochemical': ['helmet', 'respirator', 'safety_vest', 'gloves', 'safety_suit', 'safety_glasses'],
            'marine_shipyard': ['helmet', 'safety_vest', 'gloves', 'safety_shoes', 'safety_glasses'],
            'aviation': ['helmet', 'safety_vest', 'gloves', 'safety_glasses', 'face_mask_medical']
        }
        
        # SH17 class mapping
        self.sh17_classes = [
            'person', 'head', 'face', 'glasses', 'face_mask_medical',
            'face_guard', 'ear', 'earmuffs', 'hands', 'gloves',
            'foot', 'shoes', 'safety_vest', 'tools', 'helmet',
            'medical_suit', 'safety_suit'
        ]
        
        logger.info(f"🎯 SH17 Model Manager başlatıldı - Device: {self.device}")
        
        # Modelleri otomatik yükle
        self.load_models()
        
    def load_models(self):
        """Tüm SH17 modellerini yükle ve fallback model'i hazırla"""
        logger.info("📦 SH17 modelleri yükleniyor...")
        
        # SH17 model yolları - önce models/ klasöründe ara
        model_paths = {
            'base': f'{self.models_dir}/sh17_base/sh17_base_model/weights/best.pt',
            'construction': f'{self.models_dir}/sh17_construction/sh17_construction_model/weights/best.pt',
            'manufacturing': f'{self.models_dir}/sh17_manufacturing/sh17_manufacturing_model/weights/best.pt',
            'chemical': f'{self.models_dir}/sh17_chemical/sh17_chemical_model/weights/best.pt',
            'food_beverage': f'{self.models_dir}/sh17_food_beverage/sh17_food_beverage_model/weights/best.pt',
            'warehouse_logistics': f'{self.models_dir}/sh17_warehouse_logistics/sh17_warehouse_logistics_model/weights/best.pt',
            'energy': f'{self.models_dir}/sh17_energy/sh17_energy_model/weights/best.pt',
            'petrochemical': f'{self.models_dir}/sh17_petrochemical/sh17_petrochemical_model/weights/best.pt',
            'marine_shipyard': f'{self.models_dir}/sh17_marine_shipyard/sh17_marine_shipyard_model/weights/best.pt',
            'aviation': f'{self.models_dir}/sh17_aviation/sh17_aviation_model/weights/best.pt'
        }
        
        # SH17 modellerini yükle
        loaded_models = 0
        for sector, path in model_paths.items():
            if os.path.exists(path):
                try:
                    self.models[sector] = YOLO(path)
                    self.models[sector].to(self.device)
                    logger.info(f"✅ {sector} modeli yüklendi: {path}")
                    loaded_models += 1
                except Exception as e:
                    logger.warning(f"❌ {sector} modeli yüklenemedi: {e}")
            else:
                logger.warning(f"⚠️ {sector} modeli bulunamadı: {path}")
        
        # Production-ready fallback model yükle
        try:
            # Production ortamında otomatik YOLOv8n indirme
            logger.info("🔄 Production ortamında YOLOv8n model indiriliyor...")
            self.fallback_model = YOLO('yolov8n.pt')  # Otomatik indir
            self.fallback_model.to(self.device)
            logger.info("✅ YOLOv8n fallback model başarıyla indirildi ve yüklendi")
        except Exception as e:
            logger.warning(f"⚠️ Otomatik YOLOv8n indirme hatası: {e}")
            # Manuel fallback yolları dene
            fallback_paths = ['yolov8n.pt', 'models/yolov8n.pt', '/app/models/yolov8n.pt']
            for fallback_path in fallback_paths:
                if os.path.exists(fallback_path):
                    try:
                        self.fallback_model = YOLO(fallback_path)
                        self.fallback_model.to(self.device)
                        logger.info(f"✅ Fallback model yüklendi: {fallback_path}")
                        break
                    except Exception as load_error:
                        logger.warning(f"⚠️ Fallback model yükleme hatası {fallback_path}: {load_error}")
                        continue
            else:
                logger.warning("⚠️ Hiç fallback model bulunamadı, basit detection sistemi aktif")
                self.fallback_model = None
                
        logger.info(f"📊 Toplam {loaded_models} SH17 model yüklendi")
        
        # Eğer hiç SH17 model yüklenmediyse, fallback'i zorunlu kıl
        if loaded_models == 0:
            logger.warning("⚠️ Hiç SH17 model yüklenemedi, fallback sistemi aktif")
            self._ensure_fallback_model()
        
        return loaded_models > 0
    
    def _ensure_fallback_model(self):
        """Fallback model'in yüklü olduğundan emin ol"""
        if self.fallback_model is None:
            try:
                fallback_path = 'yolov8n.pt'
                if os.path.exists(fallback_path):
                    self.fallback_model = YOLO(fallback_path)
                    self.fallback_model.to(self.device)
                    logger.info(f"✅ Fallback model zorunlu yüklendi: {fallback_path}")
                else:
                    logger.error("❌ Fallback model bulunamadı!")
            except Exception as e:
                logger.error(f"❌ Fallback model yüklenemedi: {e}")
        
    def detect_ppe(self, image, sector='base', confidence=0.5):
        """PPE tespiti yap - SH17 veya fallback ile (OPTIMIZED)"""
        import time
        current_time = time.time()
        
        try:
            # 🚀 DETECTION THROTTLING - Çok sık detection'ı engelle
            cache_key = f"{sector}_{confidence}"
            if cache_key in self.last_detection_time:
                time_since_last = current_time - self.last_detection_time[cache_key]
                if time_since_last < self.detection_throttle:
                    # Cache'den son sonucu döndür
                    if cache_key in self.model_cache:
                        logger.debug(f"🚀 Cache'den detection sonucu döndürüldü: {sector}")
                        return self.model_cache[cache_key]
            
            # Önce SH17 model'i dene
            if sector in self.models and self.models[sector] is not None:
                logger.info(f"🎯 SH17 {sector} modeli ile detection")
                result = self._detect_with_sh17(image, sector, confidence)
                # String değil list döndür
                final_result = result if isinstance(result, list) else []
                
                # Cache'e kaydet
                self.model_cache[cache_key] = final_result
                self.last_detection_time[cache_key] = current_time
                
                return final_result
            
            # SH17 yoksa fallback kullan
            elif self.fallback_model is not None:
                logger.info(f"🔄 Fallback model ile detection (sector: {sector})")
                result = self._detect_with_fallback(image, sector, confidence)
                # String değil list döndür
                final_result = result if isinstance(result, list) else []
                
                # Cache'e kaydet
                self.model_cache[cache_key] = final_result
                self.last_detection_time[cache_key] = current_time
                
                return final_result
            
            else:
                logger.error("❌ Hiçbir model yüklü değil!")
                return []
                
        except Exception as e:
            logger.error(f"❌ Detection hatası: {e}")
            # Hata durumunda fallback'e geç
            try:
                result = self._detect_with_fallback(image, sector, confidence)
                final_result = result if isinstance(result, list) else []
                
                # Cache'e kaydet
                cache_key = f"{sector}_{confidence}"
                self.model_cache[cache_key] = final_result
                self.last_detection_time[cache_key] = current_time
                
                return final_result
            except:
                return []
            
    def _detect_with_sh17(self, image, sector, confidence):
        """SH17 model ile detection (OPTIMIZED)"""
        try:
            model = self.models[sector]
            if model is None:
                logger.warning(f"⚠️ SH17 {sector} modeli None")
                return []
            
            # 🚀 INFERENCE OPTIMIZATION - Daha hızlı detection
            results = model(image, conf=confidence, device=self.device, verbose=False)  # verbose=False for speed
        
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        try:
                            detection = {
                                'class_id': int(box.cls[0]),
                                'class_name': self.sh17_classes[int(box.cls[0])],
                                'confidence': float(box.conf[0]),
                                'bbox': box.xyxy[0].cpu().numpy().tolist(),
                                        'sector': sector,
                                        'model_type': 'SH17'
                                    }
                            detections.append(detection)
                        except Exception as box_error:
                            logger.warning(f"⚠️ Box processing hatası: {box_error}")
                            continue
                    
            return detections
            
        except Exception as e:
            logger.error(f"❌ SH17 detection hatası: {e}")
            return []
    
    def _detect_with_fallback(self, image, sector, confidence):
        """Fallback model ile detection (OPTIMIZED)"""
        try:
            if self.fallback_model is None:
                self._ensure_fallback_model()
                if self.fallback_model is None:
                    return []
            
            # 🚀 INFERENCE OPTIMIZATION - Daha hızlı detection
            results = self.fallback_model(image, conf=confidence, device=self.device, verbose=False)  # verbose=False for speed
            
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        try:
                            class_id = int(box.cls[0])
                            class_name = self.fallback_model.names[class_id]
                            
                            # Sadece person ve PPE ile ilgili sınıfları al
                            if class_name in ['person', 'helmet', 'safety_vest', 'gloves', 'safety_shoes']:
                                detection = {
                                    'class_id': class_id,
                                    'class_name': class_name,
                                    'confidence': float(box.conf[0]),
                                    'bbox': box.xyxy[0].cpu().numpy().tolist(),
                                    'sector': sector,
                                    'model_type': 'Fallback'
                            }
                            detections.append(detection)
                        except Exception as box_error:
                            logger.warning(f"⚠️ Fallback box processing hatası: {box_error}")
                            continue
                    
                        return detections
            
        except Exception as e:
            logger.error(f"❌ Fallback detection hatası: {e}")
            return []
        
    def detect_sector_specific(self, image, sector, confidence=0.5):
        """Sektör spesifik PPE tespiti"""
        if sector not in self.sector_mapping:
            logger.warning(f"⚠️ Bilinmeyen sektör: {sector}, 'construction' kullanılıyor")
            sector = 'construction'
        
        return self.detect_ppe(image, sector, confidence)
    
    def get_sector_requirements(self, sector):
        """Sektör için gerekli PPE listesi"""
        return self.sector_mapping.get(sector, self.sector_mapping['construction'])
    
    def analyze_compliance(self, detections, required_ppe):
        """PPE uyumluluk analizi"""
        if not detections:
            return {'compliant': False, 'missing': required_ppe, 'score': 0.0}
        
        detected_ppe = [d['class_name'] for d in detections if d['class_name'] in required_ppe]
        missing_ppe = [ppe for ppe in required_ppe if ppe not in detected_ppe]
        
        compliance_score = len(detected_ppe) / len(required_ppe) if required_ppe else 0.0
        
        return {
            'compliant': len(missing_ppe) == 0,
            'detected': detected_ppe,
            'missing': missing_ppe,
            'score': compliance_score,
            'total_required': len(required_ppe),
            'total_detected': len(detected_ppe)
        }
    
    def get_model_performance(self, sector='base'):
        """Model performans metrikleri"""
        if sector in self.models:
            return {
                'model_type': 'SH17',
                'sector': sector,
                'device': self.device,
                'status': 'Active'
            }
        elif self.fallback_model is not None:
            return {
                'model_type': 'Fallback',
                'sector': sector,
                'device': self.device,
                'status': 'Active'
            }
        else:
            return {
                'model_type': 'None',
                'sector': sector,
                'device': self.device,
                'status': 'Inactive'
            }
    
    def is_sh17_available(self, sector='base'):
        """SH17 model'in kullanılabilir olup olmadığını kontrol et"""
        return sector in self.models and self.models[sector] is not None
    
    def get_available_sectors(self):
        """Kullanılabilir sektörleri listele"""
        available = []
        for sector in self.sector_mapping.keys():
            if self.is_sh17_available(sector):
                available.append(sector)
        return available
    
    def get_system_status(self):
        """Sistem durumu raporu"""
        sh17_count = len([s for s in self.sector_mapping.keys() if self.is_sh17_available(s)])
        fallback_available = self.fallback_model is not None
        
        return {
            'sh17_models_loaded': sh17_count,
            'total_sectors': len(self.sector_mapping),
            'fallback_available': fallback_available,
            'device': self.device,
            'status': 'Operational' if (sh17_count > 0 or fallback_available) else 'Critical'
        }

    def clear_cache(self):
        """Model cache'ini temizle"""
        self.model_cache.clear()
        self.last_detection_time.clear()
        logger.info("🧹 Model cache temizlendi")
    
    def optimize_for_speed(self):
        """Detection hızını optimize et"""
        # Detection throttle'ı azalt
        self.detection_throttle = 0.05  # 50ms
        logger.info("🚀 Detection hızı optimize edildi - Throttle: 50ms")
    
    def optimize_for_accuracy(self):
        """Detection doğruluğunu optimize et"""
        # Detection throttle'ı artır
        self.detection_throttle = 0.2  # 200ms
        logger.info("🎯 Detection doğruluğu optimize edildi - Throttle: 200ms")
    
    def get_performance_stats(self):
        """Performans istatistikleri"""
        cache_size = len(self.model_cache)
        avg_detection_time = 0
        
        if self.last_detection_time:
            times = list(self.last_detection_time.values())
            if times:
                avg_detection_time = sum(times) / len(times)
        
                return {
            'cache_size': cache_size,
            'avg_detection_time': avg_detection_time,
            'throttle_ms': int(self.detection_throttle * 1000),
            'models_loaded': len(self.models),
            'fallback_available': self.fallback_model is not None
        }

def main():
    """Test fonksiyonu"""
    manager = SH17ModelManager()
    manager.load_models()
    
    print("📊 Sistem Durumu:")
    print(manager.get_system_status())
    
    print("\n🎯 Kullanılabilir Sektörler:")
    print(manager.get_available_sectors())

if __name__ == "__main__":
    main() 