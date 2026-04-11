from flask import Blueprint, jsonify, request
import logging

logger = logging.getLogger(__name__)

def create_blueprint(api):
    """Notification Blueprint oluşturur"""
    bp = Blueprint('notification', __name__)

    @bp.route('/api/company/<company_id>/notification/test', methods=['POST'])
    def send_test_notification(company_id):
        """Telegram üzerinden test bildirimi gönderir"""
        try:
            from services.notification_service import get_notification_service
            ns = get_notification_service(api.db) # API üzerinden db'ye erişim
            
            success = ns.send_test_notification(company_id)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Test bildirimi başarıyla gönderildi.'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Bildirim gönderilemedi. Lütfen /start ile botu aktif ettiğinizden emin olun.'
                }), 400
                
        except Exception as e:
            logger.error(f"❌ API Notification Error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    return bp
