import requests
import logging
import threading
import time
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Unified Notification Service for SmartSafe AI.
    Handles Telegram (Text & Photo), and other notification channels.
    """
    
    def __init__(self, db_adapter=None):
        self.db_adapter = db_adapter
        # Global fallback token from environment
        self.global_bot_token = os.getenv('DEFAULT_TELEGRAM_BOT_TOKEN')
        # Telegram API URLs
        self.telegram_msg_url = "https://api.telegram.org/bot{token}/sendMessage"
        self.telegram_photo_url = "https://api.telegram.org/bot{token}/sendPhoto"
        self.telegram_updates_url = "https://api.telegram.org/bot{token}/getUpdates"
        
        # Polling state
        self._last_update_id = 0
        self._polling_active = False
        
        if self.global_bot_token:
            self._start_polling_thread()

    def _start_polling_thread(self):
        """Starts a background thread to listen for /start commands"""
        # Flask debug modundayken çift başlamayı engelle
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            return

        if not self.global_bot_token:
            logger.error("🛑 NotificationService: DEFAULT_TELEGRAM_BOT_TOKEN is MISSING!")
            return

        if self._polling_active:
            return
        
        # Botun geçerli olup olmadığını kontrol et ve kimliğini doğrula
        try:
            me_url = f"https://api.telegram.org/bot{self.global_bot_token}/getMe"
            me_res = requests.get(me_url, timeout=int(os.environ.get('SOCKET_TIMEOUT', 10))).json()
            if me_res.get('ok'):
                bot_info = me_res.get('result', {})
                logger.info(f"✨ Telegram Bot Doğrulandı: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            else:
                logger.error(f"🛑 Telegram Bot Token GEÇERSİZ! API Yanıtı: {me_res}")
                return
        except Exception as e:
            logger.error(f"⚠️ Telegram Bot bağlantısı kurulamadı: {e}")
            # Yine de devam et, belki geçici bir sorundur

        self._polling_active = True
        thread = threading.Thread(target=self._poll_updates_loop, daemon=True)
        thread.start()
        logger.info("🚀 NotificationService: Telegram polling thread (Main) başlatıldı.")

    def _poll_updates_loop(self):
        """Background loop to check for new messages to the bot"""
        offset = 0
        logger.info("📡 Telegram polling loop started...")
        
        while self._polling_active:
            try:
                url = f"https://api.telegram.org/bot{self.global_bot_token}/getUpdates"
                params = {"offset": offset, "timeout": int(os.environ.get('TELEGRAM_TIMEOUT', 30))}
                response = requests.get(url, params=params, timeout=int(os.environ.get('TELEGRAM_POLLING_TIMEOUT', 35)))
                
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get('result', []):
                        self._handle_telegram_update(update)
                        offset = update['update_id'] + 1
                elif response.status_code == 409:
                    # Conflict: Başka bir instance çalışıyor
                    logger.warning("⚠️ Telegram Polling Conflict: Başka bir bot örneği çalışıyor olabilir. 10 saniye bekleniyor...")
                    time.sleep(int(os.environ.get('TELEGRAM_RETRY_DELAY', 10)))
                elif response.status_code == 401:
                    logger.error("🛑 Telegram Bot Token GEÇERSİZ! Polling durduruluyor.")
                    self._polling_active = False
                else:
                    logger.error(f"❌ Telegram API Error: {response.status_code} - {response.text}")
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"❌ NotificationService Polling Error: {e}")
                time.sleep(10)

    def _handle_telegram_update(self, update: Dict[str, Any]):
        """Processes a single update from Telegram"""
        try:
            message = update.get('message', {})
            text = message.get('text', '')
            chat_id = str(message.get('chat', {}).get('id'))
            
            # 1. /start komutu ile bağlama (Özel sohbet veya grup)
            if text.startswith('/start'):
                # Extract potential company_id from /start [token]
                parts = text.split()
                if len(parts) > 1:
                    company_id = parts[1]
                    logger.info(f"✨ NotificationService: Received /start with company_id: {company_id} from chat_id: {chat_id}")
                    self._auto_register_company_chat(company_id, chat_id)
                else:
                    # Provide ID to the user if they just sent /start
                    welcome_msg = (
                        f"👋 *SmartSafe AI Bildirim Botuna Hoş Geldiniz!*\n\n"
                        f"Chat ID'niz: `{chat_id}`\n\n"
                        f"Eğer bu bir grup ise, lütfen `/start [ŞİRKET_ID]` formatında mesaj göndererek bağlayın."
                    )
                    self._send_telegram_message(self.global_bot_token, chat_id, welcome_msg)

            # 2. Gruba yeni eklenme olayı (Bazı durumlarda /start yerine bu gelir)
            elif 'new_chat_members' in message:
                for member in message['new_chat_members']:
                    # Eğer eklenen biz isek (bot)
                    if member.get('is_bot') and member.get('username') == os.getenv('DEFAULT_TELEGRAM_BOT_USERNAME'):
                        welcome_group = (
                            "👋 *SmartSafe Bildirim Botu Gruba Eklendi!*\n\n"
                            "Bağlantıyı tamamlamak için lütfen bu gruba `/start [ŞİRKET_ID]` mesajını gönderin.\n"
                            "Şirket ID'nizi paneldeki Ayarlar sayfasında bulabilirsiniz."
                        )
                        self._send_telegram_message(self.global_bot_token, chat_id, welcome_group)
                    
        except Exception as e:
            logger.error(f"❌ Error handling telegram update: {e}")

    def _auto_register_company_chat(self, company_id: str, chat_id: str):
        """Updates the company record with the chat_id from Telegram"""
        if not self.db_adapter:
            return
            
        try:
            # First check if company exists
            check_query = "SELECT company_id FROM companies WHERE company_id = %s"
            company = self.db_adapter.execute_query(check_query, (company_id,), fetch_one=True)
            
            if company:
                update_query = """
                    UPDATE companies 
                    SET telegram_chat_id = %s, 
                        telegram_notifications = true,
                        violation_alerts = true
                    WHERE company_id = %s
                """
                self.db_adapter.execute_query(update_query, (chat_id, company_id))
                
                # Notify the user on Telegram
                self._send_telegram_message(self.global_bot_token, chat_id, "✅ *SmartSafe AI Bağlantısı Başarılı!*\n\nİhlal bildirimleri artık bu kanal üzerinden size anlık olarak iletilecektir.")
                logger.info(f"✅ Auto-registered chat_id {chat_id} for company {company_id}")
            else:
                logger.warning(f"⚠️ Received /start for non-existent company: {company_id}")
                
        except Exception as e:
            logger.error(f"❌ Failed to auto-register company chat: {e}")

    def send_violation_notification(self, violation_event: Dict[str, Any]):
        """
        Process a violation event and send notifications through preferred channels.
        """
        try:
            company_id = violation_event.get('company_id')
            if not company_id:
                logger.error("❌ NotificationService: company_id missing in violation event")
                return

            # Fetch company notification settings
            settings = self._get_company_notification_settings(company_id)
            if not settings:
                logger.warning(f"ℹ️ NotificationService: Could not find settings for company {company_id}")
                return

            # Check if alerts are globally enabled for this company
            if not settings.get('violation_alerts', True):
                logger.debug(f"ℹ️ NotificationService: Violation alerts disabled for company {company_id}")
                return

            # Format the message
            message = self._format_violation_message(violation_event)
            snapshot_path = violation_event.get('snapshot_path')

            # Telegram Notifications
            if settings.get('telegram_notifications') and settings.get('telegram_chat_id'):
                # Use company specific token if available, else use global fallback
                bot_token = settings.get('telegram_bot_token') or self.global_bot_token
                chat_id = settings['telegram_chat_id']
                
                if not bot_token:
                    logger.warning(f"❌ NotificationService: Telegram enabled for {company_id} but no bot token provided (company or global)")
                    return
                
                # If there's a snapshot, send as photo with caption
                if snapshot_path:
                    # Resolve absolute path for internal file access
                    from detection.snapshot_manager import get_snapshot_manager
                    full_path = str(get_snapshot_manager().get_snapshot_path(snapshot_path))
                    
                    if os.path.exists(full_path):
                        self._send_telegram_photo(bot_token, chat_id, full_path, message)
                    else:
                        logger.warning(f"⚠️ Snapshot file not found at {full_path}, sending text only.")
                        self._send_telegram_message(bot_token, chat_id, message)
                else:
                    self._send_telegram_message(bot_token, chat_id, message)

            # Future: Other channels (Email, SMS, Webhook)
            
        except Exception as e:
            logger.error(f"❌ NotificationService Error: {e}")

    def send_test_notification(self, company_id: str) -> bool:
        """Sistem testi için bir deneme bildirimi gönderir"""
        try:
            settings = self._get_company_notification_settings(company_id)
            if not settings:
                logger.warning(f"⚠️ NotificationService: Test failed, settings not found for {company_id}")
                return False

            chat_id = settings.get('telegram_chat_id')
            if not chat_id:
                logger.warning(f"⚠️ NotificationService: Test failed, chat_id not found for {company_id}")
                return False

            message = (
                "🚀 *SmartSafe AI: Sistem Testi*\n\n"
                "Telegram bağlantınız başarıyla doğrulandı.\n"
                "Artık tüm güvenlik ihlallerini buradan takip edebilirsiniz. 🔥"
            )
            
            bot_token = settings.get('telegram_bot_token') or self.global_bot_token
            return self._send_telegram_message(bot_token, chat_id, message)
        except Exception as e:
            logger.error(f"❌ NotificationService Test Error: {e}")
            return False

    def _get_company_notification_settings(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Fetch notification settings from database"""
        if not self.db_adapter:
            logger.error("❌ NotificationService: db_adapter not initialized")
            return None

        try:
            query = """
                SELECT 
                    violation_alerts, 
                    telegram_notifications, 
                    telegram_bot_token, 
                    telegram_chat_id,
                    email_notifications,
                    sms_notifications
                FROM companies 
                WHERE company_id = %s
            """
            result = self.db_adapter.execute_query(query, (company_id,), fetch_one=True)
            
            if result:
                if isinstance(result, dict):
                    return result
                # Support for tuple results (fallback)
                return {
                    'violation_alerts': result[0],
                    'telegram_notifications': result[1],
                    'telegram_bot_token': result[2],
                    'telegram_chat_id': result[3],
                    'email_notifications': result[4],
                    'sms_notifications': result[5]
                }
            return None
        except Exception as e:
            logger.error(f"❌ NotificationService: Failed to fetch settings: {e}")
            return None

    def _format_violation_message(self, event: Dict[str, Any]) -> str:
        """Format a human-readable message for the violation"""
        v_type = str(event.get('violation_type', 'Bilinmeyen İhlal'))
        camera_id = str(event.get('camera_id') or event.get('dvr_channel_id', 'Bilinmeyen Kamera'))
        severity = str(event.get('severity', 'warning')).upper()
        
        # Temizlik: Markdown'u bozan karakterleri (özellikle alt çizgileri) temizle veya değiştir
        v_type = v_type.replace('_', ' ').replace('*', '').title()
        camera_id = camera_id.replace('_', ' ').replace('*', '')
        
        # Format time if it's a timestamp
        start_time = event.get('start_time')
        if isinstance(start_time, (int, float)):
            from datetime import datetime
            start_time = datetime.fromtimestamp(start_time).strftime('%H:%M:%S')
        
        emoji = "🚨" if severity == "CRITICAL" else "⚠️"
        
        # Use Markdown for formatting
        message = (
            f"{emoji} *YENİ İHLAL TESPİT EDİLDİ*\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📌 *Tür:* {v_type}\n"
            f"📹 *Kamera:* {camera_id}\n"
            f"⏰ *Zaman:* {start_time}\n"
            f"⚡ *Önem:* {severity}\n"
            f"━━━━━━━━━━━━━━━"
        )
        return message

    def _send_telegram_message(self, token: str, chat_id: str, text: str):
        """Send message via Telegram Bot API"""
        try:
            url = self.telegram_msg_url.format(token=token)
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=int(os.environ.get('TELEGRAM_TIMEOUT', 10)))
            if response.status_code == 200:
                logger.info(f"✅ Telegram notification sent to {chat_id}")
                return True
            else:
                logger.error(f"❌ Telegram API Error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Telegram Service Error: {e}")
            return False

    def _send_telegram_photo(self, token: str, chat_id: str, photo_path: str, caption: str):
        """Send photo via Telegram Bot API"""
        try:
            url = self.telegram_photo_url.format(token=token)
            with open(photo_path, 'rb') as photo:
                files = {"photo": photo}
                payload = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown"
                }
                response = requests.post(url, data=payload, files=files, timeout=int(os.environ.get('TELEGRAM_PHOTO_TIMEOUT', 15)))
                
            if response.status_code == 200:
                logger.info(f"✅ Telegram photo notification sent to {chat_id}")
                return True
            else:
                logger.error(f"❌ Telegram API Photo Error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram photo: {e}")
            return False

# Singleton instance accessor
_notification_service = None

def get_notification_service(db_adapter=None):
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(db_adapter)
    elif db_adapter and _notification_service.db_adapter is None:
        _notification_service.db_adapter = db_adapter
    return _notification_service
