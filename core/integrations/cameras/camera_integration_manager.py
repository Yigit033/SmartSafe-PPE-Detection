#!/usr/bin/env python3
"""
SmartSafe AI - Professional Camera Integration Manager
Enterprise-grade camera management with IP Webcam, RTSP, DVR/NVR, and real camera support
"""

import cv2
import numpy as np
import requests
import socket
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import base64
from urllib.parse import urlparse, quote
import xml.etree.ElementTree as ET

# Violation tracking imports
from detection.violation_tracker import get_violation_tracker
from detection.snapshot_manager import get_snapshot_manager
from integrations.cameras.ffmpeg_stream_reader import create_stream_reader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DVRConfig:
    """DVR/NVR system configuration"""
    dvr_id: str
    name: str
    ip_address: str
    port: int = 80
    username: str = "admin"
    password: str = ""
    dvr_type: str = "generic"  # generic, hikvision, dahua, axis, etc.
    protocol: str = "http"  # http, https
    api_path: str = "/api"
    rtsp_port: int = 554
    max_channels: int = 16
    status: str = "inactive"  # active, inactive, error, testing
    last_test_time: Optional[datetime] = None
    connection_retries: int = 3
    timeout: int = 10
    auth_method: str = "auto"  # 'auto', 'digest', 'basic'
    
    def get_api_url(self) -> str:
        """Generate API URL for DVR"""
        return f"{self.protocol}://{self.ip_address}:{self.port}{self.api_path}"
    
    def get_rtsp_base_url(self) -> str:
        """Generate base RTSP URL for DVR"""
        if self.username and self.password:
            safe_username = quote(self.username)
            safe_password = quote(self.password)
            return f"rtsp://{safe_username}:{safe_password}@{self.ip_address}:{self.rtsp_port}"
        else:
            return f"rtsp://{self.ip_address}:{self.rtsp_port}"
    
    def get_auth_header(self) -> Dict[str, str]:
        """Generate authentication header for DVR API (Basic only — legacy)."""
        if self.username and self.password:
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        return {}

    def make_request(self, url: str, method: str = 'GET',
                     timeout: int = None, **kwargs) -> Optional[requests.Response]:
        """
        Digest-first, Basic-fallback HTTP request helper.

        Kurumsal kameraların %80'i Digest Auth kullanır.
        Bu method önce Digest dener, 401 alırsa Basic'e geçer.
        """
        from requests.auth import HTTPDigestAuth, HTTPBasicAuth
        _timeout = timeout or self.timeout

        if not self.username:
            try:
                return requests.request(method, url, timeout=_timeout, verify=False, **kwargs)
            except Exception:
                return None

        # Auth method resolution
        auth_methods = []
        if self.auth_method == 'digest':
            auth_methods = [HTTPDigestAuth(self.username, self.password)]
        elif self.auth_method == 'basic':
            auth_methods = [HTTPBasicAuth(self.username, self.password)]
        else:  # 'auto' — digest first, basic fallback
            auth_methods = [
                HTTPDigestAuth(self.username, self.password),
                HTTPBasicAuth(self.username, self.password),
            ]

        for auth in auth_methods:
            try:
                resp = requests.request(
                    method, url, auth=auth,
                    timeout=_timeout, verify=False, **kwargs
                )
                if resp.status_code == 401:
                    continue  # try next auth method
                return resp
            except Exception:
                continue

        return None

@dataclass
class DVRChannel:
    """DVR channel configuration"""
    channel_id: str
    name: str
    dvr_id: str
    channel_number: int
    status: str = "inactive"  # active, inactive, error
    resolution: Tuple[int, int] = (1920, 1080)
    fps: int = 25
    rtsp_path: str = ""
    http_path: str = ""
    last_test_time: Optional[datetime] = None
    
    def get_rtsp_url(self, dvr_config: DVRConfig) -> str:
        """Generate RTSP URL for this channel"""
        base_url = dvr_config.get_rtsp_base_url()
        if self.rtsp_path:
            return f"{base_url}{self.rtsp_path}"
        else:
            # Generic RTSP path format
            return f"{base_url}/ch{self.channel_number:02d}/main"
    
    def get_http_url(self, dvr_config: DVRConfig) -> str:
        """Generate HTTP URL for this channel"""
        base_url = f"{dvr_config.protocol}://{dvr_config.ip_address}:{dvr_config.port}"
        if self.http_path:
            return f"{base_url}{self.http_path}"
        else:
            # Generic HTTP path format
            return f"{base_url}/ch{self.channel_number:02d}/snapshot"

