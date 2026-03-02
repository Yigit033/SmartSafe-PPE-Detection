"""
Admin Blueprint - Admin panel routes extracted from SmartSafe SaaS API.
"""
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, render_template_string, Response
import logging
import os
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('admin', __name__)

    # === ADMIN PANEL ===
    @bp.route('/admin', methods=['GET', 'POST'])
    def admin_panel():
        """Admin panel - Founder şifresi gerekli"""
        if request.method == 'GET':
            # Admin login sayfasını göster
            return render_template('admin_login.html')
        
        # POST - Admin şifre kontrolü
        try:
            data = request.form
            password = data.get('password')
            
            FOUNDER_PASSWORD = os.getenv('FOUNDER_PASSWORD', '')
            if not FOUNDER_PASSWORD:
                logger.error("FOUNDER_PASSWORD env variable is not set – admin login disabled")
                return render_template('admin_login.html', error="Admin girişi yapılandırılmamış. FOUNDER_PASSWORD env variable'ı ayarlayın.")
            
            if password == FOUNDER_PASSWORD:
                # Admin session'u oluştur
                session['admin_authenticated'] = True
                return render_template('admin.html')
            else:
                return render_template('admin_login.html', error="Yanlış şifre!")
                
        except Exception as e:
            logger.error(f"Admin login error: {e}")
            return render_template('admin_login.html', error="Giriş sırasında bir hata oluştu.")
    
    @bp.route('/api/admin/companies', methods=['GET'])
    def admin_get_companies():
        """Admin - Tüm şirketleri getir"""
        # Admin authentication kontrolü
        if not session.get('admin_authenticated'):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            # Database adapter kullan (PostgreSQL/SQLite otomatik seçim)
            conn = api.db.get_connection()
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
    
    @bp.route('/api/admin/companies/<company_id>', methods=['DELETE'])
    def admin_delete_company(company_id):
        """Admin - Şirket sil"""
        # Admin authentication kontrolü
        if not session.get('admin_authenticated'):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            # Şirket var mı kontrol et
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
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

    return bp
