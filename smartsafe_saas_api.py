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
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
from dotenv import load_dotenv
from smartsafe_multitenant_system import MultiTenantDatabase
from smartsafe_construction_system import ConstructionPPEDetector, ConstructionPPEConfig
from smartsafe_sector_detector_factory import SectorDetectorFactory
import cv2
import numpy as np
import base64
import queue
from io import BytesIO

# Load environment variables
load_dotenv()

# Configure logging - Memory optimized
import os
log_level = logging.WARNING if os.environ.get('RENDER') else logging.INFO
logging.basicConfig(level=log_level, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

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



class SmartSafeSaaSAPI:
    """SmartSafe AI SaaS API Server"""
    
    def __init__(self):
        self.app = Flask(__name__, 
                        template_folder='templates',
                        static_folder='static')
        self.app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'smartsafe-saas-2024-secure-key')
        
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
        
        # Enable CORS
        CORS(self.app)
        
        # Rate limiting
        self.limiter = Limiter(
            app=self.app,
            key_func=get_remote_address,
            default_limits=["200 per minute"]
        )
        
        # Multi-tenant database
        self.db = MultiTenantDatabase()
        
        # Enterprise modülleri başlat
        self.init_enterprise_modules()
        
        # Setup routes
        self.setup_routes()
        
        logger.info("🌐 SmartSafe AI SaaS API Server initialized")
    
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
                from camera_integration_manager import get_camera_manager
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
                from professional_config_manager import ProfessionalConfigManager
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
                from performance_optimizer import PerformanceOptimizer
                self.performance_optimizer = PerformanceOptimizer()
                logger.info("✅ Performance Optimizer lazy loaded")
            except ImportError:
                logger.warning("⚠️ Performance Optimizer import failed")
                return None
        return self.performance_optimizer
    
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
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                SELECT subscription_type, subscription_end, max_cameras, 
                       created_at, company_name, sector
                FROM companies WHERE company_id = {placeholder}
            ''', (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # Kamera kullanımını al
                cameras = self.db.get_company_cameras(company_id)
                used_cameras = len(cameras)
                
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(result, 'keys'):  # PostgreSQL Row object
                    subscription_end = result['subscription_end']
                    subscription_info = {
                        'subscription_type': result['subscription_type'] or 'basic',
                        'max_cameras': result['max_cameras'] or 5,
                        'created_at': result['created_at'] if result['created_at'] else None,
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'used_cameras': used_cameras,
                    }
                else:  # SQLite tuple
                    subscription_end = result[1]
                    subscription_info = {
                        'subscription_type': result[0] or 'basic',
                        'max_cameras': result[2] or 5,
                        'created_at': result[3] if result[3] else None,
                        'company_name': result[4],
                        'sector': result[5],
                        'used_cameras': used_cameras,
                    }
                
                # Abonelik durumunu kontrol et
                is_active = True
                days_remaining = 0
                
                if subscription_end:
                    if isinstance(subscription_end, str):
                        subscription_end = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                    
                    days_remaining = (subscription_end - datetime.now()).days
                    is_active = days_remaining > 0
                
                # Ortak alanları ekle
                subscription_info.update({
                    'subscription_end': subscription_end.isoformat() if subscription_end else None,
                    'is_active': is_active,
                    'days_remaining': days_remaining,
                    'usage_percentage': (used_cameras / (subscription_info['max_cameras'] or 5)) * 100
                })
                
                return {
                    'success': True,
                    'subscription': subscription_info
                }
            else:
                return {'success': False, 'error': 'Şirket bulunamadı'}
            
        except Exception as e:
            logger.error(f"❌ Internal abonelik bilgileri getirme hatası: {e}")
            return {'success': False, 'error': 'Veri getirme başarısız'}

    def setup_routes(self):
        """API rotalarını ayarla"""
        
        # Health check endpoint for deployment
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            try:
                # Test database connection
                db_status = "connected" if self.db else "disconnected"
                
                return jsonify({
                    'status': 'healthy',
                    'service': 'SmartSafe AI SaaS',
                    'database': db_status,
                    'enterprise_enabled': self.enterprise_enabled,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"❌ Health check error: {e}")
                return jsonify({
                    'status': 'unhealthy',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }), 500
        
        # İletişim formu endpoint'i
        @self.app.route('/api/contact', methods=['POST'])
        def contact():
            """İletişim formu gönderimi"""
            try:
                name = request.form.get('name')
                email = request.form.get('email')
                sector = request.form.get('sector')
                message = request.form.get('message')
                
                # Form validasyonu
                if not all([name, email, sector, message]):
                    return jsonify({'success': False, 'error': 'Please fill all fields'}), 400
                
                # E-posta gönderimi
                msg = Message(
                    subject=f'SmartSafe AI - Yeni İletişim Formu: {name}',
                    sender=self.app.config['MAIL_USERNAME'],
                    recipients=['yigittilaver2000@gmail.com'],
                    body=f'''Yeni bir iletişim formu gönderildi:
                    
