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
        for candidate in candidates:
            resolved = os.path.abspath(candidate)
            if os.path.exists(resolved):
                local_path = resolved
                break

        if local_path is not None:
            try:
                model = YOLO(local_path)
                model.to(self.device)
                self._food_ppe_model = model
                actual_names = getattr(model, 'names', {})
                logger.info(f"✅ Food PPE local model yüklendi: {local_path}")
                logger.info(f"   Sınıflar (model.names): {actual_names}")
                # Haircap sınıfının model.names'de mevcut olup olmadığını kontrol et
                haircap_in_model = [f"{k}:{v}" for k, v in actual_names.items()
                                    if v in self._FOOD_PPE_NAME_MAP and
                                    self._FOOD_PPE_NAME_MAP[v] == 'haircap']
                if haircap_in_model:
                    logger.info(f"   ✅ Haircap sınıf(lar)ı model'de mevcut: {haircap_in_model}")
                else:
                    # Haircap sınıfı bulunamadı — olası isim uyuşmazlığı
                    logger.warning(
                        f"   ⚠️ Haircap sınıfı model.names'de bulunamadı! "
                        f"Bilinen varyantlar (_FOOD_PPE_NAME_MAP) ile eşleşen yok. "
                        f"Model sınıfları: {actual_names}. "
                        f"Rescue pass dışlama stratejisi devreye girecek."
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
        'Googles':  'glasses',        # Roboflow typo: Googles = Goggles
        'googles':  'glasses',
        'Goggles':  'glasses',
        'gloves':   'gloves',
        'Gloves':   'gloves',
    }

    # Food model confidence cap — configurable via env var FOOD_PPE_CONFIDENCE
    _FOOD_PPE_CONFIDENCE: float = float(os.environ.get('FOOD_PPE_CONFIDENCE', '0.10'))

    # Haircap is notoriously hard for the food model; use a separate lower threshold
    _HAIRCAP_RESCUE_CONF: float = float(os.environ.get('HAIRCAP_RESCUE_CONF', '0.005'))

    def _detect_with_food_model(self, image, confidence):
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

            # Collect ALL raw detections for diagnostic logging
            all_raw = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    try:
                        rn = model_names.get(int(box.cls[0].item()), '?')
                        rc = float(box.conf[0].item())
                        rb = box.xyxy[0].cpu().numpy().tolist()
                        bw = rb[2] - rb[0]
                        bh = rb[3] - rb[1]
                        cov = (bw * bh) / frame_area * 100 if frame_area > 0 else 0
                        all_raw.append((rn, rc, cov, rb, int(box.cls[0].item())))
                    except Exception:
                        pass

            for rn, rc, cov, rb, cls_id in all_raw:
                canonical = self._FOOD_PPE_NAME_MAP.get(rn, rn.lower())
                if cov > 60:
                    logger.debug(f"🍽️ Food PPE: {rn} rejected — oversized ({cov:.0f}%)")
                    continue
                detections.append({
                    'class_id': cls_id,
                    'class_name': canonical,
                    'confidence': rc,
                    'bbox': rb,
                    'sector': 'food',
                    'model_type': 'FoodPPE-Local',
                    'raw_name': rn,
                })

            # ── Haircap rescue pass ──────────────────────────────────────────
            # If no haircap was found in the primary pass, run a second
            # inference at a much lower confidence to catch faint detections.
            # CRITICAL: canonical class_name kullan (raw_name model-specific olabilir)
            haircap_found = any(d.get('class_name') == 'haircap' for d in detections)
            if not haircap_found:
                # Rescue her zaman _HAIRCAP_RESCUE_CONF ile çalışır (primary conf'tan bağımsız)
                rescue_conf = self._HAIRCAP_RESCUE_CONF
                try:
                    rescue_results = model(image, conf=rescue_conf, device=self.device,
                                           verbose=False, imgsz=food_imgsz)

                    # ── Haircap class ID tespiti — model adlarına bağımlı olmayan yaklaşım ──
                    # Model sınıf adları eğitim datasındaki typo'lar yüzünden beklenenden
                    # farklı olabilir (örn: Appron vs Apron). İki strateji:
                    # 1. İsim tabanlı: bilinen haircap varyantlarını eşle
                    # 2. Dışlama tabanlı: bilinen non-haircap sınıflarını çıkar, kalanı haircap say
                    _HAIRCAP_NAME_TOKENS = ('haircap', 'hair_cap', 'hairnet', 'hair_net',
                                            'bonnet', 'bone', 'kep', 'cap')
                    _NON_HAIRCAP_CANONICAL = {'medical_suit', 'glasses', 'face_mask_medical', 'gloves'}

                    haircap_cls_ids = set()
                    # Strateji 1: _FOOD_PPE_NAME_MAP üzerinden canonical eşleme
                    # Bu en güvenilir yöntem — tüm bilinen isim varyantlarını kapsar
                    for k, v in model_names.items():
                        canonical = self._FOOD_PPE_NAME_MAP.get(v, self._FOOD_PPE_NAME_MAP.get(v.lower(), ''))
                        if canonical == 'haircap':
                            haircap_cls_ids.add(k)
                    if haircap_cls_ids:
                        logger.info(f"🍽️ Haircap rescue (canonical match): cls_ids={haircap_cls_ids}")

                    # Strateji 2: isim tabanlı token eşleme (fallback)
                    if not haircap_cls_ids:
                        for k, v in model_names.items():
                            vl = v.lower().replace(' ', '_')
                            if any(token in vl for token in _HAIRCAP_NAME_TOKENS):
                                haircap_cls_ids.add(k)
                        if haircap_cls_ids:
                            logger.info(f"🍽️ Haircap rescue (token match): cls_ids={haircap_cls_ids}")

                    # Strateji 3: dışlama — bilinen non-haircap sınıfları çıkar
                    if not haircap_cls_ids:
                        for k, v in model_names.items():
                            canonical_check = self._FOOD_PPE_NAME_MAP.get(
                                v, self._FOOD_PPE_NAME_MAP.get(v.lower(), ''))
                            if canonical_check in _NON_HAIRCAP_CANONICAL:
                                continue
                            haircap_cls_ids.add(k)
                        if haircap_cls_ids:
                            logger.info(f"🍽️ Haircap rescue (exclusion strategy): candidate class_ids={haircap_cls_ids}, "
                                       f"model_names={{ k: model_names[k] for k in haircap_cls_ids }}")

                    # Sanity check: class ID'lerin model'in gerçek sınıf aralığında olduğunu doğrula
                    valid_ids = set(model_names.keys())
                    invalid_ids = haircap_cls_ids - valid_ids
                    if invalid_ids:
                        logger.warning(f"🍽️ Haircap rescue: geçersiz class_ids tespit edildi ve çıkarıldı: {invalid_ids} "
                                      f"(geçerli aralık: {valid_ids})")
                        haircap_cls_ids -= invalid_ids

                    if not haircap_cls_ids:
                        logger.warning(
                            f"🍽️ Haircap rescue: model sınıflarında haircap bulunamadı! "
                            f"model.names={model_names}"
                        )

                    # Diagnostik: rescue inference'ın TÜM sınıf dağılımını logla
                    rescue_all_classes: Dict[int, int] = {}
                    rescue_raw = []
                    for rr in rescue_results:
                        if rr.boxes is None:
                            continue
                        for box in rr.boxes:
                            try:
                                cls_id = int(box.cls[0].item())
                                rescue_all_classes[cls_id] = rescue_all_classes.get(cls_id, 0) + 1
                                if cls_id not in haircap_cls_ids:
                                    continue
                                rn = model_names.get(cls_id, '?')
                                rc = float(box.conf[0].item())
                                rb = box.xyxy[0].cpu().numpy().tolist()
                                bw = rb[2] - rb[0]
                                bh = rb[3] - rb[1]
                                cov = (bw * bh) / frame_area * 100
                                rescue_raw.append((rn, rc, cov, rb, cls_id))
                            except Exception:
                                pass
                    # Tüm sınıfların dağılımını göster — model'in class_id=2'yi üretip üretmediğini doğrulamak için
                    rescue_class_summary = {model_names.get(k, f'?{k}'): v for k, v in rescue_all_classes.items()}
                    if rescue_raw:
                        logger.info(f"🍽️ Haircap rescue: {len(rescue_raw)} raw at conf>={rescue_conf}")
                    else:
                        logger.info(f"🍽️ Haircap rescue: 0 haircap at conf>={rescue_conf}, "
                                   f"target_cls_ids={haircap_cls_ids}, "
                                   f"all_classes_in_rescue={rescue_class_summary}, "
                                   f"model.names={model_names}")
                    for rn, rc, cov, rb, cls_id in rescue_raw:
                        if cov > 60:
                            logger.debug(f"🍽️ Haircap rescue: {rn} rejected — oversized ({cov:.0f}%)")
                            continue
                        canonical = self._FOOD_PPE_NAME_MAP.get(rn, rn.lower())
                        # Eğer canonical hâlâ haircap değilse, zorla haircap yap
                        # (exclusion strategy ile bulunan sınıflar için)
                        if canonical not in ('haircap',):
                            canonical = 'haircap'
                        detections.append({
                            'class_id': cls_id,
                            'class_name': canonical,
                            'confidence': rc,
                            'bbox': rb,
                            'sector': 'food',
                            'model_type': 'FoodPPE-Local-Rescue',
                            'raw_name': rn,
                        })
                except Exception as rescue_err:
                    logger.debug(f"🍽️ Haircap rescue failed: {rescue_err}")

            # ── Logging ──────────────────────────────────────────────────────
            raw_str = ', '.join(f"{rn}({rc:.2f},{cov:.0f}%)" for rn, rc, cov, *_ in all_raw)
            if detections:
                summary = {}
                for d in detections:
                    key = d.get('raw_name', d.get('class_name', '?'))
                    summary[key] = summary.get(key, 0) + 1
                logger.info(f"🍽️ Food PPE local: {len(detections)} tespit (conf>={food_conf}, imgsz={food_imgsz}, img={img_w}x{img_h}) → {summary}")
            else:
                logger.info(f"🍽️ Food PPE local: 0 tespit (conf>={food_conf}, imgsz={food_imgsz}, img={img_w}x{img_h}, raw=[{raw_str}])")
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
                        logger.info(f"🍽️ Color haircap: white={white_ratio:.0%} blue={blue_ratio:.0%} "
                                   f"total={cap_ratio:.0%} → conf={conf:.2f}")
                except ImportError:
                    logger.debug("cv2 not available for color analysis fallback")
                    break
                except Exception as e:
                    logger.debug(f"Color analysis failed: {e}")

        if haircap_detections:
            logger.info(f"🍽️ Head-crop/color haircap rescue: {len(haircap_detections)} detections "
                       f"(types: {[d['model_type'] for d in haircap_detections]})")
        return haircap_detections

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
                food_results = self._detect_with_food_model(image, confidence)
                if food_results:
                    sh17_results.extend(food_results)
                    logger.debug(f"🍽️ Food merge: +{len(food_results)} food tespit → toplam {len(sh17_results)}")

                # ── Adım 3: Haircap head-crop rescue ──────────────────────
                # Food model haircap bulamadıysa, SH17 head tespitlerini
                # crop'layıp yakınlaştırarak tekrar dene + renk analizi fallback
                has_haircap = any(d.get('class_name') == 'haircap' for d in sh17_results)
                if not has_haircap:
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