import sys
import os
# Ana dizini (root) sistem yoluna ekle - 'models' klasörünün dışarıda kalabilmesi için
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)


from flask import Flask, request, jsonify, session, Response, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import sqlite3
import json

import threading
import time
import requests
import logging
import re
from urllib.parse import quote, unquote

# Configure logging - Dynamic level via LOG_LEVEL env var
_env_log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, _env_log_level, logging.INFO)
if os.environ.get('RENDER') and _env_log_level == 'INFO':
    log_level = logging.WARNING

logging.basicConfig(level=log_level, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Keep request logs, but suppress ultra-noisy polling endpoints (200 OK spam).
_req_log_level = os.getenv("REQUEST_LOG_LEVEL", "INFO").upper()
_req_level = getattr(logging, _req_log_level, logging.INFO)
_werkzeug_logger = logging.getLogger("werkzeug")
_werkzeug_logger.setLevel(_req_level)

class _WerkzeugPollingNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        # Filter out specific Werkzeug development server warning and exit hint
        if 'WARNING: This is a development server' in msg or 'Press CTRL+C to quit' in msg:
            return False

        # Only drop successful access logs for polling endpoints.
        if ' 200 ' in msg and '"GET ' in msg:
            if '/detection-status/' in msg or '/detection/latest' in msg or '/health' in msg:
                return False
        return True

_werkzeug_logger.addFilter(_WerkzeugPollingNoiseFilter())


from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
# core klasöründeki .env dosyasını yükle
load_dotenv(os.path.join(current_dir, '.env'))
from services.multitenant_system import MultiTenantDatabase
from database.database_adapter import get_db_adapter
from sector.sector_ppe_config import (
    get_default_mandatory_ppe_ids,
    map_sh17_class_to_config_requirement_id,
    sector_default_ppe_map,
)
from integrations.cameras.camera_integration_manager import DVRConfig
from detection.snapshot_manager import get_snapshot_manager
from detection.violation_tracker import get_violation_tracker
from integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
from services.notification_service import get_notification_service
import cv2
import numpy as np
import base64
import queue
from io import BytesIO
import bcrypt
from pathlib import Path
from detection.utils.visual_overlay import draw_styled_box, get_class_color, draw_hud_bar, reset_label_registry

# Load environment variables
load_dotenv()

# Resolve project root (for templates/static after src/ restructure)
try:
    # __file__ = .../core/app.py
    # parents[1] => project root (folder containing 'core')
    BASE_DIR = Path(__file__).resolve().parents[1]
except Exception:
    BASE_DIR = Path(__file__).resolve().parent

# Enterprise modülleri import et
# Lazy loading için enterprise modülleri startup'ta yükleme - Memory optimization
ENTERPRISE_MODULES_AVAILABLE = True
logger.info("✅ Enterprise modülleri lazy loading için hazır - Memory optimized")

# Global değişkenler - kamera sistemi için
import threading as _threading

# ── Thread-safe frame buffer ────────────────────────────────────────────────
# 16 kamera aynı anda frame yazarken race condition'u önler
class _ThreadSafeDict(dict):
    """dict + RLock ile atomik read/write — multi-camera güvenliği"""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._lock = _threading.RLock()

    def __setitem__(self, key, value):
        with self._lock:
            super().__setitem__(key, value)

    def __getitem__(self, key):
        with self._lock:
            return super().__getitem__(key)

    def __delitem__(self, key):
        with self._lock:
            super().__delitem__(key)

    def get(self, key, default=None):
        with self._lock:
            return super().get(key, default)

    def __contains__(self, key):
        with self._lock:
            return super().__contains__(key)

    def copy_frame(self, key):
        """Frame'i kopyalayarak güvenli döndür (numpy array için)"""
        import numpy as _np
        with self._lock:
            val = super().get(key)
            if val is None:
                return None
            return val.copy() if isinstance(val, _np.ndarray) else val


active_detectors = {}       # Stream/Worker status (used by Watchdog)
active_ai_detectors = {}    # AI Inference status (used by UI for 'AI VIEW')
detection_threads = {}
camera_captures = {}       # Kamera yakalama nesneleri
frame_buffers = _ThreadSafeDict()  # Frame buffer'ları — thread-safe
detection_results = {}     # Tespit sonuçları (Queue — zaten thread-safe)
live_violation_state = {}  # SaaS canlı tespit için ihlal durumu (start/resolution)
frame_failure_counts = {}  # Kamera okuma hataları sayacı
frame_timestamps = {}      # camera_key → son frame zamanı (epoch) — StreamWatchdog izler

# İYİLEŞTİRİLDİ: Response Caching
response_cache = {}
cache_timestamps = {}
CACHE_DURATION = 300  # 5 dakika cache süresi

# ── Multi-Camera Production Resource Management ─────────────────────────────
# 20-30 kamera eşzamanlı çalışırken kaynak tüketimini sınırla
import os as _os
import multiprocessing as _mp

# Kaç kamera aynı anda inference yapabilir — efektif cihaz TORCH_DEVICE / RENDER ile utils.torch_device'dan
_effective_torch_device = "cpu"
try:
    from utils.torch_device import resolve_inference_device

    _effective_torch_device = resolve_inference_device(logger=logger)
    _has_gpu = str(_effective_torch_device).startswith("cuda")
except Exception:
    try:
        import torch as _torch_check

        _has_gpu = _torch_check.cuda.is_available()
        _effective_torch_device = "cuda" if _has_gpu else "cpu"
    except ImportError:
        _has_gpu = False
        _effective_torch_device = "cpu"

_cpu_cores = _mp.cpu_count()

# Eşzamanlı YOLO inference sayısı: GPU varsa 4 (CUDA serialize anyway), CPU'da çekirdek/2
_MAX_INFERENCE_WORKERS = int(_os.environ.get(
    'MAX_INFERENCE_WORKERS',
    4 if _has_gpu else max(2, _cpu_cores // 2)
))

# Maksimum eşzamanlı aktif kamera (lisans/kaynak sınırı)
MAX_CONCURRENT_CAMERAS = int(_os.environ.get('MAX_CONCURRENT_CAMERAS', 32))

# Inference semaphore: aynı anda en fazla _MAX_INFERENCE_WORKERS thread YOLO inference yapabilir
_inference_semaphore = _threading.Semaphore(_MAX_INFERENCE_WORKERS)

# Kamera slot semaphore: toplam aktif kamera sayısını sınırla
_camera_slot_semaphore = _threading.Semaphore(MAX_CONCURRENT_CAMERAS)

import logging as _log_tmp
_log_tmp.getLogger(__name__).info(
    f"🎛️ Resource Manager: MAX_CAMERAS={MAX_CONCURRENT_CAMERAS}, "
    f"INFERENCE_WORKERS={_MAX_INFERENCE_WORKERS}, "
    f"TORCH_DEVICE_EFFECTIVE={_effective_torch_device}, GPU_POOL={_has_gpu}"
)


def _draw_roi_debug_on_frame(frame: np.ndarray, roi_dbg: dict) -> None:
    """
    ROI_DEBUG: poligon + kişi kutuları (içerde yeşil, dışarıda kırmızı) ve özet metin.
    frame BGR, yerinde çizilir.
    """
    if not roi_dbg or not isinstance(roi_dbg, dict):
        return
    poly = roi_dbg.get("polygon") or []
    if len(poly) >= 6 and len(poly) % 2 == 0:
        n = len(poly) // 2
        pts = np.array(
            [[poly[i * 2], poly[i * 2 + 1]] for i in range(n)],
            dtype=np.int32,
        ).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], True, (255, 255, 0), 2, cv2.LINE_AA)

    # Backwards-compatible: `persons` is the legacy list (single layer).
    for p in roi_dbg.get("persons") or []:
        bb = p.get("bbox")
        if not bb or len(bb) != 4:
            continue
        try:
            x1, y1, x2, y2 = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
        except (TypeError, ValueError):
            continue
        if p.get("unknown"):
            color = (0, 165, 255)
        elif p.get("inside"):
            color = (0, 255, 0)
        else:
            color = (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # New (optional): layered bbox debug (raw vs final).
    # raw_persons: pre-tracking / pre-ROI (red)
    # final_persons: post-tracking / post-ROI (green)
    raw_list = roi_dbg.get("raw_persons") or []
    final_list = roi_dbg.get("final_persons") or []
    if raw_list or final_list:
        for p in raw_list:
            bb = p.get("bbox")
            if not bb or len(bb) != 4:
                continue
            try:
                x1, y1, x2, y2 = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
            except (TypeError, ValueError):
                continue
            # raw = thin red
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)

        for p in final_list:
            bb = p.get("bbox")
            if not bb or len(bb) != 4:
                continue
            try:
                x1, y1, x2, y2 = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
            except (TypeError, ValueError):
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Small label: track_id + roi_score (if present)
            try:
                tid = p.get("track_id")
                rs = p.get("roi_score")
                label = ""
                if tid is not None:
                    label += f"id={tid}"
                if rs is not None:
                    label += ("" if not label else " ") + f"roi={float(rs):.2f}"
                if label:
                    cv2.putText(
                        frame,
                        label,
                        (x1 + 2, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (255, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
            except Exception:
                pass

    st = roi_dbg.get("stats") or {}
    line = (
        f"ROI DEBUG  total_persons={st.get('total_persons', 0)}  "
        f"inside_roi={st.get('inside_roi', 0)}  outside_roi={st.get('outside_roi', 0)}"
    )
    fh = frame.shape[0]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = float(max(0.5, min(fh / 720.0, 1.15) * 0.7))
    thick = max(2, int(round(scale * 2)))
    (tw, th), _ = cv2.getTextSize(line, font, scale, thick)
    y0 = th + 14
    cv2.rectangle(frame, (4, 4), (tw + 16, y0 + 8), (0, 0, 0), -1)
    cv2.putText(frame, line, (10, y0), font, scale, (255, 255, 255), thick, cv2.LINE_AA)


class SmartSafeSaaSAPI:
    """SmartSafe AI SaaS API Server"""
    
    def __init__(self):
        try:
            # Headless API - No template/static folders needed
            self.app = Flask(__name__)
            
            _secret = os.getenv('SECRET_KEY')
            if not _secret:
                import secrets
                _secret = secrets.token_hex(32)
                logger.warning("SECRET_KEY not set – using random key (sessions will not persist across restarts)")
            self.app.config['SECRET_KEY'] = _secret
        except Exception as e:
            logger.error(f"❌ Flask app initialization failed: {e}")
            raise
        
        # UI caching logic removed as this is now a headless API
        
        # SH17 Model Manager entegrasyonu (Production Optimized - Lazy Loading)
        self.sh17_manager = None
        try:
            from models.sh17_model_manager import SH17ModelManager
            self.sh17_manager = SH17ModelManager()
            # RENDER.COM OPTIMIZATION: Modelleri başlangıçta yükleme, lazy loading kullan
            logger.info("✅ SH17 Model Manager API'ye entegre edildi (Lazy Loading)")
        except Exception as e:
            logger.warning(f"⚠️ SH17 Model Manager API'ye yüklenemedi: {e}. Fallback kullanılacak.")
            self.sh17_manager = None
        
        # Force production mode settings - Render.com focused
        is_production = (os.environ.get('RENDER') or 
                        os.environ.get('FLASK_ENV') == 'production')
        
        if is_production:
            self.app.config['DEBUG'] = False
            self.app.config['TESTING'] = False
            self.app.config['ENV'] = 'production'
            # Railway.app specific optimizations
            self.app.config['PROPAGATE_EXCEPTIONS'] = True
            self.app.config['PREFERRED_URL_SCHEME'] = 'https'
        
        # Schedule Manager initialization
        self.schedule_manager = None
        

        
        # Enable CORS
        allowed_origins = [
            'http://localhost:3000',
            'http://localhost:3377',
            'http://127.0.0.1:3000',
            'http://127.0.0.1:3377',
            'http://localhost:8000',
            'http://localhost:5577',
            'http://127.0.0.1:5577',
            'https://getsmartsafeai.com',  # Production frontend domain
            'https://www.getsmartsafeai.com',  # WWW variant
            'https://app.getsmartsafeai.com',  # Backend custom domain
            'https://*.vercel.app',  # Vercel preview ve production domains
            os.getenv('FRONTEND_URL', '')  # Environment variable ile özelleştirilebilir
        ]
        
        # CORS konfigürasyonu
        CORS(self.app, 
             resources={r"/*": {"origins": allowed_origins}},
             supports_credentials=True,
             allow_headers=['Content-Type', 'Authorization'],
             methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

        # --- Media Gateway configuration (WebRTC/HLS/RTSP aggregator) ---
        # Allows the platform to prefer a local media gateway (e.g., MediaMTX) as the
        # ingest/egress hub. When enabled, stream URLs are constructed against the gateway
        # instead of the DVR directly. This improves stability and browser compatibility.
        self.gateway_enabled = os.getenv('GATEWAY_ENABLED', 'false').lower() in ['1', 'true', 'yes']
        self.gateway_host = os.getenv('GATEWAY_HOST', '')
        self.gateway_rtsp_port = int(os.getenv('GATEWAY_RTSP_PORT', '8554'))
        self.gateway_http_port = int(os.getenv('GATEWAY_HTTP_PORT', '8889'))
        # Path template supports {dvr_id} and {channel:02d}
        self.gateway_path_template = os.getenv(
            'GATEWAY_PATH_TEMPLATE',
            'dvr/{dvr_id}/ch{channel:02d}'
        )

        # Production database schema handler
        self.is_production = (os.environ.get('RENDER') or
                             os.environ.get('SUPABASE_URL') or
                             os.environ.get('FLASK_ENV') == 'production')
        
        # İYİLEŞTİRİLDİ: Rate limiting with better configuration
        # Dev ortamında (kapalı devre) polling kaynaklı patlamaları engellemek için
        # daha yüksek bir default limit kullan.
        default_limits = ["200 per minute", "1000 per hour"] if self.is_production else ["2000 per minute", "20000 per hour"]
        # Optional override via env (e.g. RATE_LIMITS="500 per minute;5000 per hour")
        env_limits = os.getenv("RATE_LIMITS", "").strip()
        if env_limits:
            default_limits = [s.strip() for s in env_limits.split(";") if s.strip()]
        # Redis (or other shared storage) avoids limits' in-memory backend threading issues
        # under concurrent Flask workers/threads ("threads can only be started once").
        _rl_storage = os.getenv("RATELIMIT_STORAGE_URI", "").strip()
        if not _rl_storage:
            _fallback_redis = os.getenv("REDIS_URL", "").strip()
            if _fallback_redis.startswith(("redis://", "rediss://")):
                _rl_storage = _fallback_redis
        if not _rl_storage:
            _rl_storage = "memory://"
        self.limiter = Limiter(
            app=self.app,
            key_func=get_remote_address,
            default_limits=default_limits,
            storage_uri=_rl_storage,
        )
        if _rl_storage != "memory://":
            logger.info("Flask-Limiter using shared storage (non-memory)")
        
        # Multi-tenant database - Lazy initialization for production
        self.db = None
        self.db_adapter = None
        self._db_initialized = False
        
        if self.is_production:
            logger.info("🚀 Production mode: PostgreSQL/Supabase schema active")
            self.database_type = 'postgresql'
        else:
            logger.info("🔧 Development mode: SQLite schema active")
            self.database_type = 'sqlite'
        
        # Notification Service
        self.notification_service = get_notification_service()
        
        # Enterprise modülleri başlat
        self.init_enterprise_modules()
        
        # PPE Detection Manager başlat (Opsiyonel Modül)
        try:
            from integrations.cameras.ppe_detection_manager import PPEDetectionManager
            self.ppe_manager = PPEDetectionManager()
            if not self.ppe_manager.load_models():
                logger.info("ℹ️ PPE Detection Manager (Legacy) pasif, modern DVR entegrasyonu aktif")
                self.ppe_manager = None
        except (ImportError, ModuleNotFoundError):
            logger.debug("ℹ️ PPEDetectionManager modülü bulunamadı, standard akış kullanılacak")
            self.ppe_manager = None
        except Exception as e:
            logger.info(f"ℹ️ PPE Detection Manager başlatılamadı ({e}), standard akış devam ediyor")
            self.ppe_manager = None
        

        
        # İYİLEŞTİRİLDİ: Enhanced Error Handlers - Production Grade
        @self.app.errorhandler(404)
        def not_found(error):
            logger.warning(f"404 Not Found: {request.path}")
            return jsonify({
                'error': 'Resource not found',
                'message': 'The requested resource could not be found',
                'code': 'NOT_FOUND',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            logger.error(f"500 Internal Server Error: {error}", exc_info=True)
            return jsonify({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred',
                'code': 'INTERNAL_ERROR',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 500
        
        @self.app.errorhandler(502)
        def bad_gateway(error):
            logger.error(f"502 Bad Gateway: {error}", exc_info=True)
            return jsonify({
                'error': 'Bad gateway',
                'message': 'The server is temporarily unavailable',
                'code': 'BAD_GATEWAY',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 502
        
        @self.app.errorhandler(503)
        def service_unavailable(error):
            logger.error(f"503 Service Unavailable: {error}", exc_info=True)
            return jsonify({
                'error': 'Service unavailable',
                'message': 'The server is temporarily unavailable',
                'code': 'SERVICE_UNAVAILABLE',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 503
        
        @self.app.errorhandler(Exception)
        def handle_exception(error):
            logger.error(f"Unhandled exception: {error}", exc_info=True)
            return jsonify({
                'error': 'Internal server error',
                'message': str(error) if not self.is_production else 'An unexpected error occurred',
                'code': 'UNHANDLED_ERROR',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 500
        
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'error': 'Bad request',
                'message': 'Invalid request parameters',
                'code': 'BAD_REQUEST',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 400
        
        @self.app.errorhandler(401)
        def unauthorized(error):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Authentication required',
                'code': 'UNAUTHORIZED',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 401
        
        @self.app.errorhandler(403)
        def forbidden(error):
            return jsonify({
                'error': 'Forbidden',
                'message': 'Access denied',
                'code': 'FORBIDDEN',
                'timestamp': datetime.now().isoformat(),
                'path': request.path
            }), 403
        
        # Setup routes
        self.setup_routes()
        
        # ── Stream Watchdog başlat ──────────────────────────────────────────
        try:
            from integrations.cameras.stream_watchdog import init_stream_watchdog
            self._stream_watchdog = init_stream_watchdog(
                frame_timestamps=frame_timestamps,
                active_detectors=active_ai_detectors,
                restart_callback=self._watchdog_restart_camera,
            )
            self._stream_watchdog.start()
            logger.info("✅ Stream Watchdog başlatıldı")
        except Exception as wdg_err:
            logger.warning(f"⚠️ Stream Watchdog başlatılamadı: {wdg_err}")
            self._stream_watchdog = None
        
        logger.info("🌐 SmartSafe AI SaaS API Server initialized")
        
        # İYİLEŞTİRİLDİ: Cache management functions
        self.setup_cache_management()
    
    def ensure_database_initialized(self):
        """Ensure database is ready; re-initialize if connection died after idle."""
        # Eğer daha önce initialize ettiysek, bağlantı sağlıklı mı kontrol et
        if self.db_adapter is not None and self._db_initialized:
            try:
                if self.db_adapter.health_check():
                    return True
                else:
                    logger.warning("⚠️ Database health check failed, forcing re-initialization")
                    self._db_initialized = False
            except Exception as hc_err:
                logger.warning(f"⚠️ Database health check error: {hc_err}, will re-initialize")
                self._db_initialized = False

        try:
            # Database adapter'ı önce initialize et
            if self.db_adapter is None:
                self.db_adapter = get_db_adapter()
                if self.db_adapter:
                    self.db_adapter.init_database()
                    # Link db_adapter to notification service
                    if self.notification_service:
                        self.notification_service.db_adapter = self.db_adapter
            
            # MultiTenantDatabase'ı initialize et
            if self.db is None:
                self.db = MultiTenantDatabase()
                if self.db is None:
                    logger.error("❌ MultiTenantDatabase initialization returned None")
                    self._db_initialized = False
                    return False
            
            # Final check - db hala None ise başarısız
            if self.db is None:
                logger.error("❌ Database is still None after initialization")
                self._db_initialized = False
                return False
            
            self._db_initialized = True
            logger.info("✅ Database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            self._db_initialized = False
            self.db = None
            return False
    
    def setup_cache_management(self):
        """Cache yönetimi için yardımcı fonksiyonlar"""
        def get_cached_response(cache_key: str) -> Optional[Dict]:
            """Cache'den response al"""
            if cache_key in response_cache:
                timestamp = cache_timestamps.get(cache_key, 0)
                if time.time() - timestamp < CACHE_DURATION:
                    logger.info(f"✅ Cache hit: {cache_key}")
                    return response_cache[cache_key]
                else:
                    # Expired cache
                    del response_cache[cache_key]
                    del cache_timestamps[cache_key]
            return None
        
        def set_cached_response(cache_key: str, response_data: Dict):
            """Response'u cache'e kaydet"""
            response_cache[cache_key] = response_data
            cache_timestamps[cache_key] = time.time()
            logger.info(f"💾 Cache set: {cache_key}")
        
        def clear_expired_cache():
            """Expired cache'leri temizle"""
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in cache_timestamps.items()
                if current_time - timestamp > CACHE_DURATION
            ]
            for key in expired_keys:
                del response_cache[key]
                del cache_timestamps[key]
            if expired_keys:
                logger.info(f"🧹 Cleared {len(expired_keys)} expired cache entries")
        
        # Cache fonksiyonlarını instance'a ekle
        self.get_cached_response = get_cached_response
        self.set_cached_response = set_cached_response
        self.clear_expired_cache = clear_expired_cache
        
        # Cache cleanup thread başlat
        def cache_cleanup_worker():
            while True:
                try:
                    clear_expired_cache()
                    time.sleep(60)  # Her dakika kontrol et
                except Exception as e:
                    logger.error(f"❌ Cache cleanup error: {e}")
                    time.sleep(60)
        
        cache_thread = threading.Thread(target=cache_cleanup_worker, daemon=True)
        cache_thread.start()
        logger.info("✅ Cache management initialized")
    
    def _create_error_frame(self, error_message: str):
        """Hata mesajı içeren frame oluştur"""
        import cv2
        import numpy as np
        
        # 640x480 siyah frame oluştur
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Hata mesajını frame'e yaz
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Başlık
        cv2.putText(frame, 'SmartSafe AI - Error', (20, 50), 
                   font, 1.0, (0, 0, 255), 2)
        
        # Hata mesajını satırlara böl
        words = error_message.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if len(test_line) < 50:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Satırları yaz
        y_offset = 150
        for line in lines:
            cv2.putText(frame, line, (20, y_offset), 
                       font, 0.6, (255, 255, 255), 1)
            y_offset += 40
        
        # Yardım mesajı
        cv2.putText(frame, 'Please check:', (20, y_offset + 40), 
                   font, 0.5, (0, 255, 255), 1)
        cv2.putText(frame, '1. Camera is online', (40, y_offset + 70), 
                   font, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, '2. Network connection', (40, y_offset + 100), 
                   font, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, '3. Camera credentials', (40, y_offset + 130), 
                   font, 0.5, (255, 255, 255), 1)
        
        return frame
    
    def init_enterprise_modules(self):
        """Enterprise modülleri lazy loading ile başlat - Memory optimized"""
        if ENTERPRISE_MODULES_AVAILABLE:
            try:
                # Lazy loading - sadece gerekli olanları yükle
                self.enterprise_enabled = True
                self.error_handler = None  # Lazy load
                self.config_manager = None  # Lazy load
                self.performance_optimizer = None  # Lazy load
                self.security_manager = None  # Lazy load
                self.monitoring_system = None  # Lazy load
                self.camera_manager = None  # Lazy load
                
                logger.info("✅ Enterprise modülleri lazy loading ile hazırlandı - Memory optimized")
                
            except Exception as e:
                logger.error(f"❌ Enterprise modül hazırlama hatası: {e}")
                self.enterprise_enabled = False
        else:
            self.enterprise_enabled = False
            logger.info("⚙️ Fallback moda geçiliyor - Enterprise özellikler devre dışı")
    
    def get_camera_manager(self):
        """Lazy load camera manager"""
        if self.camera_manager is None:
            try:
                from integrations.cameras.camera_integration_manager import get_camera_manager
                self.camera_manager = get_camera_manager()
                logger.info("✅ Camera Manager lazy loaded")
            except ImportError:
                logger.warning("⚠️ Camera Manager import failed")
                return None
        return self.camera_manager
    
    def get_config_manager(self):
        """Lazy load config manager"""
        if self.config_manager is None:
            try:
                from services.professional_config_manager import ProfessionalConfigManager
                self.config_manager = ProfessionalConfigManager()
                logger.info("✅ Config Manager lazy loaded")
            except ImportError:
                logger.warning("⚠️ Config Manager import failed")
                return None
        return self.config_manager
    
    def get_performance_optimizer(self):
        """Lazy load performance optimizer"""
        if self.performance_optimizer is None:
            try:
                from services.performance_optimizer import PerformanceOptimizer
                self.performance_optimizer = PerformanceOptimizer()
                logger.info("✅ Performance Optimizer lazy loaded")
            except ImportError:
                logger.warning("⚠️ Performance Optimizer import failed")
                return None
        return self.performance_optimizer

    # ------------------------------------------------------------------
    # Helper: Build Media Gateway URLs for a given DVR/channel
    # ------------------------------------------------------------------
    def build_gateway_urls(self, dvr_system: dict, channel_number: int) -> dict:
        try:
            if not self.gateway_enabled or not self.gateway_host:
                return {}

            # Build path: supports formatting like ch01
            path = self.gateway_path_template.format(
                dvr_id=dvr_system['dvr_id'] if 'dvr_id' in dvr_system else dvr_system.get('id', ''),
                channel=channel_number
            )

            # Gateway exposes RTSP and HTTP (HLS/WebRTC)
            rtsp_url = f"rtsp://{self.gateway_host}:{self.gateway_rtsp_port}/{path}"
            # MediaMTX HLS pattern
            hls_url = f"http://{self.gateway_host}:{self.gateway_http_port}/{path}/index.m3u8"
            # MediaMTX WebRTC (WHEP-style HTTP endpoint)
            # Many deployments allow simply visiting the path over HTTP for WebRTC
            # The exact player can use this URL or a proxied variant
            webrtc_url = f"http://{self.gateway_host}:{self.gateway_http_port}/{path}"

            return {
                'enabled': True,
                'path': path,
                'rtsp_url': rtsp_url,
                'hls_url': hls_url,
                'webrtc_url': webrtc_url
            }
        except Exception as e:
            logger.warning(f"⚠️ Gateway URL build failed: {e}")
            return {}
    
    def cleanup_memory(self):
        """Memory cleanup for production optimization"""
        try:
            import gc
            gc.collect()
            logger.info("✅ Memory cleanup completed")
        except Exception as e:
            logger.warning(f"⚠️ Memory cleanup failed: {e}")
    
    def get_subscription_info_internal(self, company_id):
        """Internal subscription info - session kontrolü olmadan"""
        from datetime import datetime
        try:
            # Veritabanını başlat (lazy initialization)
            if not self.ensure_database_initialized():
                logger.error("❌ Database initialization failed in get_subscription_info_internal")
                return {'success': False, 'error': 'Veritabanı başlatılamadı'}
            
            if self.db is None:
                logger.error("❌ Database is None after initialization in get_subscription_info_internal")
                return {'success': False, 'error': 'Veritabanı bağlantısı kurulamadı'}
            
            logger.info(f"🔍 Getting subscription info for company: {company_id}")
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            query = f'''
                SELECT subscription_type, billing_cycle, subscription_start, subscription_end, max_cameras, 
                       created_at, company_name, sector, payment_status, auto_renewal, next_billing_date
                FROM companies WHERE company_id = {placeholder}
            '''
            logger.info(f"🔍 Executing query: {query} with params: {company_id}")
            cursor.execute(query, (company_id,))
            result = cursor.fetchone()
            logger.info(f"🔍 Query result: {result}")
            
            if result:
                # Kamera kullanımını al
                cameras = self.db.get_company_cameras(company_id)
                used_cameras = len(cameras)
                
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(result, 'keys'):  # PostgreSQL Row object
                    subscription_end = result['subscription_end']
                    subscription_start = result['subscription_start']
                    subscription_info = {
                        'subscription_type': result['subscription_type'] or 'basic',
                        'billing_cycle': result['billing_cycle'] or 'monthly',
                        'subscription_start': subscription_start,
                        'payment_status': result['payment_status'] or 'active',
                        'auto_renewal': result['auto_renewal'],
                        'next_billing_date': result['next_billing_date'],
                        'max_cameras': result['max_cameras'] or 25,
                        'created_at': result['created_at'] if result['created_at'] else None,
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'used_cameras': used_cameras,
                    }
                else:  # SQLite tuple
                    # subscription_type, billing_cycle, subscription_start, subscription_end, max_cameras, created_at, company_name, sector, payment_status, auto_renewal, next_billing_date
                    subscription_end = result[3]
                    subscription_start = result[2]
                    subscription_info = {
                        'subscription_type': result[0] or 'basic',
                        'billing_cycle': result[1] or 'monthly',
                        'subscription_start': subscription_start,
                        'payment_status': result[8] or 'active',
                        'auto_renewal': result[9],
                        'next_billing_date': result[10],
                        'max_cameras': result[4] or 25,
                        'created_at': result[5] if result[5] else None,
                        'company_name': result[6],
                        'sector': result[7],
                        'used_cameras': used_cameras,
                    }
                
                # Plan fiyat bilgilerini ekle
                plan_prices = {
                    'starter': {'monthly': 99, 'yearly': 990, 'cameras': 25},
                    'professional': {'monthly': 299, 'yearly': 2990, 'cameras': 100},
                    'enterprise': {'monthly': 599, 'yearly': 5990, 'cameras': 500}
                }
                
                current_plan = subscription_info['subscription_type'].lower()
                billing_cycle = subscription_info['billing_cycle']
                
                if current_plan in plan_prices:
                    subscription_info['current_price'] = plan_prices[current_plan][billing_cycle]
                    subscription_info['monthly_price'] = plan_prices[current_plan]['monthly']
                    subscription_info['yearly_price'] = plan_prices[current_plan]['yearly']
                else:
                    subscription_info['current_price'] = 99
                    subscription_info['monthly_price'] = 99
                    subscription_info['yearly_price'] = 990
                
                # Abonelik durumunu kontrol et
                is_active = True
                days_remaining = 0
                
                if subscription_end:
                    try:
                        if isinstance(subscription_end, str):
                            # Handle different date formats including microseconds
                            if 'T' in subscription_end:
                                # ISO format with timezone
                                subscription_end = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                            elif '.' in subscription_end:
                                # SQLite format with microseconds: '2025-08-01 22:14:59.075710'
                                subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
                            else:
                                # Standard format: '2025-08-01 22:14:59'
                                subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S')
                    
                                days_remaining = (subscription_end - datetime.now()).days
                                is_active = days_remaining > 0
                                logger.info(f"🔍 Subscription end: {subscription_end}, days remaining: {days_remaining}, is_active: {is_active}")
                    except Exception as date_error:
                        logger.error(f"❌ Date parsing error: {date_error}")
                        logger.error(f"❌ Raw subscription_end value: {subscription_end}")
                        is_active = True
                        days_remaining = 0
                
                # Ortak alanları ekle
                # Format subscription_start date
                subscription_start = subscription_info.get('created_at')
                if subscription_start and isinstance(subscription_start, str):
                    try:
                        if '.' in subscription_start:
                            # SQLite format with microseconds
                            subscription_start = datetime.strptime(subscription_start, '%Y-%m-%d %H:%M:%S.%f').isoformat()
                        else:
                            # Standard format
                            subscription_start = datetime.strptime(subscription_start, '%Y-%m-%d %H:%M:%S').isoformat()
                    except Exception as e:
                        logger.error(f"❌ Subscription start date parsing error: {e}")
                        subscription_start = None
                
                subscription_info.update({
                    'subscription_start': subscription_start,
                    'subscription_end': subscription_end.isoformat() if subscription_end else None,
                    'is_active': is_active,
                    'days_remaining': days_remaining,
                    'usage_percentage': (used_cameras / (subscription_info['max_cameras'] or 25)) * 100
                })
                
                # Success key'i ekle
                subscription_info['success'] = True
                return subscription_info
            else:
                logger.warning(f"⚠️ Company not found: {company_id}")
                return {'success': False, 'error': 'Şirket bulunamadı'}
            
        except Exception as e:
            logger.error(f"❌ Subscription info error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if 'conn' in locals():
                self.db.close_connection(conn)
    

    



    def setup_routes(self):
        """API rotalarini ayarla - Blueprint modüllerinden yükle"""
        from api import register_all_blueprints
        register_all_blueprints(self)
        
        # 📸 Serve violation snapshots
        @self.app.route('/static/violations/<path:filename>')
        def serve_violation_snapshot(filename):
            return send_from_directory('violations', filename)
            
        logger.info("✅ All API routes registered successfully")


    # --- Legacy setup_routes code moved to core/api/ ---
    # The following marker exists so that the rest of the class methods
    # (validate_session, template getters, etc.) remain untouched.

    def _require_db_decorator(self):
        """Decorator factory for database initialization (available to routes via api)"""
        from functools import wraps
        def require_db(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                try:
                    self.ensure_database_initialized()
                except Exception as e:
                    logger.warning(f"⚠️ Database initialization failed in request: {e}")
                return f(*args, **kwargs)
            return decorated_function
        return require_db

    def validate_session(self):
        """Oturum doğrulama - Optimized with reduced logging"""
        try:
            # Database initialization kontrolü
            if not self.ensure_database_initialized():
                logger.debug("⚠️ Database initialization failed in validate_session")
                return None
            
            if self.db is None:
                logger.debug("⚠️ Database connection is None in validate_session")
                return None
            
            session_id = session.get('session_id')
            
            # 🚀 DEVELOPMENT BYPASS: Local ortamda oturum yoksa veya geçersizse varsayılan bir oturum döndür
            # Bu, geliştiricinin her seferinde login olmak zorunda kalmasını engeller.
            is_local = os.getenv('ENV') == 'local' or os.getenv('FLASK_ENV') == 'development'
            
            if not session_id and is_local:
                # Path'den veya request args'dan company_id çekmeye çalış
                company_id = None
                if request.view_args and 'company_id' in request.view_args:
                    company_id = request.view_args['company_id']
                elif request.args and 'company_id' in request.args:
                    company_id = request.args['company_id']
                
                if company_id:
                    logger.debug(f"🚀 Dev Bypass: Auto-validating session for local dev (Company: {company_id})")
                    return {
                        'company_id': company_id,
                        'user_id': 'dev_user',
                        'username': 'Geliştirici',
                        'email': 'dev@smartsafe.ai',
                        'role': 'admin',
                        'permissions': ['all'],
                        'is_dev': True
                    }

            # Reduced logging - only log on errors or debug mode
            if not session_id:
                logger.debug("⚠️ Session ID bulunamadı")
                return None
            
            result = self.db.validate_session(session_id)
            
            # Dev bypass: Eğer session_id var ama DB'de yoksa ve local isek yine de izin ver
            if not result and is_local:
                 company_id = session.get('company_id') or (request.view_args.get('company_id') if request.view_args else None)
                 if company_id:
                     logger.debug(f"🚀 Dev Bypass (Invalid Session): Allowing local dev access for Company: {company_id}")
                     return {
                        'company_id': company_id,
                        'user_id': 'dev_user',
                        'username': 'Geliştirici',
                        'email': 'dev@smartsafe.ai',
                        'role': 'admin',
                        'permissions': ['all'],
                        'is_dev': True
                    }
            
            # Backward compatibility check
            if result and isinstance(result, dict):
                # Ensure required fields exist
                if 'company_id' not in result:
                    logger.debug("⚠️ Session result missing company_id")
                    return None
                
            return result
            
        except Exception as e:
            logger.error(f"❌ Session validation error: {e}", exc_info=True)
            return None
    
    
    
    def _get_realtime_camera_status(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get real-time camera status from IP address"""
        try:
            if hasattr(self, 'camera_manager') and self.camera_manager:
                # Try to find camera by IP in camera manager
                for camera_id, config in self.camera_manager.camera_configs.items():
                    if hasattr(config, 'connection_url') and ip_address in config.connection_url:
                        status = self.camera_manager.get_camera_status(camera_id)
                        return {
                            'real_time_status': status.get('connection_status', 'unknown'),
                            'current_fps': status.get('current_fps', 0),
                            'last_frame_time': status.get('last_frame_time'),
                            'frames_captured': status.get('frames_captured', 0),
                            'connection_drops': status.get('connection_drops', 0)
                        }
            return None
        except Exception as e:
            logger.debug(f"Real-time status check error for {ip_address}: {e}")
            return None
    
    def _basic_camera_test(self, camera_data):
        """Gelişmiş kamera testi - Tüm sorun türleri için kapsamlı analiz"""
        import time
        import requests
        import socket
        import subprocess
        import platform
        start_time = time.time()
        
        # Extract camera info from form data
        ip_address = camera_data.get('ip_address', '')
        port = camera_data.get('port', 8080)
        username = camera_data.get('username', '')
        password = camera_data.get('password', '')
        protocol = camera_data.get('protocol', 'http')
        
        test_result = { 
            'success': False,
            'connection_time': 0,
            'stream_quality': 'unknown',
            'supported_features': [],
            'camera_info': {},
            'error_message': '',
            'test_details': {
                'endpoints_tested': [],
                'protocols_tested': [],
                'connection_steps': [],
                'network_analysis': {},
                'system_analysis': {},
                'camera_analysis': {}
            }
        }
        
        try:
            # 1. Önce temel bağlantı testi
            test_result['test_details']['connection_steps'].append('Temel ağ bağlantısı test ediliyor...')
            if not self._test_network_connectivity(ip_address, port):
                test_result['error_message'] = f'IP adresi {ip_address}:{port} erişilebilir değil'
                test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
                return test_result
            
            # 2. HTTP endpoint'leri test et
            test_result['test_details']['connection_steps'].append('HTTP endpoint\'leri test ediliyor...')
            http_endpoints = [
                '/', '/video', '/shot.jpg', '/mjpeg', '/stream', '/live',
                '/camera', '/webcam', '/video.mjpg', '/video.mjpeg'
            ]
            
            working_endpoint = None
            auth_required = False
            
            for endpoint in http_endpoints:
                if self._test_http_endpoint(ip_address, port, endpoint, username, password):
                    working_endpoint = endpoint
                    test_result['test_details']['endpoints_tested'].append(f'HTTP: {endpoint} ✅')
                    break
                else:
                    # Authentication gerekli mi kontrol et
                    try:
                        url = f"http://{ip_address}:{port}{endpoint}"
                        response = requests.get(url, timeout=5)
                        if response.status_code == 401:
                            auth_required = True
                            test_result['test_details']['endpoints_tested'].append(f'HTTP: {endpoint} 🔐 (Auth gerekli)')
                            test_result['test_details']['endpoints_tested'].append(f'HTTP: {endpoint} ❌')
                    except Exception as e:
                        test_result['test_details']['endpoints_tested'].append(f'HTTP: {endpoint} ❌')
                        test_result['test_details']['connection_steps'].append(f'Hata: {str(e)}')
            
            # Authentication gerekliyse kullanıcıya bildir
            if auth_required and not username and not password:
                test_result['error_message'] = 'Kamera authentication gerektiriyor. Kullanıcı adı ve şifre girin.'
                test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
                return test_result
            
            # 3. RTSP endpoint'leri test et
            test_result['test_details']['connection_steps'].append('RTSP endpoint\'leri test ediliyor...')
            rtsp_endpoints = [
                '/video', '/stream', '/live', '/camera', '/webcam'
            ]
            
            if not working_endpoint:
                for endpoint in rtsp_endpoints:
                    if self._test_rtsp_endpoint(ip_address, port, endpoint, username, password):
                        working_endpoint = f"rtsp://{ip_address}:{port}{endpoint}"
                        test_result['test_details']['endpoints_tested'].append(f'RTSP: {endpoint} ✅')
                        break
                    else:
                        test_result['test_details']['endpoints_tested'].append(f'RTSP: {endpoint} ❌')
            
            # 4. OpenCV ile video stream testi
            if working_endpoint:
                test_result['test_details']['connection_steps'].append('Video stream test ediliyor...')
                if self._test_video_stream(working_endpoint, test_result):
                    test_result['success'] = True
                    test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
                    test_result['stream_quality'] = 'good'
                    test_result['supported_features'] = ['video_stream', 'http_stream']
                    test_result['camera_info'] = {
                        'ip': ip_address,
                        'port': port,
                        'protocol': protocol,
                        'working_endpoint': working_endpoint
                    }
                    return test_result
                else:
                    test_result['error_message'] = 'Video stream alınamadı'
            else:
                test_result['error_message'] = 'Hiçbir endpoint çalışmıyor. Kamera ayarlarını kontrol edin.'
                
        except Exception as e:
            test_result['error_message'] = f'Kamera test hatası: {str(e)}'
            test_result['test_details']['connection_steps'].append(f'Hata: {str(e)}')
        
        test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
        return test_result
    
    def _test_network_connectivity(self, ip_address, port):
        """Temel ağ bağlantısını test et"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((ip_address, port))
            sock.close()
            if result == 0:
                print(f"✅ Ağ bağlantısı başarılı: {ip_address}:{port}")
                return True
            else:
                print(f"❌ Ağ bağlantısı başarısız: {ip_address}:{port}")
                return False
        except Exception as e:
            print(f"❌ Ağ bağlantı hatası: {e}")
            return False
    
    def _test_http_endpoint(self, ip_address, port, endpoint, username, password):
        """HTTP endpoint'i test et"""
        try:
            auth = None
            if username and password:
                auth = (username, password)
            
            url = f"http://{ip_address}:{port}{endpoint}"
            response = requests.get(url, auth=auth, timeout=5)
            if response.status_code == 200:
                print(f"✅ HTTP endpoint başarılı: {url}")
                return True
            elif response.status_code == 401:
                print(f"❌ Authentication gerekli: {url}")
                return False
            else:
                print(f"❌ HTTP endpoint başarısız: {url} (Status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ HTTP endpoint hatası: {url} - {e}")
            return False
    
    def _test_rtsp_endpoint(self, ip_address, port, endpoint, username, password):
        """RTSP endpoint'i test et"""
        try:
            if username and password:
                rtsp_url = f"rtsp://{username}:{password}@{ip_address}:{port}{endpoint}"
            else:
                rtsp_url = f"rtsp://{ip_address}:{port}{endpoint}"
            
            print(f"🔍 RTSP test ediliyor: {rtsp_url}")
            cap = cv2.VideoCapture(rtsp_url)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    print(f"✅ RTSP endpoint başarılı: {rtsp_url}")
                    return True
                else:
                    print(f"❌ RTSP frame okunamadı: {rtsp_url}")
                    return False
            else:
                print(f"❌ RTSP bağlantısı açılamadı: {rtsp_url}")
                return False
        except Exception as e:
            print(f"❌ RTSP endpoint hatası: {rtsp_url} - {e}")
            return False
    
    def _test_video_stream(self, stream_url, test_result):
        """Video stream'i test et"""
        try:
            print(f"🎥 Video stream test ediliyor: {stream_url}")
            
            # Önce OpenCV ile dene
            cap = cv2.VideoCapture(stream_url)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    resolution = f"{frame.shape[1]}x{frame.shape[0]}"
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    print(f"✅ Video stream başarılı: {resolution}, FPS: {fps}")
                    test_result['camera_info']['resolution'] = resolution
                    test_result['camera_info']['fps'] = fps
                    cap.release()
                    return True
                else:
                    print(f"❌ Video frame okunamadı: {stream_url}")
                    cap.release()
            else:
                print(f"❌ Video stream açılamadı: {stream_url}")
            
            # OpenCV başarısızsa, shot endpoint'ini dene
            if '/video' in stream_url:
                shot_url = stream_url.replace('/video', '/shot.jpg')
                print(f"📸 Shot endpoint deneniyor: {shot_url}")
                
                try:
                    # URL'den authentication bilgilerini çıkar
                    if '@' in stream_url:
                        auth_part = stream_url.split('@')[0].replace('http://', '')
                        username, password = auth_part.split(':')
                        auth = (username, password)
                    else:
                        auth = None
                    
                    response = requests.get(shot_url, auth=auth, timeout=5)
                    if response.status_code == 200:
                        print("✅ Shot endpoint çalışıyor")
                        
                        # Shot'ı geçici dosyaya kaydet
                        import tempfile
                        import os
                        
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                            f.write(response.content)
                            temp_file = f.name
                        
                        # Shot'ı OpenCV ile oku
                        img = cv2.imread(temp_file)
                        if img is not None:
                            resolution = f"{img.shape[1]}x{img.shape[0]}"
                            print(f"✅ Shot okundu: {resolution}")
                            test_result['camera_info']['resolution'] = resolution
                            test_result['camera_info']['fps'] = 1  # Shot için FPS 1
                            test_result['camera_info']['stream_type'] = 'shot'
                            
                            # Geçici dosyayı sil
                            os.unlink(temp_file)
                            return True
                        else:
                            print("❌ Shot okunamadı")
                            os.unlink(temp_file)
                            
                except Exception as e:
                    print(f"❌ Shot test hatası: {e}")
            
            return False
        except Exception as e:
            print(f"❌ Video stream hatası: {stream_url} - {e}")
            test_result['test_details']['connection_steps'].append(f'Video stream hatası: {str(e)}')
            return False
    
    def camera_worker(self, camera_key, camera_id):
        """Kamera worker thread'i"""
        print(f"Kamera {camera_key} worker başlatılıyor...")
        
        try:
            # Kamera ID'sini integer'a çevir
            cam_index = int(camera_id)
            
            # Kamera yakalama nesnesi oluştur
            cap = cv2.VideoCapture(cam_index)
            
            if not cap.isOpened():
                print(f"Kamera {camera_id} açılamadı")
                return
            
            # Kamera ayarları
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            print(f"Kamera {camera_key} başarıyla kuruldu")
            
            camera_captures[camera_key] = cap
            frame_buffers[camera_key] = None
            
            while active_detectors.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    # Frame'i buffer'a kaydet
                    frame_buffers[camera_key] = frame.copy()
                else:
                    print(f"Kamera {camera_key} frame okunamadı")
                    break
                
                time.sleep(0.01)  # CPU yükünü azalt
                
        except Exception as e:
            print(f"Kamera {camera_key} worker hatası: {e}")
        finally:
            if camera_key in camera_captures and camera_captures[camera_key]:
                camera_captures[camera_key].release()
                del camera_captures[camera_key]
            if camera_key in frame_buffers:
                del frame_buffers[camera_key]
            print(f"Kamera {camera_key} worker durduruldu")
    
    def run_detection(self, camera_key, camera_id, company_id, mode, confidence=0.5):
        """Tespit çalıştır - Lazy loading ile memory optimized"""
        print(f"Tespit sistemi başlatılıyor - Kamera: {camera_key}, Sektör: {mode}, Confidence: {confidence}")
        
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=10)
        
        # Şirketin sektörünü belirle
        try:
            # Şirket bilgilerini al
            conn = self.db.get_connection()
            cursor = conn.cursor()
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            cursor.execute(f'SELECT sector FROM companies WHERE company_id = {placeholder}', (company_id,))
            result = cursor.fetchone()
            self.db.close_connection(conn)
            
            # PostgreSQL RealDictRow için sözlük erişimi kullan
            if result:
                if hasattr(result, 'keys'):  # RealDictRow veya dict
                    sector_id = result.get('sector') or 'construction'
                else:  # Liste formatı (SQLite için)
                    sector_id = result[0] if result[0] else 'construction'
            else:
                sector_id = 'construction'
            print(f"📊 Şirket {company_id} sektörü: {sector_id}")
            
        except Exception as e:
            print(f"⚠️ Şirket sektörü belirlenemedi: {e}, construction kullanılacak")
            sector_id = 'construction'
        
        # Lazy loading - Detector'ı sadece ihtiyaç anında yükle
        detector = None
        print(f"✅ {sector_id.upper()} sektörü detector lazy loading ile hazırlandı - Memory optimized")
        
        try:
            frame_count = 0
            last_detection_time = time.time()
            
            while active_detectors.get(camera_key, False):
                try:
                    # Frame buffer'dan frame al
                    if camera_key in frame_buffers:
                        frame = frame_buffers.copy_frame(camera_key)
                        if frame is None:
                            time.sleep(0.01)
                            continue
                        frame_count += 1
                        
                        # Her 5 frame'de bir tespit yap (performans için)
                        if frame_count % 5 == 0:
                            current_time = time.time()
                            
                            # Lazy loading - Detector'ı sadece ihtiyaç anında yükle
                            if detector is None:
                                try:
                                    detector = SectorDetectorFactory.get_detector(sector_id, company_id)
                                    if detector:
                                        print(f"✅ {sector_id.upper()} sektörü detector lazy loaded - Memory optimized")
                                    else:
                                        print(f"⚠️ {sector_id.upper()} detector yüklenemedi, simülasyon modu")
                                except Exception as e:
                                    print(f"❌ Sektörel Detector lazy loading hatası: {e}, simülasyon moduna geçiliyor")
                                    detector = None
                            
                            if detector is not None:
                                # Sektörel PPE tespiti
                                try:
                                    result = detector.detect_ppe(frame, camera_id)
                                    
                                    # Sonuçları SaaS formatına çevir
                                    detection_data = {
                                        'camera_id': camera_id,
                                        'company_id': company_id,
                                        'timestamp': datetime.now().isoformat(),
                                        'frame_count': frame_count,
                                        'compliance_rate': result['analysis']['compliance_rate'],
                                        'total_people': result['analysis']['total_people'],
                                        'violations': result['analysis']['violations'],
                                        'processing_time': current_time - last_detection_time,
                                        'detections': result['detections'],
                                        'sector': result.get('sector', 'unknown')
                                    }
                                    
                                    # Tespit sonucunu frame'e çiz
                                    annotated_frame = self.draw_sector_detection_results(frame, result)
                                    frame_buffers[camera_key] = annotated_frame
                                    
                                    print(f"🔍 Kamera {camera_key} ({result.get('sector', 'unknown')}): {result['analysis']['compliance_rate']:.1f}% uyum, "
                                          f"{result['analysis']['total_people']} kişi")
                                    
                                except Exception as detection_error:
                                    print(f"⚠️ Sektörel PPE tespit hatası: {detection_error}, simülasyona geçiliyor")
                                    # Hata durumunda simülasyon kullan
                                    detection_data = self.create_simulation_data(camera_id, company_id, frame_count, current_time, last_detection_time)
                            else:
                                # Simülasyon modu
                                detection_data = self.create_simulation_data(camera_id, company_id, frame_count, current_time, last_detection_time)
                                
                                # Basit frame annotation
                                annotated_frame = self.draw_simulation_results(frame, detection_data)
                                frame_buffers[camera_key] = annotated_frame
                            
                            # Queue'ya ekle
                            try:
                                detection_results[camera_key].put_nowait(detection_data)
                            except queue.Full:
                                # Queue doluysa eski sonucu çıkar, yenisini ekle
                                try:
                                    detection_results[camera_key].get_nowait()
                                except queue.Empty:
                                    pass
                                detection_results[camera_key].put_nowait(detection_data)


                            # === SaaS Resolution Status tracking (no snapshots) ===
                            try:
                                violations_count = detection_data.get('analysis', {}).get('violations_count',
                                                            len(detection_data.get('violations', [])))
                                live_violation_state[camera_key] = (violations_count > 0)
                            except Exception as state_error:
                                logger.warning(f"⚠️ State update warning: {state_error}")
                            
                            last_detection_time = current_time
                    
                    time.sleep(0.1)  # CPU yükünü azalt
                    
                except Exception as e:
                    print(f"Tespit hatası - Kamera {camera_key}: {e}")
                    time.sleep(1)
                    
        except Exception as e:
            print(f"Detection thread hatası: {e}")
            
        print(f"Kamera {camera_key} tespiti durduruldu")
    
    def calculate_real_chart_data(self, company_id):
        """Gerçek detection sonuçlarından grafik verilerini hesapla"""
        try:
            # Şirket kameralarından veri topla
            compliance_rates = []
            violation_counts = {'helmet': 0, 'vest': 0, 'shoes': 0, 'mask': 0}
            hourly_violations = [0] * 24
            
            # Aktif kameralardan veri topla
            for camera_key in active_detectors:
                if company_id in camera_key and active_detectors[camera_key]:
                    if camera_key in detection_results:
                        try:
                            # En son sonuçları al
                            temp_results = []
                            while not detection_results[camera_key].empty():
                                temp_results.append(detection_results[camera_key].get_nowait())
                            
                            if temp_results:
                                for result in temp_results:
                                    compliance_rates.append(result.get('compliance_rate', 0))
                                    
                                    # İhlal türlerini say
                                    violations = result.get('violations', [])
                                    for violation in violations:
                                        missing_ppe = violation.get('missing_ppe', [])
                                        for ppe in missing_ppe:
                                            if 'helmet' in ppe.lower() or 'baret' in ppe.lower():
                                                violation_counts['helmet'] += 1
                                            elif 'vest' in ppe.lower() or 'yelek' in ppe.lower():
                                                violation_counts['vest'] += 1
                                            elif 'shoes' in ppe.lower() or 'ayakkabı' in ppe.lower():
                                                violation_counts['shoes'] += 1
                                            elif 'mask' in ppe.lower() or 'maske' in ppe.lower():
                                                violation_counts['mask'] += 1
                                    
                                    # Saatlik ihlal dağılımı (basit simülasyon)
                                    current_hour = datetime.now().hour
                                    hourly_violations[current_hour] += len(violations)
                                
                                # Sonuçları geri koy
                                for result in temp_results:
                                    try:
                                        detection_results[camera_key].put_nowait(result)
                                    except queue.Full:
                                        break
                        except queue.Empty:
                            pass
            
            # Grafik verilerini hazırla - Backward compatibility
            chart_data = {
                'compliance_trend': compliance_rates[-7:] if len(compliance_rates) >= 7 else compliance_rates + [0] * (7 - len(compliance_rates)),
                'violation_types': [
                    violation_counts['helmet'],
                    violation_counts['vest'], 
                    violation_counts['shoes'],
                    violation_counts['mask']
                ],
                'hourly_violations': hourly_violations,
                'weekly_compliance': compliance_rates[-7:] if len(compliance_rates) >= 7 else compliance_rates + [0] * (7 - len(compliance_rates)),
                'success': True,
                'data_source': 'real_detection_data'
            }
            
            return chart_data
            
        except Exception as e:
            print(f"Chart data hesaplama hatası: {e}")
            # Hata durumunda varsayılan değerler döndür
            return {
                'compliance_trend': [0, 0, 0, 0, 0, 0, 0],
                'violation_types': [0, 0, 0, 0],
                'hourly_violations': [0] * 24,
                'weekly_compliance': [0, 0, 0, 0, 0, 0, 0],
                'success': False,
                'error': str(e),
                'data_source': 'fallback_data'
            }
    
    def create_simulation_data(self, camera_id, company_id, frame_count, current_time, last_detection_time):
        """Simülasyon verisi oluştur"""
        import random
        
        compliance_rate = random.uniform(60, 95)
        total_people = random.randint(1, 5)
        violations = []
        
        # Random ihlal oluştur
        if compliance_rate < 80:
            violations.append({
                'worker_id': f'Worker_{random.randint(1, 10)}',
                'missing_ppe': ['helmet'] if random.random() > 0.5 else ['vest']
            })
        
        return {
            'camera_id': camera_id,
            'company_id': company_id,
            'timestamp': datetime.now().isoformat(),
            'frame_count': frame_count,
            'compliance_rate': compliance_rate,
            'total_people': total_people,
            'violations': violations,
            'processing_time': current_time - last_detection_time
        }
    
    def draw_simulation_results(self, image, detection_data):
        """Simülasyon sonuçlarını çiz"""
        try:
            annotated_image = image.copy()
            height, width = annotated_image.shape[:2]
            
            # Başlık
            title_text = f"SmartSafe AI (SIM) - Kamera: {detection_data.get('camera_id', 'Unknown')}"
            cv2.putText(annotated_image, title_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Uyum oranı
            compliance_rate = detection_data.get('compliance_rate', 0)
            total_people = detection_data.get('total_people', 0)
            
            compliance_color = (0, 255, 0) if compliance_rate >= 80 else (0, 165, 255) if compliance_rate >= 60 else (0, 0, 255)
            cv2.putText(annotated_image, f"Uyum: {compliance_rate:.1f}%", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, compliance_color, 2)
            
            # Kişi sayısı
            cv2.putText(annotated_image, f"Kişi: {total_people}", 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Simülasyon etiketi
            cv2.putText(annotated_image, "SIMULASYON MODU", (10, height-50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # İhlaller
            violations = detection_data.get('violations', [])
            if violations:
                cv2.putText(annotated_image, "İHLALLER:", (width-200, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                for i, violation in enumerate(violations[:3]):
                    violation_text = f"• {violation.get('missing_ppe', ['Unknown'])[0]}"
                    cv2.putText(annotated_image, violation_text, (width-200, 55 + i*20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            cv2.putText(annotated_image, timestamp, (10, height-20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            return annotated_image
            
        except Exception as e:
            print(f"Simülasyon çizim hatası: {e}")
            return image
    
    def draw_sector_detection_results(self, image, detection_result):
        """Sektörel detection sonuçlarını görüntü üzerine çiz"""
        try:
            # Kopyasını al
            result_image = image.copy()
            height, width = result_image.shape[:2]
            
            # Sektör bilgisi
            sector = detection_result.get('sector', 'unknown')
            sector_names = {
                'construction': 'İnşaat',
                'food': 'Gıda', 
                'chemical': 'Kimya',
                'manufacturing': 'İmalat',
                'warehouse': 'Depo'
            }
            sector_name = sector_names.get(sector, sector.upper())
            
            # Başlık bilgisi
            cv2.putText(result_image, f"SmartSafe AI - {sector_name} Sektörü", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Uygunluk oranı
            compliance_rate = detection_result['analysis'].get('compliance_rate', 0)
            color = (0, 255, 0) if compliance_rate > 80 else (0, 165, 255) if compliance_rate > 60 else (0, 0, 255)
            cv2.putText(result_image, f"Uygunluk: {compliance_rate:.1f}%", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # Kişi sayısı
            total_people = detection_result['analysis'].get('total_people', 0)
            cv2.putText(result_image, f"Kişi Sayısı: {total_people}", 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # İhlal sayısı
            violations = detection_result['analysis'].get('violations', [])
            cv2.putText(result_image, f"İhlal: {len(violations)}", 
                       (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            # Sektörel özel bilgiler
            sector_specific = detection_result['analysis'].get('sector_specific', {})

            
            # Zaman damgası
            timestamp = datetime.now().strftime("%H:%M:%S")
            cv2.putText(result_image, timestamp, 
                       (result_image.shape[1] - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Detections çiz (bounding box'lar)
            detections = detection_result.get('detections', [])
            for detection in detections:
                bbox = detection.get('bbox', [])
                if len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    class_name = detection.get('class_name', 'unknown')
                    confidence = detection.get('confidence', 0)
                    
                    color = get_class_color(class_name, is_missing=False)
                    
                    # Label
                    label = f"{class_name} ({confidence:.2f})"
                    
                    # Profesyonel bounding box çiz
                    result_image = draw_styled_box(result_image, x1, y1, x2, y2, label, color)
            
            return result_image
            
        except Exception as e:
            print(f"Draw sector detection results hatası: {e}")
            return image

    def draw_detection_results(self, image, detection_data):
        """Detection sonuçlarını görüntü üzerine çiz"""
        try:
            # Görüntüyü kopyala
            annotated_image = image.copy()
            height, width = annotated_image.shape[:2]
            
            # Başlık bilgileri
            title_text = f"SmartSafe AI - Kamera: {detection_data.get('camera_id', 'Unknown')}"
            cv2.putText(annotated_image, title_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Uyum oranı
            compliance_rate = detection_data.get('compliance_rate', 0)
            total_people = detection_data.get('total_people', 0)
            
            compliance_color = (0, 255, 0) if compliance_rate >= 80 else (0, 165, 255) if compliance_rate >= 60 else (0, 0, 255)
            cv2.putText(annotated_image, f"Uyum: {compliance_rate:.1f}%", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, compliance_color, 2)
            
            # Toplam kişi sayısı
            cv2.putText(annotated_image, f"Kişi: {total_people}", 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # İhlal listesi
            violations = detection_data.get('violations', [])
            if violations:
                cv2.putText(annotated_image, "İHLALLER:", (width-200, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                for i, violation in enumerate(violations[:3]):  # Max 3 ihlal göster
                    violation_text = f"• {violation.get('missing_ppe', ['Unknown'])[0]}"
                    cv2.putText(annotated_image, violation_text, (width-200, 55 + i*20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            cv2.putText(annotated_image, timestamp, (10, height-20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            return annotated_image
            
        except Exception as e:
            print(f"Görüntü çizim hatası: {e}")
            return image  # Hata durumunda orijinal görüntüyü döndür
    
    def generate_frames(self, camera_key):
        """Video frame generator"""
        while True:
            try:
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    # Frame'i JPEG olarak encode et
                    ret, buffer = cv2.imencode('.jpg', frame_buffers[camera_key])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    else:
                        # Boş frame gönder
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
                else:
                    # Kamera aktif değilse boş frame gönder
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
                
                time.sleep(0.033)  # ~30 FPS
                
            except Exception as e:
                print(f"Frame generation error: {e}")
                break
    
    # --- Template methods removed in favor of headless API ---
 
    def add_health_check(self):
        """İYİLEŞTİRİLDİ: Enhanced health check endpoint"""
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Enhanced health check endpoint for monitoring"""
            try:
                # Check database connection (skip in production for faster response)
                db_status = "healthy"
                if not os.environ.get('RENDER'):
                    try:
                        conn = self.db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        self.db.close_connection(conn)
                    except Exception as e:
                        db_status = f"unhealthy: {str(e)}"
                else:
                    # In production, just return healthy to avoid slow health checks
                    db_status = "healthy"
                
                # Check application status
                app_status = "healthy"
                
                # Overall health
                healthy = db_status == "healthy" and app_status == "healthy"
                
                response = {
                    "status": "healthy" if healthy else "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "version": "2.0.0",
                    "services": {
                        "database": db_status,
                        "application": app_status,
                        "cache": "healthy",
                        "rate_limiting": "active"
                    },
                    "uptime": "running",
                    "features": {
                        "caching": True,
                        "mobile_optimization": True,
                        "export_functionality": True,
                        "enhanced_error_handling": True
                    }
                }
                
                return jsonify(response), 200 if healthy else 503
                
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return jsonify({
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }), 503
        
        # İYİLEŞTİRİLDİ: API Documentation endpoint
        @self.app.route('/api/docs', methods=['GET'])
        def api_documentation():
            """API Documentation endpoint"""
            docs = {
                'title': 'SmartSafe AI API Documentation',
                'version': '2.0.0',
                'description': 'Professional PPE Detection API with enhanced features',
                'endpoints': {
                    'health': {
                        'url': '/health',
                        'method': 'GET',
                        'description': 'System health check',
                        'response': {'status': 'healthy', 'timestamp': 'ISO format'}
                    },
                    'dashboard': {
                        'url': '/api/company/{company_id}/dashboard-summary',
                        'method': 'GET',
                        'description': 'Company dashboard summary with real-time statistics',
                        'features': ['Real-time stats', 'Abonelik bilgileri', 'Kameralar', 'Son İhlaller']
                    },
                    'detection': {
                        'url': '/api/detection/start',
                        'method': 'POST',
                        'description': 'Start PPE detection',
                        'parameters': {
                            'camera_id': 'Camera identifier',
                            'detection_mode': 'Sector-specific mode',
                            'confidence': 'Detection confidence (0.1-1.0)'
                        }
                    },
                    'compliance': {
                        'url': '/api/compliance/{company_id}',
                        'method': 'GET',
                        'description': 'Get compliance statistics',
                        'features': ['Cached responses', 'Real-time data', 'Export support']
                    }
                },
                'features': {
                    'caching': 'Response caching for improved performance',
                    'rate_limiting': 'Enhanced rate limiting (200/min, 1000/hour)',
                    'error_handling': 'Detailed error messages with codes',
                    'mobile_optimization': 'Responsive design for mobile devices',
                    'export_functionality': 'CSV, Excel, PDF, JSON export options'
                },
                'sectors': [
                    'construction', 'manufacturing', 'chemical', 'food',
                    'warehouse', 'energy', 'petrochemical', 'marine', 'aviation'
                ]
            }
            return jsonify(docs)

    def add_metrics_endpoint(self): 
        """Add metrics endpoint for Prometheus"""
        @self.app.route('/metrics', methods=['GET'])
        def metrics():
            """Prometheus metrics endpoint"""
            try:
                # Get basic metrics
                stats = {}  # Simplified for now
                
                metrics_data = f"""# HELP smartsafe_status Application status
# TYPE smartsafe_status gauge
smartsafe_status 1

# HELP smartsafe_uptime_seconds Application uptime in seconds
# TYPE smartsafe_uptime_seconds counter
smartsafe_uptime_seconds 3600

# HELP smartsafe_requests_total Total number of requests
# TYPE smartsafe_requests_total counter
smartsafe_requests_total 100
"""
                
                return metrics_data, 200, {'Content-Type': 'text/plain; version=0.0.4'}
                
            except Exception as e:
                logger.error(f"Metrics collection failed: {e}")
                return "# Metrics collection failed", 503, {'Content-Type': 'text/plain'}

    def run(self):
        """API server'ı çalıştır"""
        logger.info("🚀 Starting SmartSafe AI SaaS API Server")
        
        # Health check and metrics are now registered via api (health.py)
        
        # Get port from environment (Render.com compatibility)
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Using port {port}")
        
        # Set the port in app config
        self.app.config['PORT'] = port
        
        # Return the app instance for gunicorn to handle
        return self.app
    
    def _process_yolov8_results(self, results, company_id, detection_mode):
        """YOLOv8 sonuçlarını işle ve PPE compliance analizi yap"""
        people_detected = 0
        ppe_violations = []
        ppe_compliant = 0
        
        try:
            # YOLOv8 results formatı
            if hasattr(results[0], 'boxes') and results[0].boxes is not None:
                boxes = results[0].boxes
                for box in boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Person detection (COCO class 0)
                    if class_id == 0:  # person
                        people_detected += 1
                
                # YOLOv8/COCO modelinde PPE sınıfları yok — gerçek PPE tespiti SH17 gerektirir.
                # 'Herkes uyumlu' varsayımı yapma: ppe_compliant=0, ihlaller raporlanmaz.
                # Bu kod yolu yalnızca SH17 load başarısız olduğunda çalışır.
                ppe_compliant = 0  # Bilinmiyor ile uyumlu aynı şey değil
                
        except Exception as e:
            logger.error(f"❌ YOLOv8 results processing error: {e}")
            
        return people_detected, ppe_compliant, ppe_violations

    # --- Schedule Management Methods ---
    
    def is_detection_running(self, camera_key):
        """Kamera veya kanal için algılamanın aktif olup olmadığını döner.
        
        DB'yi single source of truth olarak kullanır.
        Thread ölmüşse zombie state tespit edilir ve hem DB hem memory temizlenir.
        """
        # Önce DB'ye bak (process-safe)
        try:
            db_active = get_db_adapter().is_detection_active(camera_key)
        except Exception:
            db_active = active_ai_detectors.get(camera_key, False)
        
        if not db_active:
            # DB'de yoksa memory'den de temizle
            active_ai_detectors[camera_key] = False
            return False
        
        # DB aktif diyor — thread gerçekten yaşıyor mu kontrol et
        thread_info = detection_threads.get(camera_key, {})
        thread_obj = thread_info.get('thread') if isinstance(thread_info, dict) else None
        if thread_obj is not None and not thread_obj.is_alive():
            # Zombie: DB True ama thread ölmüş → her yeri temizle
            logger.warning(f"🧟 Zombie detection tespit edildi: {camera_key} — thread ölü. DB+memory temizleniyor.")
            active_ai_detectors[camera_key] = False
            active_detectors[camera_key] = False
            try:
                get_db_adapter().set_detection_active(camera_key, '', '', active=False)
            except Exception:
                pass
            return False
        
        return True

    def internal_start_detection(self, company_id, camera_id, camera_type, mode="ppe", confidence=0.5):
        """Zamanlayıcı tarafından tetiklenen dâhili algılama başlatma."""
        camera_key = f"{company_id}_{camera_id}"
        
        # Ensure DB is ready
        if not self.ensure_database_initialized():
            logger.error(f"❌ Database not ready for scheduled start: {camera_key}")
            return False

        if self.is_detection_running(camera_key):
            logger.debug(f"ℹ️ {camera_key} zaten AI aktif, atlanıyor.")
            return False

        logger.info(f"🚀 Scheduled Start: {camera_key} ({camera_type})")
        
        # AI state set et — DB + memory
        active_ai_detectors[camera_key] = True
        active_detectors[camera_key] = True
        try:
            get_db_adapter().set_detection_active(camera_key, company_id, camera_id, mode, confidence, active=True)
        except Exception as db_err:
            logger.warning(f"⚠️ DB set_detection_active failed: {db_err}")
        
        # Thread başlat
        detection_thread = threading.Thread(
            target=self.saas_detection_worker,
            args=(camera_key, camera_id, company_id, mode, confidence, active_detectors),
            daemon=True
        )
        detection_thread.start()
        
        detection_threads[camera_key] = {
            'thread': detection_thread,
            'config': {
                'mode': mode,
                'confidence': confidence,
                'started_at': datetime.now().isoformat(),
                'source': 'schedule'
            }
        }
        return True

    def internal_stop_detection(self, company_id, camera_id):
        """Zamanlayıcı tarafından tetiklenen dâhili algılama durdurma."""
        camera_key = f"{company_id}_{camera_id}"
        
        if not self.is_detection_running(camera_key):
            return False

        logger.info(f"🛑 Scheduled Stop: {camera_key}")
        active_ai_detectors[camera_key] = False
        active_detectors[camera_key] = False
        try:
            get_db_adapter().set_detection_active(camera_key, '', '', active=False)
        except Exception as db_err:
            logger.warning(f"⚠️ DB set_detection_active(stop) failed: {db_err}")
        
        # Cleanup (detection.py'deki stop_detection mantığıyla paralel)
        if camera_key in detection_threads:
            del detection_threads[camera_key]
            
        if camera_key in camera_captures and camera_captures[camera_key] is not None:
            try:
                camera_captures[camera_key].release()
            except: pass
            del camera_captures[camera_key]
            
        if camera_key in frame_buffers:
            del frame_buffers[camera_key]
            
        # DVR ise PPE bayrağını da indir
        if "_ch" in camera_id:
            try:
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                get_stream_handler().set_ppe_detection_active(camera_id, False)
            except Exception: pass
            
        return True

    def saas_detection_worker(self, camera_key, camera_id, company_id, detection_mode, confidence=0.5, active_detectors_ref=None):
        """SaaS Profesyonel Detection Worker - OPTİMİZE EDİLDİ. active_detectors_ref: blueprint'in yazdığı dict (reloader/çift app için zorunlu)."""
        logger.info(f"🚀 SaaS Detection başlatılıyor - Kamera: {camera_id}, Şirket: {company_id}")
        # Blueprint'ten gelen aynı dict referansını kullan (aksi halde worker False görüyor)
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        self._active_detectors_ref = active_detectors_ref  # Kamera worker thread'leri için
        
        # AI detection state'ini garanti et — worker başladığında True olmalı (memory + DB)
        active_ai_detectors[camera_key] = True
        try:
            get_db_adapter().set_detection_active(camera_key, company_id, camera_id, detection_mode, confidence, active=True)
        except Exception:
            pass
        
        try:
            self._saas_detection_worker_inner(camera_key, camera_id, company_id, detection_mode, confidence, ad)
        except Exception as fatal_err:
            logger.error(f"❌ SaaS Detection worker FATAL: {camera_key} — {fatal_err}", exc_info=True)
        finally:
            # Worker her koşulda (crash, normal çıkış) state'i temizlesin — DB + memory
            active_ai_detectors[camera_key] = False
            try:
                get_db_adapter().set_detection_active(camera_key, '', '', active=False)
            except Exception:
                pass
            logger.info(f"🧹 active_ai_detectors[{camera_key}] = False (worker cleanup — DB+memory)")
    
    def _saas_detection_worker_inner(self, camera_key, camera_id, company_id, detection_mode, confidence, ad):
        """saas_detection_worker iç mantığı — finally cleanup dış katmanda."""
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=20)
        
        # Kamera başlat
        self.start_saas_camera(camera_key, camera_id, company_id, active_detectors_ref=ad)
        
        # PPE Detection Model - SH17 or PoseAware fallback (cihaz SH17/pose ile aynı çözümleyici)
        pose_detector = None
        from utils.torch_device import resolve_inference_device

        device = resolve_inference_device(logger=logger)
        # Sektöre göre varsayılan required_ppe — backend/company/sector_config.ts ile senkron
        SECTOR_DEFAULT_PPE = sector_default_ppe_map()
        def _normalize_sector(s: Optional[str]) -> str:
            if not s or not isinstance(s, str):
                return 'construction'
            k = s.strip().lower()
            if k in ('gıda', 'gida', 'food', 'food_beverage'):
                return 'food'
            if k in ('inşaat', 'insaat', 'construction'):
                return 'construction'
            if k in ('manufacturing', 'warehouse_logistics', 'chemical', 'energy',
                     'petrochemical', 'marine_shipyard', 'aviation'):
                return k
            if 'gıda' in k or 'gida' in k or 'food' in k:
                return 'food'
            if 'inşaat' in k or 'insaat' in k or 'construction' in k:
                return 'construction'
            return k

        try:
            self.ensure_database_initialized()
            if self.db is not None:
                # companies.ppe_requirements tek kaynak — MultiTenantDatabase'de bu metot yok;
                # hasattr(self.db, ...) ile kaçırılıyordu, hep sektör varsayılanına düşüyordu.
                cfg = {}
                try:
                    cfg = get_db_adapter().get_company_detection_config(company_id) or {}
                except Exception as _cfg_err:
                    logger.warning(
                        f"⚠️ get_company_detection_config başarısız: {_cfg_err}"
                    )
                    cfg = {}
                company_data = self.db.get_company_info(company_id)
                sector_raw = (
                    (cfg.get("sector") if isinstance(cfg, dict) else None)
                    or (company_data.get('sector') if company_data and isinstance(company_data, dict) else None)
                    or 'construction'
                )
                sector = _normalize_sector(sector_raw)
            else:
                sector = 'construction'
                logger.warning(f"⚠️ Database not initialized, using default sector: {sector}")
            
            # Şirket bazlı zorunlu PPE: get_company_detection_config → ppe_requirements (DB)
            # None = kolon yok/boş → sektör varsayılanı; [] = şirket açıkça "zorunlu yok" (mandatory hepsi false)
            required_ppe = None
            try:
                if isinstance(cfg, dict):
                    rp = cfg.get("required_ppe")
                    if rp is not None and isinstance(rp, list):
                        required_ppe = list(rp)
                        logger.info(
                            f"📋 Şirket PPE (companies.ppe_requirements): {required_ppe}"
                        )
            except Exception as cfg_err:
                logger.warning(
                    f"⚠️ PPE gereksinimleri okunamadı, sektör varsayılanı kullanılacak: {cfg_err}"
                )
            if required_ppe is None:
                required_ppe = SECTOR_DEFAULT_PPE.get(sector) or SECTOR_DEFAULT_PPE.get(
                    "construction"
                )
                logger.info(
                    f"📋 Sektör varsayılan PPE (ppe_requirements yok): {sector} -> {required_ppe}"
                )
            
            if self.sh17_manager:
                logger.info(f"🎯 SH17 PPE Detection - Sektör: {sector}")
                model_manager = self.sh17_manager
                use_sh17 = True
                
                # Initialize PoseAwarePPEDetector alongside SH17 for enhanced analysis
                try:
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=self.sh17_manager)
                    logger.info("✅ PoseAwarePPEDetector initialized with SH17 backend")
                except Exception as pose_err:
                    logger.warning(f"⚠️ PoseAware init failed, using SH17 directly: {pose_err}")
                    # SH17 modeli yine de kullanılacak, sadece pose-aware kapalı kalır.
                    pose_detector = None
            else:
                # Fallback: PoseAwarePPEDetector with YOLOv8n-Pose (SH17 yoksa)
                model_manager = None
                use_sh17 = False
                try:
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=None)
                    logger.info("✅ PoseAwarePPEDetector initialized (standalone fallback)")
                except Exception as pose_err:
                    logger.warning(f"⚠️ PoseAware fallback failed: {pose_err}")
                    pose_detector = None
            
        except Exception as e:
            logger.error(f"❌ Model yükleme hatası: {e}")
            return
        
        frame_count = 0
        detection_count = 0
        
        # OPTİMİZE EDİLDİ: Frame skip ve confidence ayarları
        _camera_cfg = {}
        if camera_id and self.db is not None:
            _row = self.db.get_camera_by_id(camera_id, company_id)
            if _row:
                _camera_cfg = dict(_row) if not isinstance(_row, dict) else _row
            elif hasattr(self.db, "get_dvr_channel_by_id"):
                _dvr = self.db.get_dvr_channel_by_id(camera_id, company_id)
                if _dvr:
                    _camera_cfg = dict(_dvr) if not isinstance(_dvr, dict) else _dvr
        
        frame_skip = int(_camera_cfg.get('frame_skip', 0) or os.environ.get('FRAME_SKIP', 3))
        if frame_skip < 1:
            frame_skip = 3
        optimized_confidence = max(0.5, confidence)

        if os.environ.get("ROI_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
            logger.info(
                "🧪 ROI_DEBUG: ROI poligonu + kişi kutuları (yeşil=içerde, kırmızı=dışarı); "
                "her tespit turunda stdout/log satırı: total_persons, inside_roi, outside_roi."
            )

        # Event-based ihlal takibi için ViolationTracker başlat
        violation_tracker = get_violation_tracker()
        logger.info("✅ ViolationTracker başlatıldı (event-based)")

        _active = active_ai_detectors.get(camera_key, False)
        logger.info(f"🔍 SaaS Detection worker loop başlıyor: active_ai_detectors.get({camera_key}) = {_active}")
        
        # DVR kanalları için stream hazır olana kadar daha uzun bekle
        _is_dvr = '_ch' in camera_id
        _initial_wait = 0.5 if _is_dvr else 0.1
        logger.info(f"⏳ Initial wait: {_initial_wait}s (DVR={_is_dvr}) for {camera_key}")
        time.sleep(_initial_wait)

        _roi_log_interval = float(os.environ.get("ROI_LOG_INTERVAL_SEC", "15"))
        _roi_log_last = 0.0

        from utils.detection_observability import (
            log_worker_observability_banner,
            record_and_maybe_emit_latency,
        )

        log_worker_observability_banner(logger, camera_id, camera_key)

        while active_ai_detectors.get(camera_key, False):
            try:
                # Frame al
                # Frame al — thread-safe
                if camera_key in frame_buffers:
                    frame = frame_buffers.copy_frame(camera_key)
                    if frame is None:
                        time.sleep(0.01)
                        continue
                    frame_count += 1
                    
                    # OPTİMİZE EDİLDİ: Her 6 frame'de bir tespit yap
                    if frame_count % frame_skip == 0:
                        start_time = time.time()
                        
                        # PPE Detection - PoseAware preferred, SH17 or fallback
                        people_detected = 0
                        ppe_violations = []
                        ppe_compliant = 0
                        
                        pose_aware_handled = False
                        try:
                            with _inference_semaphore:  # Max N thread aynı anda inference
                                if pose_detector is not None:
                                    pose_result = pose_detector.detect_with_pose(
                                        frame, sector, optimized_confidence, required_ppe=required_ppe
                                    )

                                    if isinstance(pose_result, dict):
                                        people_detected = pose_result.get('people_detected', 0)
                                        ppe_compliant = pose_result.get('compliant_people', 0)
                                        raw_violations = pose_result.get('ppe_violations', [])
                                        ppe_violations = raw_violations if isinstance(raw_violations, list) else []
                                        results = pose_result.get('detections', [])
                                        pose_aware_handled = True
                                        logger.debug(
                                            f"🎯 PoseAware: {people_detected} kişi, "
                                            f"{pose_result.get('compliance_rate', 0)}% uyum"
                                        )
                                    elif isinstance(pose_result, list):
                                        results = pose_result
                                        people_detected = sum(
                                            1 for d in results if d.get('class_name') == 'person'
                                        )
                                    else:
                                        results = []

                                elif use_sh17 and model_manager:
                                    results = model_manager.detect_ppe(frame, sector, optimized_confidence)
                                    people_detected = sum(
                                        1 for d in results if d.get('class_name') == 'person'
                                    )
                                else:
                                    results = []
                            
                            if not pose_aware_handled and people_detected > 0 and required_ppe and use_sh17 and model_manager:
                                try:
                                    compliance_result = model_manager.analyze_compliance(results, required_ppe)
                                    ppe_compliant = compliance_result.get('total_detected', 0)
                                    missing = compliance_result.get('missing', [])
                                    ppe_violations = [f"Missing: {item}" for item in missing]
                                except Exception as comp_err:
                                    logger.error(f"❌ SH17 compliance analizi hatası: {comp_err}")
                                    # SH17 analiz hatası: uyumluluk bilinemez; 0 bırak (güvensiz varsayım yapma)
                        except Exception as detection_error:
                            logger.error(f"❌ Detection hatası: {detection_error}")
                            results = []

                        results_pre_roi = list(results) if isinstance(results, list) else []
                        _roi_debug_meta = None
                        _roi_debug = os.environ.get("ROI_DEBUG", "").strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )
                        _bbox_debug = os.environ.get("BBOX_DEBUG", "").strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )

                        # Person-centric tracking (optional): assign stable track_id to person bboxes.
                        # This improves overlay stability and unlocks bbox reliability metrics.
                        try:
                            from utils.person_tracking import assign_track_ids_to_person_detections

                            if isinstance(results, list) and results:
                                persons_now = [
                                    d
                                    for d in results
                                    if isinstance(d, dict) and d.get("class_name") == "person"
                                ]
                                if persons_now:
                                    assign_track_ids_to_person_detections(camera_key, persons_now)
                        except Exception:
                            pass

                        # Analiz bölgesi (normalize poligon): bbox alt-orta noktası ROI dışındaysa elenir.
                        _dz = None
                        try:
                            from utils.detection_roi import (
                                build_roi_debug_meta,
                                filter_detections_by_roi,
                                get_roi_contour_pixels,
                                roi_score_for_bbox,
                            )
                            from utils.bbox_observability import record_bbox_frame

                            _dz = _camera_cfg.get("detection_zones")
                            if isinstance(results, list) and _dz is not None:
                                results, _roi_stats, _roi_on = filter_detections_by_roi(
                                    frame.shape, _dz, results
                                )
                                if _roi_on:
                                    people_detected = sum(
                                        1
                                        for d in results
                                        if isinstance(d, dict)
                                        and d.get("class_name") == "person"
                                    )
                                    if people_detected == 0:
                                        ppe_violations = []
                                        ppe_compliant = 0
                                    else:
                                        ppe_compliant = min(
                                            ppe_compliant, people_detected
                                        )
                                    _t_roi = time.time()
                                    if _t_roi - _roi_log_last >= _roi_log_interval:
                                        logger.info(
                                            "🎯 ROI filtre | bbox’lı=%s içerde=%s dışarıda=%s | kişi=%s",
                                            _roi_stats.get("total_with_bbox", 0),
                                            _roi_stats.get("inside_roi", 0),
                                            _roi_stats.get("outside_roi", 0),
                                            people_detected,
                                        )
                                        _roi_log_last = _t_roi
                            if (
                                (_roi_debug or _bbox_debug)
                                and isinstance(results_pre_roi, list)
                                and _dz is not None
                            ):
                                # Legacy ROI meta (polygon + inside/outside) stays available.
                                _roi_debug_meta = build_roi_debug_meta(frame.shape, _dz, results_pre_roi)

                                # Extended bbox debug meta (raw vs final) — optional.
                                if _bbox_debug:
                                    contour = get_roi_contour_pixels(frame.shape, _dz)
                                    raw_persons = [
                                        d
                                        for d in results_pre_roi
                                        if isinstance(d, dict) and d.get("class_name") == "person"
                                    ]
                                    final_persons = [
                                        d
                                        for d in (results if isinstance(results, list) else [])
                                        if isinstance(d, dict) and d.get("class_name") == "person"
                                    ]
                                    raw_out = []
                                    for p in raw_persons:
                                        bb = p.get("bbox")
                                        if not bb:
                                            continue
                                        raw_out.append({"bbox": bb})
                                    fin_out = []
                                    for p in final_persons:
                                        bb = p.get("bbox")
                                        if not bb:
                                            continue
                                        tid = p.get("track_id")
                                        roi_score = None
                                        if contour is not None:
                                            try:
                                                roi_score, _inside, _inter = roi_score_for_bbox(
                                                    bb, contour, frame.shape
                                                )
                                            except Exception:
                                                roi_score = None
                                        fin_out.append({"bbox": bb, "track_id": tid, "roi_score": roi_score})

                                    if isinstance(_roi_debug_meta, dict):
                                        _roi_debug_meta["raw_persons"] = raw_out
                                        _roi_debug_meta["final_persons"] = fin_out
                                if _roi_debug_meta is not None:
                                    _st = _roi_debug_meta["stats"]
                                    _msg = (
                                        "[ROI_DEBUG] "
                                        f"total_persons={_st['total_persons']} "
                                        f"inside_roi={_st['inside_roi']} "
                                        f"outside_roi={_st['outside_roi']}"
                                    )
                                    print(_msg, flush=True)
                                    logger.info(_msg)

                            # BBox reliability metrics (env-gated) — person-centric.
                            try:
                                persons_now = [
                                    d
                                    for d in (results if isinstance(results, list) else [])
                                    if isinstance(d, dict) and d.get("class_name") == "person"
                                ]
                                record_bbox_frame(
                                    logger,
                                    camera_key,
                                    frame_shape=frame.shape,
                                    person_detections=persons_now,
                                )
                            except Exception:
                                pass
                        except Exception as _roi_err:
                            logger.warning(f"⚠️ ROI filtre atlandı: {_roi_err}")
                        
                        if not results and people_detected == 0:
                            continue

                        # İhlal listesini normalize et (dict formatına çevir, string'leri sar)
                        normalized_ppe_violations, simple_ppe_violations = self._normalize_ppe_violations(ppe_violations)
                        ppe_violations = simple_ppe_violations

                        # ── Decision Engine (runtime reliability gating) ────────────────────
                        # If bbox/tracking/ROI confidence is low, DO NOT emit violation events.
                        decision_summary = {"state": "ACCEPT", "reasons": []}
                        try:
                            from utils.detection_decision import decide_frame
                            contour = None
                            try:
                                if _dz is not None:
                                    contour = get_roi_contour_pixels(frame.shape, _dz)
                            except Exception:
                                contour = None
                            persons_for_decision = [
                                d
                                for d in (results if isinstance(results, list) else [])
                                if isinstance(d, dict) and d.get("class_name") == "person"
                            ]
                            decision_summary = decide_frame(
                                camera_key,
                                persons=persons_for_decision,
                                frame_shape=frame.shape,
                                contour=contour,
                                roi_score_fn=roi_score_for_bbox if contour is not None else None,
                            )
                        except Exception:
                            decision_summary = {"state": "ACCEPT", "reasons": ["decision_error"]}

                        # Eğer kişi var ama hiç ihlal yoksa, tüm kişiler uyumlu kabul edilmeli.
                        # Bu yalnızca pose-aware uyumluluk hesabi 0 bırakmışsa (PPE konfig yok) çalışır.
                        if people_detected > 0 and len(ppe_violations) == 0 and ppe_compliant == 0:
                            ppe_compliant = people_detected

                        # ── EVENT-BASED ViolationTracker entegrasyonu ─────────────────────────
                        # Kişi bazlı ihlal event'leri üret; her ihlal sadece başladığında DB'ye
                        # yazılır (her frame'de spam yerine).
                        tracker_new_violations: list = []
                        tracker_ended_violations: list = []
                        if people_detected > 0 and ppe_violations and decision_summary.get("state") == "ACCEPT":
                            try:
                                # results listesinden person bbox'larını çıkar
                                persons_from_result = [
                                    d for d in (results if isinstance(results, list) else [])
                                    if isinstance(d, dict) and d.get('class_name') == 'person'
                                ]
                                if persons_from_result:
                                    for p_idx, person_det in enumerate(persons_from_result):
                                        if person_det.get("decision") not in (None, "ACCEPT"):
                                            continue
                                        p_bbox = person_det.get('bbox', [0, 0, 10, 10])
                                        new_v, ended_v = violation_tracker.process_detection(
                                            camera_id=camera_id,
                                            company_id=company_id,
                                            person_bbox=p_bbox,
                                            violations=list(ppe_violations),
                                        )
                                        tracker_new_violations.extend(new_v)
                                        tracker_ended_violations.extend(ended_v)
                                else:
                                    # Kişi bbox yok; dummy bbox ile tek kayıt
                                    new_v, ended_v = violation_tracker.process_detection(
                                        camera_id=camera_id,
                                        company_id=company_id,
                                        person_bbox=[0, 0, 10, 10],
                                        violations=list(ppe_violations),
                                    )
                                    tracker_new_violations.extend(new_v)
                                    tracker_ended_violations.extend(ended_v)
                            except Exception as vt_err:
                                logger.warning(f"⚠️ ViolationTracker güncelleme hatası: {vt_err}")
                        elif decision_summary.get("state") != "ACCEPT" and ppe_violations:
                            # Reliability gate: show overlay/metrics but avoid producing false alerts.
                            logger.info(
                                "🛡️ DECISION_GATE [%s] state=%s accept=%s uncertain=%s reject=%s — violation events suppressed",
                                camera_key,
                                decision_summary.get("state"),
                                decision_summary.get("people_accept"),
                                decision_summary.get("people_uncertain"),
                                decision_summary.get("people_reject"),
                            )

                        # ── VIOLATION DB & SNAPSHOT KAYIT ──────────────────────────────────
                        # DVR yoluyla aynı kalitede: snapshot + violation_events + person stats
                        try:
                            db_adapter = get_db_adapter()
                            
                            # 📸 YENİ İHLALLER İÇİN SNAPSHOT ÇEK + VIOLATION_EVENTS TABLOSUNA YAZ
                            if tracker_new_violations:
                                for new_ev in tracker_new_violations:
                                    try:
                                        logger.info(
                                            f"🚨 YENİ İHLAL: {new_ev.get('violation_type')} "
                                            f"| Kişi: {new_ev.get('person_id')} "
                                            f"| Kamera: {camera_id}"
                                        )
                                        
                                        # Kişi bbox'ını bul (snapshot için)
                                        p_bbox = new_ev.get('person_bbox', [0, 0, 10, 10])
                                        
                                        # Kişi görünürlük kontrolü - Barajı %0.5'ten %0.1'e indir (uzak kameralar için)
                                        person_visible = True
                                        if p_bbox and len(p_bbox) == 4 and frame is not None:
                                            px1, py1, px2, py2 = p_bbox
                                            person_area = (px2 - px1) * (py2 - py1)
                                            frame_area = frame.shape[1] * frame.shape[0]
                                            if person_area < (frame_area * 0.001):
                                                person_visible = False
                                        else:
                                            person_visible = False
                                        
                                        # Sadece kişi görünürse crop snapshot çekilir, değilse snapshot alınmaz
                                        snapshot_path = None
                                        try:
                                            snapshot_mgr = get_snapshot_manager()
                                            if person_visible and p_bbox != [0, 0, 10, 10]:
                                                snapshot_path = snapshot_mgr.capture_violation_snapshot(
                                                    frame=frame,
                                                    company_id=company_id,
                                                    camera_id=camera_id,
                                                    person_id=new_ev['person_id'],
                                                    violation_type=new_ev['violation_type'],
                                                    person_bbox=p_bbox,
                                                    event_id=new_ev['event_id']
                                                )
                                            
                                            # Sadece geçerli bir snapshot varsa DB'ye kaydet ve bildir
                                            if snapshot_path:
                                                new_ev['snapshot_path'] = snapshot_path
                                                logger.info(f"📸 VIOLATION SNAPSHOT: {snapshot_path}")
                                                
                                                # violation_events tablosuna kaydet
                                                if db_adapter.add_violation_event(new_ev):
                                                    # Bildirim gönder
                                                    try:
                                                        notifier = get_notification_service(db_adapter)
                                                        notifier.send_violation_notification(new_ev)
                                                    except Exception as notify_err:
                                                        logger.warning(f"⚠️ Bildirim gönderilemedi: {notify_err}")
                                                else:
                                                    logger.warning(
                                                        f"⚠️ violation_events kaydı reddedildi (fail-fast) "
                                                        f"event_id={new_ev.get('event_id')}"
                                                    )
                                            else:
                                                logger.info(f"⏭️ Snapshot alınamadığı için ihlal atlandı (uzak/küçük kişi): {new_ev.get('event_id')}")
                                        except Exception as snap_err:
                                            logger.warning(f"⚠️ Snapshot hatası: {snap_err}")
                                        
                                    except Exception as ev_err:
                                        logger.error(f"❌ Violation event kayıt hatası: {ev_err}")
                            
                            # ✅ BİTEN İHLALLER İÇİN GÜNCELLEME + PERSON STATS
                            for ended_ev in tracker_ended_violations:
                                try:
                                    logger.info(
                                        f"✅ İhlal ÇÖZÜLDÜ: {ended_ev.get('violation_type')} "
                                        f"| Kişi: {ended_ev.get('person_id')} "
                                        f"| Süre: {ended_ev.get('duration_seconds', 0)}s"
                                    )
                                    
                                    # Çözüm snapshot'ı artık alınmıyor (gereksiz tam ekran kaydını önlemek için)
                                    resolution_snapshot_path = None
                                    
                                    # violation_events tablosunu güncelle
                                    db_adapter.update_violation_event(
                                        ended_ev['event_id'],
                                        {
                                            'end_time': ended_ev.get('end_time'),
                                            'duration_seconds': ended_ev.get('duration_seconds'),
                                            'status': ended_ev.get('status', 'resolved'),
                                            'resolution_snapshot_path': resolution_snapshot_path
                                        }
                                    )
                                    
                                    # Kişi ihlal istatistiklerini güncelle (aylık takip)
                                    db_adapter.update_person_violation_stats(
                                        person_id=ended_ev['person_id'],
                                        company_id=company_id,
                                        violation_type=ended_ev['violation_type'],
                                        duration_seconds=ended_ev.get('duration_seconds', 0)
                                    )
                                    
                                except Exception as end_err:
                                    logger.error(f"❌ Ended violation güncelleme hatası: {end_err}")
                        except Exception as result_error:
                            logger.error(f"❌ Result processing hatası: {result_error}")
                        
                        compliance_rate = 0
                        if people_detected > 0:
                            compliance_rate = (ppe_compliant / people_detected) * 100
                        
                        processing_time = (time.time() - start_time) * 1000
                        detection_count += 1
                        record_and_maybe_emit_latency(logger, camera_key, processing_time)

                        fps = 1000 / processing_time if processing_time > 0 else 0
                        
                        if use_sh17 and getattr(self, "sh17_manager", None):
                            current_device = f"SH17/{self.sh17_manager.device}"
                        else:
                            current_device = device
                        logger.info(f"🔍 Detection #{detection_count}: {people_detected} kişi, {ppe_compliant} uyumlu, {len(ppe_violations)} ihlal, {compliance_rate:.1f}% uyum, {processing_time:.1f}ms, {fps:.1f} FPS")
                        logger.info(f"🖥️ Device: {current_device}, Confidence: {optimized_confidence}")
                        logger.info(f"🔍 PPE Violations: {ppe_violations}")
                        
                        # Sonuçları kaydet
                        detection_data = {
                            'camera_id': camera_id,
                            'company_id': company_id,
                            'timestamp': datetime.now().isoformat(),
                            'frame_count': int(frame_count),
                            'detection_count': int(detection_count),
                            'total_people': int(people_detected),  # Frontend uyumlu
                            'people_detected': int(people_detected),
                            'ppe_compliant': int(ppe_compliant),
                            'ppe_violations': ppe_violations,
                            'violations': ppe_violations,  # Frontend uyumlu (string listesi)
                            'violations_detail': normalized_ppe_violations,  # Backend için detaylı dict listesi
                            'compliance_rate': float(round(compliance_rate, 1)),
                            'processing_time_ms': float(round(processing_time, 2)),
                            'processing_time': float(round(processing_time / 1000, 3)),  # Frontend uyumlu
                            'detection_mode': str(detection_mode),
                            'confidence_threshold': float(confidence),
                            'detections': results if isinstance(results, list) else [],  # bbox listesi overlay için
                            'roi_debug': _roi_debug_meta,
                            'decision': decision_summary,
                        }
                        
                        # Queue'ya ekle
                        try:
                            detection_results[camera_key].put_nowait(detection_data)
                        except queue.Full:
                            try:
                                detection_results[camera_key].get_nowait()
                            except queue.Empty:
                                pass
                            detection_results[camera_key].put_nowait(detection_data)
                        
                        # Veritabanına kaydet (Production PostgreSQL için özet kayıt)
                        # Sıklık: Eğer insan varsa her 2 tespitte bir, insan yoksa her 20 tespitte bir yaz (Grafik sürekliliği için)
                        should_save = False
                        if people_detected > 0:
                            if detection_count % 2 == 0:
                                should_save = True
                        else:
                            if detection_count % 20 == 0:
                                should_save = True
                        
                        # İhlal varsa mutlaka kaydet (Eventual consistency)
                        if len(ppe_violations) > 0:
                            should_save = True

                        if should_save:
                            self.save_detection_to_db(detection_data)
                    
                    time.sleep(0.01)  # CPU'yu rahatlatmak için
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"❌ SaaS Detection hatası: {e}")
                time.sleep(1)
        
        _exit_val = ad.get(camera_key, 'KEY_MISSING')
        logger.info(
            f"🛑 SaaS Detection durduruldu - Kamera: {camera_id} | "
            f"active_detectors[{camera_key}]={_exit_val} | "
            f"active_ai_detectors[{camera_key}]={active_ai_detectors.get(camera_key, 'N/A')} | "
            f"frame_count={frame_count} | detection_count={detection_count} | "
            f"id(ad)={id(ad)}"
        )
        # NOT: active_ai_detectors cleanup artık dış katmandaki finally bloğunda yapılıyor

    def _save_detection_to_reports(self, company_id, camera_id, detection_type, 
                                  people_detected, ppe_compliant, violations_count, 
                                  processing_time, confidence):
        """Save detection data to reports table"""
        try:
            # Database adapter kullan - SQLite ve PostgreSQL uyumlu
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            
            if self.db.db_adapter.db_type == 'sqlite':
                cursor.execute(f'''
                    INSERT INTO detections (company_id, camera_id, detection_type, confidence,
                                          people_detected, ppe_compliant, violations_count, timestamp)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                            {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ''', (company_id, camera_id, detection_type, confidence,
                      people_detected, ppe_compliant, violations_count, datetime.now()))
            else:  # PostgreSQL
                cursor.execute(f'''
                    INSERT INTO detections (company_id, camera_id, detection_type, confidence,
                                          people_detected, ppe_compliant, violations_count, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (company_id, camera_id, detection_type, confidence,
                      people_detected, ppe_compliant, violations_count, datetime.now()))
            
            conn.commit()
            self.db.close_connection(conn)
            logger.debug(f"✅ Detection saved to reports: {people_detected} people, {ppe_compliant} compliant")
            
        except Exception as e:
            logger.error(f"❌ Failed to save detection to reports: {e}")

    def _generate_live_alerts(self, company_id, camera_id, people_detected, ppe_compliant, violations_count, detection_mode):
        """Real-time alert generation based on live detection results"""
        try:
            # Alert generation logic
            alerts_to_generate = []
            
            # PPE Violation Alert
            if violations_count > 0:
                alerts_to_generate.append({
                    'alert_type': 'ppe_violation',
                    'severity': 'warning',
                    'title': f'{violations_count} PPE İhlali Tespit Edildi',
                    'message': f'Kamera {camera_id} üzerinde {violations_count} adet PPE ihlali tespit edildi. Acil müdahale gerekli.',
                    'camera_id': camera_id
                })
            
            # High Risk Alert
            if violations_count >= 3:
                alerts_to_generate.append({
                    'alert_type': 'high_risk',
                    'severity': 'critical',
                    'title': 'Yüksek Riskli Durum!',
                    'message': f'Kamera {camera_id} üzerinde {violations_count} adet PPE ihlali tespit edildi. Acil müdahale gerekli!',
                    'camera_id': camera_id
                })
            
            # Compliance Rate Alert
            if people_detected > 0:
                compliance_rate = (ppe_compliant / people_detected) * 100
                if compliance_rate < 50:
                    alerts_to_generate.append({
                        'alert_type': 'low_compliance',
                        'severity': 'warning',
                        'title': 'Düşük Uyum Oranı',
                        'message': f'Kamera {camera_id} üzerinde uyum oranı %{compliance_rate:.1f}. Eğitim gerekli.',
                        'camera_id': camera_id
                    })
            
            # System Status Alert
            if people_detected > 0:
                alerts_to_generate.append({
                    'alert_type': 'system_status',
                    'severity': 'info',
                    'title': 'Sistem Aktif',
                    'message': f'Kamera {camera_id} üzerinde {people_detected} kişi tespit edildi. Sistem normal çalışıyor.',
                    'camera_id': camera_id
                })
            
            # Generate alerts
            for alert_data in alerts_to_generate:
                try:
                    # Alert'i database'e kaydet
                    conn = self.db.get_connection()
                    cursor = conn.cursor()
                    
                    placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                    
                    if self.db.db_adapter.db_type == 'sqlite':
                        cursor.execute(f'''
                            INSERT INTO alerts (company_id, camera_id, alert_type, severity, title, message, status, created_at)
                            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 'active', datetime('now'))
                        ''', (company_id, alert_data['camera_id'], alert_data['alert_type'], alert_data['severity'], 
                              alert_data['title'], alert_data['message']))
                    else:  # PostgreSQL
                        cursor.execute(f'''
                            INSERT INTO alerts (company_id, camera_id, alert_type, severity, title, message, status, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW())
                        ''', (company_id, alert_data['camera_id'], alert_data['alert_type'], alert_data['severity'], 
                              alert_data['title'], alert_data['message']))
                    
                    conn.commit()
                    self.db.close_connection(conn)
                    
                    logger.info(f"✅ Live alert generated: {alert_data['title']} - {alert_data['message']}")
                    
                except Exception as e:
                    logger.error(f"❌ Alert generation error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Live alert generation error: {e}")
    
    def _save_violation_to_reports(self, company_id, camera_id, violation):
        """Save violation data to reports table"""
        try:
            # Database adapter kullan - SQLite ve PostgreSQL uyumlu
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            
            # Violation details
            missing_ppe = violation.get('missing_ppe', ['Unknown'])[0] if isinstance(violation.get('missing_ppe'), list) else violation.get('missing_ppe', 'Unknown')
            violation_type = f"{missing_ppe}_missing"
            
            confidence = violation.get('confidence', 0.8)
            
            if self.db.db_adapter.db_type == 'sqlite':
                cursor.execute(f'''
                    INSERT INTO violations (company_id, camera_id, worker_id, missing_ppe,
                                          violation_type, confidence, timestamp)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder},
                            {placeholder}, {placeholder}, {placeholder})
                ''', (company_id, camera_id, violation.get('person_id', 'unknown'),
                      missing_ppe, violation_type, confidence, datetime.now()))
            else:  # PostgreSQL
                cursor.execute(f'''
                    INSERT INTO violations (company_id, camera_id, worker_id, missing_ppe,
                                          violation_type, confidence, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (company_id, camera_id, violation.get('person_id', 'unknown'),
                      missing_ppe, violation_type, confidence, datetime.now()))
            
            conn.commit()
            self.db.close_connection(conn)
            logger.debug(f"✅ Violation saved to reports: {missing_ppe}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save violation to reports: {e}")

    def _normalize_ppe_violations(self, ppe_violations):
        """PPE ihlallerini tek tip dict formatına çevir.

        Giriş:
          - ['Baret eksik', 'Yelek eksik', ...]  (string listesi)
          - [{'missing_ppe': [...], 'confidence': ..., 'person_id': ...}, ...]

        Çıkış:
          - normalized: [{'person_id': 'person_0', 'missing_ppe': [...], 'confidence': 0.0}, ...]
          - simple:     ['Baret eksik', 'Yelek eksik', ...] (frontend/log için)
        """
        normalized = []
        simple = []

        if ppe_violations is None:
            return [], []
        if not isinstance(ppe_violations, list):
            ppe_violations = [ppe_violations]

        for idx, v in enumerate(ppe_violations):
            if isinstance(v, dict):
                raw_missing = v.get('missing_ppe')
                if isinstance(raw_missing, list) and raw_missing:
                    missing_list = [str(raw_missing[0])]
                elif isinstance(raw_missing, str):
                    missing_list = [raw_missing]
                else:
                    missing_list = ['Unknown']

                person_id = v.get('person_id') or f"person_{idx}"

                conf = v.get('confidence', 0.0)
                try:
                    conf = float(conf)
                except Exception:
                    conf = 0.0

                norm = {
                    'person_id': str(person_id),
                    'missing_ppe': missing_list,
                    'confidence': conf,
                }
            else:
                # String veya diğer tipler - loglarda gördüğümüz 'Baret eksik' vb.
                text = str(v)
                missing_list = [text]
                norm = {
                    'person_id': f"person_{idx}",
                    'missing_ppe': missing_list,
                    'confidence': 0.0,
                }

            normalized.append(norm)
            simple.append(missing_list[0])

        return normalized, simple

    def _run_fallback_ppe_detection(self, results, frame, detection_mode):
            """Run fallback PPE detection using old system"""
            people_detected = 0
            ppe_compliant = 0
            ppe_violations = []
            
            try:
                for result in results:
                    if result.boxes is not None:
                        for box in result.boxes:
                            try:
                                class_id = int(box.cls[0])
                                confidence_score = float(box.conf[0])
                                
                                # Person detection
                                if class_id == 0:  # person class
                                    people_detected += 1
                                    
                                    # Person bbox'ını al
                                    person_bbox = box.xyxy[0].tolist()
                                    
                                    # PPE Detection
                                    ppe_status = self.analyze_ppe_compliance(frame, person_bbox, detection_mode)
                                    
                                    if ppe_status.get('compliant', False):
                                        ppe_compliant += 1
                                    else:
                                        missing_ppe = ppe_status.get('missing_ppe', ['Gerekli PPE Eksik'])
                                        violation = {
                                            'person_id': f"person_{len(ppe_violations)}",
                                            'missing_ppe': missing_ppe,
                                            'confidence': float(confidence_score),
                                            'bbox': [float(x) for x in person_bbox],
                                            'ppe_status': {
                                                'compliant': bool(ppe_status.get('compliant', False)),
                                                'missing_ppe': missing_ppe,
                                                'has_helmet': bool(ppe_status.get('has_helmet', False)),
                                                'has_vest': bool(ppe_status.get('has_vest', False))
                                            }
                                        }
                                        ppe_violations.append(violation)
                                        
                            except Exception as box_error:
                                logger.error(f"❌ Box processing hatası: {box_error}")
                                continue
                                
            except Exception as e:
                logger.error(f"❌ Fallback PPE detection error: {e}")
            
            return people_detected, ppe_compliant, ppe_violations
        
    def _convert_sh17_to_classic_format(self, sh17_result: List[Dict], detection_mode: str) -> Dict[str, Any]:
        """SH17 sonuçlarını klasik PPE formatına çevirir"""
        try:
            if not sh17_result:
                return self._create_empty_result()
            
            # SH17 sonuçlarını işle
            people_detected = 0
            ppe_compliant = 0
            ppe_violations = []
            
            for detection in sh17_result:
                class_name = detection.get('class_name', '')
                confidence = detection.get('confidence', 0.0)
                bbox = detection.get('bbox', [])
                
                # Person detection
                if class_name == 'person':
                    people_detected += 1
                    
                    # PPE compliance kontrolü
                    ppe_status = self._analyze_sh17_ppe_compliance(sh17_result, detection_mode)
                    
                    if ppe_status.get('compliant', False):
                        ppe_compliant += 1
                    else:
                        violation = {
                            'person_id': f"person_{people_detected}",
                            'missing_ppe': ppe_status.get('missing_ppe', ['Gerekli PPE Eksik']),
                            'confidence': confidence,
                            'bbox': bbox,
                            'ppe_status': ppe_status
                        }
                        ppe_violations.append(violation)
            
            return {
                'success': True,
                'people_detected': people_detected,
                'ppe_compliant': ppe_compliant,
                'ppe_violations': ppe_violations,
                'detection_system': 'SH17',
                'detection_mode': detection_mode
            }
            
        except Exception as e:
            logger.error(f"❌ SH17 format conversion error: {e}")
            return self._create_empty_result()
    
    def _analyze_sh17_ppe_compliance(self, detections: List[Dict], sector: str) -> Dict[str, Any]:
        """SH17 detection sonuçlarından PPE compliance analizi"""
        try:
            # Sektör bazlı gerekli PPE — sector_config.ts (sector_ppe_config.py) mandatory listesi
            required_ppe = get_default_mandatory_ppe_ids(sector)
            if not required_ppe:
                required_ppe = get_default_mandatory_ppe_ids("construction")
            detected_ppe = set()

            # Model class_name → sector_config `id` (gıda: haircap → hairnet, …)
            for detection in detections:
                class_name = detection.get("class_name", "")
                if class_name in required_ppe:
                    detected_ppe.add(class_name)
                rid = map_sh17_class_to_config_requirement_id(class_name, sector)
                if rid and rid in required_ppe:
                    detected_ppe.add(rid)

            # Compliance kontrolü
            missing_ppe = [item for item in required_ppe if item not in detected_ppe]
            compliant = len(missing_ppe) == 0

            return {
                'compliant': compliant,
                'missing_ppe': missing_ppe,
                'detected_ppe': list(detected_ppe),
                'required_ppe': required_ppe
            }

        except Exception as e:
            logger.error(f"❌ SH17 compliance analysis error: {e}")
            return {'compliant': False, 'missing_ppe': ['Analysis Error']}
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """Boş detection sonucu oluşturur"""
        return {
            'success': False,
            'people_detected': 0,
            'ppe_compliant': 0,
            'ppe_violations': [],
            'error': 'No detections found'
        }
        


    def analyze_ppe_compliance(self, frame, person_bbox, detection_mode):
        """İYİLEŞTİRİLDİ: PPE uyumluluğunu analiz et - Production ready with enhanced error handling"""
        try:
            import cv2
            import numpy as np
            
            # Input validation - İYİLEŞTİRİLDİ
            if frame is None:
                logger.error("❌ Frame is None")
                return {'compliant': False, 'missing_ppe': ['invalid_frame'], 'error': 'frame_is_none'}
            
            if person_bbox is None or len(person_bbox) != 4:
                logger.error(f"❌ Invalid person_bbox: {person_bbox}")
                return {'compliant': False, 'missing_ppe': ['invalid_bbox'], 'error': 'invalid_bbox_format'}
            
            if detection_mode is None or detection_mode not in ['construction', 'manufacturing', 'chemical', 'food', 'warehouse', 'energy', 'petrochemical', 'marine', 'aviation', 'general']:
                logger.warning(f"⚠️ Invalid detection_mode: {detection_mode}, using general")
                detection_mode = 'general'
            
            # Person bbox'ından ROI çıkar - İYİLEŞTİRİLDİ
            try:
                x1, y1, x2, y2 = map(int, person_bbox)
                
                # Bbox sınırlarını kontrol et
                frame_height, frame_width = frame.shape[:2]
                x1 = max(0, min(x1, frame_width))
                y1 = max(0, min(y1, frame_height))
                x2 = max(x1, min(x2, frame_width))
                y2 = max(y1, min(y2, frame_height))
                
                # ROI boyutunu kontrol et
                if x2 <= x1 or y2 <= y1:
                    logger.warning("⚠️ Invalid bbox dimensions")
                    return {'compliant': False, 'missing_ppe': ['invalid_bbox_dimensions'], 'error': 'invalid_bbox_size'}
                
                person_roi = frame[y1:y2, x1:x2]
            
                if person_roi.size == 0:
                    logger.warning("⚠️ Empty ROI")
                    return {'compliant': False, 'missing_ppe': ['empty_roi'], 'error': 'empty_roi'}
                    
                # ROI boyut kontrolü
                if person_roi.shape[0] < 20 or person_roi.shape[1] < 20:
                    logger.warning(f"⚠️ ROI too small: {person_roi.shape}")
                    return {'compliant': False, 'missing_ppe': ['roi_too_small'], 'error': 'roi_too_small'}
            
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Bbox conversion error: {e}")
                return {'compliant': False, 'missing_ppe': ['bbox_conversion_error'], 'error': str(e)}
            
            # Detection mode'a göre PPE kontrolü - İYİLEŞTİRİLDİ
            try:
                if detection_mode == 'construction':
                    return self.analyze_construction_ppe(person_roi)
                elif detection_mode == 'industrial' or detection_mode == 'manufacturing':
                    return self.analyze_manufacturing_ppe(person_roi)
                elif detection_mode == 'chemical':
                    return self.analyze_chemical_ppe(person_roi)
                elif detection_mode == 'food':
                    return self.analyze_food_ppe(person_roi)
                elif detection_mode == 'warehouse' or detection_mode == 'logistics':
                    return self.analyze_warehouse_ppe(person_roi)
                elif detection_mode == 'energy':
                    return self.analyze_energy_ppe(person_roi)
                elif detection_mode == 'petrochemical':
                    return self.analyze_petrochemical_ppe(person_roi)
                elif detection_mode == 'marine':
                    return self.analyze_marine_ppe(person_roi)
                elif detection_mode == 'aviation':
                    return self.analyze_aviation_ppe(person_roi)
                else:
                    return self.analyze_general_ppe(person_roi)
                    
            except ImportError as e:
                logger.error(f"❌ Import error in sector detection: {e}")
                return self.analyze_construction_ppe_fallback(person_roi)
            except Exception as e:
                logger.error(f"❌ Sektörel PPE analiz hatası: {e}")
                logger.error(f"❌ Error type: {type(e).__name__}")
                logger.error(f"❌ Error details: {str(e)}")
                return self.analyze_construction_ppe_fallback(person_roi)
                
        except Exception as e:
            logger.error(f"❌ PPE analiz genel hatası: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            logger.error(f"❌ Error details: {str(e)}")
            return {'compliant': False, 'missing_ppe': ['analysis_error'], 'error': str(e)}

    def analyze_construction_ppe(self, person_roi):
        """İnşaat sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            # Sektörel detector'ı kullan - Güvenli import
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                logger.info("🔍 Construction detector aranıyor...")
                detector = SectorDetectorFactory.get_detector('construction')
                
                if detector:
                    logger.info("✅ Construction detector bulundu, PPE analizi başlatılıyor...")
                    # Sektörel PPE detection
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    logger.info(f"🔍 Construction detection sonucu: {result}")
                    
                    # Sonuçları formatla
                    missing_ppe = []
                    
                    # Hibrit sistem sonuçlarını kontrol et
                    if result.get('violation_people', 0) > 0:
                        violations = result.get('violations', [])
                        for violation in violations:
                            missing_ppe.extend(violation.get('missing_ppe', []))
                    
                    # Eğer hibrit sistem PPE'yi tespit ettiyse ama violation boşsa
                    if not missing_ppe and result.get('sector_detection', False):
                        # PPE status'dan eksik olanları al
                        ppe_status = result.get('ppe_status', {})
                        required_ppe = ppe_status.get('required_ppe', [])
                        detected_ppe = []
                        
                        if ppe_status.get('has_helmet', False):
                            detected_ppe.append('helmet')
                        if ppe_status.get('has_vest', False):
                            detected_ppe.append('safety_vest')
                        
                        # Eksik PPE'leri hesapla
                        missing_ppe = [item for item in required_ppe if item not in detected_ppe]
                    
                    # Hibrit sistem yanlış sonuç veriyorsa, fallback kullan
                    if not missing_ppe and result.get('sector_detection', False):
                        logger.warning("⚠️ Hibrit sistem yanlış sonuç veriyor, fallback kullanılıyor")
                        fallback_result = self.analyze_construction_ppe_fallback(person_roi)
                        missing_ppe = fallback_result.get('missing_ppe', [])
                    
                    # Eğer hibrit sistem PPE'yi tespit ettiyse ama violation boşsa, zorla ihlal ekle
                    if not missing_ppe and result.get('sector_detection', False):
                        ppe_status = result.get('ppe_status', {})
                        if ppe_status.get('has_helmet', False) and ppe_status.get('has_vest', False):
                            # Hibrit sistem yanlış tespit ediyor, gerçek durumu kontrol et
                            logger.warning("⚠️ Hibrit sistem yanlış PPE tespit ediyor, gerçek durum kontrol ediliyor")
                            missing_ppe = ['Kask', 'Yelek']  # Zorla ihlal ekle
                    
                    # Eğer hibrit sistem PPE'yi tespit ettiyse ama violation boşsa, zorla ihlal ekle
                    if not missing_ppe and result.get('sector_detection', False):
                        # Hibrit sistem yanlış sonuç veriyor, fallback kullan
                        logger.warning("⚠️ Hibrit sistem yanlış sonuç veriyor, fallback kullanılıyor")
                        fallback_result = self.analyze_construction_ppe_fallback(person_roi)
                        missing_ppe = fallback_result.get('missing_ppe', [])
                    
                    # Eğer hibrit sistem PPE'yi tespit ettiyse ama violation boşsa, zorla ihlal ekle
                    if not missing_ppe and result.get('sector_detection', False):
                        # Hibrit sistem yanlış tespit ediyor, gerçek durumu kontrol et
                        logger.warning("⚠️ Hibrit sistem yanlış PPE tespit ediyor, gerçek durum kontrol ediliyor")
                        missing_ppe = ['Kask', 'Yelek']  # Zorla ihlal ekle
                    
                    # PPE'leri Türkçe'ye çevir
                    ppe_translations = {
                        'helmet': 'Kask',
                        'safety_vest': 'Yelek',
                        'gloves': 'Eldiven',
                        'safety_shoes': 'Güvenlik Ayakkabısı',
                        'goggles': 'Gözlük',
                        'mask': 'Maske',
                        'hairnet': 'Saç Filesi',
                        'apron': 'Önlük'
                    }
                    
                    # Türkçe çevirileri uygula
                    missing_ppe_tr = []
                    for ppe in missing_ppe:
                        missing_ppe_tr.append(ppe_translations.get(ppe, ppe))
                    
                    # Eğer hala boşsa, genel ihlal ekle
                    if not missing_ppe_tr:
                        missing_ppe_tr = ['Gerekli PPE Eksik']
                    
                    logger.info(f"🔍 Missing PPE (TR): {missing_ppe_tr}")
                    
                    return {
                        'compliant': result.get('compliance_rate', 0) >= 85.0,
                        'missing_ppe': missing_ppe_tr,
                        'has_helmet': 'helmet' not in missing_ppe,
                        'has_vest': 'safety_vest' not in missing_ppe,
                        'compliance_rate': result.get('compliance_rate', 0),
                        'sector_detection': True
                    }
                else:
                    logger.warning("⚠️ Sektörel detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
                    
            except ImportError as e:
                logger.warning(f"⚠️ Sektörel detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
            
        except Exception as e:
            logger.error(f"❌ Sektörel PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_construction_ppe_fallback(self, person_roi):
        """İYİLEŞTİRİLDİ: Gelişmiş renk bazlı PPE tespiti"""
        try:
            logger.info("🔍 İyileştirilmiş Fallback PPE analizi başlatılıyor...")
            
            # ROI boyut kontrolü
            if person_roi.size == 0 or person_roi.shape[0] < 50 or person_roi.shape[1] < 50:
                logger.warning("⚠️ ROI çok küçük, analiz atlanıyor")
                return {'compliant': False, 'missing_ppe': ['invalid_roi'], 'sector_detection': False}
            
            # Çoklu renk analizi - İYİLEŞTİRİLDİ
            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)
            rgb = cv2.cvtColor(person_roi, cv2.COLOR_BGR2RGB)
            
            # Kask tespiti - Gelişmiş renk aralıkları
            helmet_detected = False
            helmet_confidence = 0.0
            
            # Sarı/Turuncu kask
            helmet_yellow_lower = np.array([15, 50, 50])
            helmet_yellow_upper = np.array([35, 255, 255])
            helmet_yellow_mask = cv2.inRange(hsv, helmet_yellow_lower, helmet_yellow_upper)
            yellow_pixels = np.sum(helmet_yellow_mask)
            
            # Beyaz kask
            helmet_white_lower = np.array([0, 0, 200])
            helmet_white_upper = np.array([180, 30, 255])
            helmet_white_mask = cv2.inRange(hsv, helmet_white_lower, helmet_white_upper)
            white_pixels = np.sum(helmet_white_mask)
            
            # Kırmızı kask
            helmet_red_lower1 = np.array([0, 50, 50])
            helmet_red_upper1 = np.array([10, 255, 255])
            helmet_red_lower2 = np.array([170, 50, 50])
            helmet_red_upper2 = np.array([180, 255, 255])
            helmet_red_mask1 = cv2.inRange(hsv, helmet_red_lower1, helmet_red_upper1)
            helmet_red_mask2 = cv2.inRange(hsv, helmet_red_lower2, helmet_red_upper2)
            red_pixels = np.sum(helmet_red_mask1) + np.sum(helmet_red_mask2)
            
            # En yüksek pixel sayısını bul
            max_helmet_pixels = max(yellow_pixels, white_pixels, red_pixels)
            total_pixels = person_roi.shape[0] * person_roi.shape[1]
            helmet_ratio = max_helmet_pixels / total_pixels if total_pixels > 0 else 0
            
            # Gelişmiş threshold
            helmet_threshold = 0.05  # %5'ten fazla pixel varsa kask var
            helmet_detected = helmet_ratio > helmet_threshold
            helmet_confidence = min(helmet_ratio * 10, 1.0)  # Confidence hesapla
            
            # Yelek tespiti - Gelişmiş renk aralıkları
            vest_detected = False
            vest_confidence = 0.0
            
            # Yeşil yelek
            vest_green_lower = np.array([35, 50, 50])
            vest_green_upper = np.array([85, 255, 255])
            vest_green_mask = cv2.inRange(hsv, vest_green_lower, vest_green_upper)
            green_pixels = np.sum(vest_green_mask)
            
            # Turuncu yelek
            vest_orange_lower = np.array([10, 50, 50])
            vest_orange_upper = np.array([25, 255, 255])
            vest_orange_mask = cv2.inRange(hsv, vest_orange_lower, vest_orange_upper)
            orange_pixels = np.sum(vest_orange_mask)
            
            # Sarı yelek
            vest_yellow_lower = np.array([20, 50, 50])
            vest_yellow_upper = np.array([30, 255, 255])
            vest_yellow_mask = cv2.inRange(hsv, vest_yellow_lower, vest_yellow_upper)
            yellow_vest_pixels = np.sum(vest_yellow_mask)
            
            # En yüksek pixel sayısını bul
            max_vest_pixels = max(green_pixels, orange_pixels, yellow_vest_pixels)
            vest_ratio = max_vest_pixels / total_pixels if total_pixels > 0 else 0
            
            # Gelişmiş threshold
            vest_threshold = 0.08  # %8'den fazla pixel varsa yelek var
            vest_detected = vest_ratio > vest_threshold
            vest_confidence = min(vest_ratio * 8, 1.0)  # Confidence hesapla
            
            # Shape analysis - İYİLEŞTİRİLDİ
            gray = cv2.cvtColor(person_roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # Contour analizi
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Büyük contour'ları bul (kask/yelek şekli)
            large_contours = [c for c in contours if cv2.contourArea(c) > 500]
            
            # Confidence'i shape analizi ile güçlendir
            if len(large_contours) > 0:
                helmet_confidence *= 1.2  # Shape varsa confidence artır
                vest_confidence *= 1.2
            
            logger.info(f"🔍 İyileştirilmiş Fallback sonuçları:")
            logger.info(f"  - Kask: {helmet_detected} (Confidence: {helmet_confidence:.2f})")
            logger.info(f"  - Yelek: {vest_detected} (Confidence: {vest_confidence:.2f})")
            logger.info(f"  - Shape contours: {len(large_contours)}")
            
            # Eksik PPE'leri belirle - İYİLEŞTİRİLDİ
            missing_ppe = []
            compliance_score = 0
            
            if not helmet_detected or helmet_confidence < 0.3:
                missing_ppe.append('Kask')
            else:
                compliance_score += 50
                
            if not vest_detected or vest_confidence < 0.3:
                missing_ppe.append('Yelek')
            else:
                compliance_score += 50
            
            # Eğer hiç PPE tespit edilmediyse, daha akıllı karar ver
            if not missing_ppe and (helmet_confidence < 0.5 or vest_confidence < 0.5):
                missing_ppe = ['Düşük Güvenilirlik - PPE Kontrol Edilmeli']
            
            logger.info(f"🔍 İyileştirilmiş missing PPE: {missing_ppe}")
            logger.info(f"🔍 Compliance score: {compliance_score}")
            
            return {
                'compliant': len(missing_ppe) == 0 and compliance_score >= 80,
                'missing_ppe': missing_ppe,
                'has_helmet': helmet_detected and helmet_confidence >= 0.3,
                'has_vest': vest_detected and vest_confidence >= 0.3,
                'compliance_rate': compliance_score,
                'sector_detection': False,
                'helmet_confidence': helmet_confidence,
                'vest_confidence': vest_confidence
            }
            
        except Exception as e:
            logger.error(f"❌ İyileştirilmiş Fallback PPE analiz hatası: {e}")
            return {'compliant': False, 'missing_ppe': ['analysis_error'], 'sector_detection': False}

    def analyze_manufacturing_ppe(self, person_roi):
        """İmalat sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('manufacturing')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'manufacturing')
                else:
                    logger.warning("⚠️ Manufacturing detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Manufacturing detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Manufacturing PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_food_ppe(self, person_roi):
        """Gıda sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('food')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'food')
                else:
                    logger.warning("⚠️ Food detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Food detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Food PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_warehouse_ppe(self, person_roi):
        """Lojistik/Depo sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('warehouse')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'warehouse')
                else:
                    logger.warning("⚠️ Warehouse detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Warehouse detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Warehouse PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_energy_ppe(self, person_roi):
        """Enerji sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('energy')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'energy')
                else:
                    logger.warning("⚠️ Energy detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Energy detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Energy PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_petrochemical_ppe(self, person_roi):
        """Petrokimya sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('petrochemical')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'petrochemical')
                else:
                    logger.warning("⚠️ Petrochemical detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Petrochemical detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Petrochemical PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_marine_ppe(self, person_roi):
        """Denizcilik sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('marine')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'marine')
                else:
                    logger.warning("⚠️ Marine detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Marine detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Marine PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_aviation_ppe(self, person_roi):
        """Havacılık sektörü PPE analizi - Sektörel sistem ile entegre"""
        try:
            try:
                from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                detector = SectorDetectorFactory.get_detector('aviation')
                
                if detector:
                    result = detector.detect_ppe(person_roi, 'camera_unknown')
                    return self.format_sector_result(result, 'aviation')
                else:
                    logger.warning("⚠️ Aviation detector bulunamadı, fallback kullanılıyor")
                    return self.analyze_construction_ppe_fallback(person_roi)
            except ImportError as e:
                logger.warning(f"⚠️ Aviation detector import hatası: {e}, fallback kullanılıyor")
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Aviation PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_chemical_ppe(self, person_roi):
        """Kimyasal sektör PPE analizi - Sektörel sistem ile entegre"""
        try:
            from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
            detector = SectorDetectorFactory.get_detector('chemical')
            
            if detector:
                result = detector.detect_ppe(person_roi, 'camera_unknown')
                return self.format_sector_result(result, 'chemical')
            else:
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ Chemical PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def analyze_general_ppe(self, person_roi):
        """Genel PPE analizi - Sektörel sistem ile entegre"""
        try:
            from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
            detector = SectorDetectorFactory.get_detector('construction')  # Default
            
            if detector:
                result = detector.detect_ppe(person_roi, 'camera_unknown')
                return self.format_sector_result(result, 'general')
            else:
                return self.analyze_construction_ppe_fallback(person_roi)
        except Exception as e:
            logger.error(f"❌ General PPE analiz hatası: {e}")
            return self.analyze_construction_ppe_fallback(person_roi)

    def format_sector_result(self, result, sector_type):
        """Sektörel sonucu formatla - Tüm sektörler için"""
        try:
            missing_ppe = []
            if result.get('violation_people', 0) > 0:
                violations = result.get('violations', [])
                for violation in violations:
                    missing_ppe.extend(violation.get('missing_ppe', []))
            
            # Sektöre özel PPE kontrolü
            sector_ppe_status = self.get_sector_ppe_status(sector_type, missing_ppe)
            
            return {
                'compliant': result.get('compliance_rate', 0) >= 85.0,
                'missing_ppe': list(set(missing_ppe)),
                'compliance_rate': result.get('compliance_rate', 0),
                'sector_detection': True,
                'sector_type': sector_type,
                'ppe_status': sector_ppe_status
            }
        except Exception as e:
            logger.error(f"❌ Sector result format hatası: {e}")
            return {'compliant': False, 'missing_ppe': ['format_error'], 'sector_detection': False}

    def get_sector_ppe_status(self, sector_type, missing_ppe):
        """Sektöre özel PPE durumu"""
        sector_ppe = {
            'construction': {
                'has_helmet': 'helmet' not in missing_ppe,
                'has_vest': 'safety_vest' not in missing_ppe,
                'has_shoes': 'safety_shoes' not in missing_ppe,
                'required_ppe': ['helmet', 'safety_vest', 'safety_shoes']
            },
            'manufacturing': {
                'has_helmet': 'helmet' not in missing_ppe,
                'has_vest': 'safety_vest' not in missing_ppe,
                'has_gloves': 'gloves' not in missing_ppe,
                'has_glasses': 'safety_glasses' not in missing_ppe,
                'required_ppe': ['helmet', 'safety_vest', 'gloves', 'safety_glasses']
            },
            'chemical': {
                'has_helmet': 'helmet' not in missing_ppe,
                'has_vest': 'safety_vest' not in missing_ppe,
                'has_gloves': 'gloves' not in missing_ppe,
                'has_mask': 'respirator' not in missing_ppe,
                'required_ppe': ['helmet', 'safety_vest', 'gloves', 'respirator']
            },
            'food': {
                # sector_config.ts id'leri: hairnet, face_mask, apron (+ model alias haircap/safety_suit)
                'has_haircap': ('hairnet' not in missing_ppe and 'haircap' not in missing_ppe),
                'has_gloves': 'gloves' not in missing_ppe,
                'has_safety_suit': ('apron' not in missing_ppe and 'safety_suit' not in missing_ppe),
                'has_mask': 'face_mask' not in missing_ppe,
                'required_ppe': get_default_mandatory_ppe_ids('food') or ['hairnet', 'face_mask', 'apron'],
            },
            'food_beverage': {
                'has_haircap': ('hairnet' not in missing_ppe and 'haircap' not in missing_ppe),
                'has_gloves': 'gloves' not in missing_ppe,
                'has_safety_suit': ('apron' not in missing_ppe and 'safety_suit' not in missing_ppe),
                'has_mask': 'face_mask' not in missing_ppe,
                'required_ppe': get_default_mandatory_ppe_ids('food') or ['hairnet', 'face_mask', 'apron'],
            },
            'warehouse': {
                'has_helmet': 'helmet' not in missing_ppe,
                # TS: vest, shoes — SH17 genelde safety_vest / shoes
                'has_vest': ('vest' not in missing_ppe and 'safety_vest' not in missing_ppe),
                'has_shoes': ('shoes' not in missing_ppe and 'safety_shoes' not in missing_ppe),
                'required_ppe': get_default_mandatory_ppe_ids('warehouse') or ['vest', 'shoes'],
            }
        }
        
        return sector_ppe.get(sector_type, {
            'has_helmet': 'helmet' not in missing_ppe,
            'has_vest': 'safety_vest' not in missing_ppe,
            'required_ppe': ['helmet', 'safety_vest']
        })

    def _watchdog_restart_camera(self, camera_key: str) -> bool:
        """StreamWatchdog callback: stale stream tespit edildiğinde kamerayı yeniden başlatır.
        
        Args:
            camera_key: '{company_id}_{camera_id}' formatında
            
        Returns:
            True başarılıysa, False başarısızsa
        """
        try:
            # camera_key formatı: {company_id}_{camera_id}
            # camera_key formatı: COMP_ID_CAMID
            if camera_key.startswith("COMP_"):
                # COMP_ID_... formatı için ilk iki parçayı şirket ID'si olarak al
                temp_parts = camera_key.split('_', 2)
                if len(temp_parts) >= 3:
                    company_id = f"{temp_parts[0]}_{temp_parts[1]}"
                    camera_id = temp_parts[2]
                else:
                    # Alternatif veya yetersiz format
                    company_id = temp_parts[0]
                    camera_id = temp_parts[1] if len(temp_parts) > 1 else camera_key
            else:
                parts = camera_key.split('_', 1)
                if len(parts) < 2:
                    logger.error(f"[Watchdog] Geçersiz camera_key formatı: {camera_key}")
                    return False
                company_id = parts[0]
                camera_id = parts[1]
            
            logger.info(f"[Watchdog] 🔄 Kamera yeniden başlatılıyor: {camera_id} (şirket: {company_id})")
            
            # Eski worker'ı (reader thread) durdur
            active_detectors[camera_key] = False
            time.sleep(1)  # Eski thread'in kapanması için kısa bekleme
            
            # Eski kaynakları temizle
            if camera_key in camera_captures:
                try:
                    camera_captures[camera_key].release()
                except Exception:
                    pass
                del camera_captures[camera_key]
            if camera_key in frame_buffers:
                frame_buffers.pop(camera_key, None) # ThreadSafeDict handle
            
            # Yeniden başlat
            active_detectors[camera_key] = True
            frame_timestamps[camera_key] = time.time()
            self.start_saas_camera(camera_key, camera_id, company_id, active_detectors_ref=active_detectors)
            
            logger.info(f"[Watchdog] ✅ Kamera yeniden başlatıldı: {camera_id}")
            return True
            
        except Exception as exc:
            logger.error(f"[Watchdog] ❌ Kamera yeniden başlatma hatası ({camera_key}): {exc}")
            return False

    def start_saas_camera(self, camera_key, camera_id, company_id, active_detectors_ref=None):
        """SaaS Kamera başlatma - proxy-stream ile aynı kaynak: get_camera_by_id. active_detectors_ref: detection worker'dan gelen dict ref."""
        try:
            from utils.redaction import redact_url
            from urllib.parse import urlsplit

            camera_info = self.db.get_camera_by_id(camera_id, company_id)
            if not camera_info:
                if hasattr(self.db, 'get_dvr_channel_by_id'):
                    camera_info = self.db.get_dvr_channel_by_id(camera_id, company_id)
                    if camera_info:
                        logger.info(f"✅ DVR channel resolved for detection worker: {camera_id}")
            if not camera_info:
                logger.error(f"❌ Kamera bulunamadı: {camera_id}")
                return
            logger.info(f"📷 Detection worker kamera kaynağı: {camera_id} -> ip={camera_info.get('ip_address')} (proxy ile aynı get_camera_by_id)")
            
            # DVR kanalı ise mevcut DVRStreamHandler buffer'ından oku (ayrı RTSP bağlantısı açma)
            if camera_info.get('is_dvr') or str(camera_info.get('camera_type', '')).lower() == 'dvr_channel':
                self._start_dvr_detection_polling(camera_key, camera_id, camera_info, active_detectors_ref)
                return

            # Kamera URL'sini oluştur - Alternatif URL'ler ile
            camera_url = None
            if camera_info.get('ip_address') and camera_info.get('port'):
                protocol = camera_info.get('protocol', 'http')
                ip = camera_info['ip_address']
                port = camera_info['port']
                raw_stream_path = (camera_info.get('stream_path') or '/video').strip()
                # Only normalize casing for relative paths; absolute URLs must keep original casing
                # (credentials and paths can be case-sensitive depending on device).
                stream_path = raw_stream_path.lower() if "://" not in raw_stream_path else raw_stream_path
                username = camera_info.get('username', '')
                password = camera_info.get('password', '')
                
                # Snapshot-only path'ler: Detection worker /video kullanmasın; canlı görüntü /video'ya tek bağlansın
                SNAPSHOT_SUFFIXES = ('/shot.jpg', '/photoaf.jpg', '/photo.jpg', '/image.jpg', '/snapshot.jpg', '/snapshot.cgi', '/image.cgi')
                is_snapshot_path = any(stream_path.endswith(s) or stream_path == s.lstrip('/') for s in SNAPSHOT_SUFFIXES)
                
                if is_snapshot_path:
                    # Snapshot polling ile frame doldur - /video sadece tarayıcı canlı görüntü için kalsın
                    base = f"http://{ip}:{port}"
                    if username and password:
                        base_auth = f"http://{username}:{password}@{ip}:{port}"
                        snapshot_urls = [f"{base_auth}/shot.jpg", f"{base_auth}/photoaf.jpg", f"{base_auth}/photo.jpg",
                                         f"{base_auth}/image.jpg", f"{base_auth}/snapshot.jpg"]
                    else:
                        snapshot_urls = [f"{base}/shot.jpg", f"{base}/photoaf.jpg", f"{base}/photo.jpg",
                                        f"{base}/image.jpg", f"{base}/snapshot.jpg"]
                    auth = (username, password) if (username and password) else None
                    self.start_saas_camera_snapshot_polling(camera_key, snapshot_urls, auth, active_detectors_ref=active_detectors_ref)
                    logger.info(f"✅ Snapshot polling başlatıldı (canlı görüntü /video için ayrıldı): {camera_key}")
                    return
                
                # Ana URL - Authentication ile
                if username and password:
                    if "://" in stream_path:
                        # stream_path is already a full URL; do not prepend http://ip:port (prevents http...8000rtsp://... bugs).
                        camera_url = stream_path
                    elif protocol == 'rtsp':
                        camera_url = f"rtsp://{username}:{password}@{ip}:{port}{stream_path}"
                    else:
                        camera_url = f"http://{username}:{password}@{ip}:{port}{stream_path}"
                else:
                    if "://" in stream_path:
                        camera_url = stream_path
                    elif protocol == 'rtsp':
                        camera_url = f"rtsp://{ip}:{port}{stream_path}"
                    else:
                        camera_url = f"http://{ip}:{port}{stream_path}"

                # Fail-fast validation: if we ended up with a malformed URL, stop early instead of feeding OpenCV garbage.
                try:
                    parts = urlsplit(str(camera_url))
                    if not parts.scheme or not parts.netloc:
                        raise ValueError("missing scheme/netloc")
                    # Guard against accidental concatenation like "http://...:8000rtsp://..."
                    s_url = str(camera_url)
                    if s_url.startswith(("http://", "https://")) and "rtsp://" in s_url:
                        raise ValueError("mixed-scheme URL (http prefix contains rtsp://)")
                    # Optional schema-mismatch guard: if protocol says http but URL is rtsp (or vice versa), prefer URL's scheme.
                    if isinstance(protocol, str) and protocol and parts.scheme and protocol != parts.scheme:
                        logger.warning(
                            f"⚠️ Kamera protocol/URL şema uyuşmazlığı: protocol={protocol}, url={parts.scheme} "
                            f"(camera_id={camera_id}). URL şeması esas alınacak."
                        )
                except Exception as exc:
                    logger.error(f"❌ Geçersiz kamera URL (fail-fast): {redact_url(str(camera_url))} — {exc}")
                    return

                
                # Alternatif URL'ler - Önce snapshot'lar (canlı görüntü /video ile çakışmasın), sonra stream
                if username and password:
                    alternative_urls = [
                        f"http://{username}:{password}@{ip}:{port}/shot.jpg",
                        f"http://{username}:{password}@{ip}:{port}/photoaf.jpg",
                        f"http://{username}:{password}@{ip}:{port}/photo.jpg",
                        f"http://{username}:{password}@{ip}:{port}/video",
                        f"http://{username}:{password}@{ip}:{port}/mjpeg",
                        f"http://{username}:{password}@{ip}:{port}/stream",
                        f"http://{username}:{password}@{ip}:{port}/live",
                        f"http://{username}:{password}@{ip}:{port}/camera",
                        f"http://{username}:{password}@{ip}:{port}/webcam"
                    ]
                else:
                    alternative_urls = [
                        f"http://{ip}:{port}/shot.jpg",
                        f"http://{ip}:{port}/photoaf.jpg",
                        f"http://{ip}:{port}/photo.jpg",
                        f"http://{ip}:{port}/video",
                        f"http://{ip}:{port}/mjpeg",
                        f"http://{ip}:{port}/stream",
                        f"http://{ip}:{port}/live",
                        f"http://{ip}:{port}/camera",
                        f"http://{ip}:{port}/webcam"
                    ]
                
                # Kamera worker'ı alternatif URL'ler ile başlat
                self.start_camera_with_alternatives(camera_key, camera_url, alternative_urls, active_detectors_ref=active_detectors_ref)
                return
            else:
                # Webcam kullan
                camera_url = 0
            
            # Kamera worker thread'ini başlat
            camera_thread = threading.Thread(
                target=self.saas_camera_worker,
                args=(camera_key, camera_url, active_detectors_ref),
                daemon=True
            )
            camera_thread.start()
            
            logger.info(f"✅ SaaS Kamera başlatıldı: {camera_id} -> {redact_url(str(camera_url))}")
            
        except Exception as e:
            logger.error(f"❌ SaaS Kamera başlatma hatası: {e}")

    def _start_dvr_detection_polling(self, camera_key, camera_id, camera_info, active_detectors_ref=None):
        """DVR kanalı için detection frame polling — mevcut DVRStreamHandler buffer'ından okur."""
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors

        def _dvr_poll_worker():
            import base64
            poll_count = 0
            try:
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                sh = get_stream_handler()

                dvr_id = camera_info.get('dvr_id', '')
                ch_num = camera_info.get('channel_number')
                if not dvr_id and '_ch' in camera_id:
                    dvr_id = camera_id.rsplit('_ch', 1)[0]
                if ch_num is None and '_ch' in camera_id:
                    try:
                        ch_num = int(camera_id.rsplit('_ch', 1)[1])
                    except (ValueError, IndexError):
                        ch_num = 1
                stream_id = f"{dvr_id}_ch{ch_num:02d}" if ch_num else camera_id

                ip = camera_info.get('ip_address')
                user = camera_info.get('username', 'admin')
                pwd = camera_info.get('password', '')
                rtsp_port = camera_info.get('port') or 554
                rtsp_url = camera_info.get('rtsp_url') or camera_info.get('stream_path') or ''

                company_id = camera_info.get('company_id', '')

                # Proxy stream zaten aynı stream_id'yi kullanıyor olabilir
                # ÖNCELİKLE: Proxy stream kontrol et (SaaS modunda en yaygın durum)
                proxy_sid = f"proxy:{company_id}:{stream_id}"
                proxy_status = sh.get_stream_status(proxy_sid)
                
                if proxy_status and proxy_status.get('status') == 'active':
                    stream_id = proxy_sid
                    logger.info(f"✅ DVR stream already active as (proxy), reusing: {stream_id}")
                else:
                    # Alternatif: Düz stream_id kontrol et
                    status = sh.get_stream_status(stream_id)
                    if status and status.get('status') == 'active':
                        logger.info(f"✅ DVR stream already active (plain), reusing: {stream_id}")
                    else:
                        logger.info(f"🔄 DVR stream not active, starting: {stream_id}")
                        sh.start_stream(
                            stream_id=stream_id,
                            rtsp_url=rtsp_url,
                            ip_address=ip,
                            username=user,
                            password=pwd,
                            rtsp_port=int(rtsp_port),
                            channel_number=ch_num,
                            company_id=company_id,
                        )
                        deadline = time.time() + 30
                        while time.time() < deadline:
                            s = sh.get_stream_status(stream_id)
                            if s and s.get('status') == 'active':
                                break
                            time.sleep(0.5)

                logger.info(f"✅ DVR detection polling started: {camera_key} -> stream {stream_id}")

                while ad.get(camera_key, False):
                    try:
                        frame_b64 = sh.get_latest_frame(stream_id)
                        if frame_b64:
                            jpg_bytes = base64.b64decode(frame_b64)
                            nparr = np.frombuffer(jpg_bytes, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                frame_buffers[camera_key] = frame
                                poll_count += 1
                        time.sleep(0.04)
                    except Exception as poll_err:
                        logger.debug(f"⚠️ DVR poll frame error: {poll_err}")
                        time.sleep(0.2)

                logger.info(f"🛑 DVR poll worker exiting: {camera_key} | active={ad.get(camera_key, 'N/A')} | frames_polled={poll_count}")
            except Exception as e:
                logger.error(f"❌ DVR detection polling error ({camera_key}): {e}", exc_info=True)

        t = threading.Thread(target=_dvr_poll_worker, daemon=True)
        t.start()
        logger.info(f"✅ DVR detection polling thread started: {camera_key}")

    def start_camera_with_alternatives(self, camera_key, primary_url, alternative_urls, active_detectors_ref=None):
        """Alternatif URL'ler ile kamera başlatma"""
        try:
            camera_thread = threading.Thread(
                target=self.saas_camera_worker_with_alternatives,
                args=(camera_key, primary_url, alternative_urls, active_detectors_ref),
                daemon=True
            )
            camera_thread.start()
            
            logger.info(f"✅ Alternatif URL'ler ile kamera başlatıldı: {camera_key}")
            
        except Exception as e:
            logger.error(f"❌ Alternatif kamera başlatma hatası: {e}")

    def start_saas_camera_snapshot_polling(self, camera_key, snapshot_urls, auth=None, active_detectors_ref=None):
        """Snapshot URL'leri ile polling worker başlat - /video canlı görüntüye kalsın"""
        try:
            camera_thread = threading.Thread(
                target=self.saas_camera_worker_snapshot_polling,
                args=(camera_key, snapshot_urls, auth, active_detectors_ref),
                daemon=True
            )
            camera_thread.start()
        except Exception as e:
            logger.error(f"❌ Snapshot polling başlatma hatası: {e}")

    def saas_camera_worker_snapshot_polling(self, camera_key, snapshot_urls, auth=None, active_detectors_ref=None):
        """Snapshot URL'lerden periyodik frame al - MJPEG /video tarayıcıya ayrılır"""
        working_url = None
        poll_interval = 0.25  # 4 FPS snapshot - detection için yeterli
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        try:
            for url in snapshot_urls:
                try:
                    req_auth = auth if (auth and '@' not in url) else None
                    r = requests.get(url, auth=req_auth, timeout=5)
                    if r.status_code == 200 and len(r.content) > 100:
                        working_url = url
                        logger.info(f"✅ Snapshot URL kullanılıyor: {url.split('@')[-1] if '@' in url else url}")
                        break
                except Exception:
                    continue
            if not working_url:
                logger.error(f"❌ Snapshot URL çalışmadı: {camera_key}")
                return
            # URL'de kimlik varsa (user:pass@host) auth gönderme
            use_auth = auth if (auth and '@' not in working_url) else None
            camera_captures[camera_key] = None  # VideoCapture yok
            while ad.get(camera_key, False):
                try:
                    r = requests.get(working_url, auth=use_auth, timeout=3)
                    if r.status_code == 200 and r.content:
                        arr = np.frombuffer(r.content, np.uint8)
                        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame_buffers[camera_key] = frame
                except Exception as e:
                    logger.debug(f"Snapshot poll hatası: {e}")
                time.sleep(poll_interval)
        finally:
            if camera_key in camera_captures:
                del camera_captures[camera_key]
            if camera_key in frame_buffers:
                del frame_buffers[camera_key]
            logger.info(f"🛑 SaaS Snapshot polling durduruldu: {camera_key}")

    def saas_camera_worker_with_alternatives(self, camera_key, primary_url, alternative_urls, active_detectors_ref=None):
        """Alternatif URL'ler ile kamera worker"""
        cap = None
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        try:
            import cv2
            from utils.redaction import redact_url
            
            # Önce ana URL'yi dene
            logger.info(f"🔍 Ana URL deneniyor: {redact_url(str(primary_url))}")
            cap = cv2.VideoCapture(primary_url)
            current_url = primary_url
            
            # Authentication ile dene - Daha güvenilir yöntem
            if not cap.isOpened() and '@' in primary_url:
                logger.info(f"🔐 Güvenli URL ayrıştırma ve authentication deneniyor...")
                try:
                    # Protokolü ayır
                    protocol = "http"
                    url_to_parse = primary_url
                    if "://" in primary_url:
                        protocol, url_to_parse = primary_url.split("://", 1)
                    
                    # Kullanıcı adı ve şifreyi ayrıştır
                    if "@" in url_to_parse:
                        auth_part, base_url = url_to_parse.rsplit("@", 1)
                        
                        if ":" in auth_part:
                            username, password = auth_part.split(":", 1)
                        else:
                            username, password = auth_part, ""
                        
                        # Karakterleri decode et (URL'de %40 gibi yazılmış olabilir)
                        username = unquote(username)
                        password = unquote(password)
                        
                        # OpenCV authentication set etmeyi dene (base_url ile)
                        full_base_url = f"{protocol}://{base_url}"
                        cap = cv2.VideoCapture(full_base_url)
                        
                        if cap.isOpened():
                            cap.set(cv2.CAP_PROP_USERNAME, username)
                            cap.set(cv2.CAP_PROP_PASSWORD, password)
                            logger.info(f"✅ OpenCV-native authentication başarılı: {username}")
                        else:
                            # Klasik yöntem: Safe URL oluştur (özel karakterleri koru)
                            safe_user = quote(username)
                            safe_pass = quote(password, safe='') # safe='' şifredeki / : falan her şeyi quote'lar
                            safe_url = f"{protocol}://{safe_user}:{safe_pass}@{base_url}"
                            
                            cap.release()
                            cap = cv2.VideoCapture(safe_url)
                            if cap.isOpened():
                                logger.info(f"✅ Güvenli URL ile bağlantı başarılı: {username} (protocol: {protocol})")
                            else:
                                logger.warning(f"❌ Güvenli URL bağlantısı başarısız: {protocol}://{username}:***@{base_url}")
                except Exception as auth_error:
                    logger.warning(f"⚠️ Authentication ayrıştırma hatası: {auth_error}")
            
            if not cap.isOpened():
                logger.warning(f"⚠️ Ana URL başarısız, alternatifler deneniyor...")
                
                # Alternatif URL'leri dene
                for alt_url in alternative_urls:
                    logger.info(f"🔍 Alternatif URL deneniyor: {redact_url(str(alt_url))}")
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                    cap = cv2.VideoCapture(alt_url)
                    
                    if cap.isOpened():
                        logger.info(f"✅ Alternatif URL başarılı: {redact_url(str(alt_url))}")
                        current_url = alt_url
                        break
                    else:
                        logger.warning(f"❌ Alternatif URL başarısız: {redact_url(str(alt_url))}")
            
            if not cap.isOpened():
                logger.error(f"❌ Hiçbir URL çalışmadı: {camera_key}")
                return
            
            # Kamera ayarları
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            
            camera_captures[camera_key] = cap
            
            logger.info(f"✅ SaaS Kamera worker başladı: {camera_key}")
            frame_failure_counts[camera_key] = 0
            frame_timestamps[camera_key] = time.time()  # Watchdog için ilk timestamp
            
            # ── Güçlendirilmiş reconnect parametreleri ──────────────────────
            MAX_RECONNECT_ATTEMPTS = 5
            reconnect_attempt = 0
            consecutive_failures = 0
            MAX_CONSECUTIVE_FAILURES = 30  # Bu kadar ardışık hata → reconnect dene
            
            while ad.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    frame_buffers[camera_key] = frame
                    frame_timestamps[camera_key] = time.time()  # Watchdog timestamp güncelle
                    frame_failure_counts[camera_key] = 0
                    consecutive_failures = 0
                    reconnect_attempt = 0  # Başarılı frame → reconnect sayacını sıfırla
                else:
                    consecutive_failures += 1
                    frame_failure_counts[camera_key] = consecutive_failures
                    
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        # ── Reconnect mantığı (exponential backoff ile) ──────
                        if reconnect_attempt >= MAX_RECONNECT_ATTEMPTS:
                            logger.error(
                                f"❌ Max reconnect denemesi aşıldı ({MAX_RECONNECT_ATTEMPTS}): "
                                f"{camera_key} — kamera kalıcı arıza olarak işaretleniyor"
                            )
                            ad[camera_key] = False  # Detection worker'ı durdur
                            break
                        
                        reconnect_attempt += 1
                        backoff = min(2 ** (reconnect_attempt - 1), 16)  # 1→2→4→8→16s
                        logger.warning(
                            f"⚠️ Ardışık {consecutive_failures} hata — {camera_key}, "
                            f"reconnect denemesi {reconnect_attempt}/{MAX_RECONNECT_ATTEMPTS} "
                            f"(backoff {backoff}s)"
                        )
                        
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                        
                        time.sleep(backoff)
                        
                        # Önce son başarılı URL'yi dene
                        reconnected = False
                        all_urls = [current_url] + [u for u in alternative_urls if u != current_url]
                        
                        for url in all_urls:
                            try:
                                cap = cv2.VideoCapture(url)
                                if cap.isOpened():
                                    test_ret, test_frame = cap.read()
                                    if test_ret and test_frame is not None:
                                        logger.info(f"✅ Reconnect başarılı ({reconnect_attempt}. deneme): {camera_key}")
                                        current_url = url
                                        camera_captures[camera_key] = cap
                                        consecutive_failures = 0
                                        reconnected = True
                                        frame_timestamps[camera_key] = time.time()
                                        break
                                    else:
                                        cap.release()
                                        cap = None
                                else:
                                    if cap:
                                        cap.release()
                                    cap = None
                            except Exception:
                                if cap:
                                    try:
                                        cap.release()
                                    except Exception:
                                        pass
                                cap = None
                                continue
                        
                        if not reconnected:
                            logger.warning(
                                f"⚠️ Reconnect başarısız ({reconnect_attempt}. deneme): "
                                f"{camera_key} — sonraki denemede tekrar denenecek"
                            )
                            # cap None kalacak, döngünün başına döndüğünde yine hata alıp
                            # tekrar reconnect'e girecek
                            if cap is None:
                                cap = cv2.VideoCapture(current_url)
                                camera_captures[camera_key] = cap
                        
                        continue  # Reconnect sonrası döngünün başına dön
                    
                    # Çok fazla log atmamak için sadece belirli eşiklerde uyarı ver
                    elif consecutive_failures in (1, 5, 10, 20):
                        logger.debug(f"⚠️ Frame okunamadı (count={consecutive_failures}): {camera_key}")
                    
                    time.sleep(0.05)
                    
        except Exception as e:
            logger.error(f"❌ SaaS Kamera worker hatası: {e}")
        finally:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
            if camera_key in camera_captures:
                del camera_captures[camera_key]
            if camera_key in frame_buffers:
                del frame_buffers[camera_key]
            if camera_key in frame_timestamps:
                del frame_timestamps[camera_key]
            
            logger.info(f"🛑 SaaS Kamera worker durduruldu: {camera_key}")

    def saas_camera_worker(self, camera_key, camera_url, active_detectors_ref=None):
        """SaaS Kamera Worker"""
        cap = None
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        try:
            import cv2
            
            # Kamera bağlantısı - Daha esnek
            cap = cv2.VideoCapture(camera_url)
            
            # Birkaç kez deneme
            retry_count = 0
            while not cap.isOpened() and retry_count < 3:
                logger.warning(f"⚠️ Kamera bağlantısı başarısız, tekrar deneniyor... ({retry_count + 1}/3)")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(camera_url)
                retry_count += 1
            
            if not cap.isOpened():
                logger.error(f"❌ Kamera açılamadı: {camera_url}")
                return
            
            # Kamera ayarları
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            
            camera_captures[camera_key] = cap
            
            logger.info(f"✅ SaaS Kamera worker başladı: {camera_key}")
            frame_failure_counts[camera_key] = 0
            
            while ad.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    frame_buffers[camera_key] = frame
                    frame_failure_counts[camera_key] = 0
                else:
                    frame_failure_counts[camera_key] = frame_failure_counts.get(camera_key, 0) + 1
                    fail_count = frame_failure_counts[camera_key]
                    
                    if fail_count % 30 == 0:
                        logger.warning(f"⚠️ Frame okunamadı (ardışık {fail_count}) - {camera_key}")
                    elif fail_count in (1, 5, 10):
                        logger.debug(f"⚠️ Frame okunamadı (count={fail_count}): {camera_key}")
                    
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"❌ SaaS Kamera worker hatası: {e}")
        finally:
            if cap:
                cap.release()
            if camera_key in camera_captures:
                del camera_captures[camera_key]
            if camera_key in frame_buffers:
                del frame_buffers[camera_key]
            
            logger.info(f"🛑 SaaS Kamera worker durduruldu: {camera_key}")

    def generate_saas_frames(self, camera_key, company_id, camera_id, active_detectors_ref=None):
        """SaaS Frame Generator - detection state ref ile senkron"""
        
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        
        while ad.get(camera_key, False):
            try:
                # Frame al
                if camera_key in frame_buffers:
                    frame = frame_buffers.copy_frame(camera_key)
                    if frame is None:
                        time.sleep(0.01)
                        continue
                    
                    # Detection sonuçlarını al
                    detection_overlay = self.get_detection_overlay(camera_key)
                    
                    # Overlay ekle
                    if detection_overlay:
                        frame = self.draw_saas_overlay(frame, detection_overlay)
                    
                    # Frame'i encode et
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                else:
                    # Placeholder: Kamera worker henüz frame doldurmadıysa okunabilir mesaj
                    import numpy as np
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    placeholder[:] = (40, 40, 40)  # Koyu gri arka plan (siyah değil)
                    cv2.putText(placeholder, 'Kamera hazirlaniyor...', (120, 220),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
                    cv2.putText(placeholder, 'PPE Detection aktif', (180, 270),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2)
                    
                    ret, buffer = cv2.imencode('.jpg', placeholder)
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                time.sleep(0.033)  # ~30 FPS (0.05'ten 0.033'e düşürüldü)
                
            except Exception as e:
                logger.error(f"❌ Frame generation hatası: {e}")
                time.sleep(0.1)

    def get_detection_overlay(self, camera_key):
        """Detection overlay bilgilerini al"""
        try:
            if camera_key in detection_results:
                # En son detection sonucunu al
                latest_result = None
                temp_results = []
                
                # Queue'dan tüm sonuçları al
                while not detection_results[camera_key].empty():
                    try:
                        result = detection_results[camera_key].get_nowait()
                        temp_results.append(result)
                    except queue.Empty:
                        break
                
                # En son sonucu al
                if temp_results:
                    latest_result = temp_results[-1]
                    
                    # Sonuçları geri koy (sadece son 5'ini)
                    for result in temp_results[-5:]:
                        try:
                            detection_results[camera_key].put_nowait(result)
                        except queue.Full:
                            break
                
                return latest_result
            
        except Exception as e:
            logger.error(f"❌ Detection overlay hatası: {e}")
        
        return None

    def draw_saas_overlay(self, frame, detection_data):
        """SaaS Detection Overlay çiz - Bounding Box'lar ile"""
        
        try:
            # Detection data type kontrolü - String ise işleme
            if not isinstance(detection_data, dict):
                logger.warning(f"⚠️ Detection data string olarak geldi: {type(detection_data)}")
                return frame
            
            people_count = detection_data.get('people_detected', 0)
            compliance_rate = detection_data.get('compliance_rate', 0)
            violations = detection_data.get('ppe_violations', [])
            sector = detection_data.get('sector')

            compliant_count = max(0, people_count - len(violations)) if people_count > 0 else 0
            if compliance_rate > 0 and people_count > 0:
                compliant_count = int(round(compliance_rate * people_count / 100))

            frame = draw_hud_bar(
                frame,
                people=people_count,
                compliant=compliant_count,
                compliance_rate=compliance_rate,
                violations_count=len(violations),
                sector=sector,
            )

            reset_label_registry()

            roi_dbg = detection_data.get("roi_debug")
            if roi_dbg and isinstance(roi_dbg, dict):
                _draw_roi_debug_on_frame(frame, roi_dbg)

            # 🎯 BOUNDING BOX ÇİZİMİ - PPE Detection Sonuçları
            # Draw order: persons first, then positive PPE, then missing PPE
            # so that label deconfliction stacks missing labels above positive ones.
            detections = detection_data.get('detections', [])
            if detections and isinstance(detections, list):
                persons = []
                positives = []
                negatives = []
                for det in detections:
                    if not isinstance(det, dict):
                        continue
                    cn = str(det.get('class_name', '')).lower()
                    if cn in ('person', 'kisi', 'insan'):
                        persons.append(det)
                    elif det.get('missing', False):
                        negatives.append(det)
                    else:
                        positives.append(det)

                for detection in persons + positives + negatives:
                    bbox = detection.get('bbox', [])
                    class_name = detection.get('class_name', 'unknown')
                    confidence = detection.get('confidence', 0.0)
                    is_missing = bool(detection.get('missing', False))
                    is_person = class_name.lower() in ('person', 'kisi', 'insan')

                    if roi_dbg and isinstance(roi_dbg, dict) and is_person:
                        continue

                    if len(bbox) == 4:
                        try:
                            x1, y1, x2, y2 = [int(coord) for coord in bbox]
                            
                            color = get_class_color(class_name, is_missing=is_missing)
                            
                            label = f"{class_name} {confidence:.2f}"
                            
                            frame = draw_styled_box(
                                frame, x1, y1, x2, y2, label, color,
                                confidence=confidence,
                                is_person=is_person,
                                is_missing=is_missing,
                            )
                        except Exception as bbox_error:
                            logger.warning(f"⚠️ Bounding box çizim hatası: {bbox_error}")
                            continue
            
            # Zaman damgası (sağ alt köşe)
            timestamp = detection_data.get('timestamp', '')
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        from datetime import datetime as dt
                        timestamp_str = dt.fromtimestamp(timestamp).strftime('%H:%M:%S')
                    else:
                        timestamp_str = str(timestamp)[:8]
                    
                    fh, fw = frame.shape[:2]
                    ts_font = cv2.FONT_HERSHEY_DUPLEX
                    ts_scale = max(0.35, 0.40 * max(0.45, min(fh / 720.0, 2.0)))
                    (tsw, tsh), _ = cv2.getTextSize(timestamp_str, ts_font, ts_scale, 1)
                    cv2.putText(frame, timestamp_str, (fw - tsw - 10, fh - 10),
                                ts_font, ts_scale, (200, 200, 200), 1, cv2.LINE_AA)
                except Exception as ts_error:
                    logger.warning(f"⚠️ Timestamp çizim hatası: {ts_error}")
            
        except Exception as e:
            logger.error(f"❌ Overlay çizim hatası: {e}")
        
        return frame

    def save_detection_to_db(self, detection_data):
        """Detection özetini PostgreSQL detections tablosuna yazar; şema database_adapter ile tek kaynak."""
        try:
            if not hasattr(self.db, 'db_adapter'):
                return

            db_type = getattr(self.db.db_adapter, 'db_type', 'sqlite')
            if db_type == 'sqlite':
                logger.debug("Skipping save_detection_to_db on sqlite (legacy detections schema is used).")
                return

            adapter = self.db.db_adapter
            if not hasattr(adapter, 'add_camera_detection_result'):
                return

            violations = detection_data.get('ppe_violations') or detection_data.get('violations') or []
            violations_count = len(violations) if isinstance(violations, list) else int(violations or 0)
            people = int(
                detection_data.get('people_detected', detection_data.get('total_people', 0))
            )
            ppe_ok = int(detection_data.get('ppe_compliant', 0))

            payload = {
                'company_id': detection_data['company_id'],
                'camera_id': detection_data['camera_id'],
                'detection_type': str(detection_data.get('detection_mode', 'ppe')),
                'confidence': float(detection_data.get('confidence_threshold', 0.0)),
                'people_detected': people,
                'ppe_compliant': ppe_ok,
                'violations_count': violations_count,
                'total_people': people,
                'compliance_rate': detection_data.get('compliance_rate'),
                'processing_time_ms': detection_data.get('processing_time_ms'),
            }
            if adapter.add_camera_detection_result(payload):
                logger.debug(
                    "✅ Detection kaydedildi (summary): %s",
                    detection_data.get('camera_id', 'unknown'),
                )
            
        except Exception as e:
            logger.warning(f"⚠️ Detection DB kayıt hatası (devam ediliyor): {e}")
            # Production'da DB hatası olsa bile detection devam etsin

    def save_violations_to_db(self, company_id, camera_id, violations):
        """İhlalleri veritabanına kaydet - Production uyumlu"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            
            for violation in violations:
                # Production uyumlu şema - confidence kolonu kullan
                cursor.execute(f'''
                    INSERT INTO violations (
                        company_id, camera_id, timestamp, violation_type, 
                        missing_ppe, confidence, worker_id
                    ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ''', (
                    company_id,
                    camera_id,
                    datetime.now().isoformat(),
                    'PPE_VIOLATION',
                    ', '.join(violation.get('missing_ppe', [])),
                    violation.get('confidence', 0.0),  # confidence
                    violation.get('person_id', 'unknown')
                ))
            
            conn.commit()
            self.db.close_connection(conn)
            logger.debug(f"✅ Violation kaydedildi: {camera_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Violation DB kayıt hatası (devam ediliyor): {e}")
            # Production'da DB hatası olsa bile detection devam etsin



def main():
    """Ana fonksiyon - Sadece development mode için"""
    print("🌐 SmartSafe AI - SaaS Multi-Tenant API Engine")
    print("=" * 60)
    print("✅ Multi-tenant company management")
    print("✅ Company-based data isolation")
    print("✅ Secure API session management")
    print("✅ Camera & DVR integration")
    print("✅ Real-time YOLO PPE detection")
    print("=" * 60)
    print("🚀 API Server starting...")
    
    try:
        api_server = SmartSafeSaaSAPI()
        app = api_server.app
        
        # Development mode - Flask development server
        # Port 5577 veya 10000 kullan (environment variable ile değiştirilebilir)
        port = int(os.environ.get('PORT', 5577))  # Default 5577'ye değiştirildi
        logger.info(f"🔧 Development mode: Starting Flask server on port {port}")
        logger.info(f"🌐 Erişim URL: http://0.0.0.0:{port}/")
        logger.info(f"🌐 Harici erişim: http://161.9.126.42:{port}/")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)  # threaded=True for better performance
            
    except KeyboardInterrupt:
        logger.info("🛑 SaaS API Server stopped by user")
    except Exception as e:
        logger.error(f"❌ SaaS API Server error: {e}")
        return 1
    
    return 0

# =============================================================================
# PRODUCTION APP INSTANCE - Bu obje Gunicorn tarafından kullanılır
# =============================================================================
print("🔧 Creating global Flask app for production deployment...")

# Global app variable for Gunicorn
app = None

def create_emergency_app():
    """Emergency fallback Flask app for production issues"""
    from flask import Flask, jsonify
    emergency_app = Flask(__name__)
    
    @emergency_app.route('/health')
    def health_check():
        return jsonify({"status": "healthy", "mode": "emergency_fallback", "message": "System operational in fallback mode"})
    
    @emergency_app.route('/')
    def emergency_home():
        return jsonify({
            "status": "operational",
            "message": "SmartSafe AI API - Headless Mode",
            "features": ["Health Monitoring", "API Endpoints", "PPE Detection Engine"]
        })
    
    @emergency_app.route('/api/status')
    def api_status():
        from datetime import datetime
        return jsonify({
            "status": "emergency_fallback",
            "message": "Main system temporarily unavailable",
            "timestamp": datetime.now().isoformat()
        })
    
    return emergency_app


def create_app():
    """Factory function to create Flask app"""
    global app
    try:
        api_server = SmartSafeSaaSAPI()
        
        # --- Startup: Stale active_detections temizliği ---
        # Restart sonrası hiçbir detection thread çalışmıyor,
        # önceki process'ten kalan DB kayıtları stale → hepsini sil
        try:
            _db = get_db_adapter()
            cleared = _db.execute_query("DELETE FROM active_detections")
            print(f"🧹 Startup cleanup: {cleared} stale active_detections silindi")
        except Exception as cleanup_err:
            print(f"⚠️ Startup active_detections cleanup failed (tablo henüz yok olabilir): {cleanup_err}")
        
        # --- Start Schedule Manager ---
        try:
            from services.schedule_manager import get_schedule_manager
            api_server.schedule_manager = get_schedule_manager(api_server)
            api_server.schedule_manager.start()
            print("🕒 Schedule Manager started during app creation")
        except Exception as sched_err:
            print(f"⚠️ Schedule Manager startup failed: {sched_err}")
            
        app = api_server.app
        print(f"✅ Global Flask app created successfully: {app}")
        print(f"📍 App name: {app.name}")
        print(f"📍 Environment: {app.config.get('ENV', 'production')}")
        print("🚀 Ready for WSGI server (Gunicorn)")
        print("📌 Gunicorn will use this 'app' object directly")
        return app
    except Exception as e:
        print(f"❌ Critical error creating Flask app: {e}")
        import traceback
        traceback.print_exc()
        
        app = create_emergency_app()
        print("⚠️ Emergency fallback Flask app created")
        return app


# Create the app instance (used by Gunicorn)
app = create_app()

# =============================================================================
# LOCAL DEVELOPMENT ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import os, logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    env = os.getenv("ENV", "local").lower()
    port = int(os.getenv("PORT", 5577 if env == "local" else 10000))
    host = "0.0.0.0"

    logger.info(f"🚀 Starting SmartSafe SaaS API")
    logger.info(f"🌐 Host: {host}, Port: {port}")
    logger.info(f"🔧 Environment: {env}")

    if env == "local":
        # Only run Flask built-in server locally
        logger.info("🧩 Running in LOCAL mode (Flask dev server)")
        # Docker bind mount: FLASK_RELOADER_INTERVAL düşürülürse değişiklikler daha çabuk yakalanır (stat reloader).
        try:
            _reloader_interval = float(os.getenv("FLASK_RELOADER_INTERVAL", "1"))
        except ValueError:
            _reloader_interval = 1.0
        try:
            # IMPORTANT: use_reloader=False — reloader iki process başlatır ve
            # in-memory dict'ler (active_ai_detectors, frame_buffers vb.)
            # process'ler arası PAYLAŞILMAZ. Detection thread ana process'te,
            # HTTP handler child process'te çalışır → API boş döner.
            # Reloader kapatılmazsa frontend detection durumunu GÖREMEZ.
            _use_reloader = os.getenv("FLASK_USE_RELOADER", "false").lower() in ("1", "true", "yes")
            app.run(
                host=host,
                port=port,
                debug=True,
                threaded=True,
                use_reloader=_use_reloader,
            )
        except Exception as e:
            logger.error(f"❌ Local server failed: {e}")
            app = create_emergency_app()
            app.run(host=host, port=port, debug=True)
    else:
        # Production mode (Render/Gunicorn)
        logger.info("✅ Production environment detected — Gunicorn will serve the app.")

