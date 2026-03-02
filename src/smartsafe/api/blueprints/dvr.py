#!/usr/bin/env python3
"""
SmartSafe AI - DVR Blueprint
All DVR-related API routes extracted from smartsafe_saas_api.py
"""

from flask import Blueprint, request, jsonify, session, Response
import logging
import os
import time
import base64

import cv2
import numpy as np

from src.smartsafe.database.database_adapter import get_db_adapter
from src.smartsafe.integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
from src.smartsafe.integrations.cameras.camera_integration_manager import DVRConfig

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('dvr', __name__)

    @bp.route('/api/company/<company_id>/dvr/add', methods=['POST'])
    def add_dvr_system(company_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Demo hesabı kamera limiti kontrolü
        company_info = api.db.get_company_info(company_id)
        if not company_info:
            return jsonify({'error': 'Şirket bulunamadı'}), 404
        
        subscription_type = company_info.get('subscription_type', 'basic')
        max_cameras = company_info.get('max_cameras', 25)
        
        # Mevcut aktif kamera sayısını kontrol et
        active_cameras = api.db.get_active_camera_count(company_id)
        
        if subscription_type == 'demo' and active_cameras >= max_cameras:
            return jsonify({
                'error': f'Demo hesabı kamera limiti ({max_cameras}) aşıldı. Mevcut: {active_cameras}'
            }), 400
        
        data = request.get_json()
        required_fields = ['dvr_id', 'name', 'ip_address']
        if not all(f in data for f in required_fields):
            return jsonify({'error': 'Eksik DVR bilgisi'}), 400
        
        try:
            dvr_config = DVRConfig(
                dvr_id=data['dvr_id'],
                name=data['name'],
                ip_address=data['ip_address'],
                port=int(data.get('port', 80)),
                username=data.get('username', 'admin'),
                password=data.get('password', ''),
                dvr_type=data.get('dvr_type', 'generic'),
                protocol=data.get('protocol', 'http'),
                api_path=data.get('api_path', '/api'),
                rtsp_port=int(data.get('rtsp_port', 554)),
                max_channels=int(data.get('max_channels', 16))
            )
            
            manager = api.get_camera_manager().dvr_manager
            success, msg = manager.add_dvr_system(dvr_config, company_id)
            
            if success:
                # Demo hesabı için kanal limiti uygula
                if subscription_type == 'demo':
                    api._apply_demo_channel_limits(company_id, dvr_config.dvr_id, max_cameras, active_cameras)
            
            return jsonify({'success': success, 'message': msg})
        except Exception as e:
            logger.error(f"❌ DVR ekleme hatası: {e}")
            return jsonify({'error': str(e)}), 500    

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/discover', methods=['POST'])
    def discover_dvr_cameras(company_id, dvr_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Demo hesabı kamera limiti kontrolü
        company_info = api.db.get_company_info(company_id)
        if not company_info:
            return jsonify({'error': 'Şirket bulunamadı'}), 404
        
        subscription_type = company_info.get('subscription_type', 'basic')
        max_cameras = company_info.get('max_cameras', 25)
        
        # Mevcut aktif kamera sayısını kontrol et
        active_cameras = api.db.get_active_camera_count(company_id)
        
        try:
            manager = api.get_camera_manager().dvr_manager
            channels = manager.discover_cameras(dvr_id, company_id)
            
            # Demo hesabı için kanal limiti uygula
            if subscription_type == 'demo':
                channels = api._limit_demo_channels(channels, max_cameras, active_cameras)
            
            # Frontend expects `channels` key
            return jsonify({
                'success': True,
                'channels': channels,
                'count': len(channels),
                'demo_limited': subscription_type == 'demo',
                'max_cameras': max_cameras,
                'active_cameras': active_cameras
            })
        except Exception as e:
            logger.error(f"❌ DVR kanal keşif hatası: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/camera/<channel>/start', methods=['POST'])
    def start_dvr_stream(company_id, dvr_id, channel):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Demo hesabı kamera limiti kontrolü
        company_info = api.db.get_company_info(company_id)
        if not company_info:
            return jsonify({'error': 'Şirket bulunamadı'}), 404
        
        subscription_type = company_info.get('subscription_type', 'basic')
        max_cameras = company_info.get('max_cameras', 25)
        
        # Mevcut aktif kamera sayısını kontrol et
        active_cameras = api.db.get_active_camera_count(company_id)
        
        if subscription_type == 'demo' and active_cameras >= max_cameras:
            return jsonify({
                'error': f'Demo hesabı kamera limiti ({max_cameras}) aşıldı. Mevcut: {active_cameras}'
            }), 400
        
        data = request.get_json() or {}
        try:
            manager = api.get_camera_manager()
            if not manager or not hasattr(manager, 'dvr_manager'):
                return jsonify({'error': 'DVR manager not available'}), 500
            
            logger.info(f"🎥 Starting DVR stream for {dvr_id} channel {channel}")
            stream_url = manager.dvr_manager.start_stream(dvr_id, int(channel), company_id, data.get('quality', 'high'))
            
            logger.info(f"✅ DVR stream started successfully: {stream_url}")
            return jsonify({
                'success': True,
                'stream_url': stream_url,
                'dvr_id': dvr_id,
                'channel': channel,
                'demo_limited': subscription_type == 'demo',
                'max_cameras': max_cameras,
                'active_cameras': active_cameras + 1
            })
        except Exception as e:
            logger.error(f"❌ DVR stream start error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/list', methods=['GET'])
    def list_dvr_systems(company_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_systems = manager.get_dvr_systems(company_id)
            return jsonify({
                'success': True,
                'dvr_systems': dvr_systems
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/info', methods=['GET'])
    def get_dvr_info(company_id, dvr_id):
        """Get DVR system information"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if dvr_system:
                return jsonify({
                    'success': True,
                    'dvr_system': dvr_system
                })
            else:
                return jsonify({'error': 'DVR system not found'}), 404
        except Exception as e:
            logger.error(f"❌ Get DVR info error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/stream/<int:channel_number>', methods=['GET', 'POST'])
    def get_dvr_stream(company_id, dvr_id, channel_number):
        """Get DVR stream as video for browser playback"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Get DVR system info
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            
            if not dvr_system:
                return jsonify({'error': 'DVR system not found'}), 404
            
            # Prefer Media Gateway if enabled
            gateway_urls = api.build_gateway_urls({
                'dvr_id': dvr_id,
                **dvr_system
            }, channel_number)

            if gateway_urls.get('enabled'):
                rtsp_url = gateway_urls['rtsp_url']
                logger.info(f"🔗 Using gateway RTSP for stream: {rtsp_url}")
            else:
                # Fallback: seed with known-good vendor-neutral patterns (XM style first)
                rtsp_url = (
                    f"rtsp://{dvr_system['ip_address']}:{dvr_system['rtsp_port']}"
                    f"/user={dvr_system['username']}&password={dvr_system['password']}"
                    f"&channel={channel_number}&stream=0.sdp"
                )
            
            # Import stream handler
            from src.smartsafe.integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            
            # Generate stream ID
            stream_id = f"{dvr_id}_ch{channel_number:02d}"
            
            # Ensure stream is running and wait until active
            success = stream_handler.start_stream(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                ip_address=dvr_system['ip_address'],
                username=dvr_system['username'],
                password=dvr_system['password'],
                rtsp_port=dvr_system['rtsp_port'],
                channel_number=channel_number
            )
            if not success:
                return jsonify({'success': False, 'error': 'Failed to start stream'}), 404

            # Wait up to 45s for status to become active (some DVRs need longer to lock)
            became_active = False
            deadline = time.time() + 45.0
            while time.time() < deadline:
                status = stream_handler.get_stream_status(stream_id)
                # active -> success
                if status and status.get('status') == 'active':
                    became_active = True
                    break
                # explicit error -> stop early
                if status and status.get('status') == 'error':
                    break
                time.sleep(0.5)
            # Final check: if not active, report failure so UI doesn't assume success
            if not became_active:
                return jsonify({'success': False, 'error': 'Stream failed to become active within timeout'}), 404
            
            # Return stream info
            return jsonify({
                'success': True,
                'stream_id': stream_id,
                'rtsp_url': rtsp_url,
                'channel': channel_number,
                'status': 'active',
                'gateway': gateway_urls if gateway_urls else None
            })
            
        except Exception as e:
            logger.error(f"❌ Get DVR stream error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/stream/<int:channel_number>/stop', methods=['POST'])
    def stop_dvr_stream(company_id, dvr_id, channel_number):
        """Stop DVR stream"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Import stream handler
            from src.smartsafe.integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            
            # Generate stream ID
            stream_id = f"{dvr_id}_ch{channel_number:02d}"
            
            # Stop stream
            success = stream_handler.stop_stream(stream_id)
            
            if success:
                return jsonify({
                    'success': True,
                    'stream_id': stream_id
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to stop stream'
                }), 500
            
        except Exception as e:
            logger.error(f"❌ Stop DVR stream error: {e}")
            return jsonify({'error': str(e)}), 500
    
    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/frame/<int:channel_number>', methods=['GET'])
    def get_dvr_frame(company_id, dvr_id, channel_number):
        """Get latest frame from DVR stream"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Import stream handler
            from src.smartsafe.integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            
            # Generate stream ID
            stream_id = f"{dvr_id}_ch{channel_number:02d}"
            
            # Serve frames only; if stream not active yet, return 404 so client can retry without error spam
            stream_status = stream_handler.get_stream_status(stream_id)
            if not stream_status or stream_status.get('status') != 'active':
                return jsonify({'success': False, 'error': 'Stream not active'}), 404
            
            # Get latest frame with retry logic
            max_frame_retries = 3
            for retry in range(max_frame_retries):
                try:
                    frame_data = stream_handler.get_latest_frame(stream_id)
                
                    if frame_data:
                        # Optional debug overlay for professional verification
                        # Use query param overlay=true to stamp channel, stream_id and timestamp
                        overlay_flag = request.args.get('overlay', '').lower() in ['1', 'true', 'yes']
                        if overlay_flag:
                            try:
                                from datetime import datetime

                                # Decode JPEG
                                jpg_bytes = base64.b64decode(frame_data)
                                np_arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                                if img is not None:
                                    # Compose label
                                    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    label = f"CH {channel_number}  •  {stream_id}  •  {ts}"

                                    # Draw background box and text (bottom-left to avoid DVR's own OSD at top-left)
                                    font = cv2.FONT_HERSHEY_SIMPLEX
                                    scale = 0.9
                                    thickness = 2
                                    (text_w, text_h), _ = cv2.getTextSize(label, font, scale, thickness)
                                    pad = 10
                                    img_h, img_w = img.shape[:2]
                                    x0 = 10
                                    y0 = img_h - text_h - 2 * pad - 10
                                    cv2.rectangle(
                                        img,
                                        (x0, y0),
                                        (x0 + text_w + 2 * pad, y0 + text_h + 2 * pad),
                                        (0, 0, 0),
                                        thickness=-1
                                    )
                                    cv2.putText(img, label, (x0 + pad, y0 + text_h + pad), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

                                    # Re-encode
                                    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                                    ok, enc = cv2.imencode('.jpg', img, encode_params)
                                    if ok:
                                        frame_data = base64.b64encode(enc.tobytes()).decode('utf-8')
                            except Exception as overlay_err:
                                logger.warning(f"⚠️ Overlay failed, returning raw frame: {overlay_err}")

                        return jsonify({
                            'success': True,
                            'frame': frame_data,
                            'stream_id': stream_id
                        })
                    else:
                                if retry < max_frame_retries - 1:
                                    logger.warning(f"⚠️ Frame not available, retrying... (attempt {retry + 1}/{max_frame_retries})")
                                    time.sleep(0.5)
                                else:
                                    logger.error(f"❌ No frame available after {max_frame_retries} attempts: {stream_id}")
                                    return jsonify({
                                        'success': False,
                                        'error': 'No frame available'
                                    }), 404
                except Exception as frame_error:
                    logger.error(f"❌ Frame retrieval error: {frame_error}")
                    if retry < max_frame_retries - 1:
                        time.sleep(0.5)
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'Frame retrieval failed: {str(frame_error)}'
                        }), 500
            
        except Exception as e:
            logger.error(f"❌ Get DVR frame error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/mjpeg/<int:channel_number>')
    def mjpeg_dvr_stream(company_id, dvr_id, channel_number):
        """Serve MJPEG stream built from latest frames of an active DVR stream.
        Browser-friendly without MediaMTX (multipart/x-mixed-replace)."""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            # Ensure stream is running (fire-and-forget)
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'error': 'DVR system not found'}), 404

            # Start stream if needed
            from src.smartsafe.integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            stream_id = f"{dvr_id}_ch{channel_number:02d}"

            status = stream_handler.get_stream_status(stream_id)
            if not status or status.get('status') != 'active':
                seed_rtsp = (
                    f"rtsp://{dvr_system['ip_address']}:{dvr_system['rtsp_port']}"
                    f"/user={dvr_system['username']}&password={dvr_system['password']}"
                    f"&channel={channel_number}&stream=0.sdp"
                )
                stream_handler.start_stream(
                    stream_id=stream_id,
                    rtsp_url=seed_rtsp,
                    ip_address=dvr_system['ip_address'],
                    username=dvr_system['username'],
                    password=dvr_system['password'],
                    rtsp_port=dvr_system['rtsp_port'],
                    channel_number=channel_number
                )

            boundary = 'frame'

            def generate():
                # Higher frame rate for smooth video (25 FPS)
                frame_interval = 0.04  # 40ms between frames
                last_frame_time = 0
                
                while True:
                    try:
                        current_time = time.time()
                        
                        # Only send frame if enough time has passed
                        if current_time - last_frame_time >= frame_interval:
                            frame_b64 = stream_handler.get_latest_frame(stream_id)
                            if frame_b64:
                                # 🎯 DETECTION OVERLAY EKLE
                                try:
                                    # Base64'ten frame'e çevir
                                    jpg_bytes = base64.b64decode(frame_b64)
                                    nparr = np.frombuffer(jpg_bytes, np.uint8)
                                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                    
                                    if frame is not None:
                                        # Son detection sonuçlarını al
                                        detection_result = stream_handler.get_latest_detection_result(stream_id)
                                        if detection_result and 'detections' in detection_result:
                                            # Bounding box'ları çiz
                                            frame = api.draw_saas_overlay(frame, detection_result)
                                        
                                        # Frame'i tekrar encode et
                                        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                        if ret:
                                            jpg_bytes = buffer.tobytes()
                                except Exception as e:
                                    logger.debug(f"⚠️ Detection overlay hatası (devam ediliyor): {e}")
                                    # Hata durumunda orijinal frame'i kullan
                                    jpg_bytes = base64.b64decode(frame_b64)
                                
                                yield (b"--" + boundary.encode() + b"\r\n"
                                       b"Content-Type: image/jpeg\r\n"
                                       b"Content-Length: " + str(len(jpg_bytes)).encode() + b"\r\n\r\n"
                                       + jpg_bytes + b"\r\n")
                                last_frame_time = current_time
                            else:
                                # If no frame, send a small delay
                                time.sleep(0.01)
                        else:
                            # Wait until next frame time
                            time.sleep(0.01)
                            
                    except GeneratorExit:
                        break
                    except Exception as e:
                        logger.warning(f"⚠️ MJPEG frame error: {e}")
                        time.sleep(0.1)

            return Response(generate(), mimetype=f'multipart/x-mixed-replace; boundary={boundary}')

        except Exception as e:
            logger.error(f"❌ MJPEG stream error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/channels', methods=['GET'])
    def get_dvr_channels(company_id, dvr_id):
        """Get DVR channels"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Try database first (but don't fail if DB errors)
            manager = api.get_camera_manager().dvr_manager
            channels = None
            try:
                channels = manager.db_adapter.get_dvr_channels(company_id, dvr_id)
            except Exception as db_err:
                logger.warning(f"⚠️ DB channels fetch failed, using default list: {db_err}")

            # Normalize: if DB returned empty/None, build a default 1..16 list
            if not channels or not isinstance(channels, list):
                channels = [
                    {
                        'channel_id': f"{dvr_id}_ch{i:02d}",
                        'channel_number': i,
                        'name': f'Kamera {i}',
                        'status': 'available'
                    }
                    for i in range(1, 17)
                ]

            # Always return a valid JSON response
            return jsonify({
                'success': True,
                'channels': channels
            })
        except Exception as e:
            logger.error(f"❌ Get DVR channels error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/gateway/config', methods=['GET'])
    def get_gateway_config(company_id, dvr_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            return jsonify({
                'success': True,
                'enabled': api.gateway_enabled,
                'host': api.gateway_host,
                'rtsp_port': api.gateway_rtsp_port,
                'http_port': api.gateway_http_port,
                'path_template': api.gateway_path_template
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/gateway/urls/<int:channel_number>', methods=['GET'])
    def get_gateway_urls(company_id, dvr_id, channel_number):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'success': False, 'error': 'DVR system not found'}), 404

            urls = api.build_gateway_urls({
                'dvr_id': dvr_id,
                **dvr_system
            }, channel_number)

            if not urls:
                return jsonify({'success': False, 'error': 'Gateway not enabled'}), 400

            return jsonify({'success': True, 'urls': urls})
        except Exception as e:
            logger.error(f"❌ Get gateway urls error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/previews', methods=['GET'])
    def get_dvr_previews(company_id, dvr_id):
        """Return single-frame previews for available channels (for grid view)"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'success': False, 'error': 'DVR system not found'}), 404

            from src.smartsafe.integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()

            # For previews, try first N channels quickly for responsiveness
            # Allow client override (?limit=9) but cap to 12
            try:
                client_limit = int(request.args.get('limit', '9'))
            except Exception:
                client_limit = 9
            limit = max(1, min(client_limit, 12))

            detected = list(range(1, limit + 1))

            previews = []
            for ch in detected:
                frame_b64 = stream_handler.capture_single_frame(
                    ip_address=dvr_system['ip_address'],
                    username=dvr_system['username'],
                    password=dvr_system['password'],
                    rtsp_port=dvr_system['rtsp_port'],
                    channel_number=ch
                )
                previews.append({
                    'channel_number': ch,
                    'frame': frame_b64
                })

            return jsonify({'success': True, 'previews': previews})
        except Exception as e:
            logger.error(f"❌ Get DVR previews error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/proxy/<int:channel_number>', methods=['GET'])
    def proxy_dvr_stream(company_id, dvr_id, channel_number):
        """Proxy DVR stream for browser playback"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Get DVR system info
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            
            if not dvr_system:
                return jsonify({'error': 'DVR system not found'}), 404
            
            # Generate RTSP URL (browser proxy info) - use universal XM/Dahua style for correctness
            rtsp_url = (
                f"rtsp://{dvr_system['ip_address']}:{dvr_system['rtsp_port']}"
                f"/user={dvr_system['username']}&password={dvr_system['password']}"
                f"&channel={channel_number}&stream=0.sdp"
            )
            
            # For now, return a simple response with stream info
            # In production, you would implement actual RTSP to HLS conversion
            return jsonify({
                'success': True,
                'message': 'Stream proxy endpoint',
                'rtsp_url': rtsp_url,
                'note': 'RTSP to HLS conversion would be implemented here'
            })
            
        except Exception as e:
            logger.error(f"❌ Proxy DVR stream error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/delete', methods=['DELETE'])
    def delete_dvr_system(company_id, dvr_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            manager = api.get_camera_manager().dvr_manager
            success, msg = manager.remove_dvr_system(dvr_id, company_id)
            return jsonify({'success': success, 'message': msg})
            
        except Exception as e:
            logger.error(f"❌ Delete DVR system error: {e}")
            return jsonify({'error': str(e)}), 500

    # DVR-PPE Detection API endpoints
    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/detection/start', methods=['POST'])
    def start_dvr_detection(company_id, dvr_id):
        """Start DVR PPE detection"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            data = request.get_json()
            channels = data.get('channels', [1])  # Default: channel 1
            detection_mode = data.get('detection_mode', 'construction')
            
            dvr_ppe_manager = get_dvr_ppe_manager()
            result = dvr_ppe_manager.start_dvr_ppe_detection(
                dvr_id, channels, company_id, detection_mode
            )
            
            logger.info(f"🎥 DVR detection started: {result}")
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"❌ Start DVR detection error: {e}")
            return jsonify({'error': str(e)}), 500

    
    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/detection/stop', methods=['POST'])
    def stop_dvr_detection(company_id, dvr_id):
        """Stop DVR PPE detection"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            data = request.get_json()
            channels = data.get('channels', None)  # None = stop all channels
            
            dvr_ppe_manager = get_dvr_ppe_manager()
            result = dvr_ppe_manager.stop_dvr_ppe_detection(dvr_id, channels)
            
            logger.info(f"🛑 DVR detection stopped: {result}")
            return jsonify(result)

        except Exception as e:
            logger.error(f"❌ Stop DVR detection error: {e}")
            return jsonify({'error': str(e)}), 500

    
    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/detection/status', methods=['GET'])
    def get_dvr_detection_status(company_id, dvr_id):
        """Get DVR detection status"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            dvr_ppe_manager = get_dvr_ppe_manager()
            result = dvr_ppe_manager.get_dvr_detection_status(dvr_id)
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection status error: {e}")
            return jsonify({'error': str(e)}), 500
    
    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/detection/results', methods=['GET'])
    def get_dvr_detection_results(company_id, dvr_id):
        """Get DVR detection results"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            limit = request.args.get('limit', 50, type=int)
            
            # Get detection sessions
            db_adapter = get_db_adapter()
            sessions = db_adapter.get_dvr_detection_sessions(company_id, dvr_id)
            
            # Get recent results for each session
            all_results = []
            for sess in sessions:
                if sess.get('session_id'):
                    results = db_adapter.get_dvr_detection_results(sess['session_id'], limit)
                    all_results.extend(results)
            
            return jsonify({
                'sessions': sessions,
                'results': all_results,
                'total_sessions': len(sessions),
                'total_results': len(all_results)
            })
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection results error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/status', methods=['GET'])
    def get_dvr_status(company_id, dvr_id):
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            manager = api.get_camera_manager().dvr_manager
            status = manager.get_dvr_status(dvr_id)
            return jsonify({
                'success': True,
                'dvr_id': dvr_id,
                'status': status
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return bp
