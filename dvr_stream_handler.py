#!/usr/bin/env python3
"""
DVR Stream Handler - Multi-Brand RTSP to Browser Video Conversion
Supports Hikvision, Dahua, Axis, and other DVR/NVR systems
"""

import cv2
import numpy as np
import threading
import time
import base64
import socket
import re
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

class DVRStreamHandler:
    """Advanced DVR stream handler with multi-brand support"""
    
    def __init__(self):
        self.active_streams: Dict[str, Dict] = {}
        self.frame_buffers: Dict[str, list] = {}
        self.max_buffer_size = 10
        self.connection_timeout = 5000  # 5 seconds
        self.read_timeout = 3000  # 3 seconds
        
        # DVR brand-specific URL patterns
        self.dvr_url_patterns = {
            'hikvision': [
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/ISAPI/Streaming/channels/{channel}01',
                '/ISAPI/Streaming/channels/{channel}02',
                '/ISAPI/Streaming/channels/{channel}03',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/cam/realmonitor?channel={channel}&subtype=0&authbasic=1',
                '/cam/realmonitor?channel={channel}&subtype=1&authbasic=1'
            ],
            'dahua': [
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/cam/realmonitor?channel={channel}&subtype=0&authbasic=1',
                '/cam/realmonitor?channel={channel}&subtype=1&authbasic=1',
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/ch{channel:02d}/main/0',
                '/ch{channel:02d}/main/1',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/cam/realmonitor?channel={channel}&subtype=0&stream=0',
                '/cam/realmonitor?channel={channel}&subtype=1&stream=1'
            ],
            'axis': [
                '/axis-media/media.amp?videocodec=h264&camera={channel}',
                '/axis-media/media.amp?videocodec=mjpeg&camera={channel}',
                '/axis-media/media.amp?camera={channel}',
                '/axis-media/media.amp?videocodec=h264&camera={channel}&resolution=1920x1080',
                '/axis-media/media.amp?videocodec=mjpeg&camera={channel}&resolution=1280x720'
            ],
            'generic': [
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/ch{channel:02d}/main/0',
                '/ch{channel:02d}/main/1',
                '/ch{channel:02d}/sub/0',
                '/ch{channel:02d}/sub/1',
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/live/ch{channel:02d}/main',
                '/live/ch{channel:02d}/sub',
                '/live/channel{channel}/main',
                '/live/channel{channel}/sub',
                '/live/camera{channel}/main',
                '/live/camera{channel}/sub',
                '/stream/ch{channel:02d}',
                '/stream/channel{channel}',
                '/stream/camera{channel}',
                '/video/ch{channel:02d}',
                '/video/channel{channel}',
                '/video/camera{channel}'
            ]
        }
        
    def detect_dvr_brand(self, ip_address: str, username: str, password: str, rtsp_port: int) -> str:
        """Detect DVR brand by testing common URL patterns"""
        try:
            # Test multiple channels for brand detection
            test_channels = [1, 2, 3]  # Test multiple channels
            test_urls = []
            
            for channel in test_channels:
                test_urls.extend([
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel}01",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel}&subtype=0",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel:02d}/main",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel:02d}/sub"
                ])
            
            for url in test_urls:
                try:
                    cap = cv2.VideoCapture(url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
                    if cap.isOpened():
                        cap.release()
                        if 'ISAPI' in url:
                            logger.info(f"✅ Detected Hikvision DVR via URL: {url}")
                            return 'hikvision'
                        elif 'cam/realmonitor' in url:
                            logger.info(f"✅ Detected Dahua DVR via URL: {url}")
                            return 'dahua'
                        elif '/ch' in url:
                            logger.info(f"✅ Detected Generic DVR via URL: {url}")
                            return 'generic'
                except Exception as e:
                    continue
            
            # Default to generic
            logger.info("ℹ️ Brand detection failed, using generic")
            return 'generic'
            
        except Exception as e:
            logger.warning(f"⚠️ Brand detection failed: {e}")
            return 'generic'
    
    def generate_rtsp_urls(self, ip_address: str, username: str, password: str, 
                          rtsp_port: int, channel_number: int, brand: str = None) -> List[str]:
        """Generate multiple RTSP URLs for a channel"""
        urls = []
        
        # Detect brand if not provided
        if not brand:
            brand = self.detect_dvr_brand(ip_address, username, password, rtsp_port)
            logger.info(f"🔍 Detected DVR brand: {brand}")
        
        # Get brand-specific patterns
        patterns = self.dvr_url_patterns.get(brand, self.dvr_url_patterns['generic'])
        
        # Generate URLs for this brand
        for pattern in patterns:
            try:
                path = pattern.format(channel=channel_number)
                url = f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}{path}"
                urls.append(url)
            except Exception as e:
                logger.warning(f"⚠️ Failed to generate URL for pattern {pattern}: {e}")
        
        # Add channel-specific variations based on channel number
        if channel_number <= 4:
            # For low channel numbers, try more variations
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        elif channel_number <= 8:
            # For medium channel numbers
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        else:
            # For high channel numbers, try more specific patterns
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/ch{channel_number:02d}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/channel{channel_number}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/camera{channel_number}"
            ])
        
        # Add brand-specific variations
        if brand == 'hikvision':
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel_number:02d}01",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel_number:02d}02",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel_number:02d}03"
            ])
        elif brand == 'dahua':
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&stream=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&stream=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&authbasic=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&authbasic=1"
            ])
        
        # Remove duplicates while preserving order
        unique_urls = []
        seen = set()
        for url in urls:
            if url not in seen:
                unique_urls.append(url)
                seen.add(url)
        
        logger.info(f"🎯 Generated {len(unique_urls)} RTSP URLs for channel {channel_number} (brand: {brand})")
        return unique_urls
    
    def test_network_connectivity(self, ip_address: str, rtsp_port: int) -> bool:
        """Test basic network connectivity to DVR"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip_address, rtsp_port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"❌ Network connectivity test failed: {e}")
            return False
    
    def start_stream(self, stream_id: str, rtsp_url: str, 
                    ip_address: str = None, username: str = None, 
                    password: str = None, rtsp_port: int = None, 
                    channel_number: int = None) -> bool:
        """Start streaming with enhanced URL handling"""
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
                'error_count': 0,
                'ip_address': ip_address,
                'username': username,
                'password': password,
                'rtsp_port': rtsp_port,
                'channel_number': channel_number
            }
            
            self.frame_buffers[stream_id] = []
            
            # Start streaming thread
            thread = threading.Thread(
                target=self._stream_worker,
                args=(stream_id, rtsp_url, ip_address, username, password, rtsp_port, channel_number),
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
                frame_data = self.frame_buffers[stream_id][-1]
                if frame_data and len(frame_data) > 0:
                    return frame_data
                else:
                    logger.warning(f"⚠️ Empty frame data for {stream_id}")
                    return None
            else:
                logger.warning(f"⚠️ No frame buffer for {stream_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Get frame error for {stream_id}: {e}")
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
    
    def _stream_worker(self, stream_id: str, rtsp_url: str, 
                      ip_address: str = None, username: str = None, 
                      password: str = None, rtsp_port: int = None, 
                      channel_number: int = None):
        """Enhanced worker thread for streaming with multiple URL fallbacks"""
        cap = None
        max_reconnect_attempts = 3
        reconnect_delay = 5  # seconds
        
        try:
            logger.info(f"🎥 Opening RTSP stream: {stream_id} -> {rtsp_url}")
            
            # Test network connectivity first
            if ip_address and rtsp_port:
                if not self.test_network_connectivity(ip_address, rtsp_port):
                    logger.error(f"❌ No network connectivity to {ip_address}:{rtsp_port}")
                    self.active_streams[stream_id]['status'] = 'error'
                    return
            
            # Generate multiple URLs to try
            urls_to_try = [rtsp_url]  # Start with original URL
            
            # Add brand-specific URLs if we have the parameters
            if all([ip_address, username, password, rtsp_port, channel_number]):
                brand_urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
                urls_to_try.extend(brand_urls)
                logger.info(f"🎯 Channel {channel_number}: Will try {len(urls_to_try)} different URL patterns")
            else:
                logger.warning(f"⚠️ Channel {channel_number}: Missing parameters for enhanced URL generation")
            
            # Try each URL
            cap = None
            successful_url = None
            
            for i, url in enumerate(urls_to_try):
                try:
                    logger.info(f"🔄 Channel {channel_number}: Trying RTSP URL {i+1}/{len(urls_to_try)}: {url}")
                    
                    cap = cv2.VideoCapture(url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.connection_timeout)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout)
                    
                    if cap.isOpened():
                        # Test if we can actually read a frame
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            logger.info(f"✅ Channel {channel_number}: Successfully opened RTSP stream: {url}")
                            successful_url = url
                            break
                        else:
                            logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL: {url}")
                            if cap:
                                cap.release()
                                cap = None
                            else:
                                logger.warning(f"⚠️ Channel {channel_number}: URL opened but no frame data: {url}")
                                cap.release()
                                cap = None
                    else:
                        logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL: {url}")
                        if cap:
                            cap.release()
                            cap = None
                        
                except Exception as e:
                    logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL {url}: {e}")
                    if cap:
                        cap.release()
                        cap = None
                    continue
            
            if not cap or not cap.isOpened():
                logger.error(f"❌ Failed to open any RTSP stream for {stream_id}")
                self.active_streams[stream_id]['status'] = 'error'
                return
            
            # Update stream info with successful URL
            self.active_streams[stream_id]['rtsp_url'] = successful_url
            self.active_streams[stream_id]['status'] = 'active'
            logger.info(f"✅ RTSP stream opened successfully: {stream_id} -> {successful_url}")
            
            # Immediately try to read a frame to ensure stream is working
            try:
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    # Convert test frame to JPEG and add to buffer
                    _, jpeg_data = cv2.imencode('.jpg', test_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                    
                    if stream_id in self.frame_buffers:
                        self.frame_buffers[stream_id].append(jpeg_base64)
                    
                    logger.info(f"✅ Initial frame captured for {stream_id}")
                else:
                    logger.warning(f"⚠️ Initial frame read failed for {stream_id}")
            except Exception as e:
                logger.warning(f"⚠️ Initial frame processing failed for {stream_id}: {e}")
            
            frame_count = 0
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while self.active_streams[stream_id]['status'] == 'active':
                try:
                    ret, frame = cap.read()
                    
                    if not ret or frame is None:
                        consecutive_errors += 1
                        logger.warning(f"⚠️ Failed to read frame from {stream_id} (error {consecutive_errors}/{max_consecutive_errors})")
                        
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"❌ Too many consecutive errors for {stream_id}, attempting reconnection...")
                            
                            # Try to reconnect
                            cap.release()
                            cap = None
                            
                            # Try reconnection with different URLs
                            for attempt in range(max_reconnect_attempts):
                                logger.info(f"🔄 Channel {channel_number}: Reconnection attempt {attempt + 1}/{max_reconnect_attempts}")
                                
                                if all([ip_address, username, password, rtsp_port, channel_number]):
                                    reconnect_urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
                                    logger.info(f"🔄 Channel {channel_number}: Trying {len(reconnect_urls)} URLs for reconnection")
                                else:
                                    reconnect_urls = [successful_url] if successful_url else urls_to_try
                                
                                for url in reconnect_urls:
                                    try:
                                        cap = cv2.VideoCapture(url)
                                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.connection_timeout)
                                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout)
                                        
                                        if cap.isOpened():
                                            ret, test_frame = cap.read()
                                            if ret and test_frame is not None:
                                                logger.info(f"✅ Channel {channel_number}: Reconnection successful: {url}")
                                                successful_url = url
                                                consecutive_errors = 0
                                                break
                                            else:
                                                cap.release()
                                                cap = None
                                    except Exception as e:
                                        logger.warning(f"⚠️ Channel {channel_number}: Reconnection attempt failed for {url}: {e}")
                                        if cap:
                                            cap.release()
                                            cap = None
                                
                                if cap and cap.isOpened():
                                    break
                                
                                time.sleep(reconnect_delay)
                            
                            if not cap or not cap.isOpened():
                                logger.error(f"❌ Reconnection failed for {stream_id}")
                        break
                    
                    time.sleep(0.1)
                    continue
                
                except Exception as e:
                    logger.error(f"❌ Frame processing error for {stream_id}: {e}")
                # Reset error count on successful frame
                    consecutive_errors = 0
                
                # Convert frame to JPEG
                try:
                    _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                    
                    # Add to buffer
                    if stream_id in self.frame_buffers:
                        buffer = self.frame_buffers[stream_id]
                        buffer.append(jpeg_base64)
                        
                        # Keep only latest frames
                        if len(buffer) > self.max_buffer_size:
                            buffer.pop(0)
                    
                    frame_count += 1
                    self.active_streams[stream_id]['frame_count'] = frame_count
                    
                    # Log progress every 30 frames
                    if frame_count % 30 == 0:
                        logger.info(f"📊 {stream_id}: {frame_count} frames captured")
                    
                except Exception as e:
                    logger.error(f"❌ Frame processing error for {stream_id}: {e}")
                
                # Add small delay to control frame rate
                time.sleep(0.033)  # ~30 FPS
                    
        except Exception as e:
                logger.error(f"❌ Stream read error for {stream_id}: {e}")
                consecutive_errors += 1
                time.sleep(0.1)
                
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