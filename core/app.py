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
from services.multitenant_system import MultiTenantDatabase
from integrations.construction.construction_ppe_system import ConstructionPPEDetector, ConstructionPPEConfig
from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
from database.database_adapter import get_db_adapter
from integrations.cameras.camera_integration_manager import DVRConfig
from detection.snapshot_manager import get_snapshot_manager
from integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
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
    # Bu dosya: core/app.py
    # parents[0]: core
    # parents[1]: smart-safe (Root)
    BASE_DIR = Path(__file__).resolve().parents[1]
    print(f"📍 Project Base Directory: {BASE_DIR}")
except Exception as e:
    BASE_DIR = Path.cwd().parent if Path.cwd().name == 'backend' else Path.cwd()
    print(f"⚠️ BASE_DIR Fallback: {BASE_DIR}")

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

# Global API server instance for static access
class SmartSafeSaaSAPI:
    """SmartSafe AI SaaS API Server"""
    
    def __init__(self):
        try:
            static_dir = str(BASE_DIR / 'core' / 'static')
            template_dir = str(BASE_DIR / 'core' / 'templates')
            
            # 🎯 CRITICAL: Dosya sistemi güncellendi. 
            # Statik dosyalar (js, images) ve template'ler artık 'core' klasörü altında.
            print(f"📁 Static Directory: {static_dir}")
            print(f"📁 Template Directory: {template_dir}")
            
            self.app = Flask(
                            __name__,
                            template_folder=template_dir,
                            static_folder=static_dir,
                            static_url_path='/static'
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
            models_path = str(BASE_DIR / 'core' / 'models')
            self.sh17_manager = SH17ModelManager(models_dir=models_path)
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
            from integrations.cameras.ppe_detection_manager import PPEDetectionManager
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
        from blueprints import register_all_blueprints
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
                                from database.database_adapter import get_db_adapter
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
                    from detection.utils.visual_overlay import draw_styled_box, get_class_color
                    
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
    
    def saas_detection_worker(self, camera_key, camera_id, company_id, detection_mode, confidence=0.5, active_detectors_ref=None):
        """SaaS Profesyonel Detection Worker - OPTİMİZE EDİLDİ."""
        logger.info(f"🚀 SaaS Detection başlatılıyor - Kamera: {camera_id}, Şirket: {company_id}")
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=20)
        
        # Kamera başlat
        self.start_saas_camera(camera_key, camera_id, company_id, active_detectors_ref=ad)
        
        # PPE Detection Model
        pose_detector = None
        try:
            self.ensure_database_initialized()
            if self.db is not None:
                company_data = self.db.get_company_info(company_id)
                sector = company_data.get('sector', 'construction') if company_data and isinstance(company_data, dict) else 'construction'
            else:
                sector = 'construction'
                logger.warning(f"⚠️ Database not initialized, using default sector: {sector}")

            required_ppe = None
            if self.db is not None:
                try:
                    # required_ppe is stored as a JSON string in the companies table
                    ppe_info = company_data  # already fetched above via get_company_info
                    if ppe_info and isinstance(ppe_info, dict):
                        raw_ppe = ppe_info.get('required_ppe')
                        if raw_ppe is not None:
                            if isinstance(raw_ppe, str):
                                try:
                                    raw_ppe = json.loads(raw_ppe)
                                except (json.JSONDecodeError, ValueError):
                                    raw_ppe = None
                            if isinstance(raw_ppe, list):
                                normalized = []
                                for item in raw_ppe:
                                    if item is None: continue
                                    normalized.append(str(item).strip().lower())
                                required_ppe = normalized if normalized else None
                            elif isinstance(raw_ppe, dict) and 'required' in raw_ppe:
                                raw_required = raw_ppe.get('required')
                                if isinstance(raw_required, list):
                                    normalized = []
                                    for item in raw_required:
                                        if item is None: continue
                                        normalized.append(str(item).strip().lower())
                                    required_ppe = normalized if normalized else None
                except Exception as cfg_err:
                    logger.warning(f"⚠️ PPE config okunamadı: {cfg_err}")
            
            if self.sh17_manager:
                logger.info(f"🎯 SH17 PPE Detection - Sektör: {sector}")
                model_manager = self.sh17_manager
                use_sh17 = True
                
                try:
                    # Absolute import or relative based on core root
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=self.sh17_manager)
                    logger.info("✅ PoseAwarePPEDetector initialized with SH17 backend")
                except Exception as pose_err:
                    logger.warning(f"⚠️ PoseAware init failed: {pose_err}")
            else:
                try:
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=None)
                except Exception: pass
                model_manager = None
                use_sh17 = False
            
        except Exception as e:
            logger.error(f"❌ Model yükleme hatası: {e}")
            return
        
        frame_count = 0
        detection_count = 0
        frame_skip = 6
        optimized_confidence = max(0.5, confidence)
        
        while ad.get(camera_key, False):
            try:
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    frame = frame_buffers[camera_key].copy()
                    frame_count += 1
                    
                    if frame_count % frame_skip == 0:
                        start_time = time.time()
                        people_detected = 0
                        ppe_violations = []
                        ppe_compliant = 0
                        results = []
                        
                        try:
                            if pose_detector is not None:
                                pose_result = pose_detector.detect_with_pose(frame, sector, optimized_confidence, required_ppe=required_ppe)
                                if isinstance(pose_result, dict):
                                    people_detected = pose_result.get('people_detected', 0)
                                    ppe_compliant = pose_result.get('compliant_people', 0)
                                    ppe_violations = pose_result.get('ppe_violations', [])
                                    results = pose_result.get('detections', [])
                                elif isinstance(pose_result, list):
                                    results = pose_result
                                    people_detected = sum(1 for d in results if d.get('class_name') == 'person')
                            elif use_sh17 and model_manager:
                                results = model_manager.detect_ppe(frame, sector, optimized_confidence)
                                people_detected = sum(1 for d in results if d.get('class_name') == 'person')
                                if people_detected > 0 and required_ppe:
                                    compliance_result = model_manager.analyze_compliance(results, required_ppe)
                                    ppe_compliant = compliance_result.get('total_detected', 0)
                                    missing = compliance_result.get('missing', [])
                                    ppe_violations = [f"Missing: {item}" for item in missing]
                                else:
                                    ppe_compliant = people_detected
                        except Exception as detection_error:
                            logger.error(f"❌ Detection hatası: {detection_error}")
                        
                        normalized_ppe_violations, simple_ppe_violations = self._normalize_ppe_violations(ppe_violations)
                        ppe_violations = simple_ppe_violations

                        if people_detected > 0 and len(ppe_violations) == 0 and ppe_compliant == 0:
                            ppe_compliant = people_detected

                        try:
                            proc_time = time.time() - start_time
                            if people_detected > 0 or len(ppe_violations) > 0:
                                self._save_detection_to_reports(company_id, camera_id, sector, people_detected, ppe_compliant, len(ppe_violations), proc_time, optimized_confidence)
                                self._generate_live_alerts(company_id, camera_id, people_detected, ppe_compliant, len(ppe_violations), sector)
                            for violation in normalized_ppe_violations:
                                self._save_violation_to_reports(company_id, camera_id, violation)
                        except Exception as result_error:
                            logger.error(f"❌ Result processing hatası: {result_error}")
                        
                        compliance_rate = (ppe_compliant / people_detected * 100) if people_detected > 0 else 0
                        processing_time = (time.time() - start_time) * 1000
                        detection_count += 1
                        
                        detection_data = {
                            'camera_id': camera_id, 'company_id': company_id,
                            'timestamp': datetime.now().isoformat(),
                            'total_people': int(people_detected),
                            'ppe_compliant': int(ppe_compliant),
                            'violations': ppe_violations,
                            'compliance_rate': float(round(compliance_rate, 1)),
                            'processing_time': float(round(processing_time / 1000, 3)),
                            'detections': results if isinstance(results, list) else [],
                        }
                        
                        try:
                            if not detection_results[camera_key].full():
                                detection_results[camera_key].put_nowait(detection_data)
                        except Exception: pass
                        
                        if detection_count % 10 == 0:
                            self.save_detection_to_db(detection_data)
                    
                    time.sleep(0.01)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ SaaS Detection hatası: {e}")
                time.sleep(1)
        
        logger.info(f"🛑 SaaS Detection durduruldu - Kamera: {camera_id}")

    def start_saas_camera(self, camera_key, camera_id, company_id, active_detectors_ref=None):
        """SaaS Kamera başlatma"""
        try:
            camera_info = self.db.get_camera_by_id(camera_id, company_id)
            if not camera_info: return
            
            ip = camera_info.get('ip_address')
            port = camera_info.get('port')
            if ip and port:
                protocol = camera_info.get('protocol', 'http')
                stream_path = (camera_info.get('stream_path') or '/video').strip()
                username = camera_info.get('username', '')
                password = camera_info.get('password', '')
                
                if username and password:
                    camera_url = f"{protocol}://{username}:{password}@{ip}:{port}{stream_path}"
                else:
                    camera_url = f"{protocol}://{ip}:{port}{stream_path}"
                
                # Kamera thread'ini başlat
                camera_thread = threading.Thread(
                    target=self.saas_camera_worker,
                    args=(camera_key, camera_url, active_detectors_ref),
                    daemon=True
                )
                camera_thread.start()
            else:
                logger.warning(f"⚠️ Kamera IP/Port eksik: {camera_id}")
        except Exception as e:
            logger.error(f"❌ SaaS Kamera başlatma hatası: {e}")

    def saas_camera_worker(self, camera_key, camera_url, active_detectors_ref=None):
        """SaaS Kamera Worker - OpenCV ile frame okur"""
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        cap = cv2.VideoCapture(camera_url)
        try:
            while ad.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    frame_buffers[camera_key] = frame
                else:
                    time.sleep(0.1)
                    cap.release()
                    cap = cv2.VideoCapture(camera_url)
        finally:
            cap.release()
            if camera_key in frame_buffers: del frame_buffers[camera_key]

    def generate_saas_frames(self, camera_key, company_id, camera_id, active_detectors_ref=None):
        """SaaS Frame Generator - Stream için MJPEG üretir"""
        ad = active_detectors_ref if active_detectors_ref is not None else active_detectors
        while ad.get(camera_key, False):
            try:
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    frame = frame_buffers[camera_key].copy()
                    
                    # En son detection sonucunu al ve çiz
                    if camera_key in detection_results and not detection_results[camera_key].empty():
                        res = detection_results[camera_key].get_nowait()
                        frame = self.draw_saas_overlay(frame, res)
                        detection_results[camera_key].put_nowait(res) # Geri koy
                    
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                else:
                    time.sleep(0.1)
            except Exception:
                time.sleep(0.1)

    def draw_saas_overlay(self, frame, detection_data):
        """Görüntü üzerine tespit kutularını ve istatistikleri çizer"""
        try:
            h, w = frame.shape[:2]
            detections = detection_data.get('detections', [])
            
            for det in detections:
                bbox = det.get('bbox', [])
                if len(bbox) == 4:
                    x1, y1, x2, y2 = map(int, bbox)
                    label = det.get('class_name', 'unknown')
                    conf = det.get('confidence', 0)
                    color = (0, 255, 0) if det.get('compliant', True) else (0, 0, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Üst bilgi paneli
            cv2.rectangle(frame, (0, 0), (w, 40), (0, 0, 0), -1)
            info_text = f"People: {detection_data.get('total_people', 0)} | Compliant: {detection_data.get('ppe_compliant', 0)} | Rate: %{detection_data.get('compliance_rate', 0)}"
            cv2.putText(frame, info_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            return frame
        except Exception: return frame

    def _normalize_ppe_violations(self, ppe_violations):
        """İhlalleri standart formata çevirir"""
        normalized, simple = [], []
        if not ppe_violations: return [], []
        for v in ppe_violations:
            if isinstance(v, dict):
                simple.append(str(v.get('missing_ppe', ['Unknown'])[0]))
                normalized.append(v)
            else:
                simple.append(str(v))
                normalized.append({'missing_ppe': [str(v)], 'confidence': 0})
        return normalized, simple

    def _save_detection_to_reports(self, company_id, camera_id, mode, people, compliant, violations, proc_time, conf):
        """Database'e istatistik kaydı atar"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO detections (company_id, camera_id, detection_type, people_detected, ppe_compliant, violations_count, confidence, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (company_id, camera_id, mode, people, compliant, violations, conf, datetime.now()))
            conn.commit()
            conn.close()
        except Exception: pass

    def _save_violation_to_reports(self, company_id, camera_id, violation):
        """Database'e ihlal kaydı atar"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            missing = violation.get('missing_ppe', ['Unknown'])[0]
            cursor.execute("INSERT INTO violations (company_id, camera_id, missing_ppe, confidence, timestamp) VALUES (?, ?, ?, ?, ?)",
                         (company_id, camera_id, missing, violation.get('confidence', 0), datetime.now()))
            conn.commit()
            conn.close()
        except Exception: pass

    def _generate_live_alerts(self, company_id, camera_id, people, compliant, violations, mode):
        """Anlık alarmlar üretir"""
        if violations > 0:
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO alerts (company_id, camera_id, alert_type, severity, title, message, status, created_at) VALUES (?, ?, 'ppe_violation', 'warning', 'PPE Ihlali', ?, 'active', ?)",
                             (company_id, camera_id, f"{violations} adet PPE ihlali tespit edildi.", datetime.now()))
                conn.commit()
                conn.close()
            except Exception: pass

    def save_detection_to_db(self, data):
        """Genel istatistikleri periyodik kaydeder"""
        pass # Opsiyonel


# =============================================================================
# PRODUCTION APP INSTANCE - Bu obje Gunicorn tarafından kullanılır
# =============================================================================
def create_app():
    """Factory function to create Flask app"""
    try:
        api_server = SmartSafeSaaSAPI()
        app = api_server.app
        print(f"✅ Flask app created successfully: {app.name}")
        return app
    except Exception as e:
        print(f"❌ Critical error creating Flask app: {e}")
        import traceback
        traceback.print_exc()
        raise

# Create the app instance (used by Gunicorn)
app = create_app()

# =============================================================================
# LOCAL DEVELOPMENT ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    env = os.getenv("ENV", "local").lower()
    port = int(os.getenv("PORT", 5000))
    host = "0.0.0.0"

    print(f"🚀 Starting SmartSafe SaaS API")
    print(f"🌐 Host: {host}, Port: {port}")
    print(f"🔧 Environment: {env}")

    app.run(
        host=host,
        port=port,
        debug=(env == "local"),
        threaded=True
    )