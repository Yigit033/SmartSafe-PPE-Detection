"""
SmartSafe AI - Subscription Blueprint
Subscription/billing-related routes extracted from smartsafe_saas_api.py
"""

from flask import Blueprint, request, jsonify, session, redirect, render_template
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def create_blueprint(api):
    """Create and return the subscription blueprint."""
    bp = Blueprint('subscription', __name__)

    @bp.route('/upgrade-modal')
    @bp.route('/company/<company_id>/upgrade-modal')
    def upgrade_modal(company_id=None):
        """Merkezi abonelik planı yükseltme modal'ını döndür"""
        try:
            # Company ID'yi template'e gönder
            return render_template('subscription_upgrade_modal.html', company_id=company_id)
        except Exception as e:
            logger.error(f"❌ Upgrade modal hatası: {e}")
            return "Modal yüklenemedi", 500

    @bp.route('/company/<company_id>/subscription', methods=['GET'])
    def subscription_page(company_id):
        """Abonelik sayfası"""
        try:
            logger.info(f"🔍 Subscription page request: company_id={company_id}")
            
            # Session validation with detailed logging
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
            
            logger.info(f"✅ Session validation successful for subscription page")
            return render_template('subscription_page.html', company_id=company_id, user_data=user_data)
            
        except Exception as e:
            logger.error(f"❌ Subscription page error: {e}")
            return redirect(f'/company/{company_id}/login')

    @bp.route('/company/<company_id>/billing', methods=['GET'])
    def billing_page(company_id):
        """Fatura ve ödeme sayfası"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        return render_template('billing_page.html', company_id=company_id, user_data=user_data)

    # Abonelik plan değiştirme API endpoint'i
    @bp.route('/api/company/<company_id>/subscription/change-plan', methods=['POST'])
    def change_subscription_plan(company_id):
        """Abonelik planını değiştir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            new_plan = data.get('new_plan')
            new_billing_cycle = data.get('billing_cycle', 'monthly')
            
            if not new_plan:
                return jsonify({'success': False, 'error': 'Yeni plan seçimi gerekli'}), 400
            
            # Plan fiyatları
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
            
            if new_plan not in plan_prices:
                return jsonify({'success': False, 'error': 'Geçersiz plan'}), 400
            
            # Database güncelleme
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                UPDATE companies 
                SET subscription_type = {placeholder}, 
                    billing_cycle = {placeholder},
                    max_cameras = {placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder}
            ''', (new_plan, new_billing_cycle, plan_prices[new_plan]['cameras'], company_id))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Plan başarıyla değiştirildi',
                'new_plan': new_plan,
                'billing_cycle': new_billing_cycle,
                'plan_name': plan_prices[new_plan]['name'],
                'monthly_price': plan_prices[new_plan]['monthly'],
                'yearly_price': plan_prices[new_plan]['yearly'],
                'max_cameras': plan_prices[new_plan]['cameras']
            })
            
        except Exception as e:
            logger.error(f"❌ Plan değiştirme hatası: {e}")
            return jsonify({'success': False, 'error': 'Plan değiştirme başarısız'}), 500

    # Billing History API endpoint'i
    @bp.route('/api/company/<company_id>/billing/history', methods=['GET'])
    def get_billing_history(company_id):
        """Get company billing history"""
        try:
            # Session validation
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401

            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                SELECT * FROM billing_history 
                WHERE company_id = {placeholder}
                ORDER BY billing_date DESC
                LIMIT 50
            ''', (company_id,))
            
            results = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            billing_history = []
            if results:
                columns = [desc[0] for desc in cursor.description]
                for row in results:
                    billing_history.append(dict(zip(columns, row)))
            
            return jsonify({
                'success': True,
                'billing_history': billing_history
            })
            
        except Exception as e:
            logger.error(f"❌ Get billing history error: {e}")
            return jsonify({'success': False, 'error': 'Fatura geçmişi alınamadı'}), 500

    # Payment Methods API endpoint'i
    @bp.route('/api/company/<company_id>/payment/methods', methods=['GET'])
    def get_payment_methods(company_id):
        """Get company payment methods"""
        try:
            # Session validation
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401

            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                SELECT * FROM payment_methods 
                WHERE company_id = {placeholder} AND is_active = TRUE
                ORDER BY is_default DESC, created_at DESC
            ''', (company_id,))
            
            results = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            payment_methods = []
            if results:
                columns = [desc[0] for desc in cursor.description]
                for row in results:
                    payment_methods.append(dict(zip(columns, row)))
            
            return jsonify({
                'success': True,
                'payment_methods': payment_methods
            })
            
        except Exception as e:
            logger.error(f"❌ Get payment methods error: {e}")
            return jsonify({'success': False, 'error': 'Ödeme yöntemleri alınamadı'}), 500

    # Subscription Pause API endpoint'i
    @bp.route('/api/company/<company_id>/subscription/pause', methods=['POST'])
    def pause_subscription(company_id):
        """Pause company subscription"""
        try:
            # Session validation
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401

            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                UPDATE companies 
                SET payment_status = 'paused',
                    auto_renewal = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder}
            ''', (company_id,))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Abonelik duraklatıldı'
            })
            
        except Exception as e:
            logger.error(f"❌ Pause subscription error: {e}")
            return jsonify({'success': False, 'error': 'Abonelik duraklatılamadı'}), 500

    # Subscription Cancel API endpoint'i
    @bp.route('/api/company/<company_id>/subscription/cancel', methods=['POST'])
    def cancel_subscription(company_id):
        """Cancel company subscription"""
        try:
            # Session validation
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401

            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                UPDATE companies 
                SET payment_status = 'cancelled',
                    auto_renewal = FALSE,
                    subscription_end = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder}
            ''', (company_id,))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Abonelik iptal edildi'
            })
            
        except Exception as e:
            logger.error(f"❌ Cancel subscription error: {e}")
            return jsonify({'success': False, 'error': 'Abonelik iptal edilemedi'}), 500

    # Auto Renewal Toggle API endpoint'i
    @bp.route('/api/company/<company_id>/subscription/auto-renewal', methods=['POST'])
    def toggle_auto_renewal(company_id):
        """Toggle auto renewal for subscription"""
        try:
            # Session validation
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401

            data = request.get_json()
            auto_renewal = data.get('auto_renewal', True)

            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                UPDATE companies 
                SET auto_renewal = {placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder}
            ''', (auto_renewal, company_id))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': f'Otomatik yenileme {"açıldı" if auto_renewal else "kapatıldı"}',
                'auto_renewal': auto_renewal
            })
            
        except Exception as e:
            logger.error(f"❌ Toggle auto renewal error: {e}")
            return jsonify({'success': False, 'error': 'Otomatik yenileme ayarı değiştirilemedi'}), 500

    # Abonelik bilgileri API endpoint'leri
    @bp.route('/api/company/<company_id>/subscription', methods=['GET'])
    def get_subscription_info(company_id):
        """Get company subscription information"""
        try:
            logger.info(f"🔍 Abonelik isteği: company_id={company_id}")
            
            # Session validation with detailed logging
            session_id = session.get('session_id')
            logger.info(f"🔍 Session ID from session: {session_id}")
            
            user_data = api.validate_session()
            logger.info(f"🔍 Validated user data: {user_data}")
                
            if not user_data:
                logger.warning(f"⚠️ No user data found")
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            if user_data.get('company_id') != company_id:
                logger.warning(f"⚠️ Company ID mismatch: session={user_data.get('company_id')}, request={company_id}")
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                
            logger.info(f"✅ Session validation successful for API")

            # Test database connection first
            try:
                conn = api.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM companies")
                company_count = cursor.fetchone()[0]
                
                # Check if specific company exists
                placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
                cursor.execute(f"SELECT company_name FROM companies WHERE company_id = {placeholder}", (company_id,))
                company_result = cursor.fetchone()
                
                conn.close()
                logger.info(f"🔍 Database connection test successful. Total companies: {company_count}")
                if company_result:
                    logger.info(f"🔍 Company found: {company_result[0]}")
                else:
                    logger.warning(f"⚠️ Company not found: {company_id}")
                    return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
                    
            except Exception as db_error:
                logger.error(f"❌ Database connection test failed: {db_error}")
                return jsonify({'success': False, 'error': 'Veritabanı bağlantı hatası'}), 500
            
            result = api.get_subscription_info_internal(company_id)
            logger.info(f"🔍 Internal subscription result: {result}")
            if result and result.get('success'):
                return jsonify(result)
            else:
                error_msg = result.get('error', 'Şirket bulunamadı') if result else 'Şirket bulunamadı'
                return jsonify({'success': False, 'error': error_msg}), 404
            
        except Exception as e:
            logger.error(f"❌ Abonelik bilgileri getirme hatası: {e}")
            return jsonify({'success': False, 'error': 'Veri getirme başarısız'}), 500

    return bp