class DVRManager:
    """DVR/NVR system manager with database integration"""
    
    def __init__(self):
        self.dvr_systems = {}  # Memory cache
        self.dvr_channels = {}  # Memory cache
        self.active_streams = {}
        self.connection_threads = {}
        self.frame_buffers = {}
        self.last_frames = {}
        self.fps_counters = {}
        
        # Database integration
        from database.database_adapter import get_db_adapter
        self.db_adapter = get_db_adapter()
        
        logger.info("📺 DVR Manager initialized with database integration")
    
    def add_dvr_system(self, dvr_config: DVRConfig, company_id: str) -> Tuple[bool, str]:
        """Add DVR system with database persistence"""
        try:
            # Check if DVR already exists
            existing_dvr = self.db_adapter.get_dvr_system(company_id, dvr_config.dvr_id)
            
            if existing_dvr:
                # Update existing DVR
                logger.info(f"🔄 Updating existing DVR system: {dvr_config.name}")
                dvr_data = {
                    'name': dvr_config.name,
                    'ip_address': dvr_config.ip_address,
                    'port': dvr_config.port,
                    'username': dvr_config.username,
                    'password': dvr_config.password,
                    'dvr_type': dvr_config.dvr_type,
                    'protocol': dvr_config.protocol,
                    'api_path': dvr_config.api_path,
                    'rtsp_port': dvr_config.rtsp_port,
                    'max_channels': dvr_config.max_channels,
                    'status': 'active'
                }
                
                success = self.db_adapter.update_dvr_system(company_id, dvr_config.dvr_id, dvr_data)
                if success:
                    # Update memory cache
                    self.dvr_systems[dvr_config.dvr_id] = dvr_config
                    logger.info(f"✅ DVR system updated: {dvr_config.name}")
                    return True, "DVR system updated successfully"
                else:
                    logger.error(f"❌ Failed to update DVR system in database: {dvr_config.name}")
                    return False, "Database update error"
            else:
                # Add new DVR system
                logger.info(f"➕ Adding new DVR system: {dvr_config.name}")
                dvr_data = {
                    'dvr_id': dvr_config.dvr_id,
                    'name': dvr_config.name,
                    'ip_address': dvr_config.ip_address,
                    'port': dvr_config.port,
                    'username': dvr_config.username,
                    'password': dvr_config.password,
                    'dvr_type': dvr_config.dvr_type,
                    'protocol': dvr_config.protocol,
                    'api_path': dvr_config.api_path,
                    'rtsp_port': dvr_config.rtsp_port,
                    'max_channels': dvr_config.max_channels
                }
                
                success = self.db_adapter.add_dvr_system(company_id, dvr_data)
                if success:
                    # Add to memory cache
                    self.dvr_systems[dvr_config.dvr_id] = dvr_config
                    logger.info(f"✅ DVR system added: {dvr_config.name}")
                    return True, "DVR system added successfully"
                else:
                    logger.error(f"❌ Failed to add DVR system to database: {dvr_config.name}")
                    return False, "Database error"
                
        except Exception as e:
            logger.error(f"❌ Add DVR system error: {e}")
            return False, str(e)
    
    def get_dvr_systems(self, company_id: str) -> List[Dict[str, Any]]:
        """Get DVR systems from database with channel count"""
        try:
            # Get from database
            db_systems = self.db_adapter.get_dvr_systems(company_id)
            
            # Update memory cache and add channel count
            for system in db_systems:
                dvr_config = DVRConfig(
                    dvr_id=system['dvr_id'],
                    name=system['name'],
                    ip_address=system['ip_address'],
                    port=system['port'],
                    username=system['username'],
                    password=system['password'],
                    dvr_type=system['dvr_type'],
                    protocol=system['protocol'],
                    api_path=system['api_path'],
                    rtsp_port=system['rtsp_port'],
                    max_channels=system['max_channels'],
                    status=system['status']
                )
                self.dvr_systems[system['dvr_id']] = dvr_config
                
                # Add total_channels count
                channels = self.db_adapter.get_dvr_channels(company_id, system['dvr_id'])
                system['total_channels'] = len(channels) if channels else 0
            
            return db_systems
            
        except Exception as e:
            logger.error(f"❌ Get DVR systems error: {e}")
            return []
    
    def remove_dvr_system(self, dvr_id: str, company_id: str) -> Tuple[bool, str]:
        """Remove DVR system with database cleanup"""
        try:
            # Stop all active streams for this DVR
            channels = self.dvr_channels.get(dvr_id, [])
            for channel in channels:
                channel_id = channel.channel_id
                if channel_id in self.active_streams:
                    self.stop_dvr_stream(channel_id)
            
            # Remove from memory
            if dvr_id in self.dvr_systems:
                del self.dvr_systems[dvr_id]
            if dvr_id in self.dvr_channels:
                del self.dvr_channels[dvr_id]
            
            # Remove from database
            success = self.db_adapter.delete_dvr_system(company_id, dvr_id)
            if success:
                logger.info(f"✅ DVR system removed: {dvr_id}")
                return True, "DVR system removed successfully"
            else:
                logger.error(f"❌ Failed to remove DVR system from database: {dvr_id}")
                return False, "Database error"
                
        except Exception as e:
            logger.error(f"❌ Remove DVR system error: {e}")
            return False, str(e)
    
    def discover_cameras(self, dvr_id: str, company_id: str) -> List[Dict[str, Any]]:
        """Discover cameras on DVR system with database persistence"""
        if dvr_id not in self.dvr_systems:
            return []
        
        dvr_config = self.dvr_systems[dvr_id]
        channels = self._discover_dvr_channels(dvr_config)
        
        # Save channels to database
        for channel in channels:
            # Fix channel_id format to match expected format
            channel_id = f"{dvr_id}_ch{channel.channel_number:02d}"
            channel.channel_id = channel_id
            
            channel_data = {
                'channel_id': channel_id,
                'name': channel.name,
                'channel_number': channel.channel_number,
                'status': channel.status,
                'resolution_width': channel.resolution[0],
                'resolution_height': channel.resolution[1],
                'fps': channel.fps,
                'rtsp_path': channel.rtsp_path,
                'http_path': channel.http_path
            }
            
            success = self.db_adapter.add_dvr_channel(company_id, dvr_id, channel_data)
            if success:
                logger.info(f"✅ Channel {channel_id} added to database")
            else:
                logger.error(f"❌ Failed to add channel {channel_id} to database")
        
        # Update memory cache
        self.dvr_channels[dvr_id] = channels
        
        return [
            {
                'channel_id': ch.channel_id,
                'name': ch.name,
                'channel_number': ch.channel_number,
                'status': ch.status,
                'resolution': ch.resolution,
                'fps': ch.fps
            }
            for ch in channels
        ]
    
    def get_dvr_channels(self, company_id: str, dvr_id: str) -> List[Dict[str, Any]]:
        """Get DVR channels from database"""
        try:
            # Get from database
            db_channels = self.db_adapter.get_dvr_channels(company_id, dvr_id)
            
            # Update memory cache
            channels = []
            for ch_data in db_channels:
                channel = DVRChannel(
                    channel_id=ch_data['channel_id'],
                    name=ch_data['name'],
                    dvr_id=ch_data['dvr_id'],
                    channel_number=ch_data['channel_number'],
                    status=ch_data['status'],
                    resolution=(ch_data['resolution_width'], ch_data['resolution_height']),
                    fps=ch_data['fps'],
                    rtsp_path=ch_data['rtsp_path'],
                    http_path=ch_data['http_path']
                )
                channels.append(channel)
            
            self.dvr_channels[dvr_id] = channels
            return db_channels
            
        except Exception as e:
            logger.error(f"❌ Get DVR channels error: {e}")
            return []
    
    def start_stream(self, dvr_id: str, channel_number: int, company_id: str, quality: str = 'high') -> str:
        """Start stream for a DVR channel with database tracking"""
        if dvr_id not in self.dvr_systems:
            raise ValueError(f"DVR system {dvr_id} not found")
        
        dvr_config = self.dvr_systems[dvr_id]
        channel_id = f"{dvr_id}_ch{channel_number:02d}"
        
        # Find the channel
        channels = self.dvr_channels.get(dvr_id, [])
        channel = None
        for ch in channels:
            if ch.channel_number == channel_number:
                channel = ch
                break
        
        if not channel:
            # Create a new channel if not found
            channel = DVRChannel(
                channel_id=channel_id,
                name=f"Channel {channel_number}",
                dvr_id=dvr_id,
                channel_number=channel_number
            )
            # Add to channels list
            if dvr_id not in self.dvr_channels:
                self.dvr_channels[dvr_id] = []
            self.dvr_channels[dvr_id].append(channel)
            
            # Save to database
            channel_data = {
                'channel_id': channel_id,
                'name': channel.name,
                'channel_number': channel.channel_number,
                'status': 'active',
                'resolution_width': 1920,
                'resolution_height': 1080,
                'fps': 25,
                'rtsp_path': '',
                'http_path': ''
            }
            
            success = self.db_adapter.add_dvr_channel(company_id, dvr_id, channel_data)
            if not success:
                logger.warning(f"⚠️ Failed to save channel {channel_id} to database")
        
        # Generate RTSP URL
        rtsp_url = channel.get_rtsp_url(dvr_config)
        logger.info(f"🎥 Generated RTSP URL: {rtsp_url}")
        
        # Start the stream
        success, _ = self.start_dvr_stream(dvr_id, channel_id)
        if success:
            # Track stream in database
            stream_success = self.db_adapter.add_dvr_stream(company_id, dvr_id, channel_id, rtsp_url)
            if stream_success:
                logger.info(f"✅ Stream tracked in database: {channel_id}")
            else:
                logger.warning(f"⚠️ Failed to track stream in database: {channel_id}")
            return rtsp_url
        else:
            raise Exception(f"Failed to start stream for channel {channel_number}")
    
    def stop_dvr_stream(self, channel_id: str, company_id: str = None) -> bool:
        """Stop streaming from a DVR channel with database cleanup"""
        try:
            if channel_id in self.active_streams:
                cap = self.active_streams[channel_id]
                cap.release()
                del self.active_streams[channel_id]
            
            if channel_id in self.connection_threads:
                thread = self.connection_threads[channel_id]
                thread.join(timeout=2)
                del self.connection_threads[channel_id]
            
            # Update channel status in database
            if company_id:
                self.db_adapter.update_dvr_channel_status(company_id, channel_id, "inactive")
            
            # Update channel status in memory
            for dvr_id, channels in self.dvr_channels.items():
                for channel in channels:
                    if channel.channel_id == channel_id:
                        channel.status = "inactive"
                        break
            
            logger.info(f"✅ DVR stream stopped: {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop DVR stream: {e}")
            return False
    
    def test_dvr_connection(self, dvr_config: DVRConfig) -> Dict[str, Any]:
        """Test DVR connection and discover channels"""
        logger.info(f"🔍 Testing DVR connection: {dvr_config.name} at {dvr_config.ip_address}")
        
        result = {
            'success': False,
            'dvr_id': dvr_config.dvr_id,
            'connection_status': 'failed',
            'channels_discovered': 0,
            'channels': [],
            'error': None,
            'api_response': None,
            'rtsp_test': False,
            'http_test': False
        }
        
        try:
            # Test basic connectivity
            test_url = f"{dvr_config.protocol}://{dvr_config.ip_address}:{dvr_config.port}"
            response = dvr_config.make_request(test_url)
            
            if response and response.status_code == 200:
                result['http_test'] = True
                logger.info(f"✅ HTTP connection successful to {dvr_config.ip_address}")
                
                # Try to discover channels
                channels = self._discover_dvr_channels(dvr_config)
                result['channels'] = channels
                result['channels_discovered'] = len(channels)
                
                # Test RTSP connection
                rtsp_test = self._test_dvr_rtsp(dvr_config)
                result['rtsp_test'] = rtsp_test
                
                result['success'] = True
                result['connection_status'] = 'connected'
                
                # Update DVR status
                dvr_config.status = 'active'
                dvr_config.last_test_time = datetime.now()
                
                logger.info(f"✅ DVR test successful: {len(channels)} channels discovered")
                
            else:
                result['error'] = f"HTTP connection failed: {response.status_code}"
                logger.warning(f"⚠️ HTTP connection failed: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            result['error'] = "Connection refused - DVR may be offline"
            logger.error(f"❌ Connection refused to {dvr_config.ip_address}")
        except requests.exceptions.Timeout:
            result['error'] = "Connection timeout"
            logger.error(f"❌ Connection timeout to {dvr_config.ip_address}")
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ DVR test failed: {e}")
        
        return result
    
    def _discover_dvr_channels(self, dvr_config: DVRConfig) -> List[DVRChannel]:
        """Discover channels on DVR system"""
        channels = []
        
        try:
            # Try different channel discovery methods based on DVR type
            if dvr_config.dvr_type == "hikvision":
                channels = self._discover_hikvision_channels(dvr_config)
            elif dvr_config.dvr_type == "dahua":
                channels = self._discover_dahua_channels(dvr_config)
            else:
                # Generic discovery - try common channel paths
                channels = self._discover_generic_channels(dvr_config)
            
            # Update DVR channels
            self.dvr_channels[dvr_config.dvr_id] = channels
            
        except Exception as e:
            logger.error(f"❌ Channel discovery failed: {e}")
        
        return channels
    
    def _discover_generic_channels(self, dvr_config: DVRConfig) -> List[DVRChannel]:
        """Generic channel discovery for unknown DVR types"""
        channels = []
        
        # Try common channel numbers (1-16)
        for channel_num in range(1, dvr_config.max_channels + 1):
                channel = DVRChannel(
                channel_id=f"{dvr_config.dvr_id}_CH{channel_num:02d}",
                name=f"Channel {channel_num}",
                dvr_id=dvr_config.dvr_id,
                channel_number=channel_num,
                    # Prefer proven working patterns
                    rtsp_path=f"/user={dvr_config.username}&password={dvr_config.password}&channel={channel_num}&stream=0.sdp",
                http_path=f"/ch{channel_num:02d}/snapshot"
            )
        channels.append(channel)
    
        logger.info(f"📺 Generic discovery: {len(channels)} channels configured")
        return channels
    
    def _discover_hikvision_channels(self, dvr_config: DVRConfig) -> List[DVRChannel]:
        """
        Discover channels on Hikvision DVR/NVR via ISAPI.
        Uses /ISAPI/System/Video/inputs/channels for accurate channel detection.
        Falls back to /ISAPI/System/deviceInfo if inputs API is unavailable.
        Supports both Digest and Basic authentication.
        """
        channels = []
        base_url = f"{dvr_config.protocol}://{dvr_config.ip_address}:{dvr_config.port}"

        try:
            # ── Step 1: Try /ISAPI/System/Video/inputs/channels (best source) ──
            inputs_url = f"{base_url}/ISAPI/System/Video/inputs/channels"
            resp = dvr_config.make_request(inputs_url)

            if resp and resp.status_code == 200:
                root = ET.fromstring(resp.content)
                ns = ''
                # Handle namespace (Hikvision uses hikvision.com namespace)
                if root.tag.startswith('{'):
                    ns = root.tag.split('}')[0] + '}'

                for inp in root.findall(f'{ns}VideoInputChannel') or root.findall('VideoInputChannel'):
                    ch_id_el = inp.find(f'{ns}id') or inp.find('id')
                    ch_name_el = inp.find(f'{ns}name') or inp.find('name')
                    res_w_el = inp.find(f'{ns}resWidth') or inp.find('resWidth')
                    res_h_el = inp.find(f'{ns}resHeight') or inp.find('resHeight')

                    ch_num = int(ch_id_el.text) if (ch_id_el is not None and ch_id_el.text) else len(channels) + 1
                    ch_name_text = ch_name_el.text if (ch_name_el is not None and ch_name_el.text) else f"Hikvision CH{ch_num}"

                    res_w = int(res_w_el.text) if (res_w_el is not None and res_w_el.text) else 1920
                    res_h = int(res_h_el.text) if (res_h_el is not None and res_h_el.text) else 1080

                    channel = DVRChannel(
                        channel_id=f"{dvr_config.dvr_id}_CH{ch_num:02d}",
                        name=ch_name_text,
                        dvr_id=dvr_config.dvr_id,
                        channel_number=ch_num,
                        resolution=(res_w, res_h),
                        rtsp_path=f"/Streaming/Channels/{ch_num:03d}01",
                        http_path=f"/ISAPI/Streaming/channels/{ch_num:03d}01/picture"
                    )
                    channels.append(channel)

                if channels:
                    logger.info(f"📺 Hikvision ISAPI inputs: {len(channels)} channels discovered")
                    return channels

            # ── Step 2: Fallback — /ISAPI/System/deviceInfo ──
            dev_url = f"{base_url}/ISAPI/System/deviceInfo"
            resp = dvr_config.make_request(dev_url)

            if resp and resp.status_code == 200:
                root = ET.fromstring(resp.content)
                ns = ''
                if root.tag.startswith('{'):
                    ns = root.tag.split('}')[0] + '}'

                # Try analogChannelNum + digitalChannelNum for real channel count
                analog = root.find(f'{ns}analogChannelNum') or root.find('analogChannelNum')
                digital = root.find(f'{ns}digitalChannelNum') or root.find('digitalChannelNum')

                total = 0
                if analog is not None and analog.text:
                    total += int(analog.text)
                if digital is not None and digital.text:
                    total += int(digital.text)

                if total == 0:
                    total = dvr_config.max_channels

                total = min(total, 64)  # safety cap

                for ch_num in range(1, total + 1):
                    channel = DVRChannel(
                        channel_id=f"{dvr_config.dvr_id}_CH{ch_num:02d}",
                        name=f"Hikvision Channel {ch_num}",
                        dvr_id=dvr_config.dvr_id,
                        channel_number=ch_num,
                        rtsp_path=f"/Streaming/Channels/{ch_num:03d}01",
                        http_path=f"/ISAPI/Streaming/channels/{ch_num:03d}01/picture"
                    )
                    channels.append(channel)

                logger.info(f"📺 Hikvision deviceInfo: {len(channels)} channels derived")

        except Exception as e:
            logger.error(f"❌ Hikvision discovery failed: {e}")
            # Fallback to generic discovery
            channels = self._discover_generic_channels(dvr_config)

        return channels
    
    def _discover_dahua_channels(self, dvr_config: DVRConfig) -> List[DVRChannel]:
        """
        Discover channels on Dahua DVR/NVR via CGI API.
        Uses /cgi-bin/magicBox.cgi?action=getProductDefinition for real channel count.
        Supports both Digest and Basic authentication.
        """
        channels = []
        base_url = f"{dvr_config.protocol}://{dvr_config.ip_address}:{dvr_config.port}"

        try:
            # ── Step 1: Product definition — gives real channel count ──
            prod_url = f"{base_url}/cgi-bin/magicBox.cgi?action=getProductDefinition"
            resp = dvr_config.make_request(prod_url)

            max_channels = dvr_config.max_channels

            if resp and resp.status_code == 200:
                content = resp.text
                # Dahua returns key=value pairs, e.g.:
                # MaxExtraStream=3
                # VideoInChannel=16
                for line in content.splitlines():
                    line = line.strip()
                    if '=' not in line:
                        continue
                    key, _, val = line.partition('=')
                    key = key.strip()
                    val = val.strip()
                    if key in ('VideoInChannel', 'MaxChannel', 'AlarmInputNum'):
                        try:
                            parsed = int(val)
                            if key == 'VideoInChannel':
                                max_channels = parsed
                                break  # best source
                            elif max_channels == dvr_config.max_channels:
                                max_channels = parsed
                        except ValueError:
                            pass

                logger.info(f"📺 Dahua productDef: VideoInChannel={max_channels}")
            else:
                # Step 2: Fallback — try system info
                sys_url = f"{base_url}/cgi-bin/magicBox.cgi?action=getSystemInfo"
                resp = dvr_config.make_request(sys_url)
                if resp and resp.status_code == 200:
                    logger.info(f"📺 Dahua systemInfo reached, using default channels={max_channels}")

            max_channels = min(max_channels, 64)  # safety cap

            for ch_num in range(1, max_channels + 1):
                channel = DVRChannel(
                    channel_id=f"{dvr_config.dvr_id}_CH{ch_num:02d}",
                    name=f"Dahua Channel {ch_num}",
                    dvr_id=dvr_config.dvr_id,
                    channel_number=ch_num,
                    rtsp_path=f"/cam/realmonitor?channel={ch_num}&subtype=0",
                    http_path=f"/cgi-bin/snapshot.cgi?channel={ch_num}"
                )
                channels.append(channel)

            logger.info(f"📺 Dahua discovery: {len(channels)} channels configured")

        except Exception as e:
            logger.error(f"❌ Dahua discovery failed: {e}")
            channels = self._discover_generic_channels(dvr_config)

        return channels
    
    def _test_dvr_rtsp(self, dvr_config: DVRConfig) -> bool:
        """Test RTSP connectivity to DVR"""
        try:
            # Test RTSP connection to first channel
            if dvr_config.dvr_id in self.dvr_channels and self.dvr_channels[dvr_config.dvr_id]:
                first_channel = self.dvr_channels[dvr_config.dvr_id][0]
                rtsp_url = first_channel.get_rtsp_url(dvr_config)
                
                cap = cv2.VideoCapture(rtsp_url)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        logger.info(f"✅ RTSP test successful: {rtsp_url}")
                        return True
            
            logger.warning(f"⚠️ RTSP test failed for {dvr_config.ip_address}")
            return False
            
        except Exception as e:
            logger.error(f"❌ RTSP test error: {e}")
            return False
    
    def start_dvr_stream(self, dvr_id: str, channel_id: str) -> Tuple[bool, str]:
        """Start streaming from a DVR channel"""
        try:
            if dvr_id not in self.dvr_systems:
                logger.error(f"❌ DVR system not found: {dvr_id}")
                return False, "DVR system not found"
            
            dvr_config = self.dvr_systems[dvr_id]
            channels = self.dvr_channels.get(dvr_id, [])
            
            logger.info(f"🔍 DVR Config: {dvr_config.ip_address}:{dvr_config.rtsp_port}")
            logger.info(f"🔍 DVR Auth: {dvr_config.username}:{dvr_config.password}")
            logger.info(f"🔍 Available channels: {len(channels)}")
            
            # Find the channel
            channel = None
            for ch in channels:
                if ch.channel_id == channel_id:
                    channel = ch
                    break
            
            if not channel:
                logger.error(f"❌ Channel not found: {channel_id}")
                return False, "Channel not found"
            
            logger.info(f"🔍 Channel found: {channel.name} (Channel {channel.channel_number})")
            
            # Generate RTSP URL
            rtsp_url = channel.get_rtsp_url(dvr_config)
            logger.info(f"🔗 Primary RTSP URL: {rtsp_url}")
            
            # Test network connectivity first
            import socket
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((dvr_config.ip_address, dvr_config.rtsp_port))
                sock.close()
                if result == 0:
                    logger.info(f"✅ Network connectivity to {dvr_config.ip_address}:{dvr_config.rtsp_port} OK")
                else:
                    logger.warning(f"⚠️ Network connectivity to {dvr_config.ip_address}:{dvr_config.rtsp_port} failed")
            except Exception as e:
                logger.warning(f"⚠️ Network test failed: {e}")
            
            # Start video capture with timeout
            cap = cv2.VideoCapture(rtsp_url)
            
            # Set timeout for connection
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)  # 5 second timeout
            
            if not cap.isOpened():
                logger.warning(f"⚠️ Primary RTSP URL failed: {rtsp_url}")
                
                # Try alternative URL formats
                safe_username = quote(dvr_config.username)
                safe_password = quote(dvr_config.password)
                alternative_urls = [
                    f"rtsp://{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/0",
                    f"rtsp://{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/1",
                    f"rtsp://{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/main/0",
                    f"rtsp://{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/main/1",
                    f"rtsp://{safe_username}:{safe_password}@{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/main",
                    f"rtsp://{safe_username}:{safe_password}@{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/0",
                    f"rtsp://{safe_username}:{safe_password}@{dvr_config.ip_address}:{dvr_config.rtsp_port}/ch{channel.channel_number:02d}/1"
                ]
                
                for i, alt_url in enumerate(alternative_urls):
                    logger.info(f"🔄 Trying alternative URL {i+1}: {alt_url}")
                    cap = cv2.VideoCapture(alt_url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)  # 3 second timeout
                    if cap.isOpened():
                        logger.info(f"✅ Connected using alternative URL {i+1}: {alt_url}")
                        break
                    else:
                        logger.warning(f"❌ Alternative URL {i+1} failed")
                
                if not cap.isOpened():
                    error_msg = f"Failed to open RTSP stream after trying {len(alternative_urls)+1} URLs"
                    logger.error(f"❌ {error_msg}")
                    return False, error_msg
            
            # Test if we can actually read frames
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"⚠️ RTSP connection opened but cannot read frames")
                cap.release()
                return False, "RTSP connection opened but cannot read frames"
            
            logger.info(f"✅ RTSP connection successful and frame reading works")
            
            self.active_streams[channel_id] = cap
            channel.status = "active"
            
            # Start frame capture thread
            thread = threading.Thread(target=self._capture_dvr_frames, args=(channel_id,))
            thread.daemon = True
            thread.start()
            self.connection_threads[channel_id] = thread
            
            logger.info(f"✅ DVR stream started: {channel.name} ({rtsp_url})")
            return True, "Stream started successfully"
            
        except Exception as e:
            logger.error(f"❌ Failed to start DVR stream: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False, str(e)
    
    def _capture_dvr_frames(self, channel_id: str):
        """Capture frames from DVR channel"""
        cap = self.active_streams.get(channel_id)
        if not cap:
            return
        
        fps_counter = []
        start_time = time.time()
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    self.frame_buffers[channel_id] = frame
                    self.last_frames[channel_id] = datetime.now()
                    
                    # Calculate FPS
                    current_time = time.time()
                    fps_counter.append(current_time)
                    # Keep only last 30 FPS measurements
                    if len(fps_counter) > 30:
                        fps_counter.pop(0)
                    
                    # Update FPS counter
                    if len(fps_counter) > 1:
                        fps = len(fps_counter) / (fps_counter[-1] - fps_counter[0])
                        self.fps_counters[channel_id] = [fps]
                    
                    # Small delay to prevent excessive CPU usage
                    time.sleep(0.01)
                else:
                    logger.warning(f"⚠️ Failed to read frame from {channel_id}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ DVR frame capture error: {e}")
        finally:
            cap.release()
            if channel_id in self.active_streams:
                del self.active_streams[channel_id]
    
    def get_dvr_frame(self, channel_id: str) -> Optional[np.ndarray]:
        """Get latest frame from DVR channel"""
        return self.frame_buffers.get(channel_id)
    
    def get_dvr_status(self, dvr_id: str) -> Dict[str, Any]:
        """Get DVR system status"""
        if dvr_id not in self.dvr_systems:
            return {'error': 'DVR system not found'}
        
        dvr_config = self.dvr_systems[dvr_id]
        channels = self.dvr_channels.get(dvr_id, [])
        
        active_channels = [ch for ch in channels if ch.status == "active"]
        
        return {
            'dvr_id': dvr_id,
            'name': dvr_config.name,
            'ip_address': dvr_config.ip_address,
            'status': dvr_config.status,
            'total_channels': len(channels),
            'active_channels': len(active_channels),
            'channels': [
                {
                    'channel_id': ch.channel_id,
                    'name': ch.name,
                    'status': ch.status,
                    'fps': self.fps_counters.get(ch.channel_id, [0])[0] if ch.channel_id in self.fps_counters else 0
                }
                for ch in channels
            ]
        }
    
    def get_all_dvr_status(self) -> List[Dict[str, Any]]:
        """Get status of all DVR systems"""
        return [self.get_dvr_status(dvr_id) for dvr_id in self.dvr_systems.keys()]
    
    def get_dvr_system(self, company_id: str, dvr_id: str) -> Optional[Dict[str, Any]]:
        """Get specific DVR system from database"""
        try:
            # Get from database
            db_system = self.db_adapter.get_dvr_system(company_id, dvr_id)
            
            if db_system:
                logger.info(f"✅ Retrieved DVR system: {dvr_id}")
                return db_system
            else:
                logger.warning(f"⚠️ DVR system not found: {dvr_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Get DVR system error: {e}")
            return None

@dataclass
class RealCameraConfig:
    """Real camera configuration based on actual camera settings"""
    camera_id: str
    name: str
    ip_address: str
    port: int = 8080
    username: str = ""
    password: str = ""
    protocol: str = "http"  # http, rtsp, onvif
    stream_path: str = "/video"
    auth_type: str = "basic"  # basic, digest, none
    resolution: Tuple[int, int] = (1920, 1080)
    fps: int = 25
    quality: int = 80
    audio_enabled: bool = False
    night_vision: bool = False
    motion_detection: bool = True
    recording_enabled: bool = True
    status: str = "inactive"  # active, inactive, error, testing
    last_test_time: Optional[datetime] = None
    connection_retries: int = 3
    timeout: int = 10
    
    def get_stream_url(self) -> str:
        """Generate stream URL based on configuration"""
        if self.protocol == "rtsp":
            if self.username and self.password:
                safe_username = quote(self.username)
                safe_password = quote(self.password)
                return f"rtsp://{safe_username}:{safe_password}@{self.ip_address}:{self.port}{self.stream_path}"
            else:
                return f"rtsp://{self.ip_address}:{self.port}{self.stream_path}"
        else:  # HTTP
            return f"http://{self.ip_address}:{self.port}{self.stream_path}"
    
    def get_mjpeg_url(self) -> str:
        """Generate MJPEG snapshot URL"""
        return f"http://{self.ip_address}:{self.port}/shot.jpg"
    
    def get_auth_header(self) -> Dict[str, str]:
        """Generate authentication header"""
        if self.auth_type == "basic" and self.username and self.password:
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        return {}

@dataclass
class CameraSource:
    """Professional camera source configuration"""
    camera_id: str
    name: str
    source_type: str  # 'real_camera', 'ip_webcam', 'rtsp', 'local', 'usb'
    connection_url: str
    backup_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    resolution: Tuple[int, int] = (1280, 720)
    fps: int = 25
    timeout: int = 10
    retry_attempts: int = 3
    enabled: bool = True
    last_connection_test: Optional[datetime] = None
    connection_status: str = "unknown"  # unknown, connected, failed, testing

class RealCameraManager:
    """Enhanced real camera management system"""
    
    def __init__(self):
        self.real_cameras: Dict[str, RealCameraConfig] = {}
        self.active_streams: Dict[str, cv2.VideoCapture] = {}
        self.connection_threads: Dict[str, threading.Thread] = {}
        self.frame_buffers: Dict[str, np.ndarray] = {}
        self.last_frames: Dict[str, datetime] = {}
        
        # Performance tracking
        self.fps_counters: Dict[str, List[float]] = {}
        self.connection_stats: Dict[str, Dict] = {}
        
        logger.info("🎥 Real Camera Manager initialized")
    
    def add_real_camera(self, camera_config: RealCameraConfig) -> Tuple[bool, str]:
        """Add a real camera to the system"""
        try:
            # Test connection first
            test_result = self.test_real_camera_connection(camera_config)
            
            if test_result['success']:
                self.real_cameras[camera_config.camera_id] = camera_config
                camera_config.status = "active"
                camera_config.last_test_time = datetime.now()
                
                logger.info(f"✅ Real camera added successfully: {camera_config.name}")
                return True, "Camera added successfully"
            else:
                logger.error(f"❌ Failed to add camera: {test_result['error']}")
                return False, test_result['error']
                
        except Exception as e:
            logger.error(f"❌ Error adding real camera: {e}")
            return False, str(e)
    
    def test_real_camera_connection(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test real camera connection with comprehensive checks"""
        logger.info(f"🔍 Testing real camera connection: {camera_config.name}")
        
        result = {
            'success': False,
            'error': '',
            'connection_time': 0,
            'stream_quality': 'unknown',
            'supported_features': [],
            'camera_info': {}
        }
        
        start_time = time.time()
        
        try:
            # 1. Basic connectivity test
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(camera_config.timeout)
            
            connection_result = sock.connect_ex((camera_config.ip_address, camera_config.port))
            sock.close()
            
            if connection_result != 0:
                result['error'] = f"Cannot connect to {camera_config.ip_address}:{camera_config.port}"
                return result
            
            # 2. HTTP/RTSP stream test
            if camera_config.protocol == "rtsp":
                stream_test = self._test_rtsp_stream(camera_config)
            else:
                stream_test = self._test_http_stream(camera_config)
            
            if not stream_test['success']:
                result['error'] = stream_test['error']
                return result
            
            # 3. Authentication test
            if camera_config.username and camera_config.password:
                auth_test = self._test_camera_authentication(camera_config)
                if not auth_test['success']:
                    result['error'] = f"Authentication failed: {auth_test['error']}"
                    return result
            
            # 4. Feature detection
            features = self._detect_camera_features(camera_config)
            result['supported_features'] = features
            
            # 5. Quality assessment
            quality_info = self._assess_stream_quality(camera_config)
            result['stream_quality'] = quality_info
            
            result['connection_time'] = time.time() - start_time
            result['success'] = True
            
            logger.info(f"✅ Camera connection test passed: {camera_config.name}")
            return result
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Camera connection test failed: {e}")
            return result
    
    def _test_http_stream(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test HTTP stream connection"""
        try:
            stream_url = camera_config.get_stream_url()
            headers = camera_config.get_auth_header()
            
            # Test MJPEG snapshot first
            mjpeg_url = camera_config.get_mjpeg_url()
            response = requests.get(mjpeg_url, headers=headers, timeout=camera_config.timeout)
            
            if response.status_code == 200:
                # Try to open video stream
                cap = cv2.VideoCapture(stream_url)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret and frame is not None:
                        return {'success': True, 'frame_size': frame.shape}
                    else:
                        return {'success': False, 'error': 'No frame received'}
                else:
                    return {'success': False, 'error': 'Cannot open video stream'}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_rtsp_stream(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test RTSP stream connection"""
        try:
            stream_url = camera_config.get_stream_url()
            
            cap = cv2.VideoCapture(stream_url)
            if cap.isOpened():
                # Set timeout
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                ret, frame = cap.read()
                cap.release()
                
                if ret and frame is not None:
                    return {'success': True, 'frame_size': frame.shape}
                else:
                    return {'success': False, 'error': 'No frame received from RTSP'}
            else:
                return {'success': False, 'error': 'Cannot open RTSP stream'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_camera_authentication(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test camera authentication"""
        try:
            test_url = f"http://{camera_config.ip_address}:{camera_config.port}/status"
            headers = camera_config.get_auth_header()
            
            response = requests.get(test_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                return {'success': True}
            elif response.status_code == 401:
                return {'success': False, 'error': 'Invalid credentials'}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _detect_camera_features(self, camera_config: RealCameraConfig) -> List[str]:
        """Detect available camera features"""
        features = []
        
        try:
            # Test common endpoints
            base_url = f"http://{camera_config.ip_address}:{camera_config.port}"
            headers = camera_config.get_auth_header()
            
            # Common feature endpoints
            feature_endpoints = {
                'ptz': '/ptz',
                'zoom': '/zoom',
                'focus': '/focus',
                'night_vision': '/night_vision',
                'motion_detection': '/motion',
                'audio': '/audio',
                'recording': '/recording'
            }
            
            for feature, endpoint in feature_endpoints.items():
                try:
                    response = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=2)
                    if response.status_code == 200:
                        features.append(feature)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"Feature detection error: {e}")
        
        return features
    
    def _assess_stream_quality(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Assess stream quality"""
        try:
            stream_url = camera_config.get_stream_url()
            cap = cv2.VideoCapture(stream_url)
            
            if cap.isOpened():
                # Get actual resolution
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                
                cap.release()
                
                return {
                    'resolution': f"{width}x{height}",
                    'fps': fps,
                    'quality': 'good' if width >= 1280 else 'medium'
                }
            else:
                return {'quality': 'unknown', 'error': 'Cannot open stream'}
                
        except Exception as e:
            return {'quality': 'unknown', 'error': str(e)}
    
    def get_real_camera_status(self, camera_id: str) -> Dict[str, Any]:
        """Get comprehensive real camera status"""
        if camera_id not in self.real_cameras:
            return {'status': 'not_found'}
        
        camera = self.real_cameras[camera_id]
        
        return {
            'camera_id': camera_id,
            'name': camera.name,
            'ip_address': camera.ip_address,
            'port': camera.port,
            'protocol': camera.protocol,
            'status': camera.status,
            'resolution': f"{camera.resolution[0]}x{camera.resolution[1]}",
            'fps': camera.fps,
            'quality': camera.quality,
            'audio_enabled': camera.audio_enabled,
            'night_vision': camera.night_vision,
            'motion_detection': camera.motion_detection,
            'recording_enabled': camera.recording_enabled,
            'last_test_time': camera.last_test_time,
            'stream_url': camera.get_stream_url(),
            'mjpeg_url': camera.get_mjpeg_url()
        }
    
    def create_real_camera_from_form(self, form_data: Dict[str, Any]) -> RealCameraConfig:
        """Create real camera configuration from form data"""
        import uuid
        
        camera_id = form_data.get('camera_id', str(uuid.uuid4()))
        
        return RealCameraConfig(
            camera_id=camera_id,
            name=form_data.get('name', 'Real Camera'),
            ip_address=form_data.get('ip_address', '192.168.1.100'),
            port=int(form_data.get('port', 8080)),
            username=form_data.get('username', ''),
            password=form_data.get('password', ''),
            protocol=form_data.get('protocol', 'http'),
            stream_path=form_data.get('stream_path', '/video'),
            auth_type=form_data.get('auth_type', 'basic'),
            resolution=(
                int(form_data.get('width', 1920)),
                int(form_data.get('height', 1080))
            ),
            fps=int(form_data.get('fps', 25)),
            quality=int(form_data.get('quality', 80)),
            audio_enabled=form_data.get('audio_enabled', False),
            night_vision=form_data.get('night_vision', False),
            motion_detection=form_data.get('motion_detection', True),
            recording_enabled=form_data.get('recording_enabled', True)
        )

class SmartCameraDetector:
    """Akıllı kamera tespit sistemi - Yeni eklenen sınıf"""
    
    def __init__(self):
        # Genişletilmiş kamera modeli veritabanı
        self.camera_database = {
            'hikvision': {
                'name': 'Hikvision',
                'ports': [554, 80, 8000, 8080, 443],
                'paths': ['/Streaming/Channels/101', '/ISAPI/Streaming/channels/101', '/doc/page/login.asp'],
                'headers': ['Server: App-webs/', 'Server: uc-httpd'],
                'default_rtsp': 'rtsp://{ip}:554/Streaming/Channels/101',
                'default_http': 'http://{ip}:80/ISAPI/Streaming/channels/101',
                'auth_endpoints': ['/ISAPI/System/deviceInfo', '/doc/page/login.asp']
            },
            'dahua': {
                'name': 'Dahua',
                'ports': [554, 80, 37777, 443],
                'paths': ['/cam/realmonitor?channel=1&subtype=0', '/cgi-bin/magicBox.cgi'],
                'headers': ['Server: DahuaHttp'],
                'default_rtsp': 'rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0',
                'default_http': 'http://{ip}:80/cgi-bin/magicBox.cgi',
                'auth_endpoints': ['/cgi-bin/magicBox.cgi?action=getDeviceType']
            },
            'axis': {
                'name': 'Axis',
                'ports': [554, 80, 443],
                'paths': ['/axis-media/media.amp', '/axis-cgi/jpg/image.cgi'],
                'headers': ['Server: axis'],
                'default_rtsp': 'rtsp://{ip}:554/axis-media/media.amp',
                'default_http': 'http://{ip}:80/axis-cgi/jpg/image.cgi',
                'auth_endpoints': ['/axis-cgi/param.cgi?action=list']
            },
            'foscam': {
                'name': 'Foscam',
                'ports': [554, 88, 80],
                'paths': ['/videoMain', '/videostream.cgi'],
                'headers': ['Server: Foscam'],
                'default_rtsp': 'rtsp://{ip}:554/videoMain',
                'default_http': 'http://{ip}:88/videostream.cgi',
                'auth_endpoints': ['/cgi-bin/CGIProxy.fcgi?cmd=getDevState']
            },
            'generic_ip': {
                'name': 'Generic IP Camera',
                'ports': [554, 8080, 80, 8000],
                'paths': ['/video', '/stream', '/mjpeg', '/shot.jpg', '/live'],
                'headers': [],
                'default_rtsp': 'rtsp://{ip}:554/stream',
                'default_http': 'http://{ip}:8080/video',
                'auth_endpoints': ['/status', '/info']
            },
            'android_ipwebcam': {
                'name': 'Android IP Webcam',
                'ports': [8080, 8081, 8082],
                'paths': ['/shot.jpg', '/video', '/mjpeg'],
                'headers': ['Server: IP Webcam'],
                'default_rtsp': 'rtsp://{ip}:8080/video',
                'default_http': 'http://{ip}:8080/shot.jpg',
                'auth_endpoints': ['/settings']
            }
        }
        
        # Yaygın port ve path kombinasyonları
        self.common_combinations = [
            {'port': 80, 'path': '/video', 'protocol': 'http'},
            {'port': 80, 'path': '/stream', 'protocol': 'http'},
            {'port': 80, 'path': '/mjpeg', 'protocol': 'http'},
            {'port': 8080, 'path': '/video', 'protocol': 'http'},
            {'port': 8080, 'path': '/shot.jpg', 'protocol': 'http'},
            {'port': 554, 'path': '/stream', 'protocol': 'rtsp'},
            {'port': 554, 'path': '/video', 'protocol': 'rtsp'},
            {'port': 554, 'path': '/live', 'protocol': 'rtsp'},
            {'port': 8000, 'path': '/video', 'protocol': 'http'},
            {'port': 8000, 'path': '/stream', 'protocol': 'http'}
        ]
    
    def smart_detect_camera(self, ip_address: str, timeout: int = 3) -> Dict[str, Any]:
        """
        Akıllı kamera tespiti - Basitleştirilmiş versiyon
        
        Args:
            ip_address: Kamera IP adresi
            timeout: Bağlantı zaman aşımı
            
        Returns:
            Tespit edilen kamera bilgileri
        """
        logger.info(f"🔍 Smart camera detection started for {ip_address}")
        
        result = {
            'success': False,
            'ip_address': ip_address,
            'detected_model': 'unknown',
            'protocol': None,
            'port': None,
            'path': None,
            'stream_url': None,
            'mjpeg_url': None,
            'auth_required': False,
            'detection_confidence': 0.0,
            'error': None
        }
        
        try:
            # 1. Ping testi
            if not self._ping_test(ip_address):
                result['error'] = "IP adresi erişilebilir değil"
                return result
            
            # 2. Basit konfigürasyon tespiti (model tespiti olmadan)
            logger.info(f"🔍 Quick configuration detection for {ip_address}")
            
            # 8080 portu için Android IP Webcam varsayılanı
            if self._test_http_stream(f"http://{ip_address}:8080/shot.jpg", 2):
                result.update({
                    'success': True,
                    'detected_model': 'android_ipwebcam',
                    'protocol': 'http',
                    'port': 8080,
                    'path': '/shot.jpg',
                    'stream_url': f"http://{ip_address}:8080/shot.jpg",
                    'mjpeg_url': f"http://{ip_address}:8080/shot.jpg",
                    'detection_confidence': 0.8
                })
                logger.info(f"✅ Quick detection successful: Android IP Webcam on port 8080")
                return result
            
            # 8080 portu için video endpoint
            if self._test_http_stream(f"http://{ip_address}:8080/video", 2):
                result.update({
                    'success': True,
                    'detected_model': 'generic_ip',
                    'protocol': 'http',
                    'port': 8080,
                    'path': '/video',
                    'stream_url': f"http://{ip_address}:8080/video",
                    'mjpeg_url': f"http://{ip_address}:8080/shot.jpg",
                    'detection_confidence': 0.7
                })
                logger.info(f"✅ Quick detection successful: Generic IP Camera on port 8080")
                return result
            
            # 80 portu için test
            if self._test_http_stream(f"http://{ip_address}:80/video", 2):
                result.update({
                    'success': True,
                    'detected_model': 'generic_ip',
                    'protocol': 'http',
                    'port': 80,
                    'path': '/video',
                    'stream_url': f"http://{ip_address}:80/video",
                    'mjpeg_url': f"http://{ip_address}:80/shot.jpg",
                    'detection_confidence': 0.7
                })
                logger.info(f"✅ Quick detection successful: Generic IP Camera on port 80")
                return result
            
            result['error'] = "Çalışan kamera konfigürasyonu bulunamadı"
            logger.warning(f"❌ Quick detection failed for {ip_address}")
            return result
            
        except Exception as e:
            result['error'] = f"Tespit hatası: {str(e)}"
            logger.error(f"❌ Smart detection failed for {ip_address}: {e}")
            return result
    
    def _ping_test(self, ip_address: str) -> bool:
        """Ping testi - Yaygın portları test et"""
        common_ports = [80, 8080, 554, 8000, 443]
        
        for port in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip_address, port))
                sock.close()
                if result == 0:
                    logger.info(f"✅ Ping test başarılı: {ip_address}:{port}")
                    return True
            except:
                continue
        
        logger.warning(f"❌ Ping test başarısız: {ip_address} - Hiçbir port açık değil")
        return False
    
    def _detect_camera_model(self, ip_address: str, timeout: int) -> Optional[Dict]:
        """Kamera modelini tespit et - Hızlandırılmış versiyon"""
        logger.info(f"🔍 Model detection started for {ip_address}")
        
        # Hızlı test için sadece yaygın portları test et
        quick_ports = [8080, 80, 554]
        
        for port in quick_ports:
            try:
                # Basit HTTP testi
                url = f"http://{ip_address}:{port}/"
                response = requests.get(url, timeout=2)  # 2 saniye timeout
                
                if response.status_code == 200:
                    content = response.text.lower()
                    headers = str(response.headers).lower()
                    
                    # Android IP Webcam tespiti (en yaygın)
                    if 'ip webcam' in content or 'ipwebcam' in content or 'android' in content:
                        logger.info(f"✅ Android IP Webcam detected on port {port}")
                        return {
                            'model': 'android_ipwebcam',
                            'confidence': 0.9,
                            'info': self.camera_database['android_ipwebcam']
                        }
                    
                    # Hikvision tespiti
                    if 'hikvision' in content or 'app-webs' in headers:
                        logger.info(f"✅ Hikvision detected on port {port}")
                        return {
                            'model': 'hikvision',
                            'confidence': 0.9,
                            'info': self.camera_database['hikvision']
                        }
                    
                    # Dahua tespiti
                    if 'dahua' in content or 'dahuahttp' in headers:
                        logger.info(f"✅ Dahua detected on port {port}")
                        return {
                            'model': 'dahua',
                            'confidence': 0.9,
                            'info': self.camera_database['dahua']
                        }
                    
                    # Generic IP Camera (varsayılan)
                    logger.info(f"✅ Generic IP Camera detected on port {port}")
                    return {
                        'model': 'generic_ip',
                        'confidence': 0.7,
                        'info': self.camera_database['generic_ip']
                    }
                    
            except Exception as e:
                logger.debug(f"❌ Port {port} test failed: {e}")
                continue
        
        logger.warning(f"❌ No camera model detected for {ip_address}")
        return None
    
    def _find_working_config(self, ip_address: str, model_info: Optional[Dict], timeout: int) -> Optional[Dict]:
        """Çalışan konfigürasyonu bul"""
        # Önce model bilgisine göre test et
        if model_info:
            config = self._test_model_config(ip_address, model_info, timeout)
            if config:
                return config
        
        # Genel kombinasyonları test et
        for combo in self.common_combinations:
            config = self._test_combination(ip_address, combo, timeout)
            if config:
                return config
        
        return None
    
    def _test_model_config(self, ip_address: str, model_info: Dict, timeout: int) -> Optional[Dict]:
        """Model bilgisine göre konfigürasyon test et"""
        info = model_info['info']
        
        # RTSP testleri
        for port in info['ports']:
            if port == 554:  # RTSP portu
                for path in info['paths']:
                    if 'rtsp' in path or 'stream' in path:
                        rtsp_url = f"rtsp://{ip_address}:{port}{path}"
                        if self._test_rtsp_stream(rtsp_url, timeout):
                            return {
                                'protocol': 'rtsp',
                                'port': port,
                                'path': path,
                                'stream_url': rtsp_url,
                                'mjpeg_url': f"http://{ip_address}:80/shot.jpg"
                            }
        
        # HTTP testleri
        for port in info['ports']:
            if port in [80, 8080, 8000]:  # HTTP portları
                for path in info['paths']:
                    http_url = f"http://{ip_address}:{port}{path}"
                    if self._test_http_stream(http_url, timeout):
                        return {
                            'protocol': 'http',
                            'port': port,
                            'path': path,
                            'stream_url': http_url,
                            'mjpeg_url': f"http://{ip_address}:{port}/shot.jpg"
                        }
        
        return None
    
    def _test_combination(self, ip_address: str, combo: Dict, timeout: int) -> Optional[Dict]:
        """Kombinasyon test et"""
        if combo['protocol'] == 'rtsp':
            rtsp_url = f"rtsp://{ip_address}:{combo['port']}{combo['path']}"
            if self._test_rtsp_stream(rtsp_url, timeout):
                return {
                    'protocol': 'rtsp',
                    'port': combo['port'],
                    'path': combo['path'],
                    'stream_url': rtsp_url,
                    'mjpeg_url': f"http://{ip_address}:80/shot.jpg"
                }
        else:
            http_url = f"http://{ip_address}:{combo['port']}{combo['path']}"
            if self._test_http_stream(http_url, timeout):
                return {
                    'protocol': 'http',
                    'port': combo['port'],
                    'path': combo['path'],
                    'stream_url': http_url,
                    'mjpeg_url': f"http://{ip_address}:{combo['port']}/shot.jpg"
                }
        
        return None
    
    def _test_rtsp_stream(self, rtsp_url: str, timeout: int) -> bool:
        """RTSP stream test et"""
        try:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Kısa süreli test
            start_time = time.time()
            while time.time() - start_time < timeout:
                ret, frame = cap.read()
                if ret and frame is not None:
                    cap.release()
                    return True
                time.sleep(0.1)
            
            cap.release()
            return False
        except:
            return False
    
    def _test_http_stream(self, http_url: str, timeout: int) -> bool:
        """HTTP stream test et - Basitleştirilmiş versiyon"""
        try:
            logger.debug(f"🔍 Testing HTTP stream: {http_url}")
            response = requests.get(http_url, timeout=timeout)
            
            # 200, 401, 403 gibi status kodları kabul et (authentication gerekebilir)
            if response.status_code in [200, 401, 403]:
                logger.debug(f"✅ HTTP stream test successful: {http_url} (Status: {response.status_code})")
                return True
            
            logger.debug(f"❌ HTTP stream test failed: {http_url} (Status: {response.status_code})")
            return False
        except Exception as e:
            logger.debug(f"❌ HTTP stream test error: {http_url} - {e}")
            return False

class ProfessionalCameraManager:
    """Enterprise-grade camera management system"""
    
    def __init__(self):
        # Generic reader interface (FFmpegStreamReader or CV2StreamReader)
        self.active_cameras: Dict[str, Any] = {}
        self.camera_configs: Dict[str, CameraSource] = {}
        self.connection_threads: Dict[str, threading.Thread] = {}
        self.frame_buffers: Dict[str, np.ndarray] = {}
        self.last_frames: Dict[str, datetime] = {}
        
        # DVR Integration
        self.dvr_manager = DVRManager()
        
        # 🎯 PPE Detection Integration
        self.ppe_detector = None
        self.detection_results: Dict[str, Dict] = {}
        self.detection_frequency = 5  # Her 5 frame'de bir detection (daha sık)
        
        # Performance tracking
        self.fps_counters: Dict[str, List[float]] = {}
        self.connection_stats: Dict[str, Dict] = {}
        
        logger.info("🎥 Professional Camera Manager initialized with DVR support and PPE Detection")
        
        # PPE Detection Manager'ı yükle
        self._init_ppe_detector()
    
    def _init_ppe_detector(self):
        """PPE Detection Manager'ı başlat"""
        try:
            from models.sh17_model_manager import SH17ModelManager
            self.ppe_detector = SH17ModelManager()
            logger.info("✅ PPE Detection Manager yüklendi")
        except Exception as e:
            logger.warning(f"⚠️ PPE Detection Manager yüklenemedi: {e}")
            self.ppe_detector = None
    
    def detect_ip_webcam_cameras(self, network_range: str = "192.168.1.0/24") -> List[Dict]:
        """Detect IP Webcam apps on network"""
        logger.info(f"🔍 Scanning for IP Webcam cameras on {network_range}")
        
        discovered_cameras = []
        
        try:
            import ipaddress
            network = ipaddress.IPv4Network(network_range, strict=False)
            
            def test_ip_webcam(ip: str):
                """Test if IP has IP Webcam running"""
                try:
                    # Common IP Webcam ports
                    for port in [8080, 8081, 8888]:
                        test_url = f"http://{ip}:{port}"
                        response = requests.get(test_url, timeout=2)
                        
                        if response.status_code == 200:
                            # Check if it's IP Webcam
                            if 'IP Webcam' in response.text or 'video' in response.text.lower():
                                camera_info = {
                                    'ip': ip,
                                    'port': port,
                                    'type': 'ip_webcam',
                                    'video_url': f"{test_url}/video",
                                    'mjpeg_url': f"{test_url}/shot.jpg",
                                    'status': 'detected'
                                }
                                discovered_cameras.append(camera_info)
                                logger.info(f"📱 IP Webcam found: {ip}:{port}")
                                return
                except:
                    pass
            
            # Test first 20 IPs for speed
            test_ips = list(network.hosts())[:20]
            threads = []
            
            for ip in test_ips:
                thread = threading.Thread(target=test_ip_webcam, args=(str(ip),))
                thread.start()
                threads.append(thread)
            
            # Wait for all threads with timeout
            for thread in threads:
                thread.join(timeout=5)
            
            logger.info(f"✅ IP Webcam scan complete: {len(discovered_cameras)} cameras found")
            return discovered_cameras
            
        except Exception as e:
            logger.error(f"❌ IP Webcam detection failed: {e}")
            return []
    
    def test_camera_connection(self, camera_config: CameraSource) -> Dict[str, Any]:
        """Professional camera connection testing"""
        logger.info(f"🧪 Testing camera connection: {camera_config.name}")
        
        test_result = {
            'camera_id': camera_config.camera_id,
            'name': camera_config.name,
            'source_type': camera_config.source_type,
            'connection_status': 'failed',
            'response_time_ms': None,
            'resolution_detected': None,
            'fps_detected': None,
            'error_message': None,
            'test_timestamp': datetime.now(),
            'features': {
                'video_stream': False,
                'mjpeg_support': False,
                'rtsp_support': False
            }
        }
        
        start_time = time.time()
        
        try:
            if camera_config.source_type == 'ip_webcam':
                # Test IP Webcam connection
                test_result.update(self._test_ip_webcam(camera_config))
                
            elif camera_config.source_type == 'rtsp':
                # Test RTSP connection
                test_result.update(self._test_rtsp_connection(camera_config))
                
            elif camera_config.source_type == 'local':
                # Test local camera
                test_result.update(self._test_local_camera(camera_config))
                
            elif camera_config.source_type == 'usb':
                # Test USB camera
                test_result.update(self._test_usb_camera(camera_config))
            
            # Calculate response time
            test_result['response_time_ms'] = (time.time() - start_time) * 1000
            
            # Update camera config
            camera_config.last_connection_test = datetime.now()
            camera_config.connection_status = test_result['connection_status']
            
            # Success kontrolü ekle
            if test_result['connection_status'] == 'connected':
                test_result['success'] = True
            else:
                test_result['success'] = False
            
            logger.info(f"✅ Camera test complete: {camera_config.name} - {test_result['connection_status']}")
            
        except Exception as e:
            test_result['error_message'] = str(e)
            test_result['connection_status'] = 'failed'
            test_result['success'] = False
            logger.error(f"❌ Camera test failed: {camera_config.name} - {e}")
        
        return test_result
    
    def _test_ip_webcam(self, config: CameraSource) -> Dict:
        """Test IP Webcam specific connection"""
        result = {}
        
        try:
            # Authentication header'ı ekle
            headers = {}
            if config.username and config.password:
                import base64
                credentials = base64.b64encode(f"{config.username}:{config.password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
            
            # Test basic HTTP connection with authentication
            response = requests.get(config.connection_url, headers=headers, timeout=config.timeout)
            if response.status_code == 200:
                result['features']['mjpeg_support'] = True
                
                # Test video stream with authentication
                video_url = config.connection_url.replace('/shot.jpg', '/video')
                cap = cv2.VideoCapture(video_url)
                
                # Authentication için URL'yi güncelle
                if config.username and config.password:
                    safe_username = quote(config.username)
                    safe_password = quote(config.password)
                    if 'http://' in video_url:
                        video_url = video_url.replace('http://', f'http://{safe_username}:{safe_password}@')
                    elif 'https://' in video_url:
                        video_url = video_url.replace('https://', f'https://{safe_username}:{safe_password}@')
                
                cap = cv2.VideoCapture(video_url)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        result['connection_status'] = 'connected'
                        result['features']['video_stream'] = True
                        result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                        
                        # Test FPS
                        fps_start = time.time()
                        frame_count = 0
                        while frame_count < 10 and (time.time() - fps_start) < 2:
                            ret, _ = cap.read()
                            if ret:
                                frame_count += 1
                        
                        if frame_count > 0:
                            elapsed = time.time() - fps_start
                            result['fps_detected'] = round(frame_count / elapsed, 1)
                    
                    cap.release()
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'Could not open video stream'
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = f'HTTP {response.status_code}'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            error_msg = str(e)
            
            # Detaylı hata mesajları
            if 'timeout' in error_msg.lower():
                result['error_message'] = 'Bağlantı zaman aşımı. IP adresi ve port numarasını kontrol edin.'
            elif 'connection refused' in error_msg.lower():
                result['error_message'] = 'Bağlantı reddedildi. Kamera açık mı ve port doğru mu?'
            elif 'no route to host' in error_msg.lower():
                result['error_message'] = 'IP adresine ulaşılamıyor. Ağ bağlantısını kontrol edin.'
            elif 'name or service not known' in error_msg.lower():
                result['error_message'] = 'Geçersiz IP adresi formatı.'
            elif 'authentication' in error_msg.lower():
                result['error_message'] = 'Kimlik doğrulama hatası. Kullanıcı adı ve şifreyi kontrol edin.'
            elif '404' in error_msg.lower():
                result['error_message'] = 'Stream path bulunamadı. Farklı endpoint deneyin (/video, /shot.jpg).'
            elif '403' in error_msg.lower():
                result['error_message'] = 'Erişim reddedildi. Yetkilendirme gerekli.'
            elif '401' in error_msg.lower():
                result['error_message'] = 'Kimlik doğrulama gerekli. Kullanıcı adı ve şifreyi kontrol edin.'
            else:
                result['error_message'] = f'Bağlantı hatası: {error_msg}'
        
        return result
    
    def _test_rtsp_connection(self, config: CameraSource) -> Dict:
        """Test RTSP connection"""
        result = {}
        
        try:
            cap = cv2.VideoCapture(config.connection_url)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    result['connection_status'] = 'connected'
                    result['features']['rtsp_support'] = True
                    result['features']['video_stream'] = True
                    result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'No frames received'
                
                cap.release()
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = 'Could not open RTSP stream'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            result['error_message'] = str(e)
        
        return result
    
    def _test_local_camera(self, config: CameraSource) -> Dict:
        """Test local/laptop camera"""
        result = {}
        
        try:
            camera_index = int(config.connection_url)
            cap = cv2.VideoCapture(camera_index)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    result['connection_status'] = 'connected'
                    result['features']['video_stream'] = True
                    result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                    result['fps_detected'] = cap.get(cv2.CAP_PROP_FPS)
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'No frames from local camera'
                
                cap.release()
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = 'Could not open local camera'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            result['error_message'] = str(e)
        
        return result
    
    def _test_usb_camera(self, config: CameraSource) -> Dict:
        """Test USB camera connection"""
        return self._test_local_camera(config)  # Same logic as local camera
    
    def connect_camera(self, camera_config: CameraSource) -> bool:
        """Connect to camera with professional error handling"""
        logger.info(f"🔌 Connecting to camera: {camera_config.name}")
        
        try:
            # Test connection first
            test_result = self.test_camera_connection(camera_config)
            
            if test_result['connection_status'] != 'connected':
                logger.error(f"❌ Connection test failed: {camera_config.name}")
                return False
            
            # Create stream reader (FFmpeg preferred, cv2 fallback)
            if camera_config.source_type == 'ip_webcam':
                video_url = camera_config.connection_url.replace('/shot.jpg', '/video')
            else:
                video_url = camera_config.connection_url

            reader = create_stream_reader(
                video_url,
                width=camera_config.resolution[0],
                height=camera_config.resolution[1],
                fps=int(camera_config.fps),
                prefer_ffmpeg=True,
            )

            if not reader.start():
                logger.error(f"❌ Failed to start stream reader: {camera_config.name}")
                return False
            
            # Store camera
            self.active_cameras[camera_config.camera_id] = reader
            self.camera_configs[camera_config.camera_id] = camera_config
            
            # Initialize tracking
            self.fps_counters[camera_config.camera_id] = []
            self.connection_stats[camera_config.camera_id] = {
                'connected_at': datetime.now(),
                'frames_captured': 0,
                'connection_drops': 0,
                'last_frame_time': None
            }
            
            # Start frame capture thread
            capture_thread = threading.Thread(
                target=self._capture_frames,
                args=(camera_config.camera_id,),
                daemon=True
            )
            capture_thread.start()
            self.connection_threads[camera_config.camera_id] = capture_thread
            
            camera_config.connection_status = 'connected'
            logger.info(f"✅ Camera connected successfully: {camera_config.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Camera connection failed: {camera_config.name} - {e}")
            camera_config.connection_status = 'failed'
            return False
    
    def _capture_frames(self, camera_id: str):
        """Professional frame capture with performance monitoring"""
        logger.info(f"📹 Starting frame capture: {camera_id}")
        
        reader = self.active_cameras[camera_id]
        config = self.camera_configs[camera_id]
        stats = self.connection_stats[camera_id]
        
        frame_times = []
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        
        while camera_id in self.active_cameras and config.enabled:
            try:
                frame_start = time.time()
                
                frame = reader.read_frame()
                
                if frame is not None:
                    # Store frame
                    self.frame_buffers[camera_id] = frame.copy()
                    self.last_frames[camera_id] = datetime.now()
                    
                    # Update statistics
                    stats['frames_captured'] += 1
                    stats['last_frame_time'] = datetime.now()
                    
                    # Calculate FPS
                    frame_time = time.time() - frame_start
                    frame_times.append(frame_time)
                    
                    if len(frame_times) > 30:  # Keep last 30 frame times
                        frame_times.pop(0)
                    
                    if len(frame_times) > 5:
                        avg_frame_time = sum(frame_times) / len(frame_times)
                        fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
                        self.fps_counters[camera_id] = [fps]  # Store current FPS
                    
                    reconnect_attempts = 0  # Reset on successful frame
                    
                else:
                    # Frame capture failed
                    logger.warning(f"⚠️ Frame capture failed: {camera_id}")
                    
                    if reconnect_attempts < max_reconnect_attempts:
                        logger.info(f"🔄 Attempting reconnection: {camera_id} ({reconnect_attempts + 1}/{max_reconnect_attempts})")
                        
                        # Try to reconnect
                        try:
                            reader.stop()
                        except Exception:
                            pass
                        time.sleep(2)
                        
                        if config.source_type == 'ip_webcam':
                            video_url = config.connection_url.replace('/shot.jpg', '/video')
                        else:
                            video_url = config.connection_url

                        reader = create_stream_reader(
                            video_url,
                            width=config.resolution[0],
                            height=config.resolution[1],
                            fps=int(config.fps),
                            prefer_ffmpeg=True,
                        )

                        if reader.start():
                            self.active_cameras[camera_id] = reader
                            logger.info(f"✅ Reconnection successful: {camera_id}")
                        else:
                            reconnect_attempts += 1
                            stats['connection_drops'] += 1
                    else:
                        logger.error(f"❌ Max reconnection attempts reached: {camera_id}")
                        break
                
                # Frame rate control
                time.sleep(1.0 / config.fps if config.fps > 0 else 0.033)
                
            except Exception as e:
                logger.error(f"❌ Frame capture error: {camera_id} - {e}")
                time.sleep(1)
                reconnect_attempts += 1
                
                if reconnect_attempts >= max_reconnect_attempts:
                    break
        
        # Cleanup
        try:
            if reader:
                reader.stop()
        except Exception:
            pass
        
        if camera_id in self.active_cameras:
            del self.active_cameras[camera_id]
        
        config.connection_status = 'disconnected'
        logger.info(f"🔌 Frame capture stopped: {camera_id}")
    
    def disconnect_camera(self, camera_id: str) -> bool:
        """Professionally disconnect camera"""
        logger.info(f"🔌 Disconnecting camera: {camera_id}")
        
        try:
            # Mark as disabled
            if camera_id in self.camera_configs:
                self.camera_configs[camera_id].enabled = False
                self.camera_configs[camera_id].connection_status = 'disconnected'
            
            # Release stream reader
            if camera_id in self.active_cameras:
                reader = self.active_cameras[camera_id]
                try:
                    if hasattr(reader, "stop"):
                        reader.stop()
                    elif hasattr(reader, "release"):
                        reader.release()
                except Exception:
                    pass
                del self.active_cameras[camera_id]
            
            # Clean up buffers
            if camera_id in self.frame_buffers:
                del self.frame_buffers[camera_id]
            
            if camera_id in self.last_frames:
                del self.last_frames[camera_id]
            
            if camera_id in self.fps_counters:
                del self.fps_counters[camera_id]
            
            if camera_id in self.connection_stats:
                del self.connection_stats[camera_id]
            
            logger.info(f"✅ Camera disconnected: {camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Camera disconnection failed: {camera_id} - {e}")
            return False
    
    def get_camera_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get latest frame from camera"""
        return self.frame_buffers.get(camera_id)
    
    def get_camera_status(self, camera_id: str) -> Dict[str, Any]:
        """Get comprehensive camera status"""
        if camera_id not in self.camera_configs:
            return {'status': 'not_found'}
        
        config = self.camera_configs[camera_id]
        stats = self.connection_stats.get(camera_id, {})
        
        current_fps = 0
        if camera_id in self.fps_counters and self.fps_counters[camera_id]:
            current_fps = self.fps_counters[camera_id][-1]
        
        return {
            'camera_id': camera_id,
            'name': config.name,
            'source_type': config.source_type,
            'connection_status': config.connection_status,
            'enabled': config.enabled,
            'current_fps': round(current_fps, 1),
            'target_fps': config.fps,
            'resolution': f"{config.resolution[0]}x{config.resolution[1]}",
            'last_frame_time': self.last_frames.get(camera_id),
            'frames_captured': stats.get('frames_captured', 0),
            'connection_drops': stats.get('connection_drops', 0),
            'connected_since': stats.get('connected_at'),
            'last_test': config.last_connection_test
        }
    
    def get_all_camera_status(self) -> List[Dict[str, Any]]:
        """Get status of all cameras"""
        return [self.get_camera_status(camera_id) for camera_id in self.camera_configs.keys()]
    
    def create_ip_webcam_config(self, name: str, ip: str, port: int = 8080) -> CameraSource:
        """Create IP Webcam camera configuration"""
        camera_id = f"IPWEB_{ip.replace('.', '_')}_{port}"
        
        return CameraSource(
            camera_id=camera_id,
            name=name,
            source_type='ip_webcam',
            connection_url=f"http://{ip}:{port}/shot.jpg",
            resolution=(1280, 720),
            fps=25,
            timeout=10,
            retry_attempts=3
        )
    
    def create_local_camera_config(self, name: str, camera_index: int = 0) -> CameraSource:
        """Create local camera configuration"""
        camera_id = f"LOCAL_{camera_index}"
        
        return CameraSource(
            camera_id=camera_id,
            name=name,
            source_type='local',
            connection_url=str(camera_index),
            resolution=(1280, 720),
            fps=30,
            timeout=5,
            retry_attempts=2
        )
    
    def save_camera_configs(self, file_path: str = "configs/camera_configs.json"):
        """Save camera configurations to file"""
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            configs_data = {}
            for camera_id, config in self.camera_configs.items():
                configs_data[camera_id] = {
                    'camera_id': config.camera_id,
                    'name': config.name,
                    'source_type': config.source_type,
                    'connection_url': config.connection_url,
                    'backup_url': config.backup_url,
                    'username': config.username,
                    'password': config.password,
                    'resolution': config.resolution,
                    'fps': config.fps,
                    'timeout': config.timeout,
                    'retry_attempts': config.retry_attempts,
                    'enabled': config.enabled
                }
            
            with open(file_path, 'w') as f:
                json.dump(configs_data, f, indent=2, default=str)
            
            logger.info(f"✅ Camera configurations saved: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save camera configs: {e}")
    
    def load_camera_configs(self, file_path: str = "configs/camera_configs.json"):
        """Load camera configurations from file"""
        try:
            if not Path(file_path).exists():
                logger.info(f"📁 No camera config file found: {file_path}")
                return
            
            with open(file_path, 'r') as f:
                configs_data = json.load(f)
            
            for camera_id, config_dict in configs_data.items():
                config = CameraSource(**config_dict)
                self.camera_configs[camera_id] = config
            
            logger.info(f"✅ Camera configurations loaded: {len(configs_data)} cameras")
            
        except Exception as e:
            logger.error(f"❌ Failed to load camera configs: {e}")
    
    def discover_and_sync_cameras(self, company_id: str = "DEFAULT_COMPANY", network_range: str = "192.168.1.0/24") -> Dict[str, Any]:
        """
        Kameraları keşfet ve veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si
            network_range: Taranacak ağ aralığı
            
        Returns:
            Keşif ve senkronizasyon sonucu
        """
        try:
            from database.database_adapter import get_camera_discovery_manager
            from integrations.cameras.camera_discovery import IPCameraDiscovery
            
            result = {
                'network_scan': {},
                'ip_webcam_scan': {},
                'database_sync': {},
                'total_discovered': 0,
                'total_synced': 0,
                'success': False
            }
            
            logger.info(f"🔍 Starting comprehensive camera discovery for company: {company_id}")
            
            # 1. IP Camera Discovery (Professional cameras)
            logger.info("📹 Scanning for IP cameras...")
            ip_discovery = IPCameraDiscovery()
            network_result = ip_discovery.scan_network(network_range, timeout=2)
            result['network_scan'] = network_result
            
            # 2. IP Webcam Discovery (Phone cameras)  
            logger.info("📱 Scanning for IP Webcam apps...")
            ip_webcam_cameras = self.detect_ip_webcam_cameras(network_range)
            result['ip_webcam_scan'] = {
                'cameras': ip_webcam_cameras,
                'found_count': len(ip_webcam_cameras)
            }
            
            # 3. Combine all discovered cameras
            all_discovered = []
            
            # Add IP cameras
            if network_result.get('cameras'):
                all_discovered.extend(network_result['cameras'])
            
            # Add IP Webcam cameras (convert format)
            for webcam in ip_webcam_cameras:
                webcam_camera = {
                    'ip': webcam['ip'],
                    'port': webcam['port'],
                    'brand': 'IP Webcam',
                    'model': 'Mobile Camera',
                    'rtsp_url': f"http://{webcam['ip']}:{webcam['port']}/video",
                    'resolution': '1280x720',
                    'fps': 25
                }
                all_discovered.append(webcam_camera)
            
            result['total_discovered'] = len(all_discovered)
            logger.info(f"✅ Total cameras discovered: {result['total_discovered']}")
            
            # 4. Sync to database
            if all_discovered:
                logger.info("💾 Syncing discovered cameras to database...")
                discovery_manager = get_camera_discovery_manager()
                sync_result = discovery_manager.sync_discovered_cameras_to_db(company_id, all_discovered)
                result['database_sync'] = sync_result
                result['total_synced'] = sync_result['added'] + sync_result['updated']
                
                logger.info(f"✅ Database sync complete: {sync_result['added']} added, {sync_result['updated']} updated")
            else:
                logger.info("ℹ️ No cameras discovered, skipping database sync")
                result['database_sync'] = {'message': 'No cameras to sync'}
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Camera discovery and sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result
    
    def sync_config_cameras_to_db(self, company_id: str, config_file_path: str = "configs/industrial_config.yaml") -> Dict[str, Any]:
        """
        Config dosyasındaki kameraları veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si
            config_file_path: Config dosyası yolu
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            import yaml
            from database.database_adapter import get_camera_discovery_manager
            
            result = {
                'config_loaded': False,
                'cameras_found': 0,
                'database_sync': {},
                'success': False
            }
            
            logger.info(f"🔧 Syncing config cameras to database for company: {company_id}")
            
            # Config dosyasını yükle
            if not Path(config_file_path).exists():
                logger.warning(f"⚠️ Config file not found: {config_file_path}")
                result['error'] = f"Config file not found: {config_file_path}"
                return result
            
            with open(config_file_path, 'r') as f:
                config = yaml.safe_load(f)
            
            cameras = config.get('cameras', {})
            result['config_loaded'] = True
            result['cameras_found'] = len(cameras)
            
            logger.info(f"📹 Found {len(cameras)} cameras in config file")
            
            # Veritabanına senkronize et
            if cameras:
                discovery_manager = get_camera_discovery_manager()
                sync_result = discovery_manager.sync_config_cameras_to_db(company_id, cameras)
                result['database_sync'] = sync_result
                
                logger.info(f"✅ Config sync complete: {sync_result['added']} added, {sync_result['updated']} updated")
            else:
                logger.info("ℹ️ No cameras in config file")
                result['database_sync'] = {'message': 'No cameras in config'}
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Config camera sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result
    
    def get_database_cameras(self, company_id: str) -> List[Dict[str, Any]]:
        """
        Veritabanından şirket kameralarını getir
        
        Args:
            company_id: Şirket ID'si
            
        Returns:
            Kameralar listesi
        """
        try:
            from database.database_adapter import get_db_adapter
            
            db_adapter = get_db_adapter()
            
            query = '''
                SELECT camera_id, camera_name, location, ip_address, rtsp_url, 
                       resolution, fps, status, created_at, last_detection
                FROM cameras 
                WHERE company_id = ? AND status != 'deleted'
                ORDER BY created_at DESC
            '''
            
            results = db_adapter.execute_query(query, (company_id,), fetch_all=True)
            
            cameras = []
            for row in results:
                camera = {
                    'camera_id': row[0],
                    'name': row[1],
                    'location': row[2],
                    'ip_address': row[3],
                    'rtsp_url': row[4],
                    'resolution': row[5],
                    'fps': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'last_detection': row[9]
                }
                cameras.append(camera)
            
            logger.info(f"📹 Retrieved {len(cameras)} cameras from database for company: {company_id}")
            return cameras
            
        except Exception as e:
            logger.error(f"❌ Failed to get database cameras: {e}")
            return []
    
    def full_camera_sync(self, company_id: str = "DEFAULT_COMPANY", network_range: str = "192.168.1.0/24") -> Dict[str, Any]:
        """
        Kapsamlı kamera senkronizasyonu: Discovery + Config + Database
        
        Args:
            company_id: Şirket ID'si
            network_range: Taranacak ağ aralığı
            
        Returns:
            Tam senkronizasyon sonucu
        """
        try:
            result = {
                'discovery_result': {},
                'config_sync_result': {},
                'final_camera_count': 0,
                'success': False
            }
            
            logger.info(f"🚀 Starting full camera synchronization for company: {company_id}")
            
            # 1. Network discovery ve database sync
            discovery_result = self.discover_and_sync_cameras(company_id, network_range)
            result['discovery_result'] = discovery_result
            
            # 2. Config kameralarını sync et
            config_sync_result = self.sync_config_cameras_to_db(company_id)
            result['config_sync_result'] = config_sync_result
            
            # 3. Final kamera sayısını al
            final_cameras = self.get_database_cameras(company_id)
            result['final_camera_count'] = len(final_cameras)
            
            logger.info(f"✅ Full camera sync complete: {result['final_camera_count']} total cameras in database")
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Full camera sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result

    def smart_test_camera_connection(self, ip_address: str, name: str = "Smart Detected Camera") -> Dict[str, Any]:
        """
        Akıllı kamera bağlantı testi - Sadece IP adresi ile
        
        Args:
            ip_address: Kamera IP adresi
            name: Kamera adı
            
        Returns:
            Test sonucu
        """
        logger.info(f"🧠 Smart camera test for {ip_address}")
        
        # Akıllı tespit sistemi
        detector = SmartCameraDetector()
        detection_result = detector.smart_detect_camera(ip_address)
        
        if not detection_result['success']:
            return {
                'success': False,
                'error': detection_result['error'],
                'detection_info': detection_result
            }
        
        # Tespit edilen bilgilerle kamera konfigürasyonu oluştur
        camera_config = RealCameraConfig(
            camera_id=f"SMART_{ip_address.replace('.', '_')}",
            name=name,
            ip_address=ip_address,
            port=detection_result['port'],
            protocol=detection_result['protocol'],
            stream_path=detection_result['path'],
            timeout=10
        )
        
        # Normal test yap
        test_result = self.test_real_camera_connection(camera_config)
        test_result['detection_info'] = detection_result
        
        return test_result

    def smart_discover_cameras(self, network_range: str = "192.168.1.0/24") -> List[Dict]:
        """
        Akıllı kamera keşfi - Gelişmiş tespit sistemi
        
        Args:
            network_range: Taranacak ağ aralığı
            
        Returns:
            Keşfedilen kameralar listesi
        """
        logger.info(f"🧠 Smart camera discovery for {network_range}")
        
        discovered_cameras = []
        detector = SmartCameraDetector()
        
        try:
            import ipaddress
            network = ipaddress.IPv4Network(network_range, strict=False)
            
            # Paralel tarama için ThreadPool
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def scan_ip(ip):
                try:
                    detection_result = detector.smart_detect_camera(str(ip))
                    if detection_result['success']:
                        return {
                            'ip': str(ip),
                            'model': detection_result['model'],
                            'protocol': detection_result['protocol'],
                            'port': detection_result['port'],
                            'path': detection_result['path'],
                            'stream_url': detection_result['url'],
                            'confidence': detection_result['confidence'],
                            'detection_info': detection_result
                        }
                except Exception as e:
                    logger.debug(f"Scan failed for {ip}: {e}")
                return None
            
            # Paralel tarama
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(scan_ip, ip): ip for ip in network.hosts()}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        discovered_cameras.append(result)
                        logger.info(f"📹 Smart discovered: {result['model']} at {result['ip']}")
            
            logger.info(f"✅ Smart discovery complete: {len(discovered_cameras)} cameras found")
            return discovered_cameras
            
        except Exception as e:
            logger.error(f"❌ Smart discovery failed: {e}")
            return []

    def perform_ppe_detection(self, camera_id: str, frame: np.ndarray, sector: Optional[str] = None, company_id: Optional[str] = None, use_pose: bool = True) -> Dict:
        """IP Kamera için PPE Detection yap
        
        Args:
            camera_id: Kamera ID
            frame: Video frame
            sector: Sektör tipi
            company_id: Şirket ID (opsiyonel, yoksa database'den bulunur)
            use_pose: Pose-aware detection kullan (YOLOv8-Pose)
        """
        try:
            # 🚀 FAZ 3: POSE-AWARE DETECTION
            if use_pose:
                try:
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    pose_detector = get_pose_aware_detector(ppe_detector=self.ppe_detector)
                    
                    logger.info(f"🎯 Using POSE-AWARE detection for camera {camera_id}")
                    result = pose_detector.detect_with_pose(frame, sector, confidence=0.25)
                    
                    # Validate result is a dictionary
                    if not isinstance(result, dict):
                        logger.warning(f"⚠️ Pose-aware detection returned non-dict result: {type(result)}, falling back to standard")
                        raise ValueError(f"Invalid result type: {type(result)}")
                    
                    # Add camera_id and company_id to result
                    result['camera_id'] = camera_id
                    result['company_id'] = company_id
                    
                    # Ensure required keys exist
                    if 'people_detected' not in result:
                        result['people_detected'] = 0
                    if 'compliance_rate' not in result:
                        result['compliance_rate'] = 0.0
                    if 'violations_count' not in result:
                        result['violations_count'] = 0
                    
                    # Cache and save result
                    self.detection_results[camera_id] = result
                    self.save_detection_to_database(camera_id, result, sector)
                    
                    logger.info(f"✅ Pose-aware detection: People: {result.get('people_detected', 0)}, "
                               f"Compliance: {result.get('compliance_rate', 0.0)}%, Violations: {result.get('violations_count', 0)}")
                    return result
                    
                except Exception as pose_error:
                    logger.warning(f"⚠️ Pose-aware detection failed, falling back to standard: {pose_error}")
                    import traceback
                    logger.debug(f"⚠️ Pose-aware detection traceback: {traceback.format_exc()}")
                    # Fall through to standard detection
            
            # 🎯 FAZ 1-2: STANDARD ANATOMICAL DETECTION (FALLBACK)
            # Sector resolution: fetch from DB if not explicitly provided
            if not sector:
                try:
                    if not company_id:
                        # Attempt to resolve company_id from camera mapping
                        from database.database_adapter import get_db_adapter
                        db_local = get_db_adapter()
                        # Reuse existing helper if available; fallback to cameras table scan
                        camera_info = db_local.get_camera_by_id(camera_id, company_id or '') if hasattr(db_local, 'get_camera_by_id') else None
                        if camera_info and camera_info.get('company_id'):
                            company_id = camera_info.get('company_id')
                    if company_id:
                        from database.database_adapter import get_db_adapter
                        db_local = get_db_adapter()
                        company = db_local.get_company_info(company_id) if hasattr(db_local, 'get_company_info') else None
                        if company:
                            if isinstance(company, dict):
                                sector = company.get('sector') or sector
                            elif isinstance(company, (list, tuple)) and len(company) >= 5:
                                sector = company[4] or sector  # typical index for sector
                except Exception as sector_resolve_error:
                    logger.warning(f"⚠️ Sector resolve failed for camera {camera_id}: {sector_resolve_error}")
            if not sector:
                logger.warning(f"⚠️ Sector not set for camera {camera_id}, using company configuration fallback if any")
            if self.ppe_detector is None:
                logger.warning("⚠️ PPE Detection Manager yüklü değil")
                return {
                    'detections': [],
                    'people_detected': 0,
                    'compliance_rate': 0,
                    'ppe_violations': [],
                    'timestamp': time.time(),
                    'sector': sector,
                    'camera_id': camera_id,
                    'total_people': 0,
                    'compliant_people': 0,
                    'violations_count': 0
                }
            
            # Frame'i PPE detection için hazırla
            if frame is None or frame.size == 0:
                logger.warning(f"⚠️ Geçersiz frame: {camera_id}")
                return {
                    'detections': [],
                    'people_detected': 0,
                    'compliance_rate': 0,
                    'ppe_violations': [],
                    'timestamp': time.time(),
                    'sector': sector,
                    'camera_id': camera_id,
                    'total_people': 0,
                    'compliant_people': 0,
                    'violations_count': 0
                }
            
            # 🎯 PPE Detection yap - SH17 Model ile DETAYLI DETECTION + EKSİK PPE TESPİTİ
            detections = self.ppe_detector.detect_ppe(frame, sector, confidence=0.25)  # Confidence düşürüldü

            def _iou(box_a, box_b):
                try:
                    ax1, ay1, ax2, ay2 = [float(v) for v in box_a]
                    bx1, by1, bx2, by2 = [float(v) for v in box_b]
                    inter_x1 = max(ax1, bx1)
                    inter_y1 = max(ay1, by1)
                    inter_x2 = min(ax2, bx2)
                    inter_y2 = min(ay2, by2)
                    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
                        return 0.0
                    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                    area_a = (ax2 - ax1) * (ay2 - ay1)
                    area_b = (bx2 - bx1) * (by2 - by1)
                    union = max(area_a + area_b - inter, 1e-6)
                    return inter / union
                except Exception:
                    return 0.0

            def _nms(dets, iou_thresh=0.5):
                # Class-aware simple NMS on same class
                by_class = {}
                for d in dets:
                    cls = d.get('class_name', 'unknown')
                    by_class.setdefault(cls, []).append(d)
                kept = []
                for cls, items in by_class.items():
                    items_sorted = sorted(items, key=lambda x: x.get('confidence', 0.0), reverse=True)
                    while items_sorted:
                        best = items_sorted.pop(0)
                        kept.append(best)
                        items_sorted = [x for x in items_sorted if _iou(best.get('bbox', [0,0,0,0]), x.get('bbox', [0,0,0,0])) < iou_thresh]
                return kept
            
            # Detection sonucunu kontrol et - SH17 model liste döndürür
            if isinstance(detections, list) and len(detections) > 0:
                # Kişileri ve PPE itemlarını ayır
                people = [d for d in detections if isinstance(d, dict) and d.get('class_name') == 'person']
                # Pozitif sınıflar (NO-* hariç)
                helmets_pos = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['helmet','hard_hat','Hardhat','Safety Helmet']]
                vests_pos   = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['safety_vest','vest','Safety Vest']]
                shoes_pos   = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['safety_shoes','shoes','Safety Shoes']]
                # Negatif sınıflar (NO-*)
                helmets_neg = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['NO-Hardhat','NO-Helmet','no_helmet']]
                vests_neg   = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['NO-Safety Vest','NO-Vest','no_vest']]
                shoes_neg   = [d for d in detections if isinstance(d, dict) and d.get('class_name') in ['NO-Safety Shoes','NO-Shoes','no_shoes']]

                # Basit class-aware NMS (duplike kutuları azalt)
                helmets_pos = _nms(helmets_pos, 0.5)
                vests_pos   = _nms(vests_pos, 0.5)
                shoes_pos   = _nms(shoes_pos, 0.5)
                helmets_neg = _nms(helmets_neg, 0.5)
                vests_neg   = _nms(vests_neg, 0.5)
                shoes_neg   = _nms(shoes_neg, 0.5)
                
                people_detected = len(people)
                
                # 🎯 EKSİK PPE TESPİTİ - Her kişi için PPE kontrolü
                violations = []
                compliant_people = 0
                missing_ppe_detections = []  # Eksik PPE'leri göstermek için
                
                if people_detected > 0:
                    for person in people:
                        person_bbox = person.get('bbox', [])
                        if len(person_bbox) != 4:
                            continue
                        
                        px1, py1, px2, py2 = person_bbox
                        person_center_x = (px1 + px2) / 2
                        person_center_y = (py1 + py2) / 2
                        person_width = px2 - px1
                        person_height = py2 - py1
                        
                        # Bu kişiye ait PPE'leri bul (proximity based) + ANATOMİK BÖLGE OPTİMİZASYONU
                        has_helmet = False
                        has_vest = False
                        has_shoes = False
                        helmet_detection = None
                        vest_detection = None
                        shoes_detection = None
                        
                        # Frame boyutlarını al (bbox clipping için)
                        frame_height, frame_width = frame.shape[:2]
                        
                        # HELMET: yalnızca baş genişliği (%40) + yükseklik %24
                        head_width = person_width * 0.40
                        head_x1 = max(0, person_center_x - head_width / 2)
                        head_x2 = min(frame_width, person_center_x + head_width / 2)
                        head_y1 = max(0, py1)
                        head_y2 = min(frame_height, py1 + person_height * 0.24)
                        head_region = [head_x1, head_y1, head_x2, head_y2]
                        
                        # VEST: Geniş, omuzları kapsayan (%70 genişlik) dikey 0.20-0.65
                        torso_width = person_width * 0.70
                        torso_x1 = max(0, person_center_x - torso_width / 2)
                        torso_x2 = min(frame_width, person_center_x + torso_width / 2)
                        torso_y1 = max(0, py1 + person_height * 0.20)
                        torso_y2 = min(frame_height, py1 + person_height * 0.65)
                        torso_region = [torso_x1, torso_y1, torso_x2, torso_y2]
                        
                        # SHOES: İki ayrı ayak (%25 genişlik her biri) - yakınlık toleransı artırıldı
                        foot_width = person_width * 0.25
                        left_foot_x1 = max(0, px1)
                        left_foot_x2 = min(frame_width, px1 + foot_width)
                        right_foot_x1 = max(0, px2 - foot_width)
                        right_foot_x2 = min(frame_width, px2)
                        feet_y1 = max(0, py2 - person_height * 0.15)
                        feet_y2 = min(frame_height, py2)
                        feet_region_left = [left_foot_x1, feet_y1, left_foot_x2, feet_y2]
                        feet_region_right = [right_foot_x1, feet_y1, right_foot_x2, feet_y2]
                        
                        # 🎯 PRODUCTION-GRADE: Helmet kontrolü - Geliştirilmiş spatial reasoning
                        from detection.utils.detection_utils import DetectionUtils
                        
                        best_helmet_match = None
                        best_helmet_score = 0.0
                        
                        for helmet in helmets_pos:
                            hbbox = helmet.get('bbox', [])
                            if len(hbbox) == 4:
                                # Proximity score ile association
                                proximity = DetectionUtils.calculate_proximity_score(
                                    person_bbox, hbbox, 'helmet'
                                )
                                confidence = helmet.get('confidence', 0.5)
                                combined_score = (confidence * 0.4) + (proximity * 0.6)
                                
                                if combined_score > best_helmet_score and combined_score >= 0.25:
                                    best_helmet_score = combined_score
                                    best_helmet_match = helmet
                        
                        if best_helmet_match:
                            has_helmet = True
                            helmet_detection = {
                                'bbox': head_region,
                                'class_name': 'Helmet',
                                'confidence': best_helmet_match.get('confidence', 0.9),
                                'missing': False,
                                'proximity_score': best_helmet_score
                            }

                        # Negatif helmet ile çakışma: yüksek skor/IoU önceliği, fark <0.1 ise pozitif lehine
                        if has_helmet:
                            for n in helmets_neg:
                                iou_h = _iou(n.get('bbox', [0,0,0,0]), head_region)
                                if iou_h > 0.5:
                                    if n.get('confidence',0)-helmet_detection.get('confidence',0) > 0.1:
                                        has_helmet = False
                                        helmet_detection = None
                                        logger.debug("Helmet conflict: NO-* won due to higher confidence")
                                    else:
                                        logger.debug("Helmet conflict: POSITIVE kept (tie or lower NO-)")
                        
                        # 🎯 PRODUCTION-GRADE: Vest kontrolü - Geliştirilmiş spatial reasoning
                        best_vest_match = None
                        best_vest_score = 0.0
                        
                        for vest in vests_pos:
                            vbbox = vest.get('bbox', [])
                            if len(vbbox) == 4:
                                # Proximity score ile association
                                proximity = DetectionUtils.calculate_proximity_score(
                                    person_bbox, vbbox, 'vest'
                                )
                                confidence = vest.get('confidence', 0.5)
                                combined_score = (confidence * 0.4) + (proximity * 0.6)
                                
                                if combined_score > best_vest_score and combined_score >= 0.25:
                                    best_vest_score = combined_score
                                    best_vest_match = vest
                        
                        if best_vest_match:
                            has_vest = True
                            # ✅ ANATOMİK BÖLGE: Sadece torso bölgesini çerçevele
                            vest_detection = {
                                'bbox': torso_region,
                                'class_name': 'Safety Vest',
                                'confidence': best_vest_match.get('confidence', 0.9),
                                'missing': False,
                                'proximity_score': best_vest_score
                            }

                        if has_vest:
                            for n in vests_neg:
                                iou_v = _iou(n.get('bbox', [0,0,0,0]), torso_region)
                                if iou_v > 0.5:
                                    if n.get('confidence',0)-vest_detection.get('confidence',0) > 0.1:
                                        has_vest = False
                                        vest_detection = None
                                        logger.debug("Vest conflict: NO-* won due to higher confidence")
                                    else:
                                        logger.debug("Vest conflict: POSITIVE kept (tie or lower NO-)")
                        
                        # 🎯 PRODUCTION-GRADE: Shoes kontrolü - Geliştirilmiş spatial reasoning
                        best_shoe_match = None
                        best_shoe_score = 0.0
                        
                        for shoe in shoes_pos:
                            sbbox = shoe.get('bbox', [])
                            if len(sbbox) == 4:
                                # Proximity score ile association
                                proximity = DetectionUtils.calculate_proximity_score(
                                    person_bbox, sbbox, 'shoes'
                                )
                                confidence = shoe.get('confidence', 0.5)
                                combined_score = (confidence * 0.4) + (proximity * 0.6)
                                
                                if combined_score > best_shoe_score and combined_score >= 0.25:
                                    best_shoe_score = combined_score
                                    best_shoe_match = shoe
                        
                        if best_shoe_match:
                            has_shoes = True
                            # ✅ ANATOMİK BÖLGE: tekleştirilmiş gösterim (sade)
                            foot_union = [min(feet_region_left[0], feet_region_right[0]),
                                         min(feet_region_left[1], feet_region_right[1]),
                                         max(feet_region_left[2], feet_region_right[2]),
                                         max(feet_region_left[3], feet_region_right[3])]
                            missing_ppe_detections.append({
                                'bbox': foot_union,
                                'class_name': 'Safety Shoes',
                                'confidence': best_shoe_match.get('confidence', 0.9),
                                'missing': False,
                                'proximity_score': best_shoe_score
                            })

                        # Negatif ayakkabı ile çakışma
                        if has_shoes:
                            for n in shoes_neg:
                                iou_s = _iou(n.get('bbox', [0,0,0,0]), [min(feet_region_left[0], feet_region_right[0]),
                                                                         min(feet_region_left[1], feet_region_right[1]),
                                                                         max(feet_region_left[2], feet_region_right[2]),
                                                                         max(feet_region_left[3], feet_region_right[3])])
                                if iou_s > 0.5:
                                    # Ayakkabıda çakışma: pozitif lehine bağla eğer skor farkı < 0.1
                                    pos_conf = 0.9
                                    for it in missing_ppe_detections:
                                        if it.get('class_name') == 'Safety Shoes' and not it.get('missing'):
                                            pos_conf = it.get('confidence', 0.9)
                                            break
                                    if n.get('confidence',0) - pos_conf > 0.1:
                                        has_shoes = False
                                        # pozitif kaydı sil
                                        missing_ppe_detections = [it for it in missing_ppe_detections if not (it.get('class_name')=='Safety Shoes' and not it.get('missing'))]
                                        logger.debug("Shoes conflict: NO-* won due to higher confidence")
                                    else:
                                        logger.debug("Shoes conflict: POSITIVE kept (tie or lower NO-)")
                        
                        # ✅ MEVCUT PPE'leri ekle (anatomik bölge ile)
                        if helmet_detection:
                            missing_ppe_detections.append(helmet_detection)
                        if vest_detection:
                            missing_ppe_detections.append(vest_detection)
                        
                        # ❌ EKSİK PPE'leri işaretle (anatomik bölge ile)
                        if not has_helmet:
                            violations.append('Baret eksik')
                            missing_ppe_detections.append({
                                'bbox': head_region,
                                'class_name': 'NO-Helmet',
                                'confidence': 0.9,
                                'missing': True
                            })
                        
                        if not has_vest:
                            violations.append('Yelek eksik')
                            missing_ppe_detections.append({
                                'bbox': torso_region,
                                'class_name': 'NO-Vest',
                                'confidence': 0.9,
                                'missing': True
                            })
                        
                        if not has_shoes:
                            violations.append('Güvenlik ayakkabısı eksik')
                            # Tek eksik kutu (sade)
                            foot_union = [min(feet_region_left[0], feet_region_right[0]),
                                          min(feet_region_left[1], feet_region_right[1]),
                                          max(feet_region_left[2], feet_region_right[2]),
                                          max(feet_region_left[3], feet_region_right[3])]
                            missing_ppe_detections.append({
                                'bbox': foot_union,
                                'class_name': 'NO-Shoes',
                                'confidence': 0.9,
                                'missing': True
                            })
                        
                        # Compliance kontrolü
                        if has_helmet and has_vest:  # Minimum gereksinim
                            compliant_people += 1
                        
                        # 🚨 VIOLATION TRACKER - Event-based ihlal takibi
                        person_violations_list = []
                        if not has_helmet:
                            person_violations_list.append('Baret eksik')
                        if not has_vest:
                            person_violations_list.append('Yelek eksik')
                        if not has_shoes:
                            person_violations_list.append('Güvenlik ayakkabısı eksik')
                        
                        # Violation tracker'a gönder
                        if person_violations_list:
                            try:
                                violation_tracker = get_violation_tracker()
                                
                                # Company ID'yi al (parametre veya database'den)
                                if company_id is None:
                                    from database.database_adapter import get_db_adapter
                                    db = get_db_adapter()
                                    # Önce camera_id ile company_id'yi bulmaya çalış (tüm company'lerde ara)
                                    try:
                                        # SQLite için: company_id olmadan arama yap
                                        if db.db_type == 'sqlite':
                                            query = 'SELECT company_id FROM cameras WHERE camera_id = ? AND status != ? LIMIT 1'
                                        else:  # PostgreSQL
                                            query = 'SELECT company_id FROM cameras WHERE camera_id = %s AND status != %s LIMIT 1'
                                        
                                        result = db.execute_query(query, (camera_id, 'deleted'), fetch_all=False)
                                        if result and isinstance(result, dict):
                                            company_id = result.get('company_id', 'UNKNOWN')
                                        elif result:
                                            # Eğer dict değilse (fallback)
                                            company_id = str(result).strip() if result else 'UNKNOWN'
                                        else:
                                            company_id = 'UNKNOWN'
                                    except Exception as db_error:
                                        logger.warning(f"⚠️ Company ID bulunamadı: {db_error}, UNKNOWN kullanılıyor")
                                        import traceback
                                        logger.debug(f"⚠️ Company ID traceback: {traceback.format_exc()}")
                                        company_id = 'UNKNOWN'
                                
                                if company_id == 'UNKNOWN':
                                    logger.warning(f"⚠️ Company ID UNKNOWN olarak kullanılıyor - camera_id: {camera_id}")
                                
                                new_violations, ended_violations = violation_tracker.process_detection(
                                    camera_id=camera_id,
                                    company_id=company_id,
                                    person_bbox=person_bbox,
                                    violations=person_violations_list,
                                    frame_snapshot=frame
                                )
                                
                                # 📸 YENİ İHLALLER İÇİN SNAPSHOT ÇEK (İLK KEZ)
                                # Sadece yeni başlayan ihlaller için snapshot çekiyoruz
                                for new_violation in new_violations:
                                    try:
                                        # ✅ Kişinin frame'de görünür olduğundan emin ol
                                        person_visible = True
                                        if person_bbox:
                                            px1, py1, px2, py2 = person_bbox
                                            # Kişi frame içinde mi kontrol et
                                            if px1 < 0 or py1 < 0 or px2 > frame.shape[1] or py2 > frame.shape[0]:
                                                person_visible = False
                                            # Kişi çok küçük mü kontrol et (minimum %5 frame)
                                            person_area = (px2 - px1) * (py2 - py1)
                                            frame_area = frame.shape[0] * frame.shape[1]
                                            if person_area < (frame_area * 0.05):
                                                person_visible = False
                                        
                                        if not person_visible:
                                            logger.warning(f"⚠️ Kişi frame'de yeterince görünür değil, snapshot atlandı")
                                            # Database'e snapshot olmadan kaydet
                                            from database.database_adapter import get_db_adapter
                                            db = get_db_adapter()
                                            db.add_violation_event(new_violation)
                                            continue
                                        
                                        # 📸 SNAPSHOT ÇEK - İLK İHLAL ANI (EKSİK EKİPMANLARLA)
                                        snapshot_manager = get_snapshot_manager()
                                        snapshot_path = snapshot_manager.capture_violation_snapshot(
                                            frame=frame,
                                            company_id=company_id,
                                            camera_id=camera_id,
                                            person_id=new_violation['person_id'],
                                            violation_type=new_violation['violation_type'],
                                            person_bbox=person_bbox,
                                            event_id=new_violation['event_id']
                                        )
                                        
                                        # Snapshot path'i violation event'e ekle
                                        if snapshot_path:
                                            new_violation['snapshot_path'] = snapshot_path
                                            logger.info(f"📸 VIOLATION SNAPSHOT SAVED: {snapshot_path} - {new_violation['violation_type']} - Camera: {camera_id}")
                                        else:
                                            logger.warning(f"⚠️ Violation snapshot kaydedilemedi: {new_violation['violation_type']} - Camera: {camera_id} - Person: {new_violation['person_id']}")
                                        
                                        # Database'e kaydet
                                        from database.database_adapter import get_db_adapter
                                        db = get_db_adapter()
                                        db.add_violation_event(new_violation)
                                        
                                        logger.info(f"🚨 NEW VIOLATION + SNAPSHOT: {new_violation['violation_type']} - {new_violation['event_id']}")
                                    except Exception as ve:
                                        logger.error(f"❌ Violation event save error: {ve}")
                                
                                # ✅ BİTEN İHLALLER İÇİN SNAPSHOT ÇEK (ÇÖZÜM ANI)
                                # Kişi ekipmanlarını taktığında son durumu kaydet
                                for ended_violation in ended_violations:
                                    try:
                                        from database.database_adapter import get_db_adapter
                                        db = get_db_adapter()
                                        
                                        # 📸 ÇÖZÜM SNAPSHOT'I ÇEK (TAM EKİPMANLARLA)
                                        # Bu snapshot kişinin ekipmanları taktıktan sonraki halini gösterir
                                        try:
                                            snapshot_manager = get_snapshot_manager()
                                            resolution_snapshot_path = snapshot_manager.capture_violation_snapshot(
                                                frame=frame,
                                                company_id=company_id,
                                                camera_id=camera_id,
                                                person_id=ended_violation['person_id'],
                                                violation_type=f"{ended_violation['violation_type']}_resolved",
                                                person_bbox=person_bbox,
                                                event_id=ended_violation['event_id']
                                            )
                                            
                                            if resolution_snapshot_path:
                                                logger.info(f"📸 RESOLUTION SNAPSHOT SAVED: {resolution_snapshot_path} - {ended_violation['violation_type']} resolved")
                                            else:
                                                logger.warning(f"⚠️ Resolution snapshot kaydedilemedi: {ended_violation['violation_type']} - {camera_id}")
                                        except Exception as snap_error:
                                            logger.error(f"❌ Resolution snapshot error: {snap_error}")
                                            import traceback
                                            logger.error(f"❌ Snapshot traceback: {traceback.format_exc()}")
                                        
                                        # Event'i güncelle (resolution snapshot path ile)
                                        db.update_violation_event(
                                            ended_violation['event_id'],
                                            {
                                                'end_time': ended_violation['end_time'],
                                                'duration_seconds': ended_violation['duration_seconds'],
                                                'status': ended_violation['status'],
                                                'resolution_snapshot_path': resolution_snapshot_path if 'resolution_snapshot_path' in locals() else None
                                            }
                                        )
                                        
                                        # Person violation stats'ı güncelle
                                        db.update_person_violation_stats(
                                            person_id=ended_violation['person_id'],
                                            company_id=company_id,
                                            violation_type=ended_violation['violation_type'],
                                            duration_seconds=ended_violation['duration_seconds']
                                        )
                                        
                                        logger.info(f"✅ VIOLATION RESOLVED: {ended_violation['violation_type']} - Duration: {ended_violation['duration_seconds']}s")
                                    except Exception as ve:
                                        logger.error(f"❌ Violation event update error: {ve}")
                                        
                            except Exception as vt_error:
                                logger.error(f"❌ Violation tracker error: {vt_error}")
                
                # Sektöre göre gereklilik seti (varsa DB'den oku)
                required_set = {'helmet','safety_vest'}
                try:
                    from database.database_adapter import get_db_adapter
                    db_local = get_db_adapter()
                    company = db_local.get_company_info(company_id) if company_id and hasattr(db_local, 'get_company_info') else None
                    if company:
                        import json
                        rp = None
                        if isinstance(company, dict):
                            rp = company.get('required_ppe') or company.get('ppe_config')
                        elif isinstance(company, (list, tuple)):
                            # sütun ismi bilinmiyorsa atla
                            rp = None
                        if rp:
                            if isinstance(rp, str):
                                rp = json.loads(rp)
                            if isinstance(rp, dict) and 'required' in rp:
                                required_set = set(rp['required'])
                            elif isinstance(rp, list):
                                required_set = set(rp)
                except Exception:
                    pass

                # Compliance rate hesapla (sadece required olanlara göre)
                # Minimum gereklilik: required_set'teki öğeler
                required_ok = 0
                for _ in range(people_detected):
                    # Basit metrik: kişi bazında sayım yerine, var/yok toplamına göre yüzde
                    pass
                # Kişi bazlı sayım mevcut olduğundan, compliant_people zaten helmet&vest için hesaplandı.
                compliance_rate = int((compliant_people / max(people_detected, 1)) * 100) if people_detected > 0 else 100
                
                # Eksik PPE detection'larını ana listeye ekle
                all_detections = detections + missing_ppe_detections
                
                # Detection result'ı hazırla
                detection_result = {
                    'detections': all_detections,  # ✅ Tüm detections + eksik PPE'ler
                    'people_detected': people_detected,
                    'compliance_rate': compliance_rate,
                    'ppe_violations': list(set(violations)),  # Duplicate'leri kaldır
                    'timestamp': time.time(),
                    'sector': sector,
                    'camera_id': camera_id,
                    'model_type': 'SH17',
                    'total_people': people_detected,
                    'compliant_people': compliant_people,
                    'violations_count': len(set(violations))
                }
            else:
                # Hiç detection yok
                detection_result = {
                    'detections': [],
                    'people_detected': 0,
                    'compliance_rate': 100,
                    'ppe_violations': [],
                    'timestamp': time.time(),
                    'sector': sector,
                    'camera_id': camera_id,
                    'model_type': 'SH17',
                    'total_people': 0,
                    'compliant_people': 0,
                    'violations_count': 0
                }
            
            # Sonucu cache'e kaydet
            self.detection_results[camera_id] = detection_result
            
            # Database'e kaydet
            self.save_detection_to_database(camera_id, detection_result, sector)
            
            logger.info(f"🎯 PPE Detection completed for {camera_id}: People: {detection_result['people_detected']}, Violations: {detection_result['violations_count']}")
            return detection_result
            
        except Exception as e:
            logger.error(f"❌ PPE Detection hatası {camera_id}: {e}")
            return {
                'detections': [],
                'people_detected': 0,
                'compliance_rate': 0,
                'ppe_violations': [],
                'timestamp': time.time(),
                'sector': sector,
                'camera_id': camera_id,
                'error': str(e),
                'total_people': 0,
                'compliant_people': 0,
                'violations_count': 0
            }
    
    def get_latest_detection_result(self, camera_id: str) -> Optional[Dict]:
        """Kamera için en son detection sonucunu al"""
        return self.detection_results.get(camera_id)
    
    def get_detection_overlay(self, camera_id: str) -> Optional[Dict]:
        """Detection overlay bilgilerini al"""
        return self.detection_results.get(camera_id)
    
    def save_detection_to_database(self, camera_id: str, detection_result: Dict, sector: str):
        """Detection sonucunu database'e kaydet"""
        try:
            from database.database_adapter import get_db_adapter
            db = get_db_adapter()
            
            # Company ID'yi detection_result'tan al veya database'den bul
            company_id = detection_result.get('company_id')
            
            if not company_id:
                # Camera bilgisinden company_id bul (tüm company'lerde ara)
                try:
                    from database.database_adapter import get_db_adapter
                    db = get_db_adapter()
                    # Camera_id ile company_id'yi bul
                    if db.db_type == 'sqlite':
                        query = 'SELECT company_id FROM cameras WHERE camera_id = ? AND status != ? LIMIT 1'
                    else:  # PostgreSQL
                        query = 'SELECT company_id FROM cameras WHERE camera_id = %s AND status != %s LIMIT 1'
                    
                    result = db.execute_query(query, (camera_id, 'deleted'), fetch_all=False)
                    if result and isinstance(result, dict):
                        company_id = result.get('company_id', 'UNKNOWN')
                    elif result:
                        # Eğer dict değilse (fallback)
                        company_id = str(result).strip() if result else 'UNKNOWN'
                    else:
                        company_id = 'UNKNOWN'
                except Exception as db_error:
                    logger.warning(f"⚠️ Company ID bulunamadı: {db_error}")
                    import traceback
                    logger.debug(f"⚠️ Company ID traceback: {traceback.format_exc()}")
                    company_id = 'UNKNOWN'
            
            # Detection data hazırla
            detection_data = {
                'company_id': company_id,
                'camera_id': camera_id,
                'detection_type': 'ppe',
                'confidence': detection_result.get('compliance_rate', 0) / 100.0,
                'people_detected': detection_result.get('total_people', detection_result.get('people_detected', 0)),
                'ppe_compliant': detection_result.get('compliant_people', int(detection_result.get('people_detected', 0) * detection_result.get('compliance_rate', 0) / 100)),
                'violations_count': detection_result.get('violations_count', len(detection_result.get('ppe_violations', []))),
                'total_people': detection_result.get('total_people', detection_result.get('people_detected', 0))
            }
            
            # Database'e kaydet
            db.add_camera_detection_result(detection_data)
            logger.debug(f"💾 Detection saved to database: {camera_id}")
            
        except Exception as e:
            logger.error(f"❌ Save detection to database error: {e}")

    def process_camera_stream(self, camera_id: str, frame: np.ndarray) -> np.ndarray:
        """Kamera stream'ini işle ve PPE detection ekle"""
        try:
            if frame is None or frame.size == 0:
                return frame
            
            # Frame counter'ı güncelle
            if camera_id in self.connection_stats:
                self.connection_stats[camera_id]['frames_captured'] += 1
                self.connection_stats[camera_id]['last_frame_time'] = datetime.now()
            
            # 🎯 PPE DETECTION - Her 15 frame'de bir detection yap
            frame_count = self.connection_stats.get(camera_id, {}).get('frames_captured', 0)
            if frame_count % self.detection_frequency == 0:
                try:
                    # PPE Detection yap
                    detection_result = self.perform_ppe_detection(camera_id, frame)
                    
                    # Frame'e overlay ekle
                    if detection_result and 'detections' in detection_result:
                        frame = self._draw_ppe_overlay(frame, detection_result)
                        
                except Exception as e:
                    logger.warning(f"⚠️ PPE Detection overlay hatası {camera_id}: {e}")
            
            return frame
            
        except Exception as e:
            logger.error(f"❌ Stream processing hatası {camera_id}: {e}")
            return frame

    def _draw_ppe_overlay(self, frame: np.ndarray, detection_data: Dict) -> np.ndarray:
        """PPE Detection overlay - delegates to the shared visual_overlay module."""
        try:
            from detection.utils.visual_overlay import draw_styled_box, get_class_color, draw_hud_bar

            people_count = detection_data.get('people_detected', 0)
            compliant_count = detection_data.get('compliant_people', people_count)
            compliance_rate = detection_data.get('compliance_rate', 0)
            violations = detection_data.get('ppe_violations', [])
            sector = detection_data.get('sector')

            detections = detection_data.get('detections', [])

            if detections and isinstance(detections, list):
                for detection in detections:
                    if not isinstance(detection, dict):
                        continue

                    bbox = detection.get('bbox', [])
                    class_name = detection.get('class_name', 'unknown')
                    confidence = float(detection.get('confidence', 0.0))

                    if len(bbox) != 4:
                        continue

                    x1, y1, x2, y2 = [int(c) for c in bbox]
                    is_missing = bool(detection.get('missing', False)) or class_name.lower().startswith('no')
                    is_person = 'person' in class_name.lower()

                    color = get_class_color(class_name, is_missing=is_missing)
                    label = f"{class_name.upper()} {confidence:.2f}"

                    frame = draw_styled_box(
                        frame, x1, y1, x2, y2,
                        label, color,
                        confidence=confidence,
                        is_person=is_person,
                        is_missing=is_missing,
                    )

            frame = draw_hud_bar(
                frame,
                people=people_count,
                compliant=compliant_count,
                compliance_rate=compliance_rate,
                violations_count=len(violations),
                sector=sector,
            )

        except Exception as e:
            logger.error(f"❌ PPE Overlay çizim hatası: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return frame

# Global camera manager instance
camera_manager = ProfessionalCameraManager()

def get_camera_manager() -> ProfessionalCameraManager:
    """Get global camera manager instance"""
    return camera_manager

# Test function
def test_camera_manager():
    """Test the camera manager"""
    logger.info("🧪 Testing Professional Camera Manager")
    
    manager = get_camera_manager()
    
    # Test IP Webcam detection
    ip_cameras = manager.detect_ip_webcam_cameras("192.168.1.0/24")
    logger.info(f"📱 Found {len(ip_cameras)} IP Webcam cameras")
    
    # Test local camera
    local_camera = manager.create_local_camera_config("Laptop Camera", 0)
    test_result = manager.test_camera_connection(local_camera)
    logger.info(f"💻 Local camera test: {test_result['connection_status']}")
    
    # If IP cameras found, test first one
    if ip_cameras:
        ip_camera = ip_cameras[0]
        webcam_config = manager.create_ip_webcam_config(
            f"Phone Camera {ip_camera['ip']}", 
            ip_camera['ip'], 
            ip_camera['port']
        )
        test_result = manager.test_camera_connection(webcam_config)
        logger.info(f"📱 IP Webcam test: {test_result['connection_status']}")

if __name__ == "__main__":
    test_camera_manager() 