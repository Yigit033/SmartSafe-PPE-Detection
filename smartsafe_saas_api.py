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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enterprise modülleri import et
try:
    from camera_integration_manager import get_camera_manager, ProfessionalCameraManager
    from enhanced_error_handler import EnhancedErrorHandler
    from professional_config_manager import ProfessionalConfigManager
    from performance_optimizer import PerformanceOptimizer
    from enterprise_security_manager import EnterpriseSecurityManager
    from enterprise_monitoring_system import EnterpriseMonitoringSystem
    ENTERPRISE_MODULES_AVAILABLE = True
    logger.info("✅ Enterprise modülleri yüklendi")
except ImportError as e:
    logger.warning(f"⚠️ Enterprise modülleri yüklenemedi: {e}")
    ENTERPRISE_MODULES_AVAILABLE = False

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
        """Enterprise modülleri başlat"""
        if ENTERPRISE_MODULES_AVAILABLE:
            try:
                # Error Handler
                self.error_handler = EnhancedErrorHandler()
                logger.info("✅ Enhanced Error Handler başlatıldı")
                
                # Config Manager
                self.config_manager = ProfessionalConfigManager()
                logger.info("✅ Professional Config Manager başlatıldı")
                
                # Performance Optimizer
                self.performance_optimizer = PerformanceOptimizer()
                logger.info("✅ Performance Optimizer başlatıldı")
                
                # Security Manager
                self.security_manager = EnterpriseSecurityManager()
                logger.info("✅ Enterprise Security Manager başlatıldı")
                
                # Monitoring System
                self.monitoring_system = EnterpriseMonitoringSystem()
                logger.info("✅ Enterprise Monitoring System başlatıldı")
                
                # Camera Manager
                self.camera_manager = get_camera_manager()
                logger.info("✅ Professional Camera Manager başlatıldı")
                
                self.enterprise_enabled = True
                logger.info("🚀 Tüm Enterprise modülleri başarıyla entegre edildi!")
                
            except Exception as e:
                logger.error(f"❌ Enterprise modül başlatma hatası: {e}")
                self.enterprise_enabled = False
        else:
            self.enterprise_enabled = False
            logger.info("⚙️ Fallback moda geçiliyor - Enterprise özellikler devre dışı")
    
    def setup_routes(self):
        """API rotalarını ayarla"""
        
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
                    return jsonify({'success': False, 'error': 'Tüm alanları doldurun'}), 400
                
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
                    'message': 'Mesajınız başarıyla gönderildi'
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
            """Şirket kayıt formu"""
            return render_template_string(self.get_home_template())

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
                        'message': 'Şirket başarıyla kaydedildi',
                        'login_url': f'/company/{result}/login'
                    })
                else:
                    return jsonify({'success': False, 'error': result}), 400
                    
            except Exception as e:
                logger.error(f"❌ Şirket kayıt hatası: {e}")
                return jsonify({'success': False, 'error': 'Kayıt işlemi başarısız'}), 500

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
                    'max_cameras': int(request.form.get('max_cameras', 5)),
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
                        <title>Kayıt Başarılı!</title>
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
                                            <h2 class="mt-3 text-success">🎉 Kayıt Başarılı!</h2>
                                            <hr>
                                            <div class="alert alert-info">
                                                <h5><i class="fas fa-building"></i> Şirket ID'niz:</h5>
                                                <h3 class="text-primary"><strong>{company_id}</strong></h3>
                                            </div>
                                            <div class="alert alert-warning">
                                                <i class="fas fa-exclamation-triangle"></i>
                                                <strong>ÖNEMLİ:</strong> Bu ID'yi not alın! 
                                                Tekrar giriş yaparken gerekecek.
                                            </div>
                                            <div class="mt-4">
                                                <a href="{login_url}" class="btn btn-primary btn-lg">
                                                    <i class="fas fa-sign-in-alt"></i> Giriş Sayfasına Git
                                                </a>
                                            </div>
                                            <div class="mt-3">
                                                <a href="/" class="btn btn-outline-secondary">
                                                    <i class="fas fa-home"></i> Ana Sayfa
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <script>
                            // Şirket ID'sini localStorage'da sakla
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT company_name FROM companies WHERE company_id = ?', (company_id,))
                company = cursor.fetchone()
                conn.close()
                
                if not company:
                    return f'''
                    <script>
                        alert("❌ '{company_id}' ID'sine sahip şirket bulunamadı!\\nLütfen şirket ID'nizi kontrol edin.");
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
            """Şirket uyarıları"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            try:
                # Demo alert data (gerçek projede database'den gelecek)
                alerts = [
                    {
                        'violation_type': 'Baret Eksik',
                        'description': 'Çalışan baret takmadan çalışma alanına girdi',
                        'time': '14:30',
                        'camera_name': 'Kamera 1',
                        'severity': 'Yüksek'
                    },
                    {
                        'violation_type': 'Güvenlik Yeleği Eksik',
                        'description': 'Güvenlik yeleği olmadan çalışma',
                        'time': '13:45',
                        'camera_name': 'Kamera 2',
                        'severity': 'Orta'
                    },
                    {
                        'violation_type': 'Güvenlik Ayakkabısı Eksik',
                        'description': 'Uygun olmayan ayakkabı kullanımı',
                        'time': '12:20',
                        'camera_name': 'Kamera 3',
                        'severity': 'Düşük'
                    }
                ]
                
                return jsonify({'alerts': alerts})
                
            except Exception as e:
                logger.error(f"❌ Uyarılar yüklenemedi: {e}")
                return jsonify({'error': 'Uyarılar yüklenemedi'}), 500
        
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
                conn = sqlite3.connect(self.db.db_path)
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
                    companies_list.append({
                        'company_id': comp[0],
                        'company_name': comp[1],
                        'email': comp[2],
                        'sector': comp[3],
                        'max_cameras': comp[4],
                        'created_at': comp[5],
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                # Şirket var mı kontrol et
                cursor.execute('SELECT company_name FROM companies WHERE company_id = ?', (company_id,))
                company = cursor.fetchone()
                
                if not company:
                    return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
                
                # İlgili verileri sil (CASCADE mantığı)
                tables_to_clean = ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']
                
                for table in tables_to_clean:
                    cursor.execute(f'DELETE FROM {table} WHERE company_id = ?', (company_id,))
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True, 'message': f'Şirket {company[0]} silindi'})
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        # === ŞIRKET SELF-SERVICE SILME ===
        @self.app.route('/company/<company_id>/settings', methods=['GET'])
        def company_settings(company_id):
            """Şirket ayarları sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                # Önce şirket tablosunda hangi kolonların var olduğunu kontrol et
                cursor.execute("PRAGMA table_info(companies)")
                columns = [column[1] for column in cursor.fetchall()]
                print(f"🔍 Available columns in companies: {columns}")
                
                # Şirket bilgilerini güncelle - sadece mevcut kolonları kullan
                if all(col in columns for col in ['company_name', 'contact_person', 'email', 'phone', 'sector', 'address']):
                    cursor.execute("""
                        UPDATE companies 
                        SET company_name = ?, 
                            contact_person = ?, 
                            email = ?, 
                            phone = ?, 
                            sector = ?, 
                            address = ?
                        WHERE company_id = ?
                    """, (
                        data.get('company_name'),
                        data.get('contact_person'),
                        data.get('email'),
                        data.get('phone'),
                        data.get('sector'),
                        data.get('address'),
                        company_id
                    ))
                else:
                    # Sadece mevcut kolonları güncelle
                    cursor.execute("""
                        UPDATE companies 
                        SET company_name = ?, 
                            email = ?
                        WHERE company_id = ?
                    """, (
                        data.get('company_name'),
                        data.get('email'),
                        company_id
                    ))
                
                # Kullanıcı tablosunu kontrol et
                cursor.execute("PRAGMA table_info(users)")
                user_columns = [column[1] for column in cursor.fetchall()]
                print(f"🔍 Available columns in users: {user_columns}")
                
                # Kullanıcı bilgilerini güncelle - sadece mevcut kolonları kullan
                if 'contact_person' in user_columns:
                    cursor.execute("""
                        UPDATE users 
                        SET email = ?, 
                            contact_person = ?
                        WHERE company_id = ?
                    """, (
                        data.get('email'),
                        data.get('contact_person'),
                        company_id
                    ))
                else:
                    cursor.execute("""
                        UPDATE users 
                        SET email = ?
                        WHERE company_id = ?
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('SELECT password FROM companies WHERE company_id = ?', (company_id,))
                stored_password = cursor.fetchone()
                
                if not stored_password or not self.db.verify_password(data['current_password'], stored_password[0]):
                    return jsonify({'success': False, 'error': 'Mevcut şifre yanlış'}), 401
                
                # Yeni şifre hash'le
                new_password_hash = self.db.hash_password(data['new_password'])
                
                # Şifre güncelle
                cursor.execute("""
                    UPDATE companies 
                    SET password = ? 
                    WHERE company_id = ?
                """, (new_password_hash, company_id))
                
                cursor.execute("""
                    UPDATE users 
                    SET password_hash = ? 
                    WHERE company_id = ?
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('SELECT password FROM companies WHERE company_id = ?', (company_id,))
                stored_password = cursor.fetchone()
                
                if not stored_password or not self.db.verify_password(password, stored_password[0]):
                    return jsonify({'success': False, 'error': 'Yanlış şifre'}), 401
                
                # Hesap silme işlemi
                tables_to_clean = ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']
                
                for table in tables_to_clean:
                    cursor.execute(f'DELETE FROM {table} WHERE company_id = ?', (company_id,))
                
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT user_id, email, contact_person, role, status, created_at, last_login
                    FROM users 
                    WHERE company_id = ?
                    ORDER BY created_at DESC
                """, (company_id,))
                
                users = []
                for row in cursor.fetchall():
                    users.append({
                        'user_id': row[0],
                        'email': row[1],
                        'contact_person': row[2],
                        'role': row[3] if row[3] else 'admin',
                        'status': row[4] if row[4] else 'active',
                        'created_at': row[5],
                        'last_login': row[6]
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
                
                # Geçici şifre oluştur
                temp_password = f"temp{uuid.uuid4().hex[:8]}"
                password_hash = self.db.hash_password(temp_password)
                
                # Kullanıcı ekle
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO users (user_id, company_id, email, contact_person, password_hash, role, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'))
                """, (user_id, company_id, data['email'], data['contact_person'], password_hash, data['role']))
                
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
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM users WHERE user_id = ? AND company_id = ?", (user_id, company_id))
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                
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
            """İhlal raporunu getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Son 30 günün ihlal verileri
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                # Örnek veri oluştur (gerçek sistemde database'den gelecek)
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
            """Uyumluluk raporunu getir"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                # Örnek uyumluluk verileri
                compliance_data = {
                    'overall_compliance': 87.5,
                    'helmet_compliance': 92.3,
                    'vest_compliance': 85.1,
                    'shoes_compliance': 89.7,
                    'daily_stats': [
                        {'date': '2025-07-01', 'compliance': 88.2},
                        {'date': '2025-07-02', 'compliance': 91.5},
                        {'date': '2025-07-03', 'compliance': 85.8},
                        {'date': '2025-07-04', 'compliance': 89.3},
                        {'date': '2025-07-05', 'compliance': 87.5}
                    ],
                    'camera_stats': [
                        {'camera_name': 'Ana Giriş', 'compliance': 89.2},
                        {'camera_name': 'İnşaat Alanı', 'compliance': 84.5},
                        {'camera_name': 'Depo Girişi', 'compliance': 91.7}
                    ]
                }
                
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
            """Kamera bağlantı testi - Profesyonel kamera yöneticisi ile"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                rtsp_url = data.get('rtsp_url', '')
                camera_name = data.get('name', 'Test Camera')
                
                # Enterprise kamera yöneticisini kullan
                if self.enterprise_enabled and hasattr(self, 'camera_manager'):
                    # Enterprise Camera Manager kullan
                    camera_manager = self.camera_manager
                    
                    # Kamera konfigürasyonu oluştur
                    if rtsp_url.startswith('http://') and ':8080' in rtsp_url:
                        # IP Webcam
                        ip = rtsp_url.split('//')[1].split(':')[0]
                        camera_config = camera_manager.create_ip_webcam_config(camera_name, ip, 8080)
                    elif rtsp_url.startswith('rtsp://'):
                        # RTSP Camera
                        from camera_integration_manager import CameraSource
                        camera_config = CameraSource(
                            camera_id=f"TEST_{int(time.time())}",
                            name=camera_name,
                            source_type='rtsp',
                            connection_url=rtsp_url,
                            resolution=(1280, 720),
                            fps=25
                        )
                    else:
                        # Local camera
                        camera_index = int(rtsp_url) if rtsp_url.isdigit() else 0
                        camera_config = camera_manager.create_local_camera_config(camera_name, camera_index)
                    
                    # Enterprise test yap
                    test_result = camera_manager.test_camera_connection(camera_config)
                    
                    # Performance monitoring
                    if hasattr(self, 'performance_optimizer'):
                        self.performance_optimizer.record_camera_test(camera_config.camera_id, test_result)
                
                else:
                    # Fallback: Basit test
                    test_result = self._basic_camera_test(rtsp_url, camera_name)
                
                # API response formatına dönüştür
                api_response = {
                    'success': test_result['connection_status'] == 'connected',
                    'test_results': {
                        'connection_status': 'success' if test_result['connection_status'] == 'connected' else 'failed',
                        'response_time': f"{test_result.get('response_time_ms', 0):.0f}ms",
                        'resolution': test_result.get('resolution_detected', 'Bilinmiyor'),
                        'fps': test_result.get('fps_detected', 0),
                        'codec': 'H.264',
                        'source_type': test_result.get('source_type', 'unknown'),
                        'features': test_result.get('features', {}),
                        'error_message': test_result.get('error_message', ''),
                        'test_duration': f"{test_result.get('response_time_ms', 0)/1000:.1f} saniye"
                    },
                    'message': 'Kamera bağlantısı başarılı' if test_result['connection_status'] == 'connected' else f"Kamera bağlantısı başarısız: {test_result.get('error_message', 'Bilinmeyen hata')}"
                }
                
                return jsonify(api_response)
                
            except Exception as e:
                print(f"❌ Camera test error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
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
                success, message = self.db.delete_camera(company_id, camera_id)
                
                if not success:
                    return jsonify({
                        'success': False,
                        'message': message
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
        
        @self.app.route('/company/<company_id>/cameras', methods=['GET'])
        def camera_management(company_id):
            """Kamera yönetimi sayfası"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            return render_template_string(self.get_camera_management_template(), 
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
                
                cursor.execute('''
                    UPDATE companies 
                    SET required_ppe = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = ?
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

        # Video streaming endpoint'leri
        @self.app.route('/api/company/<company_id>/start-detection', methods=['POST'])
        def start_detection(company_id):
            """Şirket için tespit başlat"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
                
                data = request.json
                camera_id = data.get('camera', '0')
                mode = data.get('mode', 'construction')
                confidence = data.get('confidence', 0.5)
                
                # Kamera zaten aktifse durdur
                camera_key = f"{company_id}_{camera_id}"
                if camera_key in active_detectors and active_detectors[camera_key]:
                    return jsonify({'success': False, 'error': 'Kamera zaten aktif'})
                
                # Kamera aktif olarak işaretle
                active_detectors[camera_key] = True
                
                # Kamera worker thread'ini başlat
                camera_thread = threading.Thread(
                    target=self.camera_worker,
                    args=(camera_key, camera_id),
                    daemon=True
                )
                camera_thread.start()
                
                # Tespit thread'ini başlat - confidence parametresi ile
                detection_thread = threading.Thread(
                    target=self.run_detection,
                    args=(camera_key, camera_id, company_id, mode, confidence),
                    daemon=True
                )
                detection_thread.start()
                
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

        @self.app.route('/api/company/<company_id>/video-feed/<camera_id>')
        def video_feed(company_id, camera_id):
            """Video stream endpoint"""
            user_data = self.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            return Response(self.generate_frames(camera_key),
                           mimetype='multipart/x-mixed-replace; boundary=frame')

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
    
    def _basic_camera_test(self, rtsp_url, camera_name):
        """Basit kamera testi (Enterprise olmayan durumlar için)"""
        import time
        start_time = time.time()
        
        test_result = {
            'connection_status': 'failed',
            'response_time_ms': 0,
            'resolution_detected': 'Unknown',
            'fps_detected': 0,
            'source_type': 'unknown',
            'features': {},
            'error_message': ''
        }
        
        try:
            if rtsp_url.isdigit():
                # Local camera test
                camera_index = int(rtsp_url)
                cap = cv2.VideoCapture(camera_index)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        test_result['connection_status'] = 'connected'
                        test_result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                        test_result['fps_detected'] = cap.get(cv2.CAP_PROP_FPS) or 25
                        test_result['source_type'] = 'local'
                        test_result['features'] = {'video_stream': True}
                    else:
                        test_result['error_message'] = 'Kameradan frame alınamadı'
                    cap.release()
                else:
                    test_result['error_message'] = 'Kamera açılamadı'
                    
            elif rtsp_url.startswith(('rtsp://', 'http://')):
                # Network camera test
                cap = cv2.VideoCapture(rtsp_url)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        test_result['connection_status'] = 'connected'
                        test_result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                        test_result['fps_detected'] = cap.get(cv2.CAP_PROP_FPS) or 25
                        test_result['source_type'] = 'rtsp' if rtsp_url.startswith('rtsp://') else 'ip_webcam'
                        test_result['features'] = {'video_stream': True, 'network_camera': True}
                    else:
                        test_result['error_message'] = 'Network kamerasından frame alınamadı'
                    cap.release()
                else:
                    test_result['error_message'] = 'Network kamerası bağlantısı kurulamadı'
            else:
                test_result['error_message'] = 'Geçersiz kamera URL formatı'
                
        except Exception as e:
            test_result['error_message'] = str(e)
        
        test_result['response_time_ms'] = (time.time() - start_time) * 1000
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
        """Tespit çalıştır - Sektörel Detection Factory kullanarak"""
        print(f"Tespit sistemi başlatılıyor - Kamera: {camera_key}, Sektör: {mode}, Confidence: {confidence}")
        
        # Detection sonuçları için queue oluştur
        detection_results[camera_key] = queue.Queue(maxsize=10)
        
        # Şirketin sektörünü belirle
        try:
            # Şirket bilgilerini al
            conn = sqlite3.connect('smartsafe_saas.db')
            cursor = conn.cursor()
            cursor.execute('SELECT sector FROM companies WHERE company_id = ?', (company_id,))
            result = cursor.fetchone()
            conn.close()
            
            sector_id = result[0] if result else 'construction'
            print(f"📊 Şirket {company_id} sektörü: {sector_id}")
            
        except Exception as e:
            print(f"⚠️ Şirket sektörü belirlenemedi: {e}, construction kullanılacak")
            sector_id = 'construction'
        
        # Sektörel Detector'ı başlat
        try:
            detector = SectorDetectorFactory.get_detector(sector_id, company_id)
            if detector:
                print(f"✅ {sector_id.upper()} sektörü detector başlatıldı (Company: {company_id}) - Kamera: {camera_key}, Confidence: {confidence}")
            else:
                print(f"⚠️ {sector_id.upper()} detector yüklenemedi, simülasyon modu - Kamera: {camera_key}")
        except Exception as e:
            print(f"❌ Sektörel Detector başlatılamadı: {e}, simülasyon moduna geçiliyor")
            detector = None
        
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
    
    def get_home_template(self):
        """Ana sayfa template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe AI - SaaS Kayıt</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                    backdrop-filter: blur(10px);
                    background: rgba(255,255,255,0.95);
                }
                .btn-custom {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border: none;
                    border-radius: 25px;
                    padding: 12px 30px;
                    color: white;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                .btn-custom:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.3);
                    color: white;
                }
            </style>
        </head>
        <body>
            <div class="container mt-5">
                <div class="row justify-content-center">
                    <div class="col-md-8 col-lg-6">
                        <div class="text-center mb-4">
                            <h1 class="text-white display-4 fw-bold">
                                <i class="fas fa-shield-alt"></i> SmartSafe AI
                            </h1>
                            <p class="text-white-50 fs-5">Güvenlik İzleme SaaS Sistemi</p>
                        </div>
                        
                        <div class="card">
                            <div class="card-body p-5">
                                <h3 class="text-center mb-4">
                                    <i class="fas fa-building text-primary"></i> Şirket Kaydı
                                </h3>
                                
                                <form id="registerForm" method="POST" action="/api/register-form">
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Şirket Adı *</label>
                                            <input type="text" class="form-control" name="company_name" required>
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Sektör *</label>
                                            <select class="form-select" name="sector" required>
                                                <option value="">Seçiniz</option>
                                                <option value="construction">İnşaat</option>
                                                <option value="manufacturing">İmalat</option>
                                                <option value="chemical">Kimya</option>
                                                <option value="food">Gıda</option>
                                                <option value="warehouse">Depo/Lojistik</option>
                                            </select>
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">İletişim Kişisi *</label>
                                            <input type="text" class="form-control" name="contact_person" required>
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">E-mail *</label>
                                            <input type="text" class="form-control" name="email" required
                                                   placeholder="ornek@email.com (Türkçe karakterler desteklenir)"
                                                   autocomplete="email">
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Telefon</label>
                                            <input type="tel" class="form-control" name="phone">
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label">Kamera Sayısı</label>
                                            <select class="form-select" name="max_cameras">
                                                <option value="5">5 Kamera (Basic)</option>
                                                <option value="10">10 Kamera (Professional)</option>
                                                <option value="16">16 Kamera (Enterprise)</option>
                                            </select>
                                        </div>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Adres</label>
                                        <textarea class="form-control" name="address" rows="2"></textarea>
                                    </div>
                                    
                                    <!-- PPE Seçimi -->
                                    <div class="mb-4" id="ppe-selection-container" style="display: none;">
                                        <label class="form-label">
                                            <i class="fas fa-hard-hat text-warning"></i> 
                                            Zorunlu PPE Seçimi *
                                        </label>
                                        <p class="text-muted small">Şirketinizde zorunlu olmasını istediğiniz PPE'leri seçin:</p>
                                        <div class="alert alert-info">
                                            <i class="fas fa-info-circle"></i> 
                                            <strong>Önce sektör seçimi yapın</strong> - Sektörünüze özel PPE seçenekleri görünecek
                                        </div>
                                        
                                        <!-- İnşaat Sektörü PPE -->
                                        <div id="construction-ppe" class="ppe-options" style="display: none;">
                                            <div class="row">
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="helmet" id="construction-helmet" checked>
                                                        <label class="form-check-label" for="construction-helmet">
                                                            <i class="fas fa-hard-hat text-primary"></i> Baret/Kask

                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="construction-vest" checked>
                                                        <label class="form-check-label" for="construction-vest">
                                                            <i class="fas fa-tshirt text-warning"></i> Güvenlik Yeleği

                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="construction-shoes" checked>
                                                        <label class="form-check-label" for="construction-shoes">
                                                            <i class="fas fa-socks text-success"></i> Güvenlik Ayakkabısı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="construction-gloves">
                                                        <label class="form-check-label" for="construction-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> Güvenlik Eldiveni
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="glasses" id="construction-glasses">
                                                        <label class="form-check-label" for="construction-glasses">
                                                            <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
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
                                                            <i class="fas fa-user-nurse text-primary"></i> Bone/Başlık
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="food-mask" checked>
                                                        <label class="form-check-label" for="food-mask">
                                                            <i class="fas fa-head-side-mask text-warning"></i> Hijyen Maskesi
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-4 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="apron" id="food-apron" checked>
                                                        <label class="form-check-label" for="food-apron">
                                                            <i class="fas fa-tshirt text-success"></i> Hijyen Önlüğü
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="food-gloves">
                                                        <label class="form-check-label" for="food-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> Hijyen Eldiveni
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="safety_shoes" id="food-shoes">
                                                        <label class="form-check-label" for="food-shoes">
                                                            <i class="fas fa-socks text-info"></i> Kaymaz Ayakkabı
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
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
                                                            <i class="fas fa-hand-paper text-primary"></i> Kimyasal Eldiven
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="glasses" id="chemical-glasses" checked>
                                                        <label class="form-check-label" for="chemical-glasses">
                                                            <i class="fas fa-glasses text-warning"></i> Güvenlik Gözlüğü
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="face_mask" id="chemical-mask" checked>
                                                        <label class="form-check-label" for="chemical-mask">
                                                            <i class="fas fa-head-side-mask text-success"></i> Solunum Maskesi
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_suit" id="chemical-suit" checked>
                                                        <label class="form-check-label" for="chemical-suit">
                                                            <i class="fas fa-tshirt text-info"></i> Kimyasal Tulum
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
                                                            <i class="fas fa-hard-hat text-primary"></i> Endüstriyel Kask
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_vest" id="manufacturing-vest" checked>
                                                        <label class="form-check-label" for="manufacturing-vest">
                                                            <i class="fas fa-tshirt text-warning"></i> Reflektörlü Yelek
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="gloves" id="manufacturing-gloves" checked>
                                                        <label class="form-check-label" for="manufacturing-gloves">
                                                            <i class="fas fa-hand-paper text-success"></i> İş Eldiveni
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="manufacturing-shoes" checked>
                                                        <label class="form-check-label" for="manufacturing-shoes">
                                                            <i class="fas fa-socks text-info"></i> Çelik Burunlu Ayakkabı
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
                                                            <i class="fas fa-tshirt text-primary"></i> Görünürlük Yeleği
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="required_ppe" value="safety_shoes" id="warehouse-shoes" checked>
                                                        <label class="form-check-label" for="warehouse-shoes">
                                                            <i class="fas fa-socks text-warning"></i> Güvenlik Ayakkabısı
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="helmet" id="warehouse-helmet">
                                                        <label class="form-check-label" for="warehouse-helmet">
                                                            <i class="fas fa-hard-hat text-info"></i> Koruyucu Kask
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6 mb-2">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="optional_ppe" value="gloves" id="warehouse-gloves">
                                                        <label class="form-check-label" for="warehouse-gloves">
                                                            <i class="fas fa-hand-paper text-info"></i> İş Eldiveni
                                                            <span class="badge bg-success ms-1">Opsiyonel</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    
                                    <div class="mb-4">
                                        <label class="form-label">Şifre *</label>
                                        <input type="password" class="form-control" name="password" required>
                                    </div>
                                    
                                    <div class="d-grid">
                                        <button type="submit" class="btn btn-custom">
                                            <i class="fas fa-rocket"></i> Kayıt Ol & Hemen Başla
                                        </button>
                                    </div>
                                </form>
                                
                                <div class="text-center mt-4">
                                    <p class="text-muted">
                                        <i class="fas fa-gift text-success"></i> 
                                        İlk ay ücretsiz! Anında kurulum.
                                    </p>
                                </div>
                                
                                <hr class="my-4">
                                
                                <div class="text-center">
                                    <h5 class="mb-3">
                                        <i class="fas fa-sign-in-alt text-secondary"></i> 
                                        Kayıtlı Şirket Girişi
                                    </h5>
                                    
                                    <form method="POST" action="/api/company-login-redirect">
                                        <div class="row">
                                            <div class="col-md-8 mb-2">
                                                <input type="text" 
                                                       class="form-control" 
                                                       name="company_id" 
                                                       placeholder="Şirket ID'nizi girin (örn: COMP_ABC123)"
                                                       style="border-radius: 25px;"
                                                       required>
                                            </div>
                                            <div class="col-md-4">
                                                <button type="submit" 
                                                        class="btn btn-outline-primary w-100" 
                                                        style="border-radius: 25px;">
                                                    <i class="fas fa-arrow-right"></i> Giriş Yap
                                                </button>
                                            </div>
                                        </div>
                                        <small class="text-muted">
                                            Şirket ID'niz COMP_ ile başlayan benzersiz kodunuzdur.
                                        </small>
                                    </form>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
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
                        errorDiv.textContent = 'Geçerli bir email adresi girin (Türkçe karakterler desteklenir)';
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
                        alert('Lutfen gecerli bir email adresi girin!');
                        emailInput.focus();
                        return false;
                    }
                    
                    // PPE selection validation
                    const requiredPPE = document.querySelectorAll('input[name="required_ppe"]:checked');
                    const optionalPPE = document.querySelectorAll('input[name="optional_ppe"]:checked');
                    
                    if (requiredPPE.length === 0 && optionalPPE.length === 0) {
                        e.preventDefault();
                        alert('En az bir PPE turu secmelisiniz!');
                        return false;
                    }
                });

                // PPE Sektor Secimi - Debug Version
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('DOM yuklendi, PPE sistemi baslatiliyor...');
                    
                    var sectorSelect = document.querySelector('select[name="sector"]');
                    var ppeContainer = document.getElementById('ppe-selection-container');
                    
                    console.log('Sektor select elementi:', sectorSelect);
                    console.log('PPE container elementi:', ppeContainer);
                    
                    if (sectorSelect && ppeContainer) {
                        console.log('Elementler bulundu, event listener ekleniyor...');
                        
                        // Sayfa yuklendiginde mevcut sektor degerini kontrol et
                        var currentSector = sectorSelect.value;
                        console.log('Sayfa yuklendiginde sektor degeri:', currentSector);
                        
                        if (currentSector && currentSector !== '') {
                            console.log('Mevcut sektor var, PPE gosteriliyor...');
                            showPPEForSector(currentSector, ppeContainer);
                        }
                        
                        sectorSelect.addEventListener('change', function() {
                            var sector = this.value;
                            console.log('Sektor degisti:', sector);
                            showPPEForSector(sector, ppeContainer);
                        });
                        
                        console.log('Event listener basariyla eklendi!');
                    } else {
                        console.log('HATA: Elementler bulunamadi!');
                        console.log('sectorSelect:', sectorSelect);
                        console.log('ppeContainer:', ppeContainer);
                    }
                });
                
                function showPPEForSector(sector, ppeContainer) {
                    console.log('showPPEForSector cagirildi, sektor:', sector);
                    
                    // Tum PPE seceneklerini gizle
                    var options = document.querySelectorAll('.ppe-options');
                    console.log('Bulunan PPE option sayisi:', options.length);
                    
                    for (var i = 0; i < options.length; i++) {
                        options[i].style.display = 'none';
                        console.log('Gizlendi:', options[i].id);
                    }
                    
                    if (sector && sector !== '') {
                        // PPE container goster
                        ppeContainer.style.display = 'block';
                        console.log('PPE container gosterildi');
                        
                        // Secilen sektorun PPE'sini goster
                        var targetPPEId = sector + '-ppe';
                        var targetPPE = document.getElementById(targetPPEId);
                        
                        console.log('Aranan PPE ID:', targetPPEId);
                        console.log('Bulunan PPE elementi:', targetPPE);
                        
                        if (targetPPE) {
                            targetPPE.style.display = 'block';
                            console.log('PPE secenekleri gosterildi!');
                        } else {
                            console.log('HATA: PPE elementi bulunamadi!');
                            // Tum PPE elementlerini listele
                            var allPPEs = document.querySelectorAll('[id$="-ppe"]');
                            console.log('Mevcut PPE elementleri:');
                            for (var j = 0; j < allPPEs.length; j++) {
                                console.log('- ' + allPPEs[j].id);
                            }
                        }
                    } else {
                        ppeContainer.style.display = 'none';
                        console.log('PPE container gizlendi');
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
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-light bg-white">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="#">
                        <i class="fas fa-shield-alt text-primary"></i> SmartSafe AI
                    </a>
                    <div class="navbar-nav ms-auto">
                        <span class="nav-link fw-bold">
                            <i class="fas fa-building text-primary"></i> 
                            {{ user_data.company_name }}
                        </span>
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
                        <button class="btn btn-outline-danger btn-sm" onclick="logout()">
                            <i class="fas fa-sign-out-alt"></i> Çıkış
                        </button>
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
                    <div class="col-xl-3 col-md-6">
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
                    <div class="col-xl-3 col-md-6">
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
                    <div class="col-xl-3 col-md-6">
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
                    <div class="col-xl-3 col-md-6">
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
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-video"></i> Yeni Kamera Ekle
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="cameraForm">
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kamera Adı *</label>
                                        <input type="text" class="form-control" name="camera_name" required>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Konum *</label>
                                        <input type="text" class="form-control" name="location" required>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">IP Adresi</label>
                                        <input type="text" class="form-control" name="ip_address" placeholder="192.168.1.100">
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Port</label>
                                        <input type="number" class="form-control" name="port" value="554">
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">RTSP URL</label>
                                    <input type="text" class="form-control" name="rtsp_url" placeholder="rtsp://192.168.1.100:554/stream1">
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kullanıcı Adı</label>
                                        <input type="text" class="form-control" name="username">
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Şifre</label>
                                        <input type="password" class="form-control" name="password">
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times"></i> İptal
                            </button>
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
                
                function addCamera() {
                    const formData = new FormData(document.getElementById('cameraForm'));
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
                            document.getElementById('cameraForm').reset();
                        } else {
                            alert('❌ Hata: ' + result.error);
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
        """Şirket giriş sayfası template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe PPE - Şirket Girişi</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {
                    background-color: #f8f9fa;
                }
                .login-container {
                    max-width: 400px;
                    margin: 100px auto;
                    padding: 20px;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 0 20px rgba(0,0,0,0.1);
                }
                .logo {
                    text-align: center;
                    margin-bottom: 30px;
                }
                .logo img {
                    max-width: 200px;
                }
                .form-group {
                    margin-bottom: 20px;
                }
                .btn-login {
                    width: 100%;
                    padding: 12px;
                    background-color: #0d6efd;
                    border: none;
                    color: white;
                    font-weight: 500;
                }
                .btn-login:hover {
                    background-color: #0b5ed7;
                }
                .alert {
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="login-container">
                    <a class="navbar-brand" href="/login">
                        <i class="fas fa-shield-alt"></i> SmartSafe AI
                    </a>
                    
                    <h4 class="text-center mb-4">Şirket Girişi</h4>
                    
                    <form action="/company/''' + company_id + '''/login-form" method="POST">
                        <div class="form-group">
                            <label for="email">Email</label>
                            <input type="email" class="form-control" id="email" name="email" required>
                        </div>
                        
                        <div class="form-group">
                            <label for="password">Şifre</label>
                            <input type="password" class="form-control" id="password" name="password" required>
                        </div>
                        
                        <button type="submit" class="btn btn-login">Giriş Yap</button>
                    </form>
                    
                    <div class="text-center mt-3">
                        <small>
                            <a href="#" class="text-muted">Şifremi Unuttum</a>
                        </small>get_login_template
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
                    $('#companiesTable').DataTable();
                });
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
                        <div id="profile-section" class="settings-section">
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
                                                <option value="construction">İnşaat</option>
                                                <option value="manufacturing">İmalat</option>
                                                <option value="chemical">Kimya</option>
                                                <option value="food">Gıda</option>
                                                <option value="warehouse">Depo/Lojistik</option>
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
                                            <strong>PPE İhlal Uyarıları</strong>
                                            <small class="text-muted d-block">İhlal tespit edildiğinde email gönder</small>
                                        </div>
                                        <label class="notification-toggle">
                                            <input type="checkbox" checked>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                    
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <div>
                                            <strong>Günlük Raporlar</strong>
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
                                    <button class="btn btn-outline-primary">
                                        <i class="fas fa-credit-card"></i> Ödeme Yöntemi Değiştir
                                    </button>
                                    <button class="btn btn-outline-warning">
                                        <i class="fas fa-exchange-alt"></i> Plan Değiştir
                                    </button>
                                    <button class="btn btn-outline-info">
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
                const companyId = '{{ company_id }}';
                
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
                        errorDiv.textContent = 'Geçerli bir email adresi girin (Türkçe karakterler desteklenir)';
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
                document.addEventListener('DOMContentLoaded', function() {
                    const navLinks = document.querySelectorAll('.settings-nav .nav-link');
                    const sections = document.querySelectorAll('.settings-section');
                    
                    navLinks.forEach(link => {
                        link.addEventListener('click', function(e) {
                            e.preventDefault();
                            
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
                            if (targetElement) {
                                targetElement.style.display = 'block';
                            }
                        });
                    });
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
                            location.reload();
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
                        const reader = new FileReader();
                        reader.onload = function(e) {
                            const logoUpload = document.querySelector('.logo-upload');
                            logoUpload.innerHTML = `<img src="${e.target.result}" style="width: 100%; height: 100%; object-fit: contain; border-radius: 10px;">`;
                        };
                        reader.readAsDataURL(file);
                    }
                });
                
                // Notification Toggle Auto-save
                document.querySelectorAll('.notification-toggle input').forEach(toggle => {
                    toggle.addEventListener('change', function() {
                        const settingName = this.closest('.d-flex').querySelector('strong').textContent;
                        const isEnabled = this.checked;
                        
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
                
                // Delete Account (Enhanced)
                function deleteAccount() {
                    const formData = new FormData(document.getElementById('deleteAccountForm'));
                    const password = formData.get('password');
                    
                    if (!password) {
                        alert('❌ Lütfen şifrenizi girin!');
                        return;
                    }
                    
                    if (!document.getElementById('confirmDelete').checked) {
                        alert('❌ Lütfen onay kutusunu işaretleyin!');
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
                
                // Sayfa yüklendiğinde PPE konfigürasyonunu yükle
                document.addEventListener('DOMContentLoaded', function() {
                    if (document.getElementById('ppe-config-section')) {
                        loadPPEConfig();
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
                        alert('❌ Lütfen tüm alanları doldurun!');
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
                                                <span class="text-success fw-bold">92.3%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-success" style="width: 92.3%"></div>
                                            </div>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <div class="d-flex justify-content-between">
                                                <span>Güvenlik Yeleği</span>
                                                <span class="text-warning fw-bold">85.1%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-warning" style="width: 85.1%"></div>
                                            </div>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <div class="d-flex justify-content-between">
                                                <span>Güvenlik Ayakkabısı</span>
                                                <span class="text-success fw-bold">89.7%</span>
                                            </div>
                                            <div class="progress">
                                                <div class="progress-bar bg-success" style="width: 89.7%"></div>
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
                    initializeCharts();
                    loadViolations();
                });
                
                // Initialize Charts
                function initializeCharts() {
                    // Compliance Chart
                    const complianceCtx = document.getElementById('complianceChart').getContext('2d');
                    complianceChart = new Chart(complianceCtx, {
                        type: 'line',
                        data: {
                            labels: ['01 Tem', '02 Tem', '03 Tem', '04 Tem', '05 Tem'],
                            datasets: [{
                                label: 'Uyumluluk Oranı (%)',
                                data: [88.2, 91.5, 85.8, 89.3, 87.5],
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
                    
                    // Violation Types Chart
                    const violationCtx = document.getElementById('violationTypesChart').getContext('2d');
                    violationTypesChart = new Chart(violationCtx, {
                        type: 'doughnut',
                        data: {
                            labels: ['Baret', 'Güvenlik Yeleği', 'Güvenlik Ayakkabısı'],
                            datasets: [{
                                data: [12, 8, 3],
                                backgroundColor: ['#e74c3c', '#f39c12', '#3498db'],
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
                
                // Load Violations
                function loadViolations() {
                    fetch(`/api/company/${companyId}/reports/violations`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            displayViolations(data.violations);
                        } else {
                            console.error('Failed to load violations:', data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error loading violations:', error);
                    });
                }
                
                // Display Violations
                function displayViolations(violations) {
                    const container = document.getElementById('violationsList');
                    
                    if (violations.length === 0) {
                        container.innerHTML = `
                            <div class="text-center py-4">
                                <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
                                <h5 class="text-success">Hiç ihlal yok!</h5>
                                <p class="text-muted">Seçilen dönemde hiç PPE ihlali tespit edilmedi.</p>
                            </div>
                        `;
                        return;
                    }
                    
                    container.innerHTML = violations.map(violation => `
                        <div class="violation-card">
                            <div class="row align-items-center">
                                <div class="col-md-3">
                                    <strong>${violation.camera_name}</strong>
                                    <small class="d-block text-muted">${violation.date}</small>
                                </div>
                                <div class="col-md-4">
                                    <span class="text-danger">${violation.violation_text}</span>
                                    <small class="d-block text-muted">Güven: %${violation.confidence}</small>
                                </div>
                                <div class="col-md-2">
                                    <span class="badge bg-warning">${violation.worker_id}</span>
                                </div>
                                <div class="col-md-2">
                                    <strong class="text-danger">${violation.penalty}₺</strong>
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
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kamera Adı *</label>
                                        <input type="text" class="form-control" name="camera_name" required>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Lokasyon *</label>
                                        <input type="text" class="form-control" name="location" required>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">IP Adresi *</label>
                                        <input type="text" class="form-control" name="ip_address" required>
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Port</label>
                                        <input type="number" class="form-control" name="port" value="554">
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">RTSP URL</label>
                                    <input type="text" class="form-control" name="rtsp_url">
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Kullanıcı Adı</label>
                                        <input type="text" class="form-control" name="username">
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label">Şifre</label>
                                        <input type="password" class="form-control" name="password">
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Grup</label>
                                    <select class="form-select" name="group_id">
                                        <option value="">Grup Seçin</option>
                                    </select>
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
                    
                    const resultsContainer = document.getElementById('testResults');
                    resultsContainer.style.display = 'block';
                    resultsContainer.innerHTML = `
                        <div class="alert alert-info">
                            <i class="fas fa-spinner fa-spin"></i> Kamera bağlantısı test ediliyor...
                        </div>
                    `;
                    
                    fetch(`/api/company/${companyId}/cameras/test`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            const testData = result.test_results;
                            resultsContainer.innerHTML = `
                                <div class="alert alert-success">
                                    <h6><i class="fas fa-check-circle"></i> Test Başarılı!</h6>
                                    <div class="row">
                                        <div class="col-md-6">
                                            <p><strong>Yanıt Süresi:</strong> ${testData.response_time}</p>
                                            <p><strong>Çözünürlük:</strong> ${testData.resolution}</p>
                                            <p><strong>FPS:</strong> ${testData.fps}</p>
                                        </div>
                                        <div class="col-md-6">
                                            <p><strong>Codec:</strong> ${testData.codec}</p>
                                            <p><strong>Kalite Skoru:</strong> ${testData.quality_score}/10</p>
                                            <p><strong>Test Süresi:</strong> ${testData.test_duration}</p>
                                        </div>
                                    </div>
                                </div>
                            `;
                        } else {
                            resultsContainer.innerHTML = `
                                <div class="alert alert-danger">
                                    <i class="fas fa-exclamation-triangle"></i> Test başarısız: ${result.error}
                                </div>
                            `;
                        }
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
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            alert('✅ Kamera başarıyla eklendi!');
                            bootstrap.Modal.getInstance(document.getElementById('addCameraModal')).hide();
                            loadCameras();
                        } else {
                            alert('❌ Hata: ' + result.error);
                        }
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
                # Check database connection
                db_status = "healthy"
                try:
                    conn = self.db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    conn.close()
                except Exception as e:
                    db_status = f"unhealthy: {str(e)}"
                
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
        self.add_metrics_endpoint()
        
        try:
            # Get port from environment (Render.com compatibility)
            port = int(os.environ.get('PORT', 5000))
            
            # Use production WSGI server or development server
            if os.getenv('FLASK_ENV') == 'production':
                try:
                    from waitress import serve
                    serve(self.app, host='0.0.0.0', port=port, threads=4)
                except ImportError:
                    logger.warning("Waitress not installed, using development server")
                    self.app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
            else:
                self.app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
        except Exception as e:
            logger.error(f"Failed to start SaaS API server: {e}")
            raise

def main():
    """Ana fonksiyon"""
    print("🌐 SmartSafe AI - SaaS Multi-Tenant API Server")
    print("=" * 60)
    print("✅ Multi-tenant şirket yönetimi")
    print("✅ Şirket bazlı veri ayrımı")
    print("✅ Güvenli oturum yönetimi")
    print("✅ Kamera yönetimi")
    print("✅ Responsive web arayüzü")
    print("=" * 60)
    print("🚀 Server başlatılıyor...")
    print("📱 Ana Sayfa: http://localhost:5000")
    print("🏢 Şirket Kayıt: http://localhost:5000")
    
    try:
        api_server = SmartSafeSaaSAPI()
        api_server.run()
        
    except KeyboardInterrupt:
        logger.info("🛑 SaaS API Server stopped by user")
    except Exception as e:
        logger.error(f"❌ SaaS API Server error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())


""" ASıl dosyamız bu ama "smartsafe_saas_api_içinde_tekrar_eden_dosya.py" adlı dosyadaiki tane aynı sınıf var, gerekli düzenlemeyi yap! """ 


