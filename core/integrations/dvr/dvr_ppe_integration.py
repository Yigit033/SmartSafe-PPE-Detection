#!/usr/bin/env python3
"""
DVR-PPE Detection Integration Module
DVR RTSP stream'lerini PPE detection sistemine entegre eder
"""

import cv2
import threading
import time
import queue
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np

# Import existing modules
from integrations.cameras.ppe_detection_manager import PPEDetectionManager
from database.database_adapter import get_db_adapter
from detection.violation_tracker import get_violation_tracker
from detection.snapshot_manager import get_snapshot_manager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 3.1  RTSP URL TEMPLATES — Marka bazlı doğru format otomatik seçilir
# ─────────────────────────────────────────────────────────────────────────────
# MAIN-STREAM URL TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────
RTSP_TEMPLATES = {
    'hikvision': 'rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch:03d}01',
    'dahua':     'rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0',
    'axis':      'rtsp://{user}:{pwd}@{ip}:{port}/axis-media/media.amp',
    'samsung':   'rtsp://{user}:{pwd}@{ip}:{port}/profile3/media.smp',
    'bosch':     'rtsp://{user}:{pwd}@{ip}:{port}/video?inst=1&h26x=4',
    'hanwha':    'rtsp://{user}:{pwd}@{ip}:{port}/profile3/media.smp',
    'reolink':   'rtsp://{user}:{pwd}@{ip}:{port}/h264Preview_0{ch:02d}_main',
    'tp_link':   'rtsp://{user}:{pwd}@{ip}:{port}/stream1',
    'uniview':   'rtsp://{user}:{pwd}@{ip}:{port}/media/video{ch}',
    'xm':        'rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream=0.sdp',
    'generic':   'rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream=0.sdp',
}

# ─────────────────────────────────────────────────────────────────────────────
# SUB-STREAM URL TEMPLATES — Detection için önerilir (640x360, düşük FPS)
# Sub-stream kullanmak CPU yükünü ~4x azaltır.
# ─────────────────────────────────────────────────────────────────────────────
RTSP_SUB_TEMPLATES = {
    'hikvision': 'rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch:03d}02',
    'dahua':     'rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1',
    'axis':      'rtsp://{user}:{pwd}@{ip}:{port}/axis-media/media.amp?streamprofile=Quality',
    'samsung':   'rtsp://{user}:{pwd}@{ip}:{port}/profile5/media.smp',
    'hanwha':    'rtsp://{user}:{pwd}@{ip}:{port}/profile5/media.smp',
    'reolink':   'rtsp://{user}:{pwd}@{ip}:{port}/h264Preview_0{ch:02d}_sub',
    'uniview':   'rtsp://{user}:{pwd}@{ip}:{port}/media/video{ch}/1',
    'xm':        'rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream=1.sdp',
    'generic':   'rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream=1.sdp',
}

# Birden fazla URL formatı denenecek markalar (bazı ürünler karışık firmware kullanır)
RTSP_FALLBACKS = {
    'hikvision': [
        'rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch:03d}01',
        'rtsp://{user}:{pwd}@{ip}:{port}/h264/ch{ch}/main/av_stream',
        'rtsp://{user}:{pwd}@{ip}:{port}/Streaming/channels/{ch}01',
    ],
    'dahua': [
        'rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0',
        'rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1',
    ],
    'generic': [
        'rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream=0.sdp',
        'rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0',
        'rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch:03d}01',
        'rtsp://{user}:{pwd}@{ip}:{port}/h264/ch{ch}/main/av_stream',
    ],
}

# ── Exponential backoff ayarları ────────────────────────────────────────────
BACKOFF_BASE_SEC = 5
BACKOFF_MAX_SEC = 300
MAX_RECONNECT_ATTEMPTS = 15


def get_rtsp_url_for_brand(
    ip: str, port: int, user: str, pwd: str, channel: int,
    brand: str = 'generic'
) -> str:
    """
    Marka bazlı RTSP URL döndürür (main-stream).
    """
    import urllib.parse
    _u = urllib.parse.quote(user, safe='')
    _p = urllib.parse.quote(pwd, safe='')
    brand_key = brand.lower().replace('-', '_').replace(' ', '_')
    template = RTSP_TEMPLATES.get(brand_key, RTSP_TEMPLATES['generic'])
    return template.format(ip=ip, port=port, user=_u, pwd=_p, ch=channel)


def get_sub_stream_url(
    ip: str, port: int, user: str, pwd: str, channel: int,
    brand: str = 'generic'
) -> Optional[str]:
    """
    Marka bazlı SUB-STREAM URL döndürür.
    Detection için önerilir — düşük çözünürlük, düşük bandwidth.
    Sub-stream template yoksa None döner.
    """
    import urllib.parse
    _u = urllib.parse.quote(user, safe='')
    _p = urllib.parse.quote(pwd, safe='')
    brand_key = brand.lower().replace('-', '_').replace(' ', '_')
    template = RTSP_SUB_TEMPLATES.get(brand_key)
    if not template:
        return None
    try:
        return template.format(ip=ip, port=port, user=_u, pwd=_p, ch=channel)
    except Exception:
        return None


def get_rtsp_url_fallbacks(
    ip: str, port: int, user: str, pwd: str, channel: int,
    brand: str = 'generic'
) -> list:
    """Bir marka için denenecek RTSP URL listesi döndürür."""
    import urllib.parse
    _u = urllib.parse.quote(user, safe='')
    _p = urllib.parse.quote(pwd, safe='')
    brand_key = brand.lower().replace('-', '_').replace(' ', '_')
    templates = RTSP_FALLBACKS.get(brand_key) or RTSP_FALLBACKS['generic']
    return [t.format(ip=ip, port=port, user=_u, pwd=_p, ch=channel) for t in templates]


class DVRStreamProcessor:
    """DVR RTSP stream'lerini PPE detection için işler"""
    
    def __init__(self):
        self.active_streams = {}  # {stream_id: cv2.VideoCapture}
        self.detection_threads = {}  # {stream_id: Thread}
        self.results_queue = queue.Queue(maxsize=200)  # Bounded queue — bellek dolmasını önler
        self.ppe_manager = PPEDetectionManager()
        self.db_adapter = get_db_adapter()
        self._lock = threading.Lock()  # Thread-safe dict operasyonları için
        self.sh17_manager = None  # EnhancedPPEDetectionManager tarafından set edilir

        # Performance settings
        self.frame_skip = 3  # Her 3 frame'de bir detection
        self.max_frames_per_second = 10  # Maksimum FPS
        self.detection_confidence = 0.5

        logger.info("✅ DVR Stream Processor initialized")
    
    def start_dvr_detection(self, dvr_id: str, channel: int, company_id: str, detection_mode: Optional[str] = None, use_sh17: bool = False) -> Dict[str, Any]:
        """DVR kanalından PPE detection başlatır"""

        try:
            # Stream ID oluştur
            stream_id = f"dvr_{dvr_id}_ch{channel:02d}"

            # Zaten çalışıyorsa yeniden başlatma
            with self._lock:
                if stream_id in self.detection_threads and self.detection_threads[stream_id].is_alive():
                    logger.warning(f"⚠️ DVR detection already running: {stream_id}")
                    return {"success": True, "stream_id": stream_id, "already_running": True}

            # RTSP URL oluştur (şirket/dvr bazlı dinamik bilgilerle)
            dvr_system = self.db_adapter.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                raise RuntimeError(f"DVR system not found for company={company_id} dvr_id={dvr_id}")

            import urllib.parse
            safe_username = urllib.parse.quote(dvr_system['username'])
            safe_password = urllib.parse.quote(dvr_system['password'])

            # ── ONVIF-first URI resolution ──────────────────────────────
            rtsp_url = None
            try:
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                stream_handler = get_stream_handler()
                onvif_uri = stream_handler._try_onvif_stream_uri(
                    dvr_system['ip_address'],
                    dvr_system['username'],
                    dvr_system['password'],
                    channel
                )
                if onvif_uri:
                    rtsp_url = onvif_uri
                    logger.info(f"✅ ONVIF URI kullanılıyor (detection): kanal {channel}")
            except Exception as onvif_err:
                logger.debug(f"ℹ️ ONVIF URI alınamadı, XM fallback: {onvif_err}")

            # Fallback: marka bazlı RTSP URL — sub-stream tercih et (detection için yeterli)
            if not rtsp_url:
                brand = dvr_system.get('dvr_type', 'generic') or 'generic'
                _ip = dvr_system['ip_address']
                _port = int(dvr_system.get('rtsp_port', 554))
                _user = dvr_system['username']
                _pwd = dvr_system['password']

                # Sub-stream önce dene (640x360, CPU tasarrufu)
                sub_url = get_sub_stream_url(_ip, _port, _user, _pwd, channel, brand)
                if sub_url:
                    rtsp_url = sub_url
                    logger.info(f"📡 Sub-stream URL ({brand}): {rtsp_url}")
                else:
                    rtsp_url = get_rtsp_url_for_brand(_ip, _port, _user, _pwd, channel, brand)
                    logger.info(f"🏷️ Main-stream URL ({brand}): {rtsp_url}")

            # Resolve sector/detection_mode from company configuration when not provided
            if not detection_mode:
                try:
                    company = self.db_adapter.get_company_info(company_id) if hasattr(self.db_adapter, 'get_company_info') else None
                    if company:
                        if isinstance(company, dict):
                            detection_mode = company.get('sector') or detection_mode
                        elif isinstance(company, (list, tuple)) and len(company) >= 5:
                            detection_mode = company[4] or detection_mode
                except Exception as sec_err:
                    logger.warning(f"⚠️ DVR sector resolve failed for company {company_id}: {sec_err}")

            detection_mode = detection_mode or 'construction'
            logger.info(f"🎥 Starting DVR detection: {stream_id} - {rtsp_url}")
            logger.info(f"🔧 Detection System: {'SH17' if use_sh17 and self.sh17_manager else 'Klasik'}")

            # Detection thread'i başlat
            detection_thread = threading.Thread(
                target=self.process_dvr_stream,
                args=(stream_id, rtsp_url, company_id, detection_mode, use_sh17),
                daemon=True,
                name=f"dvr-detection-{stream_id}"
            )

            with self._lock:
                self.detection_threads[stream_id] = detection_thread
            detection_thread.start()

            # Database'e detection session kaydet
            self.save_detection_session(stream_id, dvr_id, company_id, channel, detection_mode)

            return {
                "success": True,
                "stream_id": stream_id,
                "rtsp_url": rtsp_url,
                "channel": channel,
                "detection_mode": detection_mode,
                "detection_system": "SH17" if (use_sh17 and self.sh17_manager) else "Klasik"
            }

        except Exception as e:
            logger.error(f"❌ DVR detection start error: {e}")
            return {"success": False, "error": str(e)}
    
    def process_dvr_stream(self, stream_id: str, rtsp_url: str, company_id: str, detection_mode: str, use_sh17: bool = False):
        """
        RTSP stream'i işler ve PPE detection yapar.

        Production-grade: FFmpegStreamReader + exponential backoff reconnect.
        FFmpeg yoksa cv2 fallback çalışır.
        """

        # sh17 gerçekten kullanılabilir mi kontrol et
        _use_sh17 = use_sh17 and (self.sh17_manager is not None)
        logger.info(f"🔄 Processing DVR stream: {stream_id}")
        logger.info(f"🔧 Detection System: {'SH17' if _use_sh17 else 'Klasik'}")

        from integrations.cameras.ffmpeg_stream_reader import create_stream_reader

        retry_count = 0
        reader = None

        while retry_count < MAX_RECONNECT_ATTEMPTS:
            # Stop sinyali kontrolü
            with self._lock:
                if stream_id not in self.detection_threads:
                    logger.info(f"🛑 {stream_id}: Stop sinyali alındı (reconnect döngüsü).")
                    return

            try:
                # Stream reader oluştur (FFmpeg pref, cv2 fallback)
                reader = create_stream_reader(
                    rtsp_url,
                    width=640, height=360,  # Sub-stream boyutu — detection için yeterli
                    fps=self.max_frames_per_second,
                    prefer_ffmpeg=True,
                )

                if not reader.start():
                    raise ConnectionError(f"Stream açılamadı: {rtsp_url[:60]}")

                if retry_count > 0:
                    logger.info(f"✅ {stream_id}: Reconnect başarılı (deneme {retry_count})")

                retry_count = 0  # Başarılı bağlantı — sıfırla
                logger.info(f"✅ RTSP stream açıldı: {stream_id} ({reader.__class__.__name__})")

                frame_count = 0
                detection_count = 0
                consecutive_empty = 0
                start_time = time.time()

                while reader.is_alive():
                    # Stop sinyali kontrolü (thread-safe)
                    with self._lock:
                        running = stream_id in self.detection_threads
                    if not running:
                        break

                    frame = reader.read_frame()
                    if frame is None:
                        consecutive_empty += 1
                        if consecutive_empty >= 30:  # ~6 saniye boş frame
                            raise ConnectionError(f"Stream kesildi: {consecutive_empty} boş frame")
                        time.sleep(0.2)
                        continue

                    consecutive_empty = 0
                    frame_count += 1

                    # Frame skip uygula
                    if frame_count % self.frame_skip != 0:
                        continue

                    # 🎯 PPE Detection yap — SH17 veya Klasik
                    detection_start = time.time()
                    try:
                        if _use_sh17:
                            ppe_result = self.sh17_manager.detect_ppe(frame, detection_mode, confidence=0.25)
                            detection_time = time.time() - detection_start
                            ppe_result = self._convert_sh17_to_classic_format_production(ppe_result, detection_mode, frame)
                        else:
                            ppe_result = self.ppe_manager.detect_ppe_comprehensive(frame, detection_mode)
                            detection_time = time.time() - detection_start
                        
                        if ppe_result and ppe_result.get('success', False):
                            detection_count += 1
                            
                            # 🚨 VIOLATION TRACKER ENTEGRASYONU
                            # DVR stream'den gelen ihlalleri event-based olarak takip et
                            try:
                                violations_list = ppe_result.get('ppe_violations', [])
                                
                                for person_violation in violations_list:
                                    person_bbox = person_violation.get('bbox', [])
                                    missing_ppe = person_violation.get('missing_ppe', [])
                                    
                                    # Violation tracker'a gönder
                                    violation_tracker = get_violation_tracker()
                                    
                                    new_violations, ended_violations = violation_tracker.process_detection(
                                        camera_id=stream_id,  # DVR stream_id'yi camera_id olarak kullan
                                        company_id=company_id,
                                        person_bbox=person_bbox,
                                        violations=missing_ppe,
                                        frame_snapshot=frame
                                    )
                                    
                                    # 📸 YENİ İHLALLER İÇİN SNAPSHOT ÇEK
                                    for new_violation in new_violations:
                                        try:
                                            # Kişi görünürlük kontrolü
                                            person_visible = True
                                            if person_bbox and len(person_bbox) == 4:
                                                px1, py1, px2, py2 = person_bbox
                                                if px1 < 0 or py1 < 0 or px2 > frame.shape[1] or py2 > frame.shape[0]:
                                                    person_visible = False
                                                person_area = (px2 - px1) * (py2 - py1)
                                                frame_area = frame.shape[0] * frame.shape[1]
                                                if person_area < (frame_area * 0.05):
                                                    person_visible = False
                                            
                                            if not person_visible:
                                                logger.warning(f"⚠️ DVR: Kişi frame'de yeterince görünür değil, snapshot atlandı")
                                                self.db_adapter.add_violation_event(new_violation)
                                                continue
                                            
                                            # Snapshot çek
                                            snapshot_manager = get_snapshot_manager()
                                            snapshot_path = snapshot_manager.capture_violation_snapshot(
                                                frame=frame,
                                                company_id=company_id,
                                                camera_id=stream_id,
                                                person_id=new_violation['person_id'],
                                                violation_type=new_violation['violation_type'],
                                                person_bbox=person_bbox,
                                                event_id=new_violation['event_id']
                                            )
                                            
                                            if snapshot_path:
                                                new_violation['snapshot_path'] = snapshot_path
                                                logger.info(f"📸 DVR VIOLATION SNAPSHOT SAVED: {snapshot_path} - {new_violation['violation_type']}")
                                            else:
                                                logger.warning(f"⚠️ DVR Snapshot kaydedilemedi: {new_violation['violation_type']} - {stream_id}")
                                            
                                            # Database'e kaydet
                                            self.db_adapter.add_violation_event(new_violation)
                                            logger.info(f"🚨 DVR NEW VIOLATION: {new_violation['violation_type']} - {new_violation['event_id']}")
                                        
                                        except Exception as ve:
                                            logger.error(f"❌ DVR violation event save error: {ve}")
                                    
                                    # ✅ BİTEN İHLALLER İÇİN SNAPSHOT ÇEK
                                    for ended_violation in ended_violations:
                                        try:
                                            # Çözüm snapshot'ı çek
                                            try:
                                                snapshot_manager = get_snapshot_manager()
                                                resolution_snapshot_path = snapshot_manager.capture_violation_snapshot(
                                                    frame=frame,
                                                    company_id=company_id,
                                                    camera_id=stream_id,
                                                    person_id=ended_violation['person_id'],
                                                    violation_type=f"{ended_violation['violation_type']}_resolved",
                                                    person_bbox=person_bbox,
                                                    event_id=ended_violation['event_id']
                                                )
                                                
                                                if resolution_snapshot_path:
                                                    logger.info(f"📸 DVR RESOLUTION SNAPSHOT SAVED: {resolution_snapshot_path} - {ended_violation['violation_type']} resolved")
                                                else:
                                                    logger.warning(f"⚠️ DVR Resolution snapshot kaydedilemedi: {ended_violation['violation_type']} - {stream_id}")
                                            except Exception as snap_error:
                                                logger.error(f"❌ DVR resolution snapshot error: {snap_error}")
                                                import traceback
                                                logger.error(f"❌ DVR Snapshot traceback: {traceback.format_exc()}")
                                                resolution_snapshot_path = None
                                            
                                            # Event'i güncelle
                                            self.db_adapter.update_violation_event(
                                                ended_violation['event_id'],
                                                {
                                                    'end_time': ended_violation['end_time'],
                                                    'duration_seconds': ended_violation['duration_seconds'],
                                                    'status': ended_violation['status'],
                                                    'resolution_snapshot_path': resolution_snapshot_path
                                                }
                                            )
                                            
                                            # Person violation stats'ı güncelle
                                            self.db_adapter.update_person_violation_stats(
                                                person_id=ended_violation['person_id'],
                                                company_id=company_id,
                                                violation_type=ended_violation['violation_type'],
                                                duration_seconds=ended_violation['duration_seconds']
                                            )
                                            
                                            logger.info(f"✅ DVR VIOLATION RESOLVED: {ended_violation['violation_type']} - Duration: {ended_violation['duration_seconds']}s")
                                        
                                        except Exception as ve:
                                            logger.error(f"❌ DVR violation event update error: {ve}")
                            
                            except Exception as vt_error:
                                logger.error(f"❌ DVR violation tracker error: {vt_error}")
                            
                            # Sonuçları kaydet (eski sistem)
                            self.save_detection_result(stream_id, company_id, ppe_result, detection_time)
                            
                            # Real-time dashboard için queue'ya ekle
                            self.results_queue.put({
                                'stream_id': stream_id,
                                'timestamp': datetime.now().isoformat(),
                                'ppe_result': ppe_result,
                                'detection_time': detection_time,
                                'frame_count': frame_count,
                                'detection_system': 'SH17' if use_sh17 else 'Klasik'
                            })
                            
                            # Performance logging
                            if detection_count % 30 == 0:  # Her 30 detection'da bir log
                                fps = detection_count / (time.time() - start_time)
                                logger.info(f"📊 {stream_id} - FPS: {fps:.2f}, Detection Time: {detection_time:.3f}s, System: {'SH17' if use_sh17 else 'Klasik'}")
                        else:
                            logger.warning(f"⚠️ PPE detection failed for {stream_id}: {ppe_result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        logger.error(f"❌ PPE detection error for {stream_id}: {e}")
                        # Continue processing other frames
                    
                    # Frame rate control
                    time.sleep(1 / self.max_frames_per_second)

                # İç döngü bitti — eğer stop sinyali geldiyse çık
                with self._lock:
                    if stream_id not in self.detection_threads:
                        break  # Stop sinyali — reconnect yapma

                # Döngü bitti ama stop sinyali yoksa stream kopmuştur
                raise ConnectionError(f"Stream döngüsü bitti — reader artık alive değil")

            except Exception as e:
                # ── Exponential backoff reconnect ──────────────────────
                retry_count += 1
                if reader:
                    try:
                        reader.stop()
                    except Exception:
                        pass
                    reader = None

                if retry_count >= MAX_RECONNECT_ATTEMPTS:
                    logger.error(
                        f"❌ {stream_id}: Max reconnect ({MAX_RECONNECT_ATTEMPTS}) aşıldı. "
                        f"Detection kalıcı olarak durduruluyor."
                    )
                    break

                wait = min(BACKOFF_BASE_SEC * (2 ** (retry_count - 1)), BACKOFF_MAX_SEC)
                logger.warning(
                    f"⚠️ {stream_id}: {e} — {wait}s sonra yeniden bağlanılacak "
                    f"(deneme {retry_count}/{MAX_RECONNECT_ATTEMPTS})"
                )
                time.sleep(wait)

        # ── Final cleanup ─────────────────────────────────────────────
        if reader:
            try:
                reader.stop()
            except Exception:
                pass
        with self._lock:
            self.active_streams.pop(stream_id, None)
            self.detection_threads.pop(stream_id, None)

        logger.info(f"🛑 DVR stream processing stopped: {stream_id}")
    
    def _convert_sh17_to_classic_format_production(self, sh17_result: List[Dict], detection_mode: str, frame: np.ndarray) -> Dict[str, Any]:
        """🎯 PRODUCTION-GRADE: SH17 sonuçlarını klasik PPE formatına çevirir - Advanced spatial reasoning ile"""
        try:
            if not sh17_result:
                return self._create_empty_result()
            
            # Kişileri ve PPE itemlarını ayır
            people = [d for d in sh17_result if isinstance(d, dict) and d.get('class_name') == 'person']
            helmets_pos = [d for d in sh17_result if isinstance(d, dict) and d.get('class_name') in ['helmet','hard_hat','Hardhat','Safety Helmet']]
            vests_pos = [d for d in sh17_result if isinstance(d, dict) and d.get('class_name') in ['safety_vest','vest','Safety Vest']]
            shoes_pos = [d for d in sh17_result if isinstance(d, dict) and d.get('class_name') in ['safety_shoes','shoes','Safety Shoes']]
            
            people_detected = len(people)
            ppe_violations = []
            ppe_compliant = 0
            
            # 🎯 PRODUCTION-GRADE: Her kişi için advanced PPE association
            from detection.utils.detection_utils import DetectionUtils
            
            for person_idx, person in enumerate(people):
                person_bbox = person.get('bbox', [])
                if len(person_bbox) != 4:
                    continue
                
                # Proximity scoring ile PPE association
                associated_ppe = DetectionUtils.associate_ppe_with_person(
                    person_bbox, 
                    helmets_pos + vests_pos + shoes_pos,
                    confidence_threshold=0.25
                )
                
                # Compliance kontrolü
                has_helmet = 'helmet' in associated_ppe
                has_vest = 'safety_vest' in associated_ppe or 'vest' in associated_ppe
                
                if has_helmet and has_vest:
                    ppe_compliant += 1
                else:
                    missing_ppe = []
                    if not has_helmet:
                        missing_ppe.append('Baret eksik')
                    if not has_vest:
                        missing_ppe.append('Yelek eksik')
                    
                    violation = {
                        'person_id': f"person_{person_idx + 1}",
                        'missing_ppe': missing_ppe,
                        'confidence': person.get('confidence', 0.0),
                        'bbox': person_bbox,
                        'ppe_status': {
                            'compliant': False,
                            'missing_ppe': missing_ppe,
                            'detected_ppe': list(associated_ppe.keys())
                        }
                    }
                    ppe_violations.append(violation)
            
            return {
                'success': True,
                'people_detected': people_detected,
                'compliant_people': ppe_compliant,
                'ppe_compliant': ppe_compliant,
                'ppe_violations': ppe_violations,
                'detection_system': 'SH17-Production',
                'detection_mode': detection_mode,
                'total_people': people_detected,
                'violations_count': len(ppe_violations)
            }
            
        except Exception as e:
            logger.error(f"❌ SH17 production format conversion error: {e}")
            return self._create_empty_result()
    
    def _convert_sh17_to_classic_format(self, sh17_result: List[Dict], detection_mode: str) -> Dict[str, Any]:
        """SH17 sonuçlarını klasik PPE formatına çevirir (Legacy)"""
        try:
            if not sh17_result:
                return self._create_empty_result()
            
            # SH17 sonuçlarını işle
            people_detected = 0
            ppe_compliant = 0
            ppe_violations = []
            
            for detection in sh17_result:
                class_name = detection.get('class_name', '')
                confidence = detection.get('confidence', 0.0)
                bbox = detection.get('bbox', [])
                
                # Person detection
                if class_name == 'person':
                    people_detected += 1
                    
                    # PPE compliance kontrolü
                    ppe_status = self._analyze_sh17_ppe_compliance(sh17_result, detection_mode)
                    
                    if ppe_status.get('compliant', False):
                        ppe_compliant += 1
                    else:
                        violation = {
                            'person_id': f"person_{people_detected}",
                            'missing_ppe': ppe_status.get('missing_ppe', ['Gerekli PPE Eksik']),
                            'confidence': confidence,
                            'bbox': bbox,
                            'ppe_status': ppe_status
                        }
                        ppe_violations.append(violation)
            
            return {
                'success': True,
                'people_detected': people_detected,
                'ppe_compliant': ppe_compliant,
                'ppe_violations': ppe_violations,
                'detection_system': 'SH17',
                'detection_mode': detection_mode
            }
            
        except Exception as e:
            logger.error(f"❌ SH17 format conversion error: {e}")
            return self._create_empty_result()
    
    def _analyze_sh17_ppe_compliance(self, detections: List[Dict], sector: str) -> Dict[str, Any]:
        """SH17 detection sonuçlarından PPE compliance analizi"""
        try:
            # Sektör bazlı gerekli PPE'ler
            sector_requirements = {
                'construction': ['helmet', 'safety_vest'],
                'manufacturing': ['helmet', 'safety_vest', 'gloves'],
                'chemical': ['helmet', 'respirator', 'gloves', 'safety_glasses'],
                'food_beverage': ['hair_net', 'gloves', 'apron'],
                'warehouse_logistics': ['helmet', 'safety_vest', 'safety_shoes'],
                'energy': ['helmet', 'safety_vest', 'safety_shoes', 'gloves'],
                'petrochemical': ['helmet', 'respirator', 'safety_vest', 'gloves'],
                'marine_shipyard': ['helmet', 'life_vest', 'safety_shoes'],
                'aviation': ['aviation_helmet', 'reflective_vest', 'ear_protection']
            }
            
            required_ppe = sector_requirements.get(sector, ['helmet', 'safety_vest'])
            detected_ppe = []
            
            # Tespit edilen PPE'leri topla
            for detection in detections:
                class_name = detection.get('class_name', '')
                if class_name in ['helmet', 'safety_vest', 'gloves', 'safety_shoes', 'safety_glasses', 'face_mask_medical']:
                    detected_ppe.append(class_name)
            
            # Compliance kontrolü
            missing_ppe = [item for item in required_ppe if item not in detected_ppe]
            compliant = len(missing_ppe) == 0
            
            return {
                'compliant': compliant,
                'missing_ppe': missing_ppe,
                'detected_ppe': detected_ppe,
                'required_ppe': required_ppe
            }
            
        except Exception as e:
            logger.error(f"❌ SH17 compliance analysis error: {e}")
            return {'compliant': False, 'missing_ppe': ['Analysis Error']}
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """Boş detection sonucu oluşturur"""
        return {
            'success': False,
            'people_detected': 0,
            'ppe_compliant': 0,
            'ppe_violations': [],
            'error': 'No detections found'
        }
    
    def stop_dvr_detection(self, stream_id: str) -> Dict[str, Any]:
        """DVR detection'ı durdurur (thread-safe)"""

        try:
            logger.info(f"🛑 Stopping DVR detection: {stream_id}")

            # Detection thread'ini durdur — dict'ten sil, thread while döngüsünden çıkar
            thread_to_join = None
            with self._lock:
                thread_to_join = self.detection_threads.pop(stream_id, None)

            # Thread'in durmasını bekle (max 3 saniye)
            if thread_to_join and thread_to_join.is_alive():
                thread_to_join.join(timeout=3.0)

            # Stream'i kapat
            with self._lock:
                cap = self.active_streams.pop(stream_id, None)
            if cap:
                cap.release()

            # Database'de session'ı güncelle
            self.update_detection_session(stream_id, 'stopped')

            return {"success": True, "stream_id": stream_id}

        except Exception as e:
            logger.error(f"❌ Stop DVR detection error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_active_detections(self) -> List[str]:
        """Aktif detection'ları döndürür (thread-safe)"""
        with self._lock:
            return [sid for sid, t in self.detection_threads.items() if t.is_alive()]
    
    def get_detection_results(self, stream_id: str, limit: int = 50) -> List[Dict]:
        """Detection sonuçlarını döndürür"""
        try:
            return self.db_adapter.get_dvr_detection_results(stream_id, limit)
        except Exception as e:
            logger.error(f"❌ Get detection results error: {e}")
            return []
    
    def save_detection_result(self, stream_id: str, company_id: str, ppe_result: Dict, detection_time: float):
        """Detection sonucunu database'e kaydeder"""
        try:
            result_data = {
                'stream_id': stream_id,
                'company_id': company_id,
                'total_people': ppe_result.get('total_people', 0),
                'compliant_people': ppe_result.get('compliant_people', 0),
                'violations_count': ppe_result.get('violations_count', 0),
                'missing_ppe': json.dumps(ppe_result.get('missing_ppe', [])),
                'detection_confidence': ppe_result.get('confidence', 0.0),
                'detection_time': detection_time,
                'frame_timestamp': datetime.now().isoformat()
            }
            
            self.db_adapter.add_dvr_detection_result(result_data)
            
        except Exception as e:
            logger.error(f"❌ Save detection result error: {e}")
    
    def save_detection_session(self, stream_id: str, dvr_id: str, company_id: str, channel: int, detection_mode: str):
        """Detection session'ını database'e kaydeder"""
        try:
            session_data = {
                'session_id': stream_id,
                'dvr_id': dvr_id,
                'company_id': company_id,
                'channels': json.dumps([channel]),
                'detection_mode': detection_mode,
                'status': 'active',
                'start_time': datetime.now().isoformat()
            }
            
            self.db_adapter.add_dvr_detection_session(session_data)
            
        except Exception as e:
            logger.error(f"❌ Save detection session error: {e}")
    
    def update_detection_session(self, stream_id: str, status: str):
        """Detection session'ını günceller"""
        try:
            self.db_adapter.update_dvr_detection_session(stream_id, {
                'status': status,
                'end_time': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"❌ Update detection session error: {e}")


class EnhancedPPEDetectionManager:
    """DVR ve normal kameralar için gelişmiş PPE detection"""
    
    def __init__(self):
        self.ppe_manager = PPEDetectionManager()
        self.dvr_processor = DVRStreamProcessor()
        self.sh17_manager = None
        self.sh17_available = False

        # SH17 Model Manager entegrasyonu
        try:
            from models.sh17_model_manager import SH17ModelManager
            self.sh17_manager = SH17ModelManager()
            self.sh17_manager.load_models()
            self.sh17_available = True
            # DVRStreamProcessor'a da sh17_manager'ı ver — artık DVR stream'leri de SH17 kullanır
            self.dvr_processor.sh17_manager = self.sh17_manager
            logger.info("✅ SH17 Model Manager entegre edildi (DVR stream processor dahil)")
        except Exception as e:
            logger.warning(f"⚠️ SH17 Model Manager yüklenemedi: {e}")
            self.sh17_available = False
        
    def start_dvr_ppe_detection(self, dvr_id: str, channels: List[int], company_id: str, detection_mode: str = 'construction') -> Dict[str, Any]:
        """Birden fazla DVR kanalında PPE detection başlatır"""

        # Kapasite kontrolü — maksimum 64 eş zamanlı DVR kanalı
        MAX_DVR_CHANNELS = 64
        current_active = len(self.dvr_processor.get_active_detections())
        if current_active + len(channels) > MAX_DVR_CHANNELS:
            return {
                "success": False,
                "error": f"Maksimum eş zamanlı DVR kanal limitine ulaşıldı ({MAX_DVR_CHANNELS}). Şu an {current_active} kanal aktif.",
                "active_channels": current_active,
                "max_channels": MAX_DVR_CHANNELS
            }

        # SH17 kullanımını kontrol et
        use_sh17 = self.sh17_available and detection_mode in [
            'construction', 'manufacturing', 'chemical', 'food_beverage',
            'warehouse_logistics', 'energy', 'petrochemical', 'marine_shipyard', 'aviation'
        ]

        if use_sh17:
            logger.info(f"🎯 SH17 detection mode aktif: {detection_mode}")
        else:
            logger.info(f"🔄 Klasik detection mode: {detection_mode}")

        active_detections = []

        for channel in channels:
            result = self.dvr_processor.start_dvr_detection(
                dvr_id, channel, company_id, detection_mode, use_sh17
            )

            if result['success']:
                active_detections.append(result['stream_id'])
                logger.info(f"✅ DVR detection started: {result['stream_id']} - {'SH17' if use_sh17 else 'Klasik'}")
            else:
                logger.error(f"❌ DVR detection failed for channel {channel}: {result.get('error', 'Unknown error')}")

        return {
            "success": len(active_detections) > 0,
            "active_detections": active_detections,
            "total_channels": len(channels),
            "successful_channels": len(active_detections),
            "detection_system": "SH17" if use_sh17 else "Klasik"
        }
    
    def stop_dvr_ppe_detection(self, dvr_id: str, channels: List[int] = None) -> Dict[str, Any]:
        """DVR PPE detection'ı durdurur"""
        
        stopped_detections = []
        
        if channels is None:
            # Tüm aktif detection'ları durdur
            active_detections = self.dvr_processor.get_active_detections()
            for stream_id in active_detections:
                if dvr_id in stream_id:
                    result = self.dvr_processor.stop_dvr_detection(stream_id)
                    if result['success']:
                        stopped_detections.append(stream_id)
        else:
            # Belirtilen kanalları durdur
            for channel in channels:
                stream_id = f"dvr_{dvr_id}_ch{channel:02d}"
                result = self.dvr_processor.stop_dvr_detection(stream_id)
                if result['success']:
                    stopped_detections.append(stream_id)
        
        return {
            "success": len(stopped_detections) > 0,
            "stopped_detections": stopped_detections
        }
    
    def get_dvr_detection_status(self, dvr_id: str) -> Dict[str, Any]:
        """DVR detection durumunu döndürür"""
        
        active_detections = self.dvr_processor.get_active_detections()
        dvr_detections = [d for d in active_detections if dvr_id in d]
        
        # Son detection sonuçlarını al
        detection_results = []
        for stream_id in dvr_detections:
            results = self.dvr_processor.get_detection_results(stream_id, limit=10)
            detection_results.extend(results)
        
        total_violations = sum(r.get('violations_count', 0) for r in detection_results)
        
        return {
            "dvr_id": dvr_id,
            "active_detections": dvr_detections,
            "detection_results": detection_results,
            "total_violations": total_violations,
            "total_frames_processed": sum(r.get('frame_count', 0) for r in detection_results)
        }


# Global instance
dvr_ppe_manager = EnhancedPPEDetectionManager()

def get_dvr_ppe_manager() -> EnhancedPPEDetectionManager:
    """Global DVR PPE manager instance'ını döndürür"""
    return dvr_ppe_manager 