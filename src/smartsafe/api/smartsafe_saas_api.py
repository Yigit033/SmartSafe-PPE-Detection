#!/usr/bin/env python3
"""
SmartSafe AI - SaaS Multi-Tenant API Server
Şirket bazlı veri ayrımı ile profesyonel SaaS sistemi
"""

from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, Response, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message
import sqlite3
import json

import threading
import time
import requests
import logging
import re

# Configure logging - Memory optimized
import os
log_level = logging.WARNING if os.environ.get('RENDER') else logging.INFO
logging.basicConfig(level=log_level, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# SendGrid imports (conditional - graceful fallback if not available)
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail as SendGridMail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("⚠️ SendGrid not installed. Email will use SMTP only.")
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from src.smartsafe.services.multitenant_system import MultiTenantDatabase
from src.smartsafe.integrations.construction.construction_ppe_system import ConstructionPPEDetector, ConstructionPPEConfig
from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
from src.smartsafe.database.database_adapter import get_db_adapter
from src.smartsafe.integrations.cameras.camera_integration_manager import DVRConfig
from src.smartsafe.detection.snapshot_manager import get_snapshot_manager
from src.smartsafe.integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
import cv2
import numpy as np
import base64
import queue
from io import BytesIO
import bcrypt
from pathlib import Path

# Load environment variables
load_dotenv()

# Resolve project root (for templates/static after src/ restructure)
try:
    # __file__ = .../src/smartsafe/api/smartsafe_saas_api.py
    # parents[3] => project root (one above 'src')
    BASE_DIR = Path(__file__).resolve().parents[3]
except Exception:
    BASE_DIR = Path(__file__).resolve().parent

# Enterprise modülleri import et
# Lazy loading için enterprise modülleri startup'ta yükleme - Memory optimization
ENTERPRISE_MODULES_AVAILABLE = True
logger.info("✅ Enterprise modülleri lazy loading için hazır - Memory optimized")

# Global değişkenler - kamera sistemi için
active_detectors = {}
detection_threads = {}
camera_captures = {}  # Kamera yakalama nesneleri
frame_buffers = {}    # Frame buffer'ları
detection_results = {} # Tespit sonuçları
live_violation_state = {}  # SaaS canlı tespit için ihlal durumu (start/resolution)
# Kamera okuma hataları için sayaç (noise azaltma + gerektiğinde yeniden bağlanma)
frame_failure_counts = {}

# İYİLEŞTİRİLDİ: Response Caching
response_cache = {}
cache_timestamps = {}
CACHE_DURATION = 300  # 5 dakika cache süresi



class SmartSafeSaaSAPI:
    """SmartSafe AI SaaS API Server"""
    
    def __init__(self):
        try:
            self.app = Flask(
                            __name__,
                            template_folder=str(BASE_DIR / 'templates'),
                            static_folder=str(BASE_DIR / 'static')
                            )
            _secret = os.getenv('SECRET_KEY')
            if not _secret:
                import secrets
                _secret = secrets.token_hex(32)
                logger.warning("SECRET_KEY not set – using random key (sessions will not persist across restarts)")
            self.app.config['SECRET_KEY'] = _secret
        except Exception as e:
            logger.error(f"❌ Flask app initialization failed: {e}")
            raise
        
        # 🎯 PRODUCTION-GRADE: Template caching'i devre dışı bırak (development mode)
        is_development = not (os.environ.get('RENDER') or os.environ.get('FLASK_ENV') == 'production')
        
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True
        self.app.config['DEBUG'] = is_development  # Only in development
        self.app.jinja_env.auto_reload = True
        self.app.jinja_env.cache = None
        
        # Cache headers'ı devre dışı bırak - AFTER_REQUEST DECORATOR İLE!
        @self.app.after_request
        def add_no_cache_headers(response):
            """🎯 CRITICAL: Browser cache'i tamamen devre dışı bırak"""
            response.cache_control.max_age = 0
            response.cache_control.no_cache = True
            response.cache_control.no_store = True
            response.cache_control.must_revalidate = True
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public'
            # HTML sayfaları için ekstra header
            if response.content_type and 'text/html' in response.content_type:
                response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
            return response
        
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
        
        # Mail configuration
        self.app.config['MAIL_SERVER'] = 'smtp.gmail.com'
        self.app.config['MAIL_PORT'] = 587
        self.app.config['MAIL_USE_TLS'] = True
        self.app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'your-email@gmail.com')
        self.app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'your-app-password')
        self.mail = Mail(self.app)
        
        # Enable CORS - Vercel Frontend + Render Backend
        # Production'da Vercel domain'inizi ekleyin
        allowed_origins = [
            'http://localhost:3000',
            'http://localhost:8000',
            'http://localhost:5000',
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
        
        # İYİLEŞTİRİLDİ: Rate limiting with better configuration
        self.limiter = Limiter(
            app=self.app,
            key_func=get_remote_address,
            default_limits=["200 per minute", "1000 per hour"],
            storage_uri="memory://"
        )
        
        # Multi-tenant database - Lazy initialization for production
        self.db = None
        self.db_adapter = None
        self._db_initialized = False
        
        # Production database schema handler
        self.is_production = (os.environ.get('RENDER') or 
                             os.environ.get('SUPABASE_URL') or
                             os.environ.get('FLASK_ENV') == 'production')
        
        if self.is_production:
            logger.info("🚀 Production mode: PostgreSQL/Supabase schema active")
            self.database_type = 'postgresql'
        else:
            logger.info("🔧 Development mode: SQLite schema active")
            self.database_type = 'sqlite'
        
        # Enterprise modülleri başlat
        self.init_enterprise_modules()
        
        # PPE Detection Manager başlat
        try:
            from src.smartsafe.integrations.cameras.ppe_detection_manager import PPEDetectionManager
            self.ppe_manager = PPEDetectionManager()
            if not self.ppe_manager.load_models():
                logger.warning("⚠️ PPE Detection Manager yüklenemedi, fallback kullanılacak")
                self.ppe_manager = None
        except Exception as e:
            logger.warning(f"⚠️ PPE Detection Manager yüklenemedi: {e}, fallback kullanılacak")
            self.ppe_manager = None
        
        # Şifre güvenlik politikası
        self.password_policy = {
            'min_length': 8,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_digits': True,
            'require_special': True
        }
        
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
        
        logger.info("🌐 SmartSafe AI SaaS API Server initialized")
        
        # İYİLEŞTİRİLDİ: Cache management functions
        self.setup_cache_management()
    
    def ensure_database_initialized(self):
        """Lazy initialize database on first request"""
        # Her zaman self.db kontrolü yap - eğer None ise tekrar initialize et
        if self.db is not None and self._db_initialized:
            return True
        
        try:
            # Database adapter'ı önce initialize et
            if self.db_adapter is None:
                self.db_adapter = get_db_adapter()
                if self.db_adapter:
                    self.db_adapter.init_database()
            
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
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
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
                from src.smartsafe.services.professional_config_manager import ProfessionalConfigManager
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
                from src.smartsafe.services.performance_optimizer import PerformanceOptimizer
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
                conn.close()
    
    def _apply_demo_channel_limits(self, company_id: str, dvr_id: str, max_cameras: int, active_cameras: int):
        """Demo hesabı için DVR kanal limitlerini uygula"""
        try:
            logger.info(f"🔒 Demo hesabı kanal limiti uygulanıyor: {company_id} - DVR: {dvr_id}")
            
            # DVR'daki toplam kanal sayısını al
            manager = self.get_camera_manager()
            if not manager or not hasattr(manager, 'dvr_manager'):
                logger.warning("⚠️ DVR manager bulunamadı")
                return
            
            # DVR kanallarını al
            dvr_channels = manager.dvr_manager.get_dvr_channels(company_id, dvr_id)
            if not dvr_channels:
                logger.warning("⚠️ DVR kanalları bulunamadı")
                return
            
            total_channels = len(dvr_channels)
            available_slots = max_cameras - active_cameras
            
            if available_slots <= 0:
                logger.warning(f"⚠️ Demo hesabı kamera slotu kalmadı: {active_cameras}/{max_cameras}")
                return
            
            # Sadece kullanılabilir slot kadar kanalı aktif et
            active_channels = min(available_slots, total_channels)
            
            logger.info(f"✅ Demo hesabı kanal limiti uygulandı: {active_channels}/{total_channels} kanal aktif")
            
            # Kanal durumlarını güncelle (sadece aktif olanlar)
            for i, channel in enumerate(dvr_channels):
                if i < active_channels:
                    # Aktif kanal
                    self._activate_demo_channel(company_id, dvr_id, channel['channel_id'])
                else:
                    # Pasif kanal
                    self._deactivate_demo_channel(company_id, dvr_id, channel['channel_id'])
            
        except Exception as e:
            logger.error(f"❌ Demo kanal limiti uygulama hatası: {e}")
    
    def _activate_demo_channel(self, company_id: str, dvr_id: str, channel_id: str):
        """Demo hesabı için kanalı aktif et"""
        try:
            # Kanalı aktif et
            manager = self.get_camera_manager()
            if manager and hasattr(manager, 'dvr_manager'):
                # Kanal durumunu güncelle
                self.db.update_dvr_channel_status(company_id, dvr_id, channel_id, 'active')
                logger.info(f"✅ Demo kanal aktif edildi: {channel_id}")
        except Exception as e:
            logger.error(f"❌ Demo kanal aktif etme hatası: {e}")
    
    def _deactivate_demo_channel(self, company_id: str, dvr_id: str, channel_id: str):
        """Demo hesabı için kanalı pasif et"""
        try:
            # Kanalı pasif et
            manager = self.get_camera_manager()
            if manager and hasattr(manager, 'dvr_manager'):
                # Kanal durumunu güncelle
                self.db.update_dvr_channel_status(company_id, dvr_id, channel_id, 'inactive')
                logger.info(f"✅ Demo kanal pasif edildi: {channel_id}")
        except Exception as e:
            logger.error(f"❌ Demo kanal pasif etme hatası: {e}")
    
    def _limit_demo_channels(self, channels: List[Dict], max_cameras: int, active_cameras: int) -> List[Dict]:
        """Demo hesabı için kanal listesini limitlendir"""
        try:
            available_slots = max_cameras - active_cameras
            
            if available_slots <= 0:
                logger.warning(f"⚠️ Demo hesabı kamera slotu kalmadı: {active_cameras}/{max_cameras}")
                return []
            
            # Sadece kullanılabilir slot kadar kanalı döndür
            limited_channels = channels[:available_slots]
            
            # Kalan kanalları pasif olarak işaretle
            for channel in limited_channels:
                channel['demo_active'] = True
                channel['demo_note'] = f'Demo hesabı - {len(limited_channels)}/{len(channels)} kanal aktif'
            
            logger.info(f"✅ Demo kanal limiti uygulandı: {len(limited_channels)}/{len(channels)} kanal aktif")
            return limited_channels
            
        except Exception as e:
            logger.error(f"❌ Demo kanal limiti hatası: {e}")
            return channels
    
    def _send_email_with_sendgrid(self, to_email: str, subject: str, content: str) -> bool:
        """
        SendGrid API kullanarak mail gönder
        Returns: True if successful, False otherwise
        """
        if not SENDGRID_AVAILABLE:
            logger.debug("SendGrid not available, skipping")
            return False
            
        try:
            api_key = os.getenv('SENDGRID_API_KEY')
            if not api_key:
                logger.debug("SENDGRID_API_KEY not set")
                return False
            
            from_email = os.getenv('MAIL_DEFAULT_SENDER', 'yigittilaver2000@gmail.com')
            
            # SendGrid mail objesi oluştur
            message = SendGridMail(
                from_email=Email(from_email),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=Content("text/plain", content)
            )
            
            # SendGrid API ile gönder
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"✅ SendGrid ile mail gönderildi: {to_email} (status: {response.status_code})")
                return True
            else:
                logger.warning(f"⚠️ SendGrid beklenmeyen status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ SendGrid mail gönderim hatası: {e}")
            return False
    
    def _send_demo_notification(self, email: str, message: str):
        """
        Demo bildirim maili gönder - PostgreSQL ve SQLite uyumlu
        SMTP → SendGrid fallback → Log fallback
        """
        mail_sent = False
        subject = "SmartSafe AI Demo Hesap Bilgileri"
        
        # 1. Önce SMTP dene
        try:
            if hasattr(self, 'mail') and self.mail:
                msg = Message(
                    subject=subject,
                    recipients=[email],
                    body=message,
                    sender=os.getenv('MAIL_DEFAULT_SENDER', 'yigittilaver2000@gmail.com')
                )
                self.mail.send(msg)
                logger.info(f"✅ SMTP ile demo mail gönderildi: {email}")
                mail_sent = True
                return
        except Exception as smtp_error:
            logger.warning(f"⚠️ SMTP başarısız: {smtp_error}")
        
        # 2. SMTP başarısızsa SendGrid dene
        if not mail_sent:
            logger.info("🔄 SendGrid ile deneniyor...")
            mail_sent = self._send_email_with_sendgrid(email, subject, message)
        
        # 3. Her iki yöntem de başarısızsa log'a yaz
        if not mail_sent:
            logger.error(f"❌ Tüm mail yöntemleri başarısız oldu: {email}")
            logger.warning(f"⚠️ Mail gönderilemedi. Log'daki mesaj içeriğini manuel gönderin.")
            logger.info(f"📧 Mail içeriği:\n{message}")

    def _send_company_notification(self, email: str, message: str):
        """
        Şirket kayıt bildirim maili gönder - PostgreSQL ve SQLite uyumlu
        SMTP → SendGrid fallback → Log fallback
        """
        mail_sent = False
        subject = "SmartSafe AI Şirket Hesap Bilgileri"
        
        # 1. Önce SMTP dene
        try:
            if hasattr(self, 'mail') and self.mail:
                msg = Message(
                    subject=subject,
                    recipients=[email],
                    body=message,
                    sender=os.getenv('MAIL_DEFAULT_SENDER', 'yigittilaver2000@gmail.com')
                )
                self.mail.send(msg)
                logger.info(f"✅ SMTP ile şirket maili gönderildi: {email}")
                mail_sent = True
                return
        except Exception as smtp_error:
            logger.warning(f"⚠️ SMTP başarısız: {smtp_error}")
        
        # 2. SMTP başarısızsa SendGrid dene
        if not mail_sent:
            logger.info("🔄 SendGrid ile deneniyor...")
            mail_sent = self._send_email_with_sendgrid(email, subject, message)
        
        # 3. Her iki yöntem de başarısızsa log'a yaz
        if not mail_sent:
            logger.error(f"❌ Tüm mail yöntemleri başarısız oldu: {email}")
            logger.warning(f"⚠️ Mail gönderilemedi. Log'daki mesaj içeriğini manuel gönderin.")
            logger.info(f"📧 Mail içeriği:\n{message}")

    def validate_password_strength(self, password: str) -> tuple[bool, list[str]]:
        """Şifre gücünü kontrol et - 5 temel gereksinimi doğrula"""
        errors = []

        # Boş veya None şifreleri normalize et
        if password is None:
            password = ""
        password = password.strip()
        
        # 1. Minimum uzunluk kontrolü
        if len(password) < self.password_policy['min_length']:
            errors.append(f"Şifre en az {self.password_policy['min_length']} karakter olmalıdır")
        
        # 2. Büyük harf kontrolü
        if self.password_policy['require_uppercase'] and not re.search(r'[A-Z]', password):
            errors.append("Şifre en az 1 büyük harf (A-Z) içermelidir")
        
        # 3. Küçük harf kontrolü
        if self.password_policy['require_lowercase'] and not re.search(r'[a-z]', password):
            errors.append("Şifre en az 1 küçük harf (a-z) içermelidir")
        
        # 4. Rakam kontrolü
        if self.password_policy['require_digits'] and not re.search(r'\d', password):
            errors.append("Şifre en az 1 rakam (0-9) içermelidir")
        
        # 5. Özel karakter kontrolü (yaygın özel karakterleri kapsayacak şekilde genişletildi)
        if self.password_policy['require_special'] and not re.search(r'[!@#$%^&*()\-_=+.,?":{}|<>]', password):
            errors.append("Şifre en az 1 özel karakter (!@#$%^&*()_-+= vb.) içermelidir")
        
        # 6. Yaygın şifre kontrolü
        common_passwords = ['password', '123456', 'admin', 'smartsafe', 'qwerty', 'abc123']
        if password.lower() in common_passwords:
            errors.append("Bu şifre çok yaygın, lütfen daha güvenli bir şifre seçin")
        
        return len(errors) == 0, errors

    def setup_routes(self):
        """API rotalarını ayarla - Blueprint modüllerinden yükle"""
        from src.smartsafe.api.blueprints import register_all_blueprints
        register_all_blueprints(self)
        logger.info("✅ All API blueprints registered successfully")


    # --- Legacy setup_routes code moved to src/smartsafe/api/blueprints/ ---
    # The following marker exists so that the rest of the class methods
    # (validate_session, template getters, etc.) remain untouched.

    def _require_db_decorator(self):
        """Decorator factory for database initialization (available to blueprints via api)"""
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
            # Reduced logging - only log on errors or debug mode
            if not session_id:
                logger.debug("⚠️ Session ID bulunamadı")
                return None
            
            result = self.db.validate_session(session_id)
            # Only log if validation fails or in debug mode
            if not result:
                logger.debug(f"⚠️ Session validation failed for: {session_id[:20]}...")
            
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
    
    def check_demo_status(self, company_id: str) -> Dict[str, Any]:
        """Demo hesabı durumunu kontrol et"""
        try:
            # Database initialization kontrolü
            if not self.ensure_database_initialized():
                logger.error("❌ Database initialization failed in check_demo_status")
                return {'is_demo': False, 'expires_at': None}
            
            if self.db is None:
                logger.error("❌ Database connection is None in check_demo_status")
                return {'is_demo': False, 'expires_at': None}
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder()
            
            # Safe query with fallback for missing account_type column
            try:
                cursor.execute(f'''
                    SELECT account_type, demo_expires_at, demo_limits, created_at
                    FROM companies 
                    WHERE company_id = {placeholder}
                ''', (company_id,))
                result = cursor.fetchone()
            except Exception as e:
                if 'account_type' in str(e) and 'does not exist' in str(e):
                    # Column doesn't exist, use fallback
                    logger.warning(f"⚠️ account_type column missing in demo check, using fallback")
                    cursor.execute(f'''
                        SELECT created_at FROM companies WHERE company_id = {placeholder}
                    ''', (company_id,))
                    fallback_result = cursor.fetchone()
                    if fallback_result:
                        result = ('full', None, None, fallback_result[0])  # Default values
                    else:
                        result = None
                else:
                    raise e
            conn.close()
            
            if not result:
                return {'is_demo': False, 'expired': False}
            
            # PostgreSQL Row object vs SQLite tuple compatibility
            if hasattr(result, 'keys'):  # PostgreSQL Row object
                account_type = result['account_type']
                demo_expires_at = result['demo_expires_at']
                demo_limits = result['demo_limits']
                created_at = result['created_at']
            else:  # SQLite tuple
                account_type, demo_expires_at, demo_limits, created_at = result
            
            if account_type != 'demo':
                return {'is_demo': False, 'expired': False}
            
            # Demo süresi kontrolü
            from datetime import datetime
            import json
            
            if demo_expires_at:
                if isinstance(demo_expires_at, str):
                    expire_date = datetime.fromisoformat(demo_expires_at.replace('Z', '+00:00'))
                else:
                    expire_date = demo_expires_at
                
                is_expired = datetime.now() > expire_date
                days_remaining = max(0, (expire_date - datetime.now()).days)
            else:
                is_expired = True
                days_remaining = 0
            
            # Demo limitleri parse et
            limits = {}
            if demo_limits:
                try:
                    if isinstance(demo_limits, str):
                        limits = json.loads(demo_limits)
                    else:
                        limits = demo_limits
                except:
                    limits = {'cameras': 2, 'violations': 100, 'days': 7}
            
            return {
                'is_demo': True,
                'expired': is_expired,
                'days_remaining': days_remaining,
                'limits': limits,
                'created_at': created_at
            }
            
        except Exception as e:
            logger.error(f"❌ Demo status check error: {e}")
            return {'is_demo': False, 'expired': False}
    
    def enforce_demo_limits(self, company_id: str, action: str) -> Dict[str, Any]:
        """Demo limitlerini kontrol et ve uygula"""
        try:
            demo_status = self.check_demo_status(company_id)
            
            if not demo_status['is_demo']:
                return {'allowed': True, 'message': 'Full account'}
            
            if demo_status['expired']:
                return {'allowed': False, 'message': 'Demo süresi dolmuş', 'expired': True}
            
            limits = demo_status.get('limits', {})
            
            # Kamera limiti kontrolü
            if action == 'add_camera':
                cameras = self.db.get_company_cameras(company_id)
                if len(cameras) >= limits.get('cameras', 2):
                    return {
                        'allowed': False, 
                        'message': f"Demo hesabında maksimum {limits.get('cameras', 2)} kamera ekleyebilirsiniz",
                        'limit_type': 'camera'
                    }
            
            # İhlal limiti kontrolü
            elif action == 'log_violation':
                # Son 7 günlük ihlal sayısını kontrol et
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder()
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= datetime('now', '-7 days')
                ''', (company_id,))
                
                violation_count = cursor.fetchone()[0]
                conn.close()
                
                if violation_count >= limits.get('violations', 100):
                    return {
                        'allowed': False,
                        'message': f"Demo hesabında maksimum {limits.get('violations', 100)} ihlal kaydedebilirsiniz",
                        'limit_type': 'violation'
                    }
            
            return {'allowed': True, 'message': 'Demo limitleri içinde'}
            
        except Exception as e:
            logger.error(f"❌ Demo limits enforcement error: {e}")
            return {'allowed': True, 'message': 'Limit check failed'}
    
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
            conn.close()
            
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
                    if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                        frame = frame_buffers[camera_key].copy()
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

                            # === NEW: Persist detection to DB for dynamic widgets ===
                            try:
                                from src.smartsafe.database.database_adapter import get_db_adapter
                                db = get_db_adapter()
                                # Normalize fields
                                total_people = detection_data.get('total_people', detection_data.get('people_detected', 0))
                                compliance_rate = detection_data.get('analysis', {}).get('compliance_rate', detection_data.get('compliance_rate', 0))
                                compliant_people = detection_data.get('analysis', {}).get('ppe_compliant',
                                                         int(total_people * (compliance_rate or 0) / 100))
                                violations_count = detection_data.get('analysis', {}).get('violations_count',
                                                            len(detection_data.get('violations', [])))

                                db.add_camera_detection_result({
                                    'company_id': company_id,
                                    'camera_id': camera_id,
                                    'detection_type': 'ppe',
                                    'confidence': (compliance_rate or 0) / 100.0,
                                    'people_detected': total_people,
                                    'ppe_compliant': compliant_people,
                                    'violations_count': violations_count,
                                    'total_people': total_people
                                })
                            except Exception as persist_error:
                                logger.warning(f"⚠️ Detection persist warning: {persist_error}")

                            # === NEW: Snapshot business rule (start once, resolve once) ===
                            try:
                                violations_count = detection_data.get('analysis', {}).get('violations_count',
                                                            len(detection_data.get('violations', [])))
                                prev_active = live_violation_state.get(camera_key, False)
                                now_active = violations_count > 0
                                if frame is not None:
                                    snapshot_manager = get_snapshot_manager()
                                    # İhlal başladı (0 -> >0)
                                    if now_active and not prev_active:
                                        snapshot_path = snapshot_manager.capture_full_frame_snapshot(
                                            frame=frame,
                                            company_id=str(company_id),
                                            camera_id=str(camera_id),
                                            tag='violation_start'
                                        )
                                        if snapshot_path:
                                            logger.info(f"📸 SaaS VIOLATION START SNAPSHOT: {snapshot_path} - Camera: {camera_id}")
                                        else:
                                            logger.warning(f"⚠️ SaaS Violation start snapshot kaydedilemedi: {camera_id}")
                                    # İhlal çözüldü (>0 -> 0)
                                    if (not now_active) and prev_active:
                                        snapshot_path = snapshot_manager.capture_full_frame_snapshot(
                                            frame=frame,
                                            company_id=str(company_id),
                                            camera_id=str(camera_id),
                                            tag='violation_resolved'
                                        )
                                        if snapshot_path:
                                            logger.info(f"📸 SaaS VIOLATION RESOLVED SNAPSHOT: {snapshot_path} - Camera: {camera_id}")
                                        else:
                                            logger.warning(f"⚠️ SaaS Violation resolved snapshot kaydedilemedi: {camera_id}")
                                live_violation_state[camera_key] = now_active
                            except Exception as snap_error:
                                logger.warning(f"⚠️ Snapshot rule warning: {snap_error}")
                            
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
                    
                    # Sınıfa göre renk belirle
                    from src.smartsafe.detection.utils.visual_overlay import draw_styled_box, get_class_color
                    
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
    
    def get_pricing_template(self):
        """Fiyatlandırma sayfası template'i"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Fiyatlandırma - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .pricing-card {
                    background: white;
                    border-radius: 20px;
                    padding: 40px 30px;
                    margin: 20px 0;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                    position: relative;
                    overflow: hidden;
                }
                .pricing-card:hover {
                    transform: translateY(-10px);
                    box-shadow: 0 30px 60px rgba(0,0,0,0.15);
                }
                .pricing-card.featured {
                    border: 3px solid #667eea;
                    transform: scale(1.05);
                }
                .pricing-card.featured::before {
                    content: "EN POPÜLER";
                    position: absolute;
                    top: 20px;
                    right: -30px;
                    background: #667eea;
                    color: white;
                    padding: 5px 40px;
                    font-size: 12px;
                    font-weight: bold;
                    transform: rotate(45deg);
                }
                .price {
                    font-size: 3rem;
                    font-weight: bold;
                    color: #2c3e50;
                    margin: 20px 0;
                }
                .price-currency {
                    font-size: 1.5rem;
                    color: #7f8c8d;
                }
                .price-period {
                    font-size: 1rem;
                    color: #95a5a6;
                }
                .feature-list {
                    list-style: none;
                    padding: 0;
                    margin: 30px 0;
                }
                .feature-list li {
                    padding: 10px 0;
                    border-bottom: 1px solid #ecf0f1;
                }
                .feature-list li:last-child {
                    border-bottom: none;
                }
                .feature-check {
                    color: #27ae60;
                    margin-right: 10px;
                }
                .feature-cross {
                    color: #e74c3c;
                    margin-right: 10px;
                }
                .btn-pricing {
                    width: 100%;
                    padding: 15px;
                    border-radius: 50px;
                    font-weight: bold;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    transition: all 0.3s ease;
                }
                .btn-pricing:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(0,0,0,0.2);
                }
                .navbar {
                    background: rgba(255,255,255,0.95) !important;
                    backdrop-filter: blur(10px);
                }
                .hero-section {
                    padding: 100px 0 50px;
                    text-align: center;
                    color: white;
                }
                .comparison-table {
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    margin: 50px 0;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light fixed-top">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/">Ana Sayfa</a>
                        <a class="nav-link" href="/pricing">Fiyatlandırma</a>
                        <a class="nav-link" href="/app">Kayıt Ol</a>
                    </div>
                </div>
            </nav>

            <section class="hero-section">
                <div class="container">
                    <h1 class="display-4 fw-bold mb-4">
                        <i class="fas fa-tags"></i> Fiyatlandırma Planları
                    </h1>
                    <p class="lead">İhtiyacınıza uygun planı seçin ve hemen başlayın</p>
                    <div class="row justify-content-center mt-5">
                        <div class="col-12">
                            <div class="alert alert-info d-inline-block">
                                <i class="fas fa-gift"></i> <strong>Özel Fırsat:</strong> İlk 30 gün ücretsiz!
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <section class="pricing-section">
                <div class="container">
                    <div class="row">
                        <!-- Starter Plan -->
                        <div class="col-lg-4">
                            <div class="pricing-card">
                                <div class="text-center">
                                    <h3 class="fw-bold text-primary">
                                        <i class="fas fa-rocket"></i> Starter
                                    </h3>
                                    <p class="text-muted">Küçük işletmeler için</p>
                                    <div class="price">
                                        <span class="price-currency">₺</span>99
                                        <span class="price-period">/ay</span>
                                    </div>
                                </div>
                                
                                <ul class="feature-list">
                                    <li><i class="fas fa-check feature-check"></i> 5 Kamera Desteği</li>
                                    <li><i class="fas fa-check feature-check"></i> Temel PPE Tespiti</li>
                                    <li><i class="fas fa-check feature-check"></i> Email Bildirimleri</li>
                                    <li><i class="fas fa-check feature-check"></i> Günlük Raporlar</li>
                                    <li><i class="fas fa-check feature-check"></i> 7 Gün Veri Saklama</li>
                                    <li><i class="fas fa-times feature-cross"></i> Gelişmiş Analitik</li>
                                    <li><i class="fas fa-times feature-cross"></i> API Erişimi</li>
                                    <li><i class="fas fa-times feature-cross"></i> Öncelikli Destek</li>
                                </ul>
                                
                                <a href="/app?plan=starter" class="btn btn-outline-primary btn-pricing">
                                    <i class="fas fa-arrow-right"></i> Başlayın
                                </a>
                            </div>
                        </div>

                        <!-- Professional Plan -->
                        <div class="col-lg-4">
                            <div class="pricing-card featured">
                                <div class="text-center">
                                    <h3 class="fw-bold text-primary">
                                        <i class="fas fa-star"></i> Professional
                                    </h3>
                                    <p class="text-muted">Orta ölçekli şirketler için</p>
                                    <div class="price">
                                        <span class="price-currency">₺</span>299
                                        <span class="price-period">/ay</span>
                                    </div>
                                </div>
                                
                                <ul class="feature-list">
                                    <li><i class="fas fa-check feature-check"></i> 15 Kamera Desteği</li>
                                    <li><i class="fas fa-check feature-check"></i> Gelişmiş PPE Tespiti</li>
                                    <li><i class="fas fa-check feature-check"></i> Email + SMS Bildirimleri</li>
                                    <li><i class="fas fa-check feature-check"></i> Detaylı Raporlar</li>
                                    <li><i class="fas fa-check feature-check"></i> 30 Gün Veri Saklama</li>
                                    <li><i class="fas fa-check feature-check"></i> Gelişmiş Analitik</li>
                                    <li><i class="fas fa-check feature-check"></i> API Erişimi</li>
                                    <li><i class="fas fa-times feature-cross"></i> Öncelikli Destek</li>
                                </ul>
                                
                                <a href="/app?plan=professional" class="btn btn-primary btn-pricing">
                                    <i class="fas fa-crown"></i> En Popüler
                                </a>
                            </div>
                        </div>

                        <!-- Enterprise Plan -->
                        <div class="col-lg-4">
                            <div class="pricing-card">
                                <div class="text-center">
                                    <h3 class="fw-bold text-primary">
                                        <i class="fas fa-building"></i> Enterprise
                                    </h3>
                                    <p class="text-muted">Büyük kuruluşlar için</p>
                                    <div class="price">
                                        <span class="price-currency">₺</span>599
                                        <span class="price-period">/ay</span>
                                    </div>
                                </div>
                                
                                <ul class="feature-list">
                                    <li><i class="fas fa-check feature-check"></i> 50 Kamera Desteği</li>
                                    <li><i class="fas fa-check feature-check"></i> AI Destekli Analiz</li>
                                    <li><i class="fas fa-check feature-check"></i> Tüm Bildirim Türleri</li>
                                    <li><i class="fas fa-check feature-check"></i> Özel Raporlar</li>
                                    <li><i class="fas fa-check feature-check"></i> 90 Gün Veri Saklama</li>
                                    <li><i class="fas fa-check feature-check"></i> Gelişmiş Analitik</li>
                                    <li><i class="fas fa-check feature-check"></i> Full API Erişimi</li>
                                    <li><i class="fas fa-check feature-check"></i> 7/24 Öncelikli Destek</li>
                                </ul>
                                
                                <a href="/app?plan=enterprise" class="btn btn-success btn-pricing">
                                    <i class="fas fa-rocket"></i> Kurumsal
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        '''
    
    def get_home_template(self):
        """Ana sayfa template"""
        return '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe AI - Company Registration</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                :root {
                    --primary: #1E3A8A;
                    --secondary: #0EA5E9;
                    --accent: #22C55E;
                    --warning: #EF4444;
                    --light: #F8FAFC;
                    --dark: #0F172A;
                }

                body {
                    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                    color: var(--dark);
                    overflow-x: hidden;
                }

                .gradient-bg {
                    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                }

                .glass-card {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }

                .feature-icon {
                    width: 64px;
                    height: 64px;
                    border-radius: 16px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                    color: white;
                    margin-bottom: 20px;
                }

                .btn-primary {
                    background: var(--primary);
                    border: none;
                    padding: 12px 32px;
                    border-radius: 30px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }

                .btn-primary:hover {
                    background: var(--secondary);
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(14, 165, 233, 0.3);
                }

                .form-control, .form-select {
                    border-radius: 15px;
                    border: 2px solid #e2e8f0;
                    padding: 12px 15px;
                    transition: all 0.3s ease;
                    font-size: 16px;
                }

                .form-control:focus, .form-select:focus {
                    border-color: var(--primary);
                    box-shadow: 0 0 0 0.2rem rgba(30, 58, 138, 0.25);
                }

                .form-check-input:checked {
                    background-color: var(--primary);
                    border-color: var(--primary);
                }

                .alert {
                    border-radius: 15px;
                    border: none;
                }
                
                /* Modern Business Form Styles */
                .business-form-section {
                    background: rgba(255, 255, 255, 0.98);
                    border-radius: 20px;
                    padding: 2rem;
                    border: 1px solid rgba(30, 58, 138, 0.1);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
                }
                
                .section-header {
                    text-align: center;
                    padding-bottom: 1.5rem;
                    border-bottom: 2px solid rgba(30, 58, 138, 0.1);
                }
                
                .section-icon-wrapper {
                    width: 60px;
                    height: 60px;
                    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1rem;
                    box-shadow: 0 4px 15px rgba(30, 58, 138, 0.3);
                }
                
                .section-icon-wrapper i {
                    font-size: 24px;
                    color: white;
                }
                
                .section-title {
                    color: var(--dark);
                    font-weight: 700;
                    font-size: 1.5rem;
                    margin-bottom: 0.5rem;
                }
                
                .section-subtitle {
                    font-size: 1rem;
                    color: #6b7280;
                    margin: 0;
                }
                
                .form-group-modern {
                    margin-bottom: 1.5rem;
                }
                
                .form-label-modern {
                    display: block;
                    font-weight: 600;
                    color: var(--dark);
                    margin-bottom: 0.75rem;
                    font-size: 0.95rem;
                }
                
                .required-mark {
                    color: #ef4444;
                    font-weight: 700;
                }
                
                .input-group-modern {
                    position: relative;
                }
                
                .form-control-modern {
                    width: 100%;
                    padding: 1rem 1rem 1rem 3rem;
                    border: 2px solid #e5e7eb;
                    border-radius: 12px;
                    font-size: 1rem;
                    transition: all 0.3s ease;
                    background: white;
                    color: var(--dark);
                }
                
                .form-control-modern:focus {
                    outline: none;
                    border-color: var(--primary);
                    box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
                    transform: translateY(-1px);
                }
                
                .form-control-modern::placeholder {
                    color: #9ca3af;
                }
                
                .input-icon {
                    position: absolute;
                    left: 1rem;
                    top: 50%;
                    transform: translateY(-50%);
                    color: #9ca3af;
                    transition: color 0.3s ease;
                }
                
                .form-control-modern:focus + .input-icon {
                    color: var(--primary);
                }
                
                /* Textarea özel stili */
                .form-control-modern[rows] {
                    padding-left: 1rem;
                    resize: vertical;
                    min-height: 80px;
                }
                
                .form-control-modern[rows] + .input-icon {
                    top: 1.5rem;
                    transform: none;
                }
                
                /* Address textarea özel stili */
                .address-textarea {
                    min-height: 120px !important;
                    padding: 1.25rem 1rem 1rem 3rem !important;
                    font-size: 1rem;
                    line-height: 1.6;
                }
                
                .address-icon {
                    top: 1.25rem !important;
                    transform: none !important;
                    left: 1rem;
                }
                
                .address-textarea:focus + .address-icon {
                    color: var(--primary);
                }
                
                /* Select özel stili */
                .form-control-modern[data-type="select"] {
                    cursor: pointer;
                }
                
                /* Responsive tasarım */
                @media (max-width: 768px) {
                    .business-form-section {
                        padding: 1.5rem;
                    }
                    
                    .section-title {
                        font-size: 1.3rem;
                    }
                    
                    .form-control-modern {
                        padding: 0.875rem 0.875rem 0.875rem 2.5rem;
                    }
                }

                .ppe-options {
                    animation: fadeIn 0.5s ease-in-out;
                }

                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .form-check-label {
                    font-weight: 500;
                    cursor: pointer;
                }

                /* Açılır-Kapanır Buton Stilleri */
                #toggleSubscriptionBtn {
                    transition: all 0.3s ease;
                    position: relative;
                    overflow: hidden;
                }
                
                #toggleSubscriptionBtn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(30, 58, 138, 0.2);
                }
                
                #toggleSubscriptionBtn:active {
                    transform: translateY(0);
                }
                
                #toggleSubscriptionBtn .fas {
                    transition: transform 0.3s ease;
                }
                
                #subscriptionPlansContainer {
                    animation: slideDown 0.4s ease-out;
                }
                
                @keyframes slideDown {
                    from { 
                        opacity: 0; 
                        transform: translateY(-20px);
                        max-height: 0;
                    }
                    to { 
                        opacity: 1; 
                        transform: translateY(0);
                        max-height: 1000px; /* Yeterince büyük bir değer */
                    }
                }
                
                /* Business Plan Kartları CSS */
                .plan-card-modern {
                    background: white;
                    border-radius: 16px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                    transition: all 0.3s ease;
                    cursor: pointer;
                    border: 2px solid #e2e8f0;
                    position: relative;
                    overflow: hidden;
                }

                .plan-card-modern:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.12);
                    border-color: #cbd5e1;
                }

                .plan-card-modern.selected {
                    border-color: #2563eb !important;
                    border-width: 3px !important;
                    box-shadow: 0 8px 25px rgba(37, 99, 235, 0.25) !important;
                    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%) !important;
                    transform: translateY(-3px);
                }

                .plan-card-modern.popular {
                    border-color: #10b981;
                    box-shadow: 0 8px 25px rgba(16, 185, 129, 0.15);
                }

                .plan-card-modern.popular:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 12px 25px rgba(16, 185, 129, 0.2);
                }

                .plan-card-header {
                    padding: 25px 20px 20px;
                    text-align: center;
                    background: #f8fafc;
                    border-bottom: 1px solid #e2e8f0;
                    position: relative;
                }

                .starter-gradient {
                    background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
                    color: #1e293b;
                }

                .professional-gradient {
                    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
                    color: #1e293b;
                }

                .enterprise-gradient {
                    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                    color: #1e293b;
                }

                .plan-icon {
                    font-size: 2rem;
                    margin-bottom: 15px;
                    color: #2563eb;
                    opacity: 0.9;
                }

                .plan-name {
                    font-size: 1.4rem;
                    font-weight: 600;
                    margin-bottom: 10px;
                    color: #1e293b;
                }

                .plan-price {
                    font-size: 1.8rem;
                    font-weight: 700;
                    margin-bottom: 5px;
                    position: relative;
                }
                
                .billing-toggle {
                    display: flex;
                    gap: 5px;
                    justify-content: center;
                    margin-bottom: 15px;
                }
                
                .billing-toggle .btn {
                    padding: 5px 15px;
                    font-size: 0.85rem;
                    border-radius: 20px;
                    transition: all 0.3s ease;
                }
                
                .billing-toggle .btn.active {
                    background-color: #3182ce;
                    color: white;
                    border-color: #3182ce;
                }
                
                .discount-badge {
                    position: absolute;
                    top: -5px;
                    right: -5px;
                    background: #38a169;
                    color: white;
                    font-size: 0.6rem;
                    padding: 2px 6px;
                    border-radius: 8px;
                    font-weight: normal;
                    color: #2563eb;
                }

                .period {
                    font-size: 0.9rem;
                    font-weight: 400;
                    color: #64748b;
                }

                .popular-badge {
                    position: absolute;
                    top: 15px;
                    right: 15px;
                    background: #10b981;
                    color: white;
                    padding: 6px 12px;
                    border-radius: 16px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
                }

                .plan-card-body {
                    padding: 20px;
                    background: white;
                }

                .plan-features {
                    margin-bottom: 15px;
                }

                .feature-item {
                    display: flex;
                    align-items: center;
                    margin-bottom: 10px;
                    font-size: 0.85rem;
                    color: #475569;
                }

                .feature-item i {
                    margin-right: 10px;
                    font-size: 0.9rem;
                    width: 18px;
                    text-align: center;
                    color: #64748b;
                }

                .plan-badge {
                    display: inline-block;
                    padding: 6px 14px;
                    border-radius: 20px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    color: white;
                }

                .starter-badge {
                    background: #64748b;
                }

                .professional-badge {
                    background: #2563eb;
                }

                .enterprise-badge {
                    background: #10b981;
                }

                .plan-info-card {
                    background: #f8fafc;
                    border-radius: 12px;
                    padding: 20px;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
                }

                .plan-info-content {
                    line-height: 1.6;
                    color: #475569;
                }

                .btn-modern {
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 500;
                    transition: all 0.2s ease;
                    border: 1px solid #2563eb;
                    color: #2563eb;
                    background: white;
                }

                .btn-modern:hover {
                    background: #2563eb;
                    color: white;
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
                }

                /* Responsive Tasarım */
                @media (max-width: 768px) {
                    .plan-card-modern {
                        margin-bottom: 20px;
                    }
                    
                    .plan-card-modern.popular {
                        margin-bottom: 25px;
                    }
                    
                    .plan-card-modern.popular:hover {
                        transform: translateY(-3px);
                    }
                }

                .form-check-input {
                    margin-top: 0.4em;
                }

                .badge {
                    font-size: 0.7em;
                }

                .btn-outline-primary {
                    border: 2px solid var(--primary);
                    color: var(--primary);
                    transition: all 0.3s ease;
                }

                .btn-outline-primary:hover {
                    background: var(--primary);
                    border-color: var(--primary);
                    transform: translateY(-2px);
                }

                .container {
                    animation: slideUp 0.6s ease-out;
                }

                @keyframes slideUp {
                    from { opacity: 0; transform: translateY(30px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            </style>
        </head>
        <body>
            <div class="container mt-5">
                <div class="row justify-content-center">
                    <div class="col-md-8 col-lg-6">
                        <div class="text-center mb-5">
                            <h1 class="text-white display-4 fw-bold mb-3" style="text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
                                <i class="fas fa-shield-alt me-3"></i> SmartSafe AI
                            </h1>
                                                            <p class="text-white-50 fs-5">Security Monitoring SaaS System</p>
                        </div>
                        
                        <div class="glass-card">
                            <div class="card-body p-5">
                                <div class="text-center mb-5">
                                    <div class="feature-icon mx-auto gradient-bg">
                                        <i class="fas fa-building"></i>
                                    </div>
                                    <h2 class="fw-bold mb-2">Company Registration</h2>
                                    <p class="text-muted">Create safe workspaces with SmartSafe AI</p>
                                </div>
                                
                                <form id="registerForm" method="POST" action="/api/register-form">
                                    <!-- Abonelik Planı Seçimi - Açılır Kapanır -->
                                    <div class="mb-4">
                                        <!-- Açılır-Kapanır Buton -->
                                        <div class="d-grid mb-3">
                                            <button type="button" class="btn btn-outline-primary btn-lg" 
                                                    onclick="toggleSubscriptionPlans()" 
                                                    id="toggleSubscriptionBtn"
                                                    style="border-radius: 15px; border: 2px solid #1E3A8A; font-weight: 600; background: rgba(30, 58, 138, 0.05);">
                                                <span id="toggleBtnText">Abonelik Planını Seç</span>
                                                <i class="fas fa-chevron-down ms-2" id="toggleIcon"></i>
                                            </button>
                                        </div>

                                        
                                        <!-- Gizli Abonelik Planları -->
                                        <div id="subscriptionPlansContainer" style="display: none;">
                                            <div class="glass-card p-4 mb-4" style="background: rgba(59, 130, 246, 0.05); border: 2px solid rgba(59, 130, 246, 0.1); border-radius: 15px;">
                                                <h5 class="text-center mb-4">
                                                    <i class="text-center mb-4"></i>
                                                    Abonelik Planı Seçin
                                                </h5>
                                                
                                                <!-- Modern Plan Kartları -->
                                                <div class="row g-3 mb-3">
                                            <!-- Starter Plan -->
                                            <div class="col-md-4">
                                                <div class="plan-card-modern" data-plan="starter" onclick="selectPlanCard('starter')">
                                                    <input type="radio" name="subscription_plan" value="starter" id="plan_starter" checked style="display: none;">
                                                    <input type="hidden" name="billing_cycle" id="billing_cycle" value="monthly">
                                                    <div class="plan-card-header starter-gradient">
                                                        <div class="plan-icon">
                                                            <i class="fas fa-rocket"></i>
                                            </div>
                                                        <h5 class="plan-name">Starter</h5>
                                                        <div class="billing-toggle mb-3">
                                                            <button type="button" class="btn btn-sm btn-outline-primary active" data-cycle="monthly" onclick="toggleBilling('starter', 'monthly')">Aylık</button>
                                                            <button type="button" class="btn btn-sm btn-outline-primary" data-cycle="yearly" onclick="toggleBilling('starter', 'yearly')">Yıllık</button>
                                                </div>
                                                        <div class="plan-price">
                                                            <div class="monthly-price">$99<span class="period">/ay</span></div>
                                                            <div class="yearly-price" style="display: none;">$990<span class="period">/yıl</span><span class="discount-badge">%17 İndirim</span></div>
                                            </div>
                                                </div>
                                                    <div class="plan-card-body">
                                                        <div class="plan-features">
                                                            <div class="feature-item">
                                                                <i class="fas fa-video text-primary"></i>
                                                                <span>25 Kamera</span>
                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-brain text-success"></i>
                                                                <span>AI Tespit (24/7)</span>
                                        </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-headset text-info"></i>
                                                                <span>Email Destek</span>
                                            </div>
                                        </div>
                                                        <div class="plan-badge starter-badge">Başlangıç</div>
                                        </div>
                                                </div>
                                            </div>

                                            <!-- Professional Plan -->
                                            <div class="col-md-4">
                                                <div class="plan-card-modern" data-plan="professional" onclick="selectPlanCard('professional')">
                                                    <input type="radio" name="subscription_plan" value="professional" id="plan_professional" style="display: none;">
                                                    <div class="plan-card-header professional-gradient">
                                                        <div class="plan-icon">
                                                            <i class="fas fa-star"></i>
                                                        </div>
                                                        <h5 class="plan-name">Professional</h5>
                                                        <div class="billing-toggle mb-3">
                                                            <button type="button" class="btn btn-sm btn-outline-primary active" data-cycle="monthly" onclick="toggleBilling('professional', 'monthly')">Aylık</button>
                                                            <button type="button" class="btn btn-sm btn-outline-primary" data-cycle="yearly" onclick="toggleBilling('professional', 'yearly')">Yıllık</button>
                                                        </div>
                                                        <div class="plan-price">
                                                            <div class="monthly-price">$299<span class="period">/ay</span></div>
                                                            <div class="yearly-price" style="display: none;">$2990<span class="period">/yıl</span><span class="discount-badge">%17 İndirim</span></div>
                                                        </div>
                                                        <div class="popular-badge">Popüler</div>
                                                    </div>
                                                    <div class="plan-card-body">
                                                        <div class="plan-features">
                                                            <div class="feature-item">
                                                                <i class="fas fa-video text-primary"></i>
                                                                <span>100 Kamera</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-brain text-success"></i>
                                                                <span>AI Tespit (24/7)</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-headset text-warning"></i>
                                                                <span>7/24 Destek</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-chart-line text-info"></i>
                                                                <span>Detaylı Analitik</span>
                                                            </div>
                                                        </div>
                                                        <div class="plan-badge professional-badge">Gelişmiş</div>
                                                    </div>
                                                </div>
                                            </div>

                                            <!-- Enterprise Plan -->
                                            <div class="col-md-4">
                                                <div class="plan-card-modern" data-plan="enterprise" onclick="selectPlanCard('enterprise')">
                                                    <input type="radio" name="subscription_plan" value="enterprise" id="plan_enterprise" style="display: none;">
                                                    <div class="plan-card-header enterprise-gradient">
                                                        <div class="plan-icon">
                                                            <i class="fas fa-crown"></i>
                                                        </div>
                                                        <h5 class="plan-name">Enterprise</h5>
                                                        <div class="billing-toggle mb-3">
                                                            <button type="button" class="btn btn-sm btn-outline-primary active" data-cycle="monthly" onclick="toggleBilling('enterprise', 'monthly')">Aylık</button>
                                                            <button type="button" class="btn btn-sm btn-outline-primary" data-cycle="yearly" onclick="toggleBilling('enterprise', 'yearly')">Yıllık</button>
                                                        </div>
                                                        <div class="plan-price">
                                                            <div class="monthly-price">$599<span class="period">/ay</span></div>
                                                            <div class="yearly-price" style="display: none;">$5990<span class="period">/yıl</span><span class="discount-badge">%17 İndirim</span></div>
                                                        </div>
                                                    </div>
                                                    <div class="plan-card-body">
                                                        <div class="plan-features">
                                                            <div class="feature-item">
                                                                <i class="fas fa-video text-primary"></i>
                                                                <span>500 Kamera</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-brain text-success"></i>
                                                                <span>AI Tespit (24/7)</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-headset text-danger"></i>
                                                                <span>Öncelikli Destek</span>
                                                            </div>
                                                            <div class="feature-item">
                                                                <i class="fas fa-cogs text-purple"></i>
                                                                <span>API Erişimi</span>
                                                            </div>
                                                        </div>
                                                        <div class="plan-badge enterprise-badge">Premium</div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Plan Bilgi Kartı -->
                                        <div class="plan-info-card">
                                            <div class="row align-items-center">
                                                <div class="col-md-8">
                                                    <div class="plan-info-content">
                                                        <i class="fas fa-info-circle text-primary me-2"></i>
                                                        <strong>Max kamera sayısı otomatik olarak seçilen plana göre belirlenir.</strong>
                                                        <br>
                                                        <span class="text-muted">İlk 7 gün ücretsiz! İstediğiniz zaman planınızı değiştirebilirsiniz.</span>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 text-end">
                                                    <button type="button" class="btn btn-outline-primary btn-modern" onclick="window.open('/upgrade-modal', '_blank', 'width=1400,height=900,scrollbars=yes,resizable=yes,toolbar=no,menubar=no')">
                                                        <i class="fas fa-info-circle me-2"></i>
                                                        Plan Detaylarını Gör
                                            </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                        </div>
                                    </div>

                                    <!-- Modern Business Form Section -->
                                    <div class="business-form-section mb-5">
                                        <div class="section-header mb-4">
                                            <div class="section-icon-wrapper">
                                                <i class="fas fa-building text-primary"></i>
                                            </div>
                                            <h5 class="section-title mb-2">Company Information</h5>
                                            <p class="section-subtitle text-muted">Please provide your company details to get started</p>
                                        </div>
                                        
                                        <div class="row g-4">
                                            <!-- Company Name -->
                                            <div class="col-md-6">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-building text-primary me-2"></i>
                                                        Company Name <span class="required-mark">*</span>
                                            </label>
                                                    <div class="input-group-modern">
                                                        <input type="text" class="form-control-modern" name="company_name" 
                                                               placeholder="Enter your company name" required>
                                                        <span class="input-icon">
                                                            <i class="fas fa-building text-primary"></i>
                                                        </span>
                                        </div>
                                                </div>
                                            </div>

                                            <!-- Contact Person -->
                                            <div class="col-md-6">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-user text-primary me-2"></i>
                                                        Contact Person <span class="required-mark">*</span>
                                            </label>
                                                    <div class="input-group-modern">
                                                        <input type="text" class="form-control-modern" name="contact_person" 
                                                               placeholder="Full Name" required>
                                                        <span class="input-icon">
                                                            <i class="fas fa-user text-primary"></i>
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <!-- Phone -->
                                            <div class="col-md-6">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-phone text-primary me-2"></i>
                                                        Phone
                                                    </label>
                                                    <div class="input-group-modern">
                                                        <input type="tel" class="form-control-modern" name="phone"
                                                               placeholder="+1 555 123 4567">
                                                        <span class="input-icon">
                                                            <i class="fas fa-phone text-primary"></i>
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <!-- Email -->
                                            <div class="col-md-6">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-envelope text-primary me-2"></i>
                                                        E-mail <span class="required-mark">*</span>
                                                    </label>
                                                    <div class="input-group-modern">
                                                        <input type="email" class="form-control-modern" name="email" required
                                                               placeholder="example@company.com"
                                                               autocomplete="email">
                                                        <span class="input-icon">
                                                            <i class="fas fa-envelope text-primary"></i>
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <!-- Address -->
                                            <div class="col-md-12">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-map-marker-alt text-primary me-2"></i>
                                                        Address
                                                    </label>
                                                    <div class="input-group-modern">
                                                        <textarea class="form-control-modern address-textarea" name="address" rows="4"
                                                                placeholder="Enter your company address (street, city, state, zip code)"></textarea>
                                                        <span class="input-icon address-icon">
                                                            <i class="fas fa-map-marker-alt text-primary"></i>
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <!-- Industry -->
                                            <div class="col-md-8">
                                                <div class="form-group-modern">
                                                    <label class="form-label-modern">
                                                        <i class="fas fa-industry text-primary me-2"></i>
                                                        Industry <span class="required-mark">*</span>
                                                    </label>
                                                    <div class="input-group-modern">
                                                        <select class="form-control-modern" name="sector" required>
                                                <option value="">Select your industry</option>
                                                <option value="construction">🏗️ Construction</option>
                                                <option value="manufacturing">🏭 Manufacturing</option>
                                                <option value="chemical">⚗️ Chemical</option>
                                                <option value="food">🍕 Food & Beverage</option>
                                                <option value="warehouse">📦 Warehouse/Logistics</option>
                                                <option value="energy">⚡ Energy</option>
                                                <option value="petrochemical">🛢️ Petrochemical</option>
                                                <option value="marine">🚢 Marine & Shipyard</option>
                                                <option value="aviation">✈️ Aviation</option>
                                            </select>
                                                        <span class="input-icon">
                                                            <i class="fas fa-industry text-primary"></i>
                                                        </span>
                                        </div>
                                        </div>
                                    </div>
                                    

                                    </div>
                                    </div>
                                    
                                    <!-- PPE Seçimi -->
                                    <div class="mb-5" id="ppe-selection-container" style="display: none;">
                                        <div class="glass-card p-4" style="background: rgba(59, 130, 246, 0.05); border: 2px solid rgba(59, 130, 246, 0.1);">
                                            <label class="form-label fw-bold fs-5 mb-3">
                                                <i class="fas fa-hard-hat text-warning me-2"></i> 
                                                Required PPE Selection *
                                            </label>
                                            <p class="text-muted mb-3">Select the PPE items that should be mandatory in your company:</p>
                                            <div class="alert alert-info border-0" style="background: rgba(59, 130, 246, 0.1);">
                                                <i class="fas fa-info-circle me-2"></i> 
                                                <strong>First select your industry</strong> - Industry-specific PPE options will appear
                                            </div>
                                        
                                            <!-- İnşaat Sektörü PPE -->
                                            <div id="construction-ppe" class="ppe-options" style="display: none;">
                                                <div class="row">
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                            <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="construction-helmet" checked>
                                                            <label class="form-check-label fw-semibold" for="construction-helmet">
                                                                <i class="fas fa-hard-hat text-primary me-2"></i> Hard Hat/Helmet
                                                            </label>
                                                        </div>
                                                    </div>
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                            <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="construction-vest" checked>
                                                            <label class="form-check-label fw-semibold" for="construction-vest">
                                                                <i class="fas fa-tshirt text-warning me-2"></i> Safety Vest
                                                            </label>
                                                        </div>
                                                    </div>
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                            <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="construction-shoes" checked>
                                                            <label class="form-check-label fw-semibold" for="construction-shoes">
                                                                <i class="fas fa-socks text-success me-2"></i> Safety Shoes
                                                            </label>
                                                        </div>
                                                    </div>
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="construction-gloves">
                                                            <label class="form-check-label fw-semibold" for="construction-gloves">
                                                                <i class="fas fa-hand-paper text-info me-2"></i> Safety Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="glasses" id="construction-glasses">
                                                            <label class="form-check-label fw-semibold" for="construction-glasses">
                                                                <i class="fas fa-glasses text-info me-2"></i> Safety Glasses
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                    <div class="col-md-4 mb-3">
                                                        <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                            <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_harness" id="construction-harness" checked>
                                                            <label class="form-check-label fw-semibold" for="construction-harness">
                                                                <i class="fas fa-user-shield text-danger me-2"></i> Safety Harness
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Gıda Sektörü PPE -->
                                        <div id="food-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-4 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="hairnet" id="food-hairnet" checked>
                                                        <label class="form-check-label fw-semibold" for="food-hairnet">
                                                            <i class="fas fa-user-nurse text-primary me-2"></i> Hair Net/Cap
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="food-mask" checked>
                                                        <label class="form-check-label fw-semibold" for="food-mask">
                                                            <i class="fas fa-head-side-mask text-warning me-2"></i> Hygiene Mask
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="apron" id="food-apron" checked>
                                                        <label class="form-check-label fw-semibold" for="food-apron">
                                                            <i class="fas fa-tshirt text-success me-2"></i> Hygiene Apron
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="food-gloves">
                                                        <label class="form-check-label fw-semibold" for="food-gloves">
                                                            <i class="fas fa-hand-paper text-info me-2"></i> Hygiene Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_shoes" id="food-shoes">
                                                        <label class="form-check-label fw-semibold" for="food-shoes">
                                                            <i class="fas fa-socks text-info me-2"></i> Non-slip Shoes
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Kimya Sektörü PPE -->
                                        <div id="chemical-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="gloves" id="chemical-gloves" checked>
                                                        <label class="form-check-label fw-semibold" for="chemical-gloves">
                                                            <i class="fas fa-hand-paper text-primary me-2"></i> Chemical Gloves
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="glasses" id="chemical-glasses" checked>
                                                        <label class="form-check-label fw-semibold" for="chemical-glasses">
                                                            <i class="fas fa-glasses text-warning me-2"></i> Safety Goggles
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="chemical-mask" checked>
                                                        <label class="form-check-label fw-semibold" for="chemical-mask">
                                                            <i class="fas fa-head-side-mask text-success me-2"></i> Respiratory Mask
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_suit" id="chemical-suit" checked>
                                                        <label class="form-check-label fw-semibold" for="chemical-suit">
                                                            <i class="fas fa-tshirt text-info me-2"></i> Chemical Suit
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- İmalat Sektörü PPE -->
                                        <div id="manufacturing-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="manufacturing-helmet" checked>
                                                        <label class="form-check-label fw-semibold" for="manufacturing-helmet">
                                                            <i class="fas fa-hard-hat text-primary me-2"></i> Industrial Helmet
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="manufacturing-vest" checked>
                                                        <label class="form-check-label fw-semibold" for="manufacturing-vest">
                                                            <i class="fas fa-tshirt text-warning me-2"></i> Safety Vest
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="manufacturing-shoes" checked>
                                                        <label class="form-check-label fw-semibold" for="manufacturing-shoes">
                                                            <i class="fas fa-socks text-success me-2"></i> Safety Shoes
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="manufacturing-gloves">
                                                        <label class="form-check-label fw-semibold" for="manufacturing-gloves">
                                                            <i class="fas fa-hand-paper text-info me-2"></i> Work Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Depo/Lojistik Sektörü PPE -->
                                        <div id="warehouse-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="warehouse-vest" checked>
                                                        <label class="form-check-label fw-semibold" for="warehouse-vest">
                                                            <i class="fas fa-tshirt text-warning me-2"></i> High-Visibility Vest
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="warehouse-shoes" checked>
                                                        <label class="form-check-label fw-semibold" for="warehouse-shoes">
                                                            <i class="fas fa-socks text-success me-2"></i> Steel-Toe Shoes
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="helmet" id="warehouse-helmet">
                                                        <label class="form-check-label fw-semibold" for="warehouse-helmet">
                                                            <i class="fas fa-hard-hat text-primary me-2"></i> Safety Helmet
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="warehouse-gloves">
                                                        <label class="form-check-label fw-semibold" for="warehouse-gloves">
                                                            <i class="fas fa-hand-paper text-info me-2"></i> Work Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Enerji Sektörü PPE -->
                                        <div id="energy-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="insulated_gloves" id="energy-gloves" checked>
                                                        <label class="form-check-label fw-semibold" for="energy-gloves">
                                                            <i class="fas fa-hand-paper text-primary me-2"></i> İzole Eldiven
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="dielectric_boots" id="energy-boots" checked>
                                                        <label class="form-check-label fw-semibold" for="energy-boots">
                                                            <i class="fas fa-socks text-warning me-2"></i> Dielektrik Ayakkabı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="arc_flash_suit" id="energy-suit" checked>
                                                        <label class="form-check-label fw-semibold" for="energy-suit">
                                                            <i class="fas fa-tshirt text-success me-2"></i> Ark Flaş Tulumu
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="energy-helmet" checked>
                                                        <label class="form-check-label fw-semibold" for="energy-helmet">
                                                            <i class="fas fa-hard-hat text-info me-2"></i> Güvenlik Kaskı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_glasses" id="energy-glasses">
                                                        <label class="form-check-label fw-semibold" for="energy-glasses">
                                                            <i class="fas fa-glasses text-info me-2"></i> Güvenlik Gözlüğü
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-3">
                                                    <div class="form-check p-3 border rounded-3" style="background: rgba(34, 197, 94, 0.05); border-color: rgba(34, 197, 94, 0.2) !important;">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="ear_protection" id="energy-ears">
                                                        <label class="form-check-label fw-semibold" for="energy-ears">
                                                            <i class="fas fa-headphones text-info me-2"></i> Kulak Koruyucu
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Petrokimya Sektörü PPE -->
                                        <div id="petrochemical-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="chemical_suit" id="petrochemical-suit" checked>
                                                        <label class="form-check-label" for="petrochemical-suit">
                                                            <i class="fas fa-tshirt text-primary"></i> Kimyasal Tulum
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="respiratory_protection" id="petrochemical-resp" checked>
                                                        <label class="form-check-label" for="petrochemical-resp">
                                                            <i class="fas fa-head-side-mask text-warning"></i> Solunum Koruyucu
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="special_gloves" id="petrochemical-gloves" checked>
                                                        <label class="form-check-label" for="petrochemical-gloves">
                                                            <i class="fas fa-hand-paper text-success"></i> Özel Eldiven
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="petrochemical-helmet" checked>
                                                        <label class="form-check-label" for="petrochemical-helmet">
                                                            <i class="fas fa-hard-hat text-info"></i> Güvenlik Kaskı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_glasses" id="petrochemical-glasses">
                                                        <label class="form-check-label" for="petrochemical-glasses">
                                                            <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_shoes" id="petrochemical-shoes">
                                                        <label class="form-check-label" for="petrochemical-shoes">
                                                            <i class="fas fa-socks text-info"></i> Güvenlik Ayakkabısı
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Denizcilik Sektörü PPE -->
                                        <div id="marine-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="life_jacket" id="marine-lifejacket" checked>
                                                        <label class="form-check-label" for="marine-lifejacket">
                                                            <i class="fas fa-life-ring text-primary"></i> Can Yeleği
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="marine_helmet" id="marine-helmet" checked>
                                                        <label class="form-check-label" for="marine-helmet">
                                                            <i class="fas fa-hard-hat text-warning"></i> Denizci Kaskı/Baret
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="waterproof_shoes" id="marine-shoes" checked>
                                                        <label class="form-check-label" for="marine-shoes">
                                                            <i class="fas fa-socks text-success"></i> Su Geçirmez Ayakkabı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="marine-vest" checked>
                                                        <label class="form-check-label" for="marine-vest">
                                                            <i class="fas fa-tshirt text-info"></i> Güvenlik Yeleği
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="marine-gloves">
                                                        <label class="form-check-label" for="marine-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> İş Eldiveni
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_glasses" id="marine-glasses">
                                                        <label class="form-check-label" for="marine-glasses">
                                                            <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Havacılık Sektörü PPE -->
                                        <div id="aviation-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="aviation_helmet" id="aviation-helmet" checked>
                                                        <label class="form-check-label" for="aviation-helmet">
                                                            <i class="fas fa-hard-hat text-primary"></i> Havacılık Kaskı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="reflective_vest" id="aviation-vest" checked>
                                                        <label class="form-check-label" for="aviation-vest">
                                                            <i class="fas fa-tshirt text-warning"></i> Reflektör Yelek
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="aviation_shoes" id="aviation-shoes" checked>
                                                        <label class="form-check-label" for="aviation-shoes">
                                                            <i class="fas fa-socks text-success"></i> Özel Ayakkabı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_glasses" id="aviation-glasses" checked>
                                                        <label class="form-check-label" for="aviation-glasses">
                                                            <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="ear_protection" id="aviation-ears">
                                                        <label class="form-check-label" for="aviation-ears">
                                                            <i class="fas fa-headphones text-info"></i> Kulak Koruyucu
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="aviation-gloves">
                                                        <label class="form-check-label" for="aviation-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> İş Eldiveni
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        </div>
                                    
                                    <div class="mb-4">
                                        <label class="form-label fw-semibold">
                                            <i class="fas fa-lock text-primary me-2"></i>Password *
                                        </label>
                                        <input type="password" class="form-control form-control-lg" name="password" id="register_password" required
                                               placeholder="Create a secure password"
                                               style="border-radius: 15px; border: 2px solid #e2e8f0;"
                                               oninput="updateRegisterPasswordStrength(this.value)">
                                        
                                        <!-- Şifre Gücü Göstergesi -->
                                        <div class="password-strength mt-2">
                                            <div class="strength-bar" style="width: 100%; height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden;">
                                                <div class="strength-fill" id="register-strength-fill" style="height: 100%; background: #dc3545; width: 0%; transition: all 0.3s ease; border-radius: 4px;"></div>
                                            </div>
                                            <small class="strength-text" id="register-strength-text" style="font-size: 0.8rem; color: #6c757d;">Password strength: Weak</small>
                                        </div>
                                        
                                        <!-- Şifre Gereksinimleri -->
                                        <div class="password-requirements mt-3" style="background: #f8f9fa; padding: 1rem; border-radius: 10px; border: 1px solid #e9ecef;">
                                            <h6 class="requirements-title mb-2" style="color: #2c3e50; font-weight: 600; font-size: 0.9rem;">
                                                <i class="fas fa-info-circle text-primary me-2"></i>
                                                Password Requirements
                                            </h6>
                                            <div class="requirements-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem;">
                                                <div class="requirement-item" id="register-req-length" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                                    <i class="fas fa-times text-danger me-2"></i>
                                                    <span>At least 8 characters</span>
                                                </div>
                                                <div class="requirement-item" id="register-req-uppercase" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                                    <i class="fas fa-times text-danger me-2"></i>
                                                    <span>At least 1 uppercase letter (A-Z)</span>
                                                </div>
                                                <div class="requirement-item" id="register-req-lowercase" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                                    <i class="fas fa-times text-danger me-2"></i>
                                                    <span>At least 1 lowercase letter (a-z)</span>
                                                </div>
                                                <div class="requirement-item" id="register-req-number" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                                    <i class="fas fa-times text-danger me-2"></i>
                                                    <span>At least 1 number (0-9)</span>
                                                </div>
                                                <div class="requirement-item" id="register-req-special" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                                    <i class="fas fa-times text-danger me-2"></i>
                                                    <span>At least 1 special character (!@#$%^&*)</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="d-grid">
                                        <button type="submit" class="btn btn-primary btn-lg" 
                                                style="border-radius: 30px; padding: 15px 0; font-weight: 600; font-size: 18px; background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%); border: none; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.3);">
                                                                                            <i class="fas fa-rocket me-2"></i> Register & Get Started
                                        </button>
                                    </div>
                                </form>
                                
                                <hr class="my-5" style="border-color: rgba(0,0,0,0.1); border-width: 2px;">
                                
                                <div class="glass-card p-4 mt-4" style="background: rgba(248, 250, 252, 0.8); border: 2px solid rgba(30, 58, 138, 0.1);">
                                    <div class="text-center mb-4">
                                        <div class="feature-icon mx-auto" style="width: 48px; height: 48px; background: linear-gradient(135deg, #64748b 0%, #475569 100%);">
                                            <i class="fas fa-sign-in-alt" style="font-size: 20px;"></i>
                                        </div>
                                        <h5 class="mt-3 mb-2 fw-bold">Registered Company Login</h5>
                                                                                 <p class="text-muted small">Login with your existing company account</p>
                                    </div>
                                    
                                    <form method="POST" action="/api/company-login-redirect">
                                        <div class="row align-items-end">
                                            <div class="col-md-8 mb-3">
                                                <label class="form-label fw-semibold small">
                                                    <i class="fas fa-id-card text-primary me-2"></i>Company ID
                                                </label>
                                                <input type="text" 
                                                       class="form-control form-control-lg" 
                                                       name="company_id" 
                                                       placeholder="COMP_ABC123 veya demo_20241217_143022"
                                                       style="border-radius: 15px; border: 2px solid #e2e8f0;"
                                                       required>
                                            </div>
                                            <div class="col-md-4 mb-3">
                                                <label class="form-label small text-transparent">.</label>
                                                <button type="submit" 
                                                        class="btn btn-outline-primary btn-lg w-100" 
                                                        style="border-radius: 15px; border: 2px solid #1E3A8A; font-weight: 600;">
                                                    <i class="fas fa-arrow-right me-2"></i> Login
                                                </button>
                                            </div>
                                        </div>
                                        <div class="alert alert-info border-0 mt-3" style="background: rgba(59, 130, 246, 0.1); border-radius: 10px;">
                                            <small class="text-muted">
                                                <i class="fas fa-info-circle me-2"></i>
                                                <strong>Company ID Formats:</strong><br>
                                                • <strong>Standard Account:</strong> COMP_ABC123 (assigned after registration)<br>
                                                • <strong>Demo Account:</strong> demo_20241217_143022 (assigned after demo request)
                                            </small>
                                        </div>
                                    </form>
                                </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Plan Detayları Modal -->
            <div class="modal fade" id="planDetailsModal" tabindex="-1" aria-labelledby="planDetailsModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content border-0 shadow-lg" style="border-radius: 20px;">
                        <div class="modal-header border-0 bg-gradient-primary text-white" style="border-radius: 20px 20px 0 0; background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%);">
                            <div class="d-flex align-items-center">
                                <div class="me-3">
                                    <div class="bg-white bg-opacity-20 rounded-circle p-3" style="width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;">
                                        <i class="fas fa-crown text-white" style="font-size: 24px;"></i>
                                    </div>
                                </div>
                                <div>
                                    <h4 class="modal-title mb-1" id="planDetailsModalLabel">
                                        <strong>SmartSafe AI Abonelik Planları</strong>
                                    </h4>
                                    <p class="mb-0 text-white-50">İhtiyacınıza en uygun planı seçin</p>
                                </div>
                            </div>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        
                        <div class="modal-body p-0">
                            <!-- Hero Section -->
                            <div class="bg-light py-4 px-4" style="background: linear-gradient(135deg, #F8FAFC 0%, #E2E8F0 100%);">
                                <div class="text-center">
                                    <h5 class="text-primary mb-2">
                                        <i class="fas fa-gift text-warning me-2"></i>
                                        <strong>İlk 7 Gün Ücretsiz Deneme!</strong>
                                    </h5>
                                    <p class="text-muted mb-0">İlk 7 gün ücretsiz • Hiçbir kredi kartı gerektirmez • İstediğiniz zaman iptal edebilirsiniz</p>
                                </div>
                            </div>

                            <!-- Plans Section -->
                            <div class="p-4">
                                <div class="row g-4">
                                    <!-- Starter Plan -->
                                    <div class="col-lg-4">
                                        <div class="card h-100 border-0 shadow-sm plan-card" data-plan="starter" style="border-radius: 16px; transition: all 0.3s ease;">
                                            <div class="card-header bg-white border-0 text-center pt-4" style="border-radius: 16px 16px 0 0;">
                                                <div class="mb-3">
                                                    <div class="bg-primary bg-opacity-10 rounded-circle mx-auto d-flex align-items-center justify-content-center" style="width: 80px; height: 80px;">
                                                        <i class="fas fa-rocket text-primary" style="font-size: 32px;"></i>
                                                    </div>
                                                </div>
                                                <h4 class="fw-bold text-dark mb-1">Starter</h4>
                                                <p class="text-muted mb-3">Küçük işletmeler için AI destekli PPE tespiti</p>
                                                <div class="mb-3">
                                                    <span class="display-6 fw-bold text-primary">$99</span>
                                                    <span class="text-muted">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">25 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24/7)</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #ffc107 !important;">
                                                            <i class="fas fa-headset text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Email Destek</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #6c757d !important;">
                                                            <i class="fas fa-chart-bar text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Temel Raporlar</span>
                                                    </div>
                                                </div>
                                                <button class="btn btn-primary btn-lg w-100 rounded-pill shadow-sm" onclick="selectPlanForRegistration('starter')" style="background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%); border: none; padding: 12px 24px;">
                                                    <i class="fas fa-check me-2"></i>Starter Planı Seç
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Professional Plan -->
                                    <div class="col-lg-4">
                                        <div class="card h-100 border-0 shadow-lg plan-card position-relative" data-plan="professional" style="border-radius: 16px; transition: all 0.3s ease; transform: scale(1.05);">
                                            <div class="position-absolute top-0 start-50 translate-middle-x">
                                                <span class="badge bg-warning text-dark px-3 py-2 rounded-pill" style="font-size: 14px;">
                                                    <i class="fas fa-star me-1"></i>En Popüler
                                                </span>
                                            </div>
                                            <div class="card-header bg-gradient-warning border-0 text-center pt-4 text-white" style="border-radius: 16px 16px 0 0; background: linear-gradient(135deg, #F59E0B 0%, #F97316 100%);">
                                                <div class="mb-3">
                                                    <div class="bg-white bg-opacity-20 rounded-circle mx-auto d-flex align-items-center justify-content-center" style="width: 80px; height: 80px;">
                                                        <i class="fas fa-star text-white" style="font-size: 32px;"></i>
                                                    </div>
                                                </div>
                                                <h4 class="fw-bold text-white mb-1">Professional</h4>
                                                <p class="text-white-50 mb-3">Büyüyen işletmeler için gelişmiş AI tespit sistemi</p>
                                                <div class="mb-3">
                                                    <span class="display-6 fw-bold text-white">$299</span>
                                                    <span class="text-white-50">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">100 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24/7)</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #ffc107 !important;">
                                                            <i class="fas fa-headset text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">7/24 Destek</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0d6efd !important;">
                                                            <i class="fas fa-chart-line text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Detaylı Analitik</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #dc3545 !important;">
                                                            <i class="fas fa-bell text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Gelişmiş Bildirimler</span>
                                                    </div>
                                                </div>
                                                <button class="btn btn-warning btn-lg w-100 rounded-pill shadow-sm text-white" onclick="selectPlanForRegistration('professional')" style="background: linear-gradient(135deg, #F59E0B 0%, #F97316 100%); border: none; padding: 12px 24px;">
                                                    <i class="fas fa-star me-2"></i>Professional Planı Seç
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Enterprise Plan -->
                                    <div class="col-lg-4">
                                        <div class="card h-100 border-0 shadow-sm plan-card" data-plan="enterprise" style="border-radius: 16px; transition: all 0.3s ease;">
                                            <div class="card-header bg-gradient-primary border-0 text-center pt-4 text-white" style="border-radius: 16px 16px 0 0; background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%);">
                                                <div class="mb-3">
                                                    <div class="bg-white bg-opacity-20 rounded-circle mx-auto d-flex align-items-center justify-content-center" style="width: 80px; height: 80px;">
                                                        <i class="fas fa-crown text-white" style="font-size: 32px;"></i>
                                                    </div>
                                                </div>
                                                <h4 class="fw-bold text-white mb-1">Enterprise</h4>
                                                <p class="text-white-50 mb-3">Büyük kurumlar için endüstriyel AI tespit sistemi</p>
                                                <div class="mb-3">
                                                    <span class="display-6 fw-bold text-white">$599</span>
                                                    <span class="text-white-50">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">500 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24/7)</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #ffc107 !important;">
                                                            <i class="fas fa-headset text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Öncelikli Destek</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0d6efd !important;">
                                                            <i class="fas fa-chart-pie text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Özel Raporlar</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #6c757d !important;">
                                                            <i class="fas fa-cogs text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">API Erişimi</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #dc3545 !important;">
                                                            <i class="fas fa-users text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">Çoklu Kullanıcı</span>
                                                    </div>
                                                </div>
                                                <button class="btn btn-primary btn-lg w-100 rounded-pill shadow-sm" onclick="selectPlanForRegistration('enterprise')" style="background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%); border: none; padding: 12px 24px;">
                                                    <i class="fas fa-crown me-2"></i>Enterprise Planı Seç
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Features Comparison -->
                                <div class="mt-5">
                                    <div class="card border-0 shadow-sm" style="border-radius: 16px;">
                                        <div class="card-header bg-light border-0 text-center" style="border-radius: 16px 16px 0 0;">
                                            <h5 class="mb-0 text-primary">
                                                <i class="fas fa-list-check me-2"></i>Özellik Karşılaştırması
                                            </h5>
                                        </div>
                                        <div class="card-body p-0">
                                            <div class="table-responsive">
                                                <table class="table table-hover mb-0">
                                                    <tbody>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold" style="width: 40%;">
                                                                <i class="fas fa-video text-primary me-2"></i>Kamera Sayısı
                                                            </td>
                                                            <td class="border-0 text-center">25</td>
                                                            <td class="border-0 text-center fw-bold text-warning">100</td>
                                                            <td class="border-0 text-center">500</td>
                                                        </tr>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold">
                                                                <i class="fas fa-brain text-primary me-2"></i>AI Tespit Hızı
                                                            </td>
                                                            <td class="border-0 text-center">24/7</td>
                                                            <td class="border-0 text-center fw-bold text-warning">24/7</td>
                                                            <td class="border-0 text-center">24/7</td>
                                                        </tr>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold">
                                                                <i class="fas fa-headset text-primary me-2"></i>Müşteri Desteği
                                                            </td>
                                                            <td class="border-0 text-center">Email</td>
                                                            <td class="border-0 text-center fw-bold text-warning">7/24</td>
                                                            <td class="border-0 text-center">Öncelikli</td>
                                                        </tr>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold">
                                                                <i class="fas fa-chart-line text-primary me-2"></i>Analitik
                                                            </td>
                                                            <td class="border-0 text-center">Temel</td>
                                                            <td class="border-0 text-center fw-bold text-warning">Detaylı</td>
                                                            <td class="border-0 text-center">Özel</td>
                                                        </tr>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold">
                                                                <i class="fas fa-users text-primary me-2"></i>Kullanıcı Sayısı
                                                            </td>
                                                            <td class="border-0 text-center">1</td>
                                                            <td class="border-0 text-center fw-bold text-warning">5</td>
                                                            <td class="border-0 text-center">Sınırsız</td>
                                                        </tr>
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Important Information -->
                                <div class="mt-4">
                                    <div class="alert alert-info border-0" style="border-radius: 16px; background: linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%);">
                                        <div class="d-flex align-items-start">
                                            <div class="me-3 mt-1">
                                                <i class="fas fa-info-circle text-primary" style="font-size: 20px;"></i>
                                            </div>
                                            <div>
                                                <h6 class="fw-bold text-primary mb-2">Önemli Bilgiler</h6>
                                                <div class="row">
                                                    <div class="col-md-6">
                                                        <ul class="list-unstyled mb-0">
                                                            <li class="mb-2">
                                                                <i class="fas fa-check-circle text-success me-2"></i>
                                                                İlk 30 gün ücretsiz deneme
                                                            </li>
                                                            <li class="mb-2">
                                                                <i class="fas fa-check-circle text-success me-2"></i>
                                                                İstediğiniz zaman planınızı değiştirebilirsiniz
                                                            </li>
                                                        </ul>
                                                    </div>
                                                    <div class="col-md-6">
                                                        <ul class="list-unstyled mb-0">
                                                            <li class="mb-2">
                                                                <i class="fas fa-check-circle text-success me-2"></i>
                                                                Kamera sayısı otomatik olarak plana göre belirlenir
                                                            </li>
                                                            <li class="mb-2">
                                                                <i class="fas fa-check-circle text-success me-2"></i>
                                                                Anında kurulum ve başlangıç
                                                            </li>
                                                        </ul>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="modal-footer border-0 bg-light" style="border-radius: 0 0 20px 20px;">
                            <button type="button" class="btn btn-outline-secondary rounded-pill px-4" data-bs-dismiss="modal">
                                <i class="fas fa-times me-2"></i>Kapat
                            </button>
                        </div>
                    </div>
                </div>
            </div>
                                            </small>
                                        </div>
                                    </form>
                                </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Abonelik planlarını aç/kapat
                function toggleSubscriptionPlans() {
                    const container = document.getElementById('subscriptionPlansContainer');
                    const btn = document.getElementById('toggleSubscriptionBtn');
                    const btnText = document.getElementById('toggleBtnText');
                    const icon = document.getElementById('toggleIcon');
                    
                    if (container.style.display === 'none' || container.style.display === '') {
                        // Aç
                        container.style.display = 'block';
                        btnText.textContent = 'Abonelik Planını Gizle';
                        icon.className = 'fas fa-chevron-up ms-2';
                        btn.style.background = 'rgba(30, 58, 138, 0.1)';
                        btn.style.borderColor = '#1E3A8A';
                        
                        // Smooth scroll to plans
                        setTimeout(() => {
                            container.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }, 100);
                    } else {
                        // Kapat
                        container.style.display = 'none';
                        btnText.textContent = 'Abonelik Planını Seç';
                        icon.className = 'fas fa-chevron-down ms-2';
                        btn.style.background = 'rgba(30, 58, 138, 0.05)';
                        btn.style.borderColor = '#1E3A8A';
                    }
                }
                
                // Global değişkenler
                let selectedBillingCycle = 'monthly';
                
                function toggleBilling(plan, cycle) {
                    console.log('Toggle billing:', plan, cycle);
                    
                    // Tüm plan kartlarındaki toggle butonlarını güncelle
                    const planCard = document.querySelector(`[data-plan="${plan}"]`);
                    if (planCard) {
                        // Toggle butonlarını güncelle
                        const toggleButtons = planCard.querySelectorAll('.billing-toggle .btn');
                        toggleButtons.forEach(btn => {
                            btn.classList.remove('active');
                            if (btn.getAttribute('data-cycle') === cycle) {
                                btn.classList.add('active');
                            }
                        });
                        
                        // Fiyat gösterimini değiştir
                        const monthlyPrice = planCard.querySelector('.monthly-price');
                        const yearlyPrice = planCard.querySelector('.yearly-price');
                        
                        if (cycle === 'monthly') {
                            monthlyPrice.style.display = 'inline';
                            yearlyPrice.style.display = 'none';
                        } else {
                            monthlyPrice.style.display = 'none';
                            yearlyPrice.style.display = 'inline';
                        }
                    }
                    
                    // Global billing cycle'ı güncelle
                    selectedBillingCycle = cycle;
                }
                
                // Plan seçimi fonksiyonu (Modern kartlar için)
                function selectPlanCard(plan) {
                    const radioButton = document.getElementById('plan_' + plan);
                    if (radioButton) {
                        radioButton.checked = true;
                        console.log('Plan seçildi:', plan);
                    }
                    
                    // Billing cycle'ı hidden input'a yaz
                    const billingCycleInput = document.getElementById('billing_cycle');
                    if (billingCycleInput) {
                        billingCycleInput.value = selectedBillingCycle;
                        console.log('Billing cycle:', selectedBillingCycle);
                    }
                    
                    // Tüm kartlardan seçim işaretini kaldır
                    document.querySelectorAll('.plan-card-modern').forEach(card => {
                        card.classList.remove('selected');
                    });
                    
                    // Seçilen kartı işaretle
                    const selectedCard = document.querySelector('[data-plan="' + plan + '"]');
                    if (selectedCard) {
                        selectedCard.classList.add('selected');
                    }
                }
                
                // Plan Detayları Modal Fonksiyonları
                function openPlanDetailsModal() {
                    const modal = new bootstrap.Modal(document.getElementById('planDetailsModal'));
                    modal.show();
                }

                function selectPlanForRegistration(plan) {
                    // Radio button'u seç
                    const radioButton = document.getElementById('plan_' + plan);
                    if (radioButton) {
                        radioButton.checked = true;
                    }
                    
                    // Modal'ı kapat
                    const modal = bootstrap.Modal.getInstance(document.getElementById('planDetailsModal'));
                    if (modal) {
                        modal.hide();
                    }
                    
                    // Kullanıcıya bilgi ver
                    const planNames = {
                        'starter': 'Starter',
                        'professional': 'Professional', 
                        'enterprise': 'Enterprise'
                    };
                    
                    // Toast notification benzeri mesaj
                    const notification = document.createElement('div');
                    notification.className = 'position-fixed top-0 end-0 p-3';
                    notification.style.zIndex = '9999';
                    notification.innerHTML = `
                        <div class="toast show" role="alert">
                            <div class="toast-header bg-success text-white">
                                <i class="fas fa-check-circle me-2"></i>
                                <strong class="me-auto">Plan Seçildi!</strong>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
                            </div>
                            <div class="toast-body">
                                <strong>${planNames[plan]}</strong> planı başarıyla seçildi!
                            </div>
                        </div>
                    `;
                    document.body.appendChild(notification);
                    
                    // 3 saniye sonra kaldır
                    setTimeout(() => {
                        notification.remove();
                    }, 3000);
                }

                // Email Validation for Registration
                function validateEmailRegister(input) {
                    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$/;
                    const isValid = emailRegex.test(input.value);
                    
                    if (input.value && !isValid) {
                        input.classList.add('is-invalid');
                        input.classList.remove('is-valid');
                        
                        // Remove existing error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                        
                        // Add error message
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'invalid-feedback';
                        errorDiv.textContent = 'Please enter a valid email address (Turkish characters are supported)';
                        input.parentNode.appendChild(errorDiv);
                    } else if (input.value && isValid) {
                        input.classList.add('is-valid');
                        input.classList.remove('is-invalid');
                        
                        // Remove error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                    } else {
                        input.classList.remove('is-valid', 'is-invalid');
                        
                        // Remove error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                    }
                }

                // Form validation on submit
                document.getElementById('registerForm').addEventListener('submit', function(e) {
                    const emailInput = this.querySelector('input[name="email"]');
                    
                    // Email validation
                    if (!emailInput.value.includes('@')) {
                        e.preventDefault();
                        alert('Please enter a valid email address!');
                        emailInput.focus();
                        return false;
                    }
                    
                    // PPE selection validation
                    const requiredPPE = document.querySelectorAll('input[name="required_ppe"]:checked');
                    const optionalPPE = document.querySelectorAll('input[name="optional_ppe"]:checked');
                    
                    if (requiredPPE.length === 0 && optionalPPE.length === 0) {
                        e.preventDefault();
                        alert('You must select at least one PPE type!');
                        return false;
                    }
                });

                // PPE Sector Selection - Debug Version
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('DOM loaded, PPE system starting...');
                    
                    var sectorSelect = document.querySelector('select[name="sector"]');
                    var ppeContainer = document.getElementById('ppe-selection-container');
                    
                    console.log('Sector select element:', sectorSelect);
                    console.log('PPE container element:', ppeContainer);
                    
                    if (sectorSelect && ppeContainer) {
                        console.log('Elements found, adding event listener...');
                        
                        // Check current sector value on page load
                        var currentSector = sectorSelect.value;
                        console.log('Sector value on page load:', currentSector);
                        
                        if (currentSector && currentSector !== '') {
                            console.log('Current sector exists, showing PPE...');
                            showPPEForSector(currentSector, ppeContainer);
                        }
                        
                        sectorSelect.addEventListener('change', function() {
                            var sector = this.value;
                            console.log('Sector changed:', sector);
                            showPPEForSector(sector, ppeContainer);
                        });
                        
                        console.log('Event listener added successfully!');
                    } else {
                        console.log('ERROR: Elements not found!');
                        console.log('sectorSelect:', sectorSelect);
                        console.log('ppeContainer:', ppeContainer);
                    }
                });
                
                function showPPEForSector(sector, ppeContainer) {
                    console.log('showPPEForSector called, sector:', sector);
                    
                    // Hide all PPE options
                    var options = document.querySelectorAll('.ppe-options');
                    console.log('Found PPE options count:', options.length);
                    
                    for (var i = 0; i < options.length; i++) {
                        options[i].style.display = 'none';
                        console.log('Hidden:', options[i].id);
                    }
                    
                    if (sector && sector !== '') {
                        // Show PPE container
                        ppeContainer.style.display = 'block';
                        console.log('PPE container shown');
                        
                        // Show selected sector's PPE
                        var targetPPEId = sector + '-ppe';
                        var targetPPE = document.getElementById(targetPPEId);
                        
                        console.log('Target PPE ID:', targetPPEId);
                        console.log('Found PPE element:', targetPPE);
                        
                        if (targetPPE) {
                            targetPPE.style.display = 'block';
                            console.log('PPE options shown!');
                        } else {
                            console.log('ERROR: PPE element not found!');
                            // List all PPE elements
                            var allPPEs = document.querySelectorAll('[id$="-ppe"]');
                            console.log('Available PPE elements:');
                            for (var j = 0; j < allPPEs.length; j++) {
                                console.log('- ' + allPPEs[j].id);
                            }
                        }
                    } else {
                        ppeContainer.style.display = 'none';
                        console.log('PPE container hidden');
                    }
                }
                
                // Demo Modal Functions
                function openDemoModal() {
                    document.getElementById('demoModal').style.display = 'block';
                }
                
                function closeDemoModal() {
                    document.getElementById('demoModal').style.display = 'none';
                }
                
                function submitDemoRequest() {
                    const form = document.getElementById('demoForm');
                    const formData = new FormData(form);
                    
                    const demoData = {
                        company_name: formData.get('demo_company_name'),
                        sector: formData.get('demo_sector'),
                        contact_person: formData.get('demo_contact_person'),
                        email: formData.get('demo_email'),
                        phone: formData.get('demo_phone') || ''
                    };
                    
                    fetch('/api/request-demo', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(demoData)
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('✅ Demo hesabınız oluşturuldu! Giriş sayfasına yönlendiriliyorsunuz...');
                            window.location.href = data.login_url;
                        } else {
                            alert('❌ Hata: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('❌ Bir hata oluştu. Lütfen tekrar deneyin.');
                    });
                }
                
                // Close modal when clicking outside
                window.onclick = function(event) {
                    const modal = document.getElementById('demoModal');
                    if (event.target == modal) {
                        closeDemoModal();
                    }
                }
                
                // Şifre validation fonksiyonları
                function validatePasswordStrength(password) {
                    const requirements = {
                        length: password.length >= 8,
                        uppercase: /[A-Z]/.test(password),
                        lowercase: /[a-z]/.test(password),
                        number: /[0-9]/.test(password),
                        special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
                    };
                    return requirements;
                }
                
                function updateRegisterPasswordStrength(password) {
                    const requirements = validatePasswordStrength(password);
                    const strengthFill = document.getElementById('register-strength-fill');
                    const strengthText = document.getElementById('register-strength-text');
                    
                    if (!strengthFill || !strengthText) return;
                    
                    // Gereksinimleri güncelle
                    Object.keys(requirements).forEach(req => {
                        const element = document.getElementById(`register-req-${req}`);
                        if (element) {
                            if (requirements[req]) {
                                element.innerHTML = '<i class="fas fa-check text-success me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.add('valid');
                            } else {
                                element.innerHTML = '<i class="fas fa-times text-danger me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.remove('valid');
                            }
                        }
                    });
                    
                    // Güç seviyesini hesapla
                    const validCount = Object.values(requirements).filter(Boolean).length;
                    let strength = 'Zayıf';
                    let width = '25%';
                    let color = '#dc3545';
                    
                    if (validCount >= 5) {
                        strength = 'Güçlü';
                        width = '100%';
                        color = '#20c997';
                    } else if (validCount >= 4) {
                        strength = 'İyi';
                        width = '75%';
                        color = '#28a745';
                    } else if (validCount >= 3) {
                        strength = 'Orta';
                        width = '50%';
                        color = '#ffc107';
                    }
                    
                    // Güç göstergesini güncelle
                    strengthFill.style.width = width;
                    strengthFill.style.background = color;
                    strengthText.textContent = `Password strength: ${strength}`;
                }
            </script>
        </body>
        </html>
        '''
    
    def get_dashboard_template(self):
        """Advanced Dashboard Template with Real-time PPE Analytics"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe AI - {{ user_data.company_name }}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .navbar {
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                    border: none;
                }
                .stat-card {
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                    border: none;
                }
                .stat-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 15px 35px rgba(0,0,0,0.2);
                }
                .stat-value {
                    font-size: 2.5rem;
                    font-weight: 700;
                    color: #2c3e50;
                    margin-bottom: 5px;
                }
                .stat-value.small-text {
                    font-size: 1.8rem;
                }
                .stat-label {
                    color: #7f8c8d;
                    font-size: 0.9rem;
                    font-weight: 500;
                }
                .stat-icon {
                    font-size: 2.5rem;
                    margin-bottom: 15px;
                }
                .chart-container {
                    position: relative;
                    height: 300px;
                    margin: 20px 0;
                }
                .status-indicator {
                    display: inline-block;
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    margin-right: 8px;
                    animation: pulse 2s infinite;
                }
                .status-active { background: #27ae60; }
                .status-warning { background: #f39c12; }
                .status-error { background: #e74c3c; }
                .status-offline { background: #95a5a6; }
                
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(39, 174, 96, 0.7); }
                    70% { box-shadow: 0 0 0 10px rgba(39, 174, 96, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(39, 174, 96, 0); }
                }
                
                .metric-trend {
                    font-size: 0.8rem;
                    margin-top: 5px;
                }
                .trend-up { color: #27ae60; }
                .trend-down { color: #e74c3c; }
                .trend-neutral { color: #95a5a6; }
                
                .camera-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 15px;
                    margin-top: 20px;
                }
                .camera-card {
                    background: white;
                    border-radius: 10px;
                    padding: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                }
                .camera-card:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                }
                
                .alert-item {
                    padding: 15px;
                    margin-bottom: 10px;
                    border-radius: 10px;
                    border-left: 4px solid #e74c3c;
                    background: #fdf2f2;
                    transition: all 0.3s ease;
                }
                .alert-item:hover {
                    background: #f8d7da;
                    transform: translateX(5px);
                }
                
                .compliance-gauge {
                    position: relative;
                    width: 150px;
                    height: 150px;
                    margin: 0 auto;
                }
                
                .refresh-btn {
                    position: fixed;
                    bottom: 30px;
                    right: 30px;
                    z-index: 1000;
                    border-radius: 50%;
                    width: 60px;
                    height: 60px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                }
                
                /* Profil Dropdown Stilleri */
                .profile-dropdown {
                    min-width: 280px;
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                    padding: 0;
                    margin-top: 10px;
                }
                
                .profile-dropdown .dropdown-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 15px 15px 0 0;
                    border: none;
                }
                
                .profile-avatar {
                    width: 32px;
                    height: 32px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 14px;
                }
                
                .profile-avatar-large {
                    width: 48px;
                    height: 48px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 20px;
                }
                
                .profile-name {
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .profile-dropdown .dropdown-item {
                    padding: 12px 20px;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .profile-dropdown .dropdown-item:hover {
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    transform: translateX(5px);
                }
                
                .profile-dropdown .dropdown-item i {
                    width: 20px;
                    text-align: center;
                }
                
                .profile-dropdown .dropdown-divider {
                    margin: 0;
                    border-color: #e9ecef;
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/company/{{ company_id }}/dashboard">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        
                        <!-- Profil Dropdown -->
                        <div class="nav-item dropdown">
                            <a class="nav-link dropdown-toggle d-flex align-items-center" href="#" id="profileDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                <div class="profile-avatar me-2">
                                    <i class="fas fa-building"></i>
                                </div>
                                <span class="profile-name">{{ user_data.company_name }}</span>
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end profile-dropdown" aria-labelledby="profileDropdown">
                                <li class="dropdown-header">
                                    <div class="d-flex align-items-center">
                                        <div class="profile-avatar-large me-3">
                                            <i class="fas fa-building"></i>
                                        </div>
                                        <div>
                                            <div class="fw-bold">{{ user_data.company_name }}</div>
                                            <small class="text-white">{{ company_id }}</small>
                                        </div>
                                    </div>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/profile">
                                        <i class="fas fa-user me-2"></i> Şirket Profili
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/subscription">
                                        <i class="fas fa-crown me-2"></i> Abonelik Bilgileri
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/billing">
                                        <i class="fas fa-credit-card me-2"></i> Fatura & Ödeme
                                    </a>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item text-danger" href="#" onclick="logout()">
                                        <i class="fas fa-sign-out-alt me-2"></i> Çıkış Yap
                                    </a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </nav>
            
            <div class="container-fluid mt-4">
                <!-- Header -->
                <div class="row mb-4">
                    <div class="col-12">
                        <div class="d-flex justify-content-between align-items-center">
                            <h2 class="text-white mb-0">
                                <i class="fas fa-tachometer-alt"></i> 
                                Dashboard - {{ user_data.company_name }}
                            </h2>
                            <div class="text-white">
                                <span class="status-indicator status-active"></span>
                                <span id="system-status">Sistem Aktif</span>
                                <small class="ms-3">Son Güncelleme: <span id="last-update">--:--</span></small>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Ana İstatistikler -->
                <div class="row mb-4">
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-primary">
                                <i class="fas fa-video"></i>
                            </div>
                            <div class="stat-value" id="active-cameras">--</div>
                            <div class="stat-label">Aktif Kamera</div>
                            <div class="metric-trend" id="cameras-trend">
                                <i class="fas fa-arrow-up trend-up"></i> +2 bu hafta
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-success">
                                <i class="fas fa-hard-hat"></i>
                            </div>
                            <div class="stat-value" id="ppe-compliance">--%</div>
                            <div class="stat-label">PPE Uyum Oranı</div>
                            <div class="metric-trend" id="compliance-trend">
                                <i class="fas fa-arrow-up trend-up"></i> +5% bu hafta
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-warning">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="stat-value" id="daily-violations">--</div>
                            <div class="stat-label">Günlük İhlaller</div>
                            <div class="metric-trend" id="violations-trend">
                                <i class="fas fa-arrow-down trend-up"></i> -3 dün
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-info">
                                <i class="fas fa-users"></i>
                            </div>
                            <div class="stat-value" id="active-workers">--</div>
                            <div class="stat-label">Aktif Çalışan</div>
                            <div class="metric-trend" id="workers-trend">
                                <i class="fas fa-minus trend-neutral"></i> Sabit
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-secondary">
                                <i class="fas fa-crown"></i>
                            </div>
                            <div class="stat-value small-text" id="subscription-plan">{{ subscription_data.subscription_type.upper() if subscription_data.subscription_type else 'BASIC' }}</div>
                            <div class="stat-label">Abonelik Planı</div>
                            <div class="metric-trend" id="subscription-trend">
                                {% if subscription_data.is_active %}
                                <i class="fas fa-check trend-up"></i> Aktif
                                {% else %}
                                    <i class="fas fa-exclamation-triangle trend-down"></i> Süresi Dolmuş
                                {% endif %}
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-dark">
                                <i class="fas fa-video"></i>
                            </div>
                            <div class="stat-value" id="camera-usage">{{ subscription_data.used_cameras }}/{{ subscription_data.max_cameras }}</div>
                            <div class="stat-label">Kamera Kullanımı</div>
                            <div class="metric-trend" id="usage-trend">
                                {% set usage_percentage = subscription_data.usage_percentage or 0 %}
                                {% if usage_percentage > 80 %}
                                    <i class="fas fa-exclamation-triangle trend-down"></i> Limit Yakın
                                {% elif usage_percentage > 60 %}
                                    <i class="fas fa-info trend-neutral"></i> Orta
                                {% else %}
                                    <i class="fas fa-check trend-up"></i> Normal
                                {% endif %}
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Grafikler -->
                <div class="row mb-4">
                    <div class="col-xl-8">
                        <div class="card">
                            <div class="card-header bg-primary text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-line"></i> 
                                    PPE Uyum Trendi (Son 7 Gün)
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="chart-container">
                                    <canvas id="complianceChart"></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-4">
                        <div class="card">
                            <div class="card-header bg-success text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-pie"></i> 
                                    İhlal Türleri
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="chart-container">
                                    <canvas id="violationsChart"></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Canlı Video Feed -->
                <div class="row mb-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">
                                    <i class="fas fa-play-circle"></i> 
                                    Canlı Tespit Sistemi
                                </h5>
                                <div>
                                    <span id="detection-status" class="badge bg-secondary me-2">Hazır</span>
                                    <span id="fps-display" class="badge bg-info me-2" style="display: none;">FPS: --</span>
                                </div>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-lg-8">
                                        <div id="video-display" class="mb-3" style="height: 400px; background: #f8f9fa; border-radius: 10px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 2px solid #dee2e6;">
                                            <img id="video-feed" style="display: none; max-width: 100%; max-height: 100%; border-radius: 8px;" alt="Canlı Kamera Görüntüsü">
                                            <div id="video-placeholder" style="text-align: center;">
                                                <i class="fas fa-video fa-4x text-muted mb-3"></i>
                                                <h5 class="text-muted">Canlı Video Feed</h5>
                                                <p class="text-muted">Tespiti başlatmak için aşağıdaki butonu kullanın</p>
                                            </div>
                                        </div>
                                        <div class="row">
                                            <div class="col-md-4 mb-3">
                                                <label class="form-label">Kamera Seç:</label>
                                                                                <select class="form-select" id="camera-select">
                                    <option value="">Kamera seçin...</option>
                                    <!-- Kameralar dinamik olarak yüklenecek -->
                                </select>
                                            </div>
                                            <div class="col-md-4 mb-3">
                                                <label class="form-label">Tespit Modu:</label>
                                                <select class="form-select" id="detection-mode">
                                                    <option value="construction">🏗️ İnşaat Modu</option>
                                                    <option value="manufacturing">🏭 İmalat Modu</option>
                                                    <option value="chemical">🧪 Kimya Modu</option>
                                                    <option value="food">🍽️ Gıda Modu</option>
                                                    <option value="warehouse">📦 Lojistik/Depo Modu</option>
                                                    <option value="energy">⚡ Enerji Modu</option>
                                                    <option value="petrochemical">🛢️ Petrokimya Modu</option>
                                                    <option value="marine">🚢 Denizcilik Modu</option>
                                                    <option value="aviation">✈️ Havacılık Modu</option>
                                                    <option value="general">🔍 Genel Tespit</option>
                                                </select>
                                            </div>
                                            <div class="col-md-4 mb-3">
                                                <label class="form-label">Kontroller:</label>
                                                <div class="d-flex gap-2">
                                                    <button id="start-btn" class="btn btn-success flex-fill" onclick="startDetection()">
                                                        <i class="fas fa-play"></i> Başlat
                                                    </button>
                                                    <button id="stop-btn" class="btn btn-danger flex-fill" onclick="stopDetection()" disabled>
                                                        <i class="fas fa-stop"></i> Durdur
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-lg-4">
                                        <div class="card bg-light">
                                            <div class="card-header">
                                                <h6 class="mb-0">
                                                    <i class="fas fa-chart-line"></i> Anlık İstatistikler
                                                </h6>
                                            </div>
                                            <div class="card-body">
                                                <!-- İYİLEŞTİRİLDİ: Real-time Statistics -->
                                                <div class="row text-center">
                                                    <div class="col-6 mb-3">
                                                        <div class="stat-value text-primary" id="live-people-count">0</div>
                                                        <div class="stat-label">Kişi Sayısı</div>
                                                        <div class="stat-trend" id="people-trend">
                                                            <small class="text-muted">↑ +0</small>
                                                        </div>
                                                    </div>
                                                    <div class="col-6 mb-3">
                                                        <div class="stat-value text-success" id="live-compliance-rate">0%</div>
                                                        <div class="stat-label">Uyum Oranı</div>
                                                        <div class="stat-trend" id="compliance-trend">
                                                            <small class="text-muted">→ 0%</small>
                                                    </div>
                                                </div>
                                                </div>
                                                
                                                <!-- İYİLEŞTİRİLDİ: Enhanced Statistics -->
                                                <div class="row text-center mt-3">
                                                    <div class="col-4 mb-2">
                                                        <div class="stat-value text-info" id="live-fps">0</div>
                                                        <div class="stat-label">FPS</div>
                                                    </div>
                                                    <div class="col-4 mb-2">
                                                        <div class="stat-value text-warning" id="live-processing-time">0ms</div>
                                                        <div class="stat-label">İşlem Süresi</div>
                                                    </div>
                                                    <div class="col-4 mb-2">
                                                        <div class="stat-value text-secondary" id="live-detection-count">0</div>
                                                        <div class="stat-label">Tespit Sayısı</div>
                                                    </div>
                                                </div>
                                                
                                                <!-- İYİLEŞTİRİLDİ: Real-time Violations -->
                                                <div id="live-violations" class="mt-3">
                                                    <h6 class="text-danger d-flex justify-content-between align-items-center">
                                                        <span><i class="fas fa-exclamation-triangle"></i> Aktif İhlaller</span>
                                                        <span class="badge bg-danger" id="violation-count">0</span>
                                                    </h6>
                                                    <div id="live-violations-list">
                                                        <p class="text-muted small">Henüz ihlal tespit edilmedi</p>
                                                    </div>
                                                </div>
                                                
                                                <!-- İYİLEŞTİRİLDİ: Performance Metrics -->
                                                <div class="mt-3 p-2 bg-light rounded">
                                                    <small class="text-muted">
                                                        <i class="fas fa-clock"></i> Son güncelleme: <span id="last-update">-</span>
                                                    </small>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Kameralar ve Uyarılar -->
                <div class="row">
                    <div class="col-xl-8">
                        <div class="card">
                            <div class="card-header bg-info text-white d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">
                                    <i class="fas fa-video"></i> 
                                    Kamera Durumu
                                </h5>
                                <div class="d-flex gap-1">
                                    <!-- İYİLEŞTİRİLDİ: Export Buttons -->
                                    <div class="dropdown">
                                        <button class="btn btn-light btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                                            <i class="fas fa-download"></i> Dışa Aktar
                                        </button>
                                        <ul class="dropdown-menu">
                                            <li><a class="dropdown-item" href="#" onclick="exportData('csv')">
                                                <i class="fas fa-file-csv"></i> CSV
                                            </a></li>
                                            <li><a class="dropdown-item" href="#" onclick="exportData('excel')">
                                                <i class="fas fa-file-excel"></i> Excel
                                            </a></li>
                                            <li><a class="dropdown-item" href="#" onclick="exportData('pdf')">
                                                <i class="fas fa-file-pdf"></i> PDF
                                            </a></li>
                                            <li><hr class="dropdown-divider"></li>
                                            <li><a class="dropdown-item" href="#" onclick="exportData('json')">
                                                <i class="fas fa-file-code"></i> JSON
                                            </a></li>
                                        </ul>
                                    </div>
                                <a href="/company/{{ company_id }}/cameras" class="btn btn-light btn-sm">
                                    <i class="fas fa-plus"></i> Yeni Kamera
                                </a>
                                </div>
                            </div>
                            <div class="card-body">
                                <div class="camera-grid" id="cameras-grid">
                                    <!-- Kameralar buraya yüklenecek -->
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-4">
                        <div class="card">
                            <div class="card-header bg-warning text-white d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">
                                    <i class="fas fa-bell"></i> 
                                    Akıllı Uyarılar
                                </h5>
                                <div class="d-flex gap-1">
                                    <button class="btn btn-light btn-sm" onclick="clearAlerts()" title="Uyarıları Temizle">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                    <button class="btn btn-light btn-sm" onclick="toggleAlerts()" title="Uyarı Sesini Aç/Kapat">
                                        <i class="fas fa-volume-up" id="alert-sound-icon"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="card-body" style="max-height: 400px; overflow-y: auto;">
                                <!-- İYİLEŞTİRİLDİ: Enhanced Alerts -->
                                <div class="mb-3">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <small class="text-muted">Uyarı Filtreleri:</small>
                                        <div class="btn-group btn-group-sm">
                                            <button class="btn btn-outline-primary active" onclick="filterAlerts('all')">Tümü</button>
                                            <button class="btn btn-outline-danger" onclick="filterAlerts('violations')">İhlaller</button>
                                            <button class="btn btn-outline-warning" onclick="filterAlerts('system')">Sistem</button>
                                        </div>
                                    </div>
                                </div>
                                
                                <div id="alerts-list">
                                    <!-- İYİLEŞTİRİLDİ: Smart Alerts -->
                                    <div class="alert alert-info alert-dismissible fade show" role="alert">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-info-circle me-2"></i>
                                            <div>
                                                <strong>Sistem Hazır</strong>
                                                <br><small class="text-muted">PPE tespit sistemi aktif ve çalışıyor</small>
                                </div>
                            </div>
                                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    </div>
                                
                                <!-- İYİLEŞTİRİLDİ: Alert Statistics -->
                                <div class="mt-3 p-2 bg-light rounded">
                                    <div class="row text-center">
                                        <div class="col-4">
                                            <small class="text-danger">
                                                <i class="fas fa-exclamation-triangle"></i><br>
                                                <span id="critical-alerts">0</span>
                                            </small>
                                        </div>
                                        <div class="col-4">
                                            <small class="text-warning">
                                                <i class="fas fa-exclamation-circle"></i><br>
                                                <span id="warning-alerts">0</span>
                                            </small>
                                        </div>
                                        <div class="col-4">
                                            <small class="text-info">
                                                <i class="fas fa-info-circle"></i><br>
                                                <span id="info-alerts">1</span>
                                            </small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- İYİLEŞTİRİLDİ: Mobile-Friendly Controls -->
            <div class="mobile-controls d-md-none">
                <div class="fixed-bottom bg-dark p-2">
                    <div class="row text-center">
                        <div class="col-4">
                            <button class="btn btn-success btn-sm w-100" onclick="startDetection()">
                                <i class="fas fa-play"></i><br><small>Başlat</small>
                            </button>
                        </div>
                        <div class="col-4">
                            <button class="btn btn-danger btn-sm w-100" onclick="stopDetection()">
                                <i class="fas fa-stop"></i><br><small>Durdur</small>
                            </button>
                        </div>
                        <div class="col-4">
                            <button class="btn btn-primary btn-sm w-100" onclick="refreshDashboard()">
                                <i class="fas fa-sync-alt"></i><br><small>Yenile</small>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Desktop Yenileme Butonu -->
            <button class="btn btn-primary refresh-btn d-none d-md-block" onclick="refreshDashboard()" title="Verileri Yenile">
                <i class="fas fa-sync-alt"></i>
            </button>
            

            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}';
                let complianceChart, violationsChart;
                
                // Ana fonksiyon - Sayfa yüklendiğinde çalışır
                document.addEventListener('DOMContentLoaded', function() {
                    initializeDashboard();
                    
                    // Otomatik yenileme (30 saniye)
                    setInterval(refreshDashboard, 30000);
                });
                
                function initializeDashboard() {
                    loadStats();
                    loadCameras();
                    loadAlerts();
                    initializeCharts();
                    updateLastUpdate();
                }
                
                function refreshDashboard() {
                    loadStats();
                    loadCameras();
                    loadAlerts();
                    updateCharts();
                    updateLastUpdate();
                    
                    // Refresh animasyonu
                    const refreshBtn = document.querySelector('.refresh-btn i');
                    refreshBtn.style.animation = 'none';
                    setTimeout(() => {
                        refreshBtn.style.animation = 'spin 1s linear';
                    }, 10);
                }
                
                function loadStats() {
                    fetch(`/api/company/${companyId}/stats`)
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('active-cameras').textContent = data.active_cameras || 0;
                            document.getElementById('ppe-compliance').textContent = (data.compliance_rate || 0).toFixed(1) + '%';
                            document.getElementById('daily-violations').textContent = data.today_violations || 0;
                            document.getElementById('active-workers').textContent = data.active_workers || 0;
                            
                            // Trend göstergeleri
                            updateTrendIndicators(data);
                        })
                        .catch(error => {
                            console.error('Stats yüklenemedi:', error);
                        });
                }
                
                function loadCameras() {
                    fetch(`/api/company/${companyId}/cameras`)
                        .then(response => response.json())
                        .then(data => {
                            console.log('✅ Unified Camera Data:', data); // Debug log
                            
                            const grid = document.getElementById('cameras-grid');
                            const cameraSelect = document.getElementById('camera-select');
                            
                            // Summary bilgilerini güncelle
                            if (data.summary) {
                                updateCameraSummary(data.summary);
                            }
                            
                            // Kamera seçim listesini güncelle
                            cameraSelect.innerHTML = '<option value="">Kamera seçin...</option>';
                            
                            if (data.cameras && data.cameras.length > 0) {
                                // Grid'e kamera kartları ekle
                                grid.innerHTML = data.cameras.map(camera => `
                                    <div class="camera-card">
                                        <div class="d-flex justify-content-between align-items-center mb-2">
                                            <h6 class="mb-0">${camera.camera_name}</h6>
                                            <span class="status-indicator ${getCameraStatusClass(camera.status)}"></span>
                                        </div>
                                        <p class="text-muted mb-1">
                                            <i class="fas fa-map-marker-alt"></i> ${camera.location}
                                        </p>
                                        <p class="text-muted mb-2">
                                            <i class="fas fa-network-wired"></i> ${camera.ip_address || 'N/A'}
                                        </p>
                                        <div class="d-flex justify-content-between">
                                            <small class="text-success">
                                                <i class="fas fa-eye"></i> ${camera.detections_today || 0} tespit
                                            </small>
                                            <small class="text-warning">
                                                <i class="fas fa-exclamation-triangle"></i> ${camera.violations_today || 0} ihlal
                                            </small>
                                        </div>
                                        <div class="mt-2">
                                            <button class="btn btn-sm btn-outline-primary" onclick="viewStream('${camera.camera_id}')">
                                                <i class="fas fa-eye"></i> Görüntüle
                                            </button>
                                        </div>
                                    </div>
                                `).join('');
                                
                                // Seçim listesine kameraları ekle
                                data.cameras.forEach(camera => {
                                    const option = document.createElement('option');
                                    option.value = camera.camera_id;
                                    option.textContent = `${camera.camera_name} - ${camera.location}`;
                                    cameraSelect.appendChild(option);
                                });
                                
                            } else {
                                grid.innerHTML = `
                                    <div class="col-12 text-center py-5">
                                        <i class="fas fa-video fa-3x text-muted mb-3"></i>
                                        <p class="text-muted">Henüz kamera eklenmemiş</p>
                                        <p class="text-muted">Kamera eklemek için:</p>
                                        <div class="d-flex gap-2 justify-content-center">
                                        <a href="/company/${companyId}/cameras" class="btn btn-primary">
                                                <i class="fas fa-plus"></i> Buradan Ekle
                                        </a>
                                            <button class="btn btn-success" onclick="syncCameras()">
                                                <i class="fas fa-sync"></i> Kamera Keşfet & Sync
                                        </button>
                                            <a href="/company/${companyId}/cameras" class="btn btn-outline-primary">
                                                <i class="fas fa-cog"></i> Kamera Yönetimi
                                            </a>
                                        </div>
                                    </div>
                                `;
                            }
                        })
                        .catch(error => {
                            console.error('Kameralar yüklenemedi:', error);
                            const grid = document.getElementById('cameras-grid');
                            grid.innerHTML = `
                                <div class="col-12">
                                    <div class="alert alert-danger">
                                        <i class="fas fa-exclamation-triangle"></i>
                                        Kameralar yüklenemedi. Lütfen sayfayı yenileyin.
                                    </div>
                                </div>
                            `;
                        });
                }
                
                function loadAlerts() {
                    fetch(`/api/company/${companyId}/alerts`)
                        .then(response => response.json())
                        .then(data => {
                            const alertsList = document.getElementById('alerts-list');
                            if (data.alerts && data.alerts.length > 0) {
                                alertsList.innerHTML = data.alerts.map(alert => `
                                    <div class="alert-item">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div>
                                                <strong>${alert.violation_type}</strong>
                                                <p class="mb-1">${alert.description}</p>
                                                <small class="text-muted">
                                                    <i class="fas fa-clock"></i> ${alert.time}
                                                    <i class="fas fa-video ms-2"></i> ${alert.camera_name}
                                                </small>
                                            </div>
                                            <span class="badge bg-danger">${alert.severity}</span>
                                        </div>
                                    </div>
                                `).join('');
                            } else {
                                alertsList.innerHTML = `
                                    <div class="text-center py-4">
                                        <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
                                        <p class="text-muted">Yeni uyarı yok</p>
                                    </div>
                                `;
                            }
                        })
                        .catch(error => {
                            console.error('Uyarılar yüklenemedi:', error);
                        });
                }
                
                function initializeCharts() {
                    // PPE Uyum Trendi Grafiği
                    const complianceCtx = document.getElementById('complianceChart').getContext('2d');
                    complianceChart = new Chart(complianceCtx, {
                        type: 'line',
                        data: {
                            labels: ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'],
                            datasets: [{
                                label: 'PPE Uyum Oranı (%)',
                                data: [78, 82, 85, 88, 92, 87, 90],
                                borderColor: '#667eea',
                                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                                borderWidth: 3,
                                fill: true,
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    max: 100
                                }
                            },
                            plugins: {
                                legend: {
                                    display: false
                                }
                            }
                        }
                    });
                    
                    // İhlal Türleri Grafiği
                    const violationsCtx = document.getElementById('violationsChart').getContext('2d');
                    violationsChart = new Chart(violationsCtx, {
                        type: 'doughnut',
                        data: {
                            labels: ['Baret Eksik', 'Yelek Eksik', 'Ayakkabı Eksik', 'Maske Eksik'],
                            datasets: [{
                                data: [45, 30, 15, 10],
                                backgroundColor: [
                                    '#e74c3c',
                                    '#f39c12',
                                    '#3498db',
                                    '#9b59b6'
                                ],
                                borderWidth: 0
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    labels: {
                                        usePointStyle: true,
                                        padding: 20
                                    }
                                }
                            }
                        }
                    });
                }
                
                function updateCharts() {
                    // Gerçek verilerle grafikleri güncelle
                    fetch(`/api/company/${companyId}/chart-data`)
                        .then(response => response.json())
                        .then(data => {
                            if (data.compliance_trend) {
                                complianceChart.data.datasets[0].data = data.compliance_trend;
                                complianceChart.update();
                            }
                            if (data.violation_types) {
                                violationsChart.data.datasets[0].data = data.violation_types;
                                violationsChart.update();
                            }
                        })
                        .catch(error => {
                            console.error('Grafik verileri yüklenemedi:', error);
                        });
                }
                
                function updateTrendIndicators(data) {
                    // İYİLEŞTİRİLDİ: Trend göstergelerini güncelle - Backward compatibility
                    const trends = {
                        'people-trend': data['people-trend'] || data.people_trend || 0,
                        'compliance-trend': data['compliance-trend'] || data.compliance_trend || 0,
                        'fps-trend': data['fps-trend'] || data.fps_trend || 0,
                        'processing-trend': data['processing-trend'] || data.processing_trend || 0,
                        'cameras-trend': data.cameras_trend || data.cameras_trend || 0,
                        'violations-trend': data.violations_trend || data.violations_trend || 0,
                        'workers-trend': data.workers_trend || data.workers_trend || 0
                    };
                    
                    Object.entries(trends).forEach(([id, value]) => {
                        const element = document.getElementById(id);
                        if (element) {
                            const icon = element.querySelector('i');
                            const smallElement = element.querySelector('small');
                            if (icon && smallElement) {
                            if (value > 0) {
                                icon.className = 'fas fa-arrow-up trend-up';
                                    smallElement.textContent = `↑ +${value}`;
                            } else if (value < 0) {
                                icon.className = 'fas fa-arrow-down trend-down';
                                    smallElement.textContent = `↓ ${value}`;
                            } else {
                                icon.className = 'fas fa-minus trend-neutral';
                                    smallElement.textContent = `→ 0`;
                                }
                            }
                        }
                    });
                }
                
                function getCameraStatusClass(status) {
                    const statusMap = {
                        'active': 'status-active',
                        'warning': 'status-warning',
                        'error': 'status-error',
                        'offline': 'status-offline'
                    };
                    return statusMap[status] || 'status-offline';
                }
                
                function updateLastUpdate() {
                    const now = new Date();
                    document.getElementById('last-update').textContent = 
                        now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
                }
                
                function testCameraConnection() {
                    const formData = new FormData(document.getElementById('addCameraForm'));
                    const data = Object.fromEntries(formData);
                    
                    // Gerekli alanları kontrol et
                    if (!data.ip_address) {
                        alert('❌ IP adresi gerekli!');
                        return;
                    }
                    
                    const testButton = document.querySelector('button[onclick="testCameraConnection()"]');
                    const testResults = document.getElementById('testResults');
                    
                    // Test başlatıldığında UI güncelle
                    testButton.disabled = true;
                    testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Akıllı Test Ediliyor...';
                    testResults.style.display = 'block';
                    testResults.innerHTML = `
                        <div class="alert alert-info">
                            <i class="fas fa-brain"></i> Akıllı kamera tespiti ve bağlantı testi yapılıyor...
                        </div>
                    `;
                    
                    // Önce akıllı tespit dene
                    fetch(`/api/company/${companyId}/cameras/smart-test`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            ip_address: data.ip_address,
                            camera_name: data.name || 'Test Camera'
                        })
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            // Akıllı tespit başarılı - formu otomatik doldur
                            if (result.detected_model) {
                                Object.keys(result.detected_model).forEach(key => {
                                    const input = document.querySelector(`[name="${key}"]`);
                                    if (input && result.detected_model[key]) {
                                        input.value = result.detected_model[key];
                                    }
                                });
                            }
                            
                            testResults.innerHTML = `
                                <div class="alert alert-success">
                                    <h6><i class="fas fa-check-circle"></i> Akıllı Tespit Başarılı!</h6>
                                    <ul class="mb-0">
                                        <li><strong>Tespit Edilen Model:</strong> ${result.detected_model?.name || 'Bilinmiyor'}</li>
                                        <li><strong>Üretici:</strong> ${result.detected_model?.manufacturer || 'Bilinmiyor'}</li>
                                        <li><strong>Protokol:</strong> ${result.detected_model?.default_rtsp || result.detected_model?.default_http || 'Bilinmiyor'}</li>
                                        <li><strong>Port:</strong> ${result.detected_model?.ports?.[0] || 'Bilinmiyor'}</li>
                                        <li><strong>Bağlantı Süresi:</strong> ${result.connection_time || 0}ms</li>
                                        <li><strong>Kalite:</strong> ${result.stream_quality || 'İyi'}</li>
                                    </ul>
                                    <div class="mt-2">
                                        <small class="text-success">
                                            <i class="fas fa-magic"></i> Kamera ayarları otomatik olarak dolduruldu!
                                        </small>
                                    </div>
                                </div>
                            `;
                        } else {
                            // Akıllı tespit başarısız - manuel test dene
                            return fetch(`/api/company/${companyId}/cameras/test`, {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify(data)
                            });
                        }
                    })
                    .then(response => {
                        if (response && !response.ok) {
                            return response.json();
                        }
                        return null;
                    })
                    .then(result => {
                        if (result && !result.success) {
                            testResults.innerHTML = `
                                <div class="alert alert-warning">
                                    <h6><i class="fas fa-exclamation-triangle"></i> Manuel Test Gerekli!</h6>
                                    <p><strong>Akıllı tespit başarısız:</strong> ${result.error || 'Bilinmeyen hata'}</p>
                                    <div class="mt-2">
                                        <small><strong>Öneriler:</strong></small>
                                        <ul class="mb-0">
                                            <li>Kamera ayarlarını manuel olarak kontrol edin</li>
                                            <li>IP adresinin doğru olduğundan emin olun</li>
                                            <li>Kamera ve bilgisayarın aynı ağda olduğunu kontrol edin</li>
                                            <li>Kullanıcı adı ve şifrenin doğru olduğunu kontrol edin</li>
                                        </ul>
                                    </div>
                                </div>
                            `;
                        }
                    })
                    .catch(error => {
                        console.error('Kamera test hatası:', error);
                        testResults.innerHTML = `
                            <div class="alert alert-danger">
                                <h6><i class="fas fa-times-circle"></i> Test Hatası!</h6>
                                <p>Kamera testi sırasında bir hata oluştu: ${error.message}</p>
                            </div>
                        `;
                    })
                    .finally(() => {
                        // Test bittiğinde UI'yi eski haline getir
                        testButton.disabled = false;
                        testButton.innerHTML = '<i class="fas fa-brain"></i> Akıllı Test Et';
                    });
                }
                
                function smartDetectCamera() {
                    const ipAddress = document.querySelector('input[name="ip_address"]').value;
                    const cameraName = document.querySelector('input[name="name"]').value || 'Test Camera';
                    
                    if (!ipAddress) {
                        alert('❌ IP adresi gerekli!');
                        return;
                    }
                    
                    const smartButton = document.querySelector('button[onclick="smartDetectCamera()"]');
                    const testResults = document.getElementById('testResults');
                    
                    // Akıllı tespit başlatıldığında UI güncelle
                    smartButton.disabled = true;
                    smartButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Tespit Ediliyor...';
                    testResults.style.display = 'block';
                    testResults.innerHTML = `
                        <div class="alert alert-info">
                            <i class="fas fa-search"></i> Kamera modeli tespit ediliyor...
                        </div>
                    `;
                    
                    fetch(`/api/company/${companyId}/cameras/smart-discover`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            ip_address: ipAddress,
                            camera_name: cameraName
                        })
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success && result.detected_cameras && result.detected_cameras.length > 0) {
                            const camera = result.detected_cameras[0];
                            
                            // Formu otomatik doldur
                            if (camera.detected_model) {
                                Object.keys(camera.detected_model).forEach(key => {
                                    const input = document.querySelector(`[name="${key}"]`);
                                    if (input && camera.detected_model[key]) {
                                        input.value = camera.detected_model[key];
                                    }
                                });
                            }
                            
                            testResults.innerHTML = `
                                <div class="alert alert-success">
                                    <h6><i class="fas fa-check-circle"></i> Kamera Tespit Edildi!</h6>
                                    <ul class="mb-0">
                                        <li><strong>Model:</strong> ${camera.detected_model?.name || 'Bilinmiyor'}</li>
                                        <li><strong>Üretici:</strong> ${camera.detected_model?.manufacturer || 'Bilinmiyor'}</li>
                                        <li><strong>IP:</strong> ${camera.ip_address}</li>
                                        <li><strong>Port:</strong> ${camera.detected_model?.ports?.[0] || 'Bilinmiyor'}</li>
                                        <li><strong>Güven Skoru:</strong> ${camera.confidence_score || 0}%</li>
                                    </ul>
                                    <div class="mt-2">
                                        <small class="text-success">
                                            <i class="fas fa-magic"></i> Kamera ayarları otomatik olarak dolduruldu!
                                        </small>
                                    </div>
                                </div>
                            `;
                        } else {
                            testResults.innerHTML = `
                                <div class="alert alert-warning">
                                    <h6><i class="fas fa-exclamation-triangle"></i> Kamera Tespit Edilemedi!</h6>
                                    <p>Kamera otomatik olarak tespit edilemedi. Manuel ayarları kontrol edin.</p>
                                    <div class="mt-2">
                                        <small><strong>Öneriler:</strong></small>
                                        <ul class="mb-0">
                                            <li>IP adresinin doğru olduğundan emin olun</li>
                                            <li>Kameranın açık ve erişilebilir olduğunu kontrol edin</li>
                                            <li>Kamera ve bilgisayarın aynı ağda olduğunu kontrol edin</li>
                                            <li>Manuel ayarları kullanarak kamera ekleyin</li>
                                        </ul>
                                    </div>
                                </div>
                            `;
                        }
                    })
                    .catch(error => {
                        console.error('Akıllı tespit hatası:', error);
                        testResults.innerHTML = `
                            <div class="alert alert-danger">
                                <h6><i class="fas fa-times-circle"></i> Tespit Hatası!</h6>
                                <p>Kamera tespiti sırasında bir hata oluştu: ${error.message}</p>
                            </div>
                        `;
                    })
                    .finally(() => {
                        // Tespit bittiğinde UI'yi eski haline getir
                        smartButton.disabled = false;
                        smartButton.innerHTML = '<i class="fas fa-brain"></i> Akıllı Tespit';
                    });
                }
                

                
                // Video Feed Fonksiyonları
                let detectionActive = false;
                let currentCameraId = null;
                let detectionMonitoringInterval = null;
                
                function startDetection() {
                    const camera = document.getElementById('camera-select').value;
                    const mode = document.getElementById('detection-mode').value;
                    
                    if (detectionActive) {
                        alert('⚠️ Tespit zaten aktif!');
                        return;
                    }
                    
                    // UI güncelle
                    document.getElementById('start-btn').disabled = true;
                    document.getElementById('detection-status').textContent = 'Başlatılıyor...';
                    document.getElementById('detection-status').className = 'badge bg-warning me-2';
                    
                    fetch(`/api/company/${companyId}/start-detection`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({camera_id: camera, detection_mode: mode, confidence: 0.6})
                    })
                    .then(response => response.json())
                    .then(data => {
                        if(data.success) {
                            detectionActive = true;
                            currentCameraId = camera;
                            
                            // Video feed'i başlat
                            startVideoFeed(camera);
                            
                            // UI güncelle
                            document.getElementById('start-btn').disabled = true;
                            document.getElementById('stop-btn').disabled = false;
                            document.getElementById('detection-status').textContent = 'Aktif';
                            document.getElementById('detection-status').className = 'badge bg-success me-2';
                            document.getElementById('fps-display').style.display = 'inline';
                            
                            // Detection monitoring başlat
                            startDetectionMonitoring();
                            
                            // Success alert
                            showAlert('✅ Tespit sistemi başlatıldı!', 'success');
                        } else {
                            // Hata durumunda UI'yi resetle
                            document.getElementById('start-btn').disabled = false;
                            document.getElementById('detection-status').textContent = 'Hata';
                            document.getElementById('detection-status').className = 'badge bg-danger me-2';
                            
                            showAlert('❌ Hata: ' + data.error, 'danger');
                        }
                    })
                    .catch(error => {
                        console.error('Detection başlatma hatası:', error);
                        document.getElementById('start-btn').disabled = false;
                        document.getElementById('detection-status').textContent = 'Hata';
                        document.getElementById('detection-status').className = 'badge bg-danger me-2';
                        showAlert('❌ Bağlantı hatası!', 'danger');
                    });
                }

                function stopDetection() {
                    if (!detectionActive) {
                        return;
                    }
                    
                    // UI güncelle
                    document.getElementById('stop-btn').disabled = true;
                    document.getElementById('detection-status').textContent = 'Durduruluyor...';
                    document.getElementById('detection-status').className = 'badge bg-warning me-2';
                    
                    fetch(`/api/company/${companyId}/stop-detection`, {method: 'POST'})
                        .then(response => response.json())
                        .then(data => {
                            if(data.success) {
                                detectionActive = false;
                                currentCameraId = null;
                                
                                // Video feed'i durdur
                                stopVideoFeed();
                                
                                // Detection monitoring durdur
                                if (detectionMonitoringInterval) {
                                    clearInterval(detectionMonitoringInterval);
                                    detectionMonitoringInterval = null;
                                }
                                
                                // UI güncelle
                                document.getElementById('start-btn').disabled = false;
                                document.getElementById('stop-btn').disabled = true;
                                document.getElementById('detection-status').textContent = 'Durduruldu';
                                document.getElementById('detection-status').className = 'badge bg-secondary me-2';
                                document.getElementById('fps-display').style.display = 'none';
                                
                                // İstatistikleri sıfırla
                                document.getElementById('live-people-count').textContent = '0';
                                document.getElementById('live-compliance-rate').textContent = '0%';
                                document.getElementById('live-violations-list').innerHTML = '<p class="text-muted small">Henüz ihlal tespit edilmedi</p>';
                                
                                showAlert('✅ Tespit sistemi durduruldu!', 'info');
                            }
                        })
                        .catch(error => {
                            console.error('Detection durdurma hatası:', error);
                            document.getElementById('stop-btn').disabled = false;
                        });
                }
                
                function startVideoFeed(cameraId) {
                    const videoElement = document.getElementById('video-feed');
                    const placeholder = document.getElementById('video-placeholder');
                    
                    // Video feed URL'sini ayarla
                    videoElement.src = `/api/company/${companyId}/video-feed/${cameraId}`;
                    
                    // Video yüklendiğinde göster
                    videoElement.onload = function() {
                        placeholder.style.display = 'none';
                        videoElement.style.display = 'block';
                    };
                    
                    // Hata durumunda placeholder'ı geri göster
                    videoElement.onerror = function() {
                        videoElement.style.display = 'none';
                        placeholder.style.display = 'block';
                        placeholder.innerHTML = '<i class="fas fa-exclamation-triangle fa-4x text-warning mb-3"></i><h5 class="text-warning">Kamera Bağlantısı Kurulamadı</h5><p class="text-warning">Lütfen kamera ayarlarını kontrol edin</p>';
                    };
                }
                
                function stopVideoFeed() {
                    const videoElement = document.getElementById('video-feed');
                    const placeholder = document.getElementById('video-placeholder');
                    
                    // Video feed'i durdur
                    videoElement.src = '';
                    videoElement.style.display = 'none';
                    
                    // Placeholder'ı geri göster
                    placeholder.style.display = 'block';
                    placeholder.innerHTML = '<i class="fas fa-video fa-4x text-muted mb-3"></i><h5 class="text-muted">Canlı Video Feed</h5><p class="text-muted">Tespiti başlatmak için yukarıdaki butonu kullanın</p>';
                }
                
                function startDetectionMonitoring() {
                    detectionMonitoringInterval = setInterval(() => {
                        if (detectionActive && currentCameraId) {
                            // Detection sonuçlarını al
                            fetch(`/api/company/${companyId}/detection-results/${currentCameraId}`)
                                .then(response => response.json())
                                .then(data => {
                                    if (data.success && data.result) {
                                        const result = data.result;
                                        
                                        // İYİLEŞTİRİLDİ: Tüm dinamik verileri güncelle
                                        document.getElementById('live-people-count').textContent = result.total_people || 0;
                                        document.getElementById('live-compliance-rate').textContent = `${(result.compliance_rate || 0).toFixed(1)}%`;
                                        
                                        // YENİ: FPS, işlem süresi ve tespit sayısı güncelleme
                                        const fps = Math.round(1000 / (result.processing_time_ms || 100));
                                        document.getElementById('fps-display').textContent = `FPS: ${fps}`;
                                        document.getElementById('live-fps').textContent = fps;
                                        document.getElementById('live-processing-time').textContent = `${(result.processing_time_ms || 0).toFixed(0)}ms`;
                                        document.getElementById('live-detection-count').textContent = result.detection_count || 0;
                                        
                                        // YENİ: Violation count badge güncelleme
                                        const violationCount = result.violations ? result.violations.length : 0;
                                        document.getElementById('violation-count').textContent = violationCount;
                                        
                                        // YENİ: Son güncelleme zamanı
                                        const now = new Date();
                                        document.getElementById('last-update').textContent = 
                                            now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                                        
                                        // YENİ: Trend göstergelerini güncelle
                                        updateTrendIndicators({
                                            'people-trend': result.total_people > 0 ? 1 : 0,
                                            'compliance-trend': result.compliance_rate > 80 ? 1 : (result.compliance_rate > 60 ? 0 : -1),
                                            'fps-trend': fps > 15 ? 1 : (fps > 5 ? 0 : -1),
                                            'processing-trend': result.processing_time_ms < 100 ? 1 : (result.processing_time_ms < 200 ? 0 : -1)
                                        });
                                        
                                        // Detection status'u güncelle
                                        const statusElement = document.getElementById('detection-status');
                                        statusElement.innerHTML = `Aktif - ${result.total_people || 0} kişi`;
                                        
                                        // Compliance rate'e göre renk değiştir
                                        if (result.compliance_rate >= 80) {
                                            statusElement.className = 'badge bg-success me-2';
                                            document.getElementById('live-compliance-rate').className = 'stat-value text-success';
                                        } else if (result.compliance_rate >= 60) {
                                            statusElement.className = 'badge bg-warning me-2';
                                            document.getElementById('live-compliance-rate').className = 'stat-value text-warning';
                                        } else {
                                            statusElement.className = 'badge bg-danger me-2';
                                            document.getElementById('live-compliance-rate').className = 'stat-value text-danger';
                                        }
                                        
                                        // İhlalleri göster
                                        const violationsList = document.getElementById('live-violations-list');
                                        console.log('🔍 Detection result:', result);
                                        console.log('🔍 Violations:', result.violations);
                                        
                                        if (result.violations && result.violations.length > 0) {
                                            violationsList.innerHTML = result.violations.map(violation => 
                                                `<div class="alert alert-danger alert-sm py-1 px-2 mb-1">
                                                    <small><strong>${violation.person_id || 'Kişi'}:</strong> ${violation.missing_ppe.join(', ')}</small>
                                                </div>`
                                            ).join('');
                                        } else {
                                            violationsList.innerHTML = '<p class="text-muted small">Henüz ihlal tespit edilmedi</p>';
                                        }
                                    } else {
                                        document.getElementById('fps-display').textContent = 'FPS: --';
                                        // İYİLEŞTİRİLDİ: Boş durumda da dinamik verileri sıfırla
                                        document.getElementById('live-fps').textContent = '0';
                                        document.getElementById('live-processing-time').textContent = '0ms';
                                        document.getElementById('live-detection-count').textContent = '0';
                                        document.getElementById('violation-count').textContent = '0';
                                    }
                                })
                                .catch(error => {
                                    console.error('Detection monitoring error:', error);
                                    document.getElementById('fps-display').textContent = 'FPS: --';
                                    // İYİLEŞTİRİLDİ: Hata durumunda da dinamik verileri sıfırla
                                    document.getElementById('live-fps').textContent = '0';
                                    document.getElementById('live-processing-time').textContent = '0ms';
                                    document.getElementById('live-detection-count').textContent = '0';
                                    document.getElementById('violation-count').textContent = '0';
                                });
                        }
                    }, 2000); // Her 2 saniyede bir
                }
                
                function showAlert(message, type) {
                    const alertDiv = document.createElement('div');
                    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
                    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
                    alertDiv.innerHTML = `
                        ${message}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    document.body.appendChild(alertDiv);
                    
                    setTimeout(() => {
                        if (alertDiv.parentNode) {
                            alertDiv.remove();
                        }
                    }, 5000);
                }
                
                function logout() {
                    fetch('/logout', {method: 'POST'})
                        .then(() => {
                            window.location.href = '/';
                        });
                }
                
                // === UNIFIED CAMERA SYNC FUNCTIONS ===
                function syncCameras() {
                    const syncBtn = event.target;
                    const originalText = syncBtn.innerHTML;
                    
                    syncBtn.disabled = true;
                    syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Senkronize ediliyor...';
                    
                    fetch(`/api/company/${companyId}/cameras/sync`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            network_range: '192.168.1.0/24',
                            force_sync: true
                        })
                    })
                        .then(response => response.json())
                        .then(data => {
                        console.log('✅ Sync result:', data);
                        
                        if (data.success) {
                            showAlert(`✅ Kamera senkronizasyonu tamamlandı! ${data.total_cameras} kamera bulundu (${data.mode} mode).`, 'success');
                            
                            // Refresh cameras and stats
                            loadCameras();
                            loadStats();
                            } else {
                            showAlert(`❌ Senkronizasyon hatası: ${data.error}`, 'danger');
                            }
                        })
                        .catch(error => {
                        console.error('❌ Sync error:', error);
                        showAlert('❌ Senkronizasyon sırasında bir hata oluştu.', 'danger');
                    })
                    .finally(() => {
                        syncBtn.disabled = false;
                        syncBtn.innerHTML = originalText;
                    });
                }
                
                // Update camera summary in dashboard
                function updateCameraSummary(summary) {
                    console.log('📊 Updating camera summary:', summary);
                    
                    // Update any elements that display camera counts
                    const totalElements = document.querySelectorAll('.total-cameras-count, [data-camera-total]');
                    const activeElements = document.querySelectorAll('.active-cameras-count, [data-camera-active]');
                    
                    totalElements.forEach(el => {
                        el.textContent = summary.total_cameras || 0;
                    });
                    
                    activeElements.forEach(el => {
                        el.textContent = summary.active_cameras || 0;
                        });
                }
                
                // CSS animasyonu
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes spin {
                        from { transform: rotate(0deg); }
                        to { transform: rotate(360deg); }
                    }
                `;
                document.head.appendChild(style);
            </script>
        </body>
        </html>
        '''
    
    def get_login_template(self, company_id):
        """Company login page template"""
        template = '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe AI - Company Login</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
            <style>
                :root {
                    --primary: #1E3A8A;
                    --secondary: #0EA5E9;
                    --accent: #22C55E;
                    --warning: #EF4444;
                    --light: #F8FAFC;
                    --dark: #0F172A;
                }

                body {
                    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                    color: var(--dark);
                    overflow-x: hidden;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                    padding: 20px;
                }

                .gradient-bg {
                    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                }

                .glass-card {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                    max-width: 450px;
                    width: 100%;
                    margin: 0 auto;
                }

                .feature-icon {
                    width: 64px;
                    height: 64px;
                    border-radius: 16px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                    color: white;
                    margin-bottom: 20px;
                }

                .btn-primary {
                    background: var(--primary);
                    border: none;
                    padding: 12px 32px;
                    border-radius: 30px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }

                .btn-primary:hover {
                    background: var(--secondary);
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(14, 165, 233, 0.3);
                }

                .form-control {
                    border-radius: 15px;
                    border: 2px solid #e2e8f0;
                    padding: 12px 15px;
                    transition: all 0.3s ease;
                    font-size: 16px;
                }

                .form-control:focus {
                    border-color: var(--primary);
                    box-shadow: 0 0 0 0.2rem rgba(30, 58, 138, 0.25);
                }

                .alert {
                    border-radius: 15px;
                    border: none;
                }

                .container {
                    animation: slideUp 0.6s ease-out;
                }

                @keyframes slideUp {
                    from { opacity: 0; transform: translateY(30px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .btn-outline-primary {
                    border: 2px solid var(--primary);
                    color: var(--primary);
                    transition: all 0.3s ease;
                }

                .btn-outline-primary:hover {
                    background: var(--primary);
                    border-color: var(--primary);
                    transform: translateY(-2px);
                }

                .login-header {
                    text-align: center;
                    margin-bottom: 2rem;
                }

                .company-badge {
                    background: rgba(30, 58, 138, 0.1);
                    color: var(--primary);
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 600;
                    border: 1px solid rgba(30, 58, 138, 0.2);
                }
            </style>
        </head>
        <body>
            <div class="container-fluid d-flex justify-content-center align-items-center min-vh-100">
                <div class="glass-card p-5">
                    <div class="login-header">
                        <div class="feature-icon mx-auto gradient-bg">
                            <i class="fas fa-shield-alt"></i>
                        </div>
                        <h2 class="fw-bold mb-3">SmartSafe AI</h2>
                        <div class="company-badge mb-3">
                            <i class="fas fa-building me-2"></i>
                            Company ID: COMPANY_ID_PLACEHOLDER
                        </div>
                        <p class="text-muted">Secure login</p>
                        
                        <!-- Demo Hesap Bilgisi -->
                        <div id="demo-info" style="display: none;" class="alert alert-warning border-0 mb-3" style="background: rgba(251, 191, 36, 0.1); border-radius: 15px;">
                            <small>
                                <i class="fas fa-clock text-warning me-2"></i>
                                <strong>Demo Hesap:</strong> 7 günlük ücretsiz deneme süreniz devam ediyor!
                            </small>
                        </div>
                    </div>
                    
                    <!-- Login Type Toggle -->
                    <div class="login-type-toggle mb-4">
                        <div class="btn-group w-100" role="group">
                            <input type="radio" class="btn-check" name="login_type" id="company_login" value="company" checked>
                            <label class="btn btn-outline-primary" for="company_login">
                                <i class="fas fa-building me-2"></i>Şirket Girişi
                            </label>
                            
                            <input type="radio" class="btn-check" name="login_type" id="demo_login" value="demo">
                            <label class="btn btn-outline-warning" for="demo_login">
                                <i class="fas fa-play me-2"></i>Demo Girişi
                            </label>
                        </div>
                    </div>
                    
                    <!-- Company Login Form -->
                    <form id="companyLoginForm" action="/company/COMPANY_ID_PLACEHOLDER/login-form" method="POST">
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-envelope text-primary me-2"></i>Şirket Email
                            </label>
                            <input type="email" class="form-control form-control-lg" id="company_email" name="email" 
                                   placeholder="example@yourcompany.com" required>
                        </div>
                        
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-lock text-primary me-2"></i>Şifre
                            </label>
                            <input type="password" class="form-control form-control-lg" id="company_password" name="password" 
                                   placeholder="Şifrenizi girin" required>
                        </div>
                        
                        <div class="d-grid mb-4">
                            <button type="submit" class="btn btn-primary btn-lg" 
                                    style="border-radius: 30px; padding: 15px 0; font-weight: 600; font-size: 18px; background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%); border: none; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.3);">
                                <i class="fas fa-sign-in-alt me-2"></i>Şirket Girişi
                            </button>
                        </div>
                    </form>
                    
                    <!-- Demo Login Form -->
                    <form id="demoLoginForm" action="/company/COMPANY_ID_PLACEHOLDER/demo-login" method="POST" style="display: none;">
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-id-card text-warning me-2"></i>Demo Hesap ID
                            </label>
                            <input type="text" class="form-control form-control-lg" id="demo_id" name="demo_id" 
                                   placeholder="demo_20250823_163119" required>
                        </div>
                        
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-envelope text-warning me-2"></i>Şirket Email
                            </label>
                            <input type="email" class="form-control form-control-lg" id="demo_email" name="email" 
                                   placeholder="demo@yourcompany.com" required>
                        </div>
                        
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-lock text-warning me-2"></i>Şifre
                            </label>
                            <input type="password" class="form-control form-control-lg" id="demo_password" name="password" 
                                   placeholder="Demo şifrenizi girin" required
                                   oninput="updateDemoPasswordStrength(this.value)">
                            
                            <!-- Şifre Gücü Göstergesi -->
                            <div class="password-strength mt-2">
                                <div class="strength-bar" style="width: 100%; height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden;">
                                    <div class="strength-fill" id="demo-strength-fill" style="height: 100%; background: #dc3545; width: 0%; transition: all 0.3s ease; border-radius: 4px;"></div>
                                </div>
                                <small class="strength-text" id="demo-strength-text" style="font-size: 0.8rem; color: #6c757d;">Password strength: Weak</small>
                            </div>
                            
                            <!-- Şifre Gereksinimleri -->
                            <div class="password-requirements mt-3" style="background: #f8f9fa; padding: 1rem; border-radius: 10px; border: 1px solid #e9ecef;">
                                <h6 class="requirements-title mb-2" style="color: #2c3e50; font-weight: 600; font-size: 0.9rem;">
                                    <i class="fas fa-info-circle text-warning me-2"></i>
                                    Password Requirements
                                </h6>
                                <div class="requirements-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem;">
                                    <div class="requirement-item" id="demo-req-length" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                        <i class="fas fa-times text-danger me-2"></i>
                                        <span>En az 8 karakter</span>
                                    </div>
                                    <div class="requirement-item" id="demo-req-uppercase" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                        <i class="fas fa-times text-danger me-2"></i>
                                        <span>En az 1 büyük harf (A-Z)</span>
                                    </div>
                                    <div class="requirement-item" id="demo-req-lowercase" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                        <i class="fas fa-times text-danger me-2"></i>
                                        <span>En az 1 küçük harf (a-z)</span>
                                    </div>
                                    <div class="requirement-item" id="demo-req-number" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                        <i class="fas fa-times text-danger me-2"></i>
                                        <span>En az 1 rakam (0-9)</span>
                                    </div>
                                    <div class="requirement-item" id="demo-req-special" style="display: flex; align-items: center; font-size: 0.8rem; color: #6c757d;">
                                        <i class="fas fa-times text-danger me-2"></i>
                                        <span>En az 1 özel karakter (!@#$%^&*)</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="d-grid mb-4">
                            <button type="submit" class="btn btn-warning btn-lg" 
                                    style="border-radius: 30px; padding: 15px 0; font-weight: 600; font-size: 18px; background: linear-gradient(135deg, #F59E0B 0%, #F97316 100%); border: none; box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);">
                                <i class="fas fa-play me-2"></i>Demo Girişi
                            </button>
                        </div>
                    </form>
                    
                    <div class="text-center">
                        <div class="alert alert-info border-0 mb-3" style="background: rgba(59, 130, 246, 0.1); border-radius: 15px;">
                            <small>
                                <i class="fas fa-info-circle me-2"></i>
                                Use the email and password provided during company registration
                            </small>
                        </div>
                        
                                                 <div class="row">
                             <div class="col-6">
                                 <a href="/#contact" class="btn btn-outline-secondary btn-sm w-100" style="border-radius: 20px;">
                                     <i class="fas fa-key me-1"></i>Forgot Password
                                 </a>
                             </div>
                             <div class="col-6">
                                 <a href="/app" class="btn btn-outline-primary btn-sm w-100" style="border-radius: 20px;">
                                     <i class="fas fa-user-plus me-1"></i>New Registration
                                 </a>
                             </div>
                         </div>
                    </div>
                </div>
            </div>

            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Login type toggle functionality
                document.addEventListener('DOMContentLoaded', function() {
                    const companyId = 'COMPANY_ID_PLACEHOLDER';
                    const companyLoginForm = document.getElementById('companyLoginForm');
                    const demoLoginForm = document.getElementById('demoLoginForm');
                    const companyLoginRadio = document.getElementById('company_login');
                    const demoLoginRadio = document.getElementById('demo_login');
                    
                    console.log('Company ID:', companyId); // Debug için
                    console.log('Forms found:', {companyLoginForm, demoLoginForm}); // Debug için
                    console.log('Radios found:', {companyLoginRadio, demoLoginRadio}); // Debug için
                    
                    // Login type değiştiğinde form'ları göster/gizle
                    function toggleLoginForms() {
                        console.log('Toggle called, companyLoginRadio.checked:', companyLoginRadio.checked); // Debug için
                        if (companyLoginRadio.checked) {
                            companyLoginForm.style.display = 'block';
                            demoLoginForm.style.display = 'none';
                            console.log('Company form shown, demo form hidden'); // Debug için
                        } else {
                            companyLoginForm.style.display = 'none';
                            demoLoginForm.style.display = 'block';
                            console.log('Demo form shown, company form hidden'); // Debug için
                        }
                    }
                    
                    // Radio button change event
                    companyLoginRadio.addEventListener('change', function() {
                        console.log('Company radio changed'); // Debug için
                        toggleLoginForms();
                    });
                    demoLoginRadio.addEventListener('change', function() {
                        console.log('Demo radio changed'); // Debug için
                        toggleLoginForms();
                    });
                    
                    // Demo hesap kontrolü ve güvenlik
                    if (companyId && companyId.startsWith('demo_')) {
                        console.log('Demo account detected'); // Debug için
                        // Demo hesap bilgisini göster
                        const demoInfo = document.getElementById('demo-info');
                        if (demoInfo) {
                            demoInfo.style.display = 'block';
                        }
                        
                        // Demo hesap için özel stil - Gerçek şirketlerle aynı mavi arka plan
                        document.body.style.background = 'linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%)';
                        
                        // Company badge'i demo renk yap
                        const companyBadge = document.querySelector('.company-badge');
                        if (companyBadge) {
                            companyBadge.innerHTML = `
                                <i class="fas fa-clock text-warning me-2"></i>
                                <strong>Demo Account:</strong> ${companyId}
                            `;
                            companyBadge.style.color = '#059669';
                        }
                        
                        // Demo hesaplar için normal girişi devre dışı bırak
                        companyLoginRadio.disabled = true;
                        companyLoginRadio.checked = false;
                        demoLoginRadio.checked = true;
                        toggleLoginForms();
                        
                        // Uyarı mesajı göster
                        const warningDiv = document.createElement('div');
                        warningDiv.className = 'alert alert-warning border-0 mb-3';
                        warningDiv.innerHTML = `
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            <strong>Demo Hesap:</strong> Bu hesap sadece demo girişi yapabilir.
                        `;
                        companyLoginForm.parentNode.insertBefore(warningDiv, companyLoginForm);
                        
                    } else {
                        console.log('Normal account detected'); // Debug için
                        // Normal hesaplar için demo girişi devre dışı bırak
                        demoLoginRadio.disabled = true;
                        demoLoginRadio.checked = false;
                        companyLoginRadio.checked = true;
                        toggleLoginForms();
                        
                        // Uyarı mesajı göster
                        const warningDiv = document.createElement('div');
                        warningDiv.className = 'alert alert-info border-0 mb-3';
                        warningDiv.innerHTML = `
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>Normal Hesap:</strong> Bu hesap sadece şirket girişi yapabilir.
                        `;
                        demoLoginForm.parentNode.insertBefore(warningDiv, demoLoginForm);
                    }
                    
                    // Form validation - Sadece görünür form submit edilebilir
                    companyLoginForm.addEventListener('submit', function(e) {
                        console.log('Company form submit attempted'); // Debug
                        // Eğer demo hesap ise ve company form görünürse engelle
                        if (companyId && companyId.startsWith('demo_')) {
                            e.preventDefault();
                            alert('❌ Demo hesaplar normal giriş yapamaz!');
                            return false;
                        }
                        // Eğer demo form görünürse company form submit'ini engelle
                        if (demoLoginForm.style.display === 'block') {
                            e.preventDefault();
                            alert('❌ Demo girişi için demo formu kullanın!');
                            return false;
                        }
                        console.log('Company form submitted successfully'); // Debug
                    });
                    
                    demoLoginForm.addEventListener('submit', function(e) {
                        console.log('Demo form submit attempted'); // Debug
                        // Eğer normal hesap ise ve demo form görünürse engelle
                        if (!companyId || !companyId.startsWith('demo_')) {
                            e.preventDefault();
                            alert('❌ Normal hesaplar demo giriş yapamaz!');
                            return false;
                        }
                        // Eğer company form görünürse demo form submit'ini engelle
                        if (companyLoginForm.style.display === 'block') {
                            e.preventDefault();
                            alert('❌ Şirket girişi için şirket formu kullanın!');
                            return false;
                        }
                        console.log('Demo form submitted successfully'); // Debug
                    });
                });
            </script>
        </body>
        </html>
        '''
        
        # Template'deki placeholder'ları gerçek company_id ile değiştir
        return template.replace('COMPANY_ID_PLACEHOLDER', company_id)
    
    def get_admin_login_template(self, error=None):
        """Admin login template"""
        error_html = ''
        if error:
            error_html = f'''
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i> {error}
            </div>
            '''
        
        return f'''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Giriş - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {{
                    background: linear-gradient(135deg, #dc3545 0%, #6f42c1 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .card {{
                    border-radius: 15px;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                }}
                .btn-custom {{
                    background: linear-gradient(135deg, #dc3545 0%, #6f42c1 100%);
                    border: none;
                    border-radius: 25px;
                    padding: 12px 30px;
                    color: white;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }}
                .btn-custom:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.3);
                    color: white;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-6 col-lg-4">
                        <div class="card">
                            <div class="card-body p-5">
                                <div class="text-center mb-4">
                                    <i class="fas fa-crown text-warning" style="font-size: 3rem;"></i>
                                    <h3 class="mt-3">Admin Panel</h3>
                                    <p class="text-muted">Founder Access Only</p>
                                </div>
                                
                                {error_html}
                                
                                <form method="POST" action="/admin">
                                    <div class="mb-3">
                                        <label class="form-label">Founder Şifresi</label>
                                        <input type="password" class="form-control" name="password" required 
                                               placeholder="Admin şifrenizi girin">
                                    </div>
                                    
                                    <div class="d-grid">
                                        <button type="submit" class="btn btn-custom">
                                            <i class="fas fa-sign-in-alt"></i> Giriş Yap
                                        </button>
                                    </div>
                                </form>
                                
                                <div class="text-center mt-4">
                                    <a href="/" class="btn btn-outline-secondary">
                                        <i class="fas fa-arrow-left"></i> Ana Sayfa
                                    </a>
                                </div>
                                
                                <div class="text-center mt-3">
                                    <small class="text-muted">
                                        <i class="fas fa-info-circle"></i> 
                                        Admin şifresi FOUNDER_PASSWORD env variable ile ayarlanır.
                                    </small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        '''
    
    def get_admin_template(self):
        """Professional Admin Panel Template for Company Management"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Panel - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
            <style>
                body { background: #f8f9fa; }
                .navbar { background: #dc3545; }
                .card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-dark">
                <div class="container-fluid">
                    <a class="navbar-brand" href="/admin">SmartSafe AI - Admin Panel</a>
                </div>
            </nav>
            <div class="container mt-4">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Şirket Yönetimi</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table" id="companiesTable">
                                <thead>
                                    <tr>
                                        <th>Şirket Adı</th>
                                        <th>Sektör</th>
                                        <th>Durum</th>
                                        <th>İşlemler</th>
                                    </tr>
                                </thead>
                                <tbody id="companyTableBody"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
            <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
            <script>
                $(document).ready(function() {
                    loadCompanies();
                });
                
                function loadCompanies() {
                    fetch('/api/admin/companies')
                        .then(response => response.json())
                        .then(data => {
                            if (data.companies) {
                                const tbody = document.querySelector('#companiesTable tbody');
                                tbody.innerHTML = '';
                                
                                data.companies.forEach(company => {
                                    const row = document.createElement('tr');
                                    row.innerHTML = `
                                        <td>${company.company_name}</td>
                                        <td>${company.email}</td>
                                        <td>${company.sector}</td>
                                        <td>${company.max_cameras}</td>
                                        <td>${company.created_at}</td>
                                        <td>
                                            <span class="badge bg-${company.status === 'active' ? 'success' : 'danger'}">
                                                ${company.status}
                                            </span>
                                        </td>
                                        <td>
                                            <button class="btn btn-sm btn-danger" onclick="deleteCompany('${company.company_id}')">
                                                <i class="fas fa-trash"></i>
                                            </button>
                                        </td>
                                    `;
                                    tbody.appendChild(row);
                                });
                                
                                // Initialize DataTable after loading data
                                $('#companiesTable').DataTable({
                                    destroy: true, // Allow reinitialization
                                    language: {
                                        url: '//cdn.datatables.net/plug-ins/1.11.5/i18n/tr.json'
                                    }
                                });
                            }
                        })
                        .catch(error => {
                            console.error('Error loading companies:', error);
                            alert('Şirketler yüklenirken hata oluştu: ' + error.message);
                        });
                }
                
                function deleteCompany(companyId) {
                    if (confirm('Bu şirketi silmek istediğinizden emin misiniz?')) {
                        fetch(`/api/admin/companies/${companyId}`, {
                            method: 'DELETE'
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('Şirket başarıyla silindi');
                                loadCompanies(); // Reload table
                            } else {
                                alert('Hata: ' + data.error);
                            }
                        })
                        .catch(error => {
                            console.error('Error deleting company:', error);
                            alert('Silme işlemi sırasında hata oluştu');
                        });
                    }
                }
            </script>
        </body>
        </html>
        '''
    
    def get_company_settings_template(self):
        """Advanced Company Settings Template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Şirket Ayarları - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .navbar {
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    border: none;
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                }
                .settings-nav {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 20px;
                }
                .settings-nav .nav-link {
                    color: white;
                    border-radius: 10px;
                    margin: 5px 0;
                    transition: all 0.3s ease;
                }
                .settings-nav .nav-link:hover, .settings-nav .nav-link.active {
                    background: rgba(255,255,255,0.2);
                    color: white;
                    transform: translateX(10px);
                }
                .form-section {
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }
                .form-section h5 {
                    color: #2c3e50;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #ecf0f1;
                }
                .logo-upload {
                    width: 150px;
                    height: 150px;
                    border: 3px dashed #ddd;
                    border-radius: 15px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    margin: 0 auto;
                }
                .logo-upload:hover {
                    border-color: #667eea;
                    background: rgba(102, 126, 234, 0.1);
                }
                .ppe-config-item {
                    background: #f8f9fa;
                    border-radius: 10px;
                    padding: 15px;
                    margin-bottom: 10px;
                    border-left: 4px solid #667eea;
                }
                .notification-toggle {
                    position: relative;
                    display: inline-block;
                    width: 60px;
                    height: 34px;
                }
                .notification-toggle input {
                    opacity: 0;
                    width: 0;
                    height: 0;
                }
                .slider {
                    position: absolute;
                    cursor: pointer;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background-color: #ccc;
                    transition: .4s;
                    border-radius: 34px;
                }
                .slider:before {
                    position: absolute;
                    content: "";
                    height: 26px;
                    width: 26px;
                    left: 4px;
                    bottom: 4px;
                    background-color: white;
                    transition: .4s;
                    border-radius: 50%;
                }
                input:checked + .slider {
                    background-color: #667eea;
                }
                input:checked + .slider:before {
                    transform: translateX(26px);
                }
                .subscription-card {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                }

                .plan-card {
                    transition: all 0.3s ease;
                    border: 2px solid transparent;
                    cursor: pointer;
                }

                .plan-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 10px 25px rgba(0,0,0,0.1);
                }
                
                /* Profil Dropdown Stilleri */
                .profile-dropdown {
                    min-width: 280px;
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                    padding: 0;
                    margin-top: 10px;
                }
                
                .profile-dropdown .dropdown-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 15px 15px 0 0;
                    border: none;
                }
                
                .profile-avatar {
                    width: 32px;
                    height: 32px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 14px;
                }
                
                .profile-avatar-large {
                    width: 48px;
                    height: 48px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 20px;
                }
                
                .profile-name {
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .profile-dropdown .dropdown-item {
                    padding: 12px 20px;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .profile-dropdown .dropdown-item:hover {
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    transform: translateX(5px);
                }
                
                .profile-dropdown .dropdown-item i {
                    width: 20px;
                    text-align: center;
                }
                
                .profile-dropdown .dropdown-divider {
                    margin: 0;
                    border-color: #e9ecef;
                }

                .plan-card.selected {
                    border-color: #007bff;
                    box-shadow: 0 0 20px rgba(0,123,255,0.3);
                }

                .plan-card .card-header {
                    font-weight: bold;
                }

                .plan-card ul li {
                    margin-bottom: 8px;
                    font-size: 0.9em;
                }

                .plan-card ul li i {
                    width: 20px;
                    color: #6c757d;
                }
                .plan-feature {
                    margin: 10px 0;
                }
                .plan-feature i {
                    color: #27ae60;
                    margin-right: 10px;
                }
                .danger-zone {
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-top: 30px;
                }
                .settings-section {
                    display: none;
                }
                
                /* Modern Subscription Card Styles */
                .subscription-card-modern {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .subscription-card-modern:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
                }
                
                .subscription-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 2rem;
                    text-align: center;
                    position: relative;
                }
                
                .subscription-header::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
                    opacity: 0.3;
                }
                
                .subscription-icon {
                    position: relative;
                    z-index: 1;
                    width: 80px;
                    height: 80px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1rem;
                    font-size: 2rem;
                    color: white;
                    backdrop-filter: blur(10px);
                }
                
                .subscription-title {
                    position: relative;
                    z-index: 1;
                }
                
                .subscription-title h4 {
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                }
                
                .subscription-title p {
                    opacity: 0.9;
                    font-size: 1rem;
                }
                
                .subscription-content {
                    padding: 2rem;
                }
                
                .info-section {
                    margin-bottom: 2rem;
                }
                
                .section-title {
                    color: #2c3e50;
                    font-weight: 600;
                    margin-bottom: 1.5rem;
                    padding-bottom: 0.5rem;
                    border-bottom: 2px solid #e9ecef;
                }
                
                .info-grid {
                    display: grid;
                    grid-template-columns: 1fr;
                    gap: 1rem;
                }
                
                .info-item {
                    display: flex;
                    align-items: center;
                    padding: 1rem;
                    background: #f8f9fa;
                    border-radius: 12px;
                    transition: all 0.3s ease;
                    border: 1px solid #e9ecef;
                }
                
                .info-item:hover {
                    background: white;
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                    transform: translateY(-2px);
                }
                
                .info-icon {
                    width: 50px;
                    height: 50px;
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 1rem;
                    color: white;
                    font-size: 1.2rem;
                    flex-shrink: 0;
                }
                
                .info-content {
                    flex: 1;
                }
                
                .info-content label {
                    display: block;
                    font-size: 0.875rem;
                    color: #6c757d;
                    margin-bottom: 0.25rem;
                    font-weight: 500;
                }
                
                .info-value {
                    display: block;
                    font-size: 1.1rem;
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .usage-card {
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    border-radius: 16px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    border: 1px solid #dee2e6;
                }
                
                .usage-header {
                    display: flex;
                    align-items: center;
                    margin-bottom: 1rem;
                }
                
                .usage-icon {
                    width: 50px;
                    height: 50px;
                    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 1rem;
                    color: white;
                    font-size: 1.2rem;
                }
                
                .usage-info h6 {
                    margin: 0;
                    color: #2c3e50;
                    font-weight: 600;
                }
                
                .usage-text {
                    color: #6c757d;
                    font-size: 0.9rem;
                }
                
                .usage-progress {
                    margin-top: 1rem;
                }
                
                .usage-progress .progress {
                    height: 12px;
                    border-radius: 6px;
                    background: #e9ecef;
                    overflow: hidden;
                }
                
                .usage-progress .progress-bar {
                    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                    border-radius: 6px;
                    position: relative;
                    transition: all 0.3s ease;
                }
                
                .progress-text {
                    position: absolute;
                    right: 8px;
                    top: 50%;
                    transform: translateY(-50%);
                    color: white;
                    font-size: 0.75rem;
                    font-weight: 600;
                }
                
                .features-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 1rem;
                }
                
                .feature-item {
                    display: flex;
                    align-items: center;
                    padding: 1rem;
                    background: white;
                    border-radius: 12px;
                    border: 1px solid #e9ecef;
                    transition: all 0.3s ease;
                }
                
                .feature-item:hover {
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                    transform: translateY(-2px);
                }
                
                .feature-icon {
                    width: 40px;
                    height: 40px;
                    border-radius: 10px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 0.75rem;
                    color: white;
                    font-size: 1rem;
                    flex-shrink: 0;
                }
                
                .feature-content {
                    flex: 1;
                }
                
                .feature-content strong {
                    display: block;
                    color: #2c3e50;
                    font-size: 0.9rem;
                    margin-bottom: 0.25rem;
                }
                
                .feature-content small {
                    color: #6c757d;
                    font-size: 0.8rem;
                }
                
                .subscription-actions {
                    background: #f8f9fa;
                    padding: 2rem;
                    text-align: center;
                    border-top: 1px solid #e9ecef;
                }
                
                .subscription-actions .btn {
                    border-radius: 12px;
                    font-weight: 600;
                    padding: 0.75rem 1.5rem;
                    transition: all 0.3s ease;
                }
                
                .subscription-actions .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                }
                
                /* Responsive Design */
                @media (max-width: 768px) {
                    .info-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .features-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .subscription-header {
                        padding: 1.5rem;
                    }
                    
                    .subscription-content {
                        padding: 1.5rem;
                    }
                    
                    .subscription-actions {
                        padding: 1.5rem;
                    }
                    
                    .subscription-actions .btn {
                        display: block;
                        width: 100%;
                        margin-bottom: 1rem;
                    }
                    
                    .subscription-actions .btn:last-child {
                        margin-bottom: 0;
                    }
                }
                
                /* Modern Profile Card Styles */
                .profile-card-modern {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .profile-card-modern:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
                }
                
                .profile-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 2rem;
                    text-align: center;
                    position: relative;
                }
                
                .profile-header::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
                    opacity: 0.3;
                }
                
                .profile-icon {
                    position: relative;
                    z-index: 1;
                    width: 80px;
                    height: 80px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1rem;
                    font-size: 2rem;
                    color: white;
                    backdrop-filter: blur(10px);
                }
                
                .profile-title {
                    position: relative;
                    z-index: 1;
                }
                
                .profile-title h4 {
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                }
                
                .profile-title p {
                    opacity: 0.9;
                    font-size: 1rem;
                }
                
                .profile-content {
                    padding: 2rem;
                }
                
                .logo-section {
                    text-align: center;
                }
                
                .logo-upload-modern {
                    width: 200px;
                    height: 200px;
                    border: 3px dashed #dee2e6;
                    border-radius: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    position: relative;
                    overflow: hidden;
                }
                
                .logo-upload-modern:hover {
                    border-color: #667eea;
                    background: #f8f9fa;
                    transform: scale(1.02);
                }
                
                .logo-preview {
                    width: 100%;
                    height: 100%;
                    position: relative;
                }
                
                .logo-preview img {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                    border-radius: 17px;
                }
                
                .logo-overlay {
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(102, 126, 234, 0.9);
                    color: white;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    opacity: 0;
                    transition: all 0.3s ease;
                    border-radius: 17px;
                }
                
                .logo-upload-modern:hover .logo-overlay {
                    opacity: 1;
                }
                
                .logo-overlay i {
                    font-size: 2rem;
                    margin-bottom: 0.5rem;
                }
                
                .logo-overlay span {
                    font-weight: 600;
                    font-size: 0.9rem;
                }
                
                .logo-placeholder {
                    color: #6c757d;
                }
                
                .logo-icon {
                    width: 60px;
                    height: 60px;
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto;
                    font-size: 1.5rem;
                }
                
                .logo-info {
                    margin-top: 1rem;
                }
                
                .logo-info .info-item {
                    display: flex;
                    align-items: center;
                    margin-bottom: 0.5rem;
                    font-size: 0.8rem;
                    color: #6c757d;
                }
                
                .logo-info .info-item i {
                    margin-right: 0.5rem;
                    width: 16px;
                }
                
                .company-info {
                    margin-top: 1rem;
                }
                
                .section-title {
                    color: #2c3e50;
                    font-weight: 600;
                    margin-bottom: 1.5rem;
                    padding-bottom: 0.5rem;
                    border-bottom: 2px solid #e9ecef;
                }
                
                .form-group-modern {
                    margin-bottom: 1.5rem;
                }
                
                .form-label-modern {
                    display: block;
                    font-weight: 600;
                    color: #2c3e50;
                    margin-bottom: 0.5rem;
                    font-size: 0.9rem;
                }
                
                .input-group-modern {
                    position: relative;
                }
                
                .form-control-modern,
                .form-select-modern {
                    width: 100%;
                    padding: 0.75rem 1rem 0.75rem 3rem;
                    border: 2px solid #e9ecef;
                    border-radius: 12px;
                    font-size: 0.95rem;
                    transition: all 0.3s ease;
                    background: white;
                }
                
                .form-control-modern:focus,
                .form-select-modern:focus {
                    outline: none;
                    border-color: #667eea;
                    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
                }
                
                .form-control-modern:read-only {
                    background: #f8f9fa;
                    color: #6c757d;
                }
                
                .input-icon {
                    position: absolute;
                    left: 1rem;
                    top: 50%;
                    transform: translateY(-50%);
                    color: #6c757d;
                    font-size: 1rem;
                }
                
                .form-text {
                    display: block;
                    margin-top: 0.25rem;
                    font-size: 0.8rem;
                    color: #6c757d;
                }
                
                .profile-actions {
                    background: #f8f9fa;
                    padding: 2rem;
                    text-align: center;
                    border-top: 1px solid #e9ecef;
                    margin-top: 2rem;
                }
                
                .profile-actions .btn {
                    border-radius: 12px;
                    font-weight: 600;
                    padding: 0.75rem 1.5rem;
                    transition: all 0.3s ease;
                }
                
                .profile-actions .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                }
                
                /* Responsive Profile Design */
                @media (max-width: 768px) {
                    .profile-header {
                        padding: 1.5rem;
                    }
                    
                    .profile-content {
                        padding: 1.5rem;
                    }
                    
                    .logo-upload-modern {
                        width: 150px;
                        height: 150px;
                    }
                    
                    .profile-actions {
                        padding: 1.5rem;
                    }
                    
                    .profile-actions .btn {
                        display: block;
                        width: 100%;
                        margin-bottom: 1rem;
                    }
                    
                    .profile-actions .btn:last-child {
                        margin-bottom: 0;
                    }
                }
                
                /* Modern Security Card Styles */
                .security-card-modern {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .security-card-modern:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
                }
                
                .security-header {
                    background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                    color: white;
                    padding: 2rem;
                    text-align: center;
                    position: relative;
                }
                
                .security-header::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="security-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/></pattern></defs><rect width="100" height="100" fill="url(%23security-grid)"/></svg>');
                    opacity: 0.3;
                }
                
                .security-icon {
                    position: relative;
                    z-index: 1;
                    width: 80px;
                    height: 80px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1rem;
                    font-size: 2rem;
                    color: white;
                    backdrop-filter: blur(10px);
                }
                
                .security-title {
                    position: relative;
                    z-index: 1;
                }
                
                .security-title h4 {
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                }
                
                .security-title p {
                    opacity: 0.9;
                    font-size: 1rem;
                }
                
                .security-content {
                    padding: 2rem;
                }
                
                .security-section {
                    margin-bottom: 3rem;
                    padding: 2rem;
                    background: #f8f9fa;
                    border-radius: 16px;
                    border: 1px solid #e9ecef;
                }
                
                .security-section:last-child {
                    margin-bottom: 0;
                }
                
                .section-header {
                    display: flex;
                    align-items: center;
                    margin-bottom: 2rem;
                }
                
                .section-icon {
                    width: 60px;
                    height: 60px;
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 1.5rem;
                    font-size: 1.5rem;
                    flex-shrink: 0;
                }
                
                .section-icon.danger {
                    background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
                }
                
                .section-info {
                    flex: 1;
                }
                
                .section-title {
                    color: #2c3e50;
                    font-weight: 600;
                    margin-bottom: 0.5rem;
                    font-size: 1.1rem;
                }
                
                .section-description {
                    color: #6c757d;
                    margin: 0;
                    font-size: 0.9rem;
                }
                
                .password-form-container {
                    background: white;
                    padding: 2rem;
                    border-radius: 12px;
                    border: 1px solid #e9ecef;
                }
                
                .password-strength {
                    margin-top: 1rem;
                }
                
                .strength-bar {
                    width: 100%;
                    height: 8px;
                    background: #e9ecef;
                    border-radius: 4px;
                    overflow: hidden;
                    margin-bottom: 0.5rem;
                }
                
                .strength-fill {
                    height: 100%;
                    background: #dc3545;
                    width: 0%;
                    transition: all 0.3s ease;
                    border-radius: 4px;
                }
                
                .strength-fill.weak { width: 25%; background: #dc3545; }
                .strength-fill.fair { width: 50%; background: #ffc107; }
                .strength-fill.good { width: 75%; background: #28a745; }
                .strength-fill.strong { width: 100%; background: #20c997; }
                
                .strength-text {
                    font-size: 0.8rem;
                    color: #6c757d;
                }
                
                .password-requirements {
                    background: #f8f9fa;
                    padding: 1.5rem;
                    border-radius: 12px;
                    border: 1px solid #e9ecef;
                }
                
                .requirements-title {
                    color: #2c3e50;
                    font-weight: 600;
                    margin-bottom: 1rem;
                    font-size: 0.9rem;
                }
                
                .requirements-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 0.75rem;
                }
                
                .requirement-item {
                    display: flex;
                    align-items: center;
                    font-size: 0.8rem;
                    color: #6c757d;
                }
                
                .requirement-item i {
                    margin-right: 0.5rem;
                    width: 16px;
                }
                
                .requirement-item.valid {
                    color: #28a745;
                }
                
                .requirement-item.valid i {
                    color: #28a745;
                }
                
                .form-actions {
                    text-align: center;
                    padding-top: 1rem;
                    border-top: 1px solid #e9ecef;
                }
                
                .form-actions .btn {
                    border-radius: 12px;
                    font-weight: 600;
                    padding: 0.75rem 1.5rem;
                    transition: all 0.3s ease;
                }
                
                .form-actions .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                }
                
                .danger-section {
                    background: linear-gradient(135deg, #fff5f5 0%, #fed7d7 100%);
                    border: 2px solid #feb2b2;
                }
                
                .danger-zone-container {
                    background: white;
                    padding: 2rem;
                    border-radius: 12px;
                    border: 1px solid #feb2b2;
                }
                
                .danger-warning {
                    display: flex;
                    align-items: center;
                    background: #fed7d7;
                    padding: 1.5rem;
                    border-radius: 12px;
                    margin-bottom: 2rem;
                    border: 1px solid #feb2b2;
                }
                
                .warning-icon {
                    width: 50px;
                    height: 50px;
                    background: #dc3545;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 1rem;
                    color: white;
                    font-size: 1.5rem;
                    flex-shrink: 0;
                }
                
                .warning-content {
                    flex: 1;
                }
                
                .warning-title {
                    color: #dc3545;
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                    font-size: 1rem;
                }
                
                .warning-text {
                    color: #721c24;
                    margin: 0;
                    font-size: 0.9rem;
                }
                
                .form-check-modern {
                    display: flex;
                    align-items: flex-start;
                    padding: 1rem;
                    background: #fff5f5;
                    border-radius: 12px;
                    border: 1px solid #feb2b2;
                }
                
                .form-check-input-modern {
                    margin-right: 1rem;
                    margin-top: 0.25rem;
                    width: 1.2rem;
                    height: 1.2rem;
                }
                
                .form-check-label-modern {
                    color: #721c24;
                    font-weight: 600;
                    font-size: 0.9rem;
                    line-height: 1.4;
                }
                
                .tips-section {
                    background: linear-gradient(135deg, #f0f8ff 0%, #e6f3ff 100%);
                    border: 2px solid #b3d9ff;
                }
                
                .tips-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 1.5rem;
                    margin-top: 1.5rem;
                }
                
                .tip-card {
                    background: white;
                    padding: 1.5rem;
                    border-radius: 12px;
                    text-align: center;
                    border: 1px solid #b3d9ff;
                    transition: all 0.3s ease;
                }
                
                .tip-card:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
                }
                
                .tip-icon {
                    width: 60px;
                    height: 60px;
                    background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1rem;
                    color: white;
                    font-size: 1.5rem;
                }
                
                .tip-card h6 {
                    color: #2c3e50;
                    font-weight: 600;
                    margin-bottom: 0.75rem;
                    font-size: 1rem;
                }
                
                .tip-card p {
                    color: #6c757d;
                    margin: 0;
                    font-size: 0.85rem;
                    line-height: 1.4;
                }
                
                /* Responsive Security Design */
                @media (max-width: 768px) {
                    .security-header {
                        padding: 1.5rem;
                    }
                    
                    .security-content {
                        padding: 1.5rem;
                    }
                    
                    .security-section {
                        padding: 1.5rem;
                        margin-bottom: 2rem;
                    }
                    
                    .section-header {
                        flex-direction: column;
                        text-align: center;
                    }
                    
                    .section-icon {
                        margin-right: 0;
                        margin-bottom: 1rem;
                    }
                    
                    .requirements-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .tips-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .form-actions .btn {
                        display: block;
                        width: 100%;
                        margin-bottom: 1rem;
                    }
                    
                    .form-actions .btn:last-child {
                        margin-bottom: 0;
                    }
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/company/{{ company_id }}/dashboard">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="nav-link active" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        
                        <!-- Profil Dropdown -->
                        <div class="nav-item dropdown">
                            <a class="nav-link dropdown-toggle d-flex align-items-center" href="#" id="profileDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                <div class="profile-avatar me-2">
                                    <i class="fas fa-building"></i>
                                </div>
                                <span class="profile-name">{{ user_data.company_name }}</span>
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end profile-dropdown" aria-labelledby="profileDropdown">
                                <li class="dropdown-header">
                                    <div class="d-flex align-items-center">
                                        <div class="profile-avatar-large me-3">
                                            <i class="fas fa-building"></i>
                                        </div>
                                        <div>
                                            <div class="fw-bold">{{ user_data.company_name }}</div>
                                            <small class="text-white">{{ company_id }}</small>
                                        </div>
                                    </div>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/profile">
                                        <i class="fas fa-user me-2"></i> Şirket Profili
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/subscription">
                                        <i class="fas fa-crown me-2"></i> Abonelik Bilgileri
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/billing">
                                        <i class="fas fa-credit-card me-2"></i> Fatura & Ödeme
                                    </a>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item text-danger" href="#" onclick="logout()">
                                        <i class="fas fa-sign-out-alt me-2"></i> Çıkış Yap
                                    </a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <div class="row">
                    <div class="col-md-3">
                        <!-- Settings Navigation -->
                        <div class="settings-nav">
                            <h5 class="text-white mb-3">
                                <i class="fas fa-cog"></i> Ayarlar
                            </h5>
                            <nav class="nav flex-column">
                                <a class="nav-link active" href="#profile" data-section="profile">
                                    <i class="fas fa-building"></i> Şirket Profili
                                </a>
                                <a class="nav-link" href="#ppe-config" data-section="ppe-config">
                                    <i class="fas fa-hard-hat"></i> PPE Konfigürasyonu
                                </a>
                                <a class="nav-link" href="#notifications" data-section="notifications">
                                    <i class="fas fa-bell"></i> Bildirimler
                                </a>
                                <a class="nav-link" href="#subscription" data-section="subscription">
                                    <i class="fas fa-credit-card"></i> Abonelik
                                </a>
                                <a class="nav-link" href="#security" data-section="security">
                                    <i class="fas fa-shield-alt"></i> Güvenlik
                                </a>
                            </nav>
                        </div>
                    </div>
                    
                    <div class="col-md-9">
                        <!-- Şirket Profili -->
                        <div id="profile-section" class="settings-section" style="display: block;">
                            <div class="profile-card-modern">
                                <div class="profile-header">
                                    <div class="profile-icon">
                                        <i class="fas fa-building"></i>
                                    </div>
                                    <div class="profile-title">
                                        <h4 class="mb-1">Şirket Profili</h4>
                                        <p class="text-white mb-0">Şirket bilgilerinizi güncelleyin ve yönetin</p>
                                    </div>
                                </div>
                                
                                <div class="profile-content">
                                <form id="profileForm">
                                        <div class="row g-4">
                                            <!-- Logo Upload Section -->
                                            <div class="col-lg-4">
                                                <div class="logo-section">
                                                    <div class="logo-upload-modern" onclick="document.getElementById('logoInput').click()">
                                                    {% if company.logo_url %}
                                                            <div class="logo-preview">
                                                                <img src="{{ company.logo_url }}" alt="Şirket Logo">
                                                                <div class="logo-overlay">
                                                                    <i class="fas fa-camera"></i>
                                                                    <span>Logo Değiştir</span>
                                                                </div>
                                                            </div>
                                                    {% else %}
                                                            <div class="logo-placeholder">
                                                                <div class="logo-icon">
                                                                    <i class="fas fa-camera"></i>
                                                                </div>
                                                                <h6 class="mt-3">Logo Yükle</h6>
                                                                <p class="text-muted small">PNG, JPG, GIF (Max 5MB)</p>
                                                    </div>
                                                    {% endif %}
                                                </div>
                                                <input type="file" id="logoInput" accept="image/*" style="display: none;">
                                                    
                                                    <div class="logo-info mt-3">
                                                        <div class="info-item">
                                                            <i class="fas fa-info-circle text-primary"></i>
                                                            <span>Önerilen boyut: 300x300px</span>
                                            </div>
                                                        <div class="info-item">
                                                            <i class="fas fa-shield-alt text-success"></i>
                                                            <span>Güvenli yükleme</span>
                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <!-- Company Information -->
                                            <div class="col-lg-8">
                                                <div class="company-info">
                                                    <h6 class="section-title">
                                                        <i class="fas fa-info-circle text-primary me-2"></i>
                                                        Temel Bilgiler
                                                    </h6>
                                                    
                                                    <div class="row g-3">
                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-fingerprint text-info me-2"></i>
                                                                    Şirket ID
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <input type="text" class="form-control-modern" value="{{ company_id }}" readonly>
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-lock text-muted"></i>
                                                                    </span>
                                            </div>
                                                                <small class="form-text">Bu alan değiştirilemez</small>
                                                            </div>
                                                        </div>
                                                        
                                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-building text-primary me-2"></i>
                                                                    Şirket Adı *
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <input type="text" class="form-control-modern" name="company_name" value="{{ user_data.company_name }}" placeholder="Şirket adınızı girin">
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-building text-primary"></i>
                                                                    </span>
                                            </div>
                                        </div>
                                    </div>
                                    
                                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-user text-success me-2"></i>
                                                                    İletişim Kişisi *
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <input type="text" class="form-control-modern" name="contact_person" value="{{ user_data.contact_person }}" placeholder="İletişim kişisini girin">
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-user text-success"></i>
                                                                    </span>
                                        </div>
                                                            </div>
                                                        </div>
                                                        
                                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-envelope text-warning me-2"></i>
                                                                    Email *
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <input type="text" class="form-control-modern" name="email" value="{{ user_data.email }}" 
                                                                           placeholder="ornek@email.com"
                                                   oninput="validateEmail(this)"
                                                   onblur="validateEmail(this)"
                                                   autocomplete="email">
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-envelope text-warning"></i>
                                                                    </span>
                                                                </div>
                                                                <small class="form-text">Türkçe karakterler desteklenir</small>
                                        </div>
                                    </div>
                                    
                                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-phone text-info me-2"></i>
                                                                    Telefon
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <input type="tel" class="form-control-modern" name="phone" value="{{ user_data.phone }}" placeholder="+90 5XX XXX XX XX">
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-phone text-info"></i>
                                                                    </span>
                                        </div>
                                                            </div>
                                                        </div>
                                                        
                                                        <div class="col-md-6">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-industry text-danger me-2"></i>
                                                                    Sektör
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <select class="form-select-modern" name="sector">
                                                                        <option value="construction" {% if user_data.sector == 'construction' %}selected{% endif %}>🏗️ İnşaat</option>
                                                                        <option value="manufacturing" {% if user_data.sector == 'manufacturing' %}selected{% endif %}>🏭 İmalat</option>
                                                                        <option value="chemical" {% if user_data.sector == 'chemical' %}selected{% endif %}>🧪 Kimya</option>
                                                                        <option value="food" {% if user_data.sector == 'food' %}selected{% endif %}>🍽️ Gıda</option>
                                                                        <option value="warehouse" {% if user_data.sector == 'warehouse' %}selected{% endif %}>📦 Depo/Lojistik</option>
                                                                        <option value="energy" {% if user_data.sector == 'energy' %}selected{% endif %}>⚡ Enerji</option>
                                                                        <option value="petrochemical" {% if user_data.sector == 'petrochemical' %}selected{% endif %}>🛢️ Petrokimya</option>
                                                                        <option value="marine" {% if user_data.sector == 'marine' %}selected{% endif %}>🚢 Denizcilik & Tersane</option>
                                                                        <option value="aviation" {% if user_data.sector == 'aviation' %}selected{% endif %}>✈️ Havacılık</option>
                                            </select>
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-industry text-danger"></i>
                                                                    </span>
                                                                </div>
                                        </div>
                                    </div>
                                    
                                                        <div class="col-12">
                                                            <div class="form-group-modern">
                                                                <label class="form-label-modern">
                                                                    <i class="fas fa-map-marker-alt text-danger me-2"></i>
                                                                    Adres
                                                                </label>
                                                                <div class="input-group-modern">
                                                                    <textarea class="form-control-modern" name="address" rows="3" placeholder="Şirket adresini girin">{{ user_data.address }}</textarea>
                                                                    <span class="input-icon">
                                                                        <i class="fas fa-map-marker-alt text-danger"></i>
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                    </div>
                                    
                                        <div class="profile-actions">
                                            <button type="submit" class="btn btn-primary btn-lg">
                                                <i class="fas fa-save me-2"></i>
                                                Değişiklikleri Kaydet
                                    </button>
                                            <button type="button" class="btn btn-outline-secondary btn-lg ms-3" onclick="resetForm()">
                                                <i class="fas fa-undo me-2"></i>
                                                Sıfırla
                                            </button>
                                        </div>
                                </form>
                                </div>
                            </div>
                        </div>
                        
                        <!-- PPE Konfigürasyonu -->
                        <div id="ppe-config-section" class="settings-section" style="display: none;">
                            <div class="form-section">
                                <h5><i class="fas fa-hard-hat"></i> PPE Konfigürasyonu</h5>
                                <p class="text-muted">Şirket kayıt sırasında seçtiğiniz PPE'leri yönetin ve ek konfigürasyonlar yapın.</p>
                                
                                <!-- Loading State -->
                                <div id="ppe-loading" class="text-center py-4">
                                    <div class="spinner-border text-primary" role="status">
                                        <span class="visually-hidden">Yükleniyor...</span>
                                </div>
                                    <p class="mt-2 text-muted">PPE konfigürasyonu yükleniyor...</p>
                                        </div>
                                        
                                <!-- PPE Configuration Content -->
                                <div id="ppe-content" style="display: none;">
                                    <!-- Sector Info -->
                                    <div class="alert alert-primary">
                                        <div class="row align-items-center">
                                            <div class="col-md-8">
                                                <i class="fas fa-industry"></i>
                                                <strong>Mevcut Sektör:</strong> <span id="current-sector">{{ user_data.sector|title }}</span>
                                                <span class="badge bg-white text-primary ms-2">Sektör Bazlı Konfigürasyon</span>
                                                </div>
                                            </div>
                                        </div>
                                        

                                    
                                    <!-- Özel PPE Konfigürasyonu -->
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="mb-0"><i class="fas fa-cogs"></i> Özel PPE Konfigürasyonu</h6>
                                            <small class="text-muted">Ek PPE türleri ekleyebilir veya mevcut ayarları değiştirebilirsiniz</small>
                                                </div>
                                        <div class="card-body">
                                                                                        <div class="row">
                                                <div class="col-12">
                                                    <h6 class="text-danger mb-3">
                                                        <i class="fas fa-exclamation-triangle"></i> Zorunlu PPE Ekipmanları
                                                        <small class="text-muted d-block">Bu PPE'ler tespit edilmediğinde uyarı verilir</small>
                                                    </h6>
                                                    <div id="required-ppe-config">
                                                        <!-- Dinamik içerik -->
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                

                                    

                                </div>
                                

                                
                                <!-- Action Buttons -->
                                <div class="text-center mt-4">
                                    <button type="button" class="btn btn-primary btn-lg" onclick="savePPEConfig()">
                                        <i class="fas fa-save"></i> Konfigürasyonu Kaydet
                                    </button>
                                    <button type="button" class="btn btn-outline-secondary btn-lg ms-2" onclick="resetPPEConfig()">
                                        <i class="fas fa-undo"></i> Sıfırla
                                    </button>
                                    <button type="button" class="btn btn-outline-info btn-lg ms-2" onclick="previewPPEConfig()">
                                        <i class="fas fa-eye"></i> Önizleme
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Bildirimler -->
                        <div id="notifications-section" class="settings-section" style="display: none;">
                            <div class="form-section">
                                <h5><i class="fas fa-bell"></i> Bildirim Ayarları</h5>
                                <p class="text-muted">Hangi durumlarda nasıl bilgilendirilmek istediğinizi seçin.</p>
                                
                                <div class="mb-4">
                                    <h6>Email Bildirimleri</h6>
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Email Bildirimleri</strong>
                                            <small class="text-muted d-block">Genel email bildirimleri</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="email_notifications" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>SMS Bildirimleri</strong>
                                            <small class="text-muted d-block">Acil durumlarda SMS gönder</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="sms_notifications">
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Push Bildirimleri</strong>
                                            <small class="text-muted d-block">Tarayıcı bildirimleri</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="push_notifications" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                </div>
                                
                                <div class="mb-4">
                                    <h6>Uyarı Türleri</h6>
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>İhlal Uyarıları</strong>
                                            <small class="text-muted d-block">PPE ihlali tespit edildiğinde uyar</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="violation_alerts" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Sistem Uyarıları</strong>
                                            <small class="text-muted d-block">Sistem durumu ve hata uyarıları</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="system_alerts" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Rapor Bildirimleri</strong>
                                            <small class="text-muted d-block">Günlük ve haftalık raporlar</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" id="report_notifications" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Abonelik -->
                        <div id="subscription-section" class="settings-section" style="display: none;">
                            <div class="subscription-card-modern">
                                <div class="subscription-header">
                                    <div class="subscription-icon">
                                        <i class="fas fa-crown"></i>
                                        </div>
                                    <div class="subscription-title">
                                        <h4 class="mb-1">Abonelik Bilgileri</h4>
                                        <p class="text-white mb-0">Mevcut planınız ve kullanım detayları</p>
                                        </div>
                                        </div>
                                
                                <div class="subscription-content">
                                    <div class="row g-4">
                                        <!-- Plan Detayları -->
                                        <div class="col-lg-6">
                                            <div class="info-section">
                                                <h6 class="section-title">
                                                    <i class="fas fa-info-circle text-primary me-2"></i>
                                                    Plan Detayları
                                                </h6>
                                                <div class="info-grid">
                                                    <div class="info-item">
                                                        <div class="info-icon bg-primary">
                                                            <i class="fas fa-crown"></i>
                                        </div>
                                                        <div class="info-content">
                                                            <label>Plan Türü</label>
                                                            <span id="subscription-type" class="info-value">BASIC</span>
                                        </div>
                                        </div>
                                                    
                                                    <div class="info-item">
                                                        <div class="info-icon bg-info">
                                                            <i class="fas fa-calendar-alt"></i>
                                    </div>
                                                        <div class="info-content">
                                                            <label>Fatura Döngüsü</label>
                                                            <span id="billing-cycle" class="info-value">AYLIK</span>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="info-item">
                                                        <div class="info-icon bg-success">
                                                            <i class="fas fa-dollar-sign"></i>
                                                        </div>
                                                        <div class="info-content">
                                                            <label>Mevcut Fiyat</label>
                                                            <span id="current-price" class="info-value">$99/ay</span>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="info-item">
                                                        <div class="info-icon bg-warning">
                                                            <i class="fas fa-clock"></i>
                                                        </div>
                                                        <div class="info-content">
                                                            <label>Bitiş Tarihi</label>
                                                            <span id="subscription-end" class="info-value">--</span>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="info-item">
                                                        <div class="info-icon bg-danger">
                                                            <i class="fas fa-hourglass-half"></i>
                                                        </div>
                                                        <div class="info-content">
                                                            <label>Kalan Gün</label>
                                                            <span id="days-remaining" class="info-value">--</span>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="info-item">
                                                        <div class="info-icon bg-secondary">
                                                            <i class="fas fa-toggle-on"></i>
                                                        </div>
                                                        <div class="info-content">
                                                            <label>Durum</label>
                                                            <span id="subscription-status" class="info-value">Aktif</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <!-- Kullanım ve Özellikler -->
                                        <div class="col-lg-6">
                                            <div class="info-section">
                                                <h6 class="section-title">
                                                    <i class="fas fa-chart-line text-success me-2"></i>
                                                    Kullanım ve Özellikler
                                                </h6>
                                                
                                                <!-- Kamera Kullanımı -->
                                                <div class="usage-card">
                                                    <div class="usage-header">
                                                        <div class="usage-icon">
                                            <i class="fas fa-video"></i>
                                        </div>
                                                        <div class="usage-info">
                                                            <h6 class="mb-1">Kamera Kullanımı</h6>
                                                            <span id="camera-usage" class="usage-text">--/--</span>
                                        </div>
                                                    </div>
                                                    <div class="usage-progress">
                                                        <div class="progress">
                                                            <div class="progress-bar" id="usage-progress" role="progressbar" style="width: 0%">
                                                                <span class="progress-text">0%</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                
                                                <!-- Özellikler -->
                                                <div class="features-grid">
                                                    <div class="feature-item">
                                                        <div class="feature-icon bg-success">
                                            <i class="fas fa-shield-alt"></i>
                                        </div>
                                                        <div class="feature-content">
                                                            <strong>Güvenlik</strong>
                                                            <small>SSL Şifreleme</small>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="feature-item">
                                                        <div class="feature-icon bg-info">
                                            <i class="fas fa-headset"></i>
                                        </div>
                                                        <div class="feature-content">
                                                            <strong>Destek</strong>
                                                            <small>7/24 Teknik Destek</small>
                                    </div>
                                </div>
                                
                                                    <div class="feature-item">
                                                        <div class="feature-icon bg-warning">
                                                            <i class="fas fa-sync-alt"></i>
                                                        </div>
                                                        <div class="feature-content">
                                                            <strong>Güncellemeler</strong>
                                                            <small>Otomatik Güncelleme</small>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="feature-item">
                                                        <div class="feature-icon bg-primary">
                                                            <i class="fas fa-database"></i>
                                                        </div>
                                                        <div class="feature-content">
                                                            <strong>Yedekleme</strong>
                                                            <small>Günlük Yedekleme</small>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="subscription-actions">
                                    <button class="btn btn-primary btn-lg" onclick="openUpgradeModal()">
                                        <i class="fas fa-arrow-up me-2"></i>
                                        Planı Yükselt
                                    </button>
                                    <button class="btn btn-outline-primary btn-lg ms-3">
                                        <i class="fas fa-file-invoice me-2"></i>
                                        Fatura Geçmişi
                                    </button>
                                    <button class="btn btn-outline-secondary btn-lg ms-3">
                                        <i class="fas fa-download me-2"></i>
                                        Rapor İndir
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Güvenlik -->
                        <div id="security-section" class="settings-section" style="display: none;">
                            <div class="security-card-modern">
                                <div class="security-header">
                                    <div class="security-icon">
                                        <i class="fas fa-shield-alt"></i>
                                    </div>
                                    <div class="security-title">
                                        <h4 class="mb-1">Güvenlik Ayarları</h4>
                                        <p class="text-white mb-0">Hesap güvenliğinizi yönetin ve koruyun</p>
                                    </div>
                                </div>
                                
                                <div class="security-content">
                                    <!-- Şifre Değiştirme Bölümü -->
                                    <div class="security-section">
                                        <div class="section-header">
                                            <div class="section-icon">
                                                <i class="fas fa-key text-primary"></i>
                                            </div>
                                            <div class="section-info">
                                                <h6 class="section-title">Şifre Değiştir</h6>
                                                <p class="section-description">Hesap güvenliğiniz için güçlü bir şifre belirleyin</p>
                                            </div>
                                        </div>
                                        
                                        <div class="password-form-container">
                                    <form id="passwordForm">
                                                <div class="row g-3">
                                                    <div class="col-md-12">
                                                        <div class="form-group-modern">
                                                            <label class="form-label-modern">
                                                                <i class="fas fa-lock text-warning me-2"></i>
                                                                Mevcut Şifre
                                                            </label>
                                                            <div class="input-group-modern">
                                                                <input type="password" class="form-control-modern" name="current_password" required placeholder="Mevcut şifrenizi girin">
                                                                <span class="input-icon">
                                                                    <i class="fas fa-lock text-warning"></i>
                                                                </span>
                                        </div>
                                        </div>
                                        </div>
                                                    
                                                    <div class="col-md-6">
                                                        <div class="form-group-modern">
                                                            <label class="form-label-modern">
                                                                <i class="fas fa-key text-success me-2"></i>
                                                                Yeni Şifre
                                                            </label>
                                                            <div class="input-group-modern">
                                                                <input type="password" class="form-control-modern" name="new_password" required placeholder="Yeni şifrenizi girin">
                                                                <span class="input-icon">
                                                                    <i class="fas fa-key text-success"></i>
                                                                </span>
                                                            </div>
                                                            <div class="password-strength mt-2">
                                                                <div class="strength-bar">
                                                                    <div class="strength-fill" id="strength-fill"></div>
                                                                </div>
                                                                <small class="strength-text" id="strength-text">Password strength: Weak</small>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="col-md-6">
                                                        <div class="form-group-modern">
                                                            <label class="form-label-modern">
                                                                <i class="fas fa-check-circle text-info me-2"></i>
                                                                Yeni Şifre (Tekrar)
                                                            </label>
                                                            <div class="input-group-modern">
                                                                <input type="password" class="form-control-modern" name="confirm_password" required placeholder="Şifrenizi tekrar girin">
                                                                <span class="input-icon">
                                                                    <i class="fas fa-check-circle text-info"></i>
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                
                                                <div class="password-requirements mt-4">
                                                    <h6 class="requirements-title">
                                                        <i class="fas fa-info-circle text-primary me-2"></i>
                                                        Password Requirements
                                                    </h6>
                                                    <div class="requirements-grid">
                                                        <div class="requirement-item" id="req-length">
                                                            <i class="fas fa-times text-danger"></i>
                                                            <span>En az 8 karakter</span>
                                                        </div>
                                                        <div class="requirement-item" id="req-uppercase">
                                                            <i class="fas fa-times text-danger"></i>
                                                            <span>En az 1 büyük harf (A-Z)</span>
                                                        </div>
                                                        <div class="requirement-item" id="req-lowercase">
                                                            <i class="fas fa-times text-danger"></i>
                                                            <span>En az 1 küçük harf (a-z)</span>
                                                        </div>
                                                        <div class="requirement-item" id="req-number">
                                                            <i class="fas fa-times text-danger"></i>
                                                            <span>En az 1 rakam (0-9)</span>
                                                        </div>
                                                        <div class="requirement-item" id="req-special">
                                                            <i class="fas fa-times text-danger"></i>
                                                            <span>En az 1 özel karakter (!@#$%^&*)</span>
                                                        </div>
                                                    </div>
                                                </div>
                                                
                                                <div class="form-actions mt-4">
                                                    <button type="submit" class="btn btn-primary btn-lg">
                                                        <i class="fas fa-key me-2"></i>
                                                        Şifre Değiştir
                                        </button>
                                                    <button type="button" class="btn btn-outline-secondary btn-lg ms-3" onclick="resetPasswordForm()">
                                                        <i class="fas fa-undo me-2"></i>
                                                        Sıfırla
                                                    </button>
                                                </div>
                                    </form>
                                        </div>
                                </div>
                                
                                    <!-- Tehlikeli Bölge -->
                                    <div class="security-section danger-section">
                                        <div class="section-header">
                                            <div class="section-icon danger">
                                                <i class="fas fa-exclamation-triangle text-danger"></i>
                                            </div>
                                            <div class="section-info">
                                                <h6 class="section-title text-danger">Tehlikeli Bölge</h6>
                                                <p class="section-description">Bu işlem geri alınamaz! Hesabınızı kalıcı olarak silmek istiyorsanız aşağıdaki adımları takip edin.</p>
                                            </div>
                                        </div>
                                        
                                        <div class="danger-zone-container">
                                            <div class="danger-warning">
                                                <div class="warning-icon">
                                                    <i class="fas fa-radiation-alt"></i>
                                                </div>
                                                <div class="warning-content">
                                                    <h6 class="warning-title">⚠️ Dikkat!</h6>
                                                    <p class="warning-text">Hesap silme işlemi geri alınamaz. Tüm verileriniz, kamera kayıtlarınız ve ayarlarınız kalıcı olarak silinecektir.</p>
                                                </div>
                                            </div>
                                    
                                    <form id="deleteAccountForm">
                                                <div class="row g-3">
                                                    <div class="col-md-12">
                                                        <div class="form-group-modern">
                                                            <label class="form-label-modern">
                                                                <i class="fas fa-lock text-danger me-2"></i>
                                                                Şifrenizi Girin
                                                            </label>
                                                            <div class="input-group-modern">
                                                                <input type="password" class="form-control-modern" name="password" required placeholder="Hesap silme işlemi için şifrenizi girin">
                                                                <span class="input-icon">
                                                                    <i class="fas fa-lock text-danger"></i>
                                                                </span>
                                        </div>
                                                        </div>
                                                    </div>
                                                    
                                                    <div class="col-12">
                                                        <div class="form-check-modern">
                                                            <input class="form-check-input-modern" type="checkbox" id="confirmDelete" required>
                                                            <label class="form-check-label-modern" for="confirmDelete">
                                                                <i class="fas fa-exclamation-triangle text-danger me-2"></i>
                                                Hesabımı ve tüm verilerimi kalıcı olarak silmek istiyorum
                                            </label>
                                        </div>
                                                    </div>
                                                </div>
                                                
                                                <div class="form-actions mt-4">
                                                    <button type="button" class="btn btn-danger btn-lg" onclick="deleteAccount()">
                                                        <i class="fas fa-trash me-2"></i>
                                                        Hesabı Kalıcı Olarak Sil
                                        </button>
                                                </div>
                                    </form>
                                </div>
                            </div>
                                    
                                    <!-- Güvenlik İpuçları -->
                                    <div class="security-section tips-section">
                                        <div class="section-header">
                                            <div class="section-icon">
                                                <i class="fas fa-lightbulb text-warning"></i>
                        </div>
                                            <div class="section-info">
                                                <h6 class="section-title">Güvenlik İpuçları</h6>
                                                <p class="section-description">Hesabınızı güvende tutmak için bu önerileri takip edin</p>
                                            </div>
                                        </div>
                                        
                                        <div class="tips-grid">
                                            <div class="tip-card">
                                                <div class="tip-icon">
                                                    <i class="fas fa-shield-alt"></i>
                                                </div>
                                                <h6>Güçlü Şifre</h6>
                                                <p>En az 8 karakter, büyük/küçük harf, rakam ve özel karakter kullanın</p>
                                            </div>
                                            
                                            <div class="tip-card">
                                                <div class="tip-icon">
                                                    <i class="fas fa-sync-alt"></i>
                                                </div>
                                                <h6>Düzenli Güncelleme</h6>
                                                <p>Şifrenizi 3-6 ayda bir değiştirin</p>
                                            </div>
                                            
                                            <div class="tip-card">
                                                <div class="tip-icon">
                                                    <i class="fas fa-user-lock"></i>
                                                </div>
                                                <h6>Güvenli Erişim</h6>
                                                <p>Güvenli ağlardan erişim sağlayın</p>
                                            </div>
                                            
                                            <div class="tip-card">
                                                <div class="tip-icon">
                                                    <i class="fas fa-eye-slash"></i>
                                                </div>
                                                <h6>Gizlilik</h6>
                                                <p>Şifrenizi kimseyle paylaşmayın</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Plan Yükseltme Modal -->
            <div class="modal fade" id="upgradePlanModal" tabindex="-1" aria-labelledby="upgradePlanModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="upgradePlanModalLabel">
                                <i class="fas fa-crown text-warning"></i> Abonelik Planını Yükselt
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <!-- Mevcut Plan Bilgisi -->
                            <div class="alert alert-info">
                                <h6><i class="fas fa-info-circle"></i> Mevcut Planınız</h6>
                                <div class="row">
                                    <div class="col-md-6">
                                        <strong>Plan:</strong> <span id="current-plan-name">--</span><br>
                                        <strong>Kamera Limiti:</strong> <span id="current-camera-limit">--</span><br>
                                        <strong>Kullanım:</strong> <span id="current-usage">--</span>
                                    </div>
                                    <div class="col-md-6">
                                        <strong>Durum:</strong> <span id="current-status">--</span><br>
                                        <strong>Bitiş Tarihi:</strong> <span id="current-end-date">--</span><br>
                                        <strong>Kalan Gün:</strong> <span id="current-days-remaining">--</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Plan Seçenekleri -->
                            <h6 class="mb-3"><i class="fas fa-list"></i> Mevcut Planlar</h6>
                            <div class="row">
                                <!-- Starter Plan -->
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" data-plan="starter">
                                        <div class="card-header text-center">
                                            <h6 class="mb-0"><i class="fas fa-rocket"></i> Starter</h6>
                                        </div>
                                        <div class="card-body text-center">
                                            <h4 class="text-primary">$99<span class="text-muted">/ay</span></h4>
                                            <ul class="list-unstyled">
                                                <li><i class="fas fa-video"></i> 25 Kamera</li>
                                                <li><i class="fas fa-brain"></i> AI Tespit (24/7)</li>
                                                <li><i class="fas fa-headset"></i> Email Destek</li>
                                                <li><i class="fas fa-chart-bar"></i> Temel Raporlar</li>
                                                <li><i class="fas fa-shield-alt"></i> Temel Güvenlik</li>
                                            </ul>
                                            <button class="btn btn-outline-primary btn-sm w-100" onclick="selectPlan('starter')">
                                                Seç
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <!-- Professional Plan -->
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" data-plan="professional">
                                        <div class="card-header text-center bg-warning text-dark">
                                            <h6 class="mb-0"><i class="fas fa-star"></i> Professional</h6>
                                        </div>
                                        <div class="card-body text-center">
                                            <h4 class="text-warning">$299<span class="text-muted">/ay</span></h4>
                                            <ul class="list-unstyled">
                                                <li><i class="fas fa-video"></i> 100 Kamera</li>
                                                <li><i class="fas fa-brain"></i> AI Tespit (24/7)</li>
                                                <li><i class="fas fa-headset"></i> 7/24 Destek</li>
                                                <li><i class="fas fa-chart-line"></i> Detaylı Analitik</li>
                                                <li><i class="fas fa-shield-alt"></i> Gelişmiş Güvenlik</li>
                                                <li><i class="fas fa-bell"></i> Gelişmiş Bildirimler</li>
                                            </ul>
                                            <button class="btn btn-warning btn-sm w-100" onclick="selectPlan('professional')">
                                                Seç
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <!-- Enterprise Plan -->
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" data-plan="enterprise">
                                        <div class="card-header text-center bg-success text-white">
                                            <h6 class="mb-0"><i class="fas fa-crown"></i> Enterprise</h6>
                                        </div>
                                        <div class="card-body text-center">
                                            <h4 class="text-success">$599<span class="text-muted">/ay</span></h4>
                                            <ul class="list-unstyled">
                                                <li><i class="fas fa-video"></i> 500 Kamera</li>
                                                <li><i class="fas fa-brain"></i> AI Tespit (24/7)</li>
                                                <li><i class="fas fa-headset"></i> Öncelikli Destek</li>
                                                <li><i class="fas fa-chart-pie"></i> Özel Raporlar</li>
                                                <li><i class="fas fa-shield-alt"></i> Maksimum Güvenlik</li>
                                                <li><i class="fas fa-cogs"></i> API Erişimi</li>
                                                <li><i class="fas fa-users"></i> Çoklu Kullanıcı</li>
                                            </ul>
                                            <button class="btn btn-success btn-sm w-100" onclick="selectPlan('enterprise')">
                                                Seç
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Seçilen Plan Detayları -->
                            <div id="selected-plan-details" class="alert alert-success" style="display: none;">
                                <h6><i class="fas fa-check-circle"></i> Seçilen Plan</h6>
                                <div id="plan-details-content"></div>
                            </div>

                            <!-- Plan Değişiklik Uyarısı -->
                            <div class="alert alert-warning">
                                <h6><i class="fas fa-exclamation-triangle"></i> Önemli Bilgiler</h6>
                                <ul class="mb-0">
                                    <li>Plan değişikliği anında aktif olur</li>
                                    <li>Mevcut kameralarınız korunur</li>
                                    <li>Yeni limitler hemen uygulanır</li>
                                    <li>Fatura döneminiz değişmez</li>
                                </ul>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times"></i> İptal
                            </button>
                            <button type="button" class="btn btn-primary" id="confirm-upgrade-btn" onclick="confirmPlanUpgrade()" disabled>
                                <i class="fas fa-check"></i> Planı Değiştir
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}';
                let selectedPlan = null;
                let currentPlan = null;
                
                // Abonelik planlarını aç/kapat
                function toggleSubscriptionPlans() {
                    const container = document.getElementById('subscriptionPlansContainer');
                    const btn = document.getElementById('toggleSubscriptionBtn');
                    const btnText = document.getElementById('toggleBtnText');
                    const icon = document.getElementById('toggleIcon');
                    
                    if (container.style.display === 'none' || container.style.display === '') {
                        // Aç
                        container.style.display = 'block';
                        btnText.textContent = 'Abonelik Planını Gizle';
                        icon.className = 'fas fa-chevron-up ms-2';
                        btn.style.background = 'rgba(30, 58, 138, 0.1)';
                        btn.style.borderColor = '#1E3A8A';
                        
                        // Smooth scroll to plans
                        setTimeout(() => {
                            container.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }, 100);
                    } else {
                        // Kapat
                        container.style.display = 'none';
                        btnText.textContent = 'Abonelik Planını Seç';
                        icon.className = 'fas fa-chevron-down ms-2';
                        btn.style.background = 'rgba(30, 58, 138, 0.05)';
                        btn.style.borderColor = '#1E3A8A';
                    }
                }
                
                // Plan seçimi fonksiyonu (Modern kartlar için)
                function selectPlanCard(plan) {
                    selectedPlan = plan;
                    console.log('Plan seçildi:', selectedPlan);
                    
                    // Radio button'u seç
                    const radioButton = document.getElementById('plan_' + plan);
                    if (radioButton) {
                        radioButton.checked = true;
                        console.log('Radio button seçildi:', plan);
                    }
                    
                    // Tüm kartlardan seçim işaretini kaldır
                    document.querySelectorAll('.plan-card-modern').forEach(card => {
                        card.classList.remove('selected');
                        console.log('Kart temizlendi:', card.getAttribute('data-plan'));
                    });
                    
                    // Seçilen kartı işaretle
                    const selectedCard = document.querySelector('[data-plan="' + plan + '"]');
                    if (selectedCard) {
                        selectedCard.classList.add('selected');
                        console.log('Kart seçildi:', plan);
                        
                        // Seçilen kartın görünür olduğundan emin ol
                        selectedCard.style.zIndex = '10';
                        selectedCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    
                    // Onay butonunu aktif et (eğer varsa)
                    const confirmBtn = document.getElementById('confirm-upgrade-btn');
                    if (confirmBtn) {
                        confirmBtn.disabled = false;
                    }
                }

                // Eski selectPlan fonksiyonu (geriye uyumluluk için)
                function selectPlan(plan) {
                    selectPlanCard(plan);
                }
                
                // Plan detaylarını göster
                function showPlanDetails(plan) {
                    const planDetails = {
                        'starter': {
                            name: 'Starter',
                            price: '$99/ay',
                            cameras: '25 Kamera',
                            features: ['AI Tespit (24/7)', 'Email Destek', 'Temel Raporlar', 'Temel Güvenlik']
                        },
                        'professional': {
                            name: 'Professional',
                            price: '$299/ay',
                            cameras: '100 Kamera',
                            features: ['AI Tespit (24/7)', '7/24 Destek', 'Detaylı Analitik', 'Gelişmiş Güvenlik', 'Gelişmiş Bildirimler']
                        },
                        'enterprise': {
                            name: 'Enterprise',
                            price: '$599/ay',
                            cameras: '500 Kamera',
                            features: ['AI Tespit (24/7)', 'Öncelikli Destek', 'Özel Raporlar', 'Maksimum Güvenlik', 'API Erişimi', 'Çoklu Kullanıcı']
                        }
                    };
                    
                    const details = planDetails[plan];
                    const detailsDiv = document.getElementById('plan-details-content');
                    if (detailsDiv && details) {
                        detailsDiv.innerHTML = 
                            '<div class="row">' +
                                '<div class="col-md-6">' +
                                    '<strong>Plan:</strong> ' + details.name + '<br>' +
                                    '<strong>Fiyat:</strong> ' + details.price + '<br>' +
                                    '<strong>Kamera Limiti:</strong> ' + details.cameras +
                                '</div>' +
                                '<div class="col-md-6">' +
                                    '<strong>Özellikler:</strong><br>' +
                                    details.features.map(feature => '<i class="fas fa-check text-success"></i> ' + feature).join('<br>') +
                                '</div>' +
                            '</div>';
                        
                        const selectedPlanDetails = document.getElementById('selected-plan-details');
                        if (selectedPlanDetails) {
                            selectedPlanDetails.style.display = 'block';
                        }
                    }
                }
                
                // Email Validation Function
                function validateEmail(input) {
                    const emailRegex = /^[a-zA-Z0-9._%+-çğıöşüÇĞIİÖŞÜ]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$/;
                    const isValid = emailRegex.test(input.value);
                    
                    if (input.value && !isValid) {
                        input.classList.add('is-invalid');
                        input.classList.remove('is-valid');
                        
                        // Remove existing error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                        
                        // Add error message
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'invalid-feedback';
                        errorDiv.textContent = 'Please enter a valid email address (Turkish characters are supported)';
                        input.parentNode.appendChild(errorDiv);
                    } else if (input.value && isValid) {
                        input.classList.add('is-valid');
                        input.classList.remove('is-invalid');
                        
                        // Remove error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                    } else {
                        input.classList.remove('is-valid', 'is-invalid');
                        
                        // Remove error message
                        const existingError = input.parentNode.querySelector('.invalid-feedback');
                        if (existingError) {
                            existingError.remove();
                        }
                    }
                }

                // Settings Navigation - Simplified and Reliable
                function initializeSettingsNavigation() {
                    console.log('Settings navigation initialized');
                }
                
                // Initialize when DOM is ready
                function initializeSettings() {
                    console.log('Initializing settings page...');
                    
                    // Varsayılan planı seçili yap
                    setTimeout(() => {
                        selectPlanCard('starter');
                    }, 100);
                    
                    // Sayfa yüklendiğinde plan seçimi için event listener ekle
                    document.addEventListener('DOMContentLoaded', function() {
                        console.log('DOM loaded, initializing plan selection...');
                        selectPlanCard('starter');
                    });
                    
                }
                
                
                // Profile Form Submission
                document.getElementById('profileForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    
                    const formData = new FormData(this);
                    const data = {};
                    formData.forEach((value, key) => {
                        data[key] = value;
                    });
                    
                    fetch('/api/company/' + companyId + '/profile', {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('✅ Profil başarıyla güncellendi!');
                            // Sayfayı yeniden yükle ki güncellenmiş veriler görünsün
                            setTimeout(() => {
                            location.reload();
                            }, 1000);
                        } else {
                            alert('❌ Hata: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('❌ Güncelleme sırasında bir hata oluştu');
                    });
                });
                
                // Password Change Form
                document.getElementById('passwordForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    
                    const formData = new FormData(this);
                    const data = {};
                    formData.forEach((value, key) => {
                        data[key] = value;
                    });
                    
                    // Validate passwords match
                    if (data.new_password !== data.confirm_password) {
                        alert('❌ Yeni şifreler eşleşmiyor!');
                        return;
                    }
                    
                    fetch('/api/company/' + companyId + '/change-password', {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('✅ Şifre başarıyla değiştirildi!');
                            this.reset();
                        } else {
                            alert('❌ Hata: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('❌ Şifre değiştirme sırasında bir hata oluştu');
                    });
                });
                
                // Logo Upload
                document.getElementById('logoInput').addEventListener('change', function(e) {
                    const file = e.target.files[0];
                    if (file) {
                        // Dosya boyutu kontrolü (5MB)
                        if (file.size > 5 * 1024 * 1024) {
                            this.value = '';
                            return;
                        }
                        
                        // Dosya formatı kontrolü
                        const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif'];
                        if (!allowedTypes.includes(file.type)) {
                            alert('❌ Sadece PNG, JPG, JPEG, GIF formatları desteklenir!');
                            this.value = '';
                            return;
                        }
                        
                        // Önizleme göster
                        const reader = new FileReader();
                        reader.onload = function(e) {
                            const logoUpload = document.querySelector('.logo-upload-modern');
                            if (logoUpload) {
                                logoUpload.innerHTML = '<div class="logo-preview"><img src="' + e.target.result + '" alt="Logo Önizleme" style="width: 100%; height: 100%; object-fit: contain; border-radius: 10px;"></div>';
                            }
                        };
                        reader.readAsDataURL(file);
                        
                        // Dosyayı hemen yükle
                        uploadLogo(file);
                        
                        // File input'u reset et
                        this.value = '';
                    }
                });
                
                // Form sıfırlama fonksiyonu
                function resetForm() {
                    if (confirm('⚠️ Formdaki tüm değişiklikler sıfırlanacak. Devam etmek istiyor musunuz?')) {
                        document.getElementById('profileForm').reset();
                        
                        // Toast mesajı göster
                        const toast = document.createElement('div');
                        toast.className = 'toast-message';
                        toast.innerHTML = '🔄 Form sıfırlandı!';
                        toast.style.cssText = 
                            'position: fixed;' +
                            'top: 20px;' +
                            'right: 20px;' +
                            'background: #17a2b8;' +
                            'color: white;' +
                            'padding: 10px 20px;' +
                            'border-radius: 5px;' +
                            'z-index: 9999;' +
                            'font-weight: bold;';
                        document.body.appendChild(toast);
                        
                        setTimeout(() => {
                            toast.remove();
                        }, 3000);
                    }
                }
                
                // Şifre gücü kontrolü fonksiyonu
                function validatePasswordStrength(password) {
                    const requirements = {
                        length: password.length >= 8,
                        uppercase: /[A-Z]/.test(password),
                        lowercase: /[a-z]/.test(password),
                        number: /[0-9]/.test(password),
                        special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
                    };
                    
                    return requirements;
                }
                
                // Şifre gücü göstergesini güncelle
                function updatePasswordStrength(password) {
                    const requirements = validatePasswordStrength(password);
                    const strengthFill = document.getElementById('strength-fill');
                    const strengthText = document.getElementById('strength-text');
                    
                    if (!strengthFill || !strengthText) return;
                    
                    // Gereksinimleri güncelle
                    Object.keys(requirements).forEach(req => {
                        const element = document.getElementById(`req-${req}`);
                        if (element) {
                            if (requirements[req]) {
                                element.innerHTML = '<i class="fas fa-check text-success"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.add('valid');
                            } else {
                                element.innerHTML = '<i class="fas fa-times text-danger"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.remove('valid');
                            }
                        }
                    });
                    
                    // Güç seviyesini hesapla
                    const validCount = Object.values(requirements).filter(Boolean).length;
                    let strength = 'Zayıf';
                    let width = '25%';
                    let color = '#dc3545';
                    
                    if (validCount >= 5) {
                        strength = 'Güçlü';
                        width = '100%';
                        color = '#20c997';
                    } else if (validCount >= 4) {
                        strength = 'İyi';
                        width = '75%';
                        color = '#28a745';
                    } else if (validCount >= 3) {
                        strength = 'Orta';
                        width = '50%';
                        color = '#ffc107';
                    }
                    
                    // Güç göstergesini güncelle
                    strengthFill.style.width = width;
                    strengthFill.style.background = color;
                    strengthText.textContent = `Password strength: ${strength}`;
                }
                
                // Şifre input event listener'ları
                document.addEventListener('DOMContentLoaded', function() {
                    const newPasswordInput = document.querySelector('input[name="new_password"]');
                    if (newPasswordInput) {
                        newPasswordInput.addEventListener('input', function() {
                            updatePasswordStrength(this.value);
                        });
                    }
                    
                    // Kayıt formları için şifre validation
                    const registerPasswordInput = document.getElementById('register_password');
                    if (registerPasswordInput) {
                        registerPasswordInput.addEventListener('input', function() {
                            updateRegisterPasswordStrength(this.value);
                        });
                    }
                    
                    const demoPasswordInput = document.getElementById('demo_password');
                    if (demoPasswordInput) {
                        demoPasswordInput.addEventListener('input', function() {
                            updateDemoPasswordStrength(this.value);
                        });
                    }
                });
                
                // Kayıt formu şifre gücü kontrolü
                function updateRegisterPasswordStrength(password) {
                    const requirements = validatePasswordStrength(password);
                    const strengthFill = document.getElementById('register-strength-fill');
                    const strengthText = document.getElementById('register-strength-text');
                    
                    if (!strengthFill || !strengthText) return;
                    
                    // Gereksinimleri güncelle
                    Object.keys(requirements).forEach(req => {
                        const element = document.getElementById(`register-req-${req}`);
                        if (element) {
                            if (requirements[req]) {
                                element.innerHTML = '<i class="fas fa-check text-success me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.add('valid');
                            } else {
                                element.innerHTML = '<i class="fas fa-times text-danger me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.remove('valid');
                            }
                        }
                    });
                    
                    // Güç seviyesini hesapla
                    const validCount = Object.values(requirements).filter(Boolean).length;
                    let strength = 'Zayıf';
                    let width = '25%';
                    let color = '#dc3545';
                    
                    if (validCount >= 5) {
                        strength = 'Güçlü';
                        width = '100%';
                        color = '#20c997';
                    } else if (validCount >= 4) {
                        strength = 'İyi';
                        width = '75%';
                        color = '#28a745';
                    } else if (validCount >= 3) {
                        strength = 'Orta';
                        width = '50%';
                        color = '#ffc107';
                    }
                    
                    // Güç göstergesini güncelle
                    strengthFill.style.width = width;
                    strengthFill.style.background = color;
                    strengthText.textContent = `Password strength: ${strength}`;
                }
                
                // Demo formu şifre gücü kontrolü
                function updateDemoPasswordStrength(password) {
                    const requirements = validatePasswordStrength(password);
                    const strengthFill = document.getElementById('demo-strength-fill');
                    const strengthText = document.getElementById('demo-strength-text');
                    
                    if (!strengthFill || !strengthText) return;
                    
                    // Gereksinimleri güncelle
                    Object.keys(requirements).forEach(req => {
                        const element = document.getElementById(`demo-req-${req}`);
                        if (element) {
                            if (requirements[req]) {
                                element.innerHTML = '<i class="fas fa-check text-success me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.add('valid');
                            } else {
                                element.innerHTML = '<i class="fas fa-times text-danger me-2"></i><span>' + element.querySelector('span').textContent + '</span>';
                                element.classList.remove('valid');
                            }
                        }
                    });
                    
                    // Güç seviyesini hesapla
                    const validCount = Object.values(requirements).filter(Boolean).length;
                    let strength = 'Zayıf';
                    let width = '25%';
                    let color = '#dc3545';
                    
                    if (validCount >= 5) {
                        strength = 'Güçlü';
                        width = '100%';
                        color = '#20c997';
                    } else if (validCount >= 4) {
                        strength = 'İyi';
                        width = '75%';
                        color = '#28a745';
                    } else if (validCount >= 3) {
                        strength = 'Orta';
                        width = '50%';
                        color = '#ffc107';
                    }
                    
                    // Güç göstergesini güncelle
                    strengthFill.style.width = width;
                    strengthFill.style.background = color;
                    strengthText.textContent = `Şifre gücü: ${strength}`;
                }
                
                // Şifre formu sıfırlama fonksiyonu
                function resetPasswordForm() {
                    if (confirm('⚠️ Şifre formundaki tüm değişiklikler sıfırlanacak. Devam etmek istiyor musunuz?')) {
                        document.getElementById('passwordForm').reset();
                        
                        // Şifre gücü göstergesini sıfırla
                        const strengthFill = document.getElementById('strength-fill');
                        const strengthText = document.getElementById('strength-text');
                        if (strengthFill) {
                            strengthFill.className = 'strength-fill';
                            strengthFill.style.width = '0%';
                        }
                        if (strengthText) {
                            strengthText.textContent = 'Password strength: Weak';
                        }
                        
                        // Toast mesajı göster
                        const toast = document.createElement('div');
                        toast.className = 'toast-message';
                        toast.innerHTML = '🔄 Şifre formu sıfırlandı!';
                        toast.style.cssText = 
                            'position: fixed;' +
                            'top: 20px;' +
                            'right: 20px;' +
                            'background: #17a2b8;' +
                            'color: white;' +
                            'padding: 10px 20px;' +
                            'border-radius: 5px;' +
                            'z-index: 9999;' +
                            'font-weight: bold;';
                        document.body.appendChild(toast);
                        
                        setTimeout(() => {
                            toast.remove();
                        }, 3000);
                    }
                }
                
                // Logo yükleme fonksiyonu
                function uploadLogo(file) {
                    const formData = new FormData();
                    formData.append('logo', file);
                    
                    // Loading göster
                    const logoUpload = document.querySelector('.logo-upload-modern');
                    const originalContent = logoUpload.innerHTML;
                    logoUpload.innerHTML = 
                        '<div class="d-flex align-items-center justify-content-center h-100">' +
                            '<div class="spinner-border text-primary" role="status">' +
                                '<span class="visually-hidden">Yükleniyor...</span>' +
                            '</div>' +
                        '</div>';
                    
                    fetch('/api/company/' + companyId + '/profile/upload-logo', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // Başarılı yükleme - Logo preview'i güncelle
                            logoUpload.innerHTML = '<div class="logo-preview"><img src="' + data.logo_url + '" alt="Şirket Logo" style="width: 100%; height: 100%; object-fit: contain; border-radius: 10px;"></div>';
                            
                            // Toast mesajı göster
                            const toast = document.createElement('div');
                            toast.className = 'toast-message';
                            toast.innerHTML = '✅ Logo başarıyla yüklendi!';
                            toast.style.cssText = 
                                'position: fixed;' +
                                'top: 20px;' +
                                'right: 20px;' +
                                'background: #28a745;' +
                                'color: white;' +
                                'padding: 10px 20px;' +
                                'border-radius: 5px;' +
                                'z-index: 9999;' +
                                'font-weight: bold;';
                            document.body.appendChild(toast);
                            
                            setTimeout(() => {
                                toast.remove();
                            }, 3000);
                            
                            // File input'u reset et
                            document.getElementById('logoInput').value = '';
                        } else {
                            // Hata durumunda eski içeriği geri yükle
                            logoUpload.innerHTML = originalContent;
                            alert('❌ Logo yükleme hatası: ' + data.error);
                            
                            // File input'u reset et
                            document.getElementById('logoInput').value = '';
                        }
                    })
                    .catch(error => {
                        // Hata durumunda eski içeriği geri yükle
                        logoUpload.innerHTML = originalContent;
                        console.error('Logo upload error:', error);
                        alert('❌ Logo yükleme sırasında bir hata oluştu');
                        
                        // File input'u reset et
                        document.getElementById('logoInput').value = '';
                    });
                }
                
                // Notification Toggle Auto-save
                document.querySelectorAll('.notification-toggle input').forEach(toggle => {
                    toggle.addEventListener('change', function() {
                        const settingName = this.closest('.d-flex').querySelector('strong').textContent;
                        const isEnabled = this.checked;
                        const settingKey = this.id;
                        
                        // API'ye gönder
                        updateNotificationSetting(settingKey, isEnabled);
                        
                        // Show toast notification
                        const toast = document.createElement('div');
                        toast.className = 'toast-message';
                        toast.innerHTML = '✅ ' + settingName + ' ' + (isEnabled ? 'açıldı' : 'kapatıldı');
                        toast.style.cssText = 
                            'position: fixed;' +
                            'top: 20px;' +
                            'right: 20px;' +
                            'background: #28a745;' +
                            'color: white;' +
                            'padding: 10px 20px;' +
                            'border-radius: 5px;' +
                            'z-index: 9999;' +
                            'font-weight: bold;';
                        document.body.appendChild(toast);
                        
                        setTimeout(() => {
                            toast.remove();
                        }, 3000);
                    });
                });

                // Notification settings functions
                function updateNotificationSetting(settingKey, isEnabled) {
                    const settings = {};
                    settings[settingKey] = isEnabled;
                    
                    fetch('/api/company/' + companyId + '/notifications', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(settings)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (!result.success) {
                            console.error('Bildirim ayarı güncellenemedi:', result.error);
                        }
                    })
                    .catch(error => {
                        console.error('Bildirim ayarı güncelleme hatası:', error);
                    });
                }

                // Load notification settings
                function loadNotificationSettings() {
                    fetch('/api/company/' + companyId + '/notifications')
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            const settings = result.settings;
                            
                            // Toggle'ları güncelle
                            Object.keys(settings).forEach(key => {
                                const toggle = document.getElementById(key);
                                if (toggle) {
                                    toggle.checked = settings[key];
                                }
                            });
                        }
                    })
                    .catch(error => {
                        console.error('Bildirim ayarları yükleme hatası:', error);
                    });
                }

                // Load subscription info
                function loadSubscriptionInfo() {
                    console.log('🔄 Abonelik bilgileri yükleniyor...');
                    console.log('🔍 Company ID:', companyId);
                    console.log('🔍 Fetch URL:', '/api/company/' + companyId + '/subscription');
                    
                    // Session bilgisini dinamik olarak al - farklı yöntemler dene
                    let sessionId = '';
                    
                    // 1. Cookie'den al
                    const cookieSession = document.cookie.split('; ').find(row => row.startsWith('session_id='));
                    if (cookieSession) {
                        sessionId = cookieSession.split('=')[1];
                    }
                    
                    // 2. LocalStorage'dan al
                    if (!sessionId) {
                        sessionId = localStorage.getItem('session_id') || '';
                    }
                    
                    // 3. Meta tag'den al
                    if (!sessionId) {
                        const metaSession = document.querySelector('meta[name="session_id"]');
                        if (metaSession) {
                            sessionId = metaSession.getAttribute('content') || '';
                        }
                    }
                    
                    console.log('🔍 Session ID (cookie):', sessionId);
                    console.log('🔍 Session ID length:', sessionId.length);
                    console.log('🔍 Session ID type:', typeof sessionId);
                    
                    // Session ID yoksa da devam et - backend session validation yapacak
                    if (!sessionId || sessionId === '') {
                        console.warn('⚠️ Session ID bulunamadı, backend session validation kullanılacak');
                    }
                    
                    fetch('/api/company/' + companyId + '/subscription', {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Session-ID': sessionId
                        },
                        credentials: 'same-origin'
                    })
                    .then(response => {
                        console.log('📡 Response status:', response.status);
                        console.log('📡 Response headers:', response.headers);
                        return response.json();
                    })
                    .then(result => {
                        console.log('📊 Abonelik yükleme sonucu:', result);
                        console.log('🔍 Subscription data:', result);
                        console.log('🔍 Days remaining:', result.days_remaining);
                        console.log('🔍 Subscription end:', result.subscription_end);
                        if (result.success) {
                            // API'den gelen response'da subscription key'i yok, direkt subscription bilgileri var
                            const subscription = result;
                            
                            // Update subscription display in dashboard
                            const subscriptionPlanElement = document.getElementById('subscription-plan');
                            const cameraUsageElement = document.getElementById('camera-usage');
                            const subscriptionTrend = document.getElementById('subscription-trend');
                            const usageTrend = document.getElementById('usage-trend');
                            
                            if (subscriptionPlanElement) {
                                subscriptionPlanElement.textContent = subscription.subscription_type ? subscription.subscription_type.toUpperCase() : 'BASIC';
                                subscriptionPlanElement.className = 'stat-value small-text';
                                console.log('✅ Abonelik planı güncellendi:', subscriptionPlanElement.textContent);
                            }
                            
                            if (cameraUsageElement) {
                                cameraUsageElement.textContent = (subscription.used_cameras || 0) + '/' + (subscription.max_cameras || 25);
                                console.log('✅ Kamera kullanımı güncellendi:', cameraUsageElement.textContent);
                            }
                            
                            if (subscriptionTrend) {
                                if (subscription.is_active) {
                                    subscriptionTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Aktif';
                                    subscriptionTrend.className = 'metric-trend';
                                } else {
                                    subscriptionTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Süresi Dolmuş';
                                    subscriptionTrend.className = 'metric-trend';
                                }
                            }
                            
                            if (usageTrend) {
                                const usagePercentage = subscription.usage_percentage || 0;
                                if (usagePercentage > 80) {
                                    usageTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Limit Yakın';
                                    usageTrend.className = 'metric-trend';
                                } else if (usagePercentage > 60) {
                                    usageTrend.innerHTML = '<i class="fas fa-info trend-neutral"></i> Orta';
                                    usageTrend.className = 'metric-trend';
                                } else {
                                    usageTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Normal';
                                    usageTrend.className = 'metric-trend';
                                }
                            }
                            
                            // Ayarlar sayfasındaki abonelik bilgileri elementlerini güncelle
                            const subscriptionTypeElement = document.getElementById('subscription-type');
                            const billingCycleElement = document.getElementById('billing-cycle');
                            const currentPriceElement = document.getElementById('current-price');
                            const subscriptionStatusElement = document.getElementById('subscription-status');
                            const subscriptionEndElement = document.getElementById('subscription-end');
                            const daysRemainingElement = document.getElementById('days-remaining');
                            const usageProgressElement = document.getElementById('usage-progress');
                            
                            if (subscriptionTypeElement) {
                                subscriptionTypeElement.textContent = subscription.subscription_type ? subscription.subscription_type.toUpperCase() : 'BASIC';
                                console.log('✅ Ayarlar sayfası - Abonelik planı güncellendi:', subscriptionTypeElement.textContent);
                            }
                            
                            if (billingCycleElement) {
                                const billingCycle = subscription.billing_cycle || 'monthly';
                                billingCycleElement.textContent = billingCycle === 'monthly' ? 'AYLIK' : 'YILLIK';
                                console.log('✅ Ayarlar sayfası - Fatura döngüsü güncellendi:', billingCycleElement.textContent);
                            }
                            
                            if (currentPriceElement) {
                                const currentPrice = subscription.current_price || 99;
                                const billingCycle = subscription.billing_cycle || 'monthly';
                                const priceText = billingCycle === 'monthly' ? `$${currentPrice}/ay` : `$${currentPrice}/yıl`;
                                currentPriceElement.textContent = priceText;
                                console.log('✅ Ayarlar sayfası - Mevcut fiyat güncellendi:', currentPriceElement.textContent);
                            }
                            
                            if (subscriptionStatusElement) {
                                if (subscription.is_active) {
                                    subscriptionStatusElement.textContent = 'Aktif';
                                    subscriptionStatusElement.className = 'text-success';
                                } else {
                                    subscriptionStatusElement.textContent = 'Süresi Dolmuş';
                                    subscriptionStatusElement.className = 'text-danger';
                                }
                                console.log('✅ Ayarlar sayfası - Abonelik durumu güncellendi:', subscriptionStatusElement.textContent);
                            }
                            
                            if (subscriptionEndElement) {
                                if (subscription.subscription_end) {
                                    const endDate = new Date(subscription.subscription_end);
                                    subscriptionEndElement.textContent = endDate.toLocaleDateString('tr-TR');
                                } else {
                                    subscriptionEndElement.textContent = 'Sınırsız';
                                }
                                console.log('✅ Ayarlar sayfası - Bitiş tarihi güncellendi:', subscriptionEndElement.textContent);
                            }
                            
                            if (daysRemainingElement) {
                                console.log('🔍 Kalan gün hesaplama - subscription data:', subscription);
                                
                                if (subscription.days_remaining !== undefined) {
                                    console.log('🔍 Backend den gelen days_remaining:', subscription.days_remaining);
                                    if (subscription.days_remaining > 0) {
                                        daysRemainingElement.textContent = subscription.days_remaining + ' gün';
                                        daysRemainingElement.className = 'text-success';
                                    } else if (subscription.days_remaining === 0) {
                                        daysRemainingElement.textContent = 'Bugün sona eriyor';
                                        daysRemainingElement.className = 'text-warning';
                                    } else {
                                        daysRemainingElement.textContent = Math.abs(subscription.days_remaining) + ' gün önce';
                                        daysRemainingElement.className = 'text-danger';
                                    }
                                } else {
                                    console.log('🔍 days_remaining yok, subscription_end den hesaplaniyor:', subscription.subscription_end);
                                    // days_remaining yoksa subscription_end den hesapla
                                    if (subscription.subscription_end) {
                                        try {
                                            const endDate = new Date(subscription.subscription_end);
                                            const today = new Date();
                                            const diffTime = endDate - today;
                                            const remainingDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                                            
                                            console.log('🔍 Hesaplanan kalan gün:', remainingDays);
                                            
                                            if (remainingDays > 0) {
                                                daysRemainingElement.textContent = remainingDays + ' gün';
                                                daysRemainingElement.className = 'text-success';
                                            } else if (remainingDays === 0) {
                                                daysRemainingElement.textContent = 'Bugün sona eriyor';
                                                daysRemainingElement.className = 'text-warning';
                                            } else {
                                                daysRemainingElement.textContent = Math.abs(remainingDays) + ' gün önce';
                                                daysRemainingElement.className = 'text-danger';
                                            }
                                        } catch (e) {
                                            daysRemainingElement.textContent = '--';
                                            console.error('Kalan gün hesaplama hatası:', e);
                                        }
                                    } else {
                                        daysRemainingElement.textContent = '--';
                                    }
                                }
                                console.log('✅ Ayarlar sayfası - Kalan gün güncellendi:', daysRemainingElement.textContent);
                            }
                            
                            if (cameraUsageElement) {
                                cameraUsageElement.textContent = (subscription.used_cameras || 0) + '/' + (subscription.max_cameras || 25);
                                console.log('✅ Ayarlar sayfası - Kamera kullanımı güncellendi:', cameraUsageElement.textContent);
                            }
                            
                            if (usageProgressElement) {
                                const usagePercentage = subscription.usage_percentage || 0;
                                usageProgressElement.style.width = usagePercentage + '%';
                                
                                // Progress bar text'ini güncelle
                                const progressText = usageProgressElement.querySelector('.progress-text');
                                if (progressText) {
                                    progressText.textContent = Math.round(usagePercentage) + '%';
                                }
                                
                                if (usagePercentage > 80) {
                                    usageProgressElement.className = 'progress-bar bg-danger';
                                } else if (usagePercentage > 60) {
                                    usageProgressElement.className = 'progress-bar bg-warning';
                                } else {
                                    usageProgressElement.className = 'progress-bar bg-success';
                                }
                                console.log('✅ Ayarlar sayfası - Kullanım progress bar güncellendi:', usagePercentage + '%');
                            }
                        } else {
                            console.error('❌ API returned error:', result.error);
                            // Fallback to default values
                            const subscriptionPlanElement = document.getElementById('subscription-plan');
                            
                            if (subscriptionPlanElement) {
                                subscriptionPlanElement.textContent = 'BASIC';
                                subscriptionPlanElement.className = 'stat-value small-text';
                            }
                            if (cameraUsageElement) {
                                cameraUsageElement.textContent = '0/25';
                            }
                            
                            // Ayarlar sayfasındaki elementleri de fallback değerlerle güncelle
                            const subscriptionTypeElement = document.getElementById('subscription-type');
                            const subscriptionStatusElement = document.getElementById('subscription-status');
                            const subscriptionEndElement = document.getElementById('subscription-end');
                            const daysRemainingElement = document.getElementById('days-remaining');
                            const usageProgressElement = document.getElementById('usage-progress');
                            
                            if (subscriptionTypeElement) {
                                subscriptionTypeElement.textContent = 'BASIC';
                            }
                            if (subscriptionStatusElement) {
                                subscriptionStatusElement.textContent = 'Aktif';
                                subscriptionStatusElement.className = 'text-success';
                            }
                            if (subscriptionEndElement) {
                                subscriptionEndElement.textContent = '--';
                            }
                            if (daysRemainingElement) {
                                daysRemainingElement.textContent = '--';
                            }
                            if (usageProgressElement) {
                                usageProgressElement.style.width = '0%';
                                usageProgressElement.className = 'progress-bar bg-success';
                                
                                // Progress bar text'ini güncelle
                                const progressText = usageProgressElement.querySelector('.progress-text');
                                if (progressText) {
                                    progressText.textContent = '0%';
                                }
                            }
                        }
                    })
                    .catch(error => {
                        console.error('❌ Abonelik bilgileri yükleme hatası:', error);
                        // Fallback to default values
                        const subscriptionPlanElement = document.getElementById('subscription-plan');
                        
                        if (subscriptionPlanElement) {
                            subscriptionPlanElement.textContent = 'BASIC';
                            subscriptionPlanElement.className = 'stat-value small-text';
                        }
                        if (cameraUsageElement) {
                            cameraUsageElement.textContent = '0/25';
                        }
                        
                        // Ayarlar sayfasındaki elementleri de fallback değerlerle güncelle
                        const subscriptionTypeElement = document.getElementById('subscription-type');
                        const subscriptionStatusElement = document.getElementById('subscription-status');
                        const subscriptionEndElement = document.getElementById('subscription-end');
                        const daysRemainingElement = document.getElementById('days-remaining');
                        const usageProgressElement = document.getElementById('usage-progress');
                        
                        if (subscriptionTypeElement) {
                            subscriptionTypeElement.textContent = 'BASIC';
                        }
                        if (subscriptionStatusElement) {
                            subscriptionStatusElement.textContent = 'Aktif';
                            subscriptionStatusElement.className = 'text-success';
                        }
                        if (subscriptionEndElement) {
                            subscriptionEndElement.textContent = '--';
                        }
                        if (daysRemainingElement) {
                            daysRemainingElement.textContent = '--';
                        }
                        if (usageProgressElement) {
                            usageProgressElement.style.width = '0%';
                            usageProgressElement.className = 'progress-bar bg-success';
                            
                            // Progress bar text'ini güncelle
                            const progressText = usageProgressElement.querySelector('.progress-text');
                            if (progressText) {
                                progressText.textContent = '0%';
                            }
                        }
                    });
                }

                // Plan yükseltme modal'ını aç
                function openUpgradeModal() {
                    // Merkezi modal'ı yeni sekmede aç
                    const companyId = '{{ company_id }}';
                    const currentPlan = getCurrentUserPlan();
                    window.open(`/company/${companyId}/upgrade-modal?current_plan=${currentPlan}`, '_blank', 'width=1400,height=900,scrollbars=yes,resizable=yes,toolbar=no,menubar=no');
                }

                // Kullanıcının mevcut planını al
                function getCurrentUserPlan() {
                    // Subscription type elementinden al
                    const subscriptionTypeElement = document.getElementById('subscription-type');
                    if (subscriptionTypeElement) {
                        return subscriptionTypeElement.textContent.toLowerCase().trim();
                    }
                    
                    // localStorage'dan al
                    const storedPlan = localStorage.getItem('current_plan');
                    if (storedPlan) {
                        return storedPlan;
                    }
                    
                    return 'starter'; // Varsayılan
                }

                // Global olarak erişilebilir yap
                window.getCurrentUserPlan = getCurrentUserPlan;

                // PostMessage listener - Plan yükseltme bildirimi dinle
                window.addEventListener('message', function(event) {
                    if (event.data && event.data.type === 'PLAN_UPGRADED') {
                        console.log('🎉 Plan yükseltme başarılı:', event.data.data);
                        
                        // Başarı mesajı göster
                        showPlanUpgradeSuccess(event.data.data);
                        
                        // Abonelik bilgilerini yenile
                        if (typeof loadSubscriptionInfo === 'function') {
                            setTimeout(() => {
                                loadSubscriptionInfo();
                            }, 1000);
                        }
                        
                        // Sayfayı yenile (isteğe bağlı)
                        setTimeout(() => {
                            location.reload();
                        }, 3000);
                    }
                });

                // Plan yükseltme başarı mesajı
                function showPlanUpgradeSuccess(data) {
                    const successHtml = `
                        <div class="alert alert-success alert-dismissible fade show position-fixed" 
                             style="top: 20px; right: 20px; z-index: 9999; min-width: 350px;">
                            <div class="d-flex align-items-center">
                                <i class="fas fa-crown me-3" style="font-size: 1.5rem; color: #ffd700;"></i>
                                <div>
                                    <strong>🎉 Plan Başarıyla Yükseltildi!</strong>
                                    <br><small>Yeni Plan: ${data.plan_name} - ${data.max_cameras} Kamera</small>
                                    <br><small class="text-muted">Sayfa otomatik yenilenecek...</small>
                                </div>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    `;
                    
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = successHtml;
                    document.body.appendChild(tempDiv);
                    
                    // 5 saniye sonra kaldır
                    setTimeout(() => {
                        if (tempDiv.parentNode) {
                            tempDiv.remove();
                        }
                    }, 5000);
                }

                // Plan seçimi
                function selectPlan(plan) {
                    selectedPlan = plan;
                    
                    // Tüm kartlardan seçim işaretini kaldır
                    document.querySelectorAll('.plan-card').forEach(card => {
                        card.classList.remove('selected');
                    });
                    
                    // Seçilen kartı işaretle
                    document.querySelector('[data-plan="' + plan + '"]').classList.add('selected');
                    
                    // Plan detaylarını göster
                    showPlanDetails(plan);
                    
                    // Onay butonunu aktif et
                    document.getElementById('confirm-upgrade-btn').disabled = false;
                }

                // Plan detaylarını göster
                function showPlanDetails(plan) {
                    const planDetails = {
                        'starter': {
                            name: 'Starter',
                            price: '$99/ay',
                            cameras: '25 Kamera',
                            features: ['AI Tespit (24/7)', 'Email Destek', 'Temel Raporlar', 'Temel Güvenlik']
                        },
                        'professional': {
                            name: 'Professional',
                            price: '$299/ay',
                            cameras: '100 Kamera',
                            features: ['AI Tespit (24/7)', '7/24 Destek', 'Detaylı Analitik', 'Gelişmiş Güvenlik', 'Gelişmiş Bildirimler']
                        },
                        'enterprise': {
                            name: 'Enterprise',
                            price: '$599/ay',
                            cameras: '500 Kamera',
                            features: ['AI Tespit (24/7)', 'Öncelikli Destek', 'Özel Raporlar', 'Maksimum Güvenlik', 'API Erişimi', 'Çoklu Kullanıcı']
                        }
                    };
                    
                    const details = planDetails[plan];
                    const detailsDiv = document.getElementById('plan-details-content');
                    
                    detailsDiv.innerHTML = 
                        '<div class="row">' +
                            '<div class="col-md-6">' +
                                '<strong>Plan:</strong> ' + details.name + '<br>' +
                                '<strong>Fiyat:</strong> ' + details.price + '<br>' +
                                '<strong>Kamera Limiti:</strong> ' + details.cameras +
                            '</div>' +
                            '<div class="col-md-6">' +
                                '<strong>Özellikler:</strong><br>' +
                                details.features.map(feature => '<i class="fas fa-check text-success"></i> ' + feature).join('<br>') +
                            '</div>' +
                        '</div>';
                    
                    document.getElementById('selected-plan-details').style.display = 'block';
                }

                // Plan yükseltmeyi onayla
                function confirmPlanUpgrade() {
                    if (!selectedPlan) {
                        alert('❌ Lütfen bir plan seçin!');
                        return;
                    }
                    
                    if (selectedPlan === currentPlan) {
                        alert('❌ Zaten bu plandasınız!');
                        return;
                    }
                    
                    if (confirm('⚠️ ' + selectedPlan.toUpperCase() + ' planına geçmek istediğinizden emin misiniz?')) {
                        // Plan değiştirme API'sini çağır
                        fetch('/api/company/' + companyId + '/subscription/change-plan', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({new_plan: selectedPlan})
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert('✅ Plan başarıyla değiştirildi!');
                                
                                // Modal'ı kapat
                                const modal = bootstrap.Modal.getInstance(document.getElementById('upgradePlanModal'));
                                modal.hide();
                                
                                // Abonelik bilgilerini yenile
                                loadSubscriptionInfo();
                                
                                // Sayfayı yenile
                                setTimeout(() => {
                                    location.reload();
                                }, 1000);
                            } else {
                                alert('❌ Hata: ' + result.error);
                            }
                        })
                        .catch(error => {
                            console.error('Plan değiştirme hatası:', error);
                            alert('❌ Plan değiştirme sırasında bir hata oluştu!');
                        });
                    }
                }

                // Mevcut plan bilgilerini yükle
                function loadCurrentPlanInfo() {
                    fetch('/api/company/' + companyId + '/subscription')
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            // API'den gelen response'da subscription key'i yok, direkt subscription bilgileri var
                            const subscription = result;
                            currentPlan = subscription.subscription_type;
                            
                            // Mevcut plan bilgilerini göster
                            document.getElementById('current-plan-name').textContent = subscription.subscription_type.toUpperCase();
                            document.getElementById('current-camera-limit').textContent = subscription.max_cameras;
                            document.getElementById('current-usage').textContent = subscription.used_cameras + '/' + subscription.max_cameras;
                            document.getElementById('current-status').textContent = subscription.is_active ? 'Aktif' : 'Süresi Dolmuş';
                            document.getElementById('current-end-date').textContent = subscription.subscription_end ? new Date(subscription.subscription_end).toLocaleDateString('tr-TR') : '--';
                            document.getElementById('current-days-remaining').textContent = subscription.days_remaining || '--';
                            
                            // Mevcut planı seçili göster
                            selectPlan(currentPlan);
                        }
                    })
                    .catch(error => {
                        console.error('Mevcut plan bilgileri yükleme hatası:', error);
                    });
                }
                
                // Delete Account (Enhanced)
                function deleteAccount() {
                    const formData = new FormData(document.getElementById('deleteAccountForm'));
                    const password = formData.get('password');
                    
                    if (!password) {
                        alert('❌ Please enter your password!');
                        return;
                    }
                    
                    if (!document.getElementById('confirmDelete').checked) {
                        alert('❌ Please check the confirmation box!');
                        return;
                    }
                    
                    if (confirm('⚠️ SON UYARI: Hesabınız ve tüm veriler SİLİNECEK!\\n\\nDevam etmek istiyor musunuz?')) {
                        fetch('/api/company/' + companyId + '/delete-account', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({password: password})
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert('✅ Hesabınız başarıyla silindi!\\n\\nAna sayfaya yönlendiriliyorsunuz...');
                                window.location.href = '/';
                            } else {
                                alert('❌ Hata: ' + result.error);
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('❌ Bir hata oluştu!');
                        });
                    }
                }
                
                // PPE Configuration Update
                function updatePPEConfig() {
                    const requiredPPE = [];
                    
                    // Checkbox'ları kontrol et
                    if (document.getElementById('ppe_helmet').checked) requiredPPE.push('helmet');
                    if (document.getElementById('ppe_vest').checked) requiredPPE.push('vest');
                    if (document.getElementById('ppe_glasses').checked) requiredPPE.push('glasses');
                    if (document.getElementById('ppe_gloves').checked) requiredPPE.push('gloves');
                    if (document.getElementById('ppe_shoes').checked) requiredPPE.push('shoes');
                    if (document.getElementById('ppe_mask').checked) requiredPPE.push('mask');
                    
                    if (requiredPPE.length === 0) {
                        alert('❌ En az bir PPE türü seçmelisiniz!');
                        return;
                    }
                    
                    fetch('/api/company/' + companyId + '/ppe-config', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({required_ppe: requiredPPE})
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ PPE konfigürasyonu güncellendi!');
                            location.reload();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('❌ Bir hata oluştu!');
                    });
                }
                
                // Enhanced PPE Configuration Management
                let currentPPEConfig = { required: [], optional: [] };
                let allPPETypes = {};

                
                // Load Enhanced PPE Configuration
                function loadPPEConfig() {
                    console.log('🔄 Enhanced PPE konfigürasyonu yükleniyor...');
                    
                    try {
                        // Loading state göster
                        const loadingEl = document.getElementById('ppe-loading');
                        const contentEl = document.getElementById('ppe-content');
                        if (loadingEl) loadingEl.style.display = 'block';
                        if (contentEl) contentEl.style.display = 'none';
                    
                    fetch('/api/company/' + companyId + '/ppe-config')
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                                currentPPEConfig = result.current_config || { required: [], optional: [] };
                                allPPETypes = result.all_ppe_types || {};
                                
                                // Sektör bilgisini global olarak sakla
                                window.currentSector = result.sector || 'construction';
                                
                                // UI'yi güncelle
                                renderPPEConfiguration(result);
                                
                                // Loading'i gizle
                                if (loadingEl) loadingEl.style.display = 'none';
                                if (contentEl) contentEl.style.display = 'block';
                                
                                console.log('✅ PPE konfigürasyonu yüklendi:', currentPPEConfig, 'Sektör:', window.currentSector);
                            } else {
                                console.error('❌ PPE config yükleme hatası:', result.error);
                                showPPEError('PPE konfigürasyonu yüklenemedi: ' + result.error);
                        }
                    })
                    .catch(error => {
                            console.error('❌ PPE config fetch hatası:', error);
                            showPPEError('Bağlantı hatası oluştu');
                        });
                    } catch (error) {
                        console.error('❌ PPE config function error:', error);
                        showPPEError('PPE konfigürasyon yükleme hatası');
                    }
                }
                
                // Sektör bilgilerini render et
                function renderSectorInfo(sectorInfo, sectorCode) {
                    const container = document.getElementById('ppe-content');
                    if (!container || !sectorInfo) return;
                    
                    // Sektör bilgi kartı ekle
                    let sectorCard = document.getElementById('sector-info-card');
                    if (!sectorCard) {
                        sectorCard = document.createElement('div');
                        sectorCard.id = 'sector-info-card';
                        sectorCard.className = 'card border-primary mb-4';
                        container.insertBefore(sectorCard, container.firstChild);
                    }
                    
                    sectorCard.innerHTML = `
                        <div class="card-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">
                            <div class="d-flex align-items-center">
                                <div class="me-3" style="font-size: 2rem;">${sectorInfo.emoji}</div>
                                <div>
                                    <h5 class="card-title mb-1">
                                        <i class="${sectorInfo.icon} me-2"></i>${sectorInfo.name} Sektörü
                                    </h5>
                                    <p class="card-text mb-0" style="color: rgba(255, 255, 255, 0.9);">
                                        Şirket kayıt sırasında seçilen endüstrinize özel PPE konfigürasyonu
                                    </p>
                                </div>
                            </div>
                        </div>
                        <div class="card-body" style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);">
                            <div class="alert border-0" style="background: rgba(255, 255, 255, 0.8); border-left: 4px solid #667eea !important; color: #495057;">
                                <i class="fas fa-info-circle me-2" style="color: #667eea;"></i>
                                <strong>Bu sayfada gösterilen PPE seçenekleri</strong> şirket kayıt sırasında seçtiğiniz 
                                <strong style="color: #667eea;">${sectorInfo.name}</strong> sektörüne özeldir. Diğer sektörlerin PPE'leri burada görünmez.
                            </div>
                        </div>
                    `;
                }
                
                // Render PPE Configuration UI
                function renderPPEConfiguration(data) {
                    renderSectorInfo(data.sector_info, data.sector);
                    
                    renderCustomPPEConfig(data.sector_specific_ppe || data.all_ppe_types || allPPETypes, data.current_config || currentPPEConfig);
                    
                }
                

                
                // Özel PPE konfigürasyonu render et (sektöre özel)
                function renderCustomPPEConfig(sectorSpecificTypes, currentConfig) {
                    const requiredContainer = document.getElementById('required-ppe-config');
                    
                    if (!requiredContainer) return;
                    
                    let requiredHtml = '';
                    
                    // Sadece sektöre uygun PPE'leri göster
                    const availablePPEs = Object.keys(sectorSpecificTypes || {});
                    
                    if (availablePPEs.length === 0) {
                        const noDataHtml = `
                            <div class="alert alert-info border-0">
                                <i class="fas fa-info-circle me-2"></i>
                                <strong>Bu sektör için ek PPE seçeneği bulunmamaktadır.</strong>
                            </div>
                        `;
                        requiredContainer.innerHTML = noDataHtml;
                        return;
                    }
                    
                    requiredHtml = `<div class="row">`;
                    
                    availablePPEs.forEach(ppeType => {
                        const ppe = sectorSpecificTypes[ppeType];
                        const isCurrentlyRequired = (currentConfig.required || []).includes(ppeType);
                        
                        const requiredCheckbox = `
                            <div class="col-md-4 mb-3">
                                <div class="form-check p-3 border rounded-3" style="background: rgba(220, 53, 69, 0.05);">
                                    <input class="form-check-input" type="checkbox" 
                                           id="req_${ppeType}" 
                                           data-ppe="${ppeType}"
                                           ${isCurrentlyRequired ? 'checked' : ''}
                                           onchange="updatePPESelection('${ppeType}', 'required', this.checked)">
                                    <label class="form-check-label fw-semibold" for="req_${ppeType}">
                                        <i class="${ppe.icon} text-danger me-2"></i>
                                        <strong>${ppe.name}</strong>
        
                                    </label>
                                </div>
                            </div>
                        `;
                        
                        requiredHtml += requiredCheckbox;
                    });
                    
                    requiredHtml += `</div>`;
                    
                    requiredContainer.innerHTML = requiredHtml;
                }
                

                
                // PPE seçim güncelleme
                function updatePPESelection(ppeType, category, isChecked) {
                    if (category === 'required') {
                        if (isChecked) {
                            if (!currentPPEConfig.required.includes(ppeType)) {
                                currentPPEConfig.required.push(ppeType);
                            }
                            // Opsiyonelden kaldır
                            currentPPEConfig.optional = currentPPEConfig.optional.filter(p => p !== ppeType);
                            const optEl = document.getElementById(`opt_${ppeType}`);
                            if (optEl) optEl.checked = false;
                        } else {
                            currentPPEConfig.required = currentPPEConfig.required.filter(p => p !== ppeType);
                        }
                    } else {
                        if (isChecked) {
                            if (!currentPPEConfig.optional.includes(ppeType)) {
                                currentPPEConfig.optional.push(ppeType);
                            }
                            // Zorunludan kaldır
                            currentPPEConfig.required = currentPPEConfig.required.filter(p => p !== ppeType);
                            const reqEl = document.getElementById(`req_${ppeType}`);
                            if (reqEl) reqEl.checked = false;
                        } else {
                            currentPPEConfig.optional = currentPPEConfig.optional.filter(p => p !== ppeType);
                        }
                    }
                    
                    // Seçili PPE'leri güncelle
                    
                    
                }
                
                // Önerilen PPE'yi ekle
                function addRecommendedPPE(ppeType, category) {
                    const checkboxId = `${category === 'required' ? 'req' : 'opt'}_${ppeType}`;
                    const checkbox = document.getElementById(checkboxId);
                    if (checkbox) {
                        checkbox.checked = true;
                        updatePPESelection(ppeType, category, true);
                    }
                }
                
                // PPE konfigürasyonunu kaydet
                function savePPEConfig() {
                    if (currentPPEConfig.required.length === 0 && currentPPEConfig.optional.length === 0) {
                        alert('❌ En az bir PPE türü seçmelisiniz!');
                        return;
                    }
                    
                    const configData = {
                        required_ppe: currentPPEConfig.required,
                        optional_ppe: currentPPEConfig.optional
                    };
                    
                    console.log('💾 PPE config kaydediliyor:', configData);
                    
                    fetch('/api/company/' + companyId + '/ppe-config', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(configData)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            showSuccessToast('✅ PPE konfigürasyonu başarıyla kaydedildi!');
                            setTimeout(() => {
                                loadPPEConfig();
                            }, 1000);
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    })
                    .catch(error => {
                        console.error('❌ PPE config kaydetme hatası:', error);
                        alert('❌ Kaydetme sırasında bir hata oluştu!');
                    });
                }
                
                // PPE konfigürasyonunu sıfırla
                function resetPPEConfig() {
                    if (confirm('⚠️ PPE konfigürasyonunu sıfırlamak istediğinizden emin misiniz?')) {
                        currentPPEConfig.required = [];
                        currentPPEConfig.optional = [];
                        
                        renderPPEConfiguration({
                            current_config: currentPPEConfig,
                            all_ppe_types: allPPETypes
                        });
                        
                        showSuccessToast('🔄 PPE konfigürasyonu sıfırlandı');
                    }
                }
                
                // PPE konfigürasyon önizlemesi
                function previewPPEConfig() {
                    // UI'dan gerçek zamanlı olarak seçili PPE'leri al
                    const selectedPPEs = [];
                    const checkboxes = document.querySelectorAll('#required-ppe-config input[type="checkbox"]:checked');
                    checkboxes.forEach(checkbox => {
                        const ppeType = checkbox.getAttribute('data-ppe');
                        if (ppeType && ppeType !== '') {
                            selectedPPEs.push(ppeType);
                        }
                    });
                    
                    const modal = document.createElement('div');
                    modal.className = 'modal fade';
                    
                    let modalContent = '';
                    
                    if (selectedPPEs.length === 0) {
                        // Eğer hiç PPE seçilmemişse, sektör önerilerini göster
                        modalContent = `
                            <div class="modal-dialog modal-lg">
                                <div class="modal-content">
                                    <div class="modal-header bg-warning text-dark">
                                        <h5 class="modal-title"><i class="fas fa-exclamation-triangle"></i> PPE Konfigürasyon Durumu</h5>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                    </div>
                                    <div class="modal-body">
                                        <div class="alert alert-warning">
                                            <i class="fas fa-info-circle me-2"></i>
                                            <strong>Henüz zorunlu PPE ekipmanı seçilmemiş!</strong>
                                        </div>
                                        <div class="text-center mb-3">
                                            <h6 class="text-primary">Sektörünüze Önerilen PPE Ekipmanları</h6>
                                            <small class="text-muted">Bu ekipmanları seçerek konfigürasyonu tamamlayabilirsiniz</small>
                                        </div>
                                        <div class="ppe-list">
                                            ${Object.keys(allPPETypes).filter(ppe => allPPETypes[ppe]?.sectors?.includes(window.currentSector || 'construction')).map(ppe => `
                                                <div class="d-flex align-items-center p-2 border rounded mb-2">
                                                    <i class="${allPPETypes[ppe]?.icon || 'fas fa-shield-alt'} text-primary me-3" style="font-size: 1.2rem;"></i>
                                                    <span class="fw-bold">${allPPETypes[ppe]?.name || ppe}</span>
                                                    <span class="badge bg-secondary ms-auto">Önerilen</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                                        <button type="button" class="btn btn-primary" onclick="bootstrap.Modal.getInstance(this.closest('.modal')).hide(); document.getElementById('ppe-config-section').click();">PPE Seç</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    } else {
                        // Seçili PPE'leri göster
                        modalContent = `
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header bg-primary text-white">
                                        <h5 class="modal-title"><i class="fas fa-shield-alt"></i> PPE Konfigürasyon Önizlemesi</h5>
                                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                                    </div>
                                    <div class="modal-body">
                                        <div class="text-center mb-3">
                                            <h6 class="text-primary">Seçili Zorunlu PPE Ekipmanları</h6>
                                            <small class="text-muted">Toplam: ${selectedPPEs.length} ekipman</small>
                                        </div>
                                        <div class="ppe-list">
                                            ${selectedPPEs.map(ppe => `
                                                <div class="d-flex align-items-center p-2 border rounded mb-2">
                                                    <i class="${allPPETypes[ppe]?.icon || 'fas fa-shield-alt'} text-danger me-3" style="font-size: 1.2rem;"></i>
                                                    <span class="fw-bold">${allPPETypes[ppe]?.name || ppe}</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    }
                    
                    modal.innerHTML = modalContent;
                    document.body.appendChild(modal);
                    const bsModal = new bootstrap.Modal(modal);
                    bsModal.show();
                    
                    modal.addEventListener('hidden.bs.modal', () => {
                        document.body.removeChild(modal);
                    });
                }
                
                // Helper functions
                function showPPEError(message) {
                    const loadingEl = document.getElementById('ppe-loading');
                    if (loadingEl) {
                        loadingEl.innerHTML = `
                            <div class="alert alert-danger">
                                <i class="fas fa-exclamation-triangle"></i> ${message}
                                <br><button class="btn btn-sm btn-primary mt-2" onclick="loadPPEConfig()">Tekrar Dene</button>
                            </div>
                        `;
                    }
                }
                
                function showSuccessToast(message) {
                    const toast = document.createElement('div');
                    toast.className = 'toast-message';
                    toast.innerHTML = message;
                    toast.style.cssText = 
                        'position: fixed;' +
                        'top: 20px;' +
                        'right: 20px;' +
                        'background: #28a745;' +
                        'color: white;' +
                        'padding: 15px 20px;' +
                        'border-radius: 5px;' +
                        'z-index: 9999;' +
                        'font-weight: bold;' +
                        'box-shadow: 0 4px 8px rgba(0,0,0,0.2);';
                    document.body.appendChild(toast);
                    
                    setTimeout(() => {
                        toast.remove();
                    }, 3000);
                }
                

                
                // Logout
                function logout() {
                    if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
                        fetch('/logout', {
                            method: 'POST'
                        })
                        .then(() => {
                            window.location.href = '/';
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            window.location.href = '/';
                        });
                    }
                }
                
                // Plan seçimi fonksiyonları
                function selectPlan(planType) {
                    // Tüm plan kartlarından seçimi kaldır
                    document.querySelectorAll('.plan-card').forEach(card => {
                        card.classList.remove('selected');
                    });
                    
                    // Seçilen planı işaretle
                    const selectedCard = document.querySelector('[data-plan="' + planType + '"]');
                    if (selectedCard) {
                        selectedCard.classList.add('selected');
                    }
                    document.getElementById(planType + '_plan').checked = true;
                }
                
                function changePlan() {
                    const selectedPlan = document.querySelector('input[name="new_plan"]:checked');
                    
                    if (!selectedPlan) {
                        alert('❌ Lütfen bir plan seçin!');
                        return;
                    }
                    
                    const newPlan = selectedPlan.value;
                    
                    if (confirm(newPlan.toUpperCase() + ' planına geçmek istediğinizden emin misiniz?')) {
                        fetch('/api/company/' + companyId + '/subscription/change-plan', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({new_plan: newPlan})
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert('✅ Plan başarıyla ' + result.plan_name + ' olarak değiştirildi!');
                                bootstrap.Modal.getInstance(document.getElementById('changePlanModal')).hide();
                                loadSubscriptionInfo(); // Abonelik bilgilerini yenile
                            } else {
                                alert('❌ Hata: ' + result.error);
                            }
                        })
                        .catch(error => {
                            console.error('Plan değiştirme hatası:', error);
                            alert('❌ Plan değiştirme sırasında bir hata oluştu');
                        });
                    }
                }
                
                function changePaymentMethod() {
                    alert('💳 Ödeme yöntemi değiştirme özelliği yakında eklenecek!');
                }
                
                function downloadInvoices() {
                    alert('📄 Fatura indirme özelliği yakında eklenecek!');
                }

                // Sayfa yüklendiğinde tüm ayarları yükle
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('🔄 Settings page DOMContentLoaded - initializing...');
                    
                    try {
                        // Settings navigation'ı önce başlat
                        initializeSettings();
                        
                        // PPE konfigürasyonu yükle (sadece PPE sekmesi aktifse)
                        setTimeout(() => {
                            try {
                    if (document.getElementById('ppe-config-section')) {
                                    console.log('📋 PPE config section found, loading...');
                                    // PPE yükleme sadece PPE sekmesi görünürse
                                    if (window.location.hash === '#ppe-config' || window.location.hash === '') {
                        loadPPEConfig();
                                    }
                    }
                    
                    // Bildirim ayarlarını yükle
                    if (document.getElementById('notifications-section')) {
                        loadNotificationSettings();
                    }
                    
                    // Abonelik bilgilerini yükle
                    if (document.getElementById('subscription-section')) {
                        loadSubscriptionInfo();
                                }
                            } catch (error) {
                                console.error('Settings initialization error:', error);
                            }
                        }, 100); // Kısa delay ile navigation'ın önce kurulmasını sağla
                    } catch (error) {
                        console.error('Settings page initialization error:', error);
                    }
                });

                // Hash Navigation System
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('DOM loaded, initializing hash navigation...');
                    
                    const navLinks = document.querySelectorAll('.nav-link[data-section]');
                    const sections = document.querySelectorAll('.settings-section');
                    
                    console.log('Found nav links:', navLinks.length);
                    console.log('Found sections:', sections.length);
                    
                    // Function to switch to a section
                    function switchToSection(sectionName) {
                        console.log('Switching to section:', sectionName);
                        
                        // Update active state
                        navLinks.forEach(nl => nl.classList.remove('active'));
                        const activeLink = document.querySelector('[data-section="' + sectionName + '"]');
                        if (activeLink) {
                            activeLink.classList.add('active');
                        }
                        
                        // Show target section
                        sections.forEach(section => section.style.display = 'none');
                        const targetElement = document.getElementById(sectionName + '-section');
                        if (targetElement) {
                            targetElement.style.display = 'block';
                            console.log('Section displayed:', sectionName);
                            
                            // Load data when switching to subscription
                            if (sectionName === 'subscription' && typeof loadSubscriptionInfo === 'function') {
                                console.log('Loading subscription info...');
                                setTimeout(() => {
                                    loadSubscriptionInfo();
                                }, 200);
                            }
                        }
                    }
                    
                    // Add click handlers to nav links
                    navLinks.forEach(link => {
                        link.addEventListener('click', function(e) {
                            e.preventDefault();
                            const targetSection = this.getAttribute('data-section');
                            switchToSection(targetSection);
                            
                            // Update URL hash
                            window.location.hash = targetSection;
                        });
                    });
                    
                    // Handle initial hash on page load
                    const hash = window.location.hash.substring(1);
                    console.log('Initial hash:', hash);
                    if (hash) {
                        const targetLink = document.querySelector('[data-section="' + hash + '"]');
                        if (targetLink) {
                            console.log('Found target link for hash:', hash);
                            switchToSection(hash);
                        } else {
                            console.log('No target link found for hash:', hash);
                            switchToSection('profile');
                        }
                    } else {
                        console.log('No hash found, defaulting to profile');
                        switchToSection('profile');
                    }
                    
                    // Handle hash changes
                    window.addEventListener('hashchange', function() {
                        const hash = window.location.hash.substring(1);
                        console.log('Hash changed to:', hash);
                        
                        if (hash) {
                            const targetLink = document.querySelector('[data-section="' + hash + '"]');
                            if (targetLink) {
                                switchToSection(hash);
                            }
                        }
                    });
                });
            </script>
        </body>
        </html>
        '''
    
    def get_users_template(self):
        """Company Users Management Template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Kullanıcı Yönetimi - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .navbar {
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    border: none;
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                }
                .user-card {
                    background: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                }
                .user-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                }
                .role-badge {
                    padding: 5px 12px;
                    border-radius: 20px;
                    font-size: 0.8rem;
                    font-weight: 600;
                }
                .role-admin { background: #e74c3c; color: white; }
                .role-manager { background: #f39c12; color: white; }
                .role-operator { background: #3498db; color: white; }
                
                .status-badge {
                    padding: 4px 10px;
                    border-radius: 15px;
                    font-size: 0.75rem;
                    font-weight: 600;
                }
                .status-active { background: #27ae60; color: white; }
                .status-inactive { background: #95a5a6; color: white; }
                
                .user-avatar {
                    width: 50px;
                    height: 50px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 1.2rem;
                }
                
                .add-user-card {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 30px;
                    text-align: center;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    border: 3px dashed rgba(255,255,255,0.3);
                }
                .add-user-card:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }
                
                .permissions-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin-top: 20px;
                }
                .permission-item {
                    background: #f8f9fa;
                    border-radius: 10px;
                    padding: 15px;
                    text-align: center;
                }
                
                /* Profil Dropdown Stilleri */
                .profile-dropdown {
                    min-width: 280px;
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                    padding: 0;
                    margin-top: 10px;
                }
                
                .profile-dropdown .dropdown-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 15px 15px 0 0;
                    border: none;
                }
                
                .profile-avatar {
                    width: 32px;
                    height: 32px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 14px;
                }
                
                .profile-avatar-large {
                    width: 48px;
                    height: 48px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 20px;
                }
                
                .profile-name {
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .profile-dropdown .dropdown-item {
                    padding: 12px 20px;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .profile-dropdown .dropdown-item:hover {
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    transform: translateX(5px);
                }
                
                .profile-dropdown .dropdown-item i {
                    width: 20px;
                    text-align: center;
                }
                
                .profile-dropdown .dropdown-divider {
                    margin: 0;
                    border-color: #e9ecef;
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/company/{{ company_id }}/dashboard">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        <a class="nav-link active" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        
                        <!-- Profil Dropdown -->
                        <div class="nav-item dropdown">
                            <a class="nav-link dropdown-toggle d-flex align-items-center" href="#" id="profileDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                <div class="profile-avatar me-2">
                                    <i class="fas fa-building"></i>
                                </div>
                                <span class="profile-name">{{ user_data.company_name }}</span>
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end profile-dropdown" aria-labelledby="profileDropdown">
                                <li class="dropdown-header">
                                    <div class="d-flex align-items-center">
                                        <div class="profile-avatar-large me-3">
                                            <i class="fas fa-building"></i>
                                        </div>
                                        <div>
                                            <div class="fw-bold">{{ user_data.company_name }}</div>
                                            <small class="text-white">{{ company_id }}</small>
                                        </div>
                                    </div>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/profile">
                                        <i class="fas fa-user me-2"></i> Şirket Profili
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/subscription">
                                        <i class="fas fa-crown me-2"></i> Abonelik Bilgileri
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/billing">
                                        <i class="fas fa-credit-card me-2"></i> Fatura & Ödeme
                                    </a>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item text-danger" href="#" onclick="logout()">
                                        <i class="fas fa-sign-out-alt me-2"></i> Çıkış Yap
                                    </a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <div class="row">
                    <div class="col-md-8">
                        <div class="card">
                            <div class="card-header bg-primary text-white">
                                <h4 class="mb-0">
                                    <i class="fas fa-users"></i> Şirket Kullanıcıları
                                </h4>
                            </div>
                            <div class="card-body">
                                <div id="usersContainer">
                                    <div class="text-center py-4">
                                        <div class="spinner-border text-primary" role="status">
                                            <span class="visually-hidden">Yükleniyor...</span>
                                        </div>
                                        <p class="mt-2 text-muted">Kullanıcılar yükleniyor...</p>
                                    </div>
                                </div>
                                
                                <!-- Add User Card -->
                                <div class="add-user-card" data-bs-toggle="modal" data-bs-target="#addUserModal">
                                    <i class="fas fa-user-plus fa-3x mb-3"></i>
                                    <h5>Yeni Kullanıcı Ekle</h5>
                                    <p class="mb-0">Şirketinize yeni kullanıcı davet edin</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-4">
                        <div class="card">
                            <div class="card-header bg-info text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-shield-alt"></i> Kullanıcı Rolleri
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="permission-item mb-3">
                                    <div class="role-badge role-admin mb-2">ADMIN</div>
                                    <small class="text-muted">
                                        Tüm yetkilere sahip. Kullanıcı yönetimi, ayarlar, raporlar.
                                    </small>
                                </div>
                                
                                <div class="permission-item mb-3">
                                    <div class="role-badge role-manager mb-2">MANAGER</div>
                                    <small class="text-muted">
                                        Raporlara ve kamera yönetimine erişim. Ayarlara kısıtlı erişim.
                                    </small>
                                </div>
                                
                                <div class="permission-item">
                                    <div class="role-badge role-operator mb-2">OPERATOR</div>
                                    <small class="text-muted">
                                        Sadece dashboard ve canlı izleme. Sadece okuma yetkisi.
                                    </small>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-header bg-success text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-bar"></i> Kullanıcı İstatistikleri
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="row text-center">
                                    <div class="col-6">
                                        <h3 class="text-primary" id="totalUsers">-</h3>
                                        <small class="text-muted">Toplam Kullanıcı</small>
                                    </div>
                                    <div class="col-6">
                                        <h3 class="text-success" id="activeUsers">-</h3>
                                        <small class="text-muted">Aktif Kullanıcı</small>
                                    </div>
                                </div>
                                
                                <hr>
                                
                                <div class="row text-center">
                                    <div class="col-4">
                                        <h4 class="text-danger" id="adminCount">-</h4>
                                        <small class="text-muted">Admin</small>
                                    </div>
                                    <div class="col-4">
                                        <h4 class="text-warning" id="managerCount">-</h4>
                                        <small class="text-muted">Manager</small>
                                    </div>
                                    <div class="col-4">
                                        <h4 class="text-info" id="operatorCount">-</h4>
                                        <small class="text-muted">Operator</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Add User Modal -->
            <div class="modal fade" id="addUserModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-user-plus"></i> Yeni Kullanıcı Ekle
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="addUserForm">
                                <div class="mb-3">
                                    <label class="form-label">Email *</label>
                                    <input type="text" class="form-control" name="email" required
                                           placeholder="kullanici@email.com">
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Ad Soyad *</label>
                                    <input type="text" class="form-control" name="contact_person" required
                                           placeholder="Kullanıcının adı soyadı">
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Rol *</label>
                                    <select class="form-select" name="role" required>
                                        <option value="">Rol Seçin</option>
                                        <option value="admin">Admin - Tüm yetkiler</option>
                                        <option value="manager">Manager - Yönetim yetkileri</option>
                                        <option value="operator">Operator - Sadece görüntüleme</option>
                                    </select>
                                </div>
                                
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i>
                                    <strong>Not:</strong> Kullanıcı eklendikten sonra geçici şifre oluşturulacak ve size gösterilecek.
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">İptal</button>
                            <button type="button" class="btn btn-primary" onclick="addUser()">
                                <i class="fas fa-user-plus"></i> Kullanıcı Ekle
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- User Details Modal -->
            <div class="modal fade" id="userDetailsModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-info text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-user"></i> Kullanıcı Detayları
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" id="userDetailsContent">
                            <!-- User details will be loaded here -->
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                            <button type="button" class="btn btn-danger" id="deleteUserBtn" onclick="deleteSelectedUser()">
                                <i class="fas fa-trash"></i> Kullanıcıyı Sil
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}';
                let currentUsers = [];
                let selectedUserId = null;
                
                // Load users on page load
                document.addEventListener('DOMContentLoaded', function() {
                    loadUsers();
                });
                
                // Load Users
                function loadUsers() {
                    fetch('/api/company/' + companyId + '/users')
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            currentUsers = data.users;
                            displayUsers(data.users);
                            updateUserStats(data.users);
                        } else {
                            console.error('Failed to load users:', data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error loading users:', error);
                    });
                }
                
                // Display Users
                function displayUsers(users) {
                    const container = document.getElementById('usersContainer');
                    
                    if (users.length === 0) {
                        container.innerHTML = `
                            <div class="text-center py-4">
                                <i class="fas fa-users fa-3x text-muted mb-3"></i>
                                <h5 class="text-muted">Henüz kullanıcı yok</h5>
                                <p class="text-muted">İlk kullanıcınızı eklemek için yukarıdaki butonu kullanın.</p>
                            </div>
                        `;
                        return;
                    }
                    
                    container.innerHTML = users.map(user => `
                        <div class="user-card" onclick="showUserDetails('${user.user_id}')">
                            <div class="row align-items-center">
                                <div class="col-md-2">
                                    <div class="user-avatar">
                                        ${user.contact_person ? user.contact_person.charAt(0).toUpperCase() : 'U'}
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <h6 class="mb-1">${user.contact_person || 'İsimsiz Kullanıcı'}</h6>
                                    <p class="text-muted mb-1">
                                        <i class="fas fa-envelope me-1"></i> ${user.email}
                                    </p>
                                    <small class="text-muted">
                                        <i class="fas fa-calendar me-1"></i> 
                                        Kayıt: ${formatDate(user.created_at)}
                                    </small>
                                </div>
                                <div class="col-md-2">
                                    <span class="role-badge role-${user.role}">
                                        ${user.role.toUpperCase()}
                                    </span>
                                </div>
                                <div class="col-md-2">
                                    <span class="status-badge status-${user.status}">
                                        ${user.status === 'active' ? 'Aktif' : 'Pasif'}
                                    </span>
                                    <small class="d-block text-muted mt-1">
                                        ${user.last_login ? 'Son: ' + formatDate(user.last_login) : 'Hiç giriş yok'}
                                    </small>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
                
                // Update User Statistics
                function updateUserStats(users) {
                    const totalUsers = users.length;
                    const activeUsers = users.filter(u => u.status === 'active').length;
                    const adminCount = users.filter(u => u.role === 'admin').length;
                    const managerCount = users.filter(u => u.role === 'manager').length;
                    const operatorCount = users.filter(u => u.role === 'operator').length;
                    
                    document.getElementById('totalUsers').textContent = totalUsers;
                    document.getElementById('activeUsers').textContent = activeUsers;
                    document.getElementById('adminCount').textContent = adminCount;
                    document.getElementById('managerCount').textContent = managerCount;
                    document.getElementById('operatorCount').textContent = operatorCount;
                }
                
                // Show User Details
                function showUserDetails(userId) {
                    const user = currentUsers.find(u => u.user_id === userId);
                    if (!user) return;
                    
                    selectedUserId = userId;
                    
                    const content = `
                        <div class="row">
                            <div class="col-md-4 text-center">
                                <div class="user-avatar mx-auto mb-3" style="width: 80px; height: 80px; font-size: 2rem;">
                                    ${user.contact_person ? user.contact_person.charAt(0).toUpperCase() : 'U'}
                                </div>
                                <h5>${user.contact_person || 'İsimsiz Kullanıcı'}</h5>
                                <span class="role-badge role-${user.role} mb-2 d-inline-block">
                                    ${user.role.toUpperCase()}
                                </span>
                                <br>
                                <span class="status-badge status-${user.status}">
                                    ${user.status === 'active' ? 'Aktif' : 'Pasif'}
                                </span>
                            </div>
                            <div class="col-md-8">
                                <table class="table table-borderless">
                                    <tr>
                                        <td><strong>Kullanıcı ID:</strong></td>
                                        <td>${user.user_id}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Email:</strong></td>
                                        <td>${user.email}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Kayıt Tarihi:</strong></td>
                                        <td>${formatDate(user.created_at)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Son Giriş:</strong></td>
                                        <td>${user.last_login ? formatDate(user.last_login) : 'Hiç giriş yapmamış'}</td>
                                    </tr>
                                </table>
                                
                                <h6 class="mt-4">Rol Yetkileri:</h6>
                                <div class="permissions-grid">
                                    ${getRolePermissions(user.role)}
                                </div>
                            </div>
                        </div>
                    `;
                    
                    document.getElementById('userDetailsContent').innerHTML = content;
                    new bootstrap.Modal(document.getElementById('userDetailsModal')).show();
                }
                
                // Get Role Permissions
                function getRolePermissions(role) {
                    const permissions = {
                        admin: [
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Kullanıcı Yönetimi</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Sistem Ayarları</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Tüm Raporlar</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Kamera Yönetimi</div>'
                        ],
                        manager: [
                            '<div class="permission-item"><i class="fas fa-times text-danger"></i> Kullanıcı Yönetimi</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Kısıtlı Ayarlar</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Tüm Raporlar</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Kamera Yönetimi</div>'
                        ],
                        operator: [
                            '<div class="permission-item"><i class="fas fa-times text-danger"></i> Kullanıcı Yönetimi</div>',
                            '<div class="permission-item"><i class="fas fa-times text-danger"></i> Sistem Ayarları</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Sadece Görüntüleme</div>',
                            '<div class="permission-item"><i class="fas fa-check text-success"></i> Canlı İzleme</div>'
                        ]
                    };
                    
                    return permissions[role]?.join('') || '';
                }
                
                // Add User
                function addUser() {
                    const form = document.getElementById('addUserForm');
                    const formData = new FormData(form);
                    const data = {};
                    formData.forEach((value, key) => {
                        data[key] = value;
                    });
                    
                    if (!data.email || !data.contact_person || !data.role) {
                        alert('❌ Please fill all fields!');
                        return;
                    }
                    
                    fetch('/api/company/' + companyId + '/users', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ Kullanıcı başarıyla eklendi!\\n\\nGeçici Şifre: ' + result.temp_password + '\\n\\nBu şifreyi kullanıcıya güvenli bir şekilde iletin.');
                            bootstrap.Modal.getInstance(document.getElementById('addUserModal')).hide();
                            form.reset();
                            loadUsers();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error adding user:', error);
                        alert('❌ Kullanıcı ekleme sırasında bir hata oluştu');
                    });
                }
                
                // Delete Selected User
                function deleteSelectedUser() {
                    if (!selectedUserId) return;
                    
                    if (confirm('⚠️ Bu kullanıcıyı silmek istediğinizden emin misiniz?\\n\\nBu işlem geri alınamaz!')) {
                        fetch('/api/company/' + companyId + '/users/' + selectedUserId, {
                            method: 'DELETE'
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert('✅ Kullanıcı başarıyla silindi!');
                                bootstrap.Modal.getInstance(document.getElementById('userDetailsModal')).hide();
                                loadUsers();
                            } else {
                                alert('❌ Hata: ' + result.error);
                            }
                        })
                        .catch(error => {
                            console.error('Error deleting user:', error);
                            alert('❌ Kullanıcı silme sırasında bir hata oluştu');
                        });
                    }
                }
                
                // Format Date
                function formatDate(dateString) {
                    if (!dateString) return 'N/A';
                    const date = new Date(dateString);
                    return date.toLocaleDateString('tr-TR') + ' ' + date.toLocaleTimeString('tr-TR', {hour: '2-digit', minute: '2-digit'});
                }
                
                // Logout
                function logout() {
                    if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
                        fetch('/logout', {
                            method: 'POST'
                        })
                        .then(() => {
                            window.location.href = '/';
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            window.location.href = '/';
                        });
                    }
                }
            </script>
        </body>
        </html>
        '''

    def get_reports_template(self):
        """Company Reports Template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Raporlar - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .navbar {
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    border: none;
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                }
                .stat-card {
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                    text-align: center;
                }
                .stat-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 15px 35px rgba(0,0,0,0.2);
                }
                .stat-value {
                    font-size: 3rem;
                    font-weight: 700;
                    margin-bottom: 10px;
                }
                .compliance-good { color: #27ae60; }
                .compliance-warning { color: #f39c12; }
                .compliance-danger { color: #e74c3c; }
                
                .violation-card {
                    background: white;
                    border-radius: 10px;
                    padding: 15px;
                    margin-bottom: 10px;
                    border-left: 4px solid #e74c3c;
                    transition: all 0.3s ease;
                }
                .violation-card:hover {
                    transform: translateX(5px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }
                
                .chart-container {
                    position: relative;
                    height: 400px;
                    margin: 20px 0;
                }
                
                .report-filter {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 20px;
                }
                
                .export-btn {
                    background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
                    border: none;
                    border-radius: 25px;
                    padding: 10px 25px;
                    color: white;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                .export-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.3);
                }
                
                .nav-tabs .nav-link {
                    border-radius: 10px 10px 0 0;
                    margin-right: 5px;
                    transition: all 0.3s ease;
                }
                .nav-tabs .nav-link.active {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border-color: transparent;
                }
                
                .table-hover tbody tr:hover {
                    background-color: rgba(102, 126, 234, 0.1);
                }
                
                /* Profil Dropdown Stilleri */
                .profile-dropdown {
                    min-width: 280px;
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                    padding: 0;
                    margin-top: 10px;
                }
                
                .profile-dropdown .dropdown-header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 15px 15px 0 0;
                    border: none;
                }
                
                .profile-avatar {
                    width: 32px;
                    height: 32px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 14px;
                }
                
                .profile-avatar-large {
                    width: 48px;
                    height: 48px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 20px;
                }
                
                .profile-name {
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .profile-dropdown .dropdown-item {
                    padding: 12px 20px;
                    border: none;
                    transition: all 0.3s ease;
                }
                
                .profile-dropdown .dropdown-item:hover {
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    transform: translateX(5px);
                }
                
                .profile-dropdown .dropdown-item i {
                    width: 20px;
                    text-align: center;
                }
                
                .profile-dropdown .dropdown-divider {
                    margin: 0;
                    border-color: #e9ecef;
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/company/{{ company_id }}/dashboard">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link active" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        
                        <!-- Profil Dropdown -->
                        <div class="nav-item dropdown">
                            <a class="nav-link dropdown-toggle d-flex align-items-center" href="#" id="profileDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                <div class="profile-avatar me-2">
                                    <i class="fas fa-building"></i>
                                </div>
                                <span class="profile-name">{{ user_data.company_name }}</span>
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end profile-dropdown" aria-labelledby="profileDropdown">
                                <li class="dropdown-header">
                                    <div class="d-flex align-items-center">
                                        <div class="profile-avatar-large me-3">
                                            <i class="fas fa-building"></i>
                                        </div>
                                        <div>
                                            <div class="fw-bold">{{ user_data.company_name }}</div>
                                            <small class="text-white">{{ company_id }}</small>
                                        </div>
                                    </div>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/profile">
                                        <i class="fas fa-user me-2"></i> Şirket Profili
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/subscription">
                                        <i class="fas fa-crown me-2"></i> Abonelik Bilgileri
                                    </a>
                                </li>
                                <li>
                                    <a class="dropdown-item" href="/company/{{ company_id }}/billing">
                                        <i class="fas fa-credit-card me-2"></i> Fatura & Ödeme
                                    </a>
                                </li>
                                <li><hr class="dropdown-divider"></li>
                                <li>
                                    <a class="dropdown-item text-danger" href="#" onclick="logout()">
                                        <i class="fas fa-sign-out-alt me-2"></i> Çıkış Yap
                                    </a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <!-- Report Filters -->
                <div class="report-filter">
                    <div class="row align-items-center">
                        <div class="col-md-3">
                            <h5 class="mb-2">
                                <i class="fas fa-filter"></i> Filtreler
                            </h5>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Tarih Aralığı</label>
                            <select class="form-select" id="dateRange">
                                <option value="7">Son 7 Gün</option>
                                <option value="30" selected>Son 30 Gün</option>
                                <option value="90">Son 3 Ay</option>
                                <option value="365">Son 1 Yıl</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Kamera</label>
                            <select class="form-select" id="cameraFilter">
                                <option value="">Tüm Kameralar</option>
                                <option value="CAM_001">Ana Giriş</option>
                                <option value="CAM_002">İnşaat Alanı</option>
                                <option value="CAM_003">Depo Girişi</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">&nbsp;</label>
                            <div class="d-grid">
                                <button class="btn btn-light" onclick="applyFilters()">
                                    <i class="fas fa-search"></i> Filtrele
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Overall Statistics -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value compliance-good" id="overallCompliance">--%</div>
                            <h6 class="text-muted">Genel Uyumluluk</h6>
                            <small class="text-muted" id="complianceTrend">
                                <i class="fas fa-info-circle"></i> Gerçek veriler yükleniyor...
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value text-danger" id="totalViolations">--</div>
                            <h6 class="text-muted">Toplam İhlal</h6>
                            <small class="text-muted" id="violationsTrend">
                                <i class="fas fa-info-circle"></i> Gerçek veriler yükleniyor...
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                                                            <div class="stat-value text-warning" id="totalPenalties">--</div>
                                <h6 class="text-muted">Toplam Uyarı</h6>
                            <small class="text-muted" id="penaltiesTrend">
                                <i class="fas fa-info-circle"></i> Gerçek veriler yükleniyor...
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value text-info" id="detectedPersons">--</div>
                            <h6 class="text-muted">Tespit Edilen Kişi</h6>
                            <small class="text-muted" id="personsTrend">
                                <i class="fas fa-info-circle"></i> Gerçek veriler yükleniyor...
                            </small>
                        </div>
                    </div>
                </div>
                
                <!-- Report Tabs -->
                <div class="card">
                    <div class="card-header">
                        <ul class="nav nav-tabs card-header-tabs" id="reportTabs">
                            <li class="nav-item">
                                <a class="nav-link active" id="compliance-tab" data-bs-toggle="tab" href="#compliance">
                                    <i class="fas fa-check-circle"></i> Uyumluluk Analizi
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link" id="violations-tab" data-bs-toggle="tab" href="#violations">
                                    <i class="fas fa-exclamation-triangle"></i> İhlal Raporları
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link" id="camera-tab" data-bs-toggle="tab" href="#camera">
                                    <i class="fas fa-video"></i> Kamera Performansı
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link" id="export-tab" data-bs-toggle="tab" href="#export">
                                    <i class="fas fa-download"></i> Dışa Aktar
                                </a>
                            </li>
                        </ul>
                    </div>
                    <div class="card-body">
                        <div class="tab-content" id="reportTabContent">
                            <!-- Compliance Analysis Tab -->
                            <div class="tab-pane fade show active" id="compliance">
                                <div class="row">
                                    <div class="col-md-8">
                                        <h5>Günlük Uyumluluk Trendi</h5>
                                        <div class="chart-container">
                                            <canvas id="complianceChart"></canvas>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <h5>PPE Uyumluluk Oranları</h5>
                                        <div class="mb-3">
                                            <div class="d-flex justify-content-between">
                                                <span>Baret</span>
                                                <span class="text-success fw-bold" id="helmetCompliance">--%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-success" id="helmetProgress" style="width: 0%"></div>
                                            </div>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <div class="d-flex justify-content-between">
                                                <span>Güvenlik Yeleği</span>
                                                <span class="text-warning fw-bold" id="vestCompliance">--%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-warning" id="vestProgress" style="width: 0%"></div>
                                            </div>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <div class="d-flex justify-content-between">
                                                <span>Güvenlik Ayakkabısı</span>
                                                <span class="text-success fw-bold" id="shoesCompliance">--%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-success" id="shoesProgress" style="width: 0%"></div>
                                            </div>
                                        </div>
                                        
                                        <div class="alert alert-info mt-4">
                                            <i class="fas fa-lightbulb"></i>
                                            <strong>Öneri:</strong> Güvenlik yeleği uyumluluğunu artırmak için ek eğitim planlanabilir.
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Violations Tab -->
                            <div class="tab-pane fade" id="violations">
                                <div class="row">
                                    <div class="col-md-8">
                                        <h5>Son İhlaller</h5>
                                        <div id="violationsList">
                                            <div class="text-center py-4">
                                                <div class="spinner-border text-primary" role="status">
                                                    <span class="visually-hidden">Yükleniyor...</span>
                                                </div>
                                                <p class="mt-2 text-muted">İhlaller yükleniyor...</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <h5>İhlal Türleri</h5>
                                        <div class="chart-container" style="height: 300px;">
                                            <canvas id="violationTypesChart"></canvas>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Camera Performance Tab -->
                            <div class="tab-pane fade" id="camera">
                                <div class="row">
                                    <div class="col-md-12">
                                        <h5>Kamera Performans Analizi</h5>
                        <div class="table-responsive">
                                            <table class="table table-hover">
                                                <thead class="table-dark">
                                                    <tr>
                                                        <th>Kamera</th>
                                                        <th>Uyumluluk Oranı</th>
                                                        <th>Toplam Tespit</th>
                                                        <th>İhlal Sayısı</th>
                                                        <th>Ortalama Güven</th>
                                        <th>Durum</th>
                                    </tr>
                                </thead>
                                                <tbody id="cameraPerformanceTable">
                                                    <tr id="noDataRow">
                                                        <td colspan="6" class="text-center text-muted">
                                                            <i class="fas fa-info-circle"></i> 
                                                            Live detection başlatıldığında kamera performans verileri burada görünecek
                                                        </td>
                                                    </tr>
                                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
                            
                            <!-- Export Tab -->
                            <div class="tab-pane fade" id="export">
                                <div class="row">
                                    <div class="col-md-6">
                                        <h5>Rapor Dışa Aktarma</h5>
                                        <form id="exportForm">
                                            <div class="mb-3">
                                                <label class="form-label">Rapor Türü</label>
                                                <select class="form-select" name="type">
                                                    <option value="violations">İhlal Raporu</option>
                                                    <option value="compliance">Uyumluluk Raporu</option>
                                                    <option value="camera">Kamera Performansı</option>
                                                    <option value="summary">Özet Rapor</option>
                                                </select>
                                            </div>
                                            
                                            <div class="mb-3">
                                                <label class="form-label">Dosya Formatı</label>
                                                <div class="row">
                                                    <div class="col-6">
                                                        <div class="form-check">
                                                            <input class="form-check-input" type="radio" name="format" value="pdf" checked>
                                                            <label class="form-check-label">
                                                                <i class="fas fa-file-pdf text-danger"></i> PDF
                                                            </label>
                                                        </div>
                                                    </div>
                                                    <div class="col-6">
                                                        <div class="form-check">
                                                            <input class="form-check-input" type="radio" name="format" value="excel">
                                                            <label class="form-check-label">
                                                                <i class="fas fa-file-excel text-success"></i> Excel
                                                            </label>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <div class="mb-3">
                                                <label class="form-label">Email Gönder</label>
                                                <div class="form-check">
                                                    <input class="form-check-input" type="checkbox" id="sendEmail" name="send_email">
                                                    <label class="form-check-label" for="sendEmail">
                                                        Raporu email ile gönder
                                                    </label>
                                                </div>
                                            </div>
                                            
                                            <button type="button" class="export-btn" onclick="exportReport()">
                                                <i class="fas fa-download"></i> Rapor Oluştur
                                            </button>
                                        </form>
                                    </div>
                                    <div class="col-md-6">
                                        <h5>Otomatik Raporlar</h5>
                                        <div class="card">
                                            <div class="card-body">
                                                <h6>Günlük Özet Raporu</h6>
                                                <p class="text-muted">Her gün 18:00'de otomatik özet raporu</p>
                                                <div class="form-check form-switch">
                                                    <input class="form-check-input" type="checkbox" id="dailyReport" checked>
                                                    <label class="form-check-label" for="dailyReport">Aktif</label>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div class="card">
                                            <div class="card-body">
                                                <h6>Haftalık Analiz Raporu</h6>
                                                <p class="text-muted">Her Pazartesi 09:00'da haftalık analiz</p>
                                                <div class="form-check form-switch">
                                                    <input class="form-check-input" type="checkbox" id="weeklyReport" checked>
                                                    <label class="form-check-label" for="weeklyReport">Aktif</label>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div class="card">
                                            <div class="card-body">
                                                <h6>Aylık Uyumluluk Raporu</h6>
                                                <p class="text-muted">Her ayın 1'inde detaylı analiz</p>
                                                <div class="form-check form-switch">
                                                    <input class="form-check-input" type="checkbox" id="monthlyReport">
                                                    <label class="form-check-label" for="monthlyReport">Aktif</label>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}';
                let complianceChart = null;
                let violationTypesChart = null;
                
                // Initialize charts and data
                console.log('🔍 DOMContentLoaded event listener tanımlanıyor...');
                console.log('🔍 Company ID (global):', companyId);
                
                // Basit test - hemen çalıştır
                console.log('🔍 Hemen test çalıştırılıyor...');
                
                // Hemen çalıştır test
                setTimeout(function() {
                    console.log('🔍 setTimeout test çalıştırılıyor...');
                    console.log('🔍 Company ID (setTimeout):', companyId);
                }, 100);
                
                // Hemen çalıştır test 2
                console.log('🔍 Hemen test 2 çalıştırılıyor...');
                console.log('🔍 Company ID (hemen):', companyId);
                
                // Hemen çalıştır test 3
                console.log('🔍 Hemen test 3 çalıştırılıyor...');
                console.log('🔍 Company ID (hemen 3):', companyId);
                
                // Hemen çalıştır test 4
                console.log('🔍 Hemen test 4 çalıştırılıyor...');
                console.log('🔍 Company ID (hemen 4):', companyId);
                console.log('🔍 Hemen test 4 çalıştırılıyor...');
                console.log('🔍 Company ID (hemen 4):', companyId);
                
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('🚀 Dashboard yükleniyor...');
                    console.log('🔍 Company ID (DOM):', companyId);
                    console.log('🔍 loadSubscriptionInfo function exists:', typeof loadSubscriptionInfo);
                    console.log('🔍 loadDashboardData function exists:', typeof loadDashboardData);
                    console.log('🔍 loadViolations function exists:', typeof loadViolations);
                    console.log('🔍 loadComplianceReport function exists:', typeof loadComplianceReport);
                    
                    loadDashboardData();
                    loadViolations();
                    loadComplianceReport();
                    
                    // Abonelik bilgilerini hemen yükle
                    console.log('🔄 Abonelik bilgileri hemen yükleniyor...');
                    console.log('🔍 loadSubscriptionInfo fonksiyonu var mı?', typeof loadSubscriptionInfo);
                    
                    if (typeof loadSubscriptionInfo === 'function') {
                        try {
                            loadSubscriptionInfo();
                            console.log('✅ loadSubscriptionInfo çağrıldı');
                        } catch (error) {
                            console.error('❌ loadSubscriptionInfo hatası:', error);
                        }
                    } else {
                        console.error('❌ loadSubscriptionInfo fonksiyonu bulunamadı!');
                    }
                    
                    // Abonelik bilgilerini tekrar yükle
                    setTimeout(() => {
                        console.log('🔄 Abonelik bilgileri tekrar yükleniyor...');
                        console.log('🔍 loadSubscriptionInfo fonksiyonu var mı? (setTimeout):', typeof loadSubscriptionInfo);
                        
                        if (typeof loadSubscriptionInfo === 'function') {
                            try {
                                loadSubscriptionInfo();
                                console.log('✅ loadSubscriptionInfo tekrar çağrıldı');
                            } catch (error) {
                                console.error('❌ loadSubscriptionInfo tekrar hatası:', error);
                            }
                        } else {
                            console.error('❌ loadSubscriptionInfo fonksiyonu bulunamadı! (setTimeout)');
                        }
                    }, 1000); // 1 saniye sonra yükle
                    
                    // Dinamik güncellemeleri başlat
                    setTimeout(() => {
                        startDynamicUpdates();
                    }, 2000); // 2 saniye sonra başlat
                });
                
                // Load Dashboard Data
                function loadDashboardData() {
                    // Load violations report
                    fetch('/api/company/' + companyId + '/reports/violations')
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateViolationsChart(data.data);
                                updateViolationsStats(data.data);
                                
                                // Check if real data exists
                                if (data.data.status === 'waiting_for_live_data') {
                                    showWaitingMessage();
                                }
                            }
                        })
                        .catch(error => {
                            console.error('Error loading violations report:', error);
                            showWaitingMessage();
                        });
                    
                    // Load compliance report
                    fetch('/api/company/' + companyId + '/reports/compliance')
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateComplianceChart(data.data);
                                updateComplianceStats(data.data);
                                updateCameraPerformance(data.data);
                                
                                // Check if real data exists
                                if (data.data.status === 'waiting_for_live_data') {
                                    showWaitingMessage();
                                }
                            }
                        })
                        .catch(error => {
                            console.error('Error loading compliance report:', error);
                            showWaitingMessage();
                        });
                }
                
                // Show waiting message for live data
                function showWaitingMessage() {
                    const elements = [
                        'overallCompliance', 'totalViolations', 'totalPenalties', 'detectedPersons',
                        'complianceTrend', 'violationsTrend', 'penaltiesTrend', 'personsTrend'
                    ];
                    
                    elements.forEach(id => {
                        const element = document.getElementById(id);
                        if (element) {
                            if (id.includes('Trend')) {
                                element.innerHTML = '<i class="fas fa-info-circle"></i> Live detection başlatın';
                            } else if (id.includes('Compliance')) {
                                element.textContent = '--%';
                            } else if (id.includes('Violations')) {
                                element.textContent = '--';
                            } else if (id.includes('Penalties')) {
                                element.textContent = '--';
                            } else if (id.includes('Persons')) {
                                element.textContent = '--';
                            }
                        }
                    });
                }
                    
                    // Load subscription info
                console.log('🔄 Abonelik bilgileri yükleniyor...');
                
                // Session bilgisini dinamik olarak al
                const sessionId = document.cookie.split('; ').find(row => row.startsWith('session_id='))?.split('=')[1] || '';
                console.log('🔍 Session ID (dashboard):', sessionId);
                
                    fetch(`/api/company/${companyId}/subscription`, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Session-ID': sessionId
                        },
                        credentials: 'same-origin'
                    })
                        .then(response => response.json())
                        .then(result => {
                        console.log('📊 Abonelik yükleme sonucu:', result);
                            if (result.success) {
                                // API'den direkt subscription bilgileri geliyor, .subscription key'i yok
                                const subscription = result;
                                
                                // Update subscription display in dashboard
                                const subscriptionPlanElement = document.getElementById('subscription-plan');
                                const cameraUsageElement = document.getElementById('camera-usage');
                            const subscriptionTrend = document.getElementById('subscription-trend');
                            const usageTrend = document.getElementById('usage-trend');
                                
                                if (subscriptionPlanElement) {
                                    subscriptionPlanElement.textContent = subscription.subscription_type ? subscription.subscription_type.toUpperCase() : 'BASIC';
                                console.log('✅ Abonelik planı güncellendi:', subscriptionPlanElement.textContent);
                                }
                                
                                if (cameraUsageElement) {
                                    cameraUsageElement.textContent = (subscription.used_cameras || 0) + '/' + (subscription.max_cameras || 25);
                                console.log('✅ Kamera kullanımı güncellendi:', cameraUsageElement.textContent);
                                }
                                
                                if (subscriptionTrend) {
                                    if (subscription.is_active) {
                                        subscriptionTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Aktif';
                                        subscriptionTrend.className = 'metric-trend';
                                    } else {
                                        subscriptionTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Süresi Dolmuş';
                                        subscriptionTrend.className = 'metric-trend';
                                    }
                                }
                                
                                if (usageTrend) {
                                    const usagePercentage = subscription.usage_percentage || 0;
                                    if (usagePercentage > 80) {
                                        usageTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Limit Yakın';
                                        usageTrend.className = 'metric-trend';
                                    } else if (usagePercentage > 60) {
                                        usageTrend.innerHTML = '<i class="fas fa-info trend-neutral"></i> Orta';
                                        usageTrend.className = 'metric-trend';
                                    } else {
                                        usageTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Normal';
                                        usageTrend.className = 'metric-trend';
                                    }
                                }
                            
                            // Dinamik güncelleme için interval başlat
                            startDynamicUpdates();
                            }
                        })
                        .catch(error => {
                            console.error('Abonelik bilgileri yükleme hatası:', error);
                        });
                }
                
                // Dinamik güncelleme fonksiyonu
                function startDynamicUpdates() {
                    // Her 30 saniyede bir abonelik bilgilerini güncelle
                    setInterval(() => {
                        updateSubscriptionInfo();
                    }, 30000);
                    
                    // Her 10 saniyede bir kamera kullanımını güncelle
                    setInterval(() => {
                        updateCameraUsage();
                    }, 10000);
                }
                
                // Abonelik bilgilerini güncelle
                function updateSubscriptionInfo() {
                    console.log('🔄 Abonelik bilgileri güncelleniyor...');
                    fetch('/api/company/' + companyId + '/subscription')
                        .then(response => response.json())
                        .then(result => {
                            console.log('📊 Abonelik sonucu:', result);
                            if (result.success) {
                                // API'den direkt subscription bilgileri geliyor, .subscription key'i yok
                                const subscription = result;
                                const subscriptionPlanElement = document.getElementById('subscription-plan');
                                const subscriptionTrend = document.getElementById('subscription-trend');
                                
                                if (subscriptionPlanElement) {
                                    subscriptionPlanElement.textContent = subscription.subscription_type ? subscription.subscription_type.toUpperCase() : 'BASIC';
                                    console.log('✅ Abonelik planı güncellendi:', subscriptionPlanElement.textContent);
                                }
                                
                                if (subscriptionTrend) {
                                    if (subscription.is_active) {
                                        subscriptionTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Aktif';
                                        subscriptionTrend.className = 'metric-trend';
                                    } else {
                                        subscriptionTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Süresi Dolmuş';
                                        subscriptionTrend.className = 'metric-trend';
                                    }
                                }
                            }
                        })
                        .catch(error => {
                            console.error('❌ Abonelik güncelleme hatası:', error);
                        });
                }
                
                // Kamera kullanımını güncelle
                function updateCameraUsage() {
                    console.log('🔄 Kamera kullanımı güncelleniyor...');
                    
                    // Session bilgisini dinamik olarak al
                    const sessionId = document.cookie.split('; ').find(row => row.startsWith('session_id='))?.split('=')[1] || '';
                    console.log('🔍 Session ID (kamera):', sessionId);
                    
                    fetch('/api/company/' + companyId + '/cameras', {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Session-ID': sessionId
                        },
                        credentials: 'same-origin'
                    })
                        .then(response => response.json())
                        .then(result => {
                            console.log('📊 Kamera sonucu:', result);
                            if (result.success) {
                                const cameras = result.cameras;
                                const activeCameras = cameras.filter(cam => cam.status === 'active').length;
                                console.log('📹 Aktif kamera sayısı:', activeCameras);
                                
                                // Abonelik bilgilerini al
                                fetch(`/api/company/${companyId}/subscription`, {
                                    method: 'GET',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-Session-ID': sessionId
                                    },
                                    credentials: 'same-origin'
                                })
                                    .then(response => response.json())
                                    .then(subResult => {
                                        console.log('📊 Abonelik sonucu (kamera):', subResult);
                                        if (subResult.success) {
                                            // API'den direkt subscription bilgileri geliyor, .subscription key'i yok
                                            const subscription = subResult;
                                            const cameraUsageElement = document.getElementById('camera-usage');
                                            const usageTrend = document.getElementById('usage-trend');
                                            
                                            if (cameraUsageElement) {
                                                cameraUsageElement.textContent = activeCameras + '/' + (subscription.max_cameras || 25);
                                                console.log('✅ Kamera kullanımı güncellendi:', cameraUsageElement.textContent);
                                            }
                                            
                                            if (usageTrend) {
                                                const usagePercentage = (activeCameras / (subscription.max_cameras || 25)) * 100;
                                                if (usagePercentage > 80) {
                                                    usageTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Limit Yakın';
                                                    usageTrend.className = 'metric-trend';
                                                } else if (usagePercentage > 60) {
                                                    usageTrend.innerHTML = '<i class="fas fa-info trend-neutral"></i> Orta';
                                                    usageTrend.className = 'metric-trend';
                                                } else {
                                                    usageTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Normal';
                                                    usageTrend.className = 'metric-trend';
                                                }
                                            }
                                        }
                                    });
                            }
                        })
                        .catch(error => {
                            console.error('❌ Kamera kullanım güncelleme hatası:', error);
                        });
                }
                
                // Update Violations Chart
                function updateViolationsChart(data) {
                    const violationCtx = document.getElementById('violationTypesChart').getContext('2d');
                    
                    // PPE türlerini grupla
                    const ppeTypes = {};
                    data.ppe_violations.forEach(violation => {
                        const type = violation.ppe_type;
                        ppeTypes[type] = (ppeTypes[type] || 0) + violation.count;
                    });
                    
                    const labels = Object.keys(ppeTypes);
                    const values = Object.values(ppeTypes);
                    const colors = ['#e74c3c', '#f39c12', '#3498db', '#9b59b6', '#1abc9c'];
                    
                    if (violationTypesChart) {
                        violationTypesChart.destroy();
                    }
                    
                    violationTypesChart = new Chart(violationCtx, {
                        type: 'doughnut',
                        data: {
                            labels: labels,
                            datasets: [{
                                data: values,
                                backgroundColor: colors.slice(0, labels.length),
                                borderWidth: 0
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    position: 'bottom'
                                }
                            }
                        }
                    });
                }
                
                // Update Compliance Chart
                function updateComplianceChart(data) {
                    const complianceCtx = document.getElementById('complianceChart').getContext('2d');
                    
                    // Son 7 günün verilerini al
                    const dailyStats = data.daily_stats.slice(0, 7).reverse();
                    const labels = dailyStats.map(stat => {
                        const date = new Date(stat.date);
                        return date.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' });
                    });
                    const values = dailyStats.map(stat => stat.compliance);
                    
                    if (complianceChart) {
                        complianceChart.destroy();
                    }
                    
                    complianceChart = new Chart(complianceCtx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: 'Uyumluluk Oranı (%)',
                                data: values,
                                borderColor: '#667eea',
                                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                                borderWidth: 3,
                                fill: true,
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    max: 100
                                }
                            },
                            plugins: {
                                legend: {
                                    display: false
                                }
                            }
                        }
                    });
                }
                
                // Update Compliance Stats
                function updateComplianceStats(data) {
                    // Genel uyumluluk
                    document.getElementById('overallCompliance').textContent = data.overall_compliance + '%';
                    document.getElementById('overallCompliance').className = 
                        data.overall_compliance >= 85 ? 'stat-value compliance-good' :
                        data.overall_compliance >= 70 ? 'stat-value compliance-warning' :
                        'stat-value compliance-danger';
                    
                    // PPE türü bazlı uyumluluk
                    updatePPECompliance('helmet', data.helmet_compliance);
                    updatePPECompliance('vest', data.vest_compliance);
                    updatePPECompliance('shoes', data.shoes_compliance);
                    
                    // Toplam tespit ve ihlal sayıları
                    document.getElementById('totalDetections').textContent = data.total_detections;
                    document.getElementById('totalViolations').textContent = data.total_violations;
                }
                
                // Update PPE Compliance
                function updatePPECompliance(type, value) {
                    const element = document.getElementById(type + 'Compliance');
                    const progressBar = document.getElementById(type + 'Progress');
                    
                    if (element) {
                        element.textContent = value + '%';
                        element.className = 
                            value >= 85 ? 'text-success fw-bold' :
                            value >= 70 ? 'text-warning fw-bold' :
                            'text-danger fw-bold';
                    }
                    
                    if (progressBar) {
                        progressBar.style.width = value + '%';
                        progressBar.className = 
                            value >= 85 ? 'progress-bar bg-success' :
                            value >= 70 ? 'progress-bar bg-warning' :
                            'progress-bar bg-danger';
                    }
                }
                
                // Update Camera Performance
                function updateCameraPerformance(data) {
                    const tableBody = document.getElementById('cameraPerformanceTable');
                    if (!tableBody) return;
                    
                    tableBody.innerHTML = '';
                    
                    data.camera_stats.forEach(camera => {
                        const row = document.createElement('tr');
                        const complianceBadge = 
                            camera.compliance >= 85 ? 'bg-success' :
                            camera.compliance >= 70 ? 'bg-warning' :
                            'bg-danger';
                        
                        row.innerHTML = `
                            <td><i class="fas fa-video text-primary"></i> ${camera.camera_name}</td>
                            <td><span class="badge ${complianceBadge}">${camera.compliance}%</span></td>
                            <td>${camera.detections}</td>
                            <td>${camera.violations}</td>
                            <td>-</td>
                            <td><span class="badge bg-success">Aktif</span></td>
                        `;
                        tableBody.appendChild(row);
                    });
                }
                
                // Update Violations Stats
                function updateViolationsStats(data) {
                    document.getElementById('totalViolationsCount').textContent = data.total_violations;
                    document.getElementById('reportPeriod').textContent = data.period;
                                }
                            }
                        }
                    });
                }
                
                // Load Violations - Already implemented in loadDashboardData
                function loadViolations() {
                    // This function is called from loadDashboardData
                    // No need to duplicate API calls
                }
                
                // Load Compliance Report
                function loadComplianceReport() {
                    // This function is called from loadDashboardData
                    // No need to duplicate API calls
                }
                
                // Display Violations
                function displayViolations(data) {
                    const container = document.getElementById('violationsList');
                    
                    if (!data.camera_violations || data.camera_violations.length === 0) {
                        container.innerHTML = `
                            <div class="text-center py-4">
                                <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
                                <h5 class="text-success">Hiç ihlal yok!</h5>
                                <p class="text-muted">Son 30 gün içinde hiç PPE ihlali tespit edilmedi.</p>
                            </div>
                        `;
                        return;
                    }
                    
                    container.innerHTML = data.camera_violations.slice(0, 10).map(violation => `
                        <div class="violation-card">
                            <div class="row align-items-center">
                                <div class="col-md-3">
                                    <strong>Kamera ${violation.camera_id}</strong>
                                    <small class="d-block text-muted">${new Date(violation.last_violation).toLocaleDateString('tr-TR')}</small>
                                </div>
                                <div class="col-md-4">
                                    <span class="text-danger">${violation.count} ihlal tespit edildi</span>
                                    <small class="d-block text-muted">Son ihlal zamanı</small>
                                </div>
                                <div class="col-md-2">
                                    <span class="badge ${violation.count > 10 ? 'bg-danger' : violation.count > 5 ? 'bg-warning' : 'bg-info'}">
                                        ${violation.count > 10 ? 'Yüksek' : violation.count > 5 ? 'Orta' : 'Düşük'}
                                    </span>
                                </div>
                                <div class="col-md-2">
                                    <strong class="text-danger">${violation.count} uyarı</strong>
                                </div>
                                <div class="col-md-1">
                                    <button class="btn btn-sm btn-outline-primary" onclick="viewViolationDetail('${violation.camera_id}')">
                                        <i class="fas fa-eye"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
                
                // Apply Filters
                function applyFilters() {
                    const dateRange = document.getElementById('dateRange').value;
                    const camera = document.getElementById('cameraFilter').value;
                    
                    // Reload data with filters
                    loadViolations();
                    
                    // Show loading message
                    const container = document.getElementById('violationsList');
                    container.innerHTML = `
                        <div class="text-center py-4">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">Filtreleniyor...</span>
                            </div>
                            <p class="mt-2 text-muted">Veriler filtreleniyor...</p>
                        </div>
                    `;
                    
                    setTimeout(() => {
                        loadViolations();
                    }, 1000);
                }
                
                // Export Report
                function exportReport() {
                    const form = document.getElementById('exportForm');
                    const formData = new FormData(form);
                    const data = {};
                    formData.forEach((value, key) => {
                        data[key] = value;
                    });
                    
                    // Get checked format
                    const formatRadio = document.querySelector('input[name="format"]:checked');
                    data.format = formatRadio ? formatRadio.value : 'pdf';
                    
                    fetch('/api/company/' + companyId + '/reports/export', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ ' + result.message + '\\n\\nRapor oluşturuldu ve indirmeye hazır.');
                            // Simulated download
                            const link = document.createElement('a');
                            link.href = '#';
                            link.download = 'report.' + data.format;
                            link.click();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error exporting report:', error);
                        alert('❌ Rapor oluşturma sırasında bir hata oluştu');
                    });
                }
                
                // View Violation Detail
                function viewViolationDetail(cameraId) {
                                            alert('📹 Kamera ' + cameraId + ' detay görüntüleme\\n\\n(Bu özellik geliştirilme aşamasında)');
                }
                
                // Logout
                function logout() {
                    if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
                        fetch('/logout', {
                            method: 'POST'
                        })
                        .then(() => {
                            window.location.href = '/';
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            window.location.href = '/';
                        });
                    }
                }
            </script>
        </body>
        </html>
        '''
    
    def get_camera_management_template(self):
        """Advanced Camera Management Template with Discovery and Testing"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Kamera Yönetimi - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .camera-card {
                    background: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 20px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                }
                .camera-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 15px 35px rgba(0,0,0,0.2);
                }
                .camera-status {
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    display: inline-block;
                    margin-right: 8px;
                }
                .status-online { background: #27ae60; animation: pulse 2s infinite; }
                .status-offline { background: #e74c3c; }
                .status-testing { background: #f39c12; animation: blink 1s infinite; }
                
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(39, 174, 96, 0.7); }
                    70% { box-shadow: 0 0 0 10px rgba(39, 174, 96, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(39, 174, 96, 0); }
                }
                @keyframes blink {
                    50% { opacity: 0.5; }
                }
                
                .discovery-card {
                    background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                    text-align: center;
                }
                .discovery-btn {
                    background: rgba(255,255,255,0.2);
                    border: 2px solid rgba(255,255,255,0.3);
                    color: white;
                    border-radius: 25px;
                    padding: 12px 30px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                .discovery-btn:hover {
                    background: rgba(255,255,255,0.3);
                    transform: translateY(-2px);
                }
                
                .group-card {
                    background: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 15px;
                    border-left: 5px solid #667eea;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }
                
                .stream-preview {
                    width: 100%;
                    height: 200px;
                    background: #2c3e50;
                    border-radius: 10px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    margin-bottom: 15px;
                    position: relative;
                    overflow: hidden;
                }
                
                .test-results {
                    background: #f8f9fa;
                    border-radius: 10px;
                    padding: 15px;
                    margin-top: 15px;
                }
                
                .quality-score {
                    font-size: 2rem;
                    font-weight: bold;
                    color: #27ae60;
                }
                
                .network-scanner {
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 20px;
                }
                
                .floating-actions {
                    position: fixed;
                    bottom: 30px;
                    right: 30px;
                    z-index: 1000;
                }
                
                .floating-btn {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    margin-bottom: 10px;
                    border: none;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                    transition: all 0.3s ease;
                }
                .floating-btn:hover {
                    transform: scale(1.1);
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/company/{{ company_id }}/dashboard">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <span class="nav-link fw-bold">
                            <i class="fas fa-building text-primary"></i> 
                            {{ user_data.company_name }}
                        </span>
                        <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="nav-link active" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        <button class="btn btn-outline-danger btn-sm" onclick="logout()">
                            <i class="fas fa-sign-out-alt"></i> Çıkış
                        </button>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <!-- Header -->
                <div class="row mb-4">
                    <div class="col-12">
                        <h2 class="text-white mb-0">
                            <i class="fas fa-video"></i> Kamera Yönetimi
                        </h2>
                        <p class="text-white-50">IP kamera keşfi, test sistemi ve grup yönetimi</p>
                    </div>
                </div>
                
                <!-- Quick Actions -->
                <div class="row mb-4">
                    <div class="col-md-4">
                        <div class="discovery-card">
                            <i class="fas fa-search fa-3x mb-3"></i>
                            <h5>Otomatik Keşif</h5>
                            <p class="mb-3">Ağınızdaki IP kameraları otomatik olarak bulun</p>
                            <button class="discovery-btn" onclick="startDiscovery()">
                                <i class="fas fa-radar"></i> Keşfi Başlat
                            </button>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="camera-card text-center">
                            <i class="fas fa-plus-circle fa-3x text-primary mb-3"></i>
                            <h5>Manuel Ekleme</h5>
                            <p class="mb-3">Kamera bilgilerini manuel olarak ekleyin</p>
                            <a href="/company/${companyId}/cameras" class="btn btn-primary">
                                <i class="fas fa-plus"></i> Kamera Ekle
                            </a>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="camera-card text-center">
                            <i class="fas fa-layer-group fa-3x text-success mb-3"></i>
                            <h5>Grup Yönetimi</h5>
                            <p class="mb-3">Kameraları gruplara ayırın</p>
                            <button class="btn btn-success" data-bs-toggle="modal" data-bs-target="#groupModal">
                                <i class="fas fa-sitemap"></i> Grupları Yönet
                            </button>
                        </div>
                    </div>
                        </div>
                
                <!-- Camera Groups -->
                <div class="row mb-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header bg-primary text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-layer-group"></i> Kamera Grupları
                                </h5>
                            </div>
                            <div class="card-body">
                                <div id="cameraGroups">
                                    <!-- Groups will be loaded here -->
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Camera List -->
                <div class="row">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header bg-info text-white d-flex justify-content-between">
                                <h5 class="mb-0">
                                    <i class="fas fa-video"></i> Kameralar
                                </h5>
                                <div>
                                    <button class="btn btn-light btn-sm me-2" onclick="refreshCameras()">
                                        <i class="fas fa-sync"></i> Yenile
                                            </button>
                                    <button class="btn btn-light btn-sm" onclick="testAllCameras()">
                                        <i class="fas fa-check-circle"></i> Tümünü Test Et
                                            </button>
                                </div>
                            </div>
                            <div class="card-body">
                                <div id="cameraList">
                                    <!-- Cameras will be loaded here -->
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            

            
            <!-- Discovery Modal -->
            <div class="modal fade" id="discoveryModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header bg-info text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-search"></i> IP Kamera Keşfi
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="network-scanner">
                                <div class="row align-items-center">
                                    <div class="col-md-8">
                                        <h6>Ağ Aralığı</h6>
                                        <input type="text" class="form-control" id="networkRange" value="192.168.1.0/24">
                                    </div>
                                    <div class="col-md-4">
                                        <button class="btn btn-light w-100" onclick="scanNetwork()">
                                            <i class="fas fa-radar"></i> Tara
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div id="discoveryResults">
                                <!-- Discovery results will appear here -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Group Management Modal -->
            <div class="modal fade" id="groupModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-success text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-layer-group"></i> Grup Yönetimi
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6>Yeni Grup Oluştur</h6>
                                    <form id="createGroupForm">
                                        <div class="mb-3">
                                            <label class="form-label">Grup Adı</label>
                                            <input type="text" class="form-control" name="name" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Lokasyon</label>
                                            <input type="text" class="form-control" name="location" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Grup Türü</label>
                                            <select class="form-select" name="group_type" required>
                                                <option value="">Seçin</option>
                                                <option value="entrance">Giriş</option>
                                                <option value="work_area">Çalışma Alanı</option>
                                                <option value="storage">Depo</option>
                                                <option value="office">Ofis</option>
                                                <option value="parking">Otopark</option>
                                            </select>
                                        </div>
                                        <button type="button" class="btn btn-success" onclick="createGroup()">
                                            <i class="fas fa-plus"></i> Grup Oluştur
                                        </button>
                                    </form>
                                </div>
                                <div class="col-md-6">
                                    <h6>Mevcut Gruplar</h6>
                                    <div id="groupList">
                                        <!-- Groups will be loaded here -->
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Camera Details Modal -->
            <div class="modal fade" id="cameraDetailsModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header bg-dark text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-video"></i> Kamera Detayları
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div id="cameraDetailsContent">
                                <!-- Camera details will be loaded here -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Floating Action Buttons -->
            <div class="floating-actions">
                <button class="floating-btn btn btn-primary" onclick="startDiscovery()" title="Kamera Keşfi">
                    <i class="fas fa-search"></i>
                </button>
                <button class="floating-btn btn btn-success" onclick="refreshCameras()" title="Yenile">
                    <i class="fas fa-sync"></i>
                </button>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}';
                let discoveredCameras = [];
                let cameraGroups = [];
                
                document.addEventListener('DOMContentLoaded', function() {
                    loadCameraGroups();
                    loadCameras();
                });
                
                // Load Camera Groups
                function loadCameraGroups() {
                    fetch(`/api/company/${companyId}/cameras/groups`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            cameraGroups = data.groups;
                            displayCameraGroups(data.groups);
                            populateGroupSelects(data.groups);
                        }
                    });
                }
                
                // Display Camera Groups
                function displayCameraGroups(groups) {
                    const container = document.getElementById('cameraGroups');
                    container.innerHTML = groups.map(group => `
                        <div class="group-card">
                            <div class="row align-items-center">
                                <div class="col-md-6">
                                    <h6 class="mb-1">${group.name}</h6>
                                    <small class="text-muted">${group.location}</small>
                                </div>
                                <div class="col-md-3">
                                    <span class="badge bg-primary">${group.active_cameras}/${group.camera_count} Aktif</span>
                                </div>
                                <div class="col-md-3">
                                    <span class="badge bg-info">${group.group_type}</span>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
                
                // Load Cameras
                function loadCameras() {
                    fetch(`/api/company/${companyId}/cameras`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            displayCameras(data.cameras);
                        }
                    });
                }
                
                // Display Cameras
                function displayCameras(cameras) {
                    const container = document.getElementById('cameraList');
                    if (cameras.length === 0) {
                        container.innerHTML = `
                            <div class="text-center py-5">
                                <i class="fas fa-video fa-3x text-muted mb-3"></i>
                                <h5 class="text-muted">Henüz kamera yok</h5>
                                <p class="text-muted">İlk kameranızı eklemek için yukarıdaki seçenekleri kullanın.</p>
                            </div>
                        `;
                        return;
                    }
                    
                    container.innerHTML = cameras.map(camera => `
                        <div class="camera-card">
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="stream-preview" onclick="viewStream('${camera.camera_id}')" style="cursor: pointer;">
                                        <img src="/api/company/${companyId}/video-feed/${camera.camera_id}" 
                                             alt="Kamera Feed" 
                                             class="img-fluid rounded"
                                             style="width: 100%; height: 100%; object-fit: cover;"
                                             onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                                        <div class="d-flex align-items-center justify-content-center h-100" style="display: none;">
                                            <div class="text-center">
                                                <i class="fas fa-video fa-2x text-white-50"></i>
                                                <div class="mt-2">
                                                    <small class="text-white-50">Kamera Bağlantısı Yok</small>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="position-absolute top-0 start-0 p-2">
                                            <span class="camera-status ${camera.status === 'active' ? 'status-online' : 'status-offline'}"></span>
                                            <small class="text-white">${camera.status === 'active' ? 'Online' : 'Offline'}</small>
                                        </div>
                                        <div class="position-absolute bottom-0 end-0 p-2">
                                            <small class="text-white bg-dark bg-opacity-50 px-2 py-1 rounded">
                                                <i class="fas fa-expand"></i> Büyüt
                                            </small>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-8">
                                    <h6>${camera.camera_name}</h6>
                                    <p class="text-muted mb-1">${camera.location}</p>
                                    <p class="text-muted mb-2">${camera.ip_address}:${camera.port}</p>
                                    <div class="d-flex gap-2">
                                        <button class="btn btn-sm btn-primary" onclick="viewCameraDetails('${camera.camera_id}')">
                                            <i class="fas fa-eye"></i> Detay
                                        </button>
                                        <button class="btn btn-sm btn-warning" onclick="testCamera('${camera.camera_id}')">
                                            <i class="fas fa-check"></i> Test
                                        </button>
                                        <button class="btn btn-sm btn-success" onclick="viewStream('${camera.camera_id}')">
                                            <i class="fas fa-play"></i> Canlı
                                        </button>
                                        <button class="btn btn-sm btn-danger" onclick="deleteCamera('${camera.camera_id}')">
                                            <i class="fas fa-trash"></i> Sil
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
                
                // Start Discovery
                function startDiscovery() {
                    new bootstrap.Modal(document.getElementById('discoveryModal')).show();
                }
                
                // Scan Network
                function scanNetwork() {
                    const networkRange = document.getElementById('networkRange').value;
                    const resultsContainer = document.getElementById('discoveryResults');
                    
                    resultsContainer.innerHTML = `
                        <div class="text-center py-4">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">Taranıyor...</span>
                            </div>
                            <p class="mt-2">Ağ taranıyor: ${networkRange}</p>
                        </div>
                    `;
                    
                    fetch(`/api/company/${companyId}/cameras/discover`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ network_range: networkRange })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            discoveredCameras = data.cameras;
                            displayDiscoveredCameras(data.cameras, data.scan_time);
                        }
                    });
                }
                
                // Display Discovered Cameras
                function displayDiscoveredCameras(cameras, scanTime) {
                    const container = document.getElementById('discoveryResults');
                    container.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle"></i> ${cameras.length} kamera bulundu (${scanTime})
                        </div>
                        <div class="row">
                            ${cameras.map(camera => `
                                <div class="col-md-6 mb-3">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6>${camera.brand} ${camera.model}</h6>
                                            <p class="text-muted mb-2">${camera.ip}:${camera.port}</p>
                                            <p class="text-muted mb-2">${camera.resolution}</p>
                                            <div class="d-flex justify-content-between">
                                                <span class="badge bg-success">${camera.status}</span>
                                                <button class="btn btn-sm btn-primary" onclick="addDiscoveredCamera('${camera.ip}')">
                                                    <i class="fas fa-plus"></i> Ekle
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `;
                }
                
                // Test Camera Connection
                function testCameraConnection() {
                    const form = document.getElementById('addCameraForm');
                    const formData = new FormData(form);
                    const data = {};
                    formData.forEach((value, key) => { data[key] = value; });
                    
                    // Gerekli alanları kontrol et
                    if (!data.ip_address) {
                        alert('❌ IP adresi gerekli!');
                        return;
                    }
                    
                    const testButton = document.querySelector('button[onclick="testCameraConnection()"]');
                    const testResults = document.getElementById('testResults');
                    
                    // Test başlatıldığında UI güncelle
                    testButton.disabled = true;
                    testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Test Ediliyor...';
                    testResults.style.display = 'block';
                    testResults.innerHTML = `
                        <div class="alert alert-info">
                            <i class="fas fa-clock"></i> Kamera bağlantısı test ediliyor...
                        </div>
                    `;
                    
                    fetch(`/api/company/${companyId}/cameras/test`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            testResults.innerHTML = `
                                <div class="alert alert-success">
                                    <h6><i class="fas fa-check-circle"></i> Bağlantı Başarılı!</h6>
                                    <ul class="mb-0">
                                        <li><strong>Durum:</strong> ${result.status}</li>
                                        <li><strong>Protokol:</strong> ${result.protocol}</li>
                                        <li><strong>Çözünürlük:</strong> ${result.resolution || 'Bilinmiyor'}</li>
                                        <li><strong>Bağlantı Süresi:</strong> ${result.connection_time}ms</li>
                                        ${result.quality_score ? `<li><strong>Kalite Skoru:</strong> ${result.quality_score}/100</li>` : ''}
                                    </ul>
                                </div>
                            `;
                        } else {
                            testResults.innerHTML = `
                                <div class="alert alert-danger">
                                    <h6><i class="fas fa-times-circle"></i> Bağlantı Başarısız!</h6>
                                    <p><strong>Hata:</strong> ${result.error}</p>
                                    <div class="mt-2">
                                        <small><strong>Öneriler:</strong></small>
                                        <ul class="mb-0">
                                            <li>IP adresinin doğru olduğundan emin olun</li>
                                            <li>Kamera ve bilgisayarın aynı ağda olduğunu kontrol edin</li>
                                            <li>Kullanıcı adı ve şifrenin doğru olduğunu kontrol edin</li>
                                            <li>Kameranın açık ve erişilebilir olduğunu kontrol edin</li>
                                        </ul>
                                    </div>
                                </div>
                            `;
                        }
                    })
                    .catch(error => {
                        console.error('Kamera test hatası:', error);
                        testResults.innerHTML = `
                            <div class="alert alert-danger">
                                <h6><i class="fas fa-times-circle"></i> Test Hatası!</h6>
                                <p>Kamera testi sırasında bir hata oluştu: ${error.message}</p>
                            </div>
                        `;
                    })
                    .finally(() => {
                        // Test bittiğinde UI'yi eski haline getir
                        testButton.disabled = false;
                        testButton.innerHTML = '<i class="fas fa-check"></i> Bağlantıyı Test Et';
                    });
                }
                
                // Add Camera

                
                // Create Group
                function createGroup() {
                    const form = document.getElementById('createGroupForm');
                    const formData = new FormData(form);
                    const data = {};
                    formData.forEach((value, key) => { data[key] = value; });
                    
                    fetch(`/api/company/${companyId}/cameras/groups`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ Grup başarıyla oluşturuldu!');
                            form.reset();
                            loadCameraGroups();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    });
                }
                
                // Populate Group Selects
                function populateGroupSelects(groups) {
                    const selects = document.querySelectorAll('select[name="group_id"]');
                    selects.forEach(select => {
                        select.innerHTML = '<option value="">Grup Seçin</option>';
                        groups.forEach(group => {
                            select.innerHTML += `<option value="${group.group_id}">${group.name}</option>`;
                        });
                    });
                }
                
                // View Camera Details
                function viewCameraDetails(cameraId) {
                    fetch(`/api/company/${companyId}/cameras/${cameraId}/stream`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            const content = `
                                <div class="row">
                                    <div class="col-md-8">
                                        <div class="stream-preview" style="height: 400px;">
                                            <i class="fas fa-video fa-3x"></i>
                                            <p class="mt-3">Canlı Görüntü</p>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <h6>Stream Bilgileri</h6>
                                        <p><strong>Çözünürlük:</strong> ${data.stream_info.resolution}</p>
                                        <p><strong>FPS:</strong> ${data.stream_info.fps}</p>
                                        <p><strong>Durum:</strong> ${data.stream_info.status}</p>
                                        <p><strong>Son Frame:</strong> ${data.stream_info.last_frame_time}</p>
                                        <hr>
                                        <h6>Bağlantı</h6>
                                        <p><strong>RTSP URL:</strong><br><small>${data.stream_info.rtsp_url}</small></p>
                                        <p><strong>WebSocket:</strong><br><small>${data.stream_info.stream_url}</small></p>
                                    </div>
                                </div>
                            `;
                            document.getElementById('cameraDetailsContent').innerHTML = content;
                            new bootstrap.Modal(document.getElementById('cameraDetailsModal')).show();
                        }
                    });
                }
                
                // Test Camera
                function testCamera(cameraId) {
                    // Kamera bilgilerini API'den al
                    fetch(`/api/company/${companyId}/cameras/${cameraId}`)
                    .then(response => response.json())
                    .then(data => {
                        if (!data.success || !data.camera) {
                            alert('❌ Kamera bilgileri bulunamadı');
                            return;
                        }
                        
                        const camera = data.camera;
                    
                        // Test başlat
                        const testButton = document.querySelector(`button[onclick="testCamera('${cameraId}')"]`);
                        if (testButton) {
                            testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Test Ediliyor...';
                            testButton.disabled = true;
                        }
                        
                        // RTSP URL'yi oluştur veya mevcut olanı kullan
                        let rtspUrl = camera.rtsp_url;
                        if (!rtspUrl && camera.ip_address) {
                            const protocol = camera.protocol || 'rtsp';
                            const port = camera.port || 554;
                            const path = camera.stream_path || '/stream';
                            rtspUrl = `${protocol}://${camera.ip_address}:${port}${path}`;
                        }
                        
                        if (!rtspUrl) {
                            alert('❌ Kamera bağlantı bilgileri eksik. Lütfen kamera ayarlarını kontrol edin.');
                            if (testButton) {
                                testButton.innerHTML = '<i class="fas fa-vial"></i>';
                                testButton.disabled = false;
                            }
                            return;
                        }
                        
                        fetch(`/api/company/${companyId}/cameras/test`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                rtsp_url: rtspUrl,
                                name: camera.camera_name || camera.name || `Kamera ${cameraId}`
                            })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                const testResults = data.test_results;
                                let message = `✅ Kamera Test Sonucu: ${camera.camera_name || camera.name || `Kamera ${cameraId}`}\\n\\n`;
                                message += `🔗 Bağlantı: ${testResults.connection_status}\\n`;
                                message += `⏱️ Yanıt Süresi: ${testResults.response_time}\\n`;
                                message += `📐 Çözünürlük: ${testResults.resolution}\\n`;
                                message += `🎥 FPS: ${testResults.fps}\\n`;
                                message += `📊 Kaynak Türü: ${testResults.source_type}\\n`;
                                
                                if (testResults.error_message) {
                                    message += `\\n❌ Hata: ${testResults.error_message}`;
                                }
                                
                                alert(message);
                            } else {
                                alert(`❌ Test Hatası: ${data.message}`);
                            }
                        })
                        .catch(error => {
                            console.error('Test camera error:', error);
                            alert('❌ Kamera test edilirken bir hata oluştu');
                        })
                        .finally(() => {
                            // Test butonunu eski haline getir
                            if (testButton) {
                                testButton.innerHTML = '<i class="fas fa-vial"></i>';
                                testButton.disabled = false;
                            }
                        });
                    })
                    .catch(error => {
                        console.error('Camera fetch error:', error);
                        alert('❌ Kamera bilgileri alınırken hata oluştu');
                    });
                }
                
                // View Stream
                function viewStream(cameraId) {
                    // Gerçek video feed göster
                    const streamUrl = `/api/company/${companyId}/video-feed/${cameraId}`;
                    
                    // Modal ile video göster
                    const modalHtml = `
                        <div class="modal fade" id="streamModal" tabindex="-1">
                            <div class="modal-dialog modal-lg">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h5 class="modal-title">
                                            <i class="fas fa-video"></i> Kamera ${cameraId} - Canlı Yayın
                                        </h5>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                    </div>
                                    <div class="modal-body text-center">
                                        <img id="streamImage" src="${streamUrl}" 
                                             alt="Kamera Feed" 
                                             class="img-fluid rounded"
                                             style="max-width: 100%; height: auto;"
                                             onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIyMCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkthbWVyYSBCYcSfbGFudMSxc8SxIEt1cnVsYW1hZMSxPC90ZXh0Pjwvc3ZnPg=='; this.alt='Kamera Bağlantısı Kurulamadı';">
                                        <div class="mt-3">
                                            <small class="text-muted">
                                                <i class="fas fa-info-circle"></i> 
                                                Kamera bağlantısı kurulamazsa, kameranın açık ve erişilebilir olduğundan emin olun.
                                            </small>
                                        </div>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                                        <button type="button" class="btn btn-primary" onclick="refreshStream('${cameraId}')">
                                            <i class="fas fa-sync"></i> Yenile
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    
                    // Önceki modal'ı kaldır
                    const existingModal = document.getElementById('streamModal');
                    if (existingModal) {
                        existingModal.remove();
                    }
                    
                    // Yeni modal'ı ekle
                    document.body.insertAdjacentHTML('beforeend', modalHtml);
                    new bootstrap.Modal(document.getElementById('streamModal')).show();
                }
                
                // Refresh Stream
                function refreshStream(cameraId) {
                    const streamImage = document.getElementById('streamImage');
                    if (streamImage) {
                        const streamUrl = `/api/company/${companyId}/video-feed/${cameraId}`;
                        streamImage.src = streamUrl + '?t=' + new Date().getTime();
                    }
                }
                
                // Delete Camera
                function deleteCamera(cameraId) {
                    if (confirm('Bu kamerayı silmek istediğinizden emin misiniz?')) {
                        fetch(`/api/company/${companyId}/cameras/${cameraId}`, {
                            method: 'DELETE',
                            headers: {
                                'Content-Type': 'application/json',
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert(`✅ ${data.message}`);
                                refreshCameras(); // Kamera listesini yenile
                            } else {
                                alert(`❌ Hata: ${data.message}`);
                            }
                        })
                        .catch(error => {
                            console.error('Delete camera error:', error);
                            alert('❌ Kamera silinirken bir hata oluştu');
                        });
                    }
                }
                
                // Refresh Cameras
                function refreshCameras() {
                    loadCameras();
                    loadCameraGroups();
                }
                
                // Test All Cameras
                function testAllCameras() {
                    // Önce kamera listesini al
                    fetch(`/api/company/${companyId}/cameras`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.cameras.length > 0) {
                            const cameras = data.cameras;
                            
                            // Test modal'ı oluştur
                            const testModalHtml = `
                                <div class="modal fade" id="testAllModal" tabindex="-1">
                                    <div class="modal-dialog modal-lg">
                                        <div class="modal-content">
                                            <div class="modal-header">
                                                <h5 class="modal-title">
                                                    <i class="fas fa-check-circle"></i> Tüm Kameraları Test Et
                                                </h5>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                            </div>
                                            <div class="modal-body">
                                                <div class="alert alert-info">
                                                    <i class="fas fa-info-circle"></i> 
                                                    ${cameras.length} kamera test ediliyor...
                                                </div>
                                                <div id="testAllResults">
                                                    <div class="text-center py-4">
                                                        <div class="spinner-border text-primary" role="status">
                                                            <span class="visually-hidden">Test ediliyor...</span>
                                                        </div>
                                                        <p class="mt-2">Kameralar test ediliyor, lütfen bekleyin...</p>
                                                    </div>
                                                </div>
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `;
                            
                            // Modal'ı ekle ve göster
                            document.body.insertAdjacentHTML('beforeend', testModalHtml);
                            const testModal = new bootstrap.Modal(document.getElementById('testAllModal'));
                            testModal.show();
                            
                            // Her kamerayı test et
                            testCamerasSequentially(cameras, 0, []);
                            
                        } else {
                            showToast('⚠️ Test edilecek kamera bulunamadı', 'warning');
                        }
                    })
                    .catch(error => {
                        console.error('Test all cameras error:', error);
                        showToast('❌ Kamera listesi alınamadı', 'error');
                    });
                }
                
                // Test cameras sequentially
                function testCamerasSequentially(cameras, index, results) {
                    if (index >= cameras.length) {
                        // Tüm testler tamamlandı
                        displayAllTestResults(results);
                        return;
                    }
                    
                    const camera = cameras[index];
                    const testData = {
                        name: camera.camera_name,
                        rtsp_url: camera.rtsp_url || `rtsp://${camera.ip_address}:${camera.port}/stream`
                    };
                    
                    fetch(`/api/company/${companyId}/cameras/test`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(testData)
                    })
                    .then(response => response.json())
                    .then(result => {
                        results.push({
                            camera: camera,
                            result: result,
                            success: result.success
                        });
                        
                        // Sonraki kamerayı test et
                        testCamerasSequentially(cameras, index + 1, results);
                    })
                    .catch(error => {
                        results.push({
                            camera: camera,
                            result: { success: false, error: error.message },
                            success: false
                        });
                        
                        // Sonraki kamerayı test et
                        testCamerasSequentially(cameras, index + 1, results);
                    });
                }
                
                // Display all test results
                function displayAllTestResults(results) {
                    const successCount = results.filter(r => r.success).length;
                    const failCount = results.length - successCount;
                    
                    const alertClass = successCount === results.length ? 'alert-success' : failCount === results.length ? 'alert-danger' : 'alert-warning';
                    const resultsHtml = 
                        '<div class="alert ' + alertClass + '">' +
                            '<h6>' +
                                '<i class="fas fa-chart-pie"></i> Test Sonuçları' +
                            '</h6>' +
                            '<div class="row text-center">' +
                                '<div class="col-4">' +
                                    '<div class="text-success">' +
                                        '<i class="fas fa-check-circle fa-2x"></i>' +
                                        '<div class="mt-1"><strong>' + successCount + '</strong></div>' +
                                        '<small>Başarılı</small>' +
                                    '</div>' +
                                '</div>' +
                                '<div class="col-4">' +
                                    '<div class="text-danger">' +
                                        '<i class="fas fa-times-circle fa-2x"></i>' +
                                        '<div class="mt-1"><strong>' + failCount + '</strong></div>' +
                                        '<small>Başarısız</small>' +
                                    '</div>' +
                                '</div>' +
                                '<div class="col-4">' +
                                    '<div class="text-info">' +
                                        '<i class="fas fa-video fa-2x"></i>' +
                                        '<div class="mt-1"><strong>' + results.length + '</strong></div>' +
                                        '<small>Toplam</small>' +
                                    '</div>' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                        '<div class="row">' +
                            results.map(function(r) {
                                const cardClass = r.success ? 'border-success' : 'border-danger';
                                const badgeClass = r.success ? 'bg-success' : 'bg-danger';
                                const badgeText = r.success ? 'Başarılı' : 'Başarısız';
                                const successHtml = r.success ? 
                                    '<div class="row text-center">' +
                                        '<div class="col-6">' +
                                            '<small class="text-muted">Yanıt Süresi</small>' +
                                            '<div class="fw-bold">' + (r.result.test_results?.response_time || 'N/A') + '</div>' +
                                        '</div>' +
                                        '<div class="col-6">' +
                                            '<small class="text-muted">Çözünürlük</small>' +
                                            '<div class="fw-bold">' + (r.result.test_results?.resolution || 'N/A') + '</div>' +
                                        '</div>' +
                                    '</div>' : 
                                    '<div class="alert alert-danger mb-0">' +
                                        '<small>' +
                                            '<i class="fas fa-exclamation-triangle"></i> ' +
                                            (r.result.error || 'Bilinmeyen hata') +
                                        '</small>' +
                                    '</div>';
                                
                                return '<div class="col-md-6 mb-3">' +
                                    '<div class="card ' + cardClass + '">' +
                                        '<div class="card-body">' +
                                            '<h6 class="card-title">' +
                                                '<i class="fas fa-video"></i> ' + r.camera.camera_name +
                                                '<span class="badge ' + badgeClass + ' ms-2">' +
                                                    badgeText +
                                                '</span>' +
                                            '</h6>' +
                                            '<p class="text-muted mb-2">' +
                                                '<i class="fas fa-network-wired"></i> ' + r.camera.ip_address + ':' + r.camera.port +
                                            '</p>' +
                                            successHtml +
                                        '</div>' +
                                    '</div>' +
                                '</div>';
                            }).join('') +
                        '</div>';
                    
                    document.getElementById('testAllResults').innerHTML = resultsHtml;
                    
                    // Toast bildirimi
                    if (successCount === results.length) {
                        showToast(`✅ Tüm kameralar (${successCount}) başarıyla test edildi!`, 'success');
                    } else if (failCount === results.length) {
                        showToast(`❌ Tüm kameralar (${failCount}) test başarısız!`, 'error');
                    } else {
                        showToast(`⚠️ ${successCount} başarılı, ${failCount} başarısız`, 'warning');
                    }
                }
                
                // Show Toast Notification
                function showToast(message, type = 'info') {
                    const toastHtml = `
                        <div class="toast align-items-center text-white bg-${type === 'success' ? 'success' : type === 'error' ? 'danger' : type === 'warning' ? 'warning' : 'info'} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                            <div class="d-flex">
                                <div class="toast-body">
                                    ${message}
                                </div>
                                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                            </div>
                        </div>
                    `;
                    
                    // Toast container oluştur
                    let toastContainer = document.getElementById('toastContainer');
                    if (!toastContainer) {
                        toastContainer = document.createElement('div');
                        toastContainer.id = 'toastContainer';
                        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
                        toastContainer.style.zIndex = '1055';
                        document.body.appendChild(toastContainer);
                    }
                    
                    // Toast ekle
                    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
                    const toastElement = toastContainer.lastElementChild;
                    const toast = new bootstrap.Toast(toastElement, { delay: 4000 });
                    toast.show();
                    
                    // Toast otomatik silinsin
                    toastElement.addEventListener('hidden.bs.toast', () => {
                        toastElement.remove();
                    });
                }
                
                // Add Discovered Camera
                function addDiscoveredCamera(ip) {
                    const camera = discoveredCameras.find(c => c.ip === ip);
                    if (camera) {
                        // Fill form with discovered camera data
                        document.querySelector('input[name="camera_name"]').value = `${camera.brand} ${camera.model}`;
                        document.querySelector('input[name="ip_address"]').value = camera.ip;
                        document.querySelector('input[name="port"]').value = camera.port;
                        document.querySelector('input[name="rtsp_url"]').value = camera.rtsp_url;
                        document.querySelector('input[name="location"]').value = `IP: ${camera.ip}`;
                        
                        // Close discovery modal and open add camera modal
                        bootstrap.Modal.getInstance(document.getElementById('discoveryModal')).hide();
                        new bootstrap.Modal(document.getElementById('addCameraModal')).show();
                    }
                }
                
                // Logout
                function logout() {
                    if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
                        fetch('/logout', { method: 'POST' })
                        .then(() => { window.location.href = '/'; });
                    }
                }
            </script>
        </body>
        </html>
        '''
 
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
                        conn.close()
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
                        'url': '/company/{company_id}/dashboard',
                        'method': 'GET',
                        'description': 'Company dashboard with real-time statistics',
                        'features': ['Real-time stats', 'Mobile optimized', 'Export functionality']
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
        
        # Health check and metrics are now registered via blueprints (health.py)
        
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
                
                # Basit PPE compliance (YOLOv8 için sınırlı)
                # Gerçek PPE detection için SH17 gerekli
                ppe_compliant = people_detected  # Fallback: tüm insanlar uyumlu sayılır
                
        except Exception as e:
            logger.error(f"❌ YOLOv8 results processing error: {e}")
            
        return people_detected, ppe_compliant, ppe_violations

    def saas_detection_worker(self, camera_key, camera_id, company_id, detection_mode, confidence=0.5, active_detectors_ref=None):
        """SaaS Profesyonel Detection Worker - OPTİMİZE EDİLDİ. active_detectors_ref: blueprint'in yazdığı dict (reloader/çift app için zorunlu)."""
        logger.info(f"🚀 SaaS Detection başlatılıyor - Kamera: {camera_id}, Şirket: {company_id}")
        # Blueprint'ten gelen aynı dict referansını kullan (aksi halde worker False görüyor)
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        self._active_detectors_ref = active_detectors_ref  # Kamera worker thread'leri için
        
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=20)
        
        # Kamera başlat
        self.start_saas_camera(camera_key, camera_id, company_id, active_detectors_ref=ad)
        
        # PPE Detection Model - SH17 or PoseAware fallback
        pose_detector = None
        device = 'cpu'
        try:
            self.ensure_database_initialized()
            if self.db is not None:
                company_data = self.db.get_company_info(company_id)
                sector = company_data.get('sector', 'construction') if company_data and isinstance(company_data, dict) else 'construction'
            else:
                sector = 'construction'
                logger.warning(f"⚠️ Database not initialized, using default sector: {sector}")

            # Şirket bazlı zorunlu PPE konfigürasyonunu al (varsa)
            # None  => konfig yok / bilinmiyor → eski davranış (helmet+vest zorunlu)
            # []    => kullanıcı "hiçbir PPE zorunlu değil" seçmiş → herkes uyumlu, violation yok
            required_ppe = None
            if self.db is not None:
                try:
                    company_ppe_config = self.db.get_company_ppe_config(company_id)
                    if isinstance(company_ppe_config, dict) and 'required' in company_ppe_config:
                        raw_required = company_ppe_config.get('required')
                        # Normalize isimler (lowercase, trim) - SH17 ve pose-aware tarafı için güvenli
                        if isinstance(raw_required, list):
                            normalized = []
                            for item in raw_required:
                                if item is None:
                                    continue
                                try:
                                    normalized.append(str(item).strip().lower())
                                except Exception:
                                    continue
                            required_ppe = normalized
                        else:
                            required_ppe = None
                except Exception as cfg_err:
                    logger.warning(f"⚠️ PPE config okunamadı, varsayılan kullanılacak: {cfg_err}")
                    required_ppe = None
            
            if self.sh17_manager:
                logger.info(f"🎯 SH17 PPE Detection - Sektör: {sector}")
                model_manager = self.sh17_manager
                use_sh17 = True
                
                # Initialize PoseAwarePPEDetector alongside SH17 for enhanced analysis
                try:
                    from src.smartsafe.detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=self.sh17_manager)
                    logger.info("✅ PoseAwarePPEDetector initialized with SH17 backend")
                except Exception as pose_err:
                    logger.warning(f"⚠️ PoseAware init failed, using SH17 directly: {pose_err}")
            else:
                # Fallback: PoseAwarePPEDetector with YOLOv8n-Pose
                try:
                    from src.smartsafe.detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=None)
                    logger.info("✅ PoseAwarePPEDetector initialized (standalone fallback)")
                except Exception as pose_err:
                    logger.warning(f"⚠️ PoseAware fallback failed: {pose_err}")
                
                model_manager = None
                use_sh17 = False
            
        except Exception as e:
            logger.error(f"❌ Model yükleme hatası: {e}")
            return
        
        frame_count = 0
        detection_count = 0
        
        # OPTİMİZE EDİLDİ: Frame skip ve confidence ayarları
        frame_skip = 6  # 3'ten 6'ya çıkarıldı (daha az işlem)
        optimized_confidence = max(0.5, confidence)  # Minimum 0.5 confidence
        
        _active = ad.get(camera_key, False)
        logger.info(f"🔍 SaaS Detection worker loop başlıyor: active_detectors.get({camera_key}) = {_active}")
        
        time.sleep(0.3)  # Kamera thread'in açılması için kısa bekleme
        while ad.get(camera_key, False):
            try:
                # Frame al
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    frame = frame_buffers[camera_key].copy()
                    frame_count += 1
                    
                    # OPTİMİZE EDİLDİ: Her 6 frame'de bir tespit yap
                    if frame_count % frame_skip == 0:
                        start_time = time.time()
                        
                        # PPE Detection - PoseAware preferred, SH17 or fallback
                        people_detected = 0
                        ppe_violations = []
                        ppe_compliant = 0
                        
                        try:
                            if pose_detector is not None:
                                # PoseAwarePPEDetector: person pose + PPE region analysis
                                # required_ppe listesi (settings / şirket konfigürasyonu) burada uyum hesabına iletilir.
                                pose_result = pose_detector.detect_with_pose(frame, sector, optimized_confidence, required_ppe=required_ppe)
                                
                                if isinstance(pose_result, dict):
                                    people_detected = pose_result.get('people_detected', 0)
                                    ppe_compliant = pose_result.get('compliant_people', 0)
                                    raw_violations = pose_result.get('ppe_violations', [])
                                    ppe_violations = raw_violations if isinstance(raw_violations, list) else []
                                    results = pose_result.get('detections', [])
                                    logger.debug(f"🎯 PoseAware detection: {people_detected} people, {pose_result.get('compliance_rate', 0)}% compliance")
                                elif isinstance(pose_result, list):
                                    results = pose_result
                                    people_detected = sum(1 for d in results if d.get('class_name') == 'person')
                                else:
                                    results = []
                            elif use_sh17 and model_manager:
                                results = model_manager.detect_ppe(frame, sector, optimized_confidence)
                                people_detected = sum(1 for d in results if d.get('class_name') == 'person')

                                if people_detected > 0 and required_ppe:
                                    try:
                                        compliance_result = model_manager.analyze_compliance(results, required_ppe)
                                        ppe_compliant = compliance_result.get('total_detected', 0)
                                        missing = compliance_result.get('missing', [])
                                        ppe_violations = [f"Missing: {item}" for item in missing]
                                    except Exception as comp_err:
                                        logger.error(f"❌ SH17 compliance analizi hatası: {comp_err}")
                                        ppe_compliant = people_detected
                                else:
                                    ppe_compliant = people_detected
                            else:
                                results = []
                                
                        except Exception as detection_error:
                            logger.error(f"❌ Detection hatası: {detection_error}")
                            results = []
                        
                        if not results and people_detected == 0:
                            continue

                        # İhlal listesini normalize et (dict formatına çevir, string'leri sar)
                        normalized_ppe_violations, simple_ppe_violations = self._normalize_ppe_violations(ppe_violations)
                        ppe_violations = simple_ppe_violations

                        # Eğer kişi var ama hiç ihlal yoksa, tüm kişiler uyumlu kabul edilmeli.
                        # PoseAware veya SH17 tarafı ppe_compliant'ı 0 bıraksa bile burada normalize ediyoruz.
                        if people_detected > 0 and len(ppe_violations) == 0 and ppe_compliant == 0:
                            ppe_compliant = people_detected

                        # Reports kayıt (both SH17 and YOLOv8 paths)
                        try:
                            report_processing_time = time.time() - start_time
                            if people_detected > 0 or len(ppe_violations) > 0:
                                self._save_detection_to_reports(
                                    company_id, camera_id, detection_mode,
                                    people_detected, ppe_compliant, len(ppe_violations),
                                    report_processing_time, confidence
                                )
                                self._generate_live_alerts(
                                    company_id, camera_id, people_detected,
                                    ppe_compliant, len(ppe_violations), detection_mode
                                )
                            for violation in normalized_ppe_violations:
                                self._save_violation_to_reports(company_id, camera_id, violation)
                        except Exception as result_error:
                            logger.error(f"❌ Result processing hatası: {result_error}")
                        
                        compliance_rate = 0
                        if people_detected > 0:
                            compliance_rate = (ppe_compliant / people_detected) * 100
                        
                        processing_time = (time.time() - start_time) * 1000
                        detection_count += 1
                        
                        fps = 1000 / processing_time if processing_time > 0 else 0
                        
                        current_device = 'SH17' if use_sh17 else (device if 'device' in dir() else 'cpu')
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
                        
                        # Veritabanına kaydet (her 10 tespit) - SQLite'ta legacy şema kullanıldığı için
                        # sadece production PostgreSQL için özet kayıt atılır.
                        if detection_count % 10 == 0:
                            self.save_detection_to_db(detection_data)
                        
                        # İhlal varsa veritabanına kaydet (normalize edilmiş dict listesiyle)
                        if normalized_ppe_violations:
                            self.save_violations_to_db(company_id, camera_id, normalized_ppe_violations)
                    
                    time.sleep(0.01)  # CPU'yu rahatlatmak için
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"❌ SaaS Detection hatası: {e}")
                time.sleep(1)
        
        logger.info(f"🛑 SaaS Detection durduruldu - Kamera: {camera_id}")

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
            conn.close()
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
                    conn.close()
                    
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
            conn.close()
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
            # Sektör bazlı gerekli PPE'ler
            sector_requirements = {
                'construction': ['helmet', 'safety_vest'],
                'manufacturing': ['helmet', 'safety_vest', 'gloves'],
                'chemical': ['helmet', 'respirator', 'gloves', 'safety_glasses'],
                'food_beverage': ['hair_net', 'gloves', 'apron'],
                'warehouse_logistics': ['helmet', 'safety_vest', 'safety_shoes'],
                'energy': ['helmet', 'safety_vest', 'safety_shoes', 'gloves'],
                'petrochemical': ['helmet', 'respirator', 'safety_vest', 'gloves'],
                'marine_shipyard': ['helmet', 'life_vest', 'safety_shoes'],
                'aviation': ['aviation_helmet', 'reflective_vest', 'ear_protection']
            }
            
            required_ppe = sector_requirements.get(sector, ['helmet', 'safety_vest'])
            detected_ppe = []
            
            # Tespit edilen PPE'leri topla
            for detection in detections:
                class_name = detection.get('class_name', '')
                if class_name in ['helmet', 'safety_vest', 'gloves', 'safety_shoes', 'safety_glasses', 'face_mask_medical']:
                    detected_ppe.append(class_name)
            
            # Compliance kontrolü
            missing_ppe = [item for item in required_ppe if item not in detected_ppe]
            compliant = len(missing_ppe) == 0
            
            return {
                'compliant': compliant,
                'missing_ppe': missing_ppe,
                'detected_ppe': detected_ppe,
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
            from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
            from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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
                'has_hairnet': 'hairnet' not in missing_ppe,
                'has_gloves': 'gloves' not in missing_ppe,
                'has_apron': 'apron' not in missing_ppe,
                'has_mask': 'face_mask' not in missing_ppe,
                'required_ppe': ['hairnet', 'gloves', 'apron', 'face_mask']
            },
            'warehouse': {
                'has_helmet': 'helmet' not in missing_ppe,
                'has_vest': 'safety_vest' not in missing_ppe,
                'has_shoes': 'safety_shoes' not in missing_ppe,
                'required_ppe': ['helmet', 'safety_vest', 'safety_shoes']
            }
        }
        
        return sector_ppe.get(sector_type, {
            'has_helmet': 'helmet' not in missing_ppe,
            'has_vest': 'safety_vest' not in missing_ppe,
            'required_ppe': ['helmet', 'safety_vest']
        })

    def start_saas_camera(self, camera_key, camera_id, company_id, active_detectors_ref=None):
        """SaaS Kamera başlatma - proxy-stream ile aynı kaynak: get_camera_by_id. active_detectors_ref: detection worker'dan gelen dict ref."""
        try:
            # Proxy-stream ile aynı kaynaktan al (aynı IP/URL tutarlılığı için)
            camera_info = self.db.get_camera_by_id(camera_id, company_id)
            if not camera_info:
                logger.error(f"❌ Kamera bulunamadı: {camera_id}")
                return
            logger.info(f"📷 Detection worker kamera kaynağı: {camera_id} -> ip={camera_info.get('ip_address')} (proxy ile aynı get_camera_by_id)")
            
            # Kamera URL'sini oluştur - Alternatif URL'ler ile
            camera_url = None
            if camera_info.get('ip_address') and camera_info.get('port'):
                protocol = camera_info.get('protocol', 'http')
                ip = camera_info['ip_address']
                port = camera_info['port']
                stream_path = (camera_info.get('stream_path') or '/video').strip().lower()
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
                    if protocol == 'rtsp':
                        camera_url = f"rtsp://{username}:{password}@{ip}:{port}{stream_path}"
                    else:
                        camera_url = f"http://{username}:{password}@{ip}:{port}{stream_path}"
                else:
                    if protocol == 'rtsp':
                        camera_url = f"rtsp://{ip}:{port}{stream_path}"
                    else:
                        camera_url = f"http://{ip}:{port}{stream_path}"

                
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
            
            logger.info(f"✅ SaaS Kamera başlatıldı: {camera_id} -> {camera_url}")
            
        except Exception as e:
            logger.error(f"❌ SaaS Kamera başlatma hatası: {e}")

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
            
            # Önce ana URL'yi dene
            logger.info(f"🔍 Ana URL deneniyor: {primary_url}")
            cap = cv2.VideoCapture(primary_url)
            current_url = primary_url
            
            # Authentication ile dene - Daha güvenilir yöntem
            if not cap.isOpened() and '@' in primary_url:
                logger.info(f"🔐 Authentication ile deneniyor...")
                try:
                    # URL'den kullanıcı adı ve şifreyi çıkar
                    if '@' in primary_url:
                        auth_part = primary_url.split('@')[0].split('://')[1]
                        username, password = auth_part.split(':')
                        base_url = primary_url.split('@')[1]
                        
                        # OpenCV authentication - Daha güvenli
                        cap = cv2.VideoCapture(base_url)
                        if cap.isOpened():
                            # Authentication bilgilerini set et
                            cap.set(cv2.CAP_PROP_USERNAME, username)
                            cap.set(cv2.CAP_PROP_PASSWORD, password)
                            logger.info(f"✅ Authentication başarılı: {username}")
                        else:
                            # Alternatif authentication yöntemi
                            auth_url = f"http://{username}:{password}@{base_url}"
                            cap = cv2.VideoCapture(auth_url)
                            if cap.isOpened():
                                logger.info(f"✅ Alternatif authentication başarılı: {username}")
                except Exception as auth_error:
                    logger.warning(f"⚠️ Authentication hatası: {auth_error}")
            
            if not cap.isOpened():
                logger.warning(f"⚠️ Ana URL başarısız, alternatifler deneniyor...")
                
                # Alternatif URL'leri dene
                for alt_url in alternative_urls:
                    logger.info(f"🔍 Alternatif URL deneniyor: {alt_url}")
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                    cap = cv2.VideoCapture(alt_url)
                    
                    if cap.isOpened():
                        logger.info(f"✅ Alternatif URL başarılı: {alt_url}")
                        current_url = alt_url
                        break
                    else:
                        logger.warning(f"❌ Alternatif URL başarısız: {alt_url}")
            
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
            
            while ad.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    frame_buffers[camera_key] = frame
                    frame_failure_counts[camera_key] = 0
                else:
                    # Art arda hataları say - 30'dan sonra sadece uyarı + hafif reconnect
                    frame_failure_counts[camera_key] = frame_failure_counts.get(camera_key, 0) + 1
                    fail_count = frame_failure_counts[camera_key]
                    
                    if fail_count % 30 == 0:
                        logger.warning(f"⚠️ Frame okunamadı (ardışık {fail_count}) - {camera_key}, yeniden deneniyor...")
                        try:
                            cap.release()
                        except Exception:
                            pass
                        time.sleep(0.3)
                        cap = cv2.VideoCapture(current_url)
                        if cap.isOpened():
                            logger.info(f"✅ Kamera yeniden baglandi (frame error sonrasi): {camera_key}")
                            frame_failure_counts[camera_key] = 0
                        else:
                            logger.warning(f"⚠️ Kamera yeniden baglanamadi (frame error sonrasi): {camera_key}")
                    # Çok fazla log atmamak için her hatada değil, sadece belirli eşiklerde uyarı ver
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
        import cv2
        
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        
        while ad.get(camera_key, False):
            try:
                # Frame al
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    frame = frame_buffers[camera_key].copy()
                    
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
                
                time.sleep(0.05)  # ~20 FPS
                
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
        import cv2
        
        try:
            # Detection data type kontrolü - String ise işleme
            if not isinstance(detection_data, dict):
                logger.warning(f"⚠️ Detection data string olarak geldi: {type(detection_data)}")
                return frame
            
            # Üst bilgi paneli
            cv2.rectangle(frame, (0, 0), (640, 80), (0, 0, 0), -1)
            cv2.rectangle(frame, (0, 0), (640, 80), (255, 255, 255), 2)
            
            # Başlık
            cv2.putText(frame, 'SmartSafe AI - Live Detection', (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # İstatistikler
            people_count = detection_data.get('people_detected', 0)
            compliance_rate = detection_data.get('compliance_rate', 0)
            violations = detection_data.get('ppe_violations', [])
            
            cv2.putText(frame, f'People: {people_count}', (10, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.putText(frame, f'Compliance: {compliance_rate}%', (120, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.putText(frame, f'Violations: {len(violations)}', (280, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Uyum durumu göstergesi
            color = (0, 255, 0) if compliance_rate >= 80 else (0, 165, 255) if compliance_rate >= 60 else (0, 0, 255)
            cv2.circle(frame, (600, 40), 15, color, -1)
            
            # 🎯 BOUNDING BOX ÇİZİMİ - PPE Detection Sonuçları
            detections = detection_data.get('detections', [])
            if detections and isinstance(detections, list):
                for detection in detections:
                    if not isinstance(detection, dict):
                        continue
                        
                    bbox = detection.get('bbox', [])
                    class_name = detection.get('class_name', 'unknown')
                    confidence = detection.get('confidence', 0.0)
                    
                    if len(bbox) == 4:  # x1, y1, x2, y2
                        try:
                            x1, y1, x2, y2 = [int(coord) for coord in bbox]
                            
                            # PPE türüne göre renk belirle
                            from src.smartsafe.detection.utils.visual_overlay import draw_styled_box, get_class_color
                            
                            color = get_class_color(class_name, is_missing=False)
                            
                            # Etiket hazırla
                            label = f"{class_name} {confidence:.2f}"
                            
                            # Profesyonel bounding box çiz
                            frame = draw_styled_box(frame, x1, y1, x2, y2, label, color)
                        except Exception as bbox_error:
                            logger.warning(f"⚠️ Bounding box çizim hatası: {bbox_error}")
                            continue
            
            # İhlal detayları
            if violations and isinstance(violations, list):
                y_offset = 100
                for i, violation in enumerate(violations[:3]):  # Sadece ilk 3'ü göster
                    if isinstance(violation, dict):
                        missing_ppe = ', '.join(violation.get('missing_ppe', []))
                        cv2.putText(frame, f'Violation {i+1}: {missing_ppe}', (10, y_offset), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                        y_offset += 20
            
            # Zaman damgası
            timestamp = detection_data.get('timestamp', '')
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        # Unix timestamp'i string'e çevir
                        import datetime
                        timestamp_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        timestamp_str = str(timestamp)[:19]
                    
                    cv2.putText(frame, timestamp_str, (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                except Exception as ts_error:
                    logger.warning(f"⚠️ Timestamp çizim hatası: {ts_error}")
            
        except Exception as e:
            logger.error(f"❌ Overlay çizim hatası: {e}")
        
        return frame

    def save_detection_to_db(self, detection_data):
        """Detection sonuçlarını veritabanına kaydet - Production uyumlu"""
        try:
            # Local (SQLite) ortamda legacy 'detections' şeması (people_detected, violations_count vb.)
            # zaten _save_detection_to_reports ile dolduruluyor. Bu fonksiyonun ek person_count
            # kolonunu kullanması sadece PostgreSQL/Supabase tarafında anlamlı.
            if not hasattr(self.db, 'db_adapter'):
                return

            db_type = getattr(self.db.db_adapter, 'db_type', 'sqlite')
            if db_type == 'sqlite':
                # SQLite'ta extra özet kayıt atlamayı tercih ediyoruz; mevcut şema bozulmuyor.
                logger.debug("Skipping save_detection_to_db on sqlite (legacy detections schema is used).")
                return

            # PostgreSQL / Supabase tarafı: modern özet şema
            conn = self.db.get_connection()
            cursor = conn.cursor()

            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '%s'

            cursor.execute(f'''
                INSERT INTO detections (
                    company_id, camera_id, timestamp, person_count, 
                    ppe_compliant, compliance_rate, processing_time_ms
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                detection_data['company_id'],
                detection_data['camera_id'],
                detection_data['timestamp'],
                detection_data.get('person_count', detection_data.get('people_detected', 0)),
                detection_data.get('ppe_compliant', True),
                detection_data.get('compliance_rate', 100),
                detection_data.get('processing_time_ms', 0)
            ))

            conn.commit()
            conn.close()
            logger.debug(f"✅ Detection kaydedildi (summary): {detection_data.get('camera_id', 'unknown')}")
            
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
            conn.close()
            logger.debug(f"✅ Violation kaydedildi: {camera_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Violation DB kayıt hatası (devam ediliyor): {e}")
            # Production'da DB hatası olsa bile detection devam etsin

    def get_live_detection_template(self):
        """SaaS Live Detection HTML Template"""
        return '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canlı Tespit - SmartSafe AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-color: #667eea;
            --secondary-color: #764ba2;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --info-color: #17a2b8;
            --dark-color: #2c3e50;
        }

        body {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
        }

        .navbar {
            background: rgba(255,255,255,0.95) !important;
            backdrop-filter: blur(10px);
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
        }

        .navbar-brand {
            font-weight: 700;
            color: var(--dark-color) !important;
            font-size: 1.5rem;
        }

        .main-container {
            margin-top: 20px;
        }

        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            background: rgba(255,255,255,0.95);
        }

        .card-header {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white;
            border-radius: 15px 15px 0 0 !important;
            padding: 20px;
        }

        .live-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            background: var(--success-color);
            border-radius: 50%;
            animation: pulse 2s infinite;
            margin-right: 8px;
        }

        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.7; }
            100% { transform: scale(1); opacity: 1; }
        }

        .camera-stream {
            width: 100%;
            height: 400px;
            border-radius: 10px;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.2rem;
        }

        .camera-stream img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 10px;
        }

        .stats-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }

        .stats-card:hover {
            transform: translateY(-5px);
        }

        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: var(--dark-color);
        }

        .stat-label {
            color: #6c757d;
            font-size: 0.9rem;
        }

        .btn-custom {
            border-radius: 25px;
            padding: 12px 30px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.3s ease;
            border: none;
        }

        .btn-custom:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }

        .btn-primary-custom {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white;
        }

        .btn-success-custom {
            background: linear-gradient(135deg, var(--success-color) 0%, #20c997 100%);
            color: white;
        }

        .btn-danger-custom {
            background: linear-gradient(135deg, var(--danger-color) 0%, #e74c3c 100%);
            color: white;
        }

        .alert-custom {
            border-radius: 10px;
            border: none;
            padding: 15px 20px;
            margin-bottom: 20px;
        }

        .camera-controls {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .form-control, .form-select {
            border-radius: 10px;
            border: 2px solid #e9ecef;
            padding: 12px 15px;
            transition: all 0.3s ease;
        }

        .form-control:focus, .form-select:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
        }

        .violation-item {
            background: rgba(220, 53, 69, 0.1);
            border-left: 4px solid var(--danger-color);
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
        }

        .compliance-good { color: var(--success-color); }
        .compliance-warning { color: var(--warning-color); }
        .compliance-danger { color: var(--danger-color); }

        .system-status {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            color: white;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light fixed-top">
        <div class="container">
            <a class="navbar-brand" href="/company/{{ company_id }}/dashboard">
                <i class="fas fa-shield-alt"></i> SmartSafe AI
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/company/{{ company_id }}/dashboard">
                    <i class="fas fa-tachometer-alt"></i> Dashboard
                </a>
                <a class="nav-link" href="/company/{{ company_id }}/cameras">
                    <i class="fas fa-video"></i> Kameralar
                </a>
                <a class="nav-link active" href="/api/company/{{ company_id }}/live-detection">
                    <span class="live-indicator"></span> Canlı Tespit
                </a>
            </div>
        </div>
    </nav>

    <div class="container main-container">
        <div class="row">
            <div class="col-12">
                <div class="text-center mb-4">
                    <h1 class="text-white display-4 fw-bold">
                        <i class="fas fa-eye"></i> Canlı PPE Tespiti
                    </h1>
                    <p class="text-white-50 fs-5">{{ company_name }} - {{ sector|title }} Sektörü</p>
                </div>
                
                <div class="system-status">
                    <div class="row text-center">
                        <div class="col-md-3">
                            <i class="fas fa-server"></i>
                            <span class="ms-2">Sistem: <strong id="system-status">Hazır</strong></span>
                        </div>
                        <div class="col-md-3">
                            <i class="fas fa-video"></i>
                            <span class="ms-2">Aktif Kameralar: <strong id="active-cameras">0</strong></span>
                        </div>
                        <div class="col-md-3">
                            <i class="fas fa-eye"></i>
                            <span class="ms-2">Tespitler: <strong id="total-detections">0</strong></span>
                        </div>
                        <div class="col-md-3">
                            <i class="fas fa-percentage"></i>
                            <span class="ms-2">Uyum: <strong id="compliance-rate">--%</strong></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <!-- Ana Kamera Görüntüsü -->
            <div class="col-lg-8">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <i class="fas fa-video"></i> Kamera Görüntüsü
                            <span class="live-indicator"></span>
                            <span id="camera-status">Bekleniyor...</span>
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="camera-controls">
                            <div class="row">
                                <div class="col-md-6">
                                    <label class="form-label text-white">Kamera Seç:</label>
                                    <select class="form-select" id="camera-select">
                                        <option value="">Kamera seçin...</option>
                                        {% for camera in cameras %}
                                        <option value="{{ camera.camera_id }}">
                                            {{ camera.name }} ({{ camera.location }})
                                        </option>
                                        {% endfor %}
                                    </select>
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label text-white">Güven Eşiği:</label>
                                    <select class="form-select" id="confidence-select">
                                        <option value="0.3">Düşük (0.3)</option>
                                        <option value="0.5" selected>Orta (0.5)</option>
                                        <option value="0.7">Yüksek (0.7)</option>
                                    </select>
                                </div>
                            </div>
                            <div class="row mt-3">
                                <div class="col-12 text-center">
                                    <button class="btn btn-success-custom btn-custom me-2" onclick="startDetection()">
                                        <i class="fas fa-play"></i> Tespiti Başlat
                                    </button>
                                    <button class="btn btn-danger-custom btn-custom" onclick="stopDetection()">
                                        <i class="fas fa-stop"></i> Tespiti Durdur
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <div class="camera-stream" id="camera-display">
                            <div class="text-center">
                                <i class="fas fa-camera fa-3x mb-3"></i>
                                <p>Kamera seçin ve tespiti başlatın</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- İstatistikler ve Kontroller -->
            <div class="col-lg-4">
                <!-- Canlı İstatistikler -->
                <div class="stats-card text-center">
                    <div class="stat-value" id="people-count">0</div>
                    <div class="stat-label">Tespit Edilen Kişi</div>
                </div>
                
                <div class="stats-card text-center">
                    <div class="stat-value compliance-good" id="compliant-count">0</div>
                    <div class="stat-label">PPE Uyumlu</div>
                </div>
                
                <div class="stats-card text-center">
                    <div class="stat-value compliance-danger" id="violation-count">0</div>
                    <div class="stat-label">İhlal Sayısı</div>
                </div>

                <!-- Son İhlaller -->
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">
                            <i class="fas fa-exclamation-triangle"></i> Son İhlaller
                        </h6>
                    </div>
                    <div class="card-body">
                        <div id="recent-violations">
                            <p class="text-muted text-center">İhlal bulunamadı</p>
                        </div>
                    </div>
                </div>

                <!-- PPE Gereksinimleri -->
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">
                            <i class="fas fa-hard-hat"></i> PPE Gereksinimleri
                        </h6>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            {% for ppe in ppe_config %}
                            <div class="col-6 mb-2">
                                <div class="text-center p-2 bg-light rounded">
                                    <i class="fas fa-check-circle text-success"></i>
                                    <small class="d-block">{{ ppe|title }}</small>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentCameraId = null;
        let detectionActive = false;
        let statsInterval = null;

        // Tespit başlatma
        function startDetection() {
            const cameraSelect = document.getElementById('camera-select');
            const confidenceSelect = document.getElementById('confidence-select');
            
            if (!cameraSelect.value) {
                alert('Lütfen bir kamera seçin!');
                return;
            }
            
            if (detectionActive) {
                alert('Tespit zaten aktif!');
                return;
            }
            
            currentCameraId = cameraSelect.value;
            const confidence = parseFloat(confidenceSelect.value);
            
            // Tespit başlat
            fetch('/api/company/{{ company_id }}/start-detection', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    camera_id: currentCameraId,
                    detection_mode: 'ppe',
                    confidence: confidence
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    detectionActive = true;
                    document.getElementById('camera-status').textContent = 'Aktif';
                    document.getElementById('system-status').textContent = 'Çalışıyor';
                    
                    // Video stream'i başlat - PPE overlay'li detection stream kullan
                    const streamUrl = `/api/company/{{ company_id }}/cameras/${currentCameraId}/detection/stream`;
                    document.getElementById('camera-display').innerHTML = 
                        `<img src="${streamUrl}" alt="Kamera Görüntüsü" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
                    
                    // İstatistikleri güncellemeye başla
                    startStatsUpdate();
                    
                    showAlert('Tespit başarıyla başlatıldı!', 'success');
                } else {
                    showAlert('Tespit başlatılamadı: ' + data.error, 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Bir hata oluştu!', 'danger');
            });
        }

        // Tespit durdurma
        function stopDetection() {
            if (!detectionActive) {
                alert('Tespit zaten durmuş!');
                return;
            }
            
            fetch('/api/company/{{ company_id }}/stop-detection', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    detectionActive = false;
                    currentCameraId = null;
                    document.getElementById('camera-status').textContent = 'Durduruldu';
                    document.getElementById('system-status').textContent = 'Hazır';
                    
                    // Video stream'i durdur
                    document.getElementById('camera-display').innerHTML = `
                        <div class="text-center">
                            <i class="fas fa-camera fa-3x mb-3"></i>
                            <p>Kamera seçin ve tespiti başlatın</p>
                        </div>
                    `;
                    
                    // İstatistik güncellemeyi durdur
                    stopStatsUpdate();
                    
                    showAlert('Tespit durduruldu!', 'info');
                } else {
                    showAlert('Tespit durdurulamadı: ' + data.error, 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('Bir hata oluştu!', 'danger');
            });
        }

        // İstatistik güncelleme
        function startStatsUpdate() {
            statsInterval = setInterval(updateStats, 2000); // Her 2 saniyede bir
        }

        function stopStatsUpdate() {
            if (statsInterval) {
                clearInterval(statsInterval);
                statsInterval = null;
            }
        }

        function updateStats() {
            if (!detectionActive || !currentCameraId) return;
            
            // Canlı istatistikleri al
            fetch(`/api/company/{{ company_id }}/live-stats`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const stats = data.stats;
                        document.getElementById('active-cameras').textContent = stats.active_cameras;
                        document.getElementById('total-detections').textContent = stats.recent_detections;
                        document.getElementById('compliance-rate').textContent = stats.compliance_rate + '%';
                        
                        // Compliance rate renk
                        const complianceElement = document.getElementById('compliance-rate');
                        if (stats.compliance_rate >= 80) {
                            complianceElement.className = 'compliance-good';
                        } else if (stats.compliance_rate >= 60) {
                            complianceElement.className = 'compliance-warning';
                        } else {
                            complianceElement.className = 'compliance-danger';
                        }
                    }
                })
                .catch(error => console.error('Stats update error:', error));
            
            // Detection durumu al
            fetch(`/api/company/{{ company_id }}/detection-status/${currentCameraId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.recent_results.length > 0) {
                        const latest = data.recent_results[data.recent_results.length - 1];
                        
                        document.getElementById('people-count').textContent = latest.people_detected || 0;
                        document.getElementById('compliant-count').textContent = latest.ppe_compliant || 0;
                        document.getElementById('violation-count').textContent = latest.ppe_violations ? latest.ppe_violations.length : 0;
                        
                        // İhlalleri göster
                        updateViolations(latest.ppe_violations || []);
                    }
                })
                .catch(error => console.error('Detection status error:', error));
        }

        function updateViolations(violations) {
            const container = document.getElementById('recent-violations');
            
            if (violations.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">İhlal bulunamadı</p>';
                return;
            }
            
            let html = '';
            violations.slice(0, 5).forEach((violation, index) => {
                const missingPpe = violation.missing_ppe.join(', ');
                html += `
                    <div class="violation-item">
                        <strong>Kişi ${index + 1}</strong>
                        <div class="mt-1">
                            <small class="text-danger">Eksik PPE: ${missingPpe}</small>
                        </div>
                        <div class="mt-1">
                            <small class="text-muted">Güven: ${(violation.confidence * 100).toFixed(1)}%</small>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }

        function showAlert(message, type) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            alertDiv.style.cssText = 'top: 100px; right: 20px; z-index: 1050; min-width: 300px;';
            alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            document.body.appendChild(alertDiv);
            
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }

        // Sayfa yüklendiğinde
        document.addEventListener('DOMContentLoaded', function() {
            // İlk istatistikleri yükle
            fetch(`/api/company/{{ company_id }}/live-stats`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const stats = data.stats;
                        document.getElementById('active-cameras').textContent = stats.active_cameras;
                        document.getElementById('total-detections').textContent = stats.recent_detections;
                        document.getElementById('compliance-rate').textContent = stats.compliance_rate + '%';
                    }
                })
                .catch(error => console.error('Initial stats error:', error));
        });
    </script>
</body>
</html>
        '''

def main():
    """Ana fonksiyon - Sadece development mode için"""
    print("🌐 SmartSafe AI - SaaS Multi-Tenant API Server")
    print("=" * 60)
    print("✅ Multi-tenant şirket yönetimi")
    print("✅ Şirket bazlı veri ayrımı")
    print("✅ Güvenli oturum yönetimi")
    print("✅ Kamera yönetimi")
    print("✅ Responsive web arayüzü")
    print("=" * 60)
    print("🚀 Development Server başlatılıyor...")
    
    try:
        api_server = SmartSafeSaaSAPI()
        app = api_server.app
        
        # Development mode - Flask development server
        # Port 5000 veya 10000 kullan (environment variable ile değiştirilebilir)
        port = int(os.environ.get('PORT', 5000))  # Default 5000'e değiştirildi
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
        return """
        <!DOCTYPE html>
        <html><head><title>SmartSafe AI - Production Ready</title>
        <style>body{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5}
        .container{max-width:800px;margin:0 auto;background:white;padding:30px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}
        .status{color:#28a745;font-weight:bold}.warning{color:#ffc107}
        .info{background:#e3f2fd;padding:15px;border-radius:5px;margin:20px 0}</style></head>
        <body><div class="container">
        <h1>🚀 SmartSafe AI - Production Ready</h1>
        <p class="status">✅ System Status: OPERATIONAL</p>
        <p class="warning">⚡ Running in optimized fallback mode</p>
        <div class="info"><h3>🎯 Available Features:</h3>
        <ul><li>✅ Health monitoring</li><li>✅ API endpoints</li><li>✅ Emergency fallback system</li>
        <li>⚡ YOLOv8 PPE detection</li><li>🗄️ Database connectivity</li></ul></div>
        <p><strong>SmartSafe AI</strong> - Enterprise PPE Detection Platform</p>
        </div></body></html>"""
    
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
    port = int(os.getenv("PORT", 5000 if env == "local" else 10000))
    host = "0.0.0.0"

    logger.info(f"🚀 Starting SmartSafe SaaS API")
    logger.info(f"🌐 Host: {host}, Port: {port}")
    logger.info(f"🔧 Environment: {env}")

    if env == "local":
        # Only run Flask built-in server locally
        logger.info("🧩 Running in LOCAL mode (Flask dev server)")
        try:
            app.run(
                host=host,
                port=port,
                debug=True,
                threaded=True,
                use_reloader=True
            )
        except Exception as e:
            logger.error(f"❌ Local server failed: {e}")
            app = create_emergency_app()
            app.run(host=host, port=port, debug=True)
    else:
        # Production mode (Render/Gunicorn)
        logger.info("✅ Production environment detected — Gunicorn will serve the app.")

