#!/usr/bin/env python3
"""
SH17 Model Manager
SmartSafe AI - PPE Detection Model Integration
"""

import os
import yaml
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

try:
    import torch
except ImportError:
    torch = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

logger = logging.getLogger(__name__)

class SH17ModelManager:
    """
    🎯 SINGLETON PATTERN - Sadece 1 instance oluşturulur
    Bu sayede modeller sadece 1 kere yüklenir ve memory tasarrufu sağlanır
    """
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - sadece 1 instance oluştur"""
        if cls._instance is None:
            logger.info("🆕 Creating new SH17ModelManager instance (Singleton)")
            cls._instance = super(SH17ModelManager, cls).__new__(cls)
        else:
            logger.info("♻️ Reusing existing SH17ModelManager instance (Singleton)")
        return cls._instance
    
    def __init__(self, models_dir='models'):
        # Singleton pattern - sadece ilk instance'da initialize et
        if self._initialized:
            logger.info("✅ SH17ModelManager already initialized, skipping...")
            return
            
        logger.info("🔧 Initializing SH17ModelManager for the first time...")
        # Normalize models_dir to an absolute path so it does not depend on CWD
        models_dir_path = Path(models_dir)
        if not models_dir_path.is_absolute():
            # Anchor relative paths to the directory containing this file (the project 'models' folder)
            file_dir = Path(__file__).resolve().parent  # .../models
            if models_dir_path == Path("models"):
                # Default case: use this file's parent directory
                resolved = file_dir
            else:
                resolved = file_dir / models_dir_path
            self.models_dir = str(resolved)
        else:
            self.models_dir = str(models_dir_path)
        # Prefer GPU when available for faster inference; fall back to CPU otherwise.
        if torch is not None and torch.cuda.is_available():
            self.device = 'cuda'
        else:
            self.device = 'cpu'
        self.models = {}
        self.fallback_model = None
        
        # 🚀 PERFORMANCE OPTIMIZATION - Model caching ve inference hızlandırma
        self.model_cache = {}  # Model cache
        self.last_detection_time = {}  # Son detection zamanları
        self.detection_throttle = 0.0  # Detection throttle KAPALI - Her frame detection
        
        # 🚀 RENDER.COM MEMORY OPTIMIZATION
        self.is_production = os.environ.get('RENDER') is not None
        self.lazy_loading = self.is_production  # Production'da lazy loading aktif
        
        # 🚀 MODEL CACHE OPTIMIZATION - Production'da model cache'i enable et
        self.enable_model_cache = self.is_production
        logger.info(f"🎯 Production mode: {self.is_production}, Lazy loading: {self.lazy_loading}, Model cache: {self.enable_model_cache}")
        
        # ── Sektör bazlı zorunlu PPE gereksinimleri ───────────────────────
        # ÖNEMLI: Bu listeler SH17 model sinif adlarıyla eşleşmeli.
        # SH17 sinifları: person, head, face, glasses, face_mask_medical, face_guard,
        #                  ear, earmuffs, hands, gloves, foot, shoes, safety_vest,
        #                  tools, helmet, medical_suit, safety_suit
        self.sector_mapping = {
            # İnşaat: kask zorunlu, yansıtıcı yelek, eldiven, ayakkabı
            'construction':        ['helmet', 'safety_vest', 'gloves', 'shoes'],
            # İmalat: kask, yelek, eldiven, gözlük
            'manufacturing':       ['helmet', 'safety_vest', 'gloves', 'glasses'],
            # Kimya: kask, maske/respiratör, eldiven, gözlük, tulum
            'chemical':            ['helmet', 'face_mask_medical', 'gloves', 'glasses', 'safety_suit'],
            # Gida/Içecek: bone→head, hijyen maskesi→face_mask_medical, eldiven, önlük→medical_suit
            # NOT: SH17 bonnet/hair_net görmez ama 'head' tespiti (saç/baş bölgesi) surrogate olarak kullanılır.
            # Gerçek bone tespiti için ek model ('food_ppe') gerekir — model_manager bunu yönetir.
            'food_beverage':       ['head', 'face_mask_medical', 'gloves', 'medical_suit'],
            # Depo/Lojistik: kask, yelek, eldiven, ayakkabı
            'warehouse_logistics': ['helmet', 'safety_vest', 'gloves', 'shoes'],
            # Enerji: kask, yelek, ayakkabı, eldiven, tulum
            'energy':              ['helmet', 'safety_vest', 'shoes', 'gloves', 'safety_suit'],
            # Petrokimya: kask, maske, yelek, eldiven, tulum, gözlük
            'petrochemical':       ['helmet', 'face_mask_medical', 'safety_vest', 'gloves', 'safety_suit', 'glasses'],
            # Denizcilik/Tersane: kask, yelek, eldiven, ayakkabı, gözlük
            'marine_shipyard':     ['helmet', 'safety_vest', 'gloves', 'shoes', 'glasses'],
            # Havacılık: kask, yelek, eldiven, gözlük, maske
            'aviation':            ['helmet', 'safety_vest', 'gloves', 'glasses', 'face_mask_medical'],
            # food (alias — landing page food sektörü için)
            'food':                ['head', 'face_mask_medical', 'gloves', 'medical_suit'],
            # warehouse (alias)
            'warehouse':           ['helmet', 'safety_vest', 'gloves', 'shoes'],
        }

        # SH17 class mapping - DICT olmalı!
        self.sh17_classes = {
            0: 'person', 1: 'head', 2: 'face', 3: 'glasses', 4: 'face_mask_medical',
            5: 'face_guard', 6: 'ear', 7: 'earmuffs', 8: 'hands', 9: 'gloves',
            10: 'foot', 11: 'shoes', 12: 'safety_vest', 13: 'tools', 14: 'helmet',
            15: 'medical_suit', 16: 'safety_suit'
        }
        
        logger.info(f"🎯 SH17 Model Manager başlatıldı - Device: {self.device}")
        
        # RENDER.COM OPTIMIZATION: Lazy loading if in production
        if not self.lazy_loading:
            # Modelleri otomatik yükle (sadece development'ta)
            self.load_models()
        else:
            logger.info("🚀 Production mode: Lazy loading enabled - models will load on demand")
        
        # 🎯 SINGLETON: İlk initialization tamamlandı
        SH17ModelManager._initialized = True
        logger.info("✅ SH17ModelManager initialization complete (Singleton)")
        
    # ─── Canonical SH17 class-name normalisation ───────────────────────────────
    # Model output names  →  our internal names used in sector_mapping & PPE_CONFIG
    #
    # IMPORTANT: SH17 yolo9e.pt sinıfları GERÇEK PPE'lere 1:1 map edilmiyor;
    # bazı sektörler için alias kullanılıyor (örn. food→head surrogate for bonnet).
    # Gerçek resolution: sektöre özel ek model (gelecek) veya fine-tuned checkpoint.
    _SH17_NAME_MAP = {
        # Model raw names → canonical internal names
        'ear-mufs':      'earmuffs',
        'ear_mufs':      'earmuffs',
        'face-mask':     'face_mask_medical',
        'face_mask':     'face_mask_medical',
        'face-guard':    'face_guard',
        'tool':          'tools',
        'medical-suit':  'medical_suit',
        'safety-suit':   'safety_suit',
        'safety-vest':   'safety_vest',
        'glove':         'gloves',
        'goggles':       'glasses',
        'safety_glasses':'glasses',
        'mask':          'face_mask_medical',
        'respirator':    'face_mask_medical',  # SH17 respiratörü face_mask ile yakın
        'hard_hat':      'helmet',
        'hardhat':       'helmet',
        'baret':         'helmet',
        # Gıda sektörü alias: SH17 bonnet/hair_net görmez → head surrogate
        'bonnet':        'head',
        'hair_net':      'head',
        'hair_cap':      'head',
        'hygienic_cap':  'head',
        # Güvenlik koşum takımı: SH17'de yok → safety_suit surrogate
        'safety_harness':'safety_suit',
        'harness':       'safety_suit',
        # Ayakkabı
        'boot':          'shoes',
        'safety_boot':   'shoes',
        'safety_shoes':  'shoes',
    }

    @classmethod
    def _normalize_class_name(cls, raw: str) -> str:
        """Model sınıf adını kanonik iç adına dönüştür."""
        return cls._SH17_NAME_MAP.get(raw, raw.replace('-', '_'))

    def load_models(self):
        """
        Tek SH17 modeli yükle (yolo9e.pt) ve tüm sektörlere paylaştır.

        NEDEN TEK MODEL:
          Tüm sektör-özel best.pt dosyaları aynı yolo9e.pt ağırlıklarıdır
          (MD5 doğrulandı). 10 kopyayı ayrı ayrı yüklemek 10× bellek harcar.
          Sektör farklılığı PPE gereksinimleri (sector_mapping) üzerinden yapılır.
        """
        if YOLO is None:
            logger.error("❌ ultralytics not installed, cannot load models")
            return False

        if self.models:
            logger.info("✅ SH17 modeli zaten yüklü, skip ediliyor...")
            return True

        logger.info("📦 SH17 yolo9e.pt modeli yükleniyor...")

        # Öncelik sırası: yolo9e.pt → sektör klasörlerinden biri → yolov8n (fallback)
        candidate_paths = [
            str(Path(self.models_dir) / 'yolo9e.pt'),
            str(Path(self.models_dir) / 'sh17_base' / 'sh17_base_model' / 'weights' / 'best.pt'),
            str(Path(self.models_dir) / 'sh17_construction' / 'sh17_construction_model' / 'weights' / 'best.pt'),
        ]

        self._has_real_sh17 = False
        primary_model = None

        for path in candidate_paths:
            if not os.path.exists(path):
                continue
            try:
                m = YOLO(path)
                m.to(self.device)
                nc = len(getattr(m, 'names', {}))
                if nc == 17:
                    self._has_real_sh17 = True
                    primary_model = m
                    logger.info(f"✅ SH17 model yüklendi (17 sınıf): {path}")
                    break
                else:
                    logger.warning(f"⚠️ {path}: {nc} sınıf — SH17 değil, atlandı")
            except Exception as e:
                logger.warning(f"⚠️ Model yüklenemedi {path}: {e}")

        if primary_model is not None:
            # Tek model tüm sektörlere paylaştırılır — sektör ayrımı requirements'tan gelir
            sectors = list(self.sector_mapping.keys()) + ['base']
            for s in sectors:
                self.models[s] = primary_model
            logger.info(f"🔀 Tek SH17 model {len(self.models)} sektöre paylaştırıldı (shared reference, bellek: 1×)")
        else:
            logger.warning("⚠️ Hiç SH17 model bulunamadı — fallback yüklenecek")

        # Fallback (COCO yolov8n) — sadece SH17 yoksa devreye girer
        if not self._has_real_sh17:
            self._ensure_fallback_model()

        loaded = len(self.models)
        logger.info(f"📊 SH17 sektör coverage: {loaded} sektör, real_sh17={self._has_real_sh17}")
        return loaded > 0

    def _ensure_fallback_model(self):
        """Fallback model'in yüklü olduğundan emin ol"""
        if self.fallback_model is not None:
            return
        fallback_candidates = [
            str(Path(self.models_dir).parent / 'core' / 'yolov8n.pt'),
            'yolov8n.pt',
        ]
        for path in fallback_candidates:
            if os.path.exists(path):
                try:
                    self.fallback_model = YOLO(path)
                    self.fallback_model.to(self.device)
                    logger.info(f"✅ Fallback model yüklendi: {path}")
                    return
                except Exception as e:
                    logger.warning(f"⚠️ Fallback yüklenemedi {path}: {e}")
        # Son çare: auto-download
        try:
            self.fallback_model = YOLO('yolov8n.pt')
            self.fallback_model.to(self.device)
            logger.info("✅ YOLOv8n fallback auto-downloaded")
        except Exception as e:
            logger.error(f"❌ Fallback model tamamen başarısız: {e}")
            self.fallback_model = None

    def get_model(self, sector='base'):
        """Model al — tüm sektörler için shared SH17 modeli döndür"""
        # Eğer model yüklüyse hepsine aynı shared instance döner
        if sector in self.models:
            return self.models[sector]
        # Lazy: yüklemediyse yükle
        if not self.models:
            self.load_models()
        if sector in self.models:
            return self.models[sector]
        # Base veya fallback
        if self.models:
            return next(iter(self.models.values()))
        self._ensure_fallback_model()
        return self.fallback_model

    def _load_food_ppe_model(self):
        """Gıda sektörü için local food_ppe modelini yükle (lazy, bir kez)."""
        if hasattr(self, '_food_ppe_model'):
            return self._food_ppe_model  # Zaten yüklü

        local_path = os.environ.get(
            'FOOD_PPE_LOCAL_MODEL',
            os.path.join(self.models_dir, 'sh17_food_beverage',
                         'sh17_food_beverage_model', 'weights', 'best.pt')
        )
        if os.path.exists(local_path):
            try:
                model = YOLO(local_path)
                model.to(self.device)
                self._food_ppe_model = model
                logger.info(f"✅ Food PPE local model yüklendi: {local_path}")
                return model
            except Exception as e:
                logger.warning(f"⚠️ Food PPE local model yüklenemedi: {e}")
        self._food_ppe_model = None
        return None

    # Food PPE sınıf adı → canonical iç isim
    _FOOD_PPE_NAME_MAP = {
        'Apron':    'medical_suit',   # Önlük → medical_suit surrogate
        'apron':    'medical_suit',
        'Haircap':  'head',           # Saç filesi/bone → head surrogate
        'haircap':  'head',
        'Mask':     'face_mask_medical',
        'mask':     'face_mask_medical',
        'Googles':  'glasses',        # Roboflow typo: Googles = Goggles
        'googles':  'glasses',
        'Goggles':  'glasses',
        'gloves':   'gloves',
        'Gloves':   'gloves',
    }

    def _detect_with_food_model(self, image, confidence):
        """Local food PPE model ile detection — SH17'ye ek sınıfları döndürür."""
        model = self._load_food_ppe_model()
        if model is None:
            return []
        try:
            results = model(image, conf=confidence, device=self.device, verbose=False)
            detections = []
            model_names = getattr(model, 'names', {})
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    try:
                        raw_name = model_names.get(int(box.cls[0].item()), 'unknown')
                        canonical = self._FOOD_PPE_NAME_MAP.get(raw_name, raw_name.lower())
                        detections.append({
                            'class_id': int(box.cls[0].item()),
                            'class_name': canonical,
                            'confidence': float(box.conf[0].item()),
                            'bbox': box.xyxy[0].cpu().numpy().tolist(),
                            'sector': 'food',
                            'model_type': 'FoodPPE-Local',
                            'raw_name': raw_name,
                        })
                    except Exception:
                        continue
            logger.debug(f"🍽️ Food PPE local: {len(detections)} tespit")
            return detections
        except Exception as e:
            logger.warning(f"⚠️ Food PPE detection hatası: {e}")
            return []

    def detect_ppe(self, image, sector='base', confidence=0.5):
        """PPE tespiti — SH17 + food sektörü için dual-model desteği."""
        is_food = sector in ('food', 'food_beverage')
        try:
            # ── Adım 1: SH17 (genel PPE) ──────────────────────────────────
            if sector in self.models and self.models[sector] is not None:
                logger.debug(f"🎯 SH17 {sector} modeli ile detection")
                sh17_results = self._detect_with_sh17(image, sector, confidence)
            elif self.models:
                sh17_results = self._detect_with_sh17(image, sector, confidence)
            elif self.fallback_model is not None:
                logger.debug(f"🔄 Fallback model ile detection (sector: {sector})")
                sh17_results = self._detect_with_fallback(image, sector, confidence)
            else:
                logger.error("❌ Hiçbir model yüklü değil!")
                sh17_results = []

            sh17_results = sh17_results if isinstance(sh17_results, list) else []

            # ── Adım 2: Gıda sektörü → food PPE local model ekle ──────────
            if is_food:
                food_results = self._detect_with_food_model(image, confidence)
                if food_results:
                    # Merge: food sonuçları ekle (duplicate class_name'leri SH17 öncelikli)
                    existing_classes = {d['class_name'] for d in sh17_results}
                    for det in food_results:
                        if det['class_name'] not in existing_classes:
                            sh17_results.append(det)
                    logger.debug(f"🍽️ Food merge: toplam {len(sh17_results)} tespit")

            return sh17_results

        except Exception as e:
            logger.error(f"❌ Detection hatası: {e}")
            try:
                return self._detect_with_fallback(image, sector, confidence) or []
            except Exception:
                return []

            
    def _detect_with_sh17(self, image, sector, confidence):
        """SH17 model ile detection"""
        try:
            model = self.get_model(sector)
            if model is None:
                logger.warning(f"⚠️ SH17 {sector} modeli None")
                return []

            results = model(image, conf=confidence, device=self.device, verbose=False)

            model_names = getattr(model, 'names', {})
            num_classes = len(model_names)
            is_coco = num_classes == 80
            is_10class_ppe = num_classes == 10

            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is None or len(boxes) == 0:
                    continue
                for box in boxes:
                    try:
                        cls_tensor = box.cls
                        conf_tensor = box.conf
                        xyxy_tensor = box.xyxy
                        if not len(cls_tensor) or not len(conf_tensor) or not len(xyxy_tensor):
                            continue

                        class_id = int(cls_tensor[0].item())
                        det_confidence = float(conf_tensor[0].item())
                        bbox = xyxy_tensor[0].cpu().numpy().tolist()
                        raw_name = model_names.get(class_id, 'unknown')

                        if is_coco:
                            # COCO: sadece 'person' ile PPE analizi yapılabilir
                            if raw_name != 'person':
                                continue
                            class_name = raw_name
                            model_type = 'Fallback-COCO'
                        elif is_10class_ppe:
                            if raw_name.startswith('no_'):
                                continue
                            class_name = self._normalize_class_name(raw_name)
                            model_type = 'PPE-10'
                        else:
                            # 17-class SH17 veya diğer: canonical normalize
                            class_name = self._normalize_class_name(raw_name)
                            model_type = 'SH17'

                        detections.append({
                            'class_id': class_id,
                            'class_name': class_name,
                            'confidence': det_confidence,
                            'bbox': bbox,
                            'sector': sector,
                            'model_type': model_type
                        })
                    except Exception as box_error:
                        logger.warning(f"⚠️ Box processing hatası: {box_error}")
                        continue

            return detections

        except Exception as e:
            logger.error(f"❌ SH17 detection hatası: {e}")
            return []

    
    def _detect_with_fallback(self, image, sector, confidence):
        """Fallback model ile detection - COCO person + PPE mapping"""
        try:
            if self.fallback_model is None:
                self._ensure_fallback_model()
                if self.fallback_model is None:
                    return []
            
            results = self.fallback_model(image, conf=confidence, device=self.device, verbose=False)
            
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        try:
                            class_id = int(box.cls[0])
                            class_name = self.fallback_model.names[class_id]
                            
                            # COCO model: only 'person' is relevant for PPE pipeline.
                            # PPE items (helmet, vest, etc.) are NOT in COCO classes.
                            # We pass person detections so downstream PoseAwarePPEDetector
                            # can handle anatomical region analysis.
                            if class_name == 'person':
                                detection = {
                                    'class_id': class_id,
                                    'class_name': class_name,
                                    'confidence': float(box.conf[0]),
                                    'bbox': box.xyxy[0].cpu().numpy().tolist(),
                                    'sector': sector,
                                    'model_type': 'Fallback-COCO'
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
        has_real_sh17 = getattr(self, '_has_real_sh17', False)
        
        return {
            'sh17_models_loaded': sh17_count,
            'has_trained_sh17_models': has_real_sh17,
            'total_sectors': len(self.sector_mapping),
            'fallback_available': fallback_available,
            'device': self.device,
            'status': 'Operational' if (sh17_count > 0 or fallback_available) else 'Critical',
            'note': 'Using trained SH17 models' if has_real_sh17 else 'Using COCO fallback (PPE training required)'
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