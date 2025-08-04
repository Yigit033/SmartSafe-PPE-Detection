#!/usr/bin/env python3
"""
DVR Stream Handler - RTSP to Browser Video Conversion
"""

import cv2
import numpy as np
import threading
import time
import base64
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class DVRStreamHandler:
    """Handles DVR stream conversion for browser playback"""
    
    def __init__(self):
        self.active_streams: Dict[str, Dict] = {}
        self.frame_buffers: Dict[str, list] = {}
        self.max_buffer_size = 10
        
    def start_stream(self, stream_id: str, rtsp_url: str) -> bool:
        """Start streaming from RTSP URL"""
        try:
            if stream_id in self.active_streams:
                logger.warning(f"⚠️ Stream already active: {stream_id}")
                return True
                
            # Initialize stream info
            self.active_streams[stream_id] = {
                'rtsp_url': rtsp_url,
                'status': 'starting',
                'start_time': time.time(),
                'frame_count': 0,
                'error_count': 0
            }
            
            self.frame_buffers[stream_id] = []
            
            # Start streaming thread
            thread = threading.Thread(
                target=self._stream_worker,
                args=(stream_id, rtsp_url),
                daemon=True
            )
            thread.start()
            
            logger.info(f"✅ Stream started: {stream_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Start stream error: {e}")
            return False
    
    def stop_stream(self, stream_id: str) -> bool:
        """Stop streaming"""
        try:
            if stream_id in self.active_streams:
                self.active_streams[stream_id]['status'] = 'stopping'
                logger.info(f"🛑 Stream stopping: {stream_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Stop stream error: {e}")
            return False
    
    def get_latest_frame(self, stream_id: str) -> Optional[str]:
        """Get latest frame as base64 encoded JPEG"""
        try:
            if stream_id in self.frame_buffers and self.frame_buffers[stream_id]:
                return self.frame_buffers[stream_id][-1]
            return None
        except Exception as e:
            logger.error(f"❌ Get frame error: {e}")
            return None
    
    def get_stream_status(self, stream_id: str) -> Optional[Dict]:
        """Get stream status"""
        try:
            if stream_id in self.active_streams:
                return self.active_streams[stream_id]
            return None
        except Exception as e:
            logger.error(f"❌ Get status error: {e}")
            return None
    
    def _stream_worker(self, stream_id: str, rtsp_url: str):
        """Worker thread for streaming"""
        cap = None
        try:
            logger.info(f"🎥 Opening RTSP stream: {rtsp_url}")
            cap = cv2.VideoCapture(rtsp_url)
            
            if not cap.isOpened():
                logger.error(f"❌ Failed to open RTSP stream: {rtsp_url}")
                self.active_streams[stream_id]['status'] = 'error'
                return
            
            self.active_streams[stream_id]['status'] = 'active'
            logger.info(f"✅ RTSP stream opened successfully: {stream_id}")
            
            while self.active_streams[stream_id]['status'] == 'active':
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"⚠️ Failed to read frame from {stream_id}")
                    self.active_streams[stream_id]['error_count'] += 1
                    time.sleep(0.1)
                    continue
                
                # Convert frame to JPEG
                _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                
                # Add to buffer
                buffer = self.frame_buffers[stream_id]
                buffer.append(jpeg_base64)
                
                # Keep only latest frames
                if len(buffer) > self.max_buffer_size:
                    buffer.pop(0)
                
                self.active_streams[stream_id]['frame_count'] += 1
                
                # Add small delay to control frame rate
                time.sleep(0.033)  # ~30 FPS
                
        except Exception as e:
            logger.error(f"❌ Stream worker error for {stream_id}: {e}")
            if stream_id in self.active_streams:
                self.active_streams[stream_id]['status'] = 'error'
        finally:
            if cap:
                cap.release()
            if stream_id in self.active_streams:
                self.active_streams[stream_id]['status'] = 'stopped'
            logger.info(f"🛑 Stream worker stopped: {stream_id}")

# Global stream handler instance
stream_handler = DVRStreamHandler()

def get_stream_handler() -> DVRStreamHandler:
    """Get global stream handler instance"""
    return stream_handler 