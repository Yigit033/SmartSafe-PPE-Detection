"""
Alert Blueprint - Alert management routes extracted from SmartSafe SaaS API.
"""
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, render_template_string, Response
import logging
import os
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('alert', __name__)

    # Şirket uyarıları API - İYİLEŞTİRİLDİ: Yeni alerts tablosu kullanıyor
    @bp.route('/api/company/<company_id>/alerts', methods=['GET'])
    def get_company_alerts(company_id):
        """Şirket uyarıları - Yeni alerts tablosu ile gerçek dinamik veriler"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            # Son 24 saat içindeki alerts'leri getir
            if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                time_filter = "a.created_at >= NOW() - INTERVAL '24 hours'"
            else:
                time_filter = "a.created_at >= datetime('now', '-24 hours')"
            
            cursor.execute(f"""
                SELECT a.alert_id, a.alert_type, a.severity, a.title, a.message, 
                       a.status, a.created_at, a.camera_id, c.camera_name
                FROM alerts a
                LEFT JOIN cameras c ON a.camera_id = c.camera_id
                WHERE a.company_id = {placeholder} 
                AND {time_filter}
                ORDER BY a.created_at DESC
                LIMIT 20
            """, (company_id,))
            
            alerts_data = cursor.fetchall()
            alerts = []
            
            for alert in alerts_data:
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(alert, 'keys'):  # PostgreSQL Row object
                    alert_data = {
                        'alert_id': alert['alert_id'],
                        'alert_type': alert['alert_type'],
                        'severity': alert['severity'],
                        'title': alert['title'],
                        'message': alert['message'],
                        'status': alert['status'],
                        'created_at': alert['created_at'],
                        'camera_id': alert['camera_id'],
                        'camera_name': alert['camera_name']
                    }
                else:  # SQLite tuple
                    alert_data = {
                        'alert_id': alert[0],
                        'alert_type': alert[1],
                        'severity': alert[2],
                        'title': alert[3],
                        'message': alert[4],
                        'status': alert[5],
                        'created_at': alert[6],
                        'camera_id': alert[7],
                        'camera_name': alert[8]
                    }
                
                # Timestamp'i formatla
                try:
                    from datetime import datetime
                    if isinstance(alert_data['created_at'], str):
                        dt = datetime.fromisoformat(alert_data['created_at'].replace('Z', '+00:00'))
                    else:
                        dt = alert_data['created_at']
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = 'Bilinmiyor'
                
                # Alert severity'ye göre icon ve renk belirle
                severity_config = {
                    'critical': {'icon': '🔴', 'color': 'danger'},
                    'warning': {'icon': '🟡', 'color': 'warning'},
                    'info': {'icon': '🔵', 'color': 'info'},
                    'success': {'icon': '🟢', 'color': 'success'}
                }
                
                severity_info = severity_config.get(alert_data['severity'].lower(), 
                                                 {'icon': '🔵', 'color': 'info'})
                
                alerts.append({
                    'alert_id': alert_data['alert_id'],
                    'type': alert_data['alert_type'],
                    'title': alert_data['title'],
                    'message': alert_data['message'],
                    'time': time_str,
                    'camera_name': alert_data['camera_name'] or 'Sistem',
                    'severity': alert_data['severity'],
                    'status': alert_data['status'],
                    'icon': severity_info['icon'],
                    'color': severity_info['color']
                })
            
                        # Eğer gerçek veri yoksa demo veriler göster
            if not alerts:
                alerts = [
                    {
                        'alert_id': 'demo_1',
                        'type': 'system',
                        'title': 'Sistem Hazırlanıyor',
                        'message': 'PPE detection sistemi hazırlanıyor, kameralar test ediliyor',
                        'time': 'Şimdi',
                        'camera_name': 'Sistem',
                        'severity': 'info',
                        'status': 'active',
                        'icon': '🔵',
                        'color': 'info'
                    }
                ]
            
            conn.close()
            
            return jsonify({
                'success': True,
                'alerts': alerts,
                'total_alerts': len(alerts),
                'active_alerts': len([a for a in alerts if a['status'] == 'active']),
                'resolved_alerts': len([a for a in alerts if a['status'] == 'resolved'])
            })
            
        except Exception as e:
            logger.error(f"❌ Uyarılar yüklenemedi: {e}")
            return jsonify({
                'success': False,
                'error': 'Uyarılar yüklenemedi',
                'alerts': []
            }), 500
    
    # Real-time Alert Generation API
    @bp.route('/api/company/<company_id>/alerts/generate', methods=['POST'])
    def generate_alert(company_id):
        """Real-time alert generation - Live detection'dan gelen verilerle"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            data = request.get_json()
            alert_type = data.get('alert_type', 'system')
            severity = data.get('severity', 'info')
            title = data.get('title', 'Sistem Uyarısı')
            message = data.get('message', 'Bilinmeyen uyarı')
            camera_id = data.get('camera_id')
            
            # Alert'i database'e kaydet
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            if api.db.db_adapter.db_type == 'sqlite':
                cursor.execute(f'''
                    INSERT INTO alerts (company_id, camera_id, alert_type, severity, title, message, status, created_at)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 'active', datetime('now'))
                ''', (company_id, camera_id, alert_type, severity, title, message))
            else:  # PostgreSQL
                cursor.execute(f'''
                    INSERT INTO alerts (company_id, camera_id, alert_type, severity, title, message, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW())
                ''', (company_id, camera_id, alert_type, severity, title, message))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Alert generated: {title} - {message}")
            
            return jsonify({
                'success': True,
                'message': 'Alert başarıyla oluşturuldu',
                'alert': {
                    'alert_type': alert_type,
                    'severity': severity,
                    'title': title,
                    'message': message
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Alert generation hatası: {e}")
            return jsonify({
                'success': False,
                'error': 'Alert oluşturulamadı'
            }), 500
    
    # Alert Management API
    @bp.route('/api/company/<company_id>/alerts/<alert_id>/resolve', methods=['POST'])
    def resolve_alert(company_id, alert_id):
        """Alert'i çözüldü olarak işaretle"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            if api.db.db_adapter.db_type == 'sqlite':
                cursor.execute(f'''
                    UPDATE alerts 
                    SET status = 'resolved', resolved_at = datetime('now')
                    WHERE alert_id = {placeholder} AND company_id = {placeholder}
                ''', (alert_id, company_id))
            else:  # PostgreSQL
                cursor.execute(f'''
                    UPDATE alerts 
                    SET status = 'resolved', resolved_at = NOW()
                    WHERE alert_id = %s AND company_id = %s
                ''', (alert_id, company_id))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Alert çözüldü olarak işaretlendi'
            })
            
        except Exception as e:
            logger.error(f"❌ Alert resolve hatası: {e}")
            return jsonify({
                'success': False,
                'error': 'Alert güncellenemedi'
            }), 500

    return bp
