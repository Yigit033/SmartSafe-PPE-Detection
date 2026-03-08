"""
Admin Blueprint - Admin panel routes extracted from SmartSafe SaaS API.
"""
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, Response
import logging
import os
import uuid
import json
from datetime import datetime
import re

logger = logging.getLogger(__name__)


def _admin_required(session_obj):
    return session_obj.get('admin_authenticated', False)


def create_blueprint(api):
    bp = Blueprint('admin', __name__)

    # === ADMIN PANEL ===
    @bp.route('/admin', methods=['GET', 'POST'])
    def admin_panel():
        """Admin panel - Founder şifresi gerekli"""
        if request.method == 'GET':
            if session.get('admin_authenticated'):
                return render_template('admin.html')
            return render_template('admin_login.html')

        # POST - Admin şifre kontrolü
        try:
            password = request.form.get('password', '')
            FOUNDER_PASSWORD = os.getenv('FOUNDER_PASSWORD', '')
            if not FOUNDER_PASSWORD:
                return render_template('admin_login.html',
                    error="FOUNDER_PASSWORD env variable ayarlanmamış.")
            if password == FOUNDER_PASSWORD:
                session['admin_authenticated'] = True
                return render_template('admin.html')
            return render_template('admin_login.html', error="Yanlış şifre!")
        except Exception as e:
            logger.error(f"Admin login error: {e}")
            return render_template('admin_login.html', error="Giriş sırasında bir hata oluştu.")

    @bp.route('/admin/logout')
    def admin_logout():
        session.pop('admin_authenticated', None)
        return redirect('/admin')

    # ── GET ALL COMPANIES ──────────────────────────────────────────────
    @bp.route('/api/admin/companies', methods=['GET'])
    def admin_get_companies():
        if not _admin_required(session):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        try:
            conn = api.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT company_id, company_name, email, sector, max_cameras,
                       created_at, status, contact_person, phone, address,
                       subscription_type, account_type, api_key, ppe_requirements
                FROM companies
                ORDER BY created_at DESC
            ''')
            rows = cursor.fetchall()
            keys = ['company_id','company_name','email','sector','max_cameras',
                    'created_at','status','contact_person','phone','address',
                    'subscription_type','account_type','api_key','ppe_requirements']
            companies = []
            for row in rows:
                if hasattr(row, 'keys'):
                    d = dict(row)
                else:
                    d = dict(zip(keys, row))
                d['created_at'] = str(d.get('created_at') or '')
                companies.append(d)
            api.db.close_connection(conn)
            return jsonify({'companies': companies, 'total': len(companies)})
        except Exception as e:
            logger.error(f"admin_get_companies error: {e}")
            return jsonify({'error': str(e)}), 500

    # ── CREATE COMPANY ─────────────────────────────────────────────────
    @bp.route('/api/admin/companies', methods=['POST'])
    def admin_create_company():
        if not _admin_required(session):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        try:
            data = request.get_json(force=True)
            required = ['company_name', 'sector', 'contact_person', 'email', 'password']
            for f in required:
                if not data.get(f):
                    return jsonify({'success': False, 'error': f'{f} zorunlu'}), 400

            # Şifre hash
            try:
                import bcrypt
                pw_hash = bcrypt.hashpw(
                    data['password'].encode(), bcrypt.gensalt(12)
                ).decode()
            except ImportError:
                import hashlib
                pw_hash = hashlib.sha256(data['password'].encode()).hexdigest()

            company_id = f"COMP_{uuid.uuid4().hex[:8].upper()}"
            api_key    = str(uuid.uuid4()).replace('-', '')
            ph = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'

            conn   = api.db.get_connection()
            cursor = conn.cursor()

            cursor.execute(f'''
                INSERT INTO companies
                (company_id, company_name, sector, contact_person, email, phone, address,
                 subscription_type, max_cameras, account_type, status, api_key, created_at, updated_at)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            ''', (
                company_id,
                data['company_name'].strip(),
                data['sector'],
                data['contact_person'].strip(),
                data['email'].strip().lower(),
                data.get('phone', ''),
                data.get('address', ''),
                data.get('subscription_type', 'professional'),
                int(data.get('max_cameras', 25)),
                data.get('account_type', 'full'),
                'active',
                api_key,
            ))

            # Default admin user oluştur
            user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
            username = data['email'].split('@')[0]
            cursor.execute(f'''
                INSERT INTO users (user_id, company_id, username, email, password_hash, role, status, created_at)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},CURRENT_TIMESTAMP)
            ''', (user_id, company_id, username, data['email'].strip().lower(),
                  pw_hash, 'admin', 'active'))

            conn.commit()
            api.db.close_connection(conn)
            logger.info(f"✅ Yeni şirket oluşturuldu: {data['company_name']} ({company_id})")
            return jsonify({
                'success': True,
                'company_id': company_id,
                'api_key': api_key,
                'message': f"{data['company_name']} başarıyla oluşturuldu"
            })
        except Exception as e:
            logger.error(f"admin_create_company error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ── UPDATE COMPANY ─────────────────────────────────────────────────
    @bp.route('/api/admin/companies/<company_id>', methods=['PUT'])
    def admin_update_company(company_id):
        if not _admin_required(session):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        try:
            data = request.get_json(force=True)
            ph   = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            conn = api.db.get_connection()
            cursor = conn.cursor()

            cursor.execute(f'SELECT company_id FROM companies WHERE company_id = {ph}', (company_id,))
            if not cursor.fetchone():
                api.db.close_connection(conn)
                return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404

            updates, vals = [], []
            allowed = ['company_name','sector','contact_person','email','phone',
                       'address','subscription_type','max_cameras','account_type','status']
            for field in allowed:
                if field in data:
                    updates.append(f'{field} = {ph}')
                    vals.append(int(data[field]) if field == 'max_cameras' else data[field])

            if not updates:
                api.db.close_connection(conn)
                return jsonify({'success': False, 'error': 'Güncellenecek alan yok'}), 400

            updates.append(f'updated_at = CURRENT_TIMESTAMP')
            vals.append(company_id)
            cursor.execute(f"UPDATE companies SET {', '.join(updates)} WHERE company_id = {ph}", vals)

            # Şifre güncelle (opsiyonel)
            if data.get('password'):
                try:
                    import bcrypt
                    pw_hash = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt(12)).decode()
                except ImportError:
                    import hashlib
                    pw_hash = hashlib.sha256(data['password'].encode()).hexdigest()
                cursor.execute(
                    f'UPDATE users SET password_hash = {ph} WHERE company_id = {ph} AND role = {ph}',
                    (pw_hash, company_id, 'admin')
                )

            conn.commit()
            api.db.close_connection(conn)
            logger.info(f"✅ Şirket güncellendi: {company_id}")
            return jsonify({'success': True, 'message': 'Şirket güncellendi'})
        except Exception as e:
            logger.error(f"admin_update_company error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ── DELETE COMPANY ─────────────────────────────────────────────────
    @bp.route('/api/admin/companies/<company_id>', methods=['DELETE'])
    def admin_delete_company(company_id):
        if not _admin_required(session):
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        try:
            ph   = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            conn = api.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(f'SELECT company_name FROM companies WHERE company_id = {ph}', (company_id,))
            row = cursor.fetchone()
            if not row:
                api.db.close_connection(conn)
                return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
            name = row['company_name'] if hasattr(row, 'keys') else row[0]
            for table in ['detections', 'violations', 'cameras', 'users', 'sessions', 'companies']:
                try:
                    cursor.execute(f'DELETE FROM {table} WHERE company_id = {ph}', (company_id,))
                except Exception:
                    pass
            conn.commit()
            api.db.close_connection(conn)
            logger.info(f"🗑️ Şirket silindi: {name} ({company_id})")
            return jsonify({'success': True, 'message': f'{name} silindi'})
        except Exception as e:
            logger.error(f"admin_delete_company error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    return bp