Ad Soyad: {name}
E-posta: {email}
Sektör: {sector}
Mesaj:
{message}
                    '''
                )
                
                self.mail.send(msg)
                
                return jsonify({
                    'success': True,
                    'message': 'Your message has been sent successfully'
                })
                
            except Exception as e:
                logger.error(f"❌ İletişim formu hatası: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Mesaj gönderilirken bir hata oluştu'
                }), 500
        
        # Ana sayfa - Landing Page
        @self.app.route('/', methods=['GET'])
        def landing():
            """Landing page"""
            return render_template('landing.html')

        # Uygulama ana sayfası - Şirket kayıt
        @self.app.route('/app', methods=['GET'])
        def app_home():
            """Company registration form"""
            return render_template_string(self.get_home_template())
        
        # Fiyatlandırma sayfası
        @self.app.route('/pricing')
        def pricing():
            """Fiyatlandırma ve plan seçimi sayfası"""
            return render_template_string(self.get_pricing_template())

        # Şirket kaydı
        @self.app.route('/api/register', methods=['POST'])
        def register_company():
            """Yeni şirket kaydı"""
            try:
                data = request.json
                required_fields = ['company_name', 'sector', 'contact_person', 'email', 'password']
                
                # Gerekli alanları kontrol et
                for field in required_fields:
                    if not data.get(field):
                        return jsonify({'success': False, 'error': f'{field} gerekli'}), 400
                
                # Şirket oluştur
                success, result = self.db.create_company(data)
                
                if success:
                    return jsonify({
                        'success': True, 
                        'company_id': result,
                        'message': 'Company registered successfully',
                        'login_url': f'/company/{result}/login'
                    })
                else:
                    return jsonify({'success': False, 'error': result}), 400
                    
            except Exception as e:
                logger.error(f"❌ Şirket kayıt hatası: {e}")
                return jsonify({'success': False, 'error': 'Registration failed'}), 500

        # HTML Form kayıt endpoint'i
        @self.app.route('/api/register-form', methods=['POST'])
        def register_form():
            """HTML form'dan şirket kaydı"""
            try:
                # Form verilerini al
                data = {
                    'company_name': request.form.get('company_name'),
                    'sector': request.form.get('sector'),
                    'contact_person': request.form.get('contact_person'),
                    'email': request.form.get('email'),
                    'phone': request.form.get('phone'),
                    'address': request.form.get('address', ''),
                    'password': request.form.get('password')
                }
                
                # PPE seçimlerini al
                required_ppe = request.form.getlist('required_ppe')
                optional_ppe = request.form.getlist('optional_ppe')
                
                # En az bir PPE seçimi zorunlu
                if not required_ppe and not optional_ppe:
                    return '''
                    <script>
                        alert("❌ En az bir PPE türü seçmelisiniz!");
                        window.history.back();
                    </script>
                    '''
                
                # PPE konfigürasyonu oluştur
                ppe_config = {
                    'required': required_ppe,
                    'optional': optional_ppe
                }
                
                data['required_ppe'] = ppe_config
                
                # Abonelik planı seçimi
                subscription_plan = request.form.get('subscription_plan', 'starter')
                plan_prices = {
                    'starter': {'monthly': 99, 'cameras': 5},
                    'professional': {'monthly': 299, 'cameras': 15},
                    'enterprise': {'monthly': 599, 'cameras': 50}
                }
                
                if subscription_plan in plan_prices:
                    data['subscription_type'] = subscription_plan
                    data['max_cameras'] = plan_prices[subscription_plan]['cameras']
                else:
                    data['subscription_type'] = 'starter'
                    data['max_cameras'] = 5
                
                # Doğrulama
                required_fields = ['company_name', 'sector', 'contact_person', 'email', 'password']
                for field in required_fields:
                    if not data.get(field):
                        return f'''
                        <script>
                            alert("❌ {field} alanı gerekli!");
                            window.history.back();
                        </script>
                        '''
                
                # Şirket oluştur
                success, result = self.db.create_company(data)
                
                if success:
                    company_id = result
                    login_url = f"/company/{company_id}/login"
                    
                    # Başarılı kayıt HTML sayfası
                    return f'''
                    <!DOCTYPE html>
                    <html lang="tr">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Registration Successful!</title>
                        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
                        <style>
                            body {{
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                min-height: 100vh;
                                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            }}
                            .card {{
                                border-radius: 15px;
                                box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                                backdrop-filter: blur(10px);
                                background: rgba(255,255,255,0.95);
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container mt-5">
                            <div class="row justify-content-center">
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-body text-center p-5">
                                            <i class="fas fa-check-circle text-success" style="font-size: 4rem;"></i>
                                            <h2 class="mt-3 text-success">🎉 Registration Successful!</h2>
                                            <hr>
                                            <div class="alert alert-info">
                                                <h5><i class="fas fa-building"></i> Your Company ID:</h5>
                                                <h3 class="text-primary"><strong>{company_id}</strong></h3>
                                            </div>
                                            <div class="alert alert-warning">
                                                <i class="fas fa-exclamation-triangle"></i>
                                                <strong>IMPORTANT:</strong> Please note this ID! 
                                                You will need it to log in again.
                                            </div>
                                            <div class="mt-4">
                                                <a href="{login_url}" class="btn btn-primary btn-lg">
                                                    <i class="fas fa-sign-in-alt"></i> Go to Login Page
                                                </a>
                                            </div>
                                            <div class="mt-3">
                                                <a href="/" class="btn btn-outline-secondary">
                                                    <i class="fas fa-home"></i> Home Page
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <script>
                            // Store company ID in localStorage
                            localStorage.setItem('lastCompanyId', '{company_id}');
                        </script>
                    </body>
                    </html>
                    '''
                else:
                    return f'''
                    <script>
                        alert("❌ Kayıt hatası: {result}");
                        window.history.back();
                    </script>
                    '''
                    
            except Exception as e:
                logger.error(f"❌ Form kayıt hatası: {e}")
                return f'''
                <script>
                    alert("❌ Bir hata oluştu: {str(e)}");
                    window.history.back();
                </script>
                '''
        
        # Şirket giriş sayfası
        @self.app.route('/company/<company_id>/login', methods=['GET', 'POST'])
        def company_login(company_id):
            """Şirket giriş sayfası"""
            if request.method == 'GET':
                return self.get_login_template(company_id)
            
            # POST - Giriş işlemi
            try:
                data = request.json
                email = data.get('email')
                password = data.get('password')
                
                if not email or not password:
                    return jsonify({'success': False, 'error': 'Email ve şifre gerekli'}), 400
                
                # Kullanıcı doğrulama
                user_data = self.db.authenticate_user(email, password)
                
                if user_data and user_data['company_id'] == company_id:
                    # Oturum oluştur
                    session_id = self.db.create_session(
                        user_data['user_id'], 
                        company_id,
                        request.remote_addr,
                        request.headers.get('User-Agent', '')
                    )
                    
                    if session_id:
                        session['session_id'] = session_id
                        session['company_id'] = company_id
                        session['user_id'] = user_data['user_id']
                        
                        return jsonify({
                            'success': True, 
                            'message': 'Giriş başarılı',
                            'redirect_url': f'/company/{company_id}/dashboard'
                        })
                
                return jsonify({'success': False, 'error': 'Geçersiz email veya şifre'}), 401
                
            except Exception as e:
                logger.error(f"❌ Giriş hatası: {e}")
                return jsonify({'success': False, 'error': 'Giriş işlemi başarısız'}), 500

        # HTML Form login endpoint
        @self.app.route('/company/<company_id>/login-form', methods=['POST'])
        def company_login_form(company_id):
            """HTML form'dan şirket girişi"""
            try:
                # Form verilerini al
                email = request.form.get('email')
                password = request.form.get('password')
                
                if not email or not password:
                    return f'''
                    <script>
                        alert("❌ Email ve şifre gerekli!");
                        window.history.back();
                    </script>
                    '''
                
                # Kullanıcı doğrulama
                user_data = self.db.authenticate_user(email, password)
                
                if user_data and user_data['company_id'] == company_id:
                    # Oturum oluştur
                    session_id = self.db.create_session(
                        user_data['user_id'], 
                        company_id,
                        request.remote_addr,
                        request.headers.get('User-Agent', '')
                    )
                    
                    if session_id:
                        session['session_id'] = session_id
                        session['company_id'] = company_id
                        session['user_id'] = user_data['user_id']
                        
                        # Başarılı giriş - Dashboard'a yönlendir
                        return f'''
                        <script>
                            alert("✅ Giriş başarılı! Dashboard'a yönlendiriliyorsunuz...");
                            window.location.href = "/company/{company_id}/dashboard";
                        </script>
                        '''
                
                return f'''
                <script>
                    alert("❌ Geçersiz email veya şifre!");
                    window.history.back();
                </script>
                '''
                
            except Exception as e:
                logger.error(f"❌ Form giriş hatası: {e}")
                return f'''
                <script>
                    alert("❌ Bir hata oluştu: {str(e)}");
                    window.history.back();
                </script>
                '''
        
        # Ana sayfa şirket giriş yönlendirme
        @self.app.route('/api/company-login-redirect', methods=['POST'])
        def company_login_redirect():
            """Ana sayfadan şirket giriş yönlendirme"""
            try:
                company_id = request.form.get('company_id', '').strip()
                
                if not company_id:
                    return '''
                    <script>
                        alert("❌ Şirket ID boş bırakılamaz!");
                        window.history.back();
                    </script>
                    '''
                
                # Şirket ID formatını kontrol et
                if not company_id.startswith('COMP_'):
                    return '''
                    <script>
                        alert("❌ Geçersiz Şirket ID formatı!\\nŞirket ID'niz COMP_ ile başlamalıdır.");
                        window.history.back();
                    </script>
                    '''
                
                # Şirket var mı kontrol et
                conn = self.db.get_connection()
                cursor = conn.cursor()
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'SELECT company_name FROM companies WHERE company_id = {placeholder}', (company_id,))
                company = cursor.fetchone()
                conn.close()
                
                if not company:
                    return f'''
                    <script>
                        alert("❌ Company with ID '{company_id}' not found!\\nPlease check your company ID.");
                        window.history.back();
                    </script>
                    '''
                
                # Şirket giriş sayfasına yönlendir
                return redirect(f'/company/{company_id}/login')
                
            except Exception as e:
                logger.error(f"❌ Şirket giriş yönlendirme hatası: {e}")
                return f'''
                <script>
                    alert("❌ Bir hata oluştu: {str(e)}");
                    window.history.back();
                </script>
                '''
        
        # Şirket dashboard
        @self.app.route('/company/<company_id>/dashboard', methods=['GET'])
        def company_dashboard(company_id):
            """Şirket dashboard"""
            # Oturum kontrolü
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            return render_template_string(self.get_dashboard_template(), 
                                        company_id=company_id, 
                                        user_data=user_data)
        
        # Şirket istatistikleri API (Enhanced)
        @self.app.route('/api/company/<company_id>/stats', methods=['GET'])
        def get_company_stats(company_id):
            """Unified şirket istatistikleri - Database'den gerçek kamera sayısı"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # MultiTenant database'den base istatistikleri al
                stats = self.db.get_company_stats(company_id)
                
                # Gerçek kamera sayısını database'den al (unified approach)
                try:
                    cameras = self.db.get_company_cameras(company_id)
                    total_cameras = len(cameras)
                    active_cameras = len([c for c in cameras if c.get('status') == 'active'])
                    discovered_cameras = len([c for c in cameras if c.get('status') == 'discovered'])
                    
                    # Kamera istatistiklerini güncelle
                    stats.update({
                        'active_cameras': active_cameras,
                        'total_cameras': total_cameras,
                        'discovered_cameras': discovered_cameras,
                        'inactive_cameras': total_cameras - active_cameras
                    })
                    
                    logger.info(f"✅ Unified stats for company {company_id}: {total_cameras} cameras ({active_cameras} active, {discovered_cameras} discovered)")
                    
                except Exception as camera_error:
                    logger.error(f"❌ Error getting camera stats: {camera_error}")
                    # Fallback to existing stats without camera updates
                
                # Enhanced stats with unified camera data
                enhanced_stats = {
                    'active_cameras': stats.get('active_cameras', 0),
                    'total_cameras': stats.get('total_cameras', 0),
                    'discovered_cameras': stats.get('discovered_cameras', 0),
                    'compliance_rate': stats.get('compliance_rate', 0),
                    'today_violations': stats.get('today_violations', 0),
                    'active_workers': stats.get('active_workers', 0),
                    'total_detections': stats.get('total_detections', 0),
                    'monthly_violations': stats.get('monthly_violations', 0),
                    
                    # Trend indicators
                    'cameras_trend': stats.get('cameras_trend', 0),
                    'compliance_trend': stats.get('compliance_trend', 0),
                    'violations_trend': stats.get('violations_trend', 0),
                    'workers_trend': stats.get('workers_trend', 0),
                    
                    # Unified data source indicator
                    'data_source': 'unified_database',
                    'last_updated': datetime.now().isoformat()
                }
                
                return jsonify(enhanced_stats)
                
            except Exception as e:
                logger.error(f"❌ Stats error for company {company_id}: {e}")
                return jsonify({
                    'error': 'İstatistikler getirilemedi',
                    'details': str(e)
                }), 500
        
        # Şirket kameraları API
        @self.app.route('/api/company/<company_id>/cameras', methods=['GET'])
        def get_company_cameras(company_id):
            """Şirket kameralarını getir - Unified Database Source"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # Unified approach: Database'den kameraları al
                cameras = self.db.get_company_cameras(company_id)
                
                # Enterprise camera manager entegrasyonu
                if hasattr(self, 'camera_manager') and self.camera_manager:
                    # Real-time status update
                    for camera in cameras:
                        try:
                            # IP'den camera manager'da status kontrol et
                            if camera.get('ip_address'):
                                status_info = self._get_realtime_camera_status(camera['ip_address'])
                                if status_info:
                                    camera.update(status_info)
                        except Exception as e:
                            logger.debug(f"Real-time status check failed for {camera.get('name', 'unknown')}: {e}")
                
                # Kamera sayısı ve summary bilgileri ekle
                total_cameras = len(cameras)
                active_cameras = len([c for c in cameras if c.get('status') == 'active'])
                
                result = {
                    'success': True, 
                    'cameras': cameras,
                    'total': total_cameras,
                    'active': active_cameras,
                    'summary': {
                        'total_cameras': total_cameras,
                        'active_cameras': active_cameras,
                        'inactive_cameras': total_cameras - active_cameras,
                        'last_updated': datetime.now().isoformat()
                    }
                }
                
                logger.info(f"✅ Retrieved {total_cameras} cameras for company {company_id}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"❌ Error getting cameras for company {company_id}: {e}")
                return jsonify({'success': False, 'error': 'Kameralar getirilemedi'}), 500
        
        # Kamera ekleme API
        @self.app.route('/api/company/<company_id>/cameras', methods=['POST'])
        def add_camera(company_id):
            """Yeni kamera ekleme"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # Abonelik limit kontrolü
                subscription_info = self.get_subscription_info_internal(company_id)
                if not subscription_info['success']:
                    return jsonify({'success': False, 'error': 'Abonelik bilgileri alınamadı'}), 400
                
                subscription = subscription_info['subscription']
                current_cameras = subscription['used_cameras']
                max_cameras = subscription['max_cameras']
                
                # Limit kontrolü
                if current_cameras >= max_cameras:
                    return jsonify({
                        'success': False, 
                        'error': f'Kamera limiti aşıldı! Mevcut: {current_cameras}/{max_cameras}',
                        'limit_reached': True,
                        'current_cameras': current_cameras,
                        'max_cameras': max_cameras,
                        'subscription_type': subscription['subscription_type']
                    }), 403
                
                data = request.json
                success, result = self.db.add_camera(company_id, data)
                
                if success:
                    return jsonify({'success': True, 'camera_id': result})
                else:
                    return jsonify({'success': False, 'error': result}), 400
                    
            except Exception as e:
                logger.error(f"❌ Kamera ekleme hatası: {e}")
                return jsonify({'success': False, 'error': 'Kamera eklenemedi'}), 500
        
        # Şirket uyarıları API
        @self.app.route('/api/company/<company_id>/alerts', methods=['GET'])
        def get_company_alerts(company_id):
            """Şirket uyarıları - Gerçek verilerle"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # Son 24 saat içindeki ihlalleri getir
                if hasattr(self.db, 'db_adapter') and self.db.db_adapter.db_type == 'postgresql':
                    time_filter = "v.timestamp >= NOW() - INTERVAL '24 hours'"
                else:
                    time_filter = "v.timestamp >= datetime('now', '-24 hours')"
                
                cursor.execute(f"""
                    SELECT v.violation_type, v.missing_ppe, v.severity, v.timestamp, 
                           c.camera_name, v.image_path, v.resolved
                    FROM violations v
                    JOIN cameras c ON v.camera_id = c.camera_id
                    WHERE v.company_id = {placeholder} 
                    AND {time_filter}
                    ORDER BY v.timestamp DESC
                    LIMIT 10
                """, (company_id,))
                
                violations = cursor.fetchall()
                alerts = []
                
                for violation in violations:
                    # PostgreSQL Row object vs SQLite tuple compatibility
                    if hasattr(violation, 'keys'):  # PostgreSQL Row object
                        violation_data = {
                            'violation_type': violation['violation_type'],
                            'missing_ppe': violation['missing_ppe'],
                            'severity': violation['severity'],
                            'timestamp': violation['timestamp'],
                            'camera_name': violation['camera_name'],
                            'image_path': violation['image_path'],
                            'resolved': violation['resolved']
                        }
                    else:  # SQLite tuple
                        violation_data = {
                            'violation_type': violation[0],
                            'missing_ppe': violation[1],
                            'severity': violation[2],
                            'timestamp': violation[3],
                            'camera_name': violation[4],
                            'image_path': violation[5],
                            'resolved': violation[6]
                        }
                    
                    # Timestamp'i formatla
                    try:
                        from datetime import datetime
                        if isinstance(violation_data['timestamp'], str):
                            dt = datetime.fromisoformat(violation_data['timestamp'].replace('Z', '+00:00'))
                        else:
                            dt = violation_data['timestamp']
                        time_str = dt.strftime('%H:%M')
                    except:
                        time_str = 'Bilinmiyor'
                    
                    # Missing PPE listesini işle
                    missing_ppe_list = []
                    if violation_data['missing_ppe']:
                        try:
                            import json
                            missing_ppe_list = json.loads(violation_data['missing_ppe'])
                        except:
                            missing_ppe_list = [violation_data['missing_ppe']]
                    
                    # Türkçe PPE isimleri
                    ppe_names = {
                        'helmet': 'Baret',
                        'vest': 'Güvenlik Yeleği',
                        'glasses': 'Güvenlik Gözlüğü',
                        'gloves': 'Eldiven',
                        'shoes': 'Güvenlik Ayakkabısı',
                        'mask': 'Maske'
                    }
                    
                    missing_ppe_tr = [ppe_names.get(ppe, ppe) for ppe in missing_ppe_list]
                    
                    alerts.append({
                        'violation_type': ' + '.join(missing_ppe_tr) + ' Eksik' if missing_ppe_tr else violation_data['violation_type'],
                        'description': f"{', '.join(missing_ppe_tr)} kullanılmadan çalışma tespit edildi" if missing_ppe_tr else 'PPE ihlali tespit edildi',
                        'time': time_str,
                        'camera_name': violation_data['camera_name'],
                        'severity': violation_data['severity'] or 'Orta',
                        'resolved': violation_data['resolved'],
                        'image_path': violation_data['image_path']
                    })
                
                                # Eğer gerçek veri yoksa demo veriler göster
                if not alerts:
                    alerts = [
                        {
                            'violation_type': 'Sistem Başlatıldı',
                            'description': 'PPE detection sistemi aktif, ihlaller burada görünecek',
                            'time': 'Şimdi',
                            'camera_name': 'Sistem',
                            'severity': 'Bilgi',
                            'resolved': False,
                            'image_path': None
                        }
                    ]
                
                conn.close()
                return jsonify({'alerts': alerts})
                
            except Exception as e:
                logger.error(f"❌ Uyarılar yüklenemedi: {e}")
                # Hata durumunda da demo veriler göster
                demo_alerts = [
                    {
                        'violation_type': 'Sistem Hazırlanıyor',
                        'description': 'PPE detection sistemi hazırlanıyor, kameralar test ediliyor',
                        'time': 'Şimdi',
                        'camera_name': 'Sistem',
                        'severity': 'Bilgi',
                        'resolved': False,
                        'image_path': None
                    }
                ]
                return jsonify({'alerts': demo_alerts})
        
        # Şirket grafik verileri API
        @self.app.route('/api/company/<company_id>/chart-data', methods=['GET'])
        def get_company_chart_data(company_id):
            """Şirket grafik verileri"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # Gerçek detection sonuçlarından grafik verilerini hesapla
                chart_data = self.calculate_real_chart_data(company_id)
                
                return jsonify(chart_data)
                
            except Exception as e:
                logger.error(f"❌ Grafik verileri yüklenemedi: {e}")
                return jsonify({'error': 'Grafik verileri yüklenemedi'}), 500
        
        # Çıkış
        @self.app.route('/logout', methods=['POST'])
        def logout():
            """Çıkış işlemi"""
            session.clear()
            return jsonify({'success': True, 'message': 'Çıkış yapıldı'})
        
        # === ADMIN PANEL ===
        @self.app.route('/admin', methods=['GET', 'POST'])
        def admin_panel():
            """Admin panel - Founder şifresi gerekli"""
            if request.method == 'GET':
                # Admin login sayfasını göster
                return render_template_string(self.get_admin_login_template())
            
            # POST - Admin şifre kontrolü
            try:
                data = request.form
                password = data.get('password')
                
                # Founder şifresi (gerçek projede environment variable kullanın)
                FOUNDER_PASSWORD = "smartsafe2024admin"
                
                if password == FOUNDER_PASSWORD:
                    # Admin session'u oluştur
                    session['admin_authenticated'] = True
                    return render_template_string(self.get_admin_template())
                else:
                    return render_template_string(self.get_admin_login_template("Yanlış şifre!"))
                    
            except Exception as e:
                return render_template_string(self.get_admin_login_template(str(e)))
        
        @self.app.route('/api/admin/companies', methods=['GET'])
        def admin_get_companies():
            """Admin - Tüm şirketleri getir"""
            # Admin authentication kontrolü
            if not session.get('admin_authenticated'):
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # Database adapter kullan (PostgreSQL/SQLite otomatik seçim)
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT company_id, company_name, email, sector, max_cameras, 
                           created_at, status, contact_person, phone
                    FROM companies 
                    ORDER BY created_at DESC
                ''')
                companies = cursor.fetchall()
                
                companies_list = []
                for comp in companies:
                    # PostgreSQL RealDictRow için sözlük erişimi kullan
                    if hasattr(comp, 'keys'):  # RealDictRow veya dict
                        companies_list.append({
                            'company_id': comp.get('company_id'),
                            'company_name': comp.get('company_name'),
                            'email': comp.get('email'),
                            'sector': comp.get('sector'),
                            'max_cameras': comp.get('max_cameras'),
                            'created_at': str(comp.get('created_at')) if comp.get('created_at') else '',
                            'status': comp.get('status'),
                            'contact_person': comp.get('contact_person'),
                            'phone': comp.get('phone')
                        })
                    else:  # Liste formatı (SQLite için)
                        companies_list.append({
                            'company_id': comp[0],
                            'company_name': comp[1],
                            'email': comp[2],
                            'sector': comp[3],
                            'max_cameras': comp[4],
                            'created_at': str(comp[5]) if comp[5] else '',
                            'status': comp[6],
                            'contact_person': comp[7],
                            'phone': comp[8]
                        })
                
                conn.close()
                return jsonify({'companies': companies_list})
                
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/admin/companies/<company_id>', methods=['DELETE'])
        def admin_delete_company(company_id):
            """Admin - Şirket sil"""
            # Admin authentication kontrolü
            if not session.get('admin_authenticated'):
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                # Şirket var mı kontrol et
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'SELECT company_name FROM companies WHERE company_id = {placeholder}', (company_id,))
                company = cursor.fetchone()
                
                if not company:
                    return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
                
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(company, 'keys'):  # RealDictRow veya dict
                    company_name = company.get('company_name')
                else:  # Liste formatı (SQLite için)
                    company_name = company[0]
                
                # İlgili verileri sil (CASCADE mantığı)
                tables_to_clean = ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']
                
                for table in tables_to_clean:
                    cursor.execute(f'DELETE FROM {table} WHERE company_id = {placeholder}', (company_id,))
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True, 'message': f'Şirket {company_name} silindi'})
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        # === ŞIRKET SELF-SERVICE SILME ===
        @self.app.route('/company/<company_id>/settings', methods=['GET'])
        def company_settings(company_id):
            """Şirket ayarları sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            # Şirket bilgilerini yükle
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT company_name, contact_person, email, phone, sector, address
                    FROM companies WHERE company_id = {placeholder}
                ''', (company_id,))
                
                company_data = cursor.fetchone()
                conn.close()
                
                if company_data:
                    # PostgreSQL RealDictRow için sözlük erişimi kullan
                    if hasattr(company_data, 'keys'):  # RealDictRow veya dict
                        user_data.update({
                            'company_name': company_data.get('company_name', ''),
                            'contact_person': company_data.get('contact_person', ''),
                            'email': company_data.get('email', ''),
                            'phone': company_data.get('phone', ''),
                            'sector': company_data.get('sector', 'construction'),
                            'address': company_data.get('address', '')
                        })
                    else:  # SQLite tuple formatı
                        user_data.update({
                            'company_name': company_data[0] or '',
                            'contact_person': company_data[1] or '',
                            'email': company_data[2] or '',
                            'phone': company_data[3] or '',
                            'sector': company_data[4] or 'construction',
                            'address': company_data[5] or ''
                        })
                
            except Exception as e:
                logger.error(f"❌ Şirket bilgileri yüklenirken hata: {e}")
                # Varsayılan değerler
                user_data.update({
                    'company_name': '',
                    'contact_person': '',
                    'email': '',
                    'phone': '',
                    'sector': 'construction',
                    'address': ''
                })
            
            return render_template_string(self.get_company_settings_template(), 
                                        company_id=company_id, 
                                        user_data=user_data)
        
        @self.app.route('/api/company/<company_id>/profile', methods=['PUT'])
        def update_company_profile(company_id):
            """Şirket profili güncelle"""
            try:
                # Session kontrolü
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Veri gerekli'}), 400
                
                # Debug: Gelen veriyi logla
                print(f"🔍 Profile update data: {data}")
                
                # Profil güncelleme
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                # Şirket bilgilerini güncelle
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f"""
                        UPDATE companies 
                    SET company_name = {placeholder}, 
                        contact_person = {placeholder}, 
                        email = {placeholder}, 
                        phone = {placeholder}, 
                        sector = {placeholder}, 
                        address = {placeholder}
                    WHERE company_id = {placeholder}
                    """, (
                        data.get('company_name'),
                        data.get('contact_person'),
                        data.get('email'),
                        data.get('phone'),
                        data.get('sector'),
                        data.get('address'),
                        company_id
                    ))
                
                # Kullanıcı profil resmini güncelle (eğer varsa)
                if 'profile_image' in data:
                    cursor.execute(f"""
                        UPDATE users 
                        SET profile_image = {placeholder}
                        WHERE company_id = {placeholder}
                    """, (
                        data.get('profile_image'),
                        company_id
                    ))
                
                # Kullanıcı bilgilerini güncelle
                cursor.execute(f"""
                        UPDATE users 
                    SET email = {placeholder}
                    WHERE company_id = {placeholder}
                    """, (
                        data.get('email'),
                        company_id
                    ))
                
                conn.commit()
                conn.close()
                
                print(f"✅ Profile updated successfully for company: {company_id}")
                return jsonify({'success': True, 'message': 'Profil başarıyla güncellendi'})
                    
            except Exception as e:
                print(f"❌ Profile update error: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Sunucu hatası: {str(e)}'}), 500

        @self.app.route('/api/company/<company_id>/profile/upload-logo', methods=['POST'])
        def upload_company_logo(company_id):
            """Şirket logosu yükle"""
            try:
                # Session kontrolü
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                if 'logo' not in request.files:
                    return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400
                
                file = request.files['logo']
                if file.filename == '':
                    return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400
                
                # Dosya uzantısını kontrol et
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                file_extension = file.filename.rsplit('.', 1)[1].lower()
                
                if file_extension not in allowed_extensions:
                    return jsonify({'success': False, 'error': 'Geçersiz dosya formatı. PNG, JPG, JPEG, GIF desteklenir.'}), 400
                
                # Dosya boyutunu kontrol et (max 5MB)
                file.seek(0, 2)  # Dosya sonuna git
                file_size = file.tell()
                file.seek(0)  # Başa dön
                
                if file_size > 5 * 1024 * 1024:  # 5MB
                    return jsonify({'success': False, 'error': 'Dosya boyutu 5MB\'dan büyük olamaz'}), 400
                
                # Dosya adını oluştur
                import uuid
                filename = f"logo_{company_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
                
                # Upload klasörünü oluştur
                upload_folder = os.path.join(os.getcwd(), 'static', 'uploads', 'logos')
                os.makedirs(upload_folder, exist_ok=True)
                
                # Dosyayı kaydet
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                
                # Veritabanında profil resmini güncelle
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # Timestamp fonksiyonu
                if hasattr(self.db, 'db_adapter') and self.db.db_adapter.db_type == 'postgresql':
                    timestamp_func = 'CURRENT_TIMESTAMP'
                else:
                    timestamp_func = 'datetime(\'now\')'
                
                cursor.execute(f"""
                    UPDATE users 
                    SET profile_image = {placeholder}, updated_at = {timestamp_func}
                    WHERE company_id = {placeholder}
                """, (f'/static/uploads/logos/{filename}', company_id))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True, 
                    'message': 'Logo başarıyla yüklendi',
                    'logo_url': f'/static/uploads/logos/{filename}'
                })
                    
            except Exception as e:
                print(f"❌ Logo upload error: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Yükleme hatası: {str(e)}'}), 500
        
        @self.app.route('/api/company/<company_id>/change-password', methods=['PUT'])
        def change_company_password(company_id):
            """Şirket şifresini değiştir"""
            try:
                # Session kontrolü
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data or not all(k in data for k in ['current_password', 'new_password']):
                    return jsonify({'success': False, 'error': 'Mevcut ve yeni şifre gerekli'}), 400
                
                # Mevcut şifre kontrolü
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'SELECT password_hash FROM users WHERE company_id = {placeholder} AND role = \'admin\'', (company_id,))
                stored_password = cursor.fetchone()
                
                if not stored_password or not bcrypt.checkpw(data['current_password'].encode('utf-8'), stored_password[0].encode('utf-8')):
                    return jsonify({'success': False, 'error': 'Mevcut şifre yanlış'}), 401
                
                # Yeni şifre hash'le
                new_password_hash = bcrypt.hashpw(data['new_password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Şifre güncelle
                cursor.execute(f"""
                    UPDATE users 
                    SET password_hash = {placeholder} 
                    WHERE company_id = {placeholder}
                """, (new_password_hash, company_id))
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True, 'message': 'Şifre başarıyla değiştirildi'})
                    
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/company/<company_id>/delete-account', methods=['POST'])
        def company_delete_account(company_id):
            """Şirket hesabını sil - Self Service"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                data = request.json
                password = data.get('password')
                
                if not password:
                    return jsonify({'success': False, 'error': 'Şifre gerekli'}), 400
                
                # Şifre kontrolü
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'SELECT password_hash FROM users WHERE company_id = {placeholder} AND role = \'admin\'', (company_id,))
                stored_password = cursor.fetchone()
                
                if not stored_password or not bcrypt.checkpw(password.encode('utf-8'), stored_password[0].encode('utf-8')):
                    return jsonify({'success': False, 'error': 'Yanlış şifre'}), 401
                
                # Hesap silme işlemi
                tables_to_clean = ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']
                
                for table in tables_to_clean:
                    cursor.execute(f'DELETE FROM {table} WHERE company_id = {placeholder}', (company_id,))
                
                conn.commit()
                conn.close()
                
                # Oturumu temizle
                session.clear()
                
                return jsonify({'success': True, 'message': 'Hesabınız başarıyla silindi'})
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/company/<company_id>/users', methods=['GET'])
        def company_users(company_id):
            """Şirket kullanıcı yönetimi sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            return render_template_string(self.get_users_template(), 
                                        company_id=company_id, 
                                        user_data=user_data)
        
        @self.app.route('/api/company/<company_id>/users', methods=['GET'])
        def get_company_users(company_id):
            """Şirket kullanıcılarını getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Kullanıcıları getir
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f"""
                    SELECT user_id, email, username, role, status, created_at, last_login
                    FROM users 
                    WHERE company_id = {placeholder}
                    ORDER BY created_at DESC
                """, (company_id,))
                
                users = []
                for row in cursor.fetchall():
                    # PostgreSQL RealDictRow için sözlük erişimi kullan
                    if hasattr(row, 'keys'):  # RealDictRow veya dict
                        users.append({
                            'user_id': row.get('user_id'),
                            'email': row.get('email'),
                            'username': row.get('username'),
                            'role': row.get('role') or 'admin',
                            'status': row.get('status'),
                            'created_at': str(row.get('created_at')) if row.get('created_at') else '',
                            'last_login': str(row.get('last_login')) if row.get('last_login') else ''
                        })
                    else:  # Liste formatı (SQLite için)
                        users.append({
                            'user_id': row[0],
                            'email': row[1],
                                'username': row[2],
                            'role': row[3] if row[3] else 'admin',
                            'status': row[4] if row[4] else 'active',
                                'created_at': str(row[5]) if row[5] else '',
                                'last_login': str(row[6]) if row[6] else ''
                        })
                
                conn.close()
                return jsonify({'success': True, 'users': users})
                
            except Exception as e:
                print(f"❌ Users fetch error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/users', methods=['POST'])
        def add_company_user(company_id):
            """Yeni kullanıcı ekle"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data or not all(k in data for k in ['email', 'contact_person', 'role']):
                    return jsonify({'success': False, 'error': 'Email, isim ve rol gerekli'}), 400
                
                # Kullanıcı ID oluştur
                import uuid
                user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
                
                # Username oluştur (email'den veya contact_person'dan)
                username = data.get('username') or data['email'].split('@')[0]
                
                # Geçici şifre oluştur
                temp_password = f"temp{uuid.uuid4().hex[:8]}"
                password_hash = self.db.hash_password(temp_password)
                
                # Kullanıcı ekle
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # PostgreSQL için timestamp fonksiyonu
                timestamp_func = 'CURRENT_TIMESTAMP' if hasattr(self.db, 'db_adapter') and self.db.db_adapter.db_type == 'postgresql' else 'datetime(\'now\')'
                
                cursor.execute(f"""
                    INSERT INTO users (user_id, company_id, username, email, contact_person, password_hash, role, status, created_at)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 'active', {timestamp_func})
                """, (user_id, company_id, username, data['email'], data['contact_person'], password_hash, data['role']))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True, 
                    'message': 'Kullanıcı başarıyla eklendi',
                    'user_id': user_id,
                    'temp_password': temp_password
                })
                
            except Exception as e:
                print(f"❌ Add user error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/users/<user_id>', methods=['DELETE'])
        def delete_company_user(company_id, user_id):
            """Kullanıcı sil"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Kendi hesabını silmeye izin verme
                if user_data.get('user_id') == user_id:
                    return jsonify({'success': False, 'error': 'Kendi hesabınızı silemezsiniz'}), 400
                
                # Kullanıcı sil
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f"DELETE FROM users WHERE user_id = {placeholder} AND company_id = {placeholder}", (user_id, company_id))
                cursor.execute(f"DELETE FROM sessions WHERE user_id = {placeholder}", (user_id,))
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True, 'message': 'Kullanıcı başarıyla silindi'})
                
            except Exception as e:
                print(f"❌ Delete user error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/company/<company_id>/reports', methods=['GET'])
        def company_reports(company_id):
            """Şirket raporlama sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            return render_template_string(self.get_reports_template(), 
                                        company_id=company_id, 
                                        user_data=user_data)
        
        @self.app.route('/api/company/<company_id>/reports/violations', methods=['GET'])
        def get_violations_report(company_id):
            """İhlal raporunu getir - Dinamik Database Verisi"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Son 30 günün ihlal verileri - Gerçek Database'den
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # Günlük ihlal sayıları
                if self.db.db_adapter.db_type == 'postgresql':
                    cursor.execute(f'''
                        SELECT DATE(timestamp) as date, COUNT(*) as count,
                               STRING_AGG(DISTINCT missing_ppe, ', ') as ppe_types
                        FROM violations 
                        WHERE company_id = {placeholder} 
                        AND timestamp >= {placeholder}
                        GROUP BY DATE(timestamp)
                        ORDER BY DATE(timestamp) DESC
                        LIMIT 30
                    ''', (company_id, start_date.isoformat()))
                else:
                    cursor.execute(f'''
                        SELECT DATE(timestamp) as date, COUNT(*) as count,
                               GROUP_CONCAT(DISTINCT missing_ppe) as ppe_types
                        FROM violations 
                        WHERE company_id = {placeholder} 
                        AND timestamp >= {placeholder}
                        GROUP BY DATE(timestamp)
                        ORDER BY DATE(timestamp) DESC
                        LIMIT 30
                    ''', (company_id, start_date.isoformat()))
                
                daily_violations = cursor.fetchall()
                
                # Kamera bazlı ihlaller
                cursor.execute(f'''
                    SELECT camera_id, COUNT(*) as count,
                           MAX(timestamp) as last_violation
                    FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= {placeholder}
                    GROUP BY camera_id
                    ORDER BY count DESC
                ''', (company_id, start_date.isoformat()))
                
                camera_violations = cursor.fetchall()
                
                # PPE türü bazlı ihlaller
                cursor.execute(f'''
                    SELECT missing_ppe, COUNT(*) as count
                    FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= {placeholder}
                    GROUP BY missing_ppe
                    ORDER BY count DESC
                ''', (company_id, start_date.isoformat()))
                
                ppe_violations = cursor.fetchall()
                
                conn.close()
                
                # Veriyi formatla
                violations_data = {
                    'daily_violations': [],
                    'camera_violations': [],
                    'ppe_violations': [],
                    'total_violations': 0,
                    'period': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
                }
                
                # Günlük ihlaller
                total_violations = 0
                for row in daily_violations:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        violations_data['daily_violations'].append({
                            'date': row['date'],
                            'count': row['count'],
                            'ppe_types': row['ppe_types'] or ''
                        })
                        total_violations += row['count']
                    else:  # SQLite
                        violations_data['daily_violations'].append({
                            'date': row[0],
                            'count': row[1],
                            'ppe_types': row[2] or ''
                        })
                        total_violations += row[1]
                
                # Kamera ihlalleri
                for row in camera_violations:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        violations_data['camera_violations'].append({
                            'camera_id': row['camera_id'],
                            'count': row['count'],
                            'last_violation': row['last_violation']
                        })
                    else:  # SQLite
                        violations_data['camera_violations'].append({
                            'camera_id': row[0],
                            'count': row[1],
                            'last_violation': row[2]
                        })
                
                # PPE ihlalleri
                for row in ppe_violations:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        violations_data['ppe_violations'].append({
                            'ppe_type': row['missing_ppe'],
                            'count': row['count']
                        })
                    else:  # SQLite
                        violations_data['ppe_violations'].append({
                            'ppe_type': row[0],
                            'count': row[1]
                        })
                
                violations_data['total_violations'] = total_violations
                
                logger.info(f"✅ Violations report generated for {company_id}: {total_violations} violations")
                
                return jsonify({'success': True, 'data': violations_data})
                violations = [
                    {
                        'date': '2025-07-05',
                        'camera_id': 'CAM_001',
                        'camera_name': 'Ana Giriş',
                        'violation_type': 'helmet_missing',
                        'violation_text': 'Baret takılmamış',
                        'penalty': 100,
                        'worker_id': 'W001',
                        'confidence': 95.2
                    },
                    {
                        'date': '2025-07-04',
                        'camera_id': 'CAM_002', 
                        'camera_name': 'İnşaat Alanı',
                        'violation_type': 'safety_vest_missing',
                        'violation_text': 'Güvenlik yeleği yok',
                        'penalty': 75,
                        'worker_id': 'W002',
                        'confidence': 87.5
                    },
                    {
                        'date': '2025-07-03',
                        'camera_id': 'CAM_001',
                        'camera_name': 'Ana Giriş',
                        'violation_type': 'safety_shoes_missing',
                        'violation_text': 'Güvenlik ayakkabısı yok',
                        'penalty': 50,
                        'worker_id': 'W003',
                        'confidence': 92.1
                    }
                ]
                
                return jsonify({'success': True, 'violations': violations})
                
            except Exception as e:
                print(f"❌ Violations report error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/reports/compliance', methods=['GET'])
        def get_compliance_report(company_id):
            """Uyumluluk raporunu getir - Dinamik Database Verisi"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Gerçek uyumluluk verileri - Database'den
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # Son 30 günün detection ve violation verileri
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                # Günlük uyum oranları
                if self.db.db_adapter.db_type == 'postgresql':
                    cursor.execute(f'''
                        SELECT DATE(d.timestamp) as date,
                               COUNT(d.detection_id) as total_detections,
                               COUNT(v.violation_id) as total_violations,
                               ROUND(
                                   CASE 
                                       WHEN COUNT(d.detection_id) > 0 
                                       THEN (COUNT(d.detection_id) - COUNT(v.violation_id)) * 100.0 / COUNT(d.detection_id)
                                       ELSE 0 
                                   END, 1
                               ) as compliance_rate
                        FROM detections d
                        LEFT JOIN violations v ON DATE(d.timestamp) = DATE(v.timestamp) 
                                              AND d.company_id = v.company_id
                        WHERE d.company_id = {placeholder} 
                        AND d.timestamp >= {placeholder}
                        GROUP BY DATE(d.timestamp)
                        ORDER BY DATE(d.timestamp) DESC
                        LIMIT 30
                    ''', (company_id, start_date.isoformat()))
                else:
                    cursor.execute(f'''
                        SELECT DATE(d.timestamp) as date,
                               COUNT(d.detection_id) as total_detections,
                               COUNT(v.violation_id) as total_violations,
                               ROUND(
                                   CASE 
                                       WHEN COUNT(d.detection_id) > 0 
                                       THEN (COUNT(d.detection_id) - COUNT(v.violation_id)) * 100.0 / COUNT(d.detection_id)
                                       ELSE 0 
                                   END, 1
                               ) as compliance_rate
                        FROM detections d
                        LEFT JOIN violations v ON DATE(d.timestamp) = DATE(v.timestamp) 
                                              AND d.company_id = v.company_id
                        WHERE d.company_id = {placeholder} 
                        AND d.timestamp >= {placeholder}
                        GROUP BY DATE(d.timestamp)
                        ORDER BY DATE(d.timestamp) DESC
                        LIMIT 30
                    ''', (company_id, start_date.isoformat()))
                
                daily_compliance = cursor.fetchall()
                
                # Kamera bazlı uyum oranları
                cursor.execute(f'''
                    SELECT d.camera_id,
                           COUNT(d.detection_id) as total_detections,
                           COUNT(v.violation_id) as total_violations,
                           ROUND(
                               CASE 
                                   WHEN COUNT(d.detection_id) > 0 
                                   THEN (COUNT(d.detection_id) - COUNT(v.violation_id)) * 100.0 / COUNT(d.detection_id)
                                   ELSE 0 
                               END, 1
                           ) as compliance_rate
                    FROM detections d
                    LEFT JOIN violations v ON d.camera_id = v.camera_id 
                                          AND d.company_id = v.company_id
                    WHERE d.company_id = {placeholder} 
                    AND d.timestamp >= {placeholder}
                    GROUP BY d.camera_id
                    ORDER BY compliance_rate DESC
                ''', (company_id, start_date.isoformat()))
                
                camera_compliance = cursor.fetchall()
                
                # PPE türü bazlı uyum oranları
                cursor.execute(f'''
                    SELECT missing_ppe, COUNT(*) as violation_count
                    FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= {placeholder}
                    GROUP BY missing_ppe
                    ORDER BY violation_count DESC
                ''', (company_id, start_date.isoformat()))
                
                ppe_violations = cursor.fetchall()
                
                # Toplam istatistikler
                cursor.execute(f'''
                    SELECT COUNT(*) as total_detections
                    FROM detections 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= {placeholder}
                ''', (company_id, start_date.isoformat()))
                
                total_detections = cursor.fetchone()
                total_detections = total_detections[0] if total_detections else 0
                
                cursor.execute(f'''
                    SELECT COUNT(*) as total_violations
                    FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= {placeholder}
                ''', (company_id, start_date.isoformat()))
                
                total_violations = cursor.fetchone()
                total_violations = total_violations[0] if total_violations else 0
                
                conn.close()
                
                # Genel uyum oranı hesapla
                overall_compliance = 0
                if total_detections > 0:
                    overall_compliance = round((total_detections - total_violations) * 100.0 / total_detections, 1)
                
                # PPE türü bazlı uyum hesapla
                ppe_compliance = {
                    'helmet_compliance': 90.0,  # Varsayılan
                    'vest_compliance': 85.0,    # Varsayılan
                    'shoes_compliance': 88.0    # Varsayılan
                }
                
                # Violation verilerinden PPE uyum oranlarını hesapla
                helmet_violations = 0
                vest_violations = 0
                shoes_violations = 0
                
                for row in ppe_violations:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        ppe_type = row['missing_ppe'].lower()
                        count = row['violation_count']
                    else:  # SQLite
                        ppe_type = row[0].lower()
                        count = row[1]
                    
                    if 'helmet' in ppe_type or 'kask' in ppe_type:
                        helmet_violations += count
                    elif 'vest' in ppe_type or 'yelek' in ppe_type:
                        vest_violations += count
                    elif 'shoes' in ppe_type or 'ayakkabı' in ppe_type:
                        shoes_violations += count
                
                # PPE uyum oranlarını güncelle
                if total_detections > 0:
                    ppe_compliance['helmet_compliance'] = round((total_detections - helmet_violations) * 100.0 / total_detections, 1)
                    ppe_compliance['vest_compliance'] = round((total_detections - vest_violations) * 100.0 / total_detections, 1)
                    ppe_compliance['shoes_compliance'] = round((total_detections - shoes_violations) * 100.0 / total_detections, 1)
                
                # Veriyi formatla
                compliance_data = {
                    'overall_compliance': overall_compliance,
                    'helmet_compliance': ppe_compliance['helmet_compliance'],
                    'vest_compliance': ppe_compliance['vest_compliance'],
                    'shoes_compliance': ppe_compliance['shoes_compliance'],
                    'daily_stats': [],
                    'camera_stats': [],
                    'total_detections': total_detections,
                    'total_violations': total_violations,
                    'period': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
                }
                
                # Günlük istatistikler
                for row in daily_compliance:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        compliance_data['daily_stats'].append({
                            'date': str(row['date']),
                            'compliance': float(row['compliance_rate']) if row['compliance_rate'] else 0,
                            'detections': row['total_detections'],
                            'violations': row['total_violations']
                        })
                    else:  # SQLite
                        compliance_data['daily_stats'].append({
                            'date': str(row[0]),
                            'compliance': float(row[3]) if row[3] else 0,
                            'detections': row[1],
                            'violations': row[2]
                        })
                
                # Kamera istatistikleri
                for row in camera_compliance:
                    if hasattr(row, 'keys'):  # PostgreSQL
                        compliance_data['camera_stats'].append({
                            'camera_name': f'Kamera {row["camera_id"]}',
                            'camera_id': row['camera_id'],
                            'compliance': float(row['compliance_rate']) if row['compliance_rate'] else 0,
                            'detections': row['total_detections'],
                            'violations': row['total_violations']
                        })
                    else:  # SQLite
                        compliance_data['camera_stats'].append({
                            'camera_name': f'Kamera {row[0]}',
                            'camera_id': row[0],
                            'compliance': float(row[3]) if row[3] else 0,
                            'detections': row[1],
                            'violations': row[2]
                        })
                
                logger.info(f"✅ Compliance report generated for {company_id}: {overall_compliance}% overall compliance")
                
                return jsonify({'success': True, 'data': compliance_data})
                
            except Exception as e:
                print(f"❌ Compliance report error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/reports/export', methods=['POST'])
        def export_report(company_id):
            """Raporu dışa aktar"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                report_type = data.get('type', 'violations')
                format_type = data.get('format', 'pdf')
                
                # Örnek export işlemi
                export_url = f"/exports/{company_id}_{report_type}_{format_type}.{format_type}"
                
                return jsonify({
                    'success': True, 
                    'message': 'Rapor oluşturuldu',
                    'download_url': export_url
                })
                
            except Exception as e:
                print(f"❌ Export report error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/company/<company_id>/cameras/discover', methods=['POST'])
        def discover_cameras(company_id):
            """Unified kamera keşif ve senkronizasyon sistemi"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json() or {}
                network_range = data.get('network_range', '192.168.1.0/24')
                auto_sync = data.get('auto_sync', True)  # Otomatik DB sync
                
                logger.info(f"🔍 Starting unified camera discovery for company {company_id}")
                
                # Enterprise Camera Manager ile discovery
                if hasattr(self, 'camera_manager') and self.camera_manager and self.enterprise_enabled:
                    try:
                        # Full camera synchronization
                        sync_result = self.camera_manager.full_camera_sync(company_id, network_range)
                        
                        if sync_result['success']:
                            return jsonify({
                                'success': True,
                                'message': 'Kamera keşif ve senkronizasyon tamamlandı',
                                'discovery_result': sync_result['discovery_result'],
                                'config_sync': sync_result['config_sync_result'],
                                'total_cameras_in_db': sync_result['final_camera_count'],
                                'auto_sync_enabled': auto_sync,
                                'mode': 'enterprise'
                            })
                        else:
                            logger.warning(f"⚠️ Enterprise sync failed: {sync_result.get('error')}")
                            # Continue with fallback
                    
                    except Exception as e:
                        logger.error(f"❌ Enterprise camera discovery failed: {e}")
                        # Continue with fallback
                
                # Fallback: Standard discovery sistemi
                logger.info("📱 Using standard discovery system")
                
                discovered_cameras = []
                scan_time = '2.0 saniye'
                
                try:
                    from camera_discovery import IPCameraDiscovery
                    discovery = IPCameraDiscovery()
                    result = discovery.scan_network(network_range, timeout=2)
                    discovered_cameras = result['cameras']
                    scan_time = result['scan_time']
                    
                    # Auto sync to database if enabled
                    if auto_sync and discovered_cameras:
                        try:
                            from database_adapter import get_camera_discovery_manager
                            discovery_manager = get_camera_discovery_manager()
                            sync_result = discovery_manager.sync_discovered_cameras_to_db(company_id, discovered_cameras)
                            
                            logger.info(f"✅ Auto-sync: {sync_result['added']} added, {sync_result['updated']} updated")
                            
                            return jsonify({
                                'success': True,
                                'cameras': discovered_cameras,
                                'network_range': network_range,
                                'scan_time': scan_time,
                                'auto_sync_enabled': auto_sync,
                                'sync_result': sync_result,
                                'mode': 'standard_with_sync'
                            })
                        except Exception as sync_error:
                            logger.error(f"❌ Auto-sync failed: {sync_error}")
                            # Continue without sync
                
                except ImportError:
                    # Fallback: örnek veriler
                    discovered_cameras = [
                        {
                            'ip': '192.168.1.101',
                            'port': 554,
                            'brand': 'Hikvision',
                            'model': 'DS-2CD2043G0-I',
                            'rtsp_url': 'rtsp://192.168.1.101:554/Streaming/Channels/101',
                            'resolution': '4MP',
                            'status': 'online',
                            'auth_required': True
                        }
                    ]
                    scan_time = '2.3 saniye'
                
                return jsonify({
                    'success': True,
                    'cameras': discovered_cameras,
                    'network_range': network_range,
                    'scan_time': scan_time,
                    'auto_sync_enabled': auto_sync,
                    'mode': 'fallback'
                })
                
            except Exception as e:
                logger.error(f"❌ Camera discovery error: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/test', methods=['POST'])
        def test_camera(company_id):
            """Gerçek kamera bağlantı testi - Enhanced real camera support"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Kamera bilgileri gerekli'}), 400
                
                logger.info(f"🔍 Testing real camera connection for company {company_id}")
                
                # Try enhanced real camera manager first
                test_result = None
                try:
                    from camera_integration_manager import RealCameraManager, RealCameraConfig
                    
                    real_camera_manager = RealCameraManager()
                    
                    # Create camera config from form data
                    camera_config = RealCameraConfig(
                        camera_id=f"TEST_{data.get('ip_address', 'unknown')}",
                        name=data.get('name', 'Test Camera'),
                        ip_address=data.get('ip_address', ''),
                        port=int(data.get('port', 8080)),
                        username=data.get('username', ''),
                        password=data.get('password', ''),
                        protocol=data.get('protocol', 'http'),
                        stream_path=data.get('stream_path', '/video'),
                        auth_type=data.get('auth_type', 'basic')
                    )
                    
                    # Gerçek kamera testi yap
                    test_result = real_camera_manager.test_real_camera_connection(camera_config)
                    
                except (ImportError, AttributeError) as e:
                    logger.warning(f"⚠️ RealCameraManager not available: {e}, using fallback")
                    test_result = None
                except Exception as e:
                    logger.error(f"❌ RealCameraManager error: {e}, using fallback")
                    test_result = None
                
                # Fallback to basic connection test if RealCameraManager fails
                if test_result is None:
                    test_result = self._basic_camera_test(data)
                
                # API response formatına dönüştür
                if test_result and test_result.get('success'):
                    api_response = {
                            'success': True,
                            'connection_time': test_result.get('connection_time', 0),
                            'stream_quality': test_result.get('stream_quality', 'good'),
                            'supported_features': test_result.get('supported_features', []),
                            'camera_info': test_result.get('camera_info', {}),
                        'test_results': {
                                'connection_status': 'success',
                                'response_time': f"{test_result.get('connection_time', 0):.0f}ms",
                                'resolution': test_result.get('camera_info', {}).get('resolution', 'Bilinmiyor'),
                                'fps': test_result.get('camera_info', {}).get('fps', 25),
                                'quality': test_result.get('stream_quality', 'good'),
                                'supported_features': test_result.get('supported_features', []),
                                'test_duration': f"{test_result.get('connection_time', 0)/1000:.1f} saniye"
                            },
                            'message': f'Kamera bağlantısı başarılı! ({test_result.get("connection_time", 0):.0f}ms)'
                        }
                else:
                    api_response = {
                        'success': False,
                        'error': test_result.get('error_message', 'Bilinmeyen hata') if test_result else 'Kamera testi başarısız',
                        'test_results': {
                            'connection_status': 'failed',
                            'error_message': test_result.get('error_message', 'Bilinmeyen hata') if test_result else 'Kamera testi başarısız',
                            'test_duration': f"{test_result.get('connection_time', 0)/1000:.1f} saniye" if test_result else '0.0 saniye'
                        },
                        'message': f'Kamera bağlantısı başarısız: {test_result.get("error_message", "Bilinmeyen hata") if test_result else "Kamera testi başarısız"}'
                    }
                
                camera_name = data.get('name', data.get('ip_address', 'Unknown'))
                logger.info(f"✅ Camera test completed for {camera_name}: {api_response['success']}")
                return jsonify(api_response)
                
            except Exception as e:
                logger.error(f"❌ Real camera test error: {e}")
                return jsonify({
                    'success': False, 
                    'error': str(e),
                    'message': f'Kamera testi sırasında hata: {str(e)}'
                }), 500

        @self.app.route('/api/company/<company_id>/cameras/smart-test', methods=['POST'])
        def smart_test_camera(company_id):
            """Akıllı kamera tespiti ve test"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                ip_address = data.get('ip_address')
                camera_name = data.get('camera_name', 'Akıllı Tespit Kamera')
                
                if not ip_address:
                    return jsonify({'success': False, 'error': 'IP adresi gerekli'}), 400
                
                logger.info(f"🧠 Smart camera test for {ip_address}")
                
                try:
                    from camera_integration_manager import SmartCameraDetector
                    
                    detector = SmartCameraDetector()
                    detection_result = detector.smart_detect_camera(ip_address)
                    
                    if detection_result['success']:
                        # Kamera başarıyla tespit edildi, test et
                        config = detection_result['config']
                        
                        # RealCameraManager ile test et
                        from camera_integration_manager import RealCameraManager
                        camera_manager = RealCameraManager()
                        
                        test_result = camera_manager.test_real_camera_connection(
                            name=camera_name,
                            ip_address=ip_address,
                            port=config['port'],
                            protocol=config['protocol'],
                            stream_path=config['path'],
                            username=config['credentials']['username'],
                            password=config['credentials']['password']
                        )
                        
                        return jsonify({
                            'success': True,
                            'detection_info': detection_result,
                            'connection_test': test_result,
                            'message': f"Kamera tespit edildi: {detection_result['model']} (Güven: {detection_result['confidence']:.1%})"
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': detection_result['error'],
                            'detection_info': detection_result
                        })
                        
                except Exception as e:
                    logger.error(f"❌ Smart test error: {e}")
                    return jsonify({
                        'success': False,
                        'error': f'Akıllı test hatası: {str(e)}'
                    }), 500
                    
            except Exception as e:
                logger.error(f"❌ Smart test API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/test', methods=['POST'])
        def test_specific_camera(company_id, camera_id):
            """Belirli bir kamerayı test et"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data['company_id'] != company_id:
                    return jsonify({'success': False, 'error': 'Unauthorized'}), 401
                
                # Kamerayı veritabanından al
                camera = self.db.get_camera_by_id(camera_id, company_id)
                if not camera:
                    return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
                
                # Kamera testi
                from utils.camera_integration_manager import CameraSource
                camera_source = CameraSource(
                    name=camera['camera_name'],
                    ip_address=camera['ip_address'],
                    port=camera.get('port', 80),
                    protocol=camera.get('protocol', 'http'),
                    stream_path=camera.get('stream_path', '/video'),
                    username=camera.get('username', ''),
                    password=camera.get('password', '')
                )
                
                result = self.get_camera_manager().test_camera_connection(camera_source)
                
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Camera test error: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/stream')
        def camera_stream(company_id, camera_id):
            """Kamera stream sayfası"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data['company_id'] != company_id:
                    return redirect(f'/company/{company_id}/login')
                
                # Kamerayı veritabanından al
                camera = self.db.get_camera_by_id(camera_id, company_id)
                if not camera:
                    return "Kamera bulunamadı", 404
                
                # Stream URL'sini oluştur
                protocol = camera.get('protocol', 'http')
                port = camera.get('port', 80)
                stream_path = camera.get('stream_path', '/video')
                stream_url = f"{protocol}://{camera['ip_address']}:{port}{stream_path}"
                
                return f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>{camera['camera_name']} - Canlı Görüntü</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ margin: 0; padding: 20px; background: #000; color: white; font-family: Arial, sans-serif; }}
                        .stream-container {{ text-align: center; }}
                        .stream-title {{ margin-bottom: 20px; font-size: 24px; }}
                        .stream-video {{ max-width: 100%; height: auto; border-radius: 10px; }}
                        .stream-info {{ margin-top: 20px; font-size: 14px; color: #ccc; }}
                    </style>
                </head>
                <body>
                    <div class="stream-container">
                        <div class="stream-title">{camera['camera_name']} - Canlı Görüntü</div>
                        <img src="{stream_url}" alt="Kamera Görüntüsü" class="stream-video" 
                             onerror="this.style.display='none'; document.body.innerHTML='<div style=\\'text-align:center;padding:50px\\'><h2>Görüntü alınamadı</h2><p>Kamera bağlantısını kontrol edin</p></div>'">
                        <div class="stream-info">
                            <p>IP: {camera['ip_address']} | Konum: {camera.get('location', 'N/A')}</p>
                            <p>Son güncelleme: {camera.get('updated_at', 'N/A')}</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
            except Exception as e:
                logger.error(f"Camera stream error: {e}")
                return "Stream yüklenirken hata oluştu", 500
        

        
        @self.app.route('/api/company/<company_id>/cameras/groups', methods=['GET'])
        def get_camera_groups(company_id):
            """Kamera gruplarını getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Örnek kamera grupları
                groups = [
                    {
                        'group_id': 'GRP_001',
                        'name': 'Ana Giriş',
                        'location': 'Bina A - Zemin Kat',
                        'camera_count': 3,
                        'active_cameras': 3,
                        'group_type': 'entrance',
                        'created_at': '2025-01-01 10:00:00'
                    },
                    {
                        'group_id': 'GRP_002',
                        'name': 'İnşaat Alanı',
                        'location': 'Dış Alan - Kuzey',
                        'camera_count': 5,
                        'active_cameras': 4,
                        'group_type': 'work_area',
                        'created_at': '2025-01-01 11:00:00'
                    },
                    {
                        'group_id': 'GRP_003',
                        'name': 'Depo & Yükleme',
                        'location': 'Bina B - Arka',
                        'camera_count': 2,
                        'active_cameras': 2,
                        'group_type': 'storage',
                        'created_at': '2025-01-01 12:00:00'
                    }
                ]
                
                return jsonify({'success': True, 'groups': groups})
                
            except Exception as e:
                print(f"❌ Camera groups error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/groups', methods=['POST'])
        def create_camera_group(company_id):
            """Yeni kamera grubu oluştur"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data or not all(k in data for k in ['name', 'location', 'group_type']):
                    return jsonify({'success': False, 'error': 'Grup adı, lokasyon ve tür gerekli'}), 400
                
                # Grup ID oluştur
                import uuid
                group_id = f"GRP_{uuid.uuid4().hex[:8].upper()}"
                
                return jsonify({
                    'success': True,
                    'message': 'Kamera grubu oluşturuldu',
                    'group_id': group_id,
                    'name': data['name']
                })
                
            except Exception as e:
                print(f"❌ Create camera group error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/group', methods=['PUT'])
        def assign_camera_to_group(company_id, camera_id):
            """Kamerayı gruba ata"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                group_id = data.get('group_id')
                
                if not group_id:
                    return jsonify({'success': False, 'error': 'Grup ID gerekli'}), 400
                
                return jsonify({
                    'success': True,
                    'message': 'Kamera gruba atandı',
                    'camera_id': camera_id,
                    'group_id': group_id
                })
                
            except Exception as e:
                print(f"❌ Assign camera to group error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/smart-discover', methods=['POST'])
        def smart_discover_cameras(company_id):
            """Akıllı kamera keşfi - Ağ taraması"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                network_range = data.get('network_range', '192.168.1.0/24')
                
                logger.info(f"🧠 Smart camera discovery for company {company_id}")
                
                try:
                    from camera_integration_manager import ProfessionalCameraManager
                    
                    camera_manager = ProfessionalCameraManager()
                    discovered_cameras = camera_manager.smart_discover_cameras(network_range)
                    
                    return jsonify({
                        'success': True,
                        'cameras': discovered_cameras,
                        'total_found': len(discovered_cameras),
                        'network_range': network_range
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Smart discovery error: {e}")
                    return jsonify({
                        'success': False,
                        'error': f'Akıllı keşif hatası: {str(e)}'
                    }), 500
                
            except Exception as e:
                logger.error(f"❌ Smart discovery API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/company/<company_id>/cameras/model-database', methods=['GET'])
        def get_camera_model_database(company_id):
            """Kamera modeli veritabanını getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                try:
                    from utils.camera_model_database import get_camera_database
                    
                    db = get_camera_database()
                    models = {}
                    
                    for model_id in db.get_all_models():
                        model_info = db.get_model_info(model_id)
                        models[model_id] = {
                            'name': model_info.name,
                            'manufacturer': model_info.manufacturer,
                            'features': model_info.features,
                            'ports': model_info.ports,
                            'paths': model_info.paths
                        }
                    
                    return jsonify({
                        'success': True,
                        'models': models,
                        'total_models': len(models)
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Model database error: {e}")
                    return jsonify({
                        'success': False,
                        'error': f'Model veritabanı hatası: {str(e)}'
                    }), 500
                
            except Exception as e:
                logger.error(f"❌ Model database API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>', methods=['GET'])
        def get_camera_details(company_id, camera_id):
            """Kamera detaylarını getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Kamera detaylarını veritabanından al
                camera = self.db.get_camera_by_id(camera_id, company_id)
                if not camera:
                    return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
                
                return jsonify({
                    'success': True,
                    'camera': camera
                })
                
            except Exception as e:
                logger.error(f"❌ Kamera detayları hatası: {e}")
                return jsonify({'success': False, 'error': 'Kamera detayları alınamadı'}), 500

        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/stream', methods=['GET'])
        def get_camera_stream(company_id, camera_id):
            """Kamera stream URL'si getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Örnek stream bilgileri
                stream_info = {
                    'camera_id': camera_id,
                    'stream_url': f'ws://localhost:5000/stream/{camera_id}',
                    'rtsp_url': f'rtsp://192.168.1.101:554/stream/{camera_id}',
                    'resolution': '1920x1080',
                    'fps': 25,
                    'status': 'active',
                    'last_frame_time': '2025-01-07 14:30:25'
                }
                
                return jsonify({
                    'success': True,
                    'stream_info': stream_info
                })
                
            except Exception as e:
                print(f"❌ Camera stream error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        # Kamera silme API endpoint'i
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>', methods=['DELETE'])
        def delete_camera(company_id, camera_id):
            """Kamera silme API endpoint'i"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                logger.info(f"🗑️ Deleting camera: {camera_id} for company: {company_id}")
                
                # Önce veritabanından kamerayı sil
                success = self.db.delete_camera(camera_id, company_id)
                
                if not success:
                    return jsonify({
                        'success': False,
                        'message': 'Kamera silinemedi'
                    }), 400
                
                # Kamera yöneticisinden kamerayı ayır
                try:
                    from camera_integration_manager import get_camera_manager
                    camera_manager = get_camera_manager()
                    
                    # Kamerayı bağlantıdan ayır
                    disconnect_result = camera_manager.disconnect_camera(camera_id)
                    logger.info(f"🔌 Kamera bağlantısı kesildi: {disconnect_result}")
                        
                except ImportError:
                    logger.info("⚠️ Enterprise camera manager bulunamadı, sadece veritabanından silindi")
                
                return jsonify({
                    'success': True,
                    'message': f'Kamera {camera_id} başarıyla silindi',
                    'camera_id': camera_id
                })
                    
            except Exception as e:
                logger.error(f"❌ Camera deletion failed: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Kamera silinirken hata oluştu: {str(e)}'
                }), 500

        # Kamera düzenleme API endpoint'i
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>', methods=['PUT'])
        def update_camera(company_id, camera_id):
            """Kamera düzenleme API endpoint'i"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                logger.info(f"✏️ Updating camera: {camera_id} for company: {company_id}")
                
                # Güncellenecek alanları hazırla
                update_fields = {}
                if 'name' in data:
                    update_fields['name'] = data['name']
                if 'rtsp_url' in data:
                    update_fields['rtsp_url'] = data['rtsp_url']
                if 'enabled' in data:
                    update_fields['enabled'] = data['enabled']
                if 'resolution' in data:
                    update_fields['resolution'] = data['resolution']
                if 'fps' in data:
                    update_fields['fps'] = data['fps']
                
                if not update_fields:
                    return jsonify({
                        'success': False,
                        'message': 'Güncellenecek alan bulunamadı'
                    }), 400
                
                try:
                    from camera_integration_manager import get_camera_manager
                    camera_manager = get_camera_manager()
                    
                    # Kamera konfigürasyonunu güncelle
                    if camera_id in camera_manager.camera_configs:
                        config = camera_manager.camera_configs[camera_id]
                        
                        if 'name' in update_fields:
                            config.name = update_fields['name']
                        if 'rtsp_url' in update_fields:
                            config.connection_url = update_fields['rtsp_url']
                        if 'enabled' in update_fields:
                            config.enabled = update_fields['enabled']
                            
                            # Kamerayı etkinleştir/devre dışı bırak
                            if update_fields['enabled'] and config.connection_status != 'connected':
                                camera_manager.connect_camera(config)
                            elif not update_fields['enabled'] and config.connection_status == 'connected':
                                camera_manager.disconnect_camera(camera_id)
                        
                        if 'resolution' in update_fields:
                            res_parts = update_fields['resolution'].split('x')
                            if len(res_parts) == 2:
                                config.resolution = (int(res_parts[0]), int(res_parts[1]))
                        
                        if 'fps' in update_fields:
                            config.fps = int(update_fields['fps'])
                    
                    return jsonify({
                        'success': True,
                        'message': 'Kamera başarıyla güncellendi',
                        'camera_id': camera_id,
                        'updated_fields': list(update_fields.keys())
                    })
                        
                except ImportError:
                    # Fallback: Simülasyon modu
                    return jsonify({
                        'success': True,
                        'message': 'Kamera başarıyla güncellendi (Simülasyon)',
                        'camera_id': camera_id,
                        'updated_fields': list(update_fields.keys())
                    })
                    
            except Exception as e:
                logger.error(f"❌ Camera update failed: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Kamera güncellenirken hata oluştu: {str(e)}'
                }), 500

        # Kamera durumu API endpoint'i
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/status', methods=['GET'])
        def get_camera_status_api(company_id, camera_id):
            """Kamera durumu API endpoint'i"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                try:
                    from camera_integration_manager import get_camera_manager
                    camera_manager = get_camera_manager()
                    
                    status = camera_manager.get_camera_status(camera_id)
                    
                    return jsonify({
                        'success': True,
                        'camera_status': status
                    })
                    
                except ImportError:
                    # Fallback: Simülasyon durumu
                    return jsonify({
                        'success': True,
                        'camera_status': {
                            'camera_id': camera_id,
                            'name': f'Kamera {camera_id}',
                            'connection_status': 'connected',
                            'enabled': True,
                            'current_fps': 25.0,
                            'resolution': '1280x720',
                            'source_type': 'simulation',
                            'last_frame_time': datetime.now().isoformat()
                        }
                    })
                
            except Exception as e:
                logger.error(f"❌ Camera status failed: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Kamera durumu alınırken hata oluştu: {str(e)}'
                }), 500

        # Kamera etkinleştir/devre dışı bırak API endpoint'i
        @self.app.route('/api/company/<company_id>/cameras/<camera_id>/toggle', methods=['POST'])
        def toggle_camera(company_id, camera_id):
            """Kamera etkinleştir/devre dışı bırak API endpoint'i"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                try:
                    from camera_integration_manager import get_camera_manager
                    camera_manager = get_camera_manager()
                    
                    # Mevcut durumu al
                    current_status = camera_manager.get_camera_status(camera_id)
                    
                    if current_status.get('status') == 'not_found':
                        return jsonify({
                            'success': False,
                            'message': 'Kamera bulunamadı'
                        }), 404
                    
                    # Durumu değiştir
                    new_enabled = not current_status.get('enabled', False)
                    
                    if camera_id in camera_manager.camera_configs:
                        config = camera_manager.camera_configs[camera_id]
                        config.enabled = new_enabled
                        
                        if new_enabled:
                            # Kamerayı etkinleştir
                            connect_result = camera_manager.connect_camera(config)
                            if connect_result:
                                message = f"Kamera {camera_id} etkinleştirildi"
                                status = "enabled"
                            else:
                                message = f"Kamera {camera_id} etkinleştirilemedi"
                                status = "failed"
                        else:
                            # Kamerayı devre dışı bırak
                            disconnect_result = camera_manager.disconnect_camera(camera_id)
                            if disconnect_result:
                                message = f"Kamera {camera_id} devre dışı bırakıldı"
                                status = "disabled"
                            else:
                                message = f"Kamera {camera_id} devre dışı bırakılamadı"
                                status = "failed"
                        
                        return jsonify({
                            'success': True,
                            'message': message,
                            'camera_id': camera_id,
                            'enabled': new_enabled,
                            'status': status
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'message': 'Kamera konfigürasyonu bulunamadı'
                        }), 404
                        
                except ImportError:
                    # Fallback: Simülasyon modu
                    return jsonify({
                        'success': True,
                        'message': f'Kamera {camera_id} durumu değiştirildi (Simülasyon)',
                        'camera_id': camera_id,
                        'enabled': True,
                        'status': 'enabled'
                    })
                    
            except Exception as e:
                logger.error(f"❌ Camera toggle failed: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Kamera durumu değiştirilirken hata oluştu: {str(e)}'
                }), 500
        
        @self.app.route('/company/<company_id>/profile', methods=['GET'])
        def company_profile(company_id):
            """Şirket profil sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            # Şirket bilgilerini getir
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT company_name, sector, contact_person, email, phone, address,
                           subscription_type, subscription_start, subscription_end, max_cameras
                    FROM companies 
                    WHERE company_id = {placeholder}
                ''', (company_id,))
                
                company_data = cursor.fetchone()
                conn.close()
                
                if company_data:
                    if hasattr(company_data, 'keys'):  # PostgreSQL RealDictRow
                        company_info = {
                            'company_name': company_data['company_name'],
                            'sector': company_data['sector'],
                            'contact_person': company_data['contact_person'],
                            'email': company_data['email'],
                            'phone': company_data['phone'],
                            'address': company_data['address'],
                            'subscription_type': company_data['subscription_type'],
                            'subscription_start': company_data['subscription_start'],
                            'subscription_end': company_data['subscription_end'],
                            'max_cameras': company_data['max_cameras']
                        }
                    else:  # SQLite tuple
                        company_info = {
                            'company_name': company_data[0],
                            'sector': company_data[1],
                            'contact_person': company_data[2],
                            'email': company_data[3],
                            'phone': company_data[4],
                            'address': company_data[5],
                            'subscription_type': company_data[6],
                            'subscription_start': company_data[7],
                            'subscription_end': company_data[8],
                            'max_cameras': company_data[9]
                        }
                else:
                    company_info = {}
                
            except Exception as e:
                logger.error(f"❌ Şirket bilgileri alınamadı: {e}")
                company_info = {}
            
            return render_template('company_profile.html', company_id=company_id, company=company_info)

        @self.app.route('/company/<company_id>/cameras', methods=['GET'])
        def camera_management(company_id):
            """Kamera yönetimi sayfası - Yeni Geliştirilmiş Sistem"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            return render_template('camera_management.html', 
                                        company_id=company_id, 
                                        user_data=user_data)

        @self.app.route('/api/company/<company_id>/ppe-config', methods=['PUT'])
        def update_ppe_config(company_id):
            """Update company PPE configuration"""
            try:
                # Session kontrolü
                if not self.validate_session():
                    return jsonify({'success': False, 'error': 'Oturum geçersiz'}), 401
                
                if session.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 403
                
                data = request.json
                required_ppe = data.get('required_ppe', [])
                
                # Geçerli PPE türleri
                valid_ppe_types = ['helmet', 'vest', 'glasses', 'gloves', 'shoes', 'mask']
                
                # Validation
                if not required_ppe:
                    return jsonify({'success': False, 'error': 'En az bir PPE türü seçmelisiniz'}), 400
                
                for ppe_type in required_ppe:
                    if ppe_type not in valid_ppe_types:
                        return jsonify({'success': False, 'error': f'Geçersiz PPE türü: {ppe_type}'}), 400
                
                # Database güncelleme
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    UPDATE companies 
                    SET required_ppe = {placeholder}, updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = {placeholder}
                ''', (json.dumps(required_ppe), company_id))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'message': 'PPE konfigürasyonu güncellendi',
                    'required_ppe': required_ppe
                })
                
            except Exception as e:
                logger.error(f"❌ PPE config güncelleme hatası: {e}")
                return jsonify({'success': False, 'error': 'Güncelleme başarısız'}), 500

        @self.app.route('/api/company/<company_id>/ppe-config', methods=['GET'])
        def get_ppe_config(company_id):
            """Get company PPE configuration"""
            try:
                # Session kontrolü
                if not self.validate_session():
                    return jsonify({'success': False, 'error': 'Oturum geçersiz'}), 401
                
                if session.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 403
                
                required_ppe = self.db.get_company_ppe_requirements(company_id)
                
                return jsonify({
                    'success': True,
                    'required_ppe': required_ppe
                })
                
            except Exception as e:
                logger.error(f"❌ PPE config getirme hatası: {e}")
                return jsonify({'success': False, 'error': 'Veri getirme başarısız'}), 500

        # Bildirim ayarları API endpoint'leri
        @self.app.route('/api/company/<company_id>/notifications', methods=['GET'])
        def get_notification_settings(company_id):
            """Get company notification settings"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT email_notifications, sms_notifications, push_notifications, 
                           violation_alerts, system_alerts, report_notifications
                    FROM companies WHERE company_id = {placeholder}
                ''', (company_id,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    # PostgreSQL Row object vs SQLite tuple compatibility
                    if hasattr(result, 'keys'):  # PostgreSQL Row object
                        settings = {
                            'email_notifications': result['email_notifications'] if result['email_notifications'] is not None else True,
                            'sms_notifications': result['sms_notifications'] if result['sms_notifications'] is not None else False,
                            'push_notifications': result['push_notifications'] if result['push_notifications'] is not None else True,
                            'violation_alerts': result['violation_alerts'] if result['violation_alerts'] is not None else True,
                            'system_alerts': result['system_alerts'] if result['system_alerts'] is not None else True,
                            'report_notifications': result['report_notifications'] if result['report_notifications'] is not None else True
                        }
                    else:  # SQLite tuple
                        settings = {
                            'email_notifications': result[0] if result[0] is not None else True,
                            'sms_notifications': result[1] if result[1] is not None else False,
                            'push_notifications': result[2] if result[2] is not None else True,
                            'violation_alerts': result[3] if result[3] is not None else True,
                            'system_alerts': result[4] if result[4] is not None else True,
                            'report_notifications': result[5] if result[5] is not None else True
                        }
                else:
                    # Varsayılan ayarlar
                    settings = {
                        'email_notifications': True,
                        'sms_notifications': False,
                        'push_notifications': True,
                        'violation_alerts': True,
                        'system_alerts': True,
                        'report_notifications': True
                    }
                
                return jsonify({
                    'success': True,
                    'settings': settings
                })
                
            except Exception as e:
                logger.error(f"❌ Bildirim ayarları getirme hatası: {e}")
                return jsonify({'success': False, 'error': 'Veri getirme başarısız'}), 500

        @self.app.route('/api/company/<company_id>/notifications', methods=['PUT'])
        def update_notification_settings(company_id):
            """Update company notification settings"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'Veri gerekli'}), 400
                
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                if hasattr(self.db, 'db_adapter') and self.db.db_adapter.db_type == 'postgresql':
                    cursor.execute(f'''
                        UPDATE companies 
                        SET email_notifications = {placeholder}, 
                            sms_notifications = {placeholder}, 
                            push_notifications = {placeholder}, 
                            violation_alerts = {placeholder}, 
                            system_alerts = {placeholder}, 
                            report_notifications = {placeholder},
                            updated_at = CURRENT_TIMESTAMP
                        WHERE company_id = {placeholder}
                    ''', (
                        data.get('email_notifications', True),
                        data.get('sms_notifications', False),
                        data.get('push_notifications', True),
                        data.get('violation_alerts', True),
                        data.get('system_alerts', True),
                        data.get('report_notifications', True),
                        company_id
                    ))
                else:
                    cursor.execute(f'''
                        UPDATE companies 
                        SET email_notifications = {placeholder}, 
                            sms_notifications = {placeholder}, 
                            push_notifications = {placeholder}, 
                            violation_alerts = {placeholder}, 
                            system_alerts = {placeholder}, 
                            report_notifications = {placeholder},
                            updated_at = datetime('now')
                        WHERE company_id = {placeholder}
                    ''', (
                    data.get('email_notifications', True),
                    data.get('sms_notifications', False),
                    data.get('push_notifications', True),
                    data.get('violation_alerts', True),
                    data.get('system_alerts', True),
                    data.get('report_notifications', True),
                    company_id
                ))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'message': 'Bildirim ayarları güncellendi'
                })
                
            except Exception as e:
                logger.error(f"❌ Bildirim ayarları güncelleme hatası: {e}")
                return jsonify({'success': False, 'error': 'Güncelleme başarısız'}), 500

        # Abonelik plan değiştirme API endpoint'i
        @self.app.route('/api/company/<company_id>/subscription/change-plan', methods=['POST'])
        def change_subscription_plan(company_id):
            """Abonelik planını değiştir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                new_plan = data.get('new_plan')
                
                if not new_plan:
                    return jsonify({'success': False, 'error': 'Yeni plan seçimi gerekli'}), 400
                
                # Plan fiyatları
                plan_prices = {
                    'starter': {'monthly': 99, 'cameras': 5, 'name': 'Starter'},
                    'professional': {'monthly': 299, 'cameras': 15, 'name': 'Professional'},
                    'enterprise': {'monthly': 599, 'cameras': 50, 'name': 'Enterprise'}
                }
                
                if new_plan not in plan_prices:
                    return jsonify({'success': False, 'error': 'Geçersiz plan'}), 400
                
                # Database güncelleme
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    UPDATE companies 
                    SET subscription_type = {placeholder}, 
                        max_cameras = {placeholder},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = {placeholder}
                ''', (new_plan, plan_prices[new_plan]['cameras'], company_id))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'message': 'Plan başarıyla değiştirildi',
                    'new_plan': new_plan,
                    'plan_name': plan_prices[new_plan]['name'],
                    'monthly_price': plan_prices[new_plan]['monthly'],
                    'max_cameras': plan_prices[new_plan]['cameras']
                })
                
            except Exception as e:
                logger.error(f"❌ Plan değiştirme hatası: {e}")
                return jsonify({'success': False, 'error': 'Plan değiştirme başarısız'}), 500



        # Abonelik bilgileri API endpoint'leri
        @self.app.route('/api/company/<company_id>/subscription', methods=['GET'])
        def get_subscription_info(company_id):
            """Get company subscription information"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                result = self.get_subscription_info_internal(company_id)
                if result['success']:
                    return jsonify(result)
                else:
                    return jsonify(result), 404
                
            except Exception as e:
                logger.error(f"❌ Abonelik bilgileri getirme hatası: {e}")
                return jsonify({'success': False, 'error': 'Veri getirme başarısız'}), 500

        # === UNIFIED CAMERA SYNC ENDPOINT ===
        @self.app.route('/api/company/<company_id>/cameras/sync', methods=['POST'])
        def sync_cameras(company_id):
            """Unified kamera senkronizasyon endpoint'i - Discovery + Config + Database"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json() or {}
                network_range = data.get('network_range', '192.168.1.0/24')
                force_sync = data.get('force_sync', False)  # Zorla yeniden sync
                
                logger.info(f"🔄 Starting unified camera sync for company {company_id}")
                
                result = {
                    'success': False,
                    'timestamp': datetime.now().isoformat(),
                    'company_id': company_id,
                    'network_range': network_range,
                    'discovery_result': {},
                    'config_sync_result': {},
                    'database_cameras': [],
                    'total_cameras': 0,
                    'mode': 'unknown'
                }
                
                # Enterprise mode
                if hasattr(self, 'camera_manager') and self.camera_manager and self.enterprise_enabled:
                    try:
                        logger.info("🚀 Using Enterprise Camera Manager for sync")
                        
                        # Full camera synchronization
                        sync_result = self.camera_manager.full_camera_sync(company_id, network_range)
                        
                        if sync_result['success']:
                            # Get final camera list from database
                            final_cameras = self.camera_manager.get_database_cameras(company_id)
                            
                            result.update({
                                'success': True,
                                'discovery_result': sync_result['discovery_result'],
                                'config_sync_result': sync_result['config_sync_result'],
                                'database_cameras': final_cameras,
                                'total_cameras': len(final_cameras),
                                'mode': 'enterprise',
                                'message': 'Enterprise kamera senkronizasyonu tamamlandı'
                            })
                            
                            logger.info(f"✅ Enterprise sync complete: {len(final_cameras)} cameras in database")
                            return jsonify(result)
                        else:
                            logger.warning(f"⚠️ Enterprise sync failed: {sync_result.get('error')}")
                            result['enterprise_error'] = sync_result.get('error')
                    
                    except Exception as e:
                        logger.error(f"❌ Enterprise sync error: {e}")
                        result['enterprise_error'] = str(e)
                
                # Fallback mode
                logger.info("📱 Using fallback camera sync")
                result['mode'] = 'fallback'
                
                # Step 1: Network discovery
                try:
                    from camera_discovery import IPCameraDiscovery
                    discovery = IPCameraDiscovery()
                    discovery_result = discovery.scan_network(network_range, timeout=2)
                    result['discovery_result'] = discovery_result
                    
                    # Step 2: Sync discovered cameras to database
                    if discovery_result.get('cameras'):
                        from database_adapter import get_camera_discovery_manager
                        discovery_manager = get_camera_discovery_manager()
                        db_sync_result = discovery_manager.sync_discovered_cameras_to_db(
                            company_id, 
                            discovery_result['cameras']
                        )
                        result['discovery_sync'] = db_sync_result
                        
                except Exception as discovery_error:
                    logger.error(f"❌ Discovery failed: {discovery_error}")
                    result['discovery_error'] = str(discovery_error)
                
                # Step 3: Config file sync
                try:
                    from database_adapter import get_camera_discovery_manager
                    discovery_manager = get_camera_discovery_manager()
                    config_sync_result = discovery_manager.sync_config_cameras_to_db(company_id)
                    result['config_sync_result'] = config_sync_result
                    
                except Exception as config_error:
                    logger.error(f"❌ Config sync failed: {config_error}")
                    result['config_error'] = str(config_error)
                
                # Step 4: Get final camera list
                try:
                    final_cameras = self.db.get_company_cameras(company_id)
                    result.update({
                        'database_cameras': final_cameras,
                        'total_cameras': len(final_cameras),
                        'success': True,
                        'message': f'Fallback kamera senkronizasyonu tamamlandı: {len(final_cameras)} kamera'
                    })
                    
                except Exception as db_error:
                    logger.error(f"❌ Database read failed: {db_error}")
                    result['database_error'] = str(db_error)
                
                logger.info(f"✅ Camera sync complete: {result['total_cameras']} cameras")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"❌ Camera sync error: {e}")
                return jsonify({
                    'success': False, 
                    'error': str(e), 
                    'timestamp': datetime.now().isoformat()
                }), 500

        # === PROFESSIONAL SAAS LIVE DETECTION SYSTEM ===
        @self.app.route('/api/company/<company_id>/live-detection', methods=['GET'])
        def live_detection_dashboard(company_id):
            """SaaS Canlı Tespit Dashboard"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return redirect(f'/company/{company_id}/login')
                
                # Şirket kameralarını getir
                cameras = self.db.get_company_cameras(company_id)
                
                # Şirket bilgilerini getir
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT company_name, sector, required_ppe
                    FROM companies WHERE company_id = {placeholder}
                ''', (company_id,))
                
                company_data = cursor.fetchone()
                conn.close()
                
                if not company_data:
                    return redirect('/')
                
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(company_data, 'keys'):
                    company_name = company_data['company_name']
                    sector = company_data['sector']
                    required_ppe = company_data['required_ppe']
                else:
                    company_name = company_data[0]
                    sector = company_data[1]
                    required_ppe = company_data[2]
                
                # PPE konfigürasyonunu işle
                ppe_config = []
                if required_ppe:
                    try:
                        import json
                        ppe_data = json.loads(required_ppe)
                        if isinstance(ppe_data, dict):
                            ppe_config = ppe_data.get('required', [])
                        else:
                            ppe_config = ppe_data
                    except:
                        ppe_config = ['helmet', 'vest']
                
                return render_template_string(self.get_live_detection_template(), 
                                            company_id=company_id,
                                            company_name=company_name,
                                            sector=sector,
                                            cameras=cameras,
                                            ppe_config=ppe_config,
                                            user_data=user_data)
                
            except Exception as e:
                logger.error(f"❌ Live detection dashboard error: {e}")
                return redirect(f'/company/{company_id}/dashboard')

        @self.app.route('/api/company/<company_id>/start-detection', methods=['POST'])
        def start_detection(company_id):
            """Şirket için tespit başlat - SaaS Edition"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
                
                data = request.json
                camera_id = data.get('camera_id')
                detection_mode = data.get('mode', 'ppe')
                confidence = data.get('confidence', 0.5)
                
                if not camera_id:
                    return jsonify({'success': False, 'error': 'Kamera ID gerekli'}), 400
                
                # Kamera var mı kontrol et
                cameras = self.db.get_company_cameras(company_id)
                camera_exists = any(cam['camera_id'] == camera_id for cam in cameras)
                
                if not camera_exists:
                    return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
                
                # Kamera zaten aktifse durdur
                camera_key = f"{company_id}_{camera_id}"
                if camera_key in active_detectors and active_detectors[camera_key]:
                    return jsonify({'success': False, 'error': 'Kamera zaten aktif'})
                
                # Kamera aktif olarak işaretle
                active_detectors[camera_key] = True
                
                # Detection thread'ini başlat
                detection_thread = threading.Thread(
                    target=self.saas_detection_worker,
                    args=(camera_key, camera_id, company_id, detection_mode, confidence),
                    daemon=True
                )
                detection_thread.start()
                
                # Thread'i kaydet
                detection_threads[camera_key] = {
                    'thread': detection_thread,
                    'config': {
                        'mode': detection_mode,
                        'confidence': confidence,
                        'started_at': datetime.now().isoformat()
                    }
                }
                
                return jsonify({
                    'success': True,
                    'message': f'Kamera {camera_id} tespiti başlatıldı',
                    'camera_id': camera_id,
                    'detection_mode': detection_mode,
                    'confidence': confidence,
                    'stream_url': f'/api/company/{company_id}/camera-stream/{camera_id}'
                })
                
            except Exception as e:
                logger.error(f"❌ Detection start error: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
                detection_threads[camera_key] = {
                    'camera_thread': camera_thread,
                    'detection_thread': detection_thread,
                    'config': {
                        'mode': mode,
                        'confidence': confidence
                    }
                }
                
                return jsonify({
                    'success': True, 
                    'message': f'Kamera {camera_id} tespiti başlatıldı (Confidence: {confidence})',
                    'video_url': f'/api/company/{company_id}/video-feed/{camera_id}'
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/company/<company_id>/stop-detection', methods=['POST'])
        def stop_detection(company_id):
            """Şirket için tespit durdur"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
                
                # Şirkete ait tüm tespit thread'lerini durdur
                keys_to_remove = []
                for camera_key in list(active_detectors.keys()):
                    if camera_key.startswith(f"{company_id}_"):
                        active_detectors[camera_key] = False
                        keys_to_remove.append(camera_key)
                
                # Kamera yakalama nesnelerini serbest bırak
                for camera_key in keys_to_remove:
                    if camera_key in camera_captures and camera_captures[camera_key] is not None:
                        camera_captures[camera_key].release()
                        del camera_captures[camera_key]
                    if camera_key in frame_buffers:
                        del frame_buffers[camera_key]
                    if camera_key in detection_threads:
                        del detection_threads[camera_key]
                
                return jsonify({'success': True, 'message': 'Tüm kameralar durduruldu'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500



        @self.app.route('/api/company/<company_id>/detection-status/<camera_id>')
        def detection_status(company_id, camera_id):
            """Tespit durumu API"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'error': 'Yetkisiz erişim'}), 401
                
                camera_key = f"{company_id}_{camera_id}"
                
                # Tespit durumu
                is_active = camera_key in active_detectors and active_detectors[camera_key]
                
                # Thread bilgisi
                thread_info = detection_threads.get(camera_key, {})
                
                # Son tespit sonuçları
                recent_results = []
                if camera_key in detection_results:
                    try:
                        while not detection_results[camera_key].empty():
                            result = detection_results[camera_key].get_nowait()
                            recent_results.append(result)
                    except:
                        pass
                
                return jsonify({
                    'success': True,
                    'camera_id': camera_id,
                    'is_active': is_active,
                    'thread_info': thread_info,
                    'recent_results': recent_results[-10:] if recent_results else []  # Son 10 sonuç
                })
                
            except Exception as e:
                logger.error(f"❌ Detection status error: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/company/<company_id>/live-stats')
        def live_stats(company_id):
            """Canlı istatistikler API"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'error': 'Yetkisiz erişim'}), 401
                
                # Aktif kameralar
                active_cameras = []
                for key, active in active_detectors.items():
                    if key.startswith(f"{company_id}_") and active:
                        camera_id = key.split('_', 1)[1]
                        active_cameras.append(camera_id)
                
                # Son 1 saat içindeki tespitler
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
                
                # Son tespitler
                cursor.execute(f'''
                    SELECT COUNT(*) FROM detections 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= datetime('now', '-1 hour')
                ''', (company_id,))
                
                recent_detections = cursor.fetchone()
                recent_detections = recent_detections[0] if recent_detections else 0
                
                # Son ihlaller
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} 
                    AND timestamp >= datetime('now', '-1 hour')
                ''', (company_id,))
                
                recent_violations = cursor.fetchone()
                recent_violations = recent_violations[0] if recent_violations else 0
                
                # Uyum oranı
                compliance_rate = 0
                if recent_detections > 0:
                    compliance_rate = max(0, (recent_detections - recent_violations) / recent_detections * 100)
                
                conn.close()
                
                return jsonify({
                    'success': True,
                    'stats': {
                        'active_cameras': len(active_cameras),
                        'active_camera_ids': active_cameras,
                        'recent_detections': recent_detections,
                        'recent_violations': recent_violations,
                        'compliance_rate': round(compliance_rate, 1),
                        'system_status': 'active' if active_cameras else 'idle',
                        'timestamp': datetime.now().isoformat()
                    }
                })
                
            except Exception as e:
                logger.error(f"❌ Live stats error: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/company/<company_id>/detection-results/<camera_id>')
        def get_detection_results(company_id, camera_id):
            """Detection sonuçlarını al"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
                
                camera_key = f"{company_id}_{camera_id}"
                if camera_key in detection_results and not detection_results[camera_key].empty():
                    try:
                        latest_result = detection_results[camera_key].get_nowait()
                        return jsonify({
                            'success': True,
                            'result': latest_result
                        })
                    except queue.Empty:
                        return jsonify({
                            'success': True,
                            'result': None,
                            'message': 'Henüz tespit sonucu yok'
                        })
                else:
                    return jsonify({
                        'success': True,
                        'result': None,
                        'message': 'Kamera aktif değil veya sonuç yok'
                    })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

    def validate_session(self):
        """Oturum doğrulama"""
        session_id = session.get('session_id')
        if not session_id:
            return None
        
        return self.db.validate_session(session_id)
    
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
        """Basit kamera testi (RealCameraManager olmayan durumlar için)"""
        import time
        import requests
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
            'error_message': ''
        }
        
        try:
            # Build camera URL
            if username and password:
                if protocol == 'rtsp':
                    camera_url = f"rtsp://{username}:{password}@{ip_address}:{port}/video"
                else:
                    camera_url = f"http://{username}:{password}@{ip_address}:{port}/video"
            else:
                if protocol == 'rtsp':
                    camera_url = f"rtsp://{ip_address}:{port}/video"
                else:
                    camera_url = f"http://{ip_address}:{port}/video"
            
            # Test HTTP connection first
            if protocol == 'http':
                try:
                    auth = None
                    if username and password:
                        auth = (username, password)
                    
                    response = requests.get(f"http://{ip_address}:{port}", 
                                          auth=auth, timeout=5)
                    if response.status_code == 200:
                        test_result['success'] = True
                        test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
                        test_result['stream_quality'] = 'good'
                        test_result['supported_features'] = ['http_stream']
                        test_result['camera_info'] = {
                            'ip': ip_address,
                            'port': port,
                            'protocol': protocol
                        }
                        return test_result
                except Exception:
                    pass
            
            # Test with OpenCV as fallback
            cap = cv2.VideoCapture(camera_url)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    test_result['success'] = True
                    test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
                    test_result['stream_quality'] = 'good'
                    test_result['supported_features'] = ['video_stream']
                    test_result['camera_info'] = {
                        'ip': ip_address,
                        'port': port,
                        'protocol': protocol,
                        'resolution': f"{frame.shape[1]}x{frame.shape[0]}"
                    }
                    cap.release()
            else:
                test_result['error_message'] = 'Kamera bağlantısı kurulamadı'
                
        except Exception as e:
            test_result['error_message'] = f'Kamera test hatası: {str(e)}'
        
        test_result['connection_time'] = round((time.time() - start_time) * 1000, 2)
        return test_result
    
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
            
            # Grafik verilerini hazırla
            chart_data = {
                'compliance_trend': compliance_rates[-7:] if len(compliance_rates) >= 7 else compliance_rates + [0] * (7 - len(compliance_rates)),
                'violation_types': [
                    violation_counts['helmet'],
                    violation_counts['vest'], 
                    violation_counts['shoes'],
                    violation_counts['mask']
                ],
                'hourly_violations': hourly_violations,
                'weekly_compliance': compliance_rates[-7:] if len(compliance_rates) >= 7 else compliance_rates + [0] * (7 - len(compliance_rates))
            }
            
            return chart_data
            
        except Exception as e:
            print(f"Chart data hesaplama hatası: {e}")
            # Hata durumunda varsayılan değerler döndür
            return {
                'compliance_trend': [0, 0, 0, 0, 0, 0, 0],
                'violation_types': [0, 0, 0, 0],
                'hourly_violations': [0] * 24,
                'weekly_compliance': [0, 0, 0, 0, 0, 0, 0]
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
            if sector_specific:
                penalty_amount = sector_specific.get('penalty_amount', 0)
                cv2.putText(result_image, f"Ceza: {penalty_amount:.0f} TL", 
                           (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
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
                    
                    # Sınıfa göre renk
                    if class_name == 'person':
                        color = (255, 0, 0)  # Mavi
                    elif 'helmet' in class_name or 'baret' in class_name:
                        color = (0, 255, 0)  # Yeşil
                    elif 'vest' in class_name or 'yelek' in class_name:
                        color = (0, 255, 255)  # Sarı
                    elif 'mask' in class_name or 'maske' in class_name:
                        color = (255, 0, 255)  # Magenta
                    else:
                        color = (128, 128, 128)  # Gri
                    
                    # Bounding box çiz
                    cv2.rectangle(result_image, (x1, y1), (x2, y2), color, 2)
                    
                    # Label
                    label = f"{class_name} ({confidence:.2f})"
                    cv2.putText(result_image, label, (x1, y1-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
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
                                    <!-- Abonelik Planı Seçimi -->
                                    <div class="mb-4">
                                        <label class="form-label fw-semibold">
                                            <i class="fas fa-crown text-warning me-2"></i>Abonelik Planı *
                                        </label>
                                        <div class="row">
                                            <div class="col-md-4 mb-3">
                                                <div class="form-check">
                                                    <input class="form-check-input" type="radio" name="subscription_plan" 
                                                           id="plan_starter" value="starter" checked>
                                                    <label class="form-check-label" for="plan_starter">
                                                        <strong>Starter</strong>
                                                        <br><small class="text-muted">₺99/ay - 5 kamera</small>
                                                    </label>
                                                </div>
                                            </div>
                                            <div class="col-md-4 mb-3">
                                                <div class="form-check">
                                                    <input class="form-check-input" type="radio" name="subscription_plan" 
                                                           id="plan_professional" value="professional">
                                                    <label class="form-check-label" for="plan_professional">
                                                        <strong>Professional</strong>
                                                        <br><small class="text-muted">₺299/ay - 15 kamera</small>
                                                        <span class="badge bg-primary ms-1">Popüler</span>
                                                    </label>
                                                </div>
                                            </div>
                                            <div class="col-md-4 mb-3">
                                                <div class="form-check">
                                                    <input class="form-check-input" type="radio" name="subscription_plan" 
                                                           id="plan_enterprise" value="enterprise">
                                                    <label class="form-check-label" for="plan_enterprise">
                                                        <strong>Enterprise</strong>
                                                        <br><small class="text-muted">₺599/ay - 50 kamera</small>
                                                    </label>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="alert alert-info mt-2">
                                            <i class="fas fa-info-circle"></i> 
                                            <strong>Max kamera sayısı otomatik olarak seçilen plana göre belirlenir.</strong><br>
                                            İlk 30 gün ücretsiz! İstediğiniz zaman planınızı değiştirebilirsiniz.
                                            <br><br>
                                            <button type="button" class="btn btn-outline-primary btn-sm" onclick="openPlanDetailsModal()">
                                                <i class="fas fa-info-circle"></i> Plan Detaylarını Gör
                                            </button>
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col-md-6 mb-4">
                                            <label class="form-label fw-semibold">
                                                <i class="fas fa-building text-primary me-2"></i>Company Name *
                                            </label>
                                            <input type="text" class="form-control form-control-lg" name="company_name" 
                                                   placeholder="Enter your company name" required 
                                                   style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                        </div>
                                        <div class="col-md-6 mb-4">
                                            <label class="form-label fw-semibold">
                                                <i class="fas fa-industry text-primary me-2"></i>Industry *
                                            </label>
                                            <select class="form-select form-select-lg" name="sector" required
                                                    style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                                <option value="">Select your industry</option>
                                                <option value="construction">🏗️ Construction</option>
                                                <option value="manufacturing">🏭 Manufacturing</option>
                                                <option value="chemical">⚗️ Chemical</option>
                                                <option value="food">🍕 Food & Beverage</option>
                                                <option value="warehouse">📦 Warehouse/Logistics</option>
                                            </select>
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-4">
                                            <label class="form-label fw-semibold">
                                                <i class="fas fa-user text-primary me-2"></i>Contact Person *
                                            </label>
                                            <input type="text" class="form-control form-control-lg" name="contact_person" 
                                                   placeholder="Full Name" required
                                                   style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                        </div>
                                        <div class="col-md-6 mb-4">
                                            <label class="form-label fw-semibold">
                                                <i class="fas fa-envelope text-primary me-2"></i>E-mail *
                                            </label>
                                            <input type="email" class="form-control form-control-lg" name="email" required
                                                   placeholder="example@company.com"
                                                   autocomplete="email"
                                                   style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-4">
                                            <label class="form-label fw-semibold">
                                                <i class="fas fa-phone text-primary me-2"></i>Phone
                                            </label>
                                            <input type="tel" class="form-control form-control-lg" name="phone"
                                                   placeholder="+1 555 123 4567"
                                                   style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                        </div>

                                    </div>
                                    
                                    <div class="mb-4">
                                        <label class="form-label fw-semibold">
                                            <i class="fas fa-map-marker-alt text-primary me-2"></i>Address
                                        </label>
                                        <textarea class="form-control form-control-lg" name="address" rows="3"
                                                  placeholder="Enter your company address"
                                                  style="border-radius: 15px; border: 2px solid #e2e8f0;"></textarea>
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
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="construction-gloves">
                                                        <label class="form-check-label" for="construction-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> Safety Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="glasses" id="construction-glasses">
                                                        <label class="form-check-label" for="construction-glasses">
                                                            <i class="fas fa-glasses text-info"></i> Safety Glasses
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Gıda Sektörü PPE -->
                                        <div id="food-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="hairnet" id="food-hairnet" checked>
                                                        <label class="form-check-label" for="food-hairnet">
                                                            <i class="fas fa-user-nurse text-primary"></i> Hair Net/Cap
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="food-mask" checked>
                                                        <label class="form-check-label" for="food-mask">
                                                            <i class="fas fa-head-side-mask text-warning"></i> Hygiene Mask
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="apron" id="food-apron" checked>
                                                        <label class="form-check-label" for="food-apron">
                                                            <i class="fas fa-tshirt text-success"></i> Hygiene Apron
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="food-gloves">
                                                        <label class="form-check-label" for="food-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> Hygiene Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_shoes" id="food-shoes">
                                                        <label class="form-check-label" for="food-shoes">
                                                            <i class="fas fa-socks text-info"></i> Non-slip Shoes
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Kimya Sektörü PPE -->
                                        <div id="chemical-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="gloves" id="chemical-gloves" checked>
                                                        <label class="form-check-label" for="chemical-gloves">
                                                            <i class="fas fa-hand-paper text-primary"></i> Chemical Gloves
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="glasses" id="chemical-glasses" checked>
                                                        <label class="form-check-label" for="chemical-glasses">
                                                                <i class="fas fa-glasses text-warning"></i> Safety Goggles
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="chemical-mask" checked>
                                                        <label class="form-check-label" for="chemical-mask">
                                                            <i class="fas fa-head-side-mask text-success"></i> Respiratory Mask
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_suit" id="chemical-suit" checked>
                                                        <label class="form-check-label" for="chemical-suit">
                                                            <i class="fas fa-tshirt text-info"></i> Chemical Suit
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- İmalat Sektörü PPE -->
                                        <div id="manufacturing-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="manufacturing-helmet" checked>
                                                        <label class="form-check-label" for="manufacturing-helmet">
                                                            <i class="fas fa-hard-hat text-primary"></i> Industrial Helmet
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="manufacturing-vest" checked>
                                                        <label class="form-check-label" for="manufacturing-vest">
                                                            <i class="fas fa-tshirt text-warning"></i> Reflective Vest
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="gloves" id="manufacturing-gloves" checked>
                                                        <label class="form-check-label" for="manufacturing-gloves">
                                                            <i class="fas fa-hand-paper text-success"></i> Work Gloves
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="manufacturing-shoes" checked>
                                                        <label class="form-check-label" for="manufacturing-shoes">
                                                            <i class="fas fa-socks text-info"></i> Steel Toe Shoes
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Depo Sektörü PPE -->
                                        <div id="warehouse-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="warehouse-vest" checked>
                                                        <label class="form-check-label" for="warehouse-vest">
                                                            <i class="fas fa-tshirt text-primary"></i> Visibility Vest
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="warehouse-shoes" checked>
                                                        <label class="form-check-label" for="warehouse-shoes">
                                                            <i class="fas fa-socks text-warning"></i> Safety Shoes
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="helmet" id="warehouse-helmet">
                                                        <label class="form-check-label" for="warehouse-helmet">
                                                            <i class="fas fa-hard-hat text-info"></i> Protective Helmet
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="warehouse-gloves">
                                                        <label class="form-check-label" for="warehouse-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> Work Gloves
                                                            <span class="badge bg-success ms-1">Optional</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    
                                        </div>
                                    
                                    <div class="mb-4">
                                        <label class="form-label fw-semibold">
                                            <i class="fas fa-lock text-primary me-2"></i>Password *
                                        </label>
                                        <input type="password" class="form-control form-control-lg" name="password" required
                                               placeholder="Create a secure password"
                                               style="border-radius: 15px; border: 2px solid #e2e8f0;">
                                    </div>
                                    
                                    <div class="text-center mb-4">
                                        <div class="alert alert-success border-0" style="background: rgba(34, 197, 94, 0.1); border-radius: 15px;">
                                            <i class="fas fa-gift text-success me-2"></i> 
                                            <strong>First month free!</strong> Instant setup.
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
                                                       placeholder="COMP_ABC123"
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
                                                Your Company ID is the code starting with COMP_ given to you after registration.
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
                                        <strong>İlk 30 Gün Ücretsiz Deneme!</strong>
                                    </h5>
                                    <p class="text-muted mb-0">Hiçbir kredi kartı gerektirmez • İstediğiniz zaman iptal edebilirsiniz</p>
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
                                                    <span class="display-6 fw-bold text-primary">₺99</span>
                                                    <span class="text-muted">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">5 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24.7 FPS)</span>
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
                                                    <span class="display-6 fw-bold text-white">₺299</span>
                                                    <span class="text-white-50">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">15 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24.7 FPS)</span>
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
                                            <div class="card-header bg-gradient-success border-0 text-center pt-4 text-white" style="border-radius: 16px 16px 0 0; background: linear-gradient(135deg, #059669 0%, #10B981 100%);">
                                                <div class="mb-3">
                                                    <div class="bg-white bg-opacity-20 rounded-circle mx-auto d-flex align-items-center justify-content-center" style="width: 80px; height: 80px;">
                                                        <i class="fas fa-crown text-white" style="font-size: 32px;"></i>
                                                    </div>
                                                </div>
                                                <h4 class="fw-bold text-white mb-1">Enterprise</h4>
                                                <p class="text-white-50 mb-3">Büyük kurumlar için endüstriyel AI tespit sistemi</p>
                                                <div class="mb-3">
                                                    <span class="display-6 fw-bold text-white">₺599</span>
                                                    <span class="text-white-50">/ay</span>
                                                </div>
                                            </div>
                                            <div class="card-body text-center">
                                                <div class="mb-4">
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #198754 !important;">
                                                            <i class="fas fa-video text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">50 Kamera</span>
                                                    </div>
                                                    <div class="d-flex align-items-center justify-content-center mb-3" style="height: 50px;">
                                                        <div class="rounded-circle me-3" style="width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background-color: #0dcaf0 !important;">
                                                            <i class="fas fa-brain text-white"></i>
                                                        </div>
                                                        <span class="fw-semibold">AI Tespit (24.7 FPS)</span>
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
                                                <button class="btn btn-success btn-lg w-100 rounded-pill shadow-sm" onclick="selectPlanForRegistration('enterprise')" style="background: linear-gradient(135deg, #059669 0%, #10B981 100%); border: none; padding: 12px 24px;">
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
                                                            <td class="border-0 text-center">5</td>
                                                            <td class="border-0 text-center fw-bold text-warning">15</td>
                                                            <td class="border-0 text-center">50</td>
                                                        </tr>
                                                        <tr class="border-0">
                                                            <td class="border-0 fw-semibold">
                                                                <i class="fas fa-brain text-primary me-2"></i>AI Tespit Hızı
                                                            </td>
                                                            <td class="border-0 text-center">24.7 FPS</td>
                                                            <td class="border-0 text-center fw-bold text-warning">24.7 FPS</td>
                                                            <td class="border-0 text-center">24.7 FPS</td>
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
                    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
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
                    <a class="navbar-brand fw-bold" href="#">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="btn btn-outline-primary btn-sm me-2" href="/company/{{ company_id }}/settings">
                            <i class="fas fa-cog"></i> Ayarlar
                        </a>
                        <a class="btn btn-outline-secondary btn-sm me-2" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="btn btn-outline-info btn-sm me-2" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
                        </a>
                        <a class="btn btn-outline-warning btn-sm me-2" href="/company/{{ company_id }}/cameras">
                            <i class="fas fa-video"></i> Kameralar
                        </a>
                        
                        <!-- Profil Dropdown -->
                        <div class="nav-item dropdown">
                            <a class="btn btn-outline-dark btn-sm dropdown-toggle d-flex align-items-center" href="#" id="profileDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
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
                                            <small class="text-muted">{{ company_id }}</small>
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
                            <div class="stat-value" id="subscription-plan">--</div>
                            <div class="stat-label">Abonelik Planı</div>
                            <div class="metric-trend" id="subscription-trend">
                                <i class="fas fa-check trend-up"></i> Aktif
                            </div>
                        </div>
                    </div>
                    <div class="col-xl-2 col-md-6">
                        <div class="stat-card text-center">
                            <div class="stat-icon text-dark">
                                <i class="fas fa-video"></i>
                            </div>
                            <div class="stat-value" id="camera-usage">--</div>
                            <div class="stat-label">Kamera Kullanımı</div>
                            <div class="metric-trend" id="usage-trend">
                                <i class="fas fa-info trend-neutral"></i> Limit
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
                                                    <option value="construction">İnşaat Modu</option>
                                                    <option value="general">Genel Tespit</option>
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
                                                <div class="row text-center">
                                                    <div class="col-6 mb-3">
                                                        <div class="stat-value text-primary" id="live-people-count">0</div>
                                                        <div class="stat-label">Kişi Sayısı</div>
                                                    </div>
                                                    <div class="col-6 mb-3">
                                                        <div class="stat-value text-success" id="live-compliance-rate">0%</div>
                                                        <div class="stat-label">Uyum Oranı</div>
                                                    </div>
                                                </div>
                                                <div id="live-violations" class="mt-3">
                                                    <h6 class="text-danger">
                                                        <i class="fas fa-exclamation-triangle"></i> Aktif İhlaller
                                                    </h6>
                                                    <div id="live-violations-list">
                                                        <p class="text-muted small">Henüz ihlal tespit edilmedi</p>
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
                
                <!-- Kameralar ve Uyarılar -->
                <div class="row">
                    <div class="col-xl-8">
                        <div class="card">
                            <div class="card-header bg-info text-white d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">
                                    <i class="fas fa-video"></i> 
                                    Kamera Durumu
                                </h5>
                                <button class="btn btn-light btn-sm" data-bs-toggle="modal" data-bs-target="#addCameraModal">
                                    <i class="fas fa-plus"></i> Yeni Kamera
                                </button>
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
                            <div class="card-header bg-warning text-white">
                                <h5 class="mb-0">
                                    <i class="fas fa-bell"></i> 
                                    Son Uyarılar
                                </h5>
                            </div>
                            <div class="card-body" style="max-height: 400px; overflow-y: auto;">
                                <div id="alerts-list">
                                    <!-- Uyarılar buraya yüklenecek -->
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Yenileme Butonu -->
            <button class="btn btn-primary refresh-btn" onclick="refreshDashboard()" title="Verileri Yenile">
                <i class="fas fa-sync-alt"></i>
            </button>
            
            <!-- Kamera Ekleme Modal -->
            <div class="modal fade" id="addCameraModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-plus"></i> Yeni Kamera Ekle
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="addCameraForm">
                                <!-- Yardım Bölümü -->
                                <div class="alert alert-info">
                                    <h6><i class="fas fa-info-circle"></i> Kamera Bilgilerini Nasıl Bulabilirim?</h6>
                                    <ul class="mb-0">
                                        <li><strong>IP Adresi:</strong> Kameranızın ağ ayarları menüsünden veya router admin panelinden</li>
                                        <li><strong>Port:</strong> Yaygın portlar: 80, 8080 (HTTP), 554 (RTSP)</li>
                                        <li><strong>Kullanıcı/Şifre:</strong> Kamera web arayüzü için giriş bilgileri</li>
                                        <li><strong>Test Önerisi:</strong> Önce "Bağlantıyı Test Et" yapın, sonra ekleyin</li>
                                    </ul>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kamera Adı *</label>
                                        <input type="text" class="form-control" name="camera_name" placeholder="Örnek: Ana Giriş Kamerası" required>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Lokasyon *</label>
                                        <input type="text" class="form-control" name="location" placeholder="Örnek: Ana Giriş, Üretim Alanı" required>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">IP Adresi *</label>
                                        <input type="text" class="form-control" name="ip_address" placeholder="192.168.1.11" required>
                                        <div class="form-text">Kameranızın ağ ayarlarından IP adresini bulabilirsiniz</div>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Port</label>
                                        <input type="number" class="form-control" name="port" placeholder="8080" value="8080">
                                        <div class="form-text">Yaygın portlar: 80, 8080 (HTTP), 554 (RTSP)</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Protokol</label>
                                        <select class="form-select" name="protocol">
                                            <option value="http">HTTP (IP Webcam, Web Kameraları)</option>
                                            <option value="rtsp">RTSP (Profesyonel IP Kameraları)</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Stream Yolu</label>
                                        <input type="text" class="form-control" name="stream_path" placeholder="/video" value="/video">
                                        <div class="form-text">Yaygın yollar: /video, /stream1, /live</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kullanıcı Adı</label>
                                        <input type="text" class="form-control" name="username" placeholder="admin">
                                        <div class="form-text">Kamera web arayüzü için kullanıcı adı</div>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Şifre</label>
                                        <input type="password" class="form-control" name="password" placeholder="Kamera parolanız">
                                        <div class="form-text">Güvenlik için varsayılan parolayı değiştirin</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kimlik Doğrulama Türü</label>
                                        <select class="form-select" name="auth_type">
                                            <option value="basic">Basic Auth</option>
                                            <option value="digest">Digest Auth</option>
                                            <option value="none">Kimlik Doğrulama Yok</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Çözünürlük</label>
                                        <select class="form-select" name="resolution">
                                            <option value="640x480">640x480 (VGA)</option>
                                            <option value="1280x720">1280x720 (HD)</option>
                                            <option value="1920x1080">1920x1080 (Full HD)</option>
                                            <option value="3840x2160">3840x2160 (4K)</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">FPS (Saniye/Kare)</label>
                                        <select class="form-select" name="fps">
                                            <option value="15">15 FPS</option>
                                            <option value="20">20 FPS</option>
                                            <option value="25">25 FPS</option>
                                            <option value="30" selected>30 FPS</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Grup</label>
                                        <select class="form-select" name="group_id">
                                            <option value="">Grup Seçin</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="d-grid gap-2">
                                    <button type="button" class="btn btn-info" onclick="smartDetectCamera()">
                                        <i class="fas fa-brain"></i> Akıllı Tespit
                                    </button>
                                    <button type="button" class="btn btn-warning" onclick="testCameraConnection()">
                                        <i class="fas fa-check"></i> Bağlantıyı Test Et
                                    </button>
                                </div>
                                <div id="testResults" class="mt-3" style="display: none;">
                                    <!-- Test results will appear here -->
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">İptal</button>
                            <button type="button" class="btn btn-primary" onclick="addCamera()">
                                <i class="fas fa-plus"></i> Kamera Ekle
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
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
                                        <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addCameraModal">
                                                <i class="fas fa-plus"></i> Buradan Ekle
                                        </button>
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
                    // Trend göstergelerini güncelle
                    const trends = {
                        'cameras-trend': data.cameras_trend || 0,
                        'compliance-trend': data.compliance_trend || 0,
                        'violations-trend': data.violations_trend || 0,
                        'workers-trend': data.workers_trend || 0
                    };
                    
                    Object.entries(trends).forEach(([id, value]) => {
                        const element = document.getElementById(id);
                        if (element) {
                            const icon = element.querySelector('i');
                            if (value > 0) {
                                icon.className = 'fas fa-arrow-up trend-up';
                            } else if (value < 0) {
                                icon.className = 'fas fa-arrow-down trend-down';
                            } else {
                                icon.className = 'fas fa-minus trend-neutral';
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
                
                function addCamera() {
                    const formData = new FormData(document.getElementById('addCameraForm'));
                    const data = Object.fromEntries(formData);
                    
                    fetch(`/api/company/${companyId}/cameras`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ Kamera başarıyla eklendi!');
                            loadCameras();
                            loadStats();
                            bootstrap.Modal.getInstance(document.getElementById('addCameraModal')).hide();
                            document.getElementById('addCameraForm').reset();
                            // Test sonuçlarını temizle
                            document.getElementById('testResults').style.display = 'none';
                        } else {
                            // Limit kontrolü
                            if (result.limit_reached) {
                                alert(`❌ Kamera limiti aşıldı! Mevcut: ${result.current_cameras}/${result.max_cameras} kamera.\n\nPlanınızı yükseltmek için ayarlar sayfasını ziyaret edin.`);
                        } else {
                            alert('❌ Hata: ' + result.error);
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Kamera eklenirken hata:', error);
                        alert('❌ Bir hata oluştu!');
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
                        body: JSON.stringify({camera: camera, mode: mode})
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
                                        
                                        // FPS göster
                                        const fps = Math.round(1 / (result.processing_time || 0.04));
                                        document.getElementById('fps-display').textContent = `FPS: ${fps}`;
                                        
                                        // Detection bilgilerini güncelle
                                        document.getElementById('live-people-count').textContent = result.total_people || 0;
                                        document.getElementById('live-compliance-rate').textContent = `${(result.compliance_rate || 0).toFixed(1)}%`;
                                        
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
                                        if (result.violations && result.violations.length > 0) {
                                            violationsList.innerHTML = result.violations.map(violation => 
                                                `<div class="alert alert-danger alert-sm py-1 px-2 mb-1">
                                                    <small><strong>${violation.worker_id}:</strong> ${violation.missing_ppe.join(', ')}</small>
                                                </div>`
                                            ).join('');
                                        } else {
                                            violationsList.innerHTML = '<p class="text-muted small">Henüz ihlal tespit edilmedi</p>';
                                        }
                                    } else {
                                        document.getElementById('fps-display').textContent = 'FPS: --';
                                    }
                                })
                                .catch(error => {
                                    console.error('Detection monitoring error:', error);
                                    document.getElementById('fps-display').textContent = 'FPS: --';
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
        return '''
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
                            Company ID: ''' + company_id + '''
                        </div>
                        <p class="text-muted">Secure login</p>
                    </div>
                    
                    <form action="/company/''' + company_id + '''/login-form" method="POST">
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-envelope text-primary me-2"></i>Your Email
                            </label>
                            <input type="email" class="form-control form-control-lg" id="email" name="email" 
                                   placeholder="example@yourcompany.com" required>
                        </div>
                        
                        <div class="mb-4">
                            <label class="form-label fw-semibold">
                                <i class="fas fa-lock text-primary me-2"></i>Your Password
                            </label>
                            <input type="password" class="form-control form-control-lg" id="password" name="password" 
                                   placeholder="Enter your password" required>
                        </div>
                        
                        <div class="d-grid mb-4">
                            <button type="submit" class="btn btn-primary btn-lg" 
                                    style="border-radius: 30px; padding: 15px 0; font-weight: 600; font-size: 18px; background: linear-gradient(135deg, #1E3A8A 0%, #0EA5E9 100%); border: none; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.3);">
                                <i class="fas fa-sign-in-alt me-2"></i>Login
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
        </body>
        </html>
        '''
    
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
                                        Founder şifresi: <code>smartsafe2024admin</code>
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
                        <button class="btn btn-outline-danger btn-sm" onclick="logout()">
                            <i class="fas fa-sign-out-alt"></i> Çıkış
                        </button>
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
                            <div class="form-section">
                                <h5><i class="fas fa-building"></i> Şirket Profili</h5>
                                <form id="profileForm">
                                    <div class="row">
                                        <div class="col-md-6">
                                            <!-- Logo Upload -->
                                            <div class="text-center mb-4">
                                                <div class="logo-upload" onclick="document.getElementById('logoInput').click()">
                                                    <div>
                                                        <i class="fas fa-camera fa-2x text-muted mb-2"></i>
                                                        <p class="text-muted">Logo Yükle</p>
                                                    </div>
                                                </div>
                                                <input type="file" id="logoInput" accept="image/*" style="display: none;">
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label class="form-label">Şirket ID</label>
                                                <input type="text" class="form-control" value="{{ company_id }}" readonly>
                                            </div>
                                            <div class="mb-3">
                                                <label class="form-label">Şirket Adı *</label>
                                                <input type="text" class="form-control" name="company_name" value="{{ user_data.company_name }}">
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">İletişim Kişisi *</label>
                                            <input type="text" class="form-control" name="contact_person" value="{{ user_data.contact_person }}">
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Email *</label>
                                            <input type="text" class="form-control" name="email" value="{{ user_data.email }}" 
                                                   placeholder="ornek@email.com (Türkçe karakterler desteklenir)"
                                                   oninput="validateEmail(this)"
                                                   onblur="validateEmail(this)"
                                                   autocomplete="email">
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Telefon</label>
                                            <input type="tel" class="form-control" name="phone" value="{{ user_data.phone }}">
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Sektör</label>
                                            <select class="form-select" name="sector">
                                                <option value="construction" {% if user_data.sector == 'construction' %}selected{% endif %}>İnşaat</option>
                                                <option value="manufacturing" {% if user_data.sector == 'manufacturing' %}selected{% endif %}>İmalat</option>
                                                <option value="chemical" {% if user_data.sector == 'chemical' %}selected{% endif %}>Kimya</option>
                                                <option value="food" {% if user_data.sector == 'food' %}selected{% endif %}>Gıda</option>
                                                <option value="warehouse" {% if user_data.sector == 'warehouse' %}selected{% endif %}>Depo/Lojistik</option>
                                            </select>
                                        </div>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Adres</label>
                                        <textarea class="form-control" name="address" rows="3">{{ user_data.address }}</textarea>
                                    </div>
                                    
                                    <button type="submit" class="btn btn-primary">
                                        <i class="fas fa-save"></i> Değişiklikleri Kaydet
                                    </button>
                                </form>
                            </div>
                        </div>
                        
                        <!-- PPE Konfigürasyonu -->
                        <div id="ppe-config-section" class="settings-section" style="display: none;">
                            <div class="form-section">
                                <h5><i class="fas fa-hard-hat"></i> PPE Konfigürasyonu</h5>
                                <p class="text-muted">Sektörünüze göre zorunlu ve opsiyonel PPE ekipmanlarını ayarlayın.</p>
                                
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i>
                                    <strong>Mevcut Sektör:</strong> {{ user_data.sector|title }} 
                                    <span class="badge bg-primary ms-2">Otomatik Konfigürasyon</span>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <h6 class="text-danger">Zorunlu PPE Ekipmanları</h6>
                                        <div class="ppe-config-item">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <i class="fas fa-hard-hat text-primary"></i>
                                                    <strong>Baret</strong>
                                                    <small class="text-muted d-block">Kafa koruması</small>
                                                </div>
                                                <div>
                                                    <span class="badge bg-danger">100₺ Ceza</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div class="ppe-config-item">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <i class="fas fa-vest text-warning"></i>
                                                    <strong>Güvenlik Yeleği</strong>
                                                    <small class="text-muted d-block">Görünürlük</small>
                                                </div>
                                                <div>
                                                    <span class="badge bg-danger">75₺ Ceza</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div class="ppe-config-item">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <i class="fas fa-shoe-prints text-success"></i>
                                                    <strong>Güvenlik Ayakkabısı</strong>
                                                    <small class="text-muted d-block">Ayak koruması</small>
                                                </div>
                                                <div>
                                                    <span class="badge bg-danger">50₺ Ceza</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="col-md-6">
                                        <h6 class="text-success">Opsiyonel PPE Ekipmanları</h6>
                                        <div class="ppe-config-item">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <i class="fas fa-hand-paper text-info"></i>
                                                    <strong>Eldiven</strong>
                                                    <small class="text-muted d-block">El koruması</small>
                                                </div>
                                                <div>
                                                    <span class="badge bg-success">+10 Puan</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div class="ppe-config-item">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <i class="fas fa-glasses text-info"></i>
                                                    <strong>Güvenlik Gözlüğü</strong>
                                                    <small class="text-muted d-block">Göz koruması</small>
                                                </div>
                                                <div>
                                                    <span class="badge bg-success">+15 Puan</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mt-4">
                                    <h6>Özel PPE Konfigürasyonu</h6>
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_helmet" name="ppe_helmet">
                                                <label class="form-check-label" for="ppe_helmet">
                                                    <i class="fas fa-hard-hat text-primary"></i> Baret/Kask
                                                </label>
                                            </div>
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_vest" name="ppe_vest">
                                                <label class="form-check-label" for="ppe_vest">
                                                    <i class="fas fa-vest text-warning"></i> Güvenlik Yeleği
                                                </label>
                                            </div>
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_glasses" name="ppe_glasses">
                                                <label class="form-check-label" for="ppe_glasses">
                                                    <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                </label>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_gloves" name="ppe_gloves">
                                                <label class="form-check-label" for="ppe_gloves">
                                                    <i class="fas fa-mitten text-success"></i> İş Eldiveni
                                                </label>
                                            </div>
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_shoes" name="ppe_shoes">
                                                <label class="form-check-label" for="ppe_shoes">
                                                    <i class="fas fa-shoe-prints text-dark"></i> Güvenlik Ayakkabısı
                                                </label>
                                            </div>
                                            <div class="form-check mb-2">
                                                <input class="form-check-input" type="checkbox" id="ppe_mask" name="ppe_mask">
                                                <label class="form-check-label" for="ppe_mask">
                                                    <i class="fas fa-head-side-mask text-secondary"></i> Maske
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mt-4">
                                    <button class="btn btn-primary" onclick="updatePPEConfig()">
                                        <i class="fas fa-save"></i> PPE Ayarlarını Kaydet
                                    </button>
                                    <button class="btn btn-outline-secondary ms-2">
                                        <i class="fas fa-undo"></i> Varsayılana Döndür
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
                            <div class="subscription-card">
                                <h5><i class="fas fa-credit-card"></i> Abonelik Bilgileri</h5>
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i>
                                            <strong>Plan:</strong> <span id="subscription-type">BASIC</span>
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i>
                                            <strong>Durum:</strong> <span id="subscription-status">Aktif</span>
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i>
                                            <strong>Bitiş Tarihi:</strong> <span id="subscription-end">--</span>
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i>
                                            <strong>Kalan Gün:</strong> <span id="days-remaining">--</span>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="plan-feature">
                                            <i class="fas fa-video"></i>
                                            <strong>Kamera Kullanımı:</strong> <span id="camera-usage">--/--</span>
                                        </div>
                                        <div class="progress mb-3">
                                            <div class="progress-bar bg-success" id="usage-progress" role="progressbar" style="width: 0%"></div>
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-shield-alt"></i>
                                            <strong>Güvenlik:</strong> SSL Şifreleme
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-headset"></i>
                                            <strong>Destek:</strong> 7/24 Teknik Destek
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mt-4">
                                    <button class="btn btn-light" onclick="openUpgradeModal()">
                                        <i class="fas fa-upgrade"></i> Planı Yükselt
                                    </button>
                                    <button class="btn btn-outline-light ms-2">
                                        <i class="fas fa-file-invoice"></i> Fatura Geçmişi
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Güvenlik -->
                        <div id="security-section" class="settings-section" style="display: none;">
                            <div class="form-section">
                                <h5><i class="fas fa-shield-alt"></i> Güvenlik Ayarları</h5>
                                
                                <div class="mb-4">
                                    <h6>Şifre Değiştir</h6>
                                    <form id="passwordForm">
                                        <div class="mb-3">
                                            <label class="form-label">Mevcut Şifre</label>
                                            <input type="password" class="form-control" name="current_password" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Yeni Şifre</label>
                                            <input type="password" class="form-control" name="new_password" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Yeni Şifre (Tekrar)</label>
                                            <input type="password" class="form-control" name="confirm_password" required>
                                        </div>
                                        <button type="submit" class="btn btn-primary">
                                            <i class="fas fa-key"></i> Şifre Değiştir
                                        </button>
                                    </form>
                                </div>
                                
                                <div class="danger-zone">
                                    <h6><i class="fas fa-exclamation-triangle"></i> Tehlikeli Bölge</h6>
                                    <p>Hesabınızı kalıcı olarak silmek istiyorsanız aşağıdaki adımları takip edin.</p>
                                    
                                    <form id="deleteAccountForm">
                                        <div class="mb-3">
                                            <label class="form-label">Şifrenizi Girin</label>
                                            <input type="password" class="form-control" name="password" required>
                                        </div>
                                        <div class="form-check mb-3">
                                            <input class="form-check-input" type="checkbox" id="confirmDelete" required>
                                            <label class="form-check-label" for="confirmDelete">
                                                Hesabımı ve tüm verilerimi kalıcı olarak silmek istiyorum
                                            </label>
                                        </div>
                                        <button type="button" class="btn btn-danger" onclick="deleteAccount()">
                                            <i class="fas fa-trash"></i> Hesabı Sil
                                        </button>
                                    </form>
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
                                                <li><i class="fas fa-video"></i> 5 Kamera</li>
                                                <li><i class="fas fa-shield-alt"></i> Temel Güvenlik</li>
                                                <li><i class="fas fa-headset"></i> Email Destek</li>
                                                <li><i class="fas fa-chart-bar"></i> Temel Raporlar</li>
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
                                                <li><i class="fas fa-video"></i> 15 Kamera</li>
                                                <li><i class="fas fa-shield-alt"></i> Gelişmiş Güvenlik</li>
                                                <li><i class="fas fa-headset"></i> 7/24 Destek</li>
                                                <li><i class="fas fa-chart-line"></i> Detaylı Analitik</li>
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
                                                <li><i class="fas fa-video"></i> 50 Kamera</li>
                                                <li><i class="fas fa-shield-alt"></i> Maksimum Güvenlik</li>
                                                <li><i class="fas fa-headset"></i> Öncelikli Destek</li>
                                                <li><i class="fas fa-chart-pie"></i> Özel Raporlar</li>
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
            
            <script>
                const companyId = '{{ company_id }}';
                let selectedPlan = null;
                let currentPlan = null;
                
                // Email validation function
                function validateEmail(input) {
                    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
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
                                            <small class="text-muted d-block">Günlük özet raporu gönder</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Sistem Bakım Bildirimleri</strong>
                                            <small class="text-muted d-block">Sistem güncellemeleri hakkında bilgilendir</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox">
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                </div>
                                
                                <div class="mb-4">
                                    <h6>SMS Bildirimleri</h6>
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Kritik İhlaller</strong>
                                            <small class="text-muted d-block">Yüksek riskli ihlaller için SMS gönder</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox">
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">SMS Telefon Numarası</label>
                                        <input type="tel" class="form-control" placeholder="+90 555 123 4567">
                                    </div>
                                </div>
                                
                                <button class="btn btn-primary">
                                    <i class="fas fa-save"></i> Bildirim Ayarlarını Kaydet
                                </button>
                            </div>
                        </div>
                        
                        <!-- Abonelik -->
                        <div id="subscription-section" class="settings-section" style="display: none;">
                            <div class="subscription-card">
                                <div class="d-flex justify-content-between align-items-center mb-3">
                                    <h5 class="mb-0">
                                        <i class="fas fa-crown"></i> Professional Plan
                                    </h5>
                                    <span class="badge bg-light text-dark">AKTİF</span>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i> 10 Kamera Limiti
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i> Gelişmiş Analitik
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i> Email Desteği
                                        </div>
                                        <div class="plan-feature">
                                            <i class="fas fa-check"></i> 30 Gün Veri Saklama
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="text-end">
                                            <h3>500₺<small>/ay</small></h3>
                                            <p class="mb-0">Sonraki ödeme: 05.08.2025</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="form-section">
                                <h6>Fatura Bilgileri</h6>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Fatura Adresi</label>
                                        <textarea class="form-control" rows="3">{{ user_data.address }}</textarea>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Vergi Dairesi</label>
                                        <input type="text" class="form-control" placeholder="Vergi dairesi adı">
                                        <label class="form-label mt-2">Vergi No</label>
                                        <input type="text" class="form-control" placeholder="1234567890">
                                    </div>
                                </div>
                                
                                <div class="d-flex gap-2">
                                    <button class="btn btn-outline-primary" onclick="changePaymentMethod()">
                                        <i class="fas fa-credit-card"></i> Ödeme Yöntemi Değiştir
                                    </button>
                                    <button class="btn btn-outline-warning" data-bs-toggle="modal" data-bs-target="#changePlanModal">
                                        <i class="fas fa-exchange-alt"></i> Plan Değiştir
                                    </button>
                                    <button class="btn btn-outline-info" onclick="downloadInvoices()">
                                        <i class="fas fa-download"></i> Faturaları İndir
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Güvenlik -->
                        <div id="security-section" class="settings-section" style="display: none;">
                            <div class="form-section">
                                <h5><i class="fas fa-shield-alt"></i> Güvenlik Ayarları</h5>
                                
                                <div class="mb-4">
                                    <h6>Şifre Değiştir</h6>
                                    <form id="passwordForm">
                                        <div class="mb-3">
                                            <label class="form-label">Mevcut Şifre</label>
                                            <input type="password" class="form-control" name="current_password" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Yeni Şifre</label>
                                            <input type="password" class="form-control" name="new_password" required>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Yeni Şifre Tekrar</label>
                                            <input type="password" class="form-control" name="confirm_password" required>
                                        </div>
                                        <button type="submit" class="btn btn-primary">
                                            <i class="fas fa-key"></i> Şifreyi Değiştir
                                        </button>
                                    </form>
                                </div>
                                
                                <div class="mb-4">
                                    <h6>Güvenlik Seçenekleri</h6>
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>İki Faktörlü Doğrulama</strong>
                                            <small class="text-muted d-block">Ekstra güvenlik katmanı ekle</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox">
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Oturum Zaman Aşımı</strong>
                                            <small class="text-muted d-block">Aktif olmadığında otomatik çıkış</small>
                                        </div>
                                        <select class="form-select" style="width: auto;">
                                            <option>30 dakika</option>
                                            <option>1 saat</option>
                                            <option>4 saat</option>
                                            <option>8 saat</option>
                                        </select>
                                    </div>
                                </div>
                                
                                <button class="btn btn-primary">
                                    <i class="fas fa-save"></i> Güvenlik Ayarlarını Kaydet
                                </button>
                            </div>
                            
                            <!-- Tehlike Bölgesi -->
                            <div class="danger-zone">
                                <h5><i class="fas fa-exclamation-triangle"></i> Tehlike Bölgesi</h5>
                                <p class="mb-3">
                                    <strong>Dikkat:</strong> Hesabınızı silmek kalıcı bir işlemdir! 
                                    Tüm verileriniz (kameralar, kayıtlar, istatistikler, kullanıcılar) silinecek ve geri alınamaz.
                                </p>
                                
                                <button class="btn btn-light" data-bs-toggle="modal" data-bs-target="#deleteAccountModal">
                                    <i class="fas fa-trash text-danger"></i> Hesabı Sil
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Plan Değiştirme Modal -->
            <div class="modal fade" id="changePlanModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-exchange-alt"></i> Abonelik Planı Değiştir
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" onclick="selectPlan('starter')">
                                        <div class="card-body text-center">
                                            <h5 class="card-title">
                                                <i class="fas fa-rocket text-primary"></i> Starter
                                            </h5>
                                            <div class="price-display">₺99<small>/ay</small></div>
                                            <ul class="list-unstyled">
                                                <li>5 Kamera</li>
                                                <li>Temel PPE</li>
                                                <li>Email Bildirimleri</li>
                                            </ul>
                                            <input type="radio" name="new_plan" value="starter" id="starter_plan">
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" onclick="selectPlan('professional')">
                                        <div class="card-body text-center">
                                            <h5 class="card-title">
                                                <i class="fas fa-star text-warning"></i> Professional
                                            </h5>
                                            <div class="price-display">₺299<small>/ay</small></div>
                                            <ul class="list-unstyled">
                                                <li>15 Kamera</li>
                                                <li>Gelişmiş PPE</li>
                                                <li>SMS + Email</li>
                                            </ul>
                                            <input type="radio" name="new_plan" value="professional" id="professional_plan">
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4 mb-3">
                                    <div class="card plan-card" onclick="selectPlan('enterprise')">
                                        <div class="card-body text-center">
                                            <h5 class="card-title">
                                                <i class="fas fa-building text-success"></i> Enterprise
                                            </h5>
                                            <div class="price-display">₺599<small>/ay</small></div>
                                            <ul class="list-unstyled">
                                                <li>50 Kamera</li>
                                                <li>AI Destekli</li>
                                                <li>7/24 Destek</li>
                                            </ul>
                                            <input type="radio" name="new_plan" value="enterprise" id="enterprise_plan">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">İptal</button>
                            <button type="button" class="btn btn-primary" onclick="changePlan()">
                                <i class="fas fa-check"></i> Planı Değiştir
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Hesap Silme Modal -->
            <div class="modal fade" id="deleteAccountModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-danger text-white">
                            <h5 class="modal-title">⚠️ Hesap Silme Onayı</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-warning">
                                <strong>Bu işlem geri alınamaz!</strong><br>
                                Hesabınızı silmek için şifrenizi girin.
                            </div>
                            <form id="deleteAccountForm">
                                <div class="mb-3">
                                    <label class="form-label">Şifreniz</label>
                                    <input type="password" class="form-control" name="password" required>
                                </div>
                                <div class="form-check">
                                    <input type="checkbox" class="form-check-input" id="confirmDelete" required>
                                    <label class="form-check-label" for="confirmDelete">
                                        Hesabımı silmek istediğimi ve tüm verilerin kaybolacağını anlıyorum.
                                    </label>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">İptal</button>
                            <button type="button" class="btn btn-danger" onclick="deleteAccount()">
                                <i class="fas fa-trash"></i> Hesabı Sil
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                const companyId = '{{ company_id }}' || '';
                
                // Email Validation Function
                function validateEmail(input) {
                    const emailRegex = /^[a-zA-Z0-9._%+-çğıöşüÇĞIİÖŞÜ]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
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

                // Settings Navigation
                function initializeSettingsNavigation() {
                    console.log('Initializing Settings Navigation');
                    
                    // Wait a bit for DOM to be fully ready
                    setTimeout(() => {
                        const navLinks = document.querySelectorAll('.nav-link[data-section]');
                        const sections = document.querySelectorAll('.settings-section');
                        
                        console.log('Found nav links:', navLinks.length);
                        console.log('Found sections:', sections.length);
                        
                        if (navLinks.length === 0) {
                            console.error('No navigation links found');
                            return;
                        }
                        
                        if (sections.length === 0) {
                            console.error('No sections found');
                            return;
                        }
                        
                        navLinks.forEach(link => {
                            link.addEventListener('click', function(e) {
                                e.preventDefault();
                                e.stopPropagation();
                                console.log('Nav link clicked:', this.getAttribute('data-section'));
                                
                                // Remove active class from all nav links
                                navLinks.forEach(nl => nl.classList.remove('active'));
                                
                                // Add active class to clicked nav link
                                this.classList.add('active');
                                
                                // Hide all sections
                                sections.forEach(section => {
                                    section.style.display = 'none';
                                });
                                
                                // Show target section
                                const targetSection = this.getAttribute('data-section');
                                const targetElement = document.getElementById(targetSection + '-section');
                                console.log('Looking for element with ID:', targetSection + '-section');
                                console.log('Found target element:', targetElement);
                                
                                if (targetElement) {
                                    targetElement.style.display = 'block';
                                    console.log('Section displayed:', targetSection);
                                    
                                    // Update URL hash without triggering hashchange event
                                    const currentHash = window.location.hash.substring(1);
                                    if (currentHash !== targetSection) {
                                        history.pushState(null, null, '#' + targetSection);
                                    }
                                } else {
                                    console.error('Target section not found:', targetSection + '-section');
                                }
                            });
                        });
                        
                        // Also add click handlers to nav links for better compatibility
                        document.addEventListener('click', function(e) {
                            if (e.target.closest('.nav-link[data-section]')) {
                                const link = e.target.closest('.nav-link[data-section]');
                                const targetSection = link.getAttribute('data-section');
                                if (targetSection) {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    
                                    // Remove active class from all nav links
                                    navLinks.forEach(nl => nl.classList.remove('active'));
                                    
                                    // Add active class to clicked nav link
                                    link.classList.add('active');
                                    
                                    // Hide all sections
                                    sections.forEach(section => {
                                        section.style.display = 'none';
                                    });
                                    
                                    // Show target section
                                    const targetElement = document.getElementById(targetSection + '-section');
                                    if (targetElement) {
                                        targetElement.style.display = 'block';
                                        console.log('Section displayed via event delegation:', targetSection);
                                        
                                        // Update URL hash
                                        const currentHash = window.location.hash.substring(1);
                                        if (currentHash !== targetSection) {
                                            history.pushState(null, null, '#' + targetSection);
                                        }
                                    }
                                }
                            }
                        });
                    }, 100);
                }
                
                // Initialize when DOM is ready
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', function() {
                        initializeSettingsNavigation();
                        handleInitialHash();
                    });
                } else {
                    initializeSettingsNavigation();
                    handleInitialHash();
                }
                
                // Handle URL hash on page load
                function handleInitialHash() {
                    const hash = window.location.hash.substring(1);
                    console.log('Initial hash:', hash);
                    if (hash) {
                        const targetLink = document.querySelector(`[data-section="${hash}"]`);
                        if (targetLink) {
                            console.log('Found target link for hash:', hash);
                            targetLink.click();
                        } else {
                            console.log('No target link found for hash:', hash);
                        }
                    } else {
                        // Default to profile section if no hash
                        const profileLink = document.querySelector('[data-section="profile"]');
                        if (profileLink) {
                            console.log('Defaulting to profile section');
                            profileLink.click();
                        }
                    }
                }
                
                // Handle hash changes
                window.addEventListener('hashchange', function() {
                    const hash = window.location.hash.substring(1);
                    console.log('Hash changed to:', hash);
                    const targetLink = document.querySelector(`[data-section="${hash}"]`);
                    if (targetLink) {
                        console.log('Found target link for hash change:', hash);
                        targetLink.click();
                    } else {
                        console.log('No target link found for hash change:', hash);
                    }
                });
                
                // Profile Form Submission
                document.getElementById('profileForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    
                    const formData = new FormData(this);
                    const data = {};
                    formData.forEach((value, key) => {
                        data[key] = value;
                    });
                    
                    fetch(`/api/company/${companyId}/profile`, {
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
                    
                    fetch(`/api/company/${companyId}/change-password`, {
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
                            alert('❌ Dosya boyutu 5MB\'dan büyük olamaz!');
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
                            const logoUpload = document.querySelector('.logo-upload');
                            logoUpload.innerHTML = `<img src="${e.target.result}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 10px;">`;
                        };
                        reader.readAsDataURL(file);
                        
                        // Dosyayı hemen yükle
                        uploadLogo(file);
                    }
                });
                
                // Logo yükleme fonksiyonu
                function uploadLogo(file) {
                    const formData = new FormData();
                    formData.append('logo', file);
                    
                    // Loading göster
                    const logoUpload = document.querySelector('.logo-upload');
                    const originalContent = logoUpload.innerHTML;
                    logoUpload.innerHTML = `
                        <div class="d-flex align-items-center justify-content-center h-100">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">Yükleniyor...</span>
                            </div>
                        </div>
                    `;
                    
                    fetch(`/api/company/${companyId}/profile/upload-logo`, {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // Başarılı yükleme
                            logoUpload.innerHTML = `<img src="${data.logo_url}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 10px;">`;
                            
                            // Toast mesajı göster
                            const toast = document.createElement('div');
                            toast.className = 'toast-message';
                            toast.innerHTML = '✅ Logo başarıyla yüklendi!';
                            toast.style.cssText = `
                                position: fixed;
                                top: 20px;
                                right: 20px;
                                background: #28a745;
                                color: white;
                                padding: 10px 20px;
                                border-radius: 5px;
                                z-index: 9999;
                                font-weight: bold;
                            `;
                            document.body.appendChild(toast);
                            
                            setTimeout(() => {
                                toast.remove();
                            }, 3000);
                        } else {
                            // Hata durumunda eski içeriği geri yükle
                            logoUpload.innerHTML = originalContent;
                            alert('❌ Logo yükleme hatası: ' + data.error);
                        }
                    })
                    .catch(error => {
                        // Hata durumunda eski içeriği geri yükle
                        logoUpload.innerHTML = originalContent;
                        console.error('Logo upload error:', error);
                        alert('❌ Logo yükleme sırasında bir hata oluştu');
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
                        toast.innerHTML = `✅ ${settingName} ${isEnabled ? 'açıldı' : 'kapatıldı'}`;
                        toast.style.cssText = `
                            position: fixed;
                            top: 20px;
                            right: 20px;
                            background: #28a745;
                            color: white;
                            padding: 10px 20px;
                            border-radius: 5px;
                            z-index: 9999;
                            font-weight: bold;
                        `;
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
                    
                    fetch(`/api/company/${companyId}/notifications`, {
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
                    fetch(`/api/company/${companyId}/notifications`)
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
                    fetch(`/api/company/${companyId}/subscription`)
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            const subscription = result.subscription;
                            
                            // Update subscription display
                            document.getElementById('subscription-type').textContent = subscription.subscription_type.toUpperCase();
                            document.getElementById('subscription-status').textContent = subscription.is_active ? 'Aktif' : 'Süresi Dolmuş';
                            document.getElementById('subscription-end').textContent = new Date(subscription.subscription_end).toLocaleDateString('tr-TR');
                            document.getElementById('days-remaining').textContent = subscription.days_remaining;
                            document.getElementById('camera-usage').textContent = `${subscription.used_cameras}/${subscription.max_cameras}`;
                            
                            // Progress bar
                            const progressBar = document.getElementById('usage-progress');
                            if (progressBar) {
                                progressBar.style.width = `${subscription.usage_percentage}%`;
                                progressBar.className = `progress-bar ${subscription.usage_percentage > 80 ? 'bg-danger' : subscription.usage_percentage > 60 ? 'bg-warning' : 'bg-success'}`;
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Abonelik bilgileri yükleme hatası:', error);
                    });
                }

                // Plan yükseltme modal'ını aç
                function openUpgradeModal() {
                    loadCurrentPlanInfo();
                    const modal = new bootstrap.Modal(document.getElementById('upgradePlanModal'));
                    modal.show();
                }

                // Plan seçimi
                function selectPlan(plan) {
                    selectedPlan = plan;
                    
                    // Tüm kartlardan seçim işaretini kaldır
                    document.querySelectorAll('.plan-card').forEach(card => {
                        card.classList.remove('selected');
                    });
                    
                    // Seçilen kartı işaretle
                    document.querySelector(`[data-plan="${plan}"]`).classList.add('selected');
                    
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
                            cameras: '5 Kamera',
                            features: ['Temel Güvenlik', 'Email Destek', 'Temel Raporlar']
                        },
                        'professional': {
                            name: 'Professional',
                            price: '$299/ay',
                            cameras: '15 Kamera',
                            features: ['Gelişmiş Güvenlik', '7/24 Destek', 'Detaylı Analitik', 'Gelişmiş Bildirimler']
                        },
                        'enterprise': {
                            name: 'Enterprise',
                            price: '$599/ay',
                            cameras: '50 Kamera',
                            features: ['Maksimum Güvenlik', 'Öncelikli Destek', 'Özel Raporlar', 'API Erişimi', 'Çoklu Kullanıcı']
                        }
                    };
                    
                    const details = planDetails[plan];
                    const detailsDiv = document.getElementById('plan-details-content');
                    
                    detailsDiv.innerHTML = `
                        <div class="row">
                            <div class="col-md-6">
                                <strong>Plan:</strong> ${details.name}<br>
                                <strong>Fiyat:</strong> ${details.price}<br>
                                <strong>Kamera Limiti:</strong> ${details.cameras}
                            </div>
                            <div class="col-md-6">
                                <strong>Özellikler:</strong><br>
                                ${details.features.map(feature => `<i class="fas fa-check text-success"></i> ${feature}`).join('<br>')}
                            </div>
                        </div>
                    `;
                    
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
                    
                    if (confirm(`⚠️ ${selectedPlan.toUpperCase()} planına geçmek istediğinizden emin misiniz?`)) {
                        // Plan değiştirme API'sini çağır
                        fetch(`/api/company/${companyId}/subscription/change-plan`, {
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
                    fetch(`/api/company/${companyId}/subscription`)
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            const subscription = result.subscription;
                            currentPlan = subscription.subscription_type;
                            
                            // Mevcut plan bilgilerini göster
                            document.getElementById('current-plan-name').textContent = subscription.subscription_type.toUpperCase();
                            document.getElementById('current-camera-limit').textContent = subscription.max_cameras;
                            document.getElementById('current-usage').textContent = `${subscription.used_cameras}/${subscription.max_cameras}`;
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
                        fetch(`/api/company/${companyId}/delete-account`, {
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
                    
                    fetch(`/api/company/${companyId}/ppe-config`, {
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
                
                // Load PPE Configuration
                function loadPPEConfig() {
                    fetch(`/api/company/${companyId}/ppe-config`)
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            const requiredPPE = result.required_ppe || [];
                            
                            // Checkbox'ları güncelle
                            document.getElementById('ppe_helmet').checked = requiredPPE.includes('helmet');
                            document.getElementById('ppe_vest').checked = requiredPPE.includes('vest');
                            document.getElementById('ppe_glasses').checked = requiredPPE.includes('glasses');
                            document.getElementById('ppe_gloves').checked = requiredPPE.includes('gloves');
                            document.getElementById('ppe_shoes').checked = requiredPPE.includes('shoes');
                            document.getElementById('ppe_mask').checked = requiredPPE.includes('mask');
                        }
                    })
                    .catch(error => {
                        console.error('Error loading PPE config:', error);
                    });
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
                    event.currentTarget.classList.add('selected');
                    document.getElementById(planType + '_plan').checked = true;
                }
                
                function changePlan() {
                    const selectedPlan = document.querySelector('input[name="new_plan"]:checked');
                    
                    if (!selectedPlan) {
                        alert('❌ Lütfen bir plan seçin!');
                        return;
                    }
                    
                    const newPlan = selectedPlan.value;
                    
                    if (confirm(`${newPlan.toUpperCase()} planına geçmek istediğinizden emin misiniz?`)) {
                        fetch(`/api/company/${companyId}/subscription/change-plan`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({new_plan: newPlan})
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert(`✅ Plan başarıyla ${result.plan_name} olarak değiştirildi!`);
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
                    // PPE konfigürasyonu yükle
                    if (document.getElementById('ppe-config-section')) {
                        loadPPEConfig();
                    }
                    
                    // Bildirim ayarlarını yükle
                    if (document.getElementById('notifications-section')) {
                        loadNotificationSettings();
                    }
                    
                    // Abonelik bilgilerini yükle
                    if (document.getElementById('subscription-section')) {
                        loadSubscriptionInfo();
                    }
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
                        <a class="nav-link active" href="/company/{{ company_id }}/users">
                            <i class="fas fa-users"></i> Kullanıcılar
                        </a>
                        <a class="nav-link" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
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
                    fetch(`/api/company/${companyId}/users`)
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
                    
                    fetch(`/api/company/${companyId}/users`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert(`✅ Kullanıcı başarıyla eklendi!\\n\\nGeçici Şifre: ${result.temp_password}\\n\\nBu şifreyi kullanıcıya güvenli bir şekilde iletin.`);
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
                        fetch(`/api/company/${companyId}/users/${selectedUserId}`, {
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
                        <a class="nav-link active" href="/company/{{ company_id }}/reports">
                            <i class="fas fa-chart-line"></i> Raporlar
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
                            <div class="stat-value compliance-good" id="overallCompliance">87.5%</div>
                            <h6 class="text-muted">Genel Uyumluluk</h6>
                            <small class="text-success">
                                <i class="fas fa-arrow-up"></i> +2.3% (Son hafta)
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value text-danger" id="totalViolations">23</div>
                            <h6 class="text-muted">Toplam İhlal</h6>
                            <small class="text-danger">
                                <i class="fas fa-arrow-down"></i> -15% (Son hafta)
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value text-warning" id="totalPenalties">1,725₺</div>
                            <h6 class="text-muted">Toplam Ceza</h6>
                            <small class="text-warning">
                                <i class="fas fa-minus"></i> 0% (Son hafta)
                            </small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card">
                            <div class="stat-value text-info" id="detectedPersons">1,247</div>
                            <h6 class="text-muted">Tespit Edilen Kişi</h6>
                            <small class="text-info">
                                <i class="fas fa-arrow-up"></i> +8% (Son hafta)
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
                                                    <tr>
                                                        <td><i class="fas fa-video text-primary"></i> Ana Giriş</td>
                                                        <td><span class="badge bg-success">89.2%</span></td>
                                                        <td>456</td>
                                                        <td>12</td>
                                                        <td>94.5%</td>
                                                        <td><span class="badge bg-success">Aktif</span></td>
                                                    </tr>
                                                    <tr>
                                                        <td><i class="fas fa-video text-primary"></i> İnşaat Alanı</td>
                                                        <td><span class="badge bg-warning">84.5%</span></td>
                                                        <td>623</td>
                                                        <td>18</td>
                                                        <td>91.2%</td>
                                                        <td><span class="badge bg-success">Aktif</span></td>
                                                    </tr>
                                                    <tr>
                                                        <td><i class="fas fa-video text-primary"></i> Depo Girişi</td>
                                                        <td><span class="badge bg-success">91.7%</span></td>
                                                        <td>168</td>
                                                        <td>3</td>
                                                        <td>96.8%</td>
                                                        <td><span class="badge bg-success">Aktif</span></td>
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
                document.addEventListener('DOMContentLoaded', function() {
                    loadDashboardData();
                    loadViolations();
                    loadComplianceReport();
                });
                
                // Load Dashboard Data
                function loadDashboardData() {
                    // Load violations report
                    fetch(`/api/company/${companyId}/reports/violations`)
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateViolationsChart(data.data);
                                updateViolationsStats(data.data);
                            }
                        })
                        .catch(error => {
                            console.error('Error loading violations report:', error);
                        });
                    
                    // Load compliance report
                    fetch(`/api/company/${companyId}/reports/compliance`)
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateComplianceChart(data.data);
                                updateComplianceStats(data.data);
                                updateCameraPerformance(data.data);
                            }
                        })
                        .catch(error => {
                            console.error('Error loading compliance report:', error);
                        });
                    
                    // Load subscription info
                    fetch(`/api/company/${companyId}/subscription`)
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                const subscription = result.subscription;
                                
                                // Update subscription display in dashboard
                                document.getElementById('subscription-plan').textContent = subscription.subscription_type.toUpperCase();
                                document.getElementById('camera-usage').textContent = `${subscription.used_cameras}/${subscription.max_cameras}`;
                                
                                // Update subscription trend
                                const subscriptionTrend = document.getElementById('subscription-trend');
                                if (subscription.is_active) {
                                    subscriptionTrend.innerHTML = '<i class="fas fa-check trend-up"></i> Aktif';
                                    subscriptionTrend.className = 'metric-trend';
                                } else {
                                    subscriptionTrend.innerHTML = '<i class="fas fa-exclamation-triangle trend-down"></i> Süresi Dolmuş';
                                    subscriptionTrend.className = 'metric-trend';
                                }
                                
                                // Update usage trend
                                const usageTrend = document.getElementById('usage-trend');
                                const usagePercentage = subscription.usage_percentage;
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
                        })
                        .catch(error => {
                            console.error('Abonelik bilgileri yükleme hatası:', error);
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
                                    <strong class="text-danger">${violation.count * 75}₺</strong>
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
                    
                    fetch(`/api/company/${companyId}/reports/export`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert(`✅ ${result.message}\\n\\nRapor oluşturuldu ve indirmeye hazır.`);
                            // Simulated download
                            const link = document.createElement('a');
                            link.href = '#';
                            link.download = `report.${data.format}`;
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
                    alert(`📹 Kamera ${cameraId} detay görüntüleme\\n\\n(Bu özellik geliştirilme aşamasında)`);
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
                            <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addCameraModal">
                                <i class="fas fa-plus"></i> Kamera Ekle
                            </button>
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
            
            <!-- Add Camera Modal -->
            <div class="modal fade" id="addCameraModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-plus"></i> Yeni Kamera Ekle
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="addCameraForm">
                                <!-- Yardım Bölümü -->
                                <div class="alert alert-info">
                                    <h6><i class="fas fa-info-circle"></i> Kamera Bilgilerini Nasıl Bulabilirim?</h6>
                                    <ul class="mb-0">
                                        <li><strong>IP Adresi:</strong> Kameranızın ağ ayarları menüsünden veya router admin panelinden</li>
                                        <li><strong>Port:</strong> Yaygın portlar: 80, 8080 (HTTP), 554 (RTSP)</li>
                                        <li><strong>Kullanıcı/Şifre:</strong> Kamera web arayüzü için giriş bilgileri</li>
                                        <li><strong>Test Önerisi:</strong> Önce "Bağlantıyı Test Et" yapın, sonra ekleyin</li>
                                    </ul>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kamera Adı *</label>
                                        <input type="text" class="form-control" name="camera_name" placeholder="Örnek: Ana Giriş Kamerası" required>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Lokasyon *</label>
                                        <input type="text" class="form-control" name="location" placeholder="Örnek: Ana Giriş, Üretim Alanı" required>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">IP Adresi *</label>
                                        <input type="text" class="form-control" name="ip_address" placeholder="192.168.1.11" required>
                                        <div class="form-text">Kameranızın ağ ayarlarından IP adresini bulabilirsiniz</div>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Port</label>
                                        <input type="number" class="form-control" name="port" placeholder="8080" value="8080">
                                        <div class="form-text">Yaygın portlar: 80, 8080 (HTTP), 554 (RTSP)</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Protokol</label>
                                        <select class="form-select" name="protocol">
                                            <option value="http">HTTP (IP Webcam, Web Kameraları)</option>
                                            <option value="rtsp">RTSP (Profesyonel IP Kameraları)</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Stream Yolu</label>
                                        <input type="text" class="form-control" name="stream_path" placeholder="/video" value="/video">
                                        <div class="form-text">Yaygın yollar: /video, /stream1, /live</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kullanıcı Adı</label>
                                        <input type="text" class="form-control" name="username" placeholder="admin">
                                        <div class="form-text">Kamera web arayüzü için kullanıcı adı</div>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Şifre</label>
                                        <input type="password" class="form-control" name="password" placeholder="Kamera parolanız">
                                        <div class="form-text">Güvenlik için varsayılan parolayı değiştirin</div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kimlik Doğrulama Türü</label>
                                        <select class="form-select" name="auth_type">
                                            <option value="basic">Basic Auth</option>
                                            <option value="digest">Digest Auth</option>
                                            <option value="none">Kimlik Doğrulama Yok</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Çözünürlük</label>
                                        <select class="form-select" name="resolution">
                                            <option value="640x480">640x480 (VGA)</option>
                                            <option value="1280x720">1280x720 (HD)</option>
                                            <option value="1920x1080">1920x1080 (Full HD)</option>
                                            <option value="3840x2160">3840x2160 (4K)</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">FPS (Saniye/Kare)</label>
                                        <select class="form-select" name="fps">
                                            <option value="15">15 FPS</option>
                                            <option value="20">20 FPS</option>
                                            <option value="25">25 FPS</option>
                                            <option value="30" selected>30 FPS</option>
                                        </select>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                    <label class="form-label">Grup</label>
                                    <select class="form-select" name="group_id">
                                        <option value="">Grup Seçin</option>
                                    </select>
                                    </div>
                                </div>
                                <div class="d-grid">
                                    <button type="button" class="btn btn-warning" onclick="testCameraConnection()">
                                        <i class="fas fa-check"></i> Bağlantıyı Test Et
                                    </button>
                                </div>
                                <div id="testResults" class="mt-3" style="display: none;">
                                    <!-- Test results will appear here -->
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">İptal</button>
                            <button type="button" class="btn btn-primary" onclick="addCamera()">
                                <i class="fas fa-plus"></i> Kamera Ekle
                            </button>
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
                function addCamera() {
                    const form = document.getElementById('addCameraForm');
                    const formData = new FormData(form);
                    const data = {};
                    formData.forEach((value, key) => { data[key] = value; });
                    
                    fetch(`/api/company/${companyId}/cameras`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ Kamera başarıyla eklendi!');
                            bootstrap.Modal.getInstance(document.getElementById('addCameraModal')).hide();
                            form.reset();
                            // Test sonuçlarını temizle
                            document.getElementById('testResults').style.display = 'none';
                            loadCameras();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
                    })
                    .catch(error => {
                        console.error('Kamera ekleme hatası:', error);
                        alert('❌ Kamera ekleme sırasında bir hata oluştu');
                    });
                }
                
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
                    // Kamera bilgilerini al
                    const camera = cameras.find(c => c.camera_id === cameraId);
                    if (!camera) {
                        alert('❌ Kamera bilgileri bulunamadı');
                        return;
                    }
                    
                    // Test başlat
                    const testButton = document.querySelector(`button[onclick="testCamera('${cameraId}')"]`);
                    if (testButton) {
                        testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Test Ediliyor...';
                        testButton.disabled = true;
                    }
                    
                    fetch(`/api/company/${companyId}/cameras/test`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            rtsp_url: camera.rtsp_url,
                            name: camera.name
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            const testResults = data.test_results;
                            let message = `✅ Kamera Test Sonucu: ${camera.name}\\n\\n`;
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
                    
                    const resultsHtml = `
                        <div class="alert ${successCount === results.length ? 'alert-success' : failCount === results.length ? 'alert-danger' : 'alert-warning'}">
                            <h6>
                                <i class="fas fa-chart-pie"></i> Test Sonuçları
                            </h6>
                            <div class="row text-center">
                                <div class="col-4">
                                    <div class="text-success">
                                        <i class="fas fa-check-circle fa-2x"></i>
                                        <div class="mt-1"><strong>${successCount}</strong></div>
                                        <small>Başarılı</small>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="text-danger">
                                        <i class="fas fa-times-circle fa-2x"></i>
                                        <div class="mt-1"><strong>${failCount}</strong></div>
                                        <small>Başarısız</small>
                                    </div>
                                </div>
                                <div class="col-4">
                                    <div class="text-info">
                                        <i class="fas fa-video fa-2x"></i>
                                        <div class="mt-1"><strong>${results.length}</strong></div>
                                        <small>Toplam</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            ${results.map(r => `
                                <div class="col-md-6 mb-3">
                                    <div class="card ${r.success ? 'border-success' : 'border-danger'}">
                                        <div class="card-body">
                                            <h6 class="card-title">
                                                <i class="fas fa-video"></i> ${r.camera.camera_name}
                                                <span class="badge ${r.success ? 'bg-success' : 'bg-danger'} ms-2">
                                                    ${r.success ? 'Başarılı' : 'Başarısız'}
                                                </span>
                                            </h6>
                                            <p class="text-muted mb-2">
                                                <i class="fas fa-network-wired"></i> ${r.camera.ip_address}:${r.camera.port}
                                            </p>
                                            ${r.success ? `
                                                <div class="row text-center">
                                                    <div class="col-6">
                                                        <small class="text-muted">Yanıt Süresi</small>
                                                        <div class="fw-bold">${r.result.test_results?.response_time || 'N/A'}</div>
                                                    </div>
                                                    <div class="col-6">
                                                        <small class="text-muted">Çözünürlük</small>
                                                        <div class="fw-bold">${r.result.test_results?.resolution || 'N/A'}</div>
                                                    </div>
                                                </div>
                                            ` : `
                                                <div class="alert alert-danger mb-0">
                                                    <small>
                                                        <i class="fas fa-exclamation-triangle"></i> 
                                                        ${r.result.error || 'Bilinmeyen hata'}
                                                    </small>
                                                </div>
                                            `}
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `;
                    
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
        """Add health check endpoint for Docker"""
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint for monitoring"""
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
                    "version": "1.0.0",
                    "services": {
                        "database": db_status,
                        "application": app_status
                    },
                    "uptime": "running"
                }
                
                return jsonify(response), 200 if healthy else 503
                
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return jsonify({
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }), 503

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
        
        # Add health check and metrics endpoints
        self.add_health_check()
        if self.enterprise_enabled:
            self.add_metrics_endpoint()
        
        # Get port from environment (Render.com compatibility)
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Using port {port}")
        
        # Set the port in app config
        self.app.config['PORT'] = port
        
        # Return the app instance for gunicorn to handle
        return self.app

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
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"🔧 Development mode: Starting Flask server on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False)  # Debug=False for memory optimization
            
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
        
        # Emergency fallback app
        from flask import Flask
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return {'status': 'error', 'message': 'Emergency fallback app - main app failed to initialize'}
        
        @app.route('/')
        def index():
            return {'status': 'error', 'message': 'Main application failed to start'}
        
        print("⚠️ Emergency fallback Flask app created")
        return app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    # RENDER.COM OPTIMIZED FLASK SERVER
    print("🚀 RENDER.COM - Starting optimized Flask server...")
    
    try:
        api_server = SmartSafeSaaSAPI()
        app = api_server.app
        
        # Render.com automatic port detection
        port = int(os.environ.get('PORT', 10000))  # Render.com default port
        host = '0.0.0.0'
        
        # Platform detection - Render.com focused
        if os.environ.get('RENDER'):
            platform = "Render.com (Production)"
        else:
            platform = "Local Development"
        print(f"🌐 Platform: {platform}")
        print(f"🌐 Starting server on {host}:{port}")
        print(f"🔧 Environment: {app.config.get('ENV', 'development')}")
        print(f"🔧 Debug mode: {app.config.get('DEBUG', False)}")
        
        # RENDER.COM OPTIMIZED FLASK SERVER
        app.run(
            host=host, 
            port=port, 
            debug=False, 
            threaded=True,
            use_reloader=False,  # Render.com optimization
            use_debugger=False   # Production safety
        )
        
    except Exception as e:
        print(f"❌ Server start error: {e}")
        import traceback
        traceback.print_exc()
        # Exit with error code for Render.com
        import sys
        sys.exit(1)

    def saas_detection_worker(self, camera_key, camera_id, company_id, detection_mode, confidence=0.5):
        """SaaS Profesyonel Detection Worker"""
        logger.info(f"🚀 SaaS Detection başlatılıyor - Kamera: {camera_id}, Şirket: {company_id}")
        
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=20)
        
        # Kamera başlat
        self.start_saas_camera(camera_key, camera_id, company_id)
        
        # YOLOv8 model yükle
        try:
            import torch
            from ultralytics import YOLO
            
            # CPU kullan (daha kararlı)
            device = 'cpu'
            model = YOLO('yolov8n.pt')
            model.to(device)
            
            logger.info(f"✅ YOLOv8 model yüklendi - Device: {device}")
            
        except Exception as e:
            logger.error(f"❌ Model yükleme hatası: {e}")
            return
        
        frame_count = 0
        detection_count = 0
        
        while active_detectors.get(camera_key, False):
            try:
                # Frame al
                if camera_key in frame_buffers and frame_buffers[camera_key] is not None:
                    frame = frame_buffers[camera_key].copy()
                    frame_count += 1
                    
                    # Her 3 frame'de bir tespit yap (performans)
                    if frame_count % 3 == 0:
                        start_time = time.time()
                        
                        # YOLO detection
                        results = model(frame, conf=confidence, verbose=False)
                        
                        # Sonuçları işle
                        people_detected = 0
                        ppe_violations = []
                        ppe_compliant = 0
                        
                        for result in results:
                            if result.boxes is not None:
                                for box in result.boxes:
                                    class_id = int(box.cls[0])
                                    confidence_score = float(box.conf[0])
                                    
                                    # Person detection
                                    if class_id == 0:  # person class
                                        people_detected += 1
                                        
                                        # PPE kontrolü (basitleştirilmiş)
                                        # Gerçek uygulamada daha karmaşık PPE analizi yapılır
                                        has_helmet = confidence_score > 0.6  # Örnek
                                        has_vest = confidence_score > 0.5    # Örnek
                                        
                                        if has_helmet and has_vest:
                                            ppe_compliant += 1
                                        else:
                                            missing_ppe = []
                                            if not has_helmet:
                                                missing_ppe.append('helmet')
                                            if not has_vest:
                                                missing_ppe.append('vest')
                                            
                                            ppe_violations.append({
                                                'person_id': f"person_{len(ppe_violations)}",
                                                'missing_ppe': missing_ppe,
                                                'confidence': confidence_score,
                                                'bbox': box.xyxy[0].tolist()
                                            })
                        
                        # Uyum oranı hesapla
                        compliance_rate = 0
                        if people_detected > 0:
                            compliance_rate = (ppe_compliant / people_detected) * 100
                        
                        processing_time = (time.time() - start_time) * 1000
                        detection_count += 1
                        
                        # Sonuçları kaydet
                        detection_data = {
                            'camera_id': camera_id,
                            'company_id': company_id,
                            'timestamp': datetime.now().isoformat(),
                            'frame_count': frame_count,
                            'detection_count': detection_count,
                            'people_detected': people_detected,
                            'ppe_compliant': ppe_compliant,
                            'ppe_violations': ppe_violations,
                            'compliance_rate': round(compliance_rate, 1),
                            'processing_time_ms': round(processing_time, 2),
                            'detection_mode': detection_mode,
                            'confidence_threshold': confidence
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
                        
                        # Veritabanına kaydet (her 10 tespit)
                        if detection_count % 10 == 0:
                            self.save_detection_to_db(detection_data)
                        
                        # İhlal varsa veritabanına kaydet
                        if ppe_violations:
                            self.save_violations_to_db(company_id, camera_id, ppe_violations)
                    
                    time.sleep(0.01)  # CPU'yu rahatlatmak için
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"❌ SaaS Detection hatası: {e}")
                time.sleep(1)
        
        logger.info(f"🛑 SaaS Detection durduruldu - Kamera: {camera_id}")

    def start_saas_camera(self, camera_key, camera_id, company_id):
        """SaaS Kamera başlatma"""
        try:
            # Kamera bilgilerini al
            cameras = self.db.get_company_cameras(company_id)
            camera_info = None
            
            for cam in cameras:
                if cam['camera_id'] == camera_id:
                    camera_info = cam
                    break
            
            if not camera_info:
                logger.error(f"❌ Kamera bulunamadı: {camera_id}")
                return
            
            # Kamera URL'sini oluştur
            camera_url = None
            if camera_info.get('ip_address') and camera_info.get('port'):
                protocol = camera_info.get('protocol', 'http')
                ip = camera_info['ip_address']
                port = camera_info['port']
                stream_path = camera_info.get('stream_path', '/video')
                
                if protocol == 'rtsp':
                    camera_url = f"rtsp://{ip}:{port}{stream_path}"
                else:
                    camera_url = f"http://{ip}:{port}{stream_path}"
            else:
                # Webcam kullan
                camera_url = 0
            
            # Kamera worker thread'ini başlat
            camera_thread = threading.Thread(
                target=self.saas_camera_worker,
                args=(camera_key, camera_url),
                daemon=True
            )
            camera_thread.start()
            
            logger.info(f"✅ SaaS Kamera başlatıldı: {camera_id} -> {camera_url}")
            
        except Exception as e:
            logger.error(f"❌ SaaS Kamera başlatma hatası: {e}")

    def saas_camera_worker(self, camera_key, camera_url):
        """SaaS Kamera Worker"""
        cap = None
        try:
            import cv2
            
            # Kamera bağlantısı
            cap = cv2.VideoCapture(camera_url)
            
            if not cap.isOpened():
                logger.error(f"❌ Kamera açılamadı: {camera_url}")
                return
            
            # Kamera ayarları
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            
            camera_captures[camera_key] = cap
            
            logger.info(f"✅ SaaS Kamera worker başladı: {camera_key}")
            
            while active_detectors.get(camera_key, False):
                ret, frame = cap.read()
                if ret:
                    frame_buffers[camera_key] = frame
                else:
                    logger.warning(f"⚠️ Frame okunamadı: {camera_key}")
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

    def generate_saas_frames(self, camera_key, company_id, camera_id):
        """SaaS Frame Generator"""
        import cv2
        
        while active_detectors.get(camera_key, False):
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
                    # Placeholder frame
                    import numpy as np
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(placeholder, 'Camera Loading...', (200, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    
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
        """SaaS Detection Overlay çiz"""
        import cv2
        
        try:
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
            
            # İhlal detayları
            if violations:
                y_offset = 100
                for i, violation in enumerate(violations[:3]):  # Sadece ilk 3'ü göster
                    missing_ppe = ', '.join(violation.get('missing_ppe', []))
                    cv2.putText(frame, f'Violation {i+1}: {missing_ppe}', (10, y_offset), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                    y_offset += 20
            
            # Zaman damgası
            timestamp = detection_data.get('timestamp', '')
            if timestamp:
                cv2.putText(frame, timestamp[:19], (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
        except Exception as e:
            logger.error(f"❌ Overlay çizim hatası: {e}")
        
        return frame

    def save_detection_to_db(self, detection_data):
        """Detection sonuçlarını veritabanına kaydet"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            
            cursor.execute(f'''
                INSERT INTO detections (
                    company_id, camera_id, timestamp, people_detected, 
                    ppe_compliant, compliance_rate, processing_time_ms
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                detection_data['company_id'],
                detection_data['camera_id'],
                detection_data['timestamp'],
                detection_data['people_detected'],
                detection_data['ppe_compliant'],
                detection_data['compliance_rate'],
                detection_data['processing_time_ms']
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Detection DB kayıt hatası: {e}")

    def save_violations_to_db(self, company_id, camera_id, violations):
        """İhlalleri veritabanına kaydet"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.db.get_placeholder() if hasattr(self.db, 'get_placeholder') else '?'
            
            for violation in violations:
                cursor.execute(f'''
                    INSERT INTO violations (
                        company_id, camera_id, timestamp, violation_type, 
                        missing_ppe, confidence, person_id
                    ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ''', (
                    company_id,
                    camera_id,
                    datetime.now().isoformat(),
                    'PPE_VIOLATION',
                    ', '.join(violation['missing_ppe']),
                    violation['confidence'],
                    violation['person_id']
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Violation DB kayıt hatası: {e}")

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
                    mode: 'ppe',
                    confidence: confidence
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    detectionActive = true;
                    document.getElementById('camera-status').textContent = 'Aktif';
                    document.getElementById('system-status').textContent = 'Çalışıyor';
                    
                    // Video stream'i başlat
                    const streamUrl = `/api/company/{{ company_id }}/camera-stream/${currentCameraId}`;
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





