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

from database.database_adapter import get_db_adapter
from integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
from integrations.cameras.camera_integration_manager import DVRConfig

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
            from integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            
            # Generate stream ID
            stream_id = f"{dvr_id}_ch{channel_number:02d}"
            
            # Şirket sektörünü DB'den al (DVR detection için doğru PPE kuralları)
            company_info = api.db.get_company_info(company_id)
            company_sector = company_info.get('sector', 'construction') if company_info else 'construction'

            # Ensure stream is running and wait until active
            success = stream_handler.start_stream(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                ip_address=dvr_system['ip_address'],
                username=dvr_system['username'],
                password=dvr_system['password'],
                rtsp_port=dvr_system['rtsp_port'],
                channel_number=channel_number,
                sector=company_sector,
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
            from integrations.dvr.dvr_stream_handler import get_stream_handler
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
            from integrations.dvr.dvr_stream_handler import get_stream_handler
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
            from integrations.dvr.dvr_stream_handler import get_stream_handler
            stream_handler = get_stream_handler()
            stream_id = f"{dvr_id}_ch{channel_number:02d}"

            status = stream_handler.get_stream_status(stream_id)
            if not status or status.get('status') != 'active':
                seed_rtsp = (
                    f"rtsp://{dvr_system['ip_address']}:{dvr_system['rtsp_port']}"
                    f"/user={dvr_system['username']}&password={dvr_system['password']}"
                    f"&channel={channel_number}&stream=0.sdp"
                )
                # Şirket sektörünü al
                company_info_mjpeg = api.db.get_company_info(company_id)
                company_sector_mjpeg = company_info_mjpeg.get('sector', 'construction') if company_info_mjpeg else 'construction'
                stream_handler.start_stream(
                    stream_id=stream_id,
                    rtsp_url=seed_rtsp,
                    ip_address=dvr_system['ip_address'],
                    username=dvr_system['username'],
                    password=dvr_system['password'],
                    rtsp_port=dvr_system['rtsp_port'],
                    channel_number=channel_number,
                    sector=company_sector_mjpeg,
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
        """Get DVR channels — DB-first, max_channels-aware fallback"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            manager = api.get_camera_manager().dvr_manager

            # DVR bilgilerini al (max_channels için)
            dvr_system = None
            try:
                dvr_system = manager.get_dvr_system(company_id, dvr_id)
            except Exception:
                pass
            max_channels = int((dvr_system or {}).get('max_channels', 16))

            # DB'den kanal listesi
            channels = None
            try:
                channels = manager.db_adapter.get_dvr_channels(company_id, dvr_id)
            except Exception as db_err:
                logger.warning(f"⚠️ DB channels fetch failed: {db_err}")

            # Fallback: max_channels kadar kanal oluştur
            if not channels or not isinstance(channels, list):
                channels = [
                    {
                        'channel_id': f"{dvr_id}_ch{i:02d}",
                        'channel_number': i,
                        'name': f'Kamera {i}',
                        'status': 'available'
                    }
                    for i in range(1, max_channels + 1)
                ]

            return jsonify({'success': True, 'channels': channels, 'max_channels': max_channels})
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

            from integrations.dvr.dvr_stream_handler import get_stream_handler
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

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/test', methods=['GET'])
    def test_dvr_connection(company_id, dvr_id):
        """DVR bağlantı testi — ONVIF önce, sonra RTSP denenir"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'success': False, 'error': 'DVR sistemi bulunamadı'}), 404

            ip  = dvr_system['ip_address']
            user = dvr_system['username']
            pwd  = dvr_system['password']
            port = dvr_system.get('rtsp_port', 554)

            result = {
                'dvr_id': dvr_id,
                'ip_address': ip,
                'onvif_ok': False,
                'rtsp_ok': False,
                'channels_found': 0,
                'method': None,
                'error': None,
            }

            # 1° ONVIF teşt
            try:
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                sh = get_stream_handler()
                uri = sh._try_onvif_stream_uri(ip, user, pwd, 1)
                if uri:
                    result['onvif_ok'] = True
                    result['method'] = 'ONVIF'
                    result['channels_found'] = dvr_system.get('max_channels', 1)
            except Exception as onvif_err:
                logger.debug(f"ℹ️ ONVIF testi başarısız: {onvif_err}")

            # 2° RTSP test (eğer ONVIF başarısız)
            if not result['onvif_ok']:
                import urllib.parse, cv2
                safe_u = urllib.parse.quote(user)
                safe_p = urllib.parse.quote(pwd)
                test_urls = [
                    f"rtsp://{ip}:{port}/user={safe_u}&password={safe_p}&channel=1&stream=0.sdp",
                    f"rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/101",
                    f"rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel=1&subtype=0",
                    f"rtsp://{user}:{pwd}@{ip}:{port}/h264/ch1/main/av_stream",
                ]
                for url in test_urls:
                    try:
                        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000)
                        if cap.isOpened():
                            ret, _ = cap.read()
                            cap.release()
                            if ret:
                                result['rtsp_ok'] = True
                                result['method'] = 'RTSP'
                                result['channels_found'] = dvr_system.get('max_channels', 1)
                                break
                        else:
                            cap.release()
                    except Exception:
                        pass

            connected = result['onvif_ok'] or result['rtsp_ok']
            result['success'] = connected
            if not connected:
                result['error'] = (
                    f"{ip} adresine ulaşılamadı. "
                    "Kameranın IP/port/kullanıcı adı/şifresini ve"
                    " ağ bağlantısını kontrol edin."
                )

            logger.info(f"📶 DVR test: {dvr_id} - {'OK' if connected else 'FAIL'} ({result['method']})")
            return jsonify(result)

        except Exception as e:
            logger.error(f"❌ DVR test error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/channels/health', methods=['GET'])
    def get_dvr_channel_health(company_id, dvr_id):
        """Kanal sağlık durumu — her kanal için hızlı ping"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'success': False, 'error': 'DVR sistemi bulunamadı'}), 404

            from integrations.dvr.dvr_stream_handler import get_stream_handler
            from integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
            sh = get_stream_handler()
            dvr_ppe = get_dvr_ppe_manager()
            active_streams = dvr_ppe.dvr_processor.get_active_detections()

            max_ch = int(dvr_system.get('max_channels', 16))
            # Sadece istenen kanalları dene (client ?channels=1,2,3)
            try:
                ch_param = request.args.get('channels', '')
                req_channels = [int(c) for c in ch_param.split(',') if c.strip().isdigit()]
            except Exception:
                req_channels = []
            channels_to_check = req_channels if req_channels else list(range(1, min(max_ch, 9) + 1))

            health = []
            for ch in channels_to_check:
                stream_id = f"dvr_{dvr_id}_ch{ch:02d}"
                detection_active = stream_id in active_streams
                frame_b64 = sh.capture_single_frame(
                    ip_address=dvr_system['ip_address'],
                    username=dvr_system['username'],
                    password=dvr_system['password'],
                    rtsp_port=dvr_system['rtsp_port'],
                    channel_number=ch
                )
                health.append({
                    'channel_number': ch,
                    'online': frame_b64 is not None,
                    'detection_active': detection_active,
                    'thumbnail': frame_b64
                })

            return jsonify({'success': True, 'channels': health})
        except Exception as e:
            logger.error(f"❌ Channel health error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

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


    # =========================================================================
    # 3.1 MARKA L\u0130STES\u0130 — Frontend dropdown i\u00e7in
    # =========================================================================

    @bp.route('/api/dvr/brands', methods=['GET'])
    def get_dvr_brands():
        """DVR marka listesini ve RTSP \u015fablon \u00f6rne\u011fini d\u00f6nd\u00fcr."""
        try:
            from integrations.dvr.dvr_ppe_integration import RTSP_TEMPLATES
            brands = []
            for key, tmpl in RTSP_TEMPLATES.items():
                label = key.replace('_', ' ').title()
                brands.append({'value': key, 'label': label, 'template_preview': tmpl})
            return jsonify({'success': True, 'brands': brands})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # 3.4 DVR DETECTION RAPORU — PDF / Print-ready HTML Export
    # =========================================================================

    @bp.route('/api/company/<company_id>/dvr/<dvr_id>/report/pdf', methods=['GET'])
    def export_dvr_report_pdf(company_id, dvr_id):
        """
        DVR detection oturumlar\u0131n\u0131n print-ready HTML raporu.
        ?format=html  \u2192 taray\u0131c\u0131da yeni sekme a\u00e7, yazd\u0131r d\u00fcatonu ile PDF yap
        ?format=download  \u2192 attachment olarak indir (default)
        """
        from flask import make_response
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'error': 'Unauthorized'}), 401

            fmt = request.args.get('format', 'download')

            # Veri toplama
            db_adapter = get_db_adapter()
            manager = api.get_camera_manager().dvr_manager
            dvr_system = manager.get_dvr_system(company_id, dvr_id)
            if not dvr_system:
                return jsonify({'error': 'DVR bulunamad\u0131'}), 404

            sessions = db_adapter.get_dvr_detection_sessions(company_id, dvr_id)

            # \u0130hlal verisi
            all_results = []
            for sess in (sessions or []):
                if sess.get('session_id'):
                    results = db_adapter.get_dvr_detection_results(sess['session_id'], 100) or []
                    for r in results:
                        r['session_id'] = sess.get('session_id')
                        r['channel'] = sess.get('channel_number', '?')
                    all_results.extend(results)

            # Toplam violation say\u0131s\u0131
            total_violations = sum(len(r.get('ppe_violations') or []) for r in all_results)
            total_detections = len(all_results)

            from datetime import datetime as _dt
            now_str = _dt.now().strftime('%d.%m.%Y %H:%M')

            # Session sat\u0131rlar\u0131
            session_rows = ''
            for s in (sessions or []):
                session_rows += f"""
                <tr>
                    <td>{s.get('session_id', '-')}</td>
                    <td>{s.get('channel_number', '-')}</td>
                    <td>{s.get('start_time', '-')}</td>
                    <td>{s.get('end_time', '') or 'Devam ediyor'}</td>
                    <td>{s.get('detection_mode', 'construction')}</td>
                </tr>"""

            # Detection sat\u0131rlar\u0131
            result_rows = ''
            for r in all_results[:200]:
                viols = ', '.join(r.get('ppe_violations') or []) or '\u2014'
                ts = r.get('timestamp', '')
                result_rows += f"""
                <tr>
                    <td>{ts}</td>
                    <td>Kanal {r.get('channel', '?')}</td>
                    <td>{r.get('people_detected', 0)}</td>
                    <td class=\"{'violation' if viols != '\u2014' else ''}\">{viols}</td>
                    <td>{r.get('detection_system', 'Klasik')}</td>
                </tr>"""

            html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>DVR Raporu \u2014 {dvr_system.get('name', dvr_id)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Inter, sans-serif; color: #1a1a2e; background: #fff; padding: 30px; }}
  h1 {{ font-size: 22px; color: #0d6efd; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 28px; }}
  .meta-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; text-align: center; }}
  .meta-card .val {{ font-size: 28px; font-weight: 700; color: #0d6efd; }}
  .meta-card .lbl {{ font-size: 12px; color: #888; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 28px; }}
  th {{ background: #0d6efd; color: #fff; padding: 8px 10px; text-align: left; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #f8f9fa; }}
  td.violation {{ color: #dc3545; font-weight: 600; }}
  h2 {{ font-size: 15px; margin-bottom: 10px; border-left: 4px solid #0d6efd; padding-left: 10px; }}
  .print-btn {{ display: inline-block; margin-bottom: 20px; padding: 8px 20px;
               background: #0d6efd; color: #fff; border: none; border-radius: 6px; cursor: pointer;
               font-size: 14px; font-family: inherit; }}
  @media print {{ .print-btn {{ display: none; }} }}
  footer {{ margin-top: 30px; font-size: 11px; color: #aaa; text-align: center; }}
</style>
</head>
<body>
<button class="print-btn" onclick="window.print()">&#128438; Yazdır / PDF Kaydet</button>
<h1>SmartSafe AI \u2014 DVR Detection Raporu</h1>
<p class="subtitle">Rapor tarihi: {now_str} &nbsp;&bull;&nbsp; {dvr_system.get('name','')} ({dvr_system.get('ip_address','')})</p>

<div class="meta-grid">
  <div class="meta-card"><div class="val">{len(sessions or [])}</div><div class="lbl">Detection Oturumu</div></div>
  <div class="meta-card"><div class="val">{total_detections}</div><div class="lbl">Toplam Tespitler</div></div>
  <div class="meta-card"><div class="val" style="color:#dc3545">{total_violations}</div><div class="lbl">Toplam \u0130hlaller</div></div>
</div>

<h2>Detection Oturumlar\u0131</h2>
<table>
  <thead><tr><th>Oturum ID</th><th>Kanal</th><th>Ba\u015flang\u0131\u00e7</th><th>Biti\u015f</th><th>Mod</th></tr></thead>
  <tbody>{session_rows or '<tr><td colspan="5">Oturum bulunamad\u0131</td></tr>'}</tbody>
</table>

<h2>Detection Sonu\u00e7lar\u0131 (son 200)</h2>
<table>
  <thead><tr><th>Zaman</th><th>Kanal</th><th>Ki\u015fi</th><th>\u0130hlaller</th><th>Sistem</th></tr></thead>
  <tbody>{result_rows or '<tr><td colspan="5">Sonu\u00e7 bulunamad\u0131</td></tr>'}</tbody>
</table>

<footer>SmartSafe AI &copy; {_dt.now().year} &nbsp;&bull;&nbsp; Otomatik olu\u015fturuldu: {now_str}</footer>
</body></html>"""

            response = make_response(html)
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            if fmt == 'download':
                fname = f"DVR_Report_{dvr_id}_{_dt.now().strftime('%Y%m%d_%H%M')}.html"
                response.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
            return response

        except Exception as e:
            logger.error(f"\u274c DVR PDF export error: {e}")
            return jsonify({'error': str(e)}), 500

    return bp
