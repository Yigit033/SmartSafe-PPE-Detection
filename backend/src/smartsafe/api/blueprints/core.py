"""
SmartSafe AI - Core Blueprint
Landing page, app home, pricing & contact endpoints
"""

from flask import Blueprint, request, jsonify, render_template, render_template_string
from flask_mail import Message
import logging

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('core', __name__)

    @bp.route('/api/contact', methods=['POST'])
    def contact():
        """İletişim formu gönderimi"""
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            sector = request.form.get('sector')
            message = request.form.get('message')
            
            if not all([name, email, sector, message]):
                return jsonify({'success': False, 'error': 'Please fill all fields'}), 400
            
            msg = Message(
                subject=f'SmartSafe AI - Yeni İletişim Formu: {name}',
                sender=api.app.config['MAIL_USERNAME'],
                recipients=['yigittilaver2000@gmail.com'],
                body=f'''Yeni bir iletişim formu gönderildi:
                    
Ad Soyad: {name}
E-posta: {email}
Sektör: {sector}
Mesaj:
{message}
                    '''
            )
            
            api.mail.send(msg)
            
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

    @bp.route('/', methods=['GET'])
    def landing():
        """Landing page"""
        return render_template('landing.html')

    @bp.route('/app', methods=['GET'])
    def app_home():
        """Company registration form"""
        return render_template('home.html')

    @bp.route('/pricing')
    def pricing():
        """Fiyatlandırma ve plan seçimi sayfası"""
        return render_template('pricing.html')

    return bp
