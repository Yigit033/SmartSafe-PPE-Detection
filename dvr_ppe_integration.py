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
    
    def start_dvr_detection(self, dvr_id: str, channel: int, company_id: str, detection_mode: str = 'construction', use_sh17: bool = False) -> Dict[str, Any]:
        """DVR kanalından PPE detection başlatır"""
        
        try:
            # Stream ID oluştur
            stream_id = f"dvr_{dvr_id}_ch{channel:02d}"
            
            # RTSP URL oluştur (şirket/dvr bazlı dinamik bilgilerle)
            dvr_system = self.db_adapter.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                raise RuntimeError(f"DVR system not found for company={company_id} dvr_id={dvr_id}")

            rtsp_url = (
                f"rtsp://{dvr_system['ip_address']}:{dvr_system.get('rtsp_port', 554)}"
                f"/user={dvr_system['username']}&password={dvr_system['password']}"
                f"&channel={channel}&stream=0.sdp"
            )
            
            logger.info(f"🎥 Starting DVR detection: {stream_id} - {rtsp_url}")
            logger.info(f"🔧 Detection System: {'SH17' if use_sh17 else 'Klasik'}")
            
            # Detection thread'i başlat
            detection_thread = threading.Thread(
                target=self.process_dvr_stream,
                args=(stream_id, rtsp_url, company_id, detection_mode, use_sh17),
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
                "detection_mode": detection_mode,
                "detection_system": "SH17" if use_sh17 else "Klasik"
            }
            
        except Exception as e:
            logger.error(f"❌ DVR detection start error: {e}")
            return {"success": False, "error": str(e)}
    
    def process_dvr_stream(self, stream_id: str, rtsp_url: str, company_id: str, detection_mode: str, use_sh17: bool = False):
        """RTSP stream'i işler ve PPE detection yapar"""
        
        logger.info(f"🔄 Processing DVR stream: {stream_id}")
        logger.info(f"🔧 Detection System: {'SH17' if use_sh17 else 'Klasik'}")
        
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
                    
                    # PPE Detection yap - SH17 veya Klasik sistem
                    detection_start = time.time()
                    try:
                        if use_sh17 and hasattr(self, 'sh17_manager'):
                            # SH17 detection
                            ppe_result = self.sh17_manager.detect_ppe(frame, detection_mode, 0.5)
                            detection_time = time.time() - detection_start
                            
                            # SH17 sonuçlarını klasik formata çevir
                            ppe_result = self._convert_sh17_to_classic_format(ppe_result, detection_mode)
                        else:
                            # Klasik detection
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
    
    def _convert_sh17_to_classic_format(self, sh17_result: List[Dict], detection_mode: str) -> Dict[str, Any]:
        """SH17 sonuçlarını klasik PPE formatına çevirir"""
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
        
        # SH17 Model Manager entegrasyonu
        try:
            from models.sh17_model_manager import SH17ModelManager
            self.sh17_manager = SH17ModelManager()
            self.sh17_manager.load_models()
            self.sh17_available = True
            logger.info("✅ SH17 Model Manager entegre edildi")
        except Exception as e:
            logger.warning(f"⚠️ SH17 Model Manager yüklenemedi: {e}")
            self.sh17_available = False
        
    def start_dvr_ppe_detection(self, dvr_id: str, channels: List[int], company_id: str, detection_mode: str = 'construction') -> Dict[str, Any]:
        """Birden fazla DVR kanalında PPE detection başlatır"""
        
        # SH17 kullanımını kontrol et
        use_sh17 = self.sh17_available and detection_mode in ['construction', 'manufacturing', 'chemical', 'food_beverage', 'warehouse_logistics', 'energy', 'petrochemical', 'marine_shipyard', 'aviation']
        
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