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

from utils.torch_device import resolve_inference_device

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
    
    def _calculate_iou(self, box1, box2):
        """Intersection over Union calculation"""
        try:
            x1_1, y1_1, x2_1, y2_1 = box1
            x1_2, y1_2, x2_2, y2_2 = box2
            
            x1_i = max(x1_1, x1_2)
            y1_i = max(y1_1, y1_2)
            x2_i = min(x2_1, x2_2)
            y2_i = min(y2_1, y2_2)
            
            intersection = max(0, x2_i - x1_i) * max(0, y2_i - y1_i)
            area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
            area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
            union = area1 + area2 - intersection
            
            return intersection / max(union, 1e-6)
        except Exception:
            return 0.0

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
        # TORCH_DEVICE=auto|cpu|cuda|cuda:N — tek kaynak: utils/torch_device.py
        self.device = resolve_inference_device(logger=logger)
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
        
        # 🚀 FPS OPTIMIZATION
        self.sh17_imgsz = int(os.environ.get('SH17_IMGSZ', '640'))
        self.sh17_half = os.environ.get('SH17_HALF', '0') == '1' and self.device != 'cpu'
        
        logger.info(f"🎯 SH17 Model Manager başlatıldı - Device: {self.device}, imgsz: {self.sh17_imgsz}, half: {self.sh17_half}")
        
        # RENDER.COM OPTIMIZATION: Lazy loading if in production
        if not self.lazy_loading:
            # Modelleri otomatik yükle (sadece development'ta)
            self.load_models()
        else:
            logger.info("🚀 Production mode: Lazy loading enabled - models will load on demand")
        
        # 🎯 SINGLETON: İlk initialization tamamlandı
        SH17ModelManager._initialized = True
        logger.info("✅ SH17ModelManager initialization complete (Singleton)")
        
    # ── GPU memory management ────────────────────────────────────────────
    @staticmethod
    def _clear_gpu_cache():
        """Best-effort GPU cache flush after an OOM event."""
        if torch is not None and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except Exception:
                pass

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
          Tüm sektör-özel best.pt dosyaları(gıda sektörü hariç) aynı yolo9e.pt ağırlıklarıdır
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

        # Öncelik sırası: env (DETECTION_MODEL_PATH) -> yolo9e.pt -> sektör klasörlerinden biri -> yolov8n (fallback)
        candidate_paths = [
            os.environ.get('DETECTION_MODEL_PATH', str(Path(self.models_dir) / 'yolo9e.pt')),
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
        if hasattr(self, '_food_ppe_model') and self._food_ppe_model is not None:
            return self._food_ppe_model  # Zaten yüklü

        env_path = os.environ.get(
            'FOOD_PPE_LOCAL_MODEL',
            os.path.join('models', 'sh17_food_beverage',
                         'sh17_food_beverage_model', 'weights', 'best.pt')
        )

        # Birden fazla olası base dizine göre çözümleme yap.
        # .env dosyası genelde core/ dizinine göreli yol içerir,
        # ama script proje kökünden çalışabilir.
        candidates = [
            env_path,                                              # Olduğu gibi (mutlak veya CWD'ye göreli)
            os.path.join(self.models_dir, '..', env_path),         # core/ dizinine göreli
            os.path.join(os.path.dirname(__file__), '..', env_path),  # Bu dosyanın bulunduğu dizine göreli
            os.path.join(self.models_dir,                          # models_dir altında doğrudan
                         'sh17_food_beverage', 'sh17_food_beverage_model', 'weights', 'best.pt'),
        ]

        local_path = None
        logger.info(f"🔍 Food model search: models_dir={self.models_dir}")
        for i, candidate in enumerate(candidates):
            resolved = os.path.abspath(candidate)
            exists = os.path.exists(resolved)
            logger.info(f"   Candidate {i}: {resolved} (Exists: {exists})")
            if exists:
                local_path = resolved
                break

        if local_path is not None:
            logger.info(f"📂 Found Food PPE model at: {local_path}")
            try:
                model = YOLO(local_path)
                model.to(self.device)
                self._food_ppe_model = model
                actual_names = getattr(model, 'names', {})
                # Normal gıda modeli: çoğu checkpoint'te ayrı "haircap" yok; head + rescue ile çalışır — konsolu kirletme
                logger.debug(f"✅ Food PPE local model yüklendi: {local_path}")
                logger.debug(f"   Sınıflar (model.names): {actual_names}")
                haircap_in_model = [f"{k}:{v}" for k, v in actual_names.items()
                                    if v in self._FOOD_PPE_NAME_MAP and
                                    self._FOOD_PPE_NAME_MAP[v] == 'haircap']
                if haircap_in_model:
                    logger.debug(f"   Haircap sınıf(lar)ı model'de: {haircap_in_model}")
                else:
                    logger.debug(
                        "   Food model: haircap sınıfı yok (beklenen); head/rescue stratejisi kullanılacak. "
                        f"names={actual_names}"
                    )
                return model
            except Exception as e:
                logger.warning(f"⚠️ Food PPE local model yüklenemedi: {e}")
        else:
            logger.warning(f"⚠️ Food PPE model bulunamadı. Denenen yollar: {candidates}")

        self._food_ppe_model = None
        return None

    # Food PPE sınıf adı → canonical iç isim
    # NOT: Roboflow eğitim datasında typo'lar var (Googles, Appron).
    # Model ağırlıklarındaki sınıf adları data.yaml'dan farklı olabilir;
    # bu yüzden olası tüm varyantları ekliyoruz.
    _FOOD_PPE_NAME_MAP = {
        'Apron':    'medical_suit',   # Önlük → medical_suit surrogate
        'apron':    'medical_suit',
        'Appron':   'medical_suit',   # Model ağırlıklarındaki typo varyantı
        'appron':   'medical_suit',
        'Haircap':  'haircap',        # Saç filesi/bone
        'haircap':  'haircap',
        'Hair_cap': 'haircap',        # Olası model varyantları
        'hair_cap': 'haircap',
        'HairCap':  'haircap',
        'Hairnet':  'haircap',
        'hairnet':  'haircap',
        'Hair_net': 'haircap',
        'hair_net': 'haircap',
        'Bonnet':   'haircap',
        'bonnet':   'haircap',
        'Mask':     'face_mask_medical',
        'mask':     'face_mask_medical',
        'face-mask': 'face_mask_medical',
        'face_mask': 'face_mask_medical',
        'medical-suit': 'medical_suit',
        'safety-suit':  'safety_suit',
        'medical_suit': 'medical_suit',
        'safety_suit':  'safety_suit',
        'Googles':  'glasses',        # Roboflow typo: Googles = Goggles
        'googles':  'glasses',
        'goggles':  'glasses',
        'Goggles':  'glasses',
        'gloves':   'gloves',
        'Gloves':   'gloves',
    }

    # Food model confidence cap — configurable via env var FOOD_PPE_CONFIDENCE
    _FOOD_PPE_CONFIDENCE: float = float(os.environ.get('FOOD_PPE_CONFIDENCE', '0.45'))

    # Haircap is notoriously hard for the food model; use a separate lower threshold
    _HAIRCAP_RESCUE_CONF: float = float(os.environ.get('HAIRCAP_RESCUE_CONF', '0.15'))

    def _detect_with_food_model(self, image, confidence, sector_name='food_beverage'):
        """Local food PPE model ile detection — SH17'ye ek sınıfları döndürür."""
        model = self._load_food_ppe_model()
        if model is None:
            return []
        try:
            food_conf = min(confidence, self._FOOD_PPE_CONFIDENCE)
            img_h, img_w = image.shape[:2]
            food_imgsz = max(960, min(1280, max(img_h, img_w)))
            results = model(image, conf=food_conf, device=self.device, verbose=False, imgsz=food_imgsz)
            detections = []
            model_names = getattr(model, 'names', {})
            frame_area = max(img_h * img_w, 1)

            # ── Step 1: Primary Inference ──────────────────────────────────
            all_raw = []
            for result in results:
                if result.boxes is None: continue
                for box in result.boxes:
                    try:
                        cls_id = int(box.cls[0].item())
                        rn = model_names.get(cls_id, '?')
                        rc = float(box.conf[0].item())
                        rb = box.xyxy[0].cpu().numpy().tolist()
                        bw, bh = rb[2] - rb[0], rb[3] - rb[1]
                        cov = (bw * bh) / frame_area * 100
                        all_raw.append((rn, rc, cov, rb, cls_id))
                    except Exception: pass

            for rn, rc, cov, rb, cls_id in all_raw:
                if cov > 60: continue # Skip oversized background detections
                canonical = self._FOOD_PPE_NAME_MAP.get(rn, self._FOOD_PPE_NAME_MAP.get(rn.lower(), rn.lower()))
                detections.append({
                    'class_id': cls_id, 'class_name': canonical, 'confidence': rc,
                    'bbox': rb, 'sector': sector_name, 'model_type': 'FoodPPE-Local', 'raw_name': rn,
                })

            # ── Step 2: Rescue Pass ───────────────────────────────────────
            sector_required = self.sector_mapping.get(sector_name, [])
            missing_any = any(not any(d.get('class_name') == req for d in detections) for req in sector_required)
            
            if missing_any:
                _rescue_conf = float(os.environ.get('RESCUE_CONFIDENCE_THRESHOLD', 0.20))
                logger.debug(f"🆘 Triggering Rescue Pass (conf={_rescue_conf:.2f}) - Missing from {sector_required}")
                rescue_results = model(image, conf=_rescue_conf, device=self.device, verbose=False, imgsz=food_imgsz)
                
                logger.debug(f"🧬 Model classes detected: {model_names}")
                target_cls_ids = {k for k, v in model_names.items() if self._FOOD_PPE_NAME_MAP.get(v, self._FOOD_PPE_NAME_MAP.get(v.lower(), ''))}
                logger.debug(f"🎯 Target Class IDs for rescue: {target_cls_ids}")
                rescue_raw_list = []
                valid_rescue_count = 0

                for rr in rescue_results:
                    if rr.boxes is None: continue
                    for box in rr.boxes:
                        try:
                            cid = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            name = model_names.get(cid, f"ID_{cid}")
                            bbox = box.xyxy[0].cpu().numpy().tolist()
                            
                            # Her şeyi logla (ultra hassas)
                            if conf > 0.05:
                                logger.debug(f"🧪 Rescue RAW ALL: {name}({conf:.2f}) at {bbox}")

                            rescue_raw_list.append(f"{name}({conf:.2f})")
                            
                            if any(x in name.lower() for x in ['haircap', 'net', 'bone']):
                                logger.debug(f"👒 Found potential HAIRCAP in rescue: {name}({conf:.2f}) at bbox {bbox}")

                            if cid not in target_cls_ids: continue
                            
                            # 🚨 MANUEL FİLTRE: Konfigüre edilen eşiğin altındakileri asla kurtarma
                            if conf < float(os.environ.get('RESCUE_CONFIDENCE_THRESHOLD', 0.20)):
                                continue
                            
                            canon = self._FOOD_PPE_NAME_MAP.get(name, self._FOOD_PPE_NAME_MAP.get(name.lower(), ''))
                            if not canon: 
                                logger.debug(f"⏭️ Rescue SKIP: no canon for {name}")
                                continue
                            
                            is_duplicate = False
                            for e in detections:
                                iou = self._calculate_iou(bbox, e['bbox'])
                                if iou > 0.5:
                                    logger.debug(f"⏭️ Rescue SKIP: duplicate {canon} (IoU={iou:.2f})")
                                    is_duplicate = True
                                    break
                            if is_duplicate: continue

                            logger.debug(f"✨ Rescue SUCCESS: added {canon} ({conf:.2f}) from raw {name}")
                            detections.append({
                                'class_name': canon, 'confidence': conf, 'bbox': bbox,
                                'sector': sector_name, 'model_type': 'FoodPPE-Local-Rescue', 'raw_name': name,
                            })
                            valid_rescue_count += 1
                        except Exception: pass
                
                if rescue_raw_list:
                    rescued_items = []
                    for e in detections[-valid_rescue_count:] if valid_rescue_count > 0 else []:
                        if e.get('model_type') == 'FoodPPE-Local-Rescue':
                            rescued_items.append(f"{e.get('class_name')}({e.get('confidence'):.2f})")
                    
                    if valid_rescue_count > 0:
                        logger.info(f"🆘 Rescue Pass: Found {len(rescue_raw_list)} raw, rescued {valid_rescue_count}: {rescued_items}. Raw sample: {', '.join(rescue_raw_list[:5])}")
                    else:
                        logger.debug(f"🧪 Rescue: found {len(rescue_raw_list)} total, kept {valid_rescue_count} valid. Raw: {', '.join(rescue_raw_list[:15])}")
                else:
                    logger.debug("🧪 Rescue found NOTHING even at 0.05 conf.")

            # ── Step 3: Haircap Crop Fallback ──────────────────────────────
            # Eğer hala bone eksikse, kafaları kesip modele tekrar gönder (Slicing/SAHI mantığı)
            has_haircap = any(d.get('class_name') == 'haircap' for d in detections)
            if not has_haircap and 'haircap' in sector_required:
                from core.models.sh17_model_manager import SH17ModelManager
                # sh17_detections parametresi gerekiyor, ama burada elimizde yok.
                # Bu yüzden mevcut detections içindeki 'head'leri kullanabiliriz (eğer varsa).
                # Ancak daha iyisi, bu fonksiyonun çağrıldığı yerdeki tüm tespitleri kullanmak.
                pass 

            return detections
        except RuntimeError as e:
            if 'out of memory' in str(e).lower() or 'CUDA' in str(e):
                logger.warning(f"🔴 Food PPE CUDA OOM — clearing cache")
                self._clear_gpu_cache()
            else:
                logger.warning(f"⚠️ Food PPE detection hatası: {e}")
            return []
        except Exception as e:
            logger.warning(f"⚠️ Food PPE detection hatası: {e}")
            return []

    def _detect_haircap_by_head_crop(self, image, sh17_detections):
        """Fallback haircap detection: SH17 head tespitlerini crop'layıp food model'e yakınlaştırılmış gönder.

        SAHI (Slicing Aided Hyper Inference) mantığı: küçük nesneler (bone/haircap) tam
        frame'de tespit edilemeyebilir ama baş bölgesi kesilip büyütülünce
        model daha iyi görebilir.

        Eğer food model yine haircap bulamazsa, basit renk analizi ile
        beyaz/açık mavi bone varlığını kontrol eder (gıda fabrikasında boneler
        genelde beyaz veya açık mavi olur).
        """
        model = self._load_food_ppe_model()
        if model is None:
            return []

        head_dets = [d for d in sh17_detections
                     if d.get('class_name') == 'head' and d.get('bbox') and len(d.get('bbox', [])) == 4]
        if not head_dets:
            return []

        img_h, img_w = image.shape[:2]
        model_names = getattr(model, 'names', {})

        # Haircap class ID bul
        haircap_cls_id = None
        for k, v in model_names.items():
            canonical = self._FOOD_PPE_NAME_MAP.get(v, self._FOOD_PPE_NAME_MAP.get(v.lower(), ''))
            if canonical == 'haircap':
                haircap_cls_id = k
                break
        if haircap_cls_id is None:
            return []

        haircap_detections = []

        for head in head_dets:
            bbox = head['bbox']
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            w, h = x2 - x1, y2 - y1
            if w < 5 or h < 5:
                continue

            # Crop'u %50 genişlet (bağlam için)
            pad_x, pad_y = int(w * 0.5), int(h * 0.5)
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(img_w, x2 + pad_x)
            cy2 = min(img_h, y2 + pad_y)

            crop = image[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue

            # ── Strateji 1: Food model'i crop üzerinde çalıştır ──
            try:
                crop_results = model(crop, conf=0.01, device=self.device,
                                     verbose=False, imgsz=640)
                for cr in crop_results:
                    if cr.boxes is None:
                        continue
                    for box in cr.boxes:
                        cls_id = int(box.cls[0].item())
                        if cls_id != haircap_cls_id:
                            continue
                        rc = float(box.conf[0].item())
                        rb = box.xyxy[0].cpu().numpy().tolist()
                        # Bbox'ı orijinal frame koordinatlarına geri dönüştür
                        rb = [rb[0] + cx1, rb[1] + cy1, rb[2] + cx1, rb[3] + cy1]
                        haircap_detections.append({
                            'class_id': cls_id,
                            'class_name': 'haircap',
                            'confidence': rc,
                            'bbox': rb,
                            'sector': 'food',
                            'model_type': 'FoodPPE-HeadCrop',
                            'raw_name': model_names.get(cls_id, '?'),
                        })
            except Exception as e:
                logger.debug(f"🍽️ Head-crop inference failed: {e}")

        # ── Strateji 2: Renk analizi fallback ──
        # Eğer head-crop da haircap bulamadıysa, baş bölgesinin üst yarısında
        # beyaz/açık mavi renk analizi yap. Gıda fabrikasında boneler genelde
        # beyaz veya açık mavi tek-renkli olur.
        if not haircap_detections:
            for head in head_dets:
                bbox = head['bbox']
                x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(img_w, x2)
                y2 = min(img_h, y2)
                head_h = y2 - y1
                if head_h < 10 or (x2 - x1) < 10:
                    continue

                # Başın üst %50'sini al (bone bölgesi)
                crop_top = image[y1:y1 + int(head_h * 0.5), x1:x2]
                if crop_top.size == 0:
                    continue

                try:
                    import cv2 as _cv2
                    hsv = _cv2.cvtColor(crop_top, _cv2.COLOR_BGR2HSV)
                    h_ch, s_ch, v_ch = _cv2.split(hsv)
                    total_px = max(crop_top.shape[0] * crop_top.shape[1], 1)

                    # Beyaz bone: düşük satürasyon, yüksek parlaklık
                    white_mask = (s_ch < 60) & (v_ch > 150)
                    white_ratio = float(np.sum(white_mask)) / total_px

                    # Açık mavi bone: H 90-130, orta satürasyon, yüksek parlaklık
                    blue_mask = (h_ch >= 85) & (h_ch <= 135) & (s_ch >= 25) & (s_ch <= 160) & (v_ch > 110)
                    blue_ratio = float(np.sum(blue_mask)) / total_px

                    cap_ratio = white_ratio + blue_ratio

                    if cap_ratio > 0.35:  # Üst baş piksellerinin %35+ bone rengi
                        conf = min(0.70, 0.3 + cap_ratio * 0.5)
                        haircap_detections.append({
                            'class_id': -1,
                            'class_name': 'haircap',
                            'confidence': conf,
                            'bbox': [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                            'sector': 'food',
                            'model_type': 'ColorAnalysis-Fallback',
                            'raw_name': 'haircap_color',
                        })
                        logger.debug(f"🍽️ Color haircap: white={white_ratio:.0%} blue={blue_ratio:.0%} "
                                    f"total={cap_ratio:.0%} → conf={conf:.2f}")
                except ImportError:
                    logger.debug("cv2 not available for color analysis fallback")
                    break
                except Exception as e:
                    logger.debug(f"Color analysis failed: {e}")

        if haircap_detections:
            logger.debug(f"🍽️ Head-crop/color haircap rescue: {len(haircap_detections)} detections "
                        f"(types: {[d['model_type'] for d in haircap_detections]})")
        return haircap_detections

    def _filter_food_haircap_candidates(
        self,
        sh17_detections: List[Dict],
        food_detections: List[Dict],
        image_shape: Optional[Tuple[int, int]] = None,
    ) -> Tuple[List[Dict], bool]:
        """
        Food model 'haircap' false-positive'lerini baskıla.

        Neden gerekli?
        - Food model bazen frame'in alakasız bir bölgesinde devasa bir bbox'u 'haircap' diye etiketleyebiliyor.
        - Bu durumda `detect_ppe()` içindeki `has_haircap` True oluyor ve head-crop rescue hiç çalışmıyor.

        Strateji:
        - Haircap bbox'u en azından bir SH17 'head' bbox'u ile zayıf da olsa geometrik ilişki göstermeli.
          (IoU veya center-in-expanded-head)
        - Aksi halde haircap'i drop et ki rescue devreye girebilsin.
        """
        if not food_detections:
            return [], False

        head_boxes: List[List[float]] = [
            d.get("bbox") for d in (sh17_detections or [])
            if d.get("class_name") == "head" and isinstance(d.get("bbox"), list) and len(d.get("bbox")) == 4
        ]
        person_boxes: List[List[float]] = [
            d.get("bbox") for d in (sh17_detections or [])
            if d.get("class_name") == "person" and isinstance(d.get("bbox"), list) and len(d.get("bbox")) == 4
        ]
        # Face kutuları: food modelin haircap FP'lerini eleemek için kullanılır.
        # Bir haircap center'ı face bbox'ın İÇİNDE ise gerçek bone değil — bone
        # yüzün üstünde durur, yüz üzerinde değil.
        face_boxes: List[List[float]] = [
            d.get("bbox") for d in (sh17_detections or [])
            if d.get("class_name") == "face" and isinstance(d.get("bbox"), list) and len(d.get("bbox")) == 4
        ]

        img_h, img_w = (None, None)
        if image_shape and len(image_shape) == 2:
            img_h, img_w = int(image_shape[0]), int(image_shape[1])
        frame_area = float((img_h or 0) * (img_w or 0)) if (img_h and img_w and img_h > 0 and img_w > 0) else None

        def _iou(a: List[float], b: List[float]) -> float:
            try:
                ax1, ay1, ax2, ay2 = map(float, a)
                bx1, by1, bx2, by2 = map(float, b)
            except Exception:
                return 0.0
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0.0:
                return 0.0
            area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
            area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
            denom = area_a + area_b - inter
            return (inter / denom) if denom > 0.0 else 0.0

        def _center_in_expanded_box(hb: List[float], box: List[float], pad: float = 0.35) -> bool:
            # pad: bbox'u oran olarak genişlet, center'ın içinde olup olmadığına bak
            try:
                x1, y1, x2, y2 = map(float, hb)
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                bx1, by1, bx2, by2 = map(float, box)
                bw, bh = max(0.0, bx2 - bx1), max(0.0, by2 - by1)
                ex1 = bx1 - bw * pad
                ey1 = by1 - bh * pad
                ex2 = bx2 + bw * pad
                ey2 = by2 + bh * pad
                return (ex1 <= cx <= ex2) and (ey1 <= cy <= ey2)
            except Exception:
                return False

        filtered: List[Dict] = []
        dropped = 0
        haircap_dropped = False
        _no_overlap_bboxes: List[str] = []
        for det in food_detections:
            if det.get("class_name") != "haircap":
                filtered.append(det)
                continue

            hb = det.get("bbox") or []
            if not (isinstance(hb, list) and len(hb) == 4):
                dropped += 1
                haircap_dropped = True
                continue

            # Guard 0: invalid/degenerate bbox
            try:
                x1, y1, x2, y2 = map(float, hb)
                bw = x2 - x1
                bh = y2 - y1
                if bw <= 1 or bh <= 1:
                    dropped += 1
                    haircap_dropped = True
                    continue
                aspect = bw / max(bh, 1e-6)
            except Exception:
                dropped += 1
                haircap_dropped = True
                continue

            # Guard 1: "imkânsız haircap" (dev/abartılı bbox) — head/person olsa da drop
            cov = None
            if frame_area and frame_area > 0:
                cov = (bw * bh) / frame_area
            # Bu eşikler, sahadaki dev bbox bug'ını hedefliyor.
            if (cov is not None and cov >= 0.25) or (aspect >= 4.0) or (aspect <= 0.20):
                dropped += 1
                haircap_dropped = True
                logger.debug(
                    "🍽️ Food haircap dropped (guard): conf=%.3f bbox=%s cov=%.0f%% aspect=%.2f model_type=%s",
                    float(det.get("confidence", 0.0)),
                    [round(float(v), 1) for v in hb],
                    (cov * 100.0) if cov is not None else -1.0,
                    aspect,
                    det.get("model_type"),
                )
                continue

            # ── Guard 2: Anatomik "bone kafa ÜSTÜNDE olmalı" kontrolü ────
            # Food model cafe/restaurant arka plan dokularını (saç, duvar,
            # masa, bej kıyafet) sık sık haircap sanıyor. Gerçek bir bone:
            #   • Kafanın üst yarısında durur (merkez head'in üst %60'ında)
            #   • Yüzü örtmez (face bbox merkez haricap içinde değildir)
            # Bu iki kural FP'leri önemli ölçüde kırpar; gerçek bone'lar
            # kafa üstünde olduğu için etkilenmez.
            hb_cx = (x1 + x2) / 2.0
            hb_cy = (y1 + y2) / 2.0

            # (a) Face üzeri kontrol — haircap center'ı face bbox içinde ise FP.
            haircap_on_face = False
            for fb in face_boxes:
                try:
                    fx1, fy1, fx2, fy2 = map(float, fb)
                    if fx1 <= hb_cx <= fx2 and fy1 <= hb_cy <= fy2:
                        haircap_on_face = True
                        break
                except Exception:
                    continue

            if haircap_on_face:
                dropped += 1
                haircap_dropped = True
                _no_overlap_bboxes.append(
                    f"conf={float(det.get('confidence', 0.0)):.2f} face_overlap"
                )
                logger.debug(
                    "🍽️ Food haircap dropped (on-face): conf=%.3f bbox=%s",
                    float(det.get("confidence", 0.0)),
                    [round(float(v), 1) for v in hb],
                )
                continue

            best_iou = 0.0
            any_center_ok = False
            head_top_ok = False  # haircap center head üst %60'ında mı?

            # Primary: relate to SH17 head boxes (ideal)
            for head in head_boxes:
                best_iou = max(best_iou, _iou(hb, head))
                if _center_in_expanded_box(hb, head, pad=0.35):
                    any_center_ok = True
                # Head üst %60 anatomik kontrolü
                try:
                    hx1, hy1, hx2, hy2 = map(float, head)
                    head_h = hy2 - hy1
                    head_w = hx2 - hx1
                    if head_h > 1 and head_w > 1:
                        y_top_limit = hy1 + head_h * 0.60
                        y_above_limit = hy1 - head_h * 0.30
                        x_left_limit = hx1 - head_w * 0.25
                        x_right_limit = hx2 + head_w * 0.25
                        if (
                            y_above_limit <= hb_cy <= y_top_limit
                            and x_left_limit <= hb_cx <= x_right_limit
                        ):
                            head_top_ok = True
                except Exception:
                    pass

            # (b) Head var ama haircap kafanın ALT yarısında / yanında →
            # gerçek bone değil. IoU/center-overlap geçse bile drop.
            if head_boxes and not head_top_ok:
                dropped += 1
                haircap_dropped = True
                _no_overlap_bboxes.append(
                    f"conf={float(det.get('confidence', 0.0)):.2f} not_head_top"
                )
                logger.debug(
                    "🍽️ Food haircap dropped (not-head-top): conf=%.3f bbox=%s",
                    float(det.get("confidence", 0.0)),
                    [round(float(v), 1) for v in hb],
                )
                continue

            # Fallback: if head is missing, relate to SH17 person boxes.
            # İyileştirme: person bbox full + upper-body proxy (üst %35 ~ baş/omuz bölgesi).
            # SH17 head bulamadığında bu proxy head region yerine geçer.
            if not head_boxes and person_boxes:
                for pb in person_boxes:
                    best_iou = max(best_iou, _iou(hb, pb))
                    # pad 0.15 → 0.25 (person bbox kenar kaydığı durumları yakala)
                    if _center_in_expanded_box(hb, pb, pad=0.25):
                        any_center_ok = True
                    # Upper-body head proxy — person'un üst %35'lik bölgesi
                    try:
                        px1, py1, px2, py2 = map(float, pb)
                        p_h = py2 - py1
                        if p_h > 1:
                            upper_box = [px1, py1, px2, py1 + p_h * 0.35]
                            best_iou = max(best_iou, _iou(hb, upper_box))
                            if _center_in_expanded_box(hb, upper_box, pad=0.30):
                                any_center_ok = True
                    except Exception:
                        pass

            # heads=0 AND persons=0 → SH17 henüz kimseyi görmemiş olabilir;
            # guard'lardan geçmiş geçerli haircap'leri drop etme,
            # nihai association pose_aware_ppe_detector'a bırakılır.
            if not head_boxes and not person_boxes:
                filtered.append(det)
                logger.debug(
                    "🍽️ Food haircap kept (no heads/persons to relate): conf=%.3f bbox=%s",
                    float(det.get("confidence", 0.0)),
                    [round(float(v), 1) for v in hb],
                )
                continue

            if best_iou >= 0.005 or any_center_ok:
                filtered.append(det)
            else:
                # ── High-confidence haircap rescue ────────────────────────────
                # Food model yüksek conf ile haircap diyor ama SH17 ne head ne
                # de person ile IoU/center eşleşmesi üretemedi. İki yaygın neden:
                #   (a) SH17 bu kişinin kafasını hiç algılayamadı (head_boxes=0)
                #   (b) SH17 bazı kişilerin kafasını algılıyor, bazılarınınkini
                #       algılayamıyor — haircap kafasız kişiye ait.
                # Her iki durumda da pose_aware_ppe_detector'un IoU+proximity
                # fallback'leri haircap'i doğru kişiye bağlayabilir; filter
                # aşamasında drop etmek yerine nihai karar orada verilsin.
                try:
                    _cf = float(det.get("confidence", 0.0))
                except Exception:
                    _cf = 0.0

                _rescued = False
                # Case (a): head yok, person var — conf >= 0.50
                if not head_boxes and person_boxes and _cf >= 0.50:
                    _rescued = True
                    _rescue_reason = "no-head"
                # Case (b): head < person (kafaları eksik yakalanmış) ve haircap
                #          merkezi person'lardan birinin üst %45'inde — conf >= 0.55
                elif (
                    head_boxes
                    and person_boxes
                    and len(head_boxes) < len(person_boxes)
                    and _cf >= 0.55
                ):
                    try:
                        hx1, hy1, hx2, hy2 = map(float, hb)
                        hcx = (hx1 + hx2) / 2.0
                        hcy = (hy1 + hy2) / 2.0
                        for pb in person_boxes:
                            px1, py1, px2, py2 = map(float, pb)
                            p_h = py2 - py1
                            if p_h <= 1:
                                continue
                            if (
                                px1 <= hcx <= px2
                                and py1 <= hcy <= py1 + p_h * 0.45
                            ):
                                _rescued = True
                                _rescue_reason = "partial-head"
                                break
                    except Exception:
                        pass

                if _rescued:
                    filtered.append(det)
                    logger.debug(
                        "🍽️ Food haircap kept (%s rescue, conf=%.3f): bbox=%s",
                        _rescue_reason, _cf, [round(float(v), 1) for v in hb],
                    )
                    continue

                dropped += 1
                haircap_dropped = True
                _no_overlap_bboxes.append(
                    f"conf={_cf:.2f} iou={best_iou:.4f}"
                )

        if dropped or filtered:
            no_overlap_str = f" | no_overlap({len(_no_overlap_bboxes)}): [{', '.join(_no_overlap_bboxes[:5])}]" if _no_overlap_bboxes else ""
            logger.debug(
                f"🍽️ Haircap filter: dropped={dropped} kept={len(filtered)} "
                f"heads={len(head_boxes)} persons={len(person_boxes)}{no_overlap_str}"
            )
        return filtered, haircap_dropped

    def detect_ppe(self, image, sector='base', confidence=0.5):
        """PPE tespiti — SH17 + food sektörü için dual-model desteği."""
        is_food = sector in ('food', 'food_beverage')
        try:
            # ── Adım 1: SH17 (genel PPE) ──────────────────────────────────
            # Food sektöründe safety_suit/apron genelde 0.35-0.45 aralığında
            # tespit ediliyor; 0.5 threshold çok yüksek. Food için conf düşür.
            sh17_conf = min(confidence, 0.30) if is_food else confidence
            if sector in self.models and self.models[sector] is not None:
                logger.debug(f"🎯 SH17 {sector} modeli ile detection (conf={sh17_conf})")
                sh17_results = self._detect_with_sh17(image, sector, sh17_conf)
            elif self.models:
                sh17_results = self._detect_with_sh17(image, sector, sh17_conf)
            elif self.fallback_model is not None:
                logger.debug(f"🔄 Fallback model ile detection (sector: {sector})")
                sh17_results = self._detect_with_fallback(image, sector, sh17_conf)
            else:
                logger.error("❌ Hiçbir model yüklü değil!")
                sh17_results = []

            sh17_results = sh17_results if isinstance(sh17_results, list) else []

            # ── Adım 2: Gıda sektörü → food PPE local model ekle ──────────
            if is_food:
                self._clear_gpu_cache()
                food_results = self._detect_with_food_model(image, confidence, sector_name=sector)
                if food_results:
                    # Food model haircap false-positive'leri rescue'yu kilitleyebilir.
                    # Bu yüzden haircap adaylarını SH17 head bboxes ile tutarlı olacak şekilde filtrele.
                    food_results, food_haircap_dropped = self._filter_food_haircap_candidates(
                        sh17_results,
                        food_results,
                        image_shape=image.shape[:2] if hasattr(image, "shape") else None,
                    )
                    sh17_results.extend(food_results)
                    logger.debug(f"🍽️ Food merge: +{len(food_results)} food tespit → toplam {len(sh17_results)}")
                else:
                    food_haircap_dropped = False

                # ── Adım 3: Haircap head-crop rescue ──────────────────────
                # Food model haircap bulamadıysa, SH17 head tespitlerini
                # crop'layıp yakınlaştırarak tekrar dene + renk analizi fallback
                has_haircap = any(d.get('class_name') == 'haircap' for d in sh17_results)
                # Güçlendirilmiş gating:
                # - Haircap yoksa rescue çalışır (eski davranış)
                # - FoodPPE-Local haircap drop edildiyse de rescue çalışır (yanlış haircap "var" diye rescue kilitlenmesin)
                if (not has_haircap) or food_haircap_dropped:
                    head_crop_results = self._detect_haircap_by_head_crop(image, sh17_results)
                    if head_crop_results:
                        sh17_results.extend(head_crop_results)

            return sh17_results

        except RuntimeError as e:
            if 'out of memory' in str(e).lower() or 'CUDA' in str(e):
                logger.error(f"🔴 detect_ppe CUDA OOM — clearing cache")
                self._clear_gpu_cache()
            else:
                logger.error(f"❌ Detection hatası: {e}")
            return []
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

            results = model(
                image, 
                conf=confidence, 
                device=self.device, 
                verbose=False,
                imgsz=self.sh17_imgsz,
                half=self.sh17_half
            )

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

        except RuntimeError as e:
            if 'out of memory' in str(e).lower() or 'CUDA' in str(e):
                logger.error(f"🔴 SH17 CUDA OOM — clearing cache")
                self._clear_gpu_cache()
            else:
                logger.error(f"❌ SH17 detection hatası: {e}")
            return []
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
    
    _COMPLIANCE_ALIASES = {
        'hairnet': ['haircap', 'Haircap', 'bone', 'hair_net'],
        'hair_net': ['haircap', 'Haircap', 'bone', 'hairnet'],
        'apron': ['safety_suit', 'Safety Suit', 'medical_suit', 'Apron'],
        'face_mask': ['Face Mask', 'face_mask_medical', 'Mask'],
        'gloves': ['Gloves'],
        'helmet': ['Helmet', 'hard_hat', 'hardhat'],
        'safety_vest': ['Safety Vest', 'vest'],
    }

    def analyze_compliance(self, detections, required_ppe):
        """PPE uyumluluk analizi — alias mapping ile."""
        if not detections:
            return {'compliant': False, 'missing': required_ppe, 'score': 0.0}

        det_names = {d.get('class_name', '') for d in detections if isinstance(d, dict)}

        def _is_detected(ppe_name):
            if ppe_name in det_names:
                return True
            for alias in self._COMPLIANCE_ALIASES.get(ppe_name, []):
                if alias in det_names:
                    return True
            return False

        detected_ppe = [ppe for ppe in required_ppe if _is_detected(ppe)]
        missing_ppe = [ppe for ppe in required_ppe if not _is_detected(ppe)]

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