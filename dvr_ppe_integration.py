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
from ppe_detection_manager import PPEDetectionManager
from database_adapter import get_db_adapter

logger = logging.getLogger(__name__)

class DVRStreamProcessor:
    """DVR RTSP stream'lerini PPE detection için işler"""
    
    def __init__(self):
        self.active_streams = {}  # {stream_id: cv2.VideoCapture}
        self.detection_threads = {}  # {stream_id: Thread}
        self.results_queue = queue.Queue()
        self.ppe_manager = PPEDetectionManager()
        self.db_adapter = get_db_adapter()
        
        # Performance settings
        self.frame_skip = 3  # Her 3 frame'de bir detection
        self.max_frames_per_second = 10  # Maksimum FPS
        self.detection_confidence = 0.5
        
        logger.info("✅ DVR Stream Processor initialized")
    
    def start_dvr_detection(self, dvr_id: str, channel: int, company_id: str, detection_mode: str = 'construction') -> Dict[str, Any]:
        """DVR kanalından PPE detection başlatır"""
        
        try:
            # Stream ID oluştur
            stream_id = f"dvr_{dvr_id}_ch{channel:02d}"
            
            # RTSP URL oluştur
            rtsp_url = f"rtsp://nehu:yesilgross@192.168.1.109:554/ch{channel:02d}/main"
            
            logger.info(f"🎥 Starting DVR detection: {stream_id} - {rtsp_url}")
            
            # Detection thread'i başlat
            detection_thread = threading.Thread(
                target=self.process_dvr_stream,
                args=(stream_id, rtsp_url, company_id, detection_mode),
                daemon=True
            )
            
            self.detection_threads[stream_id] = detection_thread
            detection_thread.start()
            
            # Database'e detection session kaydet
            self.save_detection_session(stream_id, dvr_id, company_id, channel, detection_mode)
            
            return {
                "success": True,
                "stream_id": stream_id,
                "rtsp_url": rtsp_url,
                "channel": channel,
                "detection_mode": detection_mode
            }
            
        except Exception as e:
            logger.error(f"❌ DVR detection start error: {e}")
            return {"success": False, "error": str(e)}
    
    def process_dvr_stream(self, stream_id: str, rtsp_url: str, company_id: str, detection_mode: str):
        """RTSP stream'i işler ve PPE detection yapar"""
        
        logger.info(f"🔄 Processing DVR stream: {stream_id}")
        
        try:
            # RTSP stream'i aç
            cap = cv2.VideoCapture(rtsp_url)
            
            if not cap.isOpened():
                logger.error(f"❌ Failed to open RTSP stream: {rtsp_url}")
                return
            
            # Stream'i active streams'e ekle
            self.active_streams[stream_id] = cap
            
            frame_count = 0
            detection_count = 0
            start_time = time.time()
            
            logger.info(f"✅ RTSP stream opened successfully: {stream_id}")
            
            while stream_id in self.detection_threads:
                try:
                    # Frame oku
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning(f"⚠️ Failed to read frame from {stream_id}")
                        time.sleep(1)
                        continue
                    
                    frame_count += 1
                    
                    # Frame skip uygula
                    if frame_count % self.frame_skip != 0:
                        continue
                    
                    # PPE Detection yap - Enhanced error handling
                    detection_start = time.time()
                    try:
                        ppe_result = self.ppe_manager.detect_ppe_comprehensive(frame, detection_mode)
                        detection_time = time.time() - detection_start
                        
                        if ppe_result and ppe_result.get('success', False):
                            detection_count += 1
                            
                            # Sonuçları kaydet
                            self.save_detection_result(stream_id, company_id, ppe_result, detection_time)
                            
                            # Real-time dashboard için queue'ya ekle
                            self.results_queue.put({
                                'stream_id': stream_id,
                                'timestamp': datetime.now().isoformat(),
                                'ppe_result': ppe_result,
                                'detection_time': detection_time,
                                'frame_count': frame_count
                            })
                            
                            # Performance logging
                            if detection_count % 30 == 0:  # Her 30 detection'da bir log
                                fps = detection_count / (time.time() - start_time)
                                logger.info(f"📊 {stream_id} - FPS: {fps:.2f}, Detection Time: {detection_time:.3f}s")
                        else:
                            logger.warning(f"⚠️ PPE detection failed for {stream_id}: {ppe_result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        logger.error(f"❌ PPE detection error for {stream_id}: {e}")
                        # Continue processing other frames
                    
                    # Frame rate control
                    time.sleep(1 / self.max_frames_per_second)
                    
                except Exception as e:
                    logger.error(f"❌ Stream processing error for {stream_id}: {e}")
                    time.sleep(1)
            
            # Cleanup
            cap.release()
            if stream_id in self.active_streams:
                del self.active_streams[stream_id]
            
            logger.info(f"🛑 DVR stream processing stopped: {stream_id}")
            
        except Exception as e:
            logger.error(f"❌ DVR stream processing error: {e}")
    
    def stop_dvr_detection(self, stream_id: str) -> Dict[str, Any]:
        """DVR detection'ı durdurur"""
        
        try:
            logger.info(f"🛑 Stopping DVR detection: {stream_id}")
            
            # Thread'i durdur
            if stream_id in self.detection_threads:
                del self.detection_threads[stream_id]
            
            # Stream'i kapat
            if stream_id in self.active_streams:
                cap = self.active_streams[stream_id]
                cap.release()
                del self.active_streams[stream_id]
            
            # Database'de session'ı güncelle
            self.update_detection_session(stream_id, 'stopped')
            
            return {"success": True, "stream_id": stream_id}
            
        except Exception as e:
            logger.error(f"❌ Stop DVR detection error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_active_detections(self) -> List[str]:
        """Aktif detection'ları döndürür"""
        return list(self.detection_threads.keys())
    
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
        
    def start_dvr_ppe_detection(self, dvr_id: str, channels: List[int], company_id: str, detection_mode: str = 'construction') -> Dict[str, Any]:
        """Birden fazla DVR kanalında PPE detection başlatır"""
        
        active_detections = []
        
        for channel in channels:
            result = self.dvr_processor.start_dvr_detection(
                dvr_id, channel, company_id, detection_mode
            )
            
            if result['success']:
                active_detections.append(result['stream_id'])
                logger.info(f"✅ DVR detection started: {result['stream_id']}")
            else:
                logger.error(f"❌ DVR detection failed for channel {channel}: {result.get('error', 'Unknown error')}")
        
        return {
            "success": len(active_detections) > 0,
            "active_detections": active_detections,
            "total_channels": len(channels),
            "successful_channels": len(active_detections)
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