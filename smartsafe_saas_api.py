#!/usr/bin/env python3
"""
SmartSafe AI - SaaS Multi-Tenant API Server
Şirket bazlı veri ayrımı ile profesyonel SaaS sistemi
"""

from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartSafeSaaSAPI:
    """SmartSafe AI SaaS API Server"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'smartsafe-saas-2024-secure-key')
        
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
        
        # Setup routes
        self.setup_routes()
        
        logger.info("🌐 SmartSafe AI SaaS API Server initialized")
    
    def setup_routes(self):
        """API rotalarını ayarla"""
        
        # Ana sayfa - Şirket kayıt
        @self.app.route('/', methods=['GET'])
        def home():
            """Ana sayfa - Şirket kayıt formu"""
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
                ppe_requirements = []
                if request.form.get('ppe_helmet'):
                    ppe_requirements.append('helmet')
                if request.form.get('ppe_vest'):
                    ppe_requirements.append('vest')
                if request.form.get('ppe_glasses'):
                    ppe_requirements.append('glasses')
                if request.form.get('ppe_gloves'):
                    ppe_requirements.append('gloves')
                if request.form.get('ppe_shoes'):
                    ppe_requirements.append('shoes')
                if request.form.get('ppe_mask'):
                    ppe_requirements.append('mask')
                
                # En az bir PPE seçimi zorunlu
                if not ppe_requirements:
                    return '''
                    <script>
                        alert("❌ En az bir PPE türü seçmelisiniz!");
                        window.history.back();
                    </script>
                    '''
                
                data['required_ppe'] = ppe_requirements
                
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
            """Gelişmiş şirket istatistikleri"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            stats = self.db.get_company_stats(company_id)
            
            # Enhanced stats with trends
            enhanced_stats = {
                'active_cameras': stats.get('active_cameras', 0),
                'compliance_rate': stats.get('compliance_rate', 0),
                'today_violations': stats.get('today_violations', 0),
                'active_workers': stats.get('active_workers', 0),
                'total_detections': stats.get('total_detections', 0),
                'monthly_violations': stats.get('monthly_violations', 0),
                
                # Trend indicators
                'cameras_trend': stats.get('cameras_trend', 0),
                'compliance_trend': stats.get('compliance_trend', 0),
                'violations_trend': stats.get('violations_trend', 0),
                'workers_trend': stats.get('workers_trend', 0)
            }
            
            return jsonify(enhanced_stats)
        
        # Şirket kameraları API
        @self.app.route('/api/company/<company_id>/cameras', methods=['GET'])
        def get_company_cameras(company_id):
            """Şirket kameralarını getir"""
            user_data = self.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            cameras = self.db.get_company_cameras(company_id)
            return jsonify({'cameras': cameras})
        
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
                # Demo chart data (gerçek projede database'den gelecek)
                chart_data = {
                    'compliance_trend': [78, 82, 85, 88, 92, 87, 90],  # Son 7 gün
                    'violation_types': [45, 30, 15, 10],  # Baret, Yelek, Ayakkabı, Maske
                    'hourly_violations': [2, 1, 0, 1, 3, 2, 4, 5, 3, 2, 1, 0],  # 24 saat
                    'weekly_compliance': [88, 92, 85, 90, 87, 89, 91]  # Haftalık
                }
                
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
            """IP kamera otomatik keşfi"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                network_range = data.get('network_range', '192.168.1.0/24')
                
                # Gerçek IP kamera keşfi
                try:
                    from camera_discovery import IPCameraDiscovery
                    discovery = IPCameraDiscovery()
                    result = discovery.scan_network(network_range, timeout=2)
                    discovered_cameras = result['cameras']
                    scan_time = result['scan_time']
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
                    'scan_time': scan_time
                })
                
            except Exception as e:
                print(f"❌ Camera discovery error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/company/<company_id>/cameras/test', methods=['POST'])
        def test_camera(company_id):
            """Kamera bağlantı testi"""
            try:
                user_data = self.validate_session()
                if not user_data or user_data.get('company_id') != company_id:
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
                data = request.get_json()
                camera_config = {
                    'ip': data.get('ip'),
                    'port': data.get('port', 554),
                    'rtsp_url': data.get('rtsp_url'),
                    'username': data.get('username'),
                    'password': data.get('password')
                }
                
                # Gerçek kamera bağlantı testi
                try:
                    from camera_discovery import IPCameraDiscovery
                    discovery = IPCameraDiscovery()
                    test_results = discovery.test_camera_connection(camera_config)
                except ImportError:
                    # Fallback: örnek veriler
                    test_results = {
                        'connection_status': 'success',
                        'response_time': '150ms',
                        'resolution': '1920x1080',
                        'fps': 25,
                        'codec': 'H.264',
                        'bitrate': '2048 kbps',
                        'ptz_support': False,
                        'night_vision': True,
                        'audio_support': True,
                        'test_duration': '3.2 saniye',
                        'quality_score': 8.5
                    }
                
                return jsonify({
                    'success': True,
                    'test_results': test_results,
                    'message': 'Kamera testi başarılı'
                })
                
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

    def validate_session(self):
        """Oturum doğrulama"""
        session_id = session.get('session_id')
        if not session_id:
            return None
        
        return self.db.validate_session(session_id)
    
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
                                                   oninput="validateEmailRegister(this)"
                                                   onblur="validateEmailRegister(this)"
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
                                    <div class="mb-4">
                                        <label class="form-label">
                                            <i class="fas fa-hard-hat text-warning"></i> 
                                            Zorunlu PPE Seçimi *
                                        </label>
                                        <div class="card p-3" style="background-color: #f8f9fa;">
                                            <div class="row">
                                                <div class="col-md-6">
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_helmet" id="ppe_helmet" value="1">
                                                        <label class="form-check-label" for="ppe_helmet">
                                                            <i class="fas fa-hard-hat text-primary"></i> Baret/Kask
                                                        </label>
                                                    </div>
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_vest" id="ppe_vest" value="1">
                                                        <label class="form-check-label" for="ppe_vest">
                                                            <i class="fas fa-vest text-warning"></i> Güvenlik Yeleği
                                                        </label>
                                                    </div>
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_glasses" id="ppe_glasses" value="1">
                                                        <label class="form-check-label" for="ppe_glasses">
                                                            <i class="fas fa-glasses text-info"></i> Güvenlik Gözlüğü
                                                        </label>
                                                    </div>
                                                </div>
                                                <div class="col-md-6">
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_gloves" id="ppe_gloves" value="1">
                                                        <label class="form-check-label" for="ppe_gloves">
                                                            <i class="fas fa-mitten text-success"></i> İş Eldiveni
                                                        </label>
                                                    </div>
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_shoes" id="ppe_shoes" value="1">
                                                        <label class="form-check-label" for="ppe_shoes">
                                                            <i class="fas fa-shoe-prints text-dark"></i> Güvenlik Ayakkabısı
                                                        </label>
                                                    </div>
                                                    <div class="form-check mb-2">
                                                        <input class="form-check-input" type="checkbox" name="ppe_mask" id="ppe_mask" value="1">
                                                        <label class="form-check-label" for="ppe_mask">
                                                            <i class="fas fa-head-side-mask text-secondary"></i> Maske
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                            <small class="text-muted mt-2">
                                                <i class="fas fa-info-circle"></i> 
                                                Sisteminizde izlenecek PPE türlerini seçin. En az bir PPE seçimi zorunludur.
                                            </small>
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

                // Form validation on submit
                document.getElementById('registerForm').addEventListener('submit', function(e) {
                    const emailInput = this.querySelector('input[name="email"]');
                    validateEmailRegister(emailInput);
                    
                    if (emailInput.classList.contains('is-invalid') || !emailInput.value.includes('@')) {
                        e.preventDefault();
                        alert('❌ Lütfen geçerli bir email adresi girin!\n\nÖrnek: yildizteknık@gmail.com');
                        emailInput.focus();
                        return false;
                    }
                    
                    // Additional validation
                    const emailRegex = /^[a-zA-Z0-9._%+-çğıöşüÇĞIİÖŞÜ]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
                    if (!emailRegex.test(emailInput.value)) {
                        e.preventDefault();
                        alert('❌ Email formatı geçersiz!\n\nTürkçe karakterler desteklenir.\nÖrnek: yildizteknık@gmail.com');
                        emailInput.focus();
                        return false;
                    }
                    
                    // PPE selection validation
                    const ppeCheckboxes = ['ppe_helmet', 'ppe_vest', 'ppe_glasses', 'ppe_gloves', 'ppe_shoes', 'ppe_mask'];
                    const selectedPPE = ppeCheckboxes.filter(id => document.getElementById(id).checked);
                    
                    if (selectedPPE.length === 0) {
                        e.preventDefault();
                        alert('❌ En az bir PPE türü seçmelisiniz!\n\nGüvenlik sisteminin çalışması için gereklidir.');
                        document.getElementById('ppe_helmet').focus();
                        return false;
                    }
                });
            </script>
        </body>
        </html>
        '''
    
    def get_login_template(self, company_id):
        """Giriş sayfası template"""
        return f'''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SmartSafe AI - Giriş</title>
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
                .btn-custom {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            <div class="container mt-5">
                <div class="row justify-content-center">
                    <div class="col-md-6 col-lg-4">
                        <div class="text-center mb-4">
                            <h1 class="text-white display-4 fw-bold">
                                <i class="fas fa-shield-alt"></i> SmartSafe AI
                            </h1>
                            <p class="text-white-50 fs-6">Şirket ID: {company_id}</p>
                        </div>
                        
                        <div class="card">
                            <div class="card-body p-5">
                                <h3 class="text-center mb-4">
                                    <i class="fas fa-sign-in-alt text-primary"></i> Giriş
                                </h3>
                                
                                <form method="POST" action="/company/{company_id}/login-form">
                                    <div class="mb-3">
                                        <label class="form-label">E-mail</label>
                                        <input type="text" class="form-control" name="email" required
                                               placeholder="ornek@email.com"
                                               autocomplete="email">
                                    </div>
                                    
                                    <div class="mb-4">
                                        <label class="form-label">Şifre</label>
                                        <input type="password" class="form-control" name="password" required>
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
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
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
                            const grid = document.getElementById('cameras-grid');
                            if (data.cameras && data.cameras.length > 0) {
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
                                    </div>
                                `).join('');
                            } else {
                                grid.innerHTML = `
                                    <div class="col-12 text-center py-5">
                                        <i class="fas fa-video fa-3x text-muted mb-3"></i>
                                        <p class="text-muted">Henüz kamera eklenmemiş</p>
                                        <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addCameraModal">
                                            <i class="fas fa-plus"></i> İlk Kameranızı Ekleyin
                                        </button>
                                    </div>
                                `;
                            }
                        })
                        .catch(error => {
                            console.error('Kameralar yüklenemedi:', error);
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
                
                function logout() {
                    fetch('/logout', {method: 'POST'})
                        .then(() => {
                            window.location.href = '/';
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
    
    def get_admin_template(self):
        """Admin panel template"""
        return '''
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Panel - SmartSafe AI</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #dc3545 0%, #6f42c1 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .card {
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
                <div class="container">
                    <a class="navbar-brand fw-bold" href="/admin">
                        <i class="fas fa-crown text-warning"></i> SmartSafe AI - Admin Panel
                    </a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="/">Ana Sayfa</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <div class="row">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header bg-danger text-white">
                                <h4 class="mb-0">
                                    <i class="fas fa-building"></i> Kayıtlı Şirketler
                                </h4>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-striped" id="companiesTable">
                                        <thead>
                                            <tr>
                                                <th>Şirket ID</th>
                                                <th>Şirket Adı</th>
                                                <th>Email</th>
                                                <th>Sektör</th>
                                                <th>Kamera Limiti</th>
                                                <th>Kayıt Tarihi</th>
                                                <th>Durum</th>
                                                <th>İşlemler</th>
                                            </tr>
                                        </thead>
                                        <tbody id="companiesTableBody">
                                            <!-- Şirketler buraya yüklenecek -->
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Şirketleri yükle
                function loadCompanies() {
                    fetch('/api/admin/companies')
                        .then(response => response.json())
                        .then(data => {
                            const tbody = document.getElementById('companiesTableBody');
                            
                            if (data.companies && data.companies.length > 0) {
                                tbody.innerHTML = data.companies.map(company => `
                                    <tr>
                                        <td><code>${company.company_id}</code></td>
                                        <td>${company.company_name}</td>
                                        <td>${company.email}</td>
                                        <td><span class="badge bg-info">${company.sector}</span></td>
                                        <td>${company.max_cameras}</td>
                                        <td>${new Date(company.created_at).toLocaleDateString('tr-TR')}</td>
                                        <td>
                                            <span class="badge ${company.status === 'active' ? 'bg-success' : 'bg-danger'}">
                                                ${company.status}
                                            </span>
                                        </td>
                                        <td>
                                            <button class="btn btn-danger btn-sm" onclick="deleteCompany('${company.company_id}', '${company.company_name}')">
                                                <i class="fas fa-trash"></i> Sil
                                            </button>
                                        </td>
                                    </tr>
                                `).join('');
                            } else {
                                tbody.innerHTML = '<tr><td colspan="8" class="text-center">Henüz kayıtlı şirket yok</td></tr>';
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            document.getElementById('companiesTableBody').innerHTML = 
                                '<tr><td colspan="8" class="text-center text-danger">Hata oluştu</td></tr>';
                        });
                }
                
                // Şirket sil
                function deleteCompany(companyId, companyName) {
                    if (confirm(`⚠️ "${companyName}" şirketi ve tüm verileri SİLİNECEK!\\n\\nBu işlem geri alınamaz. Emin misiniz?`)) {
                        fetch(`/api/admin/companies/${companyId}`, {
                            method: 'DELETE'
                        })
                        .then(response => response.json())
                        .then(result => {
                            if (result.success) {
                                alert('✅ Şirket başarıyla silindi!');
                                loadCompanies(); // Tabloyu yenile
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
                
                // Sayfa yüklendiğinde şirketleri yükle
                document.addEventListener('DOMContentLoaded', function() {
                    loadCompanies();
                });
            </script>
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
                                    <div class="stream-preview">
                                        <i class="fas fa-video fa-2x"></i>
                                        <div class="position-absolute top-0 start-0 p-2">
                                            <span class="camera-status ${camera.status === 'active' ? 'status-online' : 'status-offline'}"></span>
                                            <small class="text-white">${camera.status === 'active' ? 'Online' : 'Offline'}</small>
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
                    alert(`🧪 ${cameraId} kamerası test ediliyor...\\n\\n(Bu özellik geliştirilme aşamasında)`);
                }
                
                // View Stream
                function viewStream(cameraId) {
                    alert(`📹 ${cameraId} canlı yayın açılıyor...\\n\\n(Bu özellik geliştirilme aşamasında)`);
                }
                
                // Delete Camera
                function deleteCamera(cameraId) {
                    if (confirm('Bu kamerayı silmek istediğinizden emin misiniz?')) {
                        alert(`🗑️ ${cameraId} kamerası siliniyor...\\n\\n(Bu özellik geliştirilme aşamasında)`);
                    }
                }
                
                // Refresh Cameras
                function refreshCameras() {
                    loadCameras();
                    loadCameraGroups();
                }
                
                // Test All Cameras
                function testAllCameras() {
                    alert('🧪 Tüm kameralar test ediliyor...\\n\\n(Bu özellik geliştirilme aşamasında)');
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