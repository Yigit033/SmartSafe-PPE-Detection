import threading
import time
import logging
from datetime import datetime
from database.database_adapter import get_db_adapter

logger = logging.getLogger(__name__)

class ScheduleManager:
    """
    Kameralar ve DVR kanalları için zaman çizelgesini yöneten servis.
    Her dakika veritabanını kontrol eder ve planlanan saatlere göre 
    algılama (detection) başlatır veya durdurur.
    """
    
    def __init__(self, app_instance=None):
        self.app_instance = app_instance
        self.db = get_db_adapter()
        self.running = False
        self.thread = None
        self._last_check_minute = -1

    def start(self):
        """Servisi başlatır."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("🕒 ScheduleManager started")

    def stop(self):
        """Servisi durdurur."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("🕒 ScheduleManager stopped")

    def _run_loop(self):
        """Ana kontrol döngüsü."""
        while self.running:
            now = datetime.now()
            current_minute = now.minute
            
            # Her dakikada sadece bir kez kontrol et
            if current_minute != self._last_check_minute:
                try:
                    self._check_schedules(now)
                    self._last_check_minute = current_minute
                except Exception as e:
                    logger.error(f"❌ Schedule check error: {e}")
            
            time.sleep(10) # 10 saniyede bir uyanıp dakikayı kontrol et

    def _check_schedules(self, now):
        """Zaman çizelgelerini veritabanından okur ve uygular."""
        if self.app_instance and not self.app_instance.ensure_database_initialized():
            logger.error("❌ Database not ready for schedule check")
            return

        # Sunucu UTC kullanıyorsa yerel saate (UTC+3) çevirelim
        from datetime import timedelta
        local_now = now + timedelta(hours=3) # UTC+3 ofseti
        
        db_day = (local_now.weekday() + 1) % 7
        current_time_str = local_now.strftime("%H:%M:%S")
        
        # Her dakikada bir kontrol logu basabiliriz
        logger.info(f"🕒 [SCHEDULER] Checking rules for: Day {db_day}, Time {current_time_str}")

        query = """
            SELECT * FROM camera_schedules 
            WHERE is_enabled = TRUE AND (day_of_week = %s OR day_of_week = 7)
        """
        schedules = self.db.execute_query(query, (db_day,))
        
        if not schedules:
            return

        for sched in schedules:
            camera_id = sched['camera_id']
            camera_type = sched['camera_type']
            company_id = sched['company_id']
            
            # Zaman formatını güvenli hale getirelim
            # start_time ve end_time tipine göre işle (timedelta veya string)
            start_val = sched['start_time']
            end_val = sched['end_time']
            
            # string'e çevirip karşılaştıralım (HH:MM:SS formatında olduklarından emin olalım)
            start_time = str(start_val) if not hasattr(start_val, 'strftime') else start_val.strftime("%H:%M:%S")
            end_time = str(end_val) if not hasattr(end_val, 'strftime') else end_val.strftime("%H:%M:%S")

            camera_key = f"{company_id}_{camera_id}"
            
            is_active_window = start_time <= current_time_str <= end_time
            
            # App instance üzerinden mevcut durumu kontrol et
            is_running = self.app_instance.is_detection_running(camera_key) if self.app_instance else False

            if is_active_window:
                logger.info(f"🔎 [SCHEDULER] Match: {camera_key} | Window: {start_time}-{end_time} | Running: {is_running}")

            if is_active_window and not is_running:
                logger.info(f"🚀 [SCHEDULE] Triggering Start for {camera_key}")
                self._trigger_start(company_id, camera_id, camera_type)
            
            elif not is_active_window and is_running:
                logger.info(f"🛑 [SCHEDULE] Triggering Stop for {camera_key}")
                self._trigger_stop(company_id, camera_id)

    def _trigger_start(self, company_id, camera_id, camera_type):
        """Internal API çağrısı ile algılamayı başlatır."""
        # Flask instance içindeki start_detection metodunu tetikle
        if not self.app_instance:
            return
        
        try:
            # Not: Bu çağrılar app.py içindeki asıl mantığı tetiklemeli.
            # Local request simülasyonu veya doğrudan metod çağrısı.
            self.app_instance.internal_start_detection(company_id, camera_id, camera_type)
        except Exception as e:
            logger.error(f"❌ Failed to start scheduled detection for {camera_id}: {e}")

    def _trigger_stop(self, company_id, camera_id):
        """Internal API çağrısı ile algılamayı durdurur."""
        if not self.app_instance:
            return
            
        try:
            self.app_instance.internal_stop_detection(company_id, camera_id)
        except Exception as e:
            logger.error(f"❌ Failed to stop scheduled detection for {camera_id}: {e}")

# Singleton instance
_manager = None

def get_schedule_manager(app_instance=None):
    global _manager
    if _manager is None:
        _manager = ScheduleManager(app_instance)
    return _manager
