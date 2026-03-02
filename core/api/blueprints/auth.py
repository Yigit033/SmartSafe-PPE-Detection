"""
Auth Blueprint - Authentication and registration routes extracted from SmartSafe SaaS API.
"""
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, render_template_string, Response
import logging
import os
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('auth', __name__)

    @bp.route('/api/register', methods=['POST'])
    def register_company():
        """Yeni şirket kaydı"""
        try:
            data = request.json

            # Veritabanını lazy initialize et
            if not api.ensure_database_initialized() or api.db is None:
                logger.error("❌ Database initialization failed in register_company")
                return jsonify({'success': False, 'error': 'Veritabanı hazır değil. Lütfen daha sonra tekrar deneyin.'}), 500
            required_fields = ['company_name', 'sector', 'contact_person', 'email', 'password']
            
            # Gerekli alanları kontrol et
            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'error': f'{field} gerekli'}), 400
            
            # Şifre validasyonu
            is_valid, validation_errors = api.validate_password_strength(data.get('password', ''))
            if not is_valid:
                return jsonify({
                    'success': False, 
                    'error': 'Şifre gereksinimleri karşılanmıyor',
                    'validation_errors': validation_errors
                }), 400
            
            # Sektör validasyonu
            valid_sectors = ['construction', 'manufacturing', 'chemical', 'food', 'warehouse', 'energy', 'petrochemical', 'marine', 'aviation']
            if data.get('sector') not in valid_sectors:
                return jsonify({'success': False, 'error': 'Geçersiz sektör seçimi'}), 400
            
            # Şirket oluştur
            success, result = api.db.create_company(data)
            
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

    # Demo kayıt endpoint'i
    @bp.route('/api/request-demo', methods=['POST'])
    def request_demo():
        """Demo hesabı talebi"""
        try:
            data = request.json

            # Veritabanını lazy initialize et
            if not api.ensure_database_initialized() or api.db is None:
                logger.error("❌ Database initialization failed in request_demo")
                return jsonify({'success': False, 'error': 'Veritabanı hazır değil. Lütfen daha sonra tekrar deneyin.'}), 500
            required_fields = ['company_name', 'sector', 'contact_person', 'email', 'password']
            
            # Gerekli alanları kontrol et
            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'error': f'{field} gerekli'}), 400
            
            # Şifre validasyonu
            is_valid, validation_errors = api.validate_password_strength(data.get('password', ''))
            if not is_valid:
                return jsonify({
                    'success': False, 
                    'error': 'Şifre gereksinimleri karşılanmıyor',
                    'validation_errors': validation_errors
                }), 400
            
            # Sektör validasyonu
            valid_sectors = ['construction', 'manufacturing', 'chemical', 'food', 'warehouse', 'energy', 'petrochemical', 'marine', 'aviation']
            if data.get('sector') not in valid_sectors:
                return jsonify({'success': False, 'error': 'Geçersiz sektör seçimi'}), 400
            
            # Demo ayarları
            from datetime import datetime, timedelta
            import json
            
            data['account_type'] = 'demo'
            data['demo_expires_at'] = (datetime.now() + timedelta(days=7)).isoformat()
            data['demo_limits'] = json.dumps({
                'cameras': 2,
                'violations': 100,
                'days': 7
            })
            data['subscription_type'] = 'demo'
            data['max_cameras'] = 2
            
            # Demo PPE konfigürasyonu - Sektöre göre varsayılan setler
            demo_ppe_defaults = {
                'construction': {
                    'required': ['helmet', 'safety_vest', 'safety_shoes'],
                    'optional': ['gloves', 'glasses']
                },
                'manufacturing': {
                    'required': ['helmet', 'safety_vest', 'gloves'],
                    'optional': ['glasses', 'ear_protection']
                },
                'chemical': {
                    'required': ['helmet', 'safety_suit', 'gloves', 'face_mask'],
                    'optional': ['glasses', 'respiratory_protection']
                },
                'food': {
                    'required': ['hairnet', 'face_mask', 'apron'],
                    'optional': ['gloves', 'safety_shoes']
                },
                'warehouse': {
                    'required': ['helmet', 'safety_vest', 'safety_shoes'],
                    'optional': ['gloves', 'glasses']
                },
                'energy': {
                    'required': ['helmet', 'insulated_gloves', 'dielectric_boots'],
                    'optional': ['ear_protection', 'arc_flash_suit']
                },
                'petrochemical': {
                    'required': ['helmet', 'chemical_suit', 'respiratory_protection'],
                    'optional': ['special_gloves', 'glasses']
                },
                'marine': {
                    'required': ['life_jacket', 'marine_helmet', 'waterproof_shoes'],
                    'optional': ['safety_vest', 'gloves']
                },
                'aviation': {
                    'required': ['aviation_helmet', 'reflective_vest', 'aviation_shoes'],
                    'optional': ['ear_protection', 'gloves']
                }
            }
            
            # Demo PPE konfigürasyonu için ek alanlar
            selected_sector = data.get('sector')
            if selected_sector in demo_ppe_defaults:
                ppe_set = demo_ppe_defaults[selected_sector]
                data['ppe_requirements'] = json.dumps(ppe_set)
                data['compliance_settings'] = json.dumps({
                    'strict_mode': False,
                    'demo_mode': True,
                    'sector': selected_sector
                })
            else:
                # Fallback için
                fallback_ppe = {
                    'required': ['helmet', 'safety_vest', 'safety_shoes'],
                    'optional': ['gloves', 'glasses']
                }
                data['ppe_requirements'] = json.dumps(fallback_ppe)
                data['compliance_settings'] = json.dumps({
                    'strict_mode': False,
                    'demo_mode': True,
                    'sector': 'general'
                })
            # Şifre kullanıcıdan gelecek - varsayılan yok
            
            # Seçilen sektöre göre PPE setini ata
            selected_sector = data.get('sector')
            if selected_sector in demo_ppe_defaults:
                data['required_ppe'] = demo_ppe_defaults[selected_sector]
            else:
                # Fallback: Genel güvenlik seti
                data['required_ppe'] = {
                    'required': ['helmet', 'safety_vest', 'safety_shoes'],
                    'optional': ['gloves', 'glasses']
                }
            
            # Demo hesabı oluştur
            success, result = api.db.create_company(data)
            
            if success:
                logger.info(f"✅ Demo hesabı oluşturuldu: {result}")
                
                # Demo PPE setini al
                selected_sector = data.get('sector')
                if selected_sector in demo_ppe_defaults:
                    ppe_info = demo_ppe_defaults[selected_sector]
                else:
                    ppe_info = {
                        'required': ['helmet', 'safety_vest', 'safety_shoes'],
                        'optional': ['gloves', 'glasses']
                    }
                
                # Admin mailine demo hesap bilgisi gönder (ASYNC - non-blocking)
                try:
                    admin_email = os.getenv('ADMIN_EMAIL', 'yigittilaver2000@gmail.com')
                    demo_notification = f"""
                    🆕 YENİ DEMO HESAP TALEBİ
                    
                    📋 Şirket Bilgileri:
                    - Şirket Adı: {data.get('company_name')}
                    - Sektör: {data.get('sector')}
                    - İletişim Kişisi: {data.get('contact_person')}
                    - Email: {data.get('email')}
                    - Telefon: {data.get('phone', 'Belirtilmemiş')}
                    
                    🔑 Demo Hesap Bilgileri:
                    - Demo ID: {result}
                    - Şifre: {data.get('password')}
                    - Süre: 7 gün
                    - Kamera Limiti: 2
                    
                    🌐 Demo Login Linki:
                    https://app.getsmartsafeai.com/company/{result}/login
                    
                    📧 MANUEL MAİL GÖNDERİMİ GEREKİYOR!
                    
                    Müşteriye gönderilecek mail içeriği:
                    ===========================================
                    
                    Konu: SmartSafe AI Demo Hesabınız Hazır
                    
                    Merhaba {data.get('contact_person')},
                    
                    SmartSafe AI demo hesabınız başarıyla oluşturuldu. 
                    Demo hesabınıza giriş yapmak için aşağıdaki bilgileri kullanabilirsiniz.
                    
                    🔑 Demo Hesap Bilgileri:
                    - Demo ID: {result}
                    - Email: {data.get('email')}
                    - Şifre: {data.get('password')}
                    
                    🌐 Demo Giriş Linki:
                    https://app.getsmartsafeai.com/company/{result}/login
                    
                    📋 Demo Hesap Özellikleri:
                    - Süre: 7 gün ücretsiz
                    - Kamera Limiti: 2 kamera
                    - DVR/NVR Desteği: Tek cihaz + 2 kanal
                    - PPE Detection: Sektöre özel
                    - Tüm özellikler aktif
                    
                    📞 Sonraki Adımlar:
                    24 saat içinde satış ekibimiz sizinle iletişime geçecek.
                    Demo süresince tüm özellikleri test edebilir,
                    fiyat planlarımızı inceleyebilirsiniz.
                    
                    Demo sonunda size en uygun planı birlikte seçelim!
                    
                    İyi çalışmalar,
                    SmartSafe AI Ekibi
                    
                    ===========================================
                    
                    ⚠️ NOT: Bu mail manuel olarak gönderilmelidir!
                    """
                    
                    # 🚀 ASYNC EMAIL SENDING - Non-blocking, doesn't delay response
                    import threading
                    mail_thread = threading.Thread(
                        target=api._send_demo_notification,
                        args=(admin_email, demo_notification),
                        daemon=True,
                        name=f"demo_mail_{result}"
                    )
                    mail_thread.start()
                    logger.info(f"✅ Demo hesap bildirimi async olarak gönderilmeye başlandı: {admin_email}")
                    
                except Exception as mail_error:
                    logger.error(f"❌ Demo mail gönderim hatası: {mail_error}")
                
                # Müşteriye mail gönderilmiyor - Manuel mail gönderimi yapılacak
                logger.info(f"📧 Demo hesabı oluşturuldu: {data.get('email')} - Manuel mail gönderimi bekleniyor")
                
                return jsonify({
                    'success': True, 
                    'company_id': result,
                    'message': 'Demo hesabınız başarıyla oluşturuldu! 24 saat içinde satış ekibimiz sizinle iletişime geçecek.',
                    'demo_info': {
                        'expires_in_days': 7,
                        'camera_limit': 2,
                        'violation_limit': 100,
                        'sector': selected_sector,
                        'ppe_config': ppe_info
                    },
                    'login_url': f'/company/{result}/login',
                    'demo_id': result,
                    'next_steps': 'Demo hesap bilgileriniz email adresinize gönderilecektir.'
                })
            else:
                # Duplicate email hatası için özel mesaj
                if 'UNIQUE constraint failed: companies.email' in str(result):
                    return jsonify({
                        'success': False, 
                        'error': 'Bu email adresi zaten kullanılıyor. Lütfen farklı bir email adresi deneyin veya mevcut hesabınızla giriş yapın.'
                    }), 400
                else:
                    return jsonify({'success': False, 'error': result}), 400
                
        except Exception as e:
            logger.error(f"❌ Demo kayıt hatası: {e}")
            return jsonify({'success': False, 'error': 'Demo request failed'}), 500

    # HTML Form kayıt endpoint'i
    @bp.route('/api/register-form', methods=['POST'])
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
            billing_cycle = request.form.get('billing_cycle', 'monthly')
            
            plan_prices = {
                'starter': {
                    'name': 'Starter',
                    'monthly': 99,
                    'yearly': 990,  # %17 indirim
                    'cameras': 25,
                    'currency': 'USD',
                    'features': ['AI Tespit (24/7)', 'Email Destek', 'Temel Raporlar', 'Temel Güvenlik'],
                    'billing_cycles': ['monthly', 'yearly']
                },
                'professional': {
                    'name': 'Professional',
                    'monthly': 299,
                    'yearly': 2990,  # %17 indirim
                    'cameras': 100,
                    'currency': 'USD',
                    'features': ['AI Tespit (24/7)', '7/24 Destek', 'Detaylı Analitik', 'Gelişmiş Güvenlik', 'Gelişmiş Bildirimler'],
                    'billing_cycles': ['monthly', 'yearly']
                },
                'enterprise': {
                    'name': 'Enterprise',
                    'monthly': 599,
                    'yearly': 5990,  # %17 indirim
                    'cameras': 500,
                    'currency': 'USD',
                    'features': ['AI Tespit (24/7)', 'Öncelikli Destek', 'Özel Raporlar', 'Maksimum Güvenlik', 'API Erişimi', 'Çoklu Kullanıcı'],
                    'billing_cycles': ['monthly', 'yearly']
                }
            }
            
            if subscription_plan in plan_prices:
                data['subscription_type'] = subscription_plan
                data['billing_cycle'] = billing_cycle
                data['max_cameras'] = plan_prices[subscription_plan]['cameras']
            else:
                data['subscription_type'] = 'starter'
                data['billing_cycle'] = 'monthly'
                data['max_cameras'] = 25
            
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
            
            # Sektör validasyonu
            valid_sectors = ['construction', 'manufacturing', 'chemical', 'food', 'warehouse', 'energy', 'petrochemical', 'marine', 'aviation']
            if data.get('sector') not in valid_sectors:
                return f'''
                <script>
                    alert("❌ Geçersiz sektör seçimi! Lütfen geçerli bir sektör seçin.");
                        window.history.back();
                    </script>
                    '''
            
            # Veritabanını başlat (lazy initialization)
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed")
                return '''
                <script>
                    alert("❌ Veritabanı başlatılamadı! Lütfen daha sonra tekrar deneyin.");
                        window.history.back();
                    </script>
                    '''
            
            # Şirket oluştur
            if api.db is None:
                logger.error("❌ Database is None after initialization")
                return '''
                <script>
                    alert("❌ Veritabanı bağlantısı kurulamadı! Lütfen daha sonra tekrar deneyin.");
                    window.history.back();
                </script>
                '''
            
            success, result = api.db.create_company(data)
            
            if success:
                company_id = result
                login_url = f"/company/{company_id}/login"
                
                # Admin mailine şirket kayıt bilgisi gönder
                try:
                    admin_email = os.getenv('ADMIN_EMAIL', 'yigittilaver2000@gmail.com')
                    
                    # Plan bilgilerini al
                    subscription_plan = data.get('subscription_type', 'starter')
                    billing_cycle = data.get('billing_cycle', 'monthly')
                    
                    plan_info = {
                        'starter': {'name': 'Starter', 'monthly': 99, 'yearly': 990, 'cameras': 25},
                        'professional': {'name': 'Professional', 'monthly': 299, 'yearly': 2990, 'cameras': 100},
                        'enterprise': {'name': 'Enterprise', 'monthly': 599, 'yearly': 5990, 'cameras': 500}
                    }
                    
                    selected_plan = plan_info.get(subscription_plan, plan_info['starter'])
                    
                    company_notification = f"""
                    🏢 YENİ ŞİRKET KAYDI
                    
                    📋 Şirket Bilgileri:
                    - Şirket Adı: {data.get('company_name')}
                    - Sektör: {data.get('sector')}
                    - İletişim Kişisi: {data.get('contact_person')}
                    - Email: {data.get('email')}
                    - Telefon: {data.get('phone', 'Belirtilmemiş')}
                    - Adres: {data.get('address', 'Belirtilmemiş')}
                    
                    💳 Abonelik Bilgileri:
                    - Plan: {selected_plan['name']} ({subscription_plan})
                    - Fatura Döngüsü: {billing_cycle}
                    - Aylık Ücret: ${selected_plan[billing_cycle]}
                    - Kamera Limiti: {selected_plan['cameras']}
                    
                    🔑 Hesap Bilgileri:
                    - Company ID: {company_id}
                    - Şifre: {data.get('password')}
                    
                    🌐 Giriş Linki:
                    https://app.getsmartsafeai.com/company/{company_id}/login
                    
                    📧 MANUEL MAİL GÖNDERİMİ GEREKİYOR!
                    
                    Müşteriye gönderilecek mail içeriği:
                    ===========================================
                    
                    Konu: SmartSafe AI Hesabınız Hazır - {selected_plan['name']} Plan
                    
                    Merhaba {data.get('contact_person')},
                    
                    SmartSafe AI şirket hesabınız başarıyla oluşturuldu!
                    Profesyonel PPE tespit sisteminize hoş geldiniz.
                    
                    🔑 Hesap Bilgileri:
                    - Company ID: {company_id}
                    - Email: {data.get('email')}
                    - Şifre: {data.get('password')}
                    
                    🌐 Giriş Linki:
                    https://app.getsmartsafeai.com/company/{company_id}/login
                    
                    💳 Abonelik Bilgileri:
                    - Plan: {selected_plan['name']}
                    - Kamera Limiti: {selected_plan['cameras']} kamera
                    - Fatura Döngüsü: {billing_cycle}
                    
                    📋 Sonraki Adımlar:
                    1. Yukarıdaki link ile giriş yapın
                    2. İlk kameranızı ekleyin
                    3. PPE kurallarınızı ayarlayın
                    4. Ekibinizi sisteme davet edin
                    
                    📞 Destek:
                    24 saat içinde teknik destek ekibimiz sizinle iletişime geçecek.
                    Kurulum ve eğitim desteği için hazırız!
                    
                    SmartSafe AI ile güvenli çalışma ortamları oluşturun!
                    
                    İyi çalışmalar,
                    SmartSafe AI Ekibi
                    
                    ===========================================
                    
                    ⚠️ NOT: Bu mail manuel olarak gönderilmelidir!
                    """
                    
                    # 🚀 ASYNC EMAIL SENDING - Non-blocking, doesn't delay response
                    import threading
                    mail_thread = threading.Thread(
                        target=api._send_company_notification,
                        args=(admin_email, company_notification),
                        daemon=True,
                        name=f"company_mail_{company_id}"
                    )
                    mail_thread.start()
                    logger.info(f"✅ Şirket kayıt bildirimi async olarak gönderilmeye başlandı: {admin_email}")
                    
                except Exception as mail_error:
                    logger.error(f"❌ Şirket kayıt mail gönderim hatası: {mail_error}")
                
                # Müşteriye mail gönderilmiyor - Manuel mail gönderimi yapılacak
                logger.info(f"📧 Şirket hesabı oluşturuldu: {data.get('email')} - Manuel mail gönderimi bekleniyor")
                
                # Profesyonel başarılı kayıt HTML sayfası
                return render_template('register_success.html', company_id=company_id)
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
    @bp.route('/company/<company_id>/login', methods=['GET', 'POST'])
    def company_login(company_id):
        """Şirket giriş sayfası"""
        if request.method == 'GET':
            return render_template('login.html', company_id=company_id)
        
        # POST - Giriş işlemi
        try:
            data = request.json
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return jsonify({'success': False, 'error': 'Email ve şifre gerekli'}), 400
            
            # Kullanıcı doğrulama
            user_data = api.db.authenticate_user(email, password)
            
            if user_data and user_data['company_id'] == company_id:
                # Oturum oluştur
                session_id = api.db.create_session(
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
    @bp.route('/company/<company_id>/login-form', methods=['POST'])
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
            
            # Demo hesap güvenlik kontrolü
            if company_id.startswith('demo_'):
                return f'''
                <script>
                    alert("❌ Demo hesaplar normal giriş yapamaz!");
                    window.history.back();
                </script>
                '''
            
            # Kullanıcı doğrulama
            user_data = api.db.authenticate_user(email, password)
            
            if user_data and user_data['company_id'] == company_id:
                # Oturum oluştur
                session_id = api.db.create_session(
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
    
    # Demo login endpoint
    @bp.route('/company/<company_id>/demo-login', methods=['POST'])
    def demo_login_form(company_id):
        """Demo hesap girişi"""
        try:
            # Form verilerini al
            demo_id = request.form.get('demo_id')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if not demo_id or not email or not password:
                return f'''
                <script>
                    alert("❌ Demo ID, email ve şifre gerekli!");
                    window.history.back();
                </script>
                '''
            
            # Demo hesap kontrolü
            if not company_id.startswith('demo_'):
                return f'''
                <script>
                    alert("❌ Bu demo girişi değil!");
                    window.history.back();
                </script>
                '''
            
            # Demo ID format kontrolü
            if not demo_id.startswith('demo_'):
                return f'''
                <script>
                    alert("❌ Geçersiz demo ID formatı!");
                    window.history.back();
                </script>
                '''
            
            # Demo hesap doğrulama
            user_data = api.db.authenticate_demo_user(demo_id, email, password)
            
            if user_data:
                # Oturum oluştur
                session_id = api.db.create_session(
                    user_data['user_id'], 
                    demo_id,
                    request.remote_addr,
                    request.headers.get('User-Agent', '')
                )
                
                if session_id:
                    session['session_id'] = session_id
                    session['company_id'] = demo_id
                    session['user_id'] = user_data['user_id']
                    session['is_demo'] = True
                    
                    # Başarılı demo giriş - Dashboard'a yönlendir
                    return f'''
                    <script>
                        alert("🎉 Demo girişi başarılı! Dashboard'a yönlendiriliyorsunuz...");
                        window.location.href = "/company/{demo_id}/dashboard";
                    </script>
                    '''
            
            return f'''
            <script>
                alert("❌ Geçersiz demo bilgileri!");
                window.history.back();
            </script>
            '''
            
        except Exception as e:
            logger.error(f"❌ Demo form giriş hatası: {e}")
            return f'''
            <script>
                alert("❌ Demo giriş hatası: {str(e)}");
                window.history.back();
            </script>
            '''
    
    # Ana sayfa şirket giriş yönlendirme
    @bp.route('/api/company-login-redirect', methods=['POST'])
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
            
            # Şirket ID formatını kontrol et (Normal + Demo)
            if not (company_id.startswith('COMP_') or company_id.startswith('demo_')):
                return '''
                <script>
                    alert("❌ Geçersiz Şirket ID formatı!\\nŞirket ID'niz COMP_ veya demo_ ile başlamalıdır.");
                    window.history.back();
                </script>
                '''
            
            # Veritabanını başlat (lazy initialization)
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in company-login-redirect")
                return '''
                <script>
                    alert("❌ Veritabanı başlatılamadı! Lütfen daha sonra tekrar deneyin.");
                    window.history.back();
                </script>
                '''
            
            if api.db is None:
                logger.error("❌ Database is None after initialization in company-login-redirect")
                return '''
                <script>
                    alert("❌ Veritabanı bağlantısı kurulamadı! Lütfen daha sonra tekrar deneyin.");
                    window.history.back();
                </script>
                '''
            
            # Şirket var mı kontrol et - Safe query with fallback
            conn = api.db.get_connection()
            cursor = conn.cursor()
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            # Try with account_type column first, fallback if column doesn't exist
            try:
                cursor.execute(f'SELECT company_name, account_type, demo_expires_at FROM companies WHERE company_id = {placeholder}', (company_id,))
                company = cursor.fetchone()
            except Exception as e:
                if 'account_type' in str(e) and 'does not exist' in str(e):
                    # Column doesn't exist, use fallback query
                    logger.warning(f"⚠️ account_type column missing, using fallback query")
                    cursor.execute(f'SELECT company_name FROM companies WHERE company_id = {placeholder}', (company_id,))
                    result = cursor.fetchone()
                    if result:
                        company = (result[0], 'full', None)  # Default values
                    else:
                        company = None
                else:
                    raise e
            conn.close()
            
            if not company:
                return '''
                <script>
                    alert("Şirket bulunamadı! Lütfen şirket ID'nizi kontrol edin.");
                    window.history.back();
                </script>
                '''
            
            # Demo hesap kontrolü
            company_name, account_type, demo_expires_at = company
            
            if account_type == 'demo' and demo_expires_at:
                # Demo süresi kontrolü
                if isinstance(demo_expires_at, str):
                    expire_date = datetime.fromisoformat(demo_expires_at.replace('Z', '+00:00'))
                else:
                    expire_date = demo_expires_at
                
                if datetime.now() > expire_date:
                    return f'''
                    <script>
                        alert("❌ Demo hesabınızın süresi dolmuş!\\nDemo süresi: 7 gün\\nŞirket: {company_name}\\n\\nYeni demo hesap oluşturmak için ana sayfaya dönün.");
                        window.location.href = '/';
                    </script>
                    '''
                
                # Demo bilgisi göster
                return f'''
                <script>
                    alert("🎯 Demo Hesap Tespit Edildi!\\n\\nŞirket: {company_name}\\nDemo Süresi: 7 gün\\nKalan Süre: {(expire_date - datetime.now()).days} gün\\n\\nGiriş yapılıyor...");
                    window.location.href = '/company/{company_id}/login';
                </script>
                '''
            
            # Normal şirket giriş sayfasına yönlendir
            return redirect(f'/company/{company_id}/login')
            
        except Exception as e:
            logger.error(f"Şirket giriş yönlendirme hatası: {e}")
            return '''
            <script>
                alert("Bir hata oluştu. Lütfen tekrar deneyin.");
                window.history.back();
            </script>
            '''

    # Çıkış
    @bp.route('/logout', methods=['POST'])
    def logout():
        """Çıkış işlemi"""
        session.clear()
        return jsonify({'success': True, 'message': 'Çıkış yapıldı'})

    return bp
