"""
SmartSafe AI - Report Blueprint
Settings, Users, Reports, Profile & Notification endpoints
"""

from flask import Blueprint, request, jsonify, session, redirect, render_template, render_template_string
import logging
import os
import uuid
import bcrypt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('report', __name__)

    # =========================================================================
    # SETTINGS
    # =========================================================================

    @bp.route('/company/<company_id>/settings', methods=['GET'])
    def company_settings(company_id):
        """Şirket ayarları sayfası"""
        try:
            logger.info(f"🔍 Settings page request: company_id={company_id}")
            
            session_id = session.get('session_id')
            logger.info(f"🔍 Session ID from session: {session_id}")
            
            user_data = api.validate_session()
            logger.info(f"🔍 Validated user data: {user_data}")
            
            if not user_data:
                logger.warning(f"⚠️ No user data found, redirecting to login")
                return redirect(f'/company/{company_id}/login')
            
            if user_data.get('company_id') != company_id:
                logger.warning(f"⚠️ Company ID mismatch: session={user_data.get('company_id')}, request={company_id}")
                return redirect(f'/company/{company_id}/login')
            
            logger.info(f"✅ Session validation successful for settings page")
            
        except Exception as e:
            logger.error(f"❌ Settings page error: {e}")
            return redirect(f'/company/{company_id}/login')
        
        try:
            if hasattr(api.db, 'get_company_info'):
                company_info = api.db.get_company_info(company_id)
                if not company_info:
                    company_info = {}
            else:
                conn = api.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT company_name, contact_person, email, phone, sector, address, profile_image, logo_url
                    FROM companies WHERE company_id = {placeholder}
                ''', (company_id,))
                
                company_data = cursor.fetchone()
                conn.close()
                
                if company_data:
                    try:
                        company_info = {
                            'company_name': company_data.get('company_name', ''),
                            'contact_person': company_data.get('contact_person', ''),
                            'email': company_data.get('email', ''),
                            'phone': company_data.get('phone', ''),
                            'sector': company_data.get('sector', 'construction'),
                            'address': company_data.get('address', ''),
                            'profile_image': company_data.get('profile_image', ''),
                            'logo_url': company_data.get('logo_url', '')
                        }
                    except AttributeError:
                        company_info = {
                            'company_name': company_data[0] or '',
                            'contact_person': company_data[1] or '',
                            'email': company_data[2] or '',
                            'phone': company_data[3] or '',
                            'sector': company_data[4] or 'construction',
                            'address': company_data[5] or '',
                            'profile_image': company_data[6] or '',
                            'logo_url': company_data[7] if len(company_data) > 7 else ''
                        }
                else:
                    company_info = {}
            
            user_data.update(company_info)
            
        except Exception as e:
            logger.error(f"❌ Şirket bilgileri yüklenirken hata: {e}")
            company_info = {
                'company_name': '',
                'contact_person': '',
                'email': '',
                'phone': '',
                'sector': 'construction',
                'address': '',
                'profile_image': '',
                'logo_url': ''
            }
            user_data.update(company_info)
        
        return render_template('company_settings.html', 
                                    company_id=company_id, 
                                    user_data=user_data,
                                    company=company_info)

    # =========================================================================
    # PROFILE
    # =========================================================================

    @bp.route('/api/company/<company_id>/profile', methods=['PUT'])
    def update_company_profile(company_id):
        """Şirket profili güncelle - Boş alanları koruyarak"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'Veri gerekli'}), 400
            
            print(f"🔍 Profile update data: {data}")
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                timestamp_func = 'CURRENT_TIMESTAMP'
            else:
                timestamp_func = 'datetime(\'now\')'
            
            update_fields = []
            update_values = []
            
            if data.get('company_name') and data.get('company_name').strip():
                update_fields.append(f"company_name = {placeholder}")
                update_values.append(data.get('company_name').strip())
            
            if data.get('contact_person') and data.get('contact_person').strip():
                update_fields.append(f"contact_person = {placeholder}")
                update_values.append(data.get('contact_person').strip())
            
            if data.get('phone') and data.get('phone').strip():
                update_fields.append(f"phone = {placeholder}")
                update_values.append(data.get('phone').strip())
            
            if data.get('sector') and data.get('sector').strip():
                update_fields.append(f"sector = {placeholder}")
                update_values.append(data.get('sector').strip())
            
            if data.get('address') and data.get('address').strip():
                update_fields.append(f"address = {placeholder}")
                update_values.append(data.get('address').strip())
            
            if data.get('email') and data.get('email').strip():
                update_fields.append(f"email = {placeholder}")
                update_values.append(data.get('email').strip())
            
            print(f"🔍 Logo URL koruma başlatılıyor...")
            try:
                print(f"🔍 Logo URL kolonu kontrol ediliyor...")
                
                if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                    try:
                        cursor.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'companies' AND column_name = 'logo_url'
                        """)
                        logo_url_exists = cursor.fetchone() is not None
                        print(f"🔍 PostgreSQL - Logo URL kolonu mevcut mu: {logo_url_exists}")
                    except Exception as pg_error:
                        print(f"⚠️ PostgreSQL kolon kontrol hatası: {pg_error}")
                        logo_url_exists = False
                else:
                    try:
                        cursor.execute("PRAGMA table_info(companies)")
                        columns = cursor.fetchall()
                        logo_url_exists = any(col[1] == 'logo_url' for col in columns)
                        print(f"🔍 SQLite - Logo URL kolonu mevcut mu: {logo_url_exists}")
                    except Exception as sqlite_error:
                        print(f"⚠️ SQLite kolon kontrol hatası: {sqlite_error}")
                        logo_url_exists = False
                
                if not logo_url_exists:
                    print(f"🔍 Logo URL kolonu ekleniyor...")
                    try:
                        if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                            cursor.execute("ALTER TABLE companies ADD COLUMN logo_url TEXT")
                        else:
                            cursor.execute("ALTER TABLE companies ADD COLUMN logo_url TEXT")
                        conn.commit()
                        print(f"✅ Logo URL kolonu eklendi!")
                    except Exception as add_col_error:
                        print(f"⚠️ Logo URL kolonu eklenirken hata: {add_col_error}")
                
                if hasattr(api.db, 'get_company_info'):
                    print(f"🔍 Database adapter kullanılıyor...")
                    company_info = api.db.get_company_info(company_id)
                    print(f"🔍 Company info: {company_info}")
                    if company_info and company_info.get('logo_url'):
                        current_logo_url = company_info['logo_url']
                        update_fields.append(f"logo_url = {placeholder}")
                        update_values.append(current_logo_url)
                        print(f"🔍 Logo URL korunuyor (DB Adapter): {current_logo_url}")
                    else:
                        print(f"⚠️ Company info veya logo_url bulunamadı: {company_info}")
                else:
                    print(f"🔍 Fallback yöntem kullanılıyor...")
                    cursor.execute(f'''
                        SELECT logo_url FROM companies WHERE company_id = {placeholder}
                    ''', (company_id,))
                    current_logo_result = cursor.fetchone()
                    print(f"🔍 Logo query result: {current_logo_result}")
                    
                    if current_logo_result:
                        current_logo_url = current_logo_result[0] if hasattr(current_logo_result, '__getitem__') else current_logo_result.get('logo_url', '')
                        if current_logo_url:
                            update_fields.append(f"logo_url = {placeholder}")
                            update_values.append(current_logo_url)
                            print(f"🔍 Logo URL korunuyor (Fallback): {current_logo_url}")
                        else:
                            print(f"⚠️ Logo URL boş: {current_logo_url}")
                    else:
                        print(f"⚠️ Logo query sonucu bulunamadı")
            except Exception as logo_error:
                print(f"⚠️ Logo URL koruma hatası: {logo_error}")
                import traceback
                traceback.print_exc()
            
            update_fields.append(f"updated_at = {timestamp_func}")
            
            print(f"🔍 Update fields: {update_fields}")
            print(f"🔍 Update values: {update_values}")
            if update_fields:
                update_values.append(company_id)
                update_sql = f"""
                    UPDATE companies 
                    SET {', '.join(update_fields)}
                WHERE company_id = {placeholder}
                """
                print(f"🔍 Update SQL: {update_sql}")
                cursor.execute(update_sql, update_values)
                print(f"🔍 Update başarılı!")
            
            if data.get('email') and data.get('email').strip():
                cursor.execute(f"""
                        UPDATE users 
                    SET email = {placeholder}
                    WHERE company_id = {placeholder}
                    """, (data.get('email').strip(), company_id))
            
            conn.commit()
            conn.close()
            
            print(f"✅ Profile updated successfully for company: {company_id}")
            return jsonify({'success': True, 'message': 'Profil başarıyla güncellendi'})
                
        except Exception as e:
            print(f"❌ Profile update error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Sunucu hatası: {str(e)}'}), 500

    @bp.route('/api/company/<company_id>/profile/upload-logo', methods=['POST'])
    def upload_company_logo(company_id):
        """Şirket logosu yükle"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            if 'logo' not in request.files:
                return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400
            
            file = request.files['logo']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400
            
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            
            if file_extension not in allowed_extensions:
                return jsonify({'success': False, 'error': 'Geçersiz dosya formatı. PNG, JPG, JPEG, GIF desteklenir.'}), 400
            
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > 5 * 1024 * 1024:
                return jsonify({'success': False, 'error': 'Dosya boyutu 5MB\'dan büyük olamaz'}), 400
            
            filename = f"logo_{company_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
            
            upload_folder = os.path.join(os.getcwd(), 'frontend', 'output', 'uploads', 'logos')
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            logo_url = f'/uploads/logos/{filename}'
            print(f"🔍 Logo URL oluşturuldu: {logo_url}")
            
            print(f"🔍 Database objesi türü: {type(api.db)}")
            print(f"🔍 Database objesi: {api.db}")
            print(f"🔍 update_company_logo_url mevcut mu: {hasattr(api.db, 'update_company_logo_url')}")
            
            if hasattr(api.db, 'update_company_logo_url'):
                print(f"🔍 Database adapter ile logo URL güncelleniyor...")
                success = api.db.update_company_logo_url(company_id, logo_url)
                print(f"🔍 Logo URL güncelleme sonucu: {success}")
                if not success:
                    print(f"❌ Database'de logo URL güncellenemedi: {company_id}")
                    return jsonify({'success': False, 'error': 'Logo URL veritabanında güncellenemedi'}), 500
                else:
                    print(f"✅ Logo URL başarıyla güncellendi: {company_id} -> {logo_url}")
            else:
                print(f"⚠️ Database adapter'da update_company_logo_url fonksiyonu bulunamadı!")
                print(f"🔍 Mevcut database metodları: {[attr for attr in dir(api.db) if not attr.startswith('_')]}")
                
                conn = api.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
                
                if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                    timestamp_func = 'CURRENT_TIMESTAMP'
                else:
                    timestamp_func = 'datetime(\'now\')'
                
                try:
                    cursor.execute(f"""
                        UPDATE companies 
                        SET logo_url = {placeholder}, updated_at = {timestamp_func}
                        WHERE company_id = {placeholder}
                    """, (logo_url, company_id))
                    
                    conn.commit()
                    conn.close()
                except Exception as db_error:
                    if 'logo_url' in str(db_error) and 'does not exist' in str(db_error):
                        print(f"⚠️ logo_url kolonu bulunamadı, sadece updated_at güncelleniyor")
                        cursor.execute(f"""
                            UPDATE companies 
                            SET updated_at = {timestamp_func}
                            WHERE company_id = {placeholder}
                        """, (company_id,))
                        conn.commit()
                        conn.close()
                    else:
                        raise db_error
            
            return jsonify({
                'success': True, 
                'message': 'Logo başarıyla yüklendi',
                'logo_url': logo_url
            })
                
        except Exception as e:
            print(f"❌ Logo upload error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Yükleme hatası: {str(e)}'}), 500

    @bp.route('/api/company/<company_id>/change-password', methods=['PUT'])
    def change_company_password(company_id):
        """Şirket şifresini değiştir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data or not all(k in data for k in ['current_password', 'new_password']):
                return jsonify({'success': False, 'error': 'Mevcut ve yeni şifre gerekli'}), 400
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'SELECT password_hash FROM users WHERE company_id = {placeholder} AND role = \'admin\'', (company_id,))
            stored_password = cursor.fetchone()
            
            if not stored_password or not bcrypt.checkpw(data['current_password'].encode('utf-8'), stored_password[0].encode('utf-8')):
                return jsonify({'success': False, 'error': 'Mevcut şifre yanlış'}), 401
            
            is_valid, validation_errors = api.validate_password_strength(data['new_password'])
            if not is_valid:
                return jsonify({
                    'success': False, 
                    'error': 'Şifre gereksinimleri karşılanmıyor',
                    'validation_errors': validation_errors
                }), 400
            
            new_password_hash = bcrypt.hashpw(data['new_password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
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

    @bp.route('/api/company/<company_id>/delete-account', methods=['POST'])
    def company_delete_account(company_id):
        """Şirket hesabını sil - Self Service"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            data = request.json
            password = data.get('password')
            
            if not password:
                return jsonify({'success': False, 'error': 'Şifre gerekli'}), 400
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'SELECT password_hash FROM users WHERE company_id = {placeholder} AND role = \'admin\'', (company_id,))
            stored_password = cursor.fetchone()
            
            if not stored_password or not bcrypt.checkpw(password.encode('utf-8'), stored_password[0].encode('utf-8')):
                return jsonify({'success': False, 'error': 'Yanlış şifre'}), 401
            
            tables_to_clean = ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']
            
            for table in tables_to_clean:
                cursor.execute(f'DELETE FROM {table} WHERE company_id = {placeholder}', (company_id,))
            
            conn.commit()
            conn.close()
            
            session.clear()
            
            return jsonify({'success': True, 'message': 'Hesabınız başarıyla silindi'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # USERS
    # =========================================================================

    @bp.route('/company/<company_id>/users', methods=['GET'])
    def company_users(company_id):
        """Şirket kullanıcı yönetimi sayfası"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        return render_template('users.html', 
                                    company_id=company_id, 
                                    user_data=user_data)

    @bp.route('/api/company/<company_id>/users', methods=['GET'])
    def get_company_users(company_id):
        """Şirket kullanıcılarını getir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f"""
                SELECT user_id, email, username, role, status, created_at, last_login
                FROM users 
                WHERE company_id = {placeholder}
                ORDER BY created_at DESC
            """, (company_id,))
            
            users = []
            for row in cursor.fetchall():
                if hasattr(row, 'keys'):
                    users.append({
                        'user_id': row.get('user_id'),
                        'email': row.get('email'),
                        'username': row.get('username'),
                        'role': row.get('role') or 'admin',
                        'status': row.get('status'),
                        'created_at': str(row.get('created_at')) if row.get('created_at') else '',
                        'last_login': str(row.get('last_login')) if row.get('last_login') else ''
                    })
                else:
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

    @bp.route('/api/company/<company_id>/users', methods=['POST'])
    def add_company_user(company_id):
        """Yeni kullanıcı ekle"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data or not all(k in data for k in ['email', 'contact_person', 'role']):
                return jsonify({'success': False, 'error': 'Email, isim ve rol gerekli'}), 400
            
            user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
            
            username = data.get('username') or data['email'].split('@')[0]
            
            temp_password = f"temp{uuid.uuid4().hex[:8]}"
            password_hash = api.db.hash_password(temp_password)
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            timestamp_func = 'CURRENT_TIMESTAMP' if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql' else 'datetime(\'now\')'
            
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

    @bp.route('/api/company/<company_id>/users/<user_id>', methods=['DELETE'])
    def delete_company_user(company_id, user_id):
        """Kullanıcı sil"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            if user_data.get('user_id') == user_id:
                return jsonify({'success': False, 'error': 'Kendi hesabınızı silemezsiniz'}), 400
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f"DELETE FROM users WHERE user_id = {placeholder} AND company_id = {placeholder}", (user_id, company_id))
            cursor.execute(f"DELETE FROM sessions WHERE user_id = {placeholder}", (user_id,))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': 'Kullanıcı başarıyla silindi'})
            
        except Exception as e:
            print(f"❌ Delete user error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # REPORTS
    # =========================================================================

    @bp.route('/company/<company_id>/reports', methods=['GET'])
    def company_reports(company_id):
        """Şirket raporlama sayfası"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        return render_template('reports.html', 
                                    company_id=company_id, 
                                    user_data=user_data)

    @bp.route('/api/company/<company_id>/reports/violations', methods=['GET'])
    def get_violations_report(company_id):
        """İhlal raporunu getir - Dinamik Database Verisi"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            if api.db.db_adapter.db_type == 'postgresql':
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
            
            violations_data = {
                'daily_violations': [],
                'camera_violations': [],
                'ppe_violations': [],
                'total_violations': 0,
                'period': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
            }
            
            total_violations = 0
            for row in daily_violations:
                if hasattr(row, 'keys'):
                    violations_data['daily_violations'].append({
                        'date': row['date'],
                        'count': row['count'],
                        'ppe_types': row['ppe_types'] or ''
                    })
                    total_violations += row['count']
                else:
                    violations_data['daily_violations'].append({
                        'date': row[0],
                        'count': row[1],
                        'ppe_types': row[2] or ''
                    })
                    total_violations += row[1]
            
            for row in camera_violations:
                if hasattr(row, 'keys'):
                    violations_data['camera_violations'].append({
                        'camera_id': row['camera_id'],
                        'count': row['count'],
                        'last_violation': row['last_violation']
                    })
                else:
                    violations_data['camera_violations'].append({
                        'camera_id': row[0],
                        'count': row[1],
                        'last_violation': row[2]
                    })
            
            for row in ppe_violations:
                if hasattr(row, 'keys'):
                    violations_data['ppe_violations'].append({
                        'ppe_type': row['missing_ppe'],
                        'count': row['count']
                    })
                else:
                    violations_data['ppe_violations'].append({
                        'ppe_type': row[0],
                        'count': row[1]
                    })
            
            violations_data['total_violations'] = total_violations
            
            if total_violations == 0:
                violations_data['message'] = 'Live detection başlatıldığında gerçek veriler burada görünecek'
                violations_data['status'] = 'waiting_for_live_data'
                violations_data['instruction'] = 'Dashboard\'da "Canlı Tespit Başlat" butonuna tıklayın'
            
            logger.info(f"✅ Violations report generated for {company_id}: {total_violations} violations")
            
            return jsonify({'success': True, 'data': violations_data})
            
        except Exception as e:
            print(f"❌ Violations report error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/reports/compliance', methods=['GET'])
    def get_compliance_report(company_id):
        """Uyumluluk raporunu getir - Dinamik Database Verisi"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            if api.db.db_adapter.db_type == 'postgresql':
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
            
            cursor.execute(f'''
                SELECT missing_ppe, COUNT(*) as violation_count
                FROM violations 
                WHERE company_id = {placeholder} 
                AND timestamp >= {placeholder}
                GROUP BY missing_ppe
                ORDER BY violation_count DESC
            ''', (company_id, start_date.isoformat()))
            
            ppe_violations = cursor.fetchall()
            
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
            
            overall_compliance = 0
            if total_detections > 0:
                overall_compliance = round((total_detections - total_violations) * 100.0 / total_detections, 1)
            
            ppe_compliance = {
                'helmet_compliance': 90.0,
                'vest_compliance': 85.0,
                'shoes_compliance': 88.0
            }
            
            helmet_violations = 0
            vest_violations = 0
            shoes_violations = 0
            
            for row in ppe_violations:
                if hasattr(row, 'keys'):
                    ppe_type = row['missing_ppe'].lower()
                    count = row['violation_count']
                else:
                    ppe_type = row[0].lower()
                    count = row[1]
                
                if 'helmet' in ppe_type or 'kask' in ppe_type:
                    helmet_violations += count
                elif 'vest' in ppe_type or 'yelek' in ppe_type:
                    vest_violations += count
                elif 'shoes' in ppe_type or 'ayakkabı' in ppe_type:
                    shoes_violations += count
            
            if total_detections > 0:
                ppe_compliance['helmet_compliance'] = round((total_detections - helmet_violations) * 100.0 / total_detections, 1)
                ppe_compliance['vest_compliance'] = round((total_detections - vest_violations) * 100.0 / total_detections, 1)
                ppe_compliance['shoes_compliance'] = round((total_detections - shoes_violations) * 100.0 / total_detections, 1)
            
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
            
            for row in daily_compliance:
                if hasattr(row, 'keys'):
                    compliance_data['daily_stats'].append({
                        'date': str(row['date']),
                        'compliance': float(row['compliance_rate']) if row['compliance_rate'] else 0,
                        'detections': row['total_detections'],
                        'violations': row['total_violations']
                    })
                else:
                    compliance_data['daily_stats'].append({
                        'date': str(row[0]),
                        'compliance': float(row[3]) if row[3] else 0,
                        'detections': row[1],
                        'violations': row[2]
                    })
            
            for row in camera_compliance:
                if hasattr(row, 'keys'):
                    compliance_data['camera_stats'].append({
                        'camera_name': f'Kamera {row["camera_id"]}',
                        'camera_id': row['camera_id'],
                        'compliance': float(row['compliance_rate']) if row['compliance_rate'] else 0,
                        'detections': row['total_detections'],
                        'violations': row['total_violations']
                    })
                else:
                    compliance_data['camera_stats'].append({
                        'camera_name': f'Kamera {row[0]}',
                        'camera_id': row[0],
                        'compliance': float(row[3]) if row[3] else 0,
                        'detections': row[1],
                        'violations': row[2]
                    })
            
            if total_detections == 0:
                compliance_data['message'] = 'Live detection başlatıldığında gerçek uyumluluk verileri burada görünecek'
                compliance_data['status'] = 'waiting_for_live_data'
                compliance_data['instruction'] = 'Dashboard\'da "Canlı Tespit Başlat" butonuna tıklayın'
            
            logger.info(f"✅ Compliance report generated for {company_id}: {overall_compliance}% overall compliance")
            
            return jsonify({'success': True, 'data': compliance_data})
            
        except Exception as e:
            print(f"❌ Compliance report error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/reports/export', methods=['POST'])
    def export_report(company_id):
        """Raporu dışa aktar - SQLite ve PostgreSQL uyumlu"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            report_type = data.get('type', 'violations')
            format_type = data.get('format', 'pdf')
            send_email = data.get('send_email', False)
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            report_data = {
                'company_id': company_id,
                'report_type': report_type,
                'format': format_type,
                'generated_at': datetime.now().isoformat(),
                'data': {}
            }
            
            if report_type == 'violations':
                cursor.execute(f'''
                    SELECT camera_id, COUNT(*) as count, MAX(timestamp) as last_violation
                    FROM violations 
                    WHERE company_id = {placeholder}
                    GROUP BY camera_id
                    ORDER BY count DESC
                ''', (company_id,))
                
                violations_data = cursor.fetchall()
                report_data['data']['violations'] = violations_data
            
            elif report_type == 'compliance':
                cursor.execute(f'''
                    SELECT DATE(timestamp) as date, 
                           COUNT(*) as total_detections,
                           SUM(CASE WHEN violations_count = 0 THEN 1 ELSE 0 END) as compliant_detections
                    FROM detections 
                    WHERE company_id = {placeholder}
                    GROUP BY DATE(timestamp)
                    ORDER BY date DESC
                    LIMIT 30
                ''', (company_id,))
                
                compliance_data = cursor.fetchall()
                report_data['data']['compliance'] = compliance_data
            
            elif report_type == 'camera':
                cursor.execute(f'''
                    SELECT camera_id,
                           COUNT(*) as total_detections,
                           AVG(confidence) as avg_confidence,
                           SUM(violations_count) as total_violations
                    FROM detections 
                    WHERE company_id = {placeholder}
                    GROUP BY camera_id
                    ORDER BY total_detections DESC
                ''', (company_id,))
                
                camera_data = cursor.fetchall()
                report_data['data']['camera_performance'] = camera_data
            
            conn.close()
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            if api.db.db_adapter.db_type == 'sqlite':
                cursor.execute('''
                    INSERT INTO reports (company_id, report_type, report_data, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (company_id, report_type, str(report_data), datetime.now()))
            else:
                cursor.execute('''
                    INSERT INTO reports (company_id, report_type, report_data, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (company_id, report_type, report_data, datetime.now()))
            
            conn.commit()
            conn.close()
            
            export_url = f"/exports/{company_id}_{report_type}_{format_type}.{format_type}"
            
            return jsonify({
                'success': True, 
                'message': f'{report_type.title()} raporu başarıyla oluşturuldu',
                'download_url': export_url,
                'report_id': f"{company_id}_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'format': format_type,
                'send_email': send_email
            })
            
        except Exception as e:
            logger.error(f"❌ Export report error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # COMPANY PROFILE PAGE
    # =========================================================================

    @bp.route('/company/<company_id>/profile', methods=['GET'])
    def company_profile(company_id):
        """Şirket profil sayfası"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        try:
            if hasattr(api.db, 'get_company_info'):
                company_info = api.db.get_company_info(company_id)
                if not company_info:
                    company_info = {}
            else:
                conn = api.db.get_connection()
                cursor = conn.cursor()
                
                placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
                cursor.execute(f'''
                    SELECT company_name, sector, contact_person, email, phone, address,
                           subscription_type, subscription_start, subscription_end, max_cameras, logo_url
                    FROM companies 
                    WHERE company_id = {placeholder}
                ''', (company_id,))
                
                company_data = cursor.fetchone()
                conn.close()
                
                if company_data:
                    if hasattr(company_data, 'keys'):
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
                            'max_cameras': company_data['max_cameras'],
                            'logo_url': company_data['logo_url']
                        }
                    else:
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
                            'max_cameras': company_data[9],
                            'logo_url': company_data[10] if len(company_data) > 10 else None
                        }
                else:
                    company_info = {}
            
        except Exception as e:
            logger.error(f"❌ Şirket bilgileri alınamadı: {e}")
            company_info = {}
        
        return render_template('company_profile.html', company_id=company_id, company=company_info, user_data=user_data)

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    @bp.route('/api/company/<company_id>/notifications', methods=['GET'])
    def get_notification_settings(company_id):
        """Get company notification settings"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                SELECT email_notifications, sms_notifications, push_notifications, 
                       violation_alerts, system_alerts, report_notifications
                FROM companies WHERE company_id = {placeholder}
            ''', (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                if hasattr(result, 'keys'):
                    settings = {
                        'email_notifications': result['email_notifications'] if result['email_notifications'] is not None else True,
                        'sms_notifications': result['sms_notifications'] if result['sms_notifications'] is not None else False,
                        'push_notifications': result['push_notifications'] if result['push_notifications'] is not None else True,
                        'violation_alerts': result['violation_alerts'] if result['violation_alerts'] is not None else True,
                        'system_alerts': result['system_alerts'] if result['system_alerts'] is not None else True,
                        'report_notifications': result['report_notifications'] if result['report_notifications'] is not None else True
                    }
                else:
                    settings = {
                        'email_notifications': result[0] if result[0] is not None else True,
                        'sms_notifications': result[1] if result[1] is not None else False,
                        'push_notifications': result[2] if result[2] is not None else True,
                        'violation_alerts': result[3] if result[3] is not None else True,
                        'system_alerts': result[4] if result[4] is not None else True,
                        'report_notifications': result[5] if result[5] is not None else True
                    }
            else:
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

    @bp.route('/api/company/<company_id>/notifications', methods=['PUT'])
    def update_notification_settings(company_id):
        """Update company notification settings"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'Veri gerekli'}), 400
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
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

    return bp
