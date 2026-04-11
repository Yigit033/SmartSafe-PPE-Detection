"""
SmartSafe AI - Camera Blueprint
Camera-related routes extracted from smartsafe_saas_api.py
"""

from flask import Blueprint, request, jsonify, session, redirect, render_template, render_template_string, Response, make_response
import logging
import os
import json
import time
import base64
import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from typing import Dict, Any
import urllib.parse

logger = logging.getLogger(__name__)


def create_blueprint(api):
    """Create and return the camera blueprint."""
    bp = Blueprint('camera', __name__)

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/mjpeg')
    def mjpeg_ip_camera_stream(company_id, camera_id):
        """Serve MJPEG stream for IP cameras with PPE detection overlay"""
        # user_data = api.validate_session()
        # if not user_data:
        #     return jsonify({'error': 'Unauthorized'}), 401

        try:
            from flask import Response
            import base64
            import time
            import cv2
            import numpy as np
            import requests
            from requests.auth import HTTPBasicAuth

            # Get camera info from database
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404

            # Get camera manager for PPE detection
            camera_manager = api.get_camera_manager()
            
            # Stream parameters
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            stream_path = camera.get('stream_path', '/shot.jpg')
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            # Build stream URL (NEVER embed credentials in URLs returned to clients)
            stream_url = f"{protocol}://{camera['ip_address']}:{port}{stream_path}"
            auth = HTTPBasicAuth(username, password) if (username and password) else None

            # Alternative URLs for different camera types
            alternative_urls = [
                f"{protocol}://{camera['ip_address']}:{port}/shot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/video",
                f"{protocol}://{camera['ip_address']}:{port}/mjpeg",
                f"{protocol}://{camera['ip_address']}:{port}/stream",
                f"{protocol}://{camera['ip_address']}:{port}/live"
            ]

            from utils.redaction import format_upstream_url_for_log

            boundary = 'frame'
            frame_count = 0
            last_detection_time = 0
            detection_frequency = 5  # Her 5 frame'de bir detection (daha sık)

            def generate():
                nonlocal frame_count, last_detection_time
                import app as _app_mod
                _mjpeg_cam_key = f"{company_id}_{camera_id}"

                while True:
                    try:
                        # Try to get frame from primary URL
                        frame = None
                        working_url = None
                        
                        # Primary URL'yi dene
                        try:
                            response = requests.get(stream_url, auth=auth, timeout=3)
                            if response.status_code == 200:
                                frame_data = np.frombuffer(response.content, np.uint8)
                                frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                                working_url = stream_url
                        except Exception as e:
                            logger.debug(
                                "Primary URL failed (%s): %s",
                                format_upstream_url_for_log(
                                    str(stream_url),
                                    company_id=company_id,
                                    camera_id=camera_id,
                                    label="mjpeg_primary",
                                ),
                                e,
                            )
                        
                        # Alternatif URL'leri dene
                        if frame is None:
                            for alt_url in alternative_urls:
                                try:
                                    response = requests.get(alt_url, auth=auth, timeout=3)
                                    if response.status_code == 200:
                                        frame_data = np.frombuffer(response.content, np.uint8)
                                        frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                                        if frame is not None:
                                            working_url = alt_url
                                            break
                                except Exception as e:
                                    logger.debug(
                                        "Alternative URL failed %s: %s",
                                        format_upstream_url_for_log(
                                            str(alt_url),
                                            company_id=company_id,
                                            camera_id=camera_id,
                                            label="mjpeg_alt",
                                        ),
                                        e,
                                    )
                                    continue
                        
                        if frame is not None and frame.size > 0:
                            frame_count += 1
                            
                            # PPE yalnızca start-detection ile açılmış kameralarda (video-feed ile aynı mantık)
                            current_time = time.time()
                            _det_on = _app_mod.active_detectors.get(_mjpeg_cam_key, False)
                            if (
                                _det_on
                                and frame_count % 5 == 0
                                and (current_time - last_detection_time) > 0.2
                            ):
                                try:
                                    # PPE Detection yap
                                    # Resolve sector from company configuration
                                    try:
                                        if api.db is not None:
                                            company_data = api.db.get_company_info(company_id)
                                            sector = company_data.get('sector') if company_data and isinstance(company_data, dict) else None
                                        else:
                                            sector = None
                                    except Exception as _sec_err:
                                        sector = None
                                    # Optional hybrid path via SectorDetectorFactory
                                    use_hybrid = os.getenv('USE_HYBRID', '').lower() == 'true'
                                    if use_hybrid and sector:
                                        try:
                                            from sector.smartsafe_sector_detector_factory import SectorDetectorFactory
                                            detector = SectorDetectorFactory.get_detector(sector, company_id)
                                            detection_result = detector.detect_ppe(frame, camera_id)
                                        except Exception as _hybrid_err:
                                            logger.warning(f"⚠️ Hybrid detection failed, falling back: {str(_hybrid_err)}")
                                            detection_result = camera_manager.perform_ppe_detection(
                                                camera_id, frame, sector=sector, company_id=company_id
                                            )
                                    else:
                                        detection_result = camera_manager.perform_ppe_detection(
                                            camera_id, frame, sector=sector, company_id=company_id
                                        )
                                    last_detection_time = current_time
                                    
                                    # Detection sonuçlarını frame'e çiz
                                    if detection_result and 'detections' in detection_result:
                                        frame = api.draw_saas_overlay(frame, detection_result)
                                        logger.info(f"🎯 PPE Detection completed for {camera_id}: {len(detection_result.get('detections', []))} detections")
                                    else:
                                        logger.debug(f"⚠️ No detection results for {camera_id}")
                                        
                                except Exception as e:
                                    logger.error(f"❌ PPE Detection hatası {camera_id}: {e}")
                                    # Hata durumunda basit bir overlay ekle
                                    try:
                                        cv2.putText(frame, f'PPE Detection Error: {str(e)[:30]}', (10, 100), 
                                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                                    except:
                                        pass
                            
                            # Frame'i JPEG olarak encode et - kalite ve boyut optimizasyonu
                            # Frame boyutunu kontrol et ve optimize et
                            frame_height, frame_width = frame.shape[:2]

                            # Büyük frame'leri yeniden boyutlandır (performans için)
                            if frame_width > 1280 or frame_height > 720:
                                scale_factor = min(1280 / frame_width, 720 / frame_height)
                                new_width = int(frame_width * scale_factor)
                                new_height = int(frame_height * scale_factor)
                                frame = cv2.resize(frame, (new_width, new_height))
                                logger.debug(f"📐 Frame resized: {frame_width}x{frame_height} -> {new_width}x{new_height}")

                            # JPEG kalitesini frame boyutuna göre ayarla
                            jpeg_quality = 85 if frame_width <= 640 else 75
                            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                            
                            if ret:
                                jpg_bytes = buffer.tobytes()
                                
                                # MJPEG frame'i gönder
                                yield (b"--" + boundary.encode() + b"\r\n"
                                       b"Content-Type: image/jpeg\r\n"
                                       b"Content-Length: " + str(len(jpg_bytes)).encode() + b"\r\n\r\n"
                                       + jpg_bytes + b"\r\n")
                                
                                # Frame rate kontrolü (~25 FPS)
                                time.sleep(0.04)
                            else:
                                time.sleep(0.1)
                        else:
                            # Frame alınamadı, placeholder gönder
                            # Frame boyutunu al (varsa) veya varsayılan kullan
                            try:
                                if 'frame' in locals() and frame is not None:
                                    frame_height, frame_width = frame.shape[:2]
                                else:
                                    frame_height, frame_width = 480, 640
                            except:
                                frame_height, frame_width = 480, 640

                            placeholder_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
                            placeholder_frame[:] = (50, 50, 50)  # Koyu gri

                            # "No Signal" yazısı ekle - frame boyutuna göre ayarla
                            text_x = max(50, frame_width // 2 - 100)
                            text_y = frame_height // 2
                            cv2.putText(placeholder_frame, "No Signal", (text_x, text_y), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                            
                            ret, buffer = cv2.imencode('.jpg', placeholder_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                            if ret:
                                jpg_bytes = buffer.tobytes()
                                yield (b"--" + boundary.encode() + b"\r\n"
                                       b"Content-Type: image/jpeg\r\n"
                                       b"Content-Length: " + str(len(jpg_bytes)).encode() + b"\r\n\r\n"
                                       + jpg_bytes + b"\r\n")
                            
                            time.sleep(1.0)  # No signal durumunda daha yavaş
                            
                    except GeneratorExit:
                        break
                    except Exception as e:
                        logger.warning(f"⚠️ IP Camera MJPEG frame error: {e}")
                        time.sleep(0.1)

            return Response(generate(), mimetype=f'multipart/x-mixed-replace; boundary={boundary}')

        except Exception as e:
            logger.error(f"❌ IP Camera MJPEG stream error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/discover', methods=['POST'])
    def discover_cameras(company_id):
        """Unified kamera keşif ve senkronizasyon sistemi"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json() or {}
            network_range = data.get('network_range')
            auto_sync = data.get('auto_sync', True)  # Otomatik DB sync
            
            # Eğer range verilmediyse, hem yerel ağı hem de kullanıcının IP'sini içeren bloğu tara
            if not network_range:
                user_ip = request.remote_addr
                if user_ip and user_ip != '127.0.0.1':
                    parts = user_ip.split('.')
                    network_range = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
                    logger.info(f"📍 Detected user IP {user_ip}, setting range to {network_range}")
                else:
                    network_range = '192.168.1.0/24' # Fallback
            
            logger.info(f"🔍 Starting unified camera discovery for company {company_id}")
            
            # Enterprise Camera Manager ile discovery
            if hasattr(api, 'camera_manager') and api.camera_manager and api.enterprise_enabled:
                try:
                    # Full camera synchronization
                    sync_result = api.camera_manager.full_camera_sync(company_id, network_range)
                    
                    if sync_result['success']:
                        return jsonify({
                            'success': True,
                            'message': 'Kamera keşif ve senkronizasyon tamamlandı',
                            'discovery_result': sync_result['discovery_result'],
                            'config_sync': sync_result['config_sync_result'],
                            'total_cameras_in_db': sync_result['final_camera_count'],
                            'auto_sync_enabled': auto_sync,
                            'mode': 'enterprise'
                        })
                    else:
                        logger.warning(f"⚠️ Enterprise sync failed: {sync_result.get('error')}")
                        # Continue with fallback
                
                except Exception as e:
                    logger.error(f"❌ Enterprise camera discovery failed: {e}")
                    # Continue with fallback
            
            # Fallback: Standard discovery sistemi
            logger.info("📱 Using standard discovery system")
            
            discovered_cameras = []
            scan_time = '2.0 saniye'
            
            try:
                from integrations.cameras.camera_discovery import IPCameraDiscovery
                discovery = IPCameraDiscovery()
                result = discovery.scan_network(network_range, timeout=2)
                discovered_cameras = result['cameras']
                scan_time = result['scan_time']
                
                # Auto sync to database if enabled
                if auto_sync and discovered_cameras:
                    try:
                        from database.database_adapter import get_camera_discovery_manager
                        discovery_manager = get_camera_discovery_manager()
                        sync_result = discovery_manager.sync_discovered_cameras_to_db(company_id, discovered_cameras)
                        
                        logger.info(f"✅ Auto-sync: {sync_result['added']} added, {sync_result['updated']} updated")
                        
                        return jsonify({
                            'success': True,
                            'cameras': discovered_cameras,
                            'network_range': network_range,
                            'scan_time': scan_time,
                            'auto_sync_enabled': auto_sync,
                            'sync_result': sync_result,
                            'mode': 'standard_with_sync'
                        })
                    except Exception as sync_error:
                        logger.error(f"❌ Auto-sync failed: {sync_error}")
                        # Continue without sync
            
            except ImportError:
                # Mock veriler yerine hata dön
                logger.error("❌ Camera discovery modules not available")
                return jsonify({
                    'success': False, 
                    'error': 'Kamera keşif modülleri yüklü değil. Lütfen sistem yöneticisi ile iletişime geçin.',
                    'mode': 'error'
                }), 500
            
            return jsonify({
                'success': True,
                'cameras': discovered_cameras,
                'network_range': network_range,
                'scan_time': scan_time,
                'auto_sync_enabled': auto_sync,
                'mode': 'fallback'
            })
            
        except Exception as e:
            logger.error(f"❌ Camera discovery error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/test', methods=['POST'])
    def test_camera(company_id):
        """Gerçek kamera bağlantı testi - Enhanced real camera support"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'Kamera bilgileri gerekli'}), 400
            
            logger.info(f"🔍 Testing real camera connection for company {company_id}")
            
            # Try enhanced real camera manager first
            test_result = None
            try:
                from integrations.cameras.camera_integration_manager import RealCameraManager, RealCameraConfig
                
                real_camera_manager = RealCameraManager()
                
                # Create camera config from form data
                camera_config = RealCameraConfig(
                    camera_id=f"TEST_{data.get('ip_address', 'unknown')}",
                    name=data.get('name', 'Test Camera'),
                    ip_address=data.get('ip_address', ''),
                    port=int(data.get('port', 8080)),
                    username=data.get('username', ''),
                    password=data.get('password', ''),
                    protocol=data.get('protocol', 'http'),
                    stream_path=data.get('stream_path', '/video'),
                    auth_type=data.get('auth_type', 'basic')
                )
                
                # Gerçek kamera testi yap
                test_result = real_camera_manager.test_real_camera_connection(camera_config)
                
            except (ImportError, AttributeError) as e:
                logger.warning(f"⚠️ RealCameraManager not available: {e}, using fallback")
                test_result = None
            except Exception as e:
                logger.error(f"❌ RealCameraManager error: {e}, using fallback")
                test_result = None
            
            # Fallback to basic connection test if RealCameraManager fails
            if test_result is None:
                test_result = api._basic_camera_test(data)
            
            # API response formatına dönüştür
            if test_result and test_result.get('success'):
                api_response = {
                        'success': True,
                        'connection_time': test_result.get('connection_time', 0),
                        'stream_quality': test_result.get('stream_quality', 'good'),
                        'supported_features': test_result.get('supported_features', []),
                        'camera_info': test_result.get('camera_info', {}),
                    'test_results': {
                            'connection_status': 'success',
                            'response_time': f"{test_result.get('connection_time', 0):.0f}ms",
                            'resolution': test_result.get('camera_info', {}).get('resolution', 'Bilinmiyor'),
                            'fps': test_result.get('camera_info', {}).get('fps', 25),
                            'quality': test_result.get('stream_quality', 'good'),
                            'supported_features': test_result.get('supported_features', []),
                            'test_duration': f"{test_result.get('connection_time', 0)/1000:.1f} saniye"
                        },
                        'message': f'Kamera bağlantısı başarılı! ({test_result.get("connection_time", 0):.0f}ms)'
                    }
            else:
                api_response = {
                    'success': False,
                    'error': test_result.get('error_message', 'Bilinmeyen hata') if test_result else 'Kamera testi başarısız',
                    'test_results': {
                        'connection_status': 'failed',
                        'error_message': test_result.get('error_message', 'Bilinmeyen hata') if test_result else 'Kamera testi başarısız',
                        'test_duration': f"{test_result.get('connection_time', 0)/1000:.1f} saniye" if test_result else '0.0 saniye'
                    },
                    'message': f'Kamera bağlantısı başarısız: {test_result.get("error_message", "Bilinmeyen hata") if test_result else "Kamera testi başarısız"}'
                }
            
            camera_name = data.get('name', data.get('ip_address', 'Unknown'))
            logger.info(f"✅ Camera test completed for {camera_name}: {api_response['success']}")
            return jsonify(api_response)
            
        except Exception as e:
            logger.error(f"❌ Real camera test error: {e}")
            return jsonify({
                'success': False, 
                'error': str(e),
                'message': f'Kamera testi sırasında hata: {str(e)}'
            }), 500

    @bp.route('/api/company/<company_id>/cameras/smart-test', methods=['POST'])
    def smart_test_camera(company_id):
        """Akıllı kamera tespiti ve test"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            ip_address = data.get('ip_address')
            camera_name = data.get('camera_name', 'Akıllı Tespit Kamera')
            
            if not ip_address:
                return jsonify({'success': False, 'error': 'IP adresi gerekli'}), 400
            
            from utils.redaction import format_upstream_url_for_log
            logger.info(
                "🧠 Smart camera test for %s",
                format_upstream_url_for_log(
                    f"http://{ip_address}/", company_id=company_id, label="smart-test"
                ),
            )
            
            try:
                from integrations.cameras.camera_integration_manager import SmartCameraDetector
                
                detector = SmartCameraDetector()
                detection_result = detector.smart_detect_camera(ip_address)
                
                if detection_result['success']:
                    # Kamera başarıyla tespit edildi, test et
                    port = detection_result.get('port', 8080)
                    protocol = detection_result.get('protocol', 'http')
                    path = detection_result.get('path', '/video')
                    
                    # Basic kamera testi
                    from integrations.cameras.camera_integration_manager import CameraSource
                    import time
                    
                    # Connection URL oluştur
                    connection_url = f"{protocol}://{ip_address}:{port}{path}"
                    
                    # CameraSource object oluştur
                    camera_config = CameraSource(
                        camera_id=f"SMART_TEST_{int(time.time())}",
                        name="Smart Detected Camera",
                        source_type='ip_webcam',
                        connection_url=connection_url,
                        username='',
                        password='',
                        timeout=10
                    )
                    
                    test_result = api.get_camera_manager().test_camera_connection(camera_config)
                    
                    return jsonify({
                        'success': True,
                        'detection_info': detection_result,
                        'connection_test': test_result,
                        'message': f"Kamera tespit edildi: {detection_result.get('detected_model', 'unknown')} (Güven: {detection_result.get('detection_confidence', 0):.1%})"
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': detection_result['error'],
                        'detection_info': detection_result
                    })
                    
            except Exception as e:
                logger.error(f"❌ Smart test error: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Akıllı test hatası: {str(e)}'
                }), 500
                
        except Exception as e:
            logger.error(f"❌ Smart test API error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @bp.route('/api/company/<company_id>/cameras/quick-test', methods=['POST'])
    def quick_test_camera(company_id):
        """Hızlı kamera testi - 2 saniye timeout"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            ip_address = data.get('ip_address')
            port = data.get('port', 8080)
            protocol = data.get('protocol', 'http')
            stream_path = data.get('stream_path', '/video')
            username = data.get('username', '')
            password = data.get('password', '')
            
            if not ip_address:
                return jsonify({'success': False, 'error': 'IP adresi gerekli'}), 400
            
            from utils.redaction import format_upstream_url_for_log
            logger.info(
                "⚡ Quick camera test for %s",
                format_upstream_url_for_log(
                    f"{protocol}://{ip_address}:{port}{stream_path}",
                    company_id=company_id,
                    label="quick-test",
                ),
            )
            
            try:
                import requests
                import time
                
                start_time = time.time()
                
                # Hızlı HTTP testi
                url = f"{protocol}://{ip_address}:{port}{stream_path}"
                headers = {}
                
                if username and password:
                    import base64
                    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                    headers['Authorization'] = f"Basic {credentials}"
                
                response = requests.get(url, headers=headers, timeout=2)
                test_duration = (time.time() - start_time) * 1000
                
                if response.status_code in [200, 401, 403]:
                    return jsonify({
                        'success': True,
                        'message': 'Hızlı bağlantı testi başarılı',
                        'test_results': {
                            'response_time': f"{test_duration:.1f}ms",
                            'status_code': response.status_code,
                            'test_duration': f"{test_duration / 1000:.1f}"
                        }
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'test_results': {
                            'test_duration': f"{test_duration / 1000:.1f}"
                        }
                    })
                    
            except requests.exceptions.Timeout:
                return jsonify({
                    'success': False,
                    'error': 'Bağlantı zaman aşımı (2 saniye)',
                    'test_results': {
                        'test_duration': '2.0'
                    }
                })
            except requests.exceptions.ConnectionError:
                return jsonify({
                    'success': False,
                    'error': 'Bağlantı hatası - Port kapalı veya erişilemiyor',
                    'test_results': {
                        'test_duration': '0.1'
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Hızlı test hatası: {str(e)}',
                    'test_results': {
                        'test_duration': '0.1'
                    }
                })
                
        except Exception as e:
            logger.error(f"❌ Quick test API error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @bp.route('/api/company/<company_id>/cameras/manual-test', methods=['POST'])
    def manual_test_camera(company_id):
        """Gerçek kamera testi - Bağlantı, Stream ve PPE Detection"""
        try:
            # Session kontrolünü daha esnek yap
            user_data = api.validate_session()
            if not user_data:
                logger.warning("⚠️ Session doğrulama başarısız, test devam ediyor...")
                # Test için geçici user_data oluştur
                user_data = {'company_id': company_id, 'user_id': 'test_user'}
            elif user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            ip_address = data.get('ip_address')
            port = data.get('port', 8080)
            protocol = data.get('protocol', 'http')
            stream_path = data.get('stream_path', '/video')
            username = data.get('username', '')
            password = data.get('password', '')
            detection_mode = data.get('detection_mode', 'construction')
            
            if not ip_address:
                return jsonify({'success': False, 'error': 'IP adresi gerekli'}), 400
            
            from utils.redaction import format_upstream_url_for_log
            logger.info(
                "🎯 Gerçek kamera testi başlatılıyor: %s",
                format_upstream_url_for_log(
                    f"{protocol}://{ip_address}:{port}{stream_path}",
                    company_id=company_id,
                    label="manual-test",
                ),
            )
            
            test_results = {
                'connection_test': {'status': 'failed', 'error': None},
                'stream_test': {'status': 'failed', 'error': None},
                'ppe_test': {'status': 'failed', 'error': None},
                'overall_success': False
            }
            
            # 1. HTTP Bağlantı Testi
            try:
                import requests
                import time
                
                start_time = time.time()
                url = f"{protocol}://{ip_address}:{port}{stream_path}"
                headers = {}
                
                if username and password:
                    import base64
                    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                    headers['Authorization'] = f"Basic {credentials}"
                
                logger.info(
                    "🔍 Test URL: %s",
                    format_upstream_url_for_log(url, company_id=company_id, label="manual-test-url"),
                )
                response = requests.get(url, headers=headers, timeout=10)  # Timeout artırıldı
                test_duration = (time.time() - start_time) * 1000
                
                if response.status_code in [200, 401, 403]:
                    test_results['connection_test'] = {
                        'status': 'success',
                        'response_time_ms': test_duration,
                        'status_code': response.status_code
                    }
                    logger.info(f"✅ HTTP bağlantı başarılı: {test_duration:.1f}ms")
                else:
                    test_results['connection_test'] = {
                        'status': 'failed',
                        'error': f'HTTP {response.status_code}',
                        'response_time_ms': test_duration
                    }
                    logger.warning(f"❌ HTTP bağlantı hatası: {response.status_code}")
                    
            except Exception as e:
                test_results['connection_test'] = {
                    'status': 'failed',
                    'error': f'Bağlantı hatası: {str(e)}'
                }
                logger.error(f"❌ Bağlantı testi hatası: {e}")
            
            # 2. Video Stream Testi
            if test_results['connection_test']['status'] == 'success':
                try:
                    import cv2
                    
                    cap = cv2.VideoCapture(url)
                    
                    if cap.isOpened():
                        # Frame capture testi
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            test_results['stream_test'] = {
                                'status': 'success',
                                'frame_info': {
                                    'width': frame.shape[1],
                                    'height': frame.shape[0],
                                    'channels': frame.shape[2] if len(frame.shape) > 2 else 1
                                }
                            }
                            logger.info(f"✅ Video stream başarılı: {frame.shape[1]}x{frame.shape[0]}")
                            
                            # 3. PPE Detection Testi
                            try:
                                # Frame'i base64'e çevir
                                _, buffer = cv2.imencode('.jpg', frame)
                                image_base64 = base64.b64encode(buffer).decode('utf-8')
                                
                                # SH17 destekli sektörler
                                sh17_sectors = [
                                    'construction', 'manufacturing', 'chemical', 'food_beverage',
                                    'warehouse_logistics', 'energy', 'petrochemical', 'marine_shipyard', 'aviation'
                                ]
                                
                                use_sh17 = detection_mode in sh17_sectors
                                
                                if use_sh17:
                                    logger.info(f"🎯 SH17 Detection kullanılıyor: {detection_mode}")
                                    
                                    # SH17 API endpoint
                                    sh17_url = f"http://localhost:10000/api/company/{company_id}/sh17/detect"
                                    sh17_payload = {
                                        "image": image_base64,
                                        "sector": detection_mode,
                                        "confidence": 0.5
                                    }
                                    
                                    try:
                                        sh17_response = requests.post(sh17_url, json=sh17_payload, timeout=10)
                                        
                                        if sh17_response.status_code == 200:
                                            sh17_result = sh17_response.json()
                                            test_results['ppe_test'] = {
                                                'status': 'success',
                                                'system_used': 'SH17',
                                                'total_detections': sh17_result.get('total_detections', 0),
                                                'people_detected': len(sh17_result.get('detections', [])),
                                                'ppe_compliant': sum(1 for d in sh17_result.get('detections', []) 
                                                                    if d.get('compliance', False)),
                                                'ppe_violations': [d for d in sh17_result.get('detections', []) 
                                                                  if not d.get('compliance', False)],
                                                'detection_mode': detection_mode
                                            }
                                            logger.info(f"✅ SH17 detection başarılı: {sh17_result.get('total_detections', 0)} detection")
                                        else:
                                            logger.warning(f"❌ SH17 detection hatası: {sh17_response.status_code}")
                                            _classic = getattr(api, '_test_classic_detection', None)
                                            if callable(_classic):
                                                test_results['ppe_test'] = _classic(
                                                    image_base64, company_id, detection_mode
                                                )
                                            else:
                                                test_results['ppe_test'] = {
                                                    'status': 'failed',
                                                    'error': 'SH17 servisi yanıt vermedi, klasik detection kullanılamadı'
                                                }
                                            
                                    except Exception as sh17_error:
                                        logger.error(f"❌ SH17 test hatası: {sh17_error}")
                                        _classic = getattr(api, '_test_classic_detection', None)
                                        if callable(_classic):
                                            test_results['ppe_test'] = _classic(
                                                image_base64, company_id, detection_mode
                                            )
                                        else:
                                            test_results['ppe_test'] = {
                                                'status': 'failed',
                                                'error': f'SH17 bağlantı hatası: {str(sh17_error)}'
                                            }
                                else:
                                    logger.info(f"🔄 Klasik Detection kullanılıyor: {detection_mode}")
                                    _classic = getattr(api, '_test_classic_detection', None)
                                    if callable(_classic):
                                        test_results['ppe_test'] = _classic(
                                            image_base64, company_id, detection_mode
                                        )
                                    else:
                                        test_results['ppe_test'] = {
                                            'status': 'failed',
                                            'error': 'Klasik PPE testi bu kurulumda kullanılamıyor'
                                        }
                                    
                            except Exception as ppe_error:
                                test_results['ppe_test'] = {
                                    'status': 'failed',
                                    'error': f'PPE test hatası: {str(ppe_error)}'
                                }
                                logger.error(f"❌ PPE test hatası: {ppe_error}")
                        else:
                            test_results['stream_test'] = {
                                'status': 'failed',
                                'error': 'Frame capture başarısız'
                            }
                            logger.warning("❌ Frame capture başarısız")
                        
                        cap.release()
                    else:
                        test_results['stream_test'] = {
                            'status': 'failed',
                            'error': 'Video stream erişilemiyor'
                        }
                        logger.warning("❌ Video stream erişilemiyor")
                        
                except Exception as stream_error:
                    test_results['stream_test'] = {
                        'status': 'failed',
                        'error': f'Stream test hatası: {str(stream_error)}'
                    }
                    logger.error(f"❌ Stream test hatası: {stream_error}")
            
            # Genel başarı durumu
            connection_success = test_results['connection_test']['status'] == 'success'
            stream_success = test_results['stream_test']['status'] == 'success'
            ppe_success = test_results['ppe_test']['status'] == 'success'
            
            # En az bağlantı başarılı olmalı
            test_results['overall_success'] = connection_success
            
            # Detaylı sonuç mesajı
            if test_results['overall_success']:
                if stream_success and ppe_success:
                    success_message = "✅ Kapsamlı test başarılı!"
                elif stream_success:
                    success_message = "✅ Bağlantı ve stream başarılı!"
                else:
                    success_message = "✅ Bağlantı başarılı!"
            else:
                success_message = "❌ Test başarısız"
            
            logger.info(f"📊 Test sonuçları: Bağlantı={connection_success}, Stream={stream_success}, PPE={ppe_success}")
            return jsonify({
                'success': test_results['overall_success'],
                'message': success_message,
                'test_results': test_results,
                'camera_info': {
                    'ip_address': ip_address,
                    'port': port,
                    'protocol': protocol,
                    'stream_path': stream_path
                }
            })
                
        except Exception as e:
            logger.error(f"❌ Manuel test API hatası: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/test', methods=['POST'])
    def test_specific_camera(company_id, camera_id):
        """Belirli bir kamerayı test et"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            # Kamerayı veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)
            from utils.redaction import sanitize_camera_record_for_log
            logger.info(
                "🔍 Camera test context for %s: %s",
                camera_id,
                sanitize_camera_record_for_log(camera) if camera else {},
            )
            if not camera:
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            # Basit HTTP testi yap
            import requests
            import time
            
            start_time = time.time()
            
            # Test URL'sini oluştur
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            stream_path = camera.get('stream_path', '/video')
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            url = f"{protocol}://{camera['ip_address']}:{port}{stream_path}"
            headers = {}
            
            if username and password:
                import base64
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f"Basic {credentials}"
            
            try:
                response = requests.get(url, headers=headers, timeout=5)
                test_duration = (time.time() - start_time) * 1000
                
                if response.status_code in [200, 401, 403]:
                    return jsonify({
                        'success': True,
                        'message': 'Kamera bağlantısı başarılı',
                        'test_results': {
                            'response_time': f"{test_duration:.1f}ms",
                            'status_code': response.status_code,
                            'test_duration': f"{test_duration / 1000:.1f}s"
                        }
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'test_results': {
                            'test_duration': f"{test_duration / 1000:.1f}s"
                        }
                    })
                    
            except requests.exceptions.RequestException as e:
                test_duration = (time.time() - start_time) * 1000
                return jsonify({
                    'success': False,
                    'error': f'Bağlantı hatası: {str(e)}',
                    'test_results': {
                        'test_duration': f"{test_duration / 1000:.1f}s"
                    }
                })
            
        except Exception as e:
            logger.error(f"Camera test error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/toggle', methods=['POST'])
    def toggle_camera_status(company_id, camera_id):
        """Kamera durumunu aktif/pasif yap"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            logger.info(f"🔄 Toggle request for camera: {camera_id}, company: {company_id}")
            
            # Kamerayı veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                logger.error(f"❌ Camera not found: {camera_id} for company: {company_id}")
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            logger.info(f"📹 Current camera status: {camera.get('status', 'unknown')}")
            
            # Yeni durumu belirle
            current_status = camera.get('status', 'active')
            new_status = 'inactive' if current_status == 'active' else 'active'
            
            logger.info(f"🔄 Toggling camera status from '{current_status}' to '{new_status}'")
            
            # Kamerayı güncelle
            success = api.db.update_camera_status(camera_id, company_id, new_status)
            
            if success:
                logger.info(f"✅ Camera status updated successfully to: {new_status}")
                return jsonify({
                    'success': True,
                    'message': f'Kamera durumu {new_status} olarak güncellendi',
                    'new_status': new_status
                })
            else:
                logger.error(f"❌ Failed to update camera status to: {new_status}")
                return jsonify({'success': False, 'error': 'Kamera durumu güncellenemedi'}), 500
            
        except Exception as e:
            logger.error(f"Camera toggle error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({'success': False, 'error': str(e)}), 500


    @bp.route('/api/company/<company_id>/cameras/<camera_id>/proxy-stream')
    def proxy_camera_stream(company_id, camera_id):
        """Kamera stream'ini proxy ile getir - CORS sorunlarını çözer"""
        from utils.redaction import format_upstream_url_for_log
        logger.debug(f"🚀 [DEBUG] Proxy stream request for company={company_id}, camera={camera_id}")
        try:
            def _structured_error(
                http_status: int,
                code: str,
                message: str,
                *,
                details: dict | None = None,
                retry_after: int | None = None,
            ):
                payload = {
                    'success': False,
                    'error': {
                        'code': code,
                        'message': message,
                        'details': dict(details) if details else {},
                    },
                }
                resp = make_response(jsonify(payload), http_status)
                if retry_after is not None and http_status in (502, 503, 429):
                    resp.headers['Retry-After'] = str(retry_after)
                return resp

            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in proxy_camera_stream")
                return _structured_error(
                    503,
                    'DB_UNAVAILABLE',
                    'Veritabanı başlatılamadı',
                    details={'retryable': False},
                )
            
            if api.db is None:
                logger.error("❌ Database connection is None in proxy_camera_stream")
                return _structured_error(
                    503,
                    'DB_UNAVAILABLE',
                    'Veritabanı bağlantısı yok',
                    details={'retryable': False},
                )
            
            # Session kontrolü - SaaS için yerelde bypass ediyoruz
            try:
                # user_data = api.validate_session()
                # logger.info(f"🔍 Session check for company {company_id}: {user_data}")
                # if not user_data or user_data.get('company_id') != company_id:
                #     logger.warning(f"❌ Session validation failed for company {company_id}")
                #     return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
                pass
            except Exception as e:
                # logger.error(f"❌ Session validation error: {e}")
                # return jsonify({'success': False, 'error': 'Oturum kontrolü hatası'}), 401
                pass
            
            # Kamerayı veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)

            # Single source of truth:
            # If this camera is actually a DVR channel, always re-resolve it from dvr_channels
            # so runtime proxy uses the latest cached "works formula" (rtsp_path) found by discovery.
            if camera and (
                camera.get('is_dvr') is True
                or str(camera.get('camera_type', '')).lower() == 'dvr_channel'
            ):
                if hasattr(api.db, 'get_dvr_channel_by_id'):
                    dvr_camera = api.db.get_dvr_channel_by_id(camera_id, company_id)
                    if dvr_camera:
                        camera = dvr_camera
                        logger.info(f"✅ Resolved DVR channel as source of truth for proxy: {camera_id}")
            
            # 🚀 DVR Kanalı kontrolü (Eğer cameras tablosunda yoksa dvr_channels'a bak)
            if not camera:
                if hasattr(api.db, 'get_dvr_channel_by_id'):
                    dvr_camera = api.db.get_dvr_channel_by_id(camera_id, company_id)
                    if dvr_camera:
                        camera = dvr_camera
                        logger.info(f"✅ Found DVR channel for proxy: {camera_id}")
            
            if not camera:
                logger.warning(f"⚠️ Camera not found: {camera_id} for company {company_id}")
                return _structured_error(404, 'CAMERA_NOT_FOUND', 'Kamera bulunamadı')
            
            # Stream URL'sini oluştur (kullanıcının stream_path'i - genelde MJPEG)
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            raw_stream_path = (camera.get('stream_path') or '/video').strip()
            # Only normalize casing for relative paths; absolute URLs must keep original casing.
            stream_path = raw_stream_path.lower() if "://" not in raw_stream_path else raw_stream_path
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            # Snapshot-only path'ler: tek kare döner, canlı akış değil. Proxy-stream için önce MJPEG dene.
            SNAPSHOT_PATH_SUFFIXES = (
                '/shot.jpg', '/photoaf.jpg', '/photo.jpg', '/image.jpg',
                '/snapshot.jpg', '/snapshot.cgi', '/image.cgi'
            )
            is_snapshot_path = any(stream_path.endswith(s) or stream_path == s.lstrip('/') 
                                   for s in SNAPSHOT_PATH_SUFFIXES)
            
            # Never embed credentials into URLs that may reach the client.
            stream_url = f"http://{camera['ip_address']}:{port}{camera.get('stream_path', '/video')}"
            
            # Önce MJPEG stream URL'leri (canlı video), en sonda snapshot (tek kare)
            stream_only_urls = [
                f"{protocol}://{camera['ip_address']}:{port}/video",
                f"{protocol}://{camera['ip_address']}:{port}/videofeed",
                f"{protocol}://{camera['ip_address']}:{port}/mjpeg",
                f"{protocol}://{camera['ip_address']}:{port}/stream",
                f"{protocol}://{camera['ip_address']}:{port}/live",
                f"{protocol}://{camera['ip_address']}:{port}/camera",
                f"{protocol}://{camera['ip_address']}:{port}/webcam",
                f"{protocol}://{camera['ip_address']}:{port}/video.mjpg",
            ]
            snapshot_fallback_urls = [
                f"{protocol}://{camera['ip_address']}:{port}/shot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/photoaf.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/photo.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/image.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/snapshot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/snapshot.cgi",
                f"{protocol}://{camera['ip_address']}:{port}/image.cgi"
            ]
            alternative_urls = stream_only_urls + snapshot_fallback_urls
            
            # 🚀 DVR Kanalı ise RTSP -> MJPEG Dönüştürücü Kullan
            if camera.get('is_dvr') or str(camera.get('stream_path', '')).startswith('rtsp://'):
                # DVR streams must be handled by the DVRStreamHandler service (state machine + probe budgets).
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                import time
                import base64

                sh = get_stream_handler()
                rtsp_url = camera.get('rtsp_url') or camera.get('stream_path') or ''
                ip_address = camera.get('ip_address')
                username = camera.get('username')
                password = camera.get('password')
                rtsp_port = camera.get('port') or 554
                channel_number = camera.get('channel_number')

                stream_id = f"proxy:{company_id}:{camera_id}"
                logger.info(f"🎥 Proxying DVR: {camera_id}")

                if not sh.start_stream(
                    stream_id=stream_id,
                    rtsp_url=str(rtsp_url),
                    ip_address=ip_address,
                    username=username,
                    password=password,
                    rtsp_port=rtsp_port,
                    channel_number=channel_number,
                    sector=None,
                    company_id=company_id,
                ):
                    return _structured_error(
                        503,
                        'STREAM_START_FAILED',
                        'Stream başlatılamadı',
                        details={
                            'retryable': True,
                            'suggested_backoff_ms': 1500,
                            'camera_id': camera_id,
                        },
                        retry_after=2,
                    )

                def _mjpeg_from_service():
                    # Generator içinde bekleme — API worker'ını bloklamaz
                    frame_sleep = 0.08
                    start_wait = time.time()
                    connected = False
                    
                    while True:
                        st_info = sh.get_stream_status(stream_id) or {}
                        status = (st_info.get('status') or '').lower()
                        
                        if status == 'active':
                            connected = True
                            b64 = sh.get_latest_frame(stream_id)
                            if b64:
                                try:
                                    frame_bytes = base64.b64decode(b64)
                                    yield (b'--frame\r\n'
                                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                                except Exception:
                                    pass
                        elif status == 'error':
                            logger.error(f"❌ Stream error detected in proxy: {stream_id}")
                            break
                        elif not connected and (time.time() - start_wait > 10.0):
                            # 10 saniye boyunca hiç bağlanamazsa pes et
                            logger.warning(f"⚠️ Stream connection timeout: {stream_id}")
                            break
                        elif (status in ('stopping', 'stopped')):
                            break
                            
                        time.sleep(frame_sleep)

                return Response(_mjpeg_from_service(), mimetype='multipart/x-mixed-replace; boundary=frame')


            # Standart IP Kamera Akışı (MJPEG)
            import requests
            from requests.auth import HTTPBasicAuth
            
            headers = {
                'User-Agent': 'SmartSafe-AI-Camera-Proxy/1.0',
                'Accept': 'image/*, video/*, */*'
            }
            auth = None
            if username and password:
                auth = HTTPBasicAuth(username, password)
            
            def _stream_response(response):
                ct = response.headers.get('Content-Type') or 'image/jpeg'
                resp = Response(
                    response.iter_content(chunk_size=32768),
                    content_type=ct,
                    direct_passthrough=True
                )
                resp.headers['Content-Type'] = ct
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['X-Accel-Buffering'] = 'no'
                return resp
            
            # Kullanıcı path'i snapshot ise (örn. /shot.jpg) önce MJPEG stream dene; yoksa donuyor hissi olur.
            if not is_snapshot_path:
                logger.info(
                    "🎥 Trying primary stream URL: %s",
                    format_upstream_url_for_log(
                        str(stream_url), company_id=company_id, camera_id=camera_id, label="primary"
                    ),
                )
                try:
                    response = requests.get(stream_url, auth=auth, headers=headers, timeout=2, stream=True)
                    if response.status_code == 200:
                        logger.info(
                            "✅ Primary stream URL successful: %s",
                            format_upstream_url_for_log(
                                str(stream_url), company_id=company_id, camera_id=camera_id, label="primary"
                            ),
                        )
                        return _stream_response(response)
                except Exception as e:
                    logger.warning(f"❌ Primary stream URL failed: {e}")
            else:
                logger.info(f"🎥 Primary path is snapshot ({stream_path}), trying MJPEG stream URLs first")
            
            for i, alt_url in enumerate(alternative_urls, 1):
                try:
                    logger.info(
                        "🎥 Trying alternative URL %s/%s: %s",
                        i,
                        len(alternative_urls),
                        format_upstream_url_for_log(
                            str(alt_url), company_id=company_id, camera_id=camera_id, label=f"alt{i}"
                        ),
                    )
                    response = requests.get(alt_url, auth=auth, headers=headers, timeout=2, stream=True)
                    if response.status_code == 200:
                        logger.info(
                            "✅ Alternative URL successful: %s",
                            format_upstream_url_for_log(
                                str(alt_url), company_id=company_id, camera_id=camera_id, label=f"alt{i}"
                            ),
                        )
                        return _stream_response(response)
                except Exception as e:
                    logger.warning(
                        "❌ Alternative URL %s failed %s: %s",
                        i,
                        format_upstream_url_for_log(
                            str(alt_url), company_id=company_id, camera_id=camera_id, label=f"alt{i}"
                        ),
                        e,
                    )
                    continue
            
            # Eğer IP kamera linki patladıysa ama RTSP URL varsa son çare onu dene (Eskiden capture'da vardı)
            rtsp_url = camera.get('rtsp_url')
            if rtsp_url and rtsp_url.startswith('rtsp://'):
                logger.info(
                    "🔄 Retrying with RTSP as backup for MJPEG proxy: %s",
                    format_upstream_url_for_log(
                        str(rtsp_url), company_id=company_id, camera_id=camera_id, label="rtsp_fallback"
                    ),
                )
                # Use the same generator as DVR
                def _backup_rtsp_generator():
                    import cv2
                    import time
                    cap = cv2.VideoCapture(rtsp_url)
                    try:
                        while cap.isOpened():
                            ret, frame = cap.read()
                            if not ret: break
                            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                            time.sleep(0.04)
                    finally:
                        cap.release()
                return Response(_backup_rtsp_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

            return _structured_error(
                503,
                'STREAM_UNAVAILABLE',
                'Kamera stream alınamadı',
                details={
                    'retryable': True,
                    'suggested_backoff_ms': 1000,
                    'camera_id': camera_id,
                },
                retry_after=1,
            )
            
        except Exception as e:
            logger.error(f"Proxy camera stream error: {e}")
            return _structured_error(
                502,
                'PROXY_ERROR',
                'Proxy stream error',
                details={'retryable': True, 'suggested_backoff_ms': 2000},
                retry_after=2,
            )

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/proxy-snapshot')
    def proxy_camera_snapshot(company_id, camera_id):
        """Kamera snapshot'ını proxy ile getir - CORS sorunlarını çözer"""
        try:
            # Session kontrolü - Render.com debug için
            try:
                user_data = api.validate_session()
                logger.info(f"🔍 Session check for company {company_id}: {user_data}")
                if not user_data or user_data.get('company_id') != company_id:
                    logger.warning(f"❌ Session validation failed for company {company_id}")
                    return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            except Exception as e:
                logger.error(f"❌ Session validation error: {e}")
                return jsonify({'success': False, 'error': 'Oturum kontrolü hatası'}), 401
            
            # Kamerayı veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404

            from utils.redaction import format_upstream_url_for_log
            
            # Snapshot URL'lerini oluştur
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            # Snapshot URL'leri - IP Webcam path'leri öncelikli
            snapshot_urls = [
                # IP Webcam specific paths (Android)
                f"{protocol}://{camera['ip_address']}:{port}/shot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/photoaf.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/photo.jpg",
                # Generic snapshot paths
                f"{protocol}://{camera['ip_address']}:{port}/snapshot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/image.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/snapshot.cgi",
                f"{protocol}://{camera['ip_address']}:{port}/image.cgi",
                f"{protocol}://{camera['ip_address']}:{port}/capture",
                f"{protocol}://{camera['ip_address']}:{port}/photo",
                f"{protocol}://{camera['ip_address']}:{port}/picture"
            ]
            
            # 🚀 DVR Kanalı ise RTSP -> Snapshot Dönüştürücü Kullan
            rtsp_url = camera.get('rtsp_url') or (camera.get('stream_path') if str(camera.get('stream_path', '')).startswith('rtsp://') else None)
            if camera.get('is_dvr') or rtsp_url:
                logger.info(
                    "📸 Capturing snapshot from DVR RTSP: %s",
                    format_upstream_url_for_log(
                        str(rtsp_url) if rtsp_url else "",
                        company_id=company_id,
                        camera_id=camera_id,
                        label="proxy_snapshot_dvr",
                    ),
                )
                try:
                    import cv2
                    cap = cv2.VideoCapture(rtsp_url)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        cap.release()
                        if ret and frame is not None:
                            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                            return Response(buffer.tobytes(), content_type='image/jpeg')
                except Exception as e:
                    logger.warning(f"❌ DVR Snapshot capture failed: {e}")

            # Standart IP Kamera Snapshot
            import requests
            from requests.auth import HTTPBasicAuth
            
            headers = {
                'User-Agent': 'SmartSafe-AI-Camera-Proxy/1.0',
                'Accept': 'image/*'
            }
            
            # Authentication
            auth = None
            if username and password:
                auth = HTTPBasicAuth(username, password)
            
            # URL'leri dene
            for url in snapshot_urls:
                try:
                    response = requests.get(url, auth=auth, headers=headers, timeout=5)
                    if response.status_code == 200:
                        return Response(response.content, 
                                     content_type=response.headers.get('content-type', 'image/jpeg'))
                except Exception as e:
                    logger.warning(
                        "Snapshot URL failed %s: %s",
                        format_upstream_url_for_log(
                            str(url), company_id=company_id, camera_id=camera_id, label="proxy_snapshot"
                        ),
                        e,
                    )
                    continue
            
            # Hiçbiri çalışmazsa ve yukarıda RTSP denememişsek (örn. IP kameranın RTSP'si varsa)
            if rtsp_url and not camera.get('is_dvr'):
                 try:
                    import cv2
                    cap = cv2.VideoCapture(rtsp_url)
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        _, buffer = cv2.imencode('.jpg', frame)
                        return Response(buffer.tobytes(), content_type='image/jpeg')
                 except: pass

            # Hiçbiri çalışmazsa hata döndür
            return jsonify({'success': False, 'error': 'Kamera snapshot alınamadı'}), 404
            
        except Exception as e:
            logger.error(f"Proxy camera snapshot error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/stream-status', methods=['GET'])
    def camera_stream_status(company_id, camera_id):
        """Stream diagnostics for frontend (DVR streams use a state machine)."""
        from utils.redaction import redact_url, stream_log_url_detail_enabled
        try:
            if not api.ensure_database_initialized() or api.db is None:
                return jsonify({'success': False, 'error': {'code': 'DB_UNAVAILABLE', 'message': 'DB unavailable'}}), 503

            cam = api.db.get_camera_by_id(camera_id, company_id)
            if not cam and hasattr(api.db, 'get_dvr_channel_by_id'):
                cam = api.db.get_dvr_channel_by_id(camera_id, company_id)
            if not cam:
                return jsonify({'success': False, 'error': {'code': 'CAMERA_NOT_FOUND', 'message': 'Not found'}}), 404

            is_dvr = (
                cam.get('is_dvr') is True
                or str(cam.get('camera_type', '')).lower() == 'dvr_channel'
                or str(cam.get('stream_path', '')).startswith('rtsp://')
            )
            if is_dvr:
                from integrations.dvr.dvr_stream_handler import get_stream_handler
                sh = get_stream_handler()
                stream_id = f"proxy:{company_id}:{camera_id}"
                status = dict(sh.get_stream_status(stream_id) or {})
                if status.get('rtsp_url'):
                    if stream_log_url_detail_enabled():
                        status['rtsp_url'] = redact_url(str(status['rtsp_url']))
                    else:
                        status['rtsp_configured'] = True
                        status['rtsp_url'] = None
                return jsonify({'success': True, 'stream_id': stream_id, 'status': status})

            return jsonify({'success': True, 'stream_id': None, 'status': {'status': 'unknown'}})
        except Exception as e:
            logger.error(f"camera_stream_status error: {e}")
            return jsonify({'success': False, 'error': {'code': 'STATUS_ERROR', 'message': 'Status error'}}), 502




    @bp.route('/api/company/<company_id>/cameras/smart-discover', methods=['POST'])
    def smart_discover_cameras(company_id):
        """Akıllı kamera keşfi - Ağ taraması"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            network_range = data.get('network_range', '192.168.1.0/24')
            
            logger.info(f"🧠 Smart camera discovery for company {company_id}")
            
            try:
                from integrations.cameras.camera_integration_manager import ProfessionalCameraManager
                
                camera_manager = ProfessionalCameraManager()
                discovered_cameras = camera_manager.smart_discover_cameras(network_range)
                
                return jsonify({
                    'success': True,
                    'cameras': discovered_cameras,
                    'total_found': len(discovered_cameras),
                    'network_range': network_range
                })
                
            except Exception as e:
                logger.error(f"❌ Smart discovery error: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Akıllı keşif hatası: {str(e)}'
                }), 500
            
        except Exception as e:
            logger.error(f"❌ Smart discovery API error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500




    # Kamera durumu API endpoint'i
    @bp.route('/api/company/<company_id>/cameras/<camera_id>/status', methods=['GET'])
    def get_camera_status_api(company_id, camera_id):
        """Kamera durumu API endpoint'i"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            try:
                from integrations.cameras.camera_integration_manager import get_camera_manager
                camera_manager = get_camera_manager()
                
                status = camera_manager.get_camera_status(camera_id)
                
                return jsonify({
                    'success': True,
                    'camera_status': status
                })
                
            except ImportError:
                # Fallback: Simülasyon durumu
                return jsonify({
                    'success': True,
                    'camera_status': {
                        'camera_id': camera_id,
                        'name': f'Kamera {camera_id}',
                        'connection_status': 'connected',
                        'enabled': True,
                        'current_fps': 25.0,
                        'resolution': '1280x720',
                        'source_type': 'simulation',
                        'last_frame_time': datetime.now().isoformat()
                    }
                })
            
        except Exception as e:
            logger.error(f"❌ Camera status failed: {e}")
            return jsonify({
                'success': False,
                'message': f'Kamera durumu alınırken hata oluştu: {str(e)}'
            }), 500

    @bp.route('/api/company/<company_id>/ppe-config', methods=['GET'])
    def get_ppe_config(company_id):
        """Get comprehensive company PPE configuration with sector-specific options"""
        try:
            # Session kontrolü
            if not api.validate_session():
                return jsonify({'success': False, 'error': 'Oturum geçersiz'}), 401
            
            if session.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 403
            
            # Şirket bilgilerini al
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            
            # COALESCE kullanarak eksik kolonlar için default değerler döndür
            if hasattr(api.db, 'db_adapter') and api.db.db_adapter.db_type == 'postgresql':
                cursor.execute('''
                    SELECT 
                        required_ppe, 
                        sector, 
                        COALESCE(ppe_requirements, '{}'::json) AS ppe_requirements,
                        COALESCE(compliance_settings, '{}'::json) AS compliance_settings
                    FROM companies 
                    WHERE company_id = %s
                ''', (company_id,))
            else:
                # SQLite için
                cursor.execute('''
                    SELECT 
                        required_ppe, 
                        sector, 
                        COALESCE(ppe_requirements, '{}') AS ppe_requirements,
                        COALESCE(compliance_settings, '{}') AS compliance_settings
                    FROM companies 
                    WHERE company_id = ?
                ''', (company_id,))
            
            result = cursor.fetchone()
            
            if result:
                required_ppe_json, sector, ppe_requirements, compliance_settings = result
                
                # Eski kayıtlar için uyumluluk mapping'i
                ppe_type_mapping = {
                    'vest': 'safety_vest',
                    'shoes': 'safety_shoes',
                    'mask': 'face_mask',
                    'suit': 'safety_suit',
                    'boots': 'safety_shoes',
                    'hat': 'helmet',
                    'cap': 'helmet'
                }
                
                # Mevcut PPE konfigürasyonunu parse et - önce ppe_requirements'i dene
                try:
                    if ppe_requirements:
                        ppe_config = json.loads(ppe_requirements)
                        if isinstance(ppe_config, dict):
                            current_required = ppe_config.get('required', [])
                            current_optional = ppe_config.get('optional', [])
                        else:
                            current_required = ppe_config if isinstance(ppe_config, list) else []
                            current_optional = []
                    elif required_ppe_json:
                        # Fallback to required_ppe column
                        ppe_config = json.loads(required_ppe_json)
                        if isinstance(ppe_config, dict):
                            current_required = ppe_config.get('required', [])
                            current_optional = ppe_config.get('optional', [])
                        else:
                            current_required = ppe_config if isinstance(ppe_config, list) else []
                            current_optional = []
                    else:
                        current_required = []
                        current_optional = []
                        
                    # PPE türlerini normalize et
                    current_required = [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in current_required]
                    current_optional = [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in current_optional]
                    
                except (json.JSONDecodeError, TypeError):
                    current_required = []
                    current_optional = []
                
                # Şirket kayıt sayfası ile uyumlu endüstri bazlı PPE türleri
                all_ppe_types = {
                    # İnşaat Sektörü PPE'leri
                    'helmet': {'name': 'Baret/Kask', 'icon': 'fas fa-hard-hat', 'category': 'head', 'sectors': ['construction', 'manufacturing', 'warehouse', 'energy', 'petrochemical', 'marine', 'aviation']},
                    'safety_vest': {'name': 'Güvenlik Yeleği', 'icon': 'fas fa-vest', 'category': 'body', 'sectors': ['construction', 'manufacturing', 'warehouse', 'energy', 'marine', 'aviation']},
                    'safety_shoes': {'name': 'Güvenlik Ayakkabısı', 'icon': 'fas fa-shoe-prints', 'category': 'feet', 'sectors': ['construction', 'manufacturing', 'warehouse', 'petrochemical']},
                    'gloves': {'name': 'Güvenlik Eldiveni', 'icon': 'fas fa-hand-paper', 'category': 'hands', 'sectors': ['construction', 'chemical', 'food', 'manufacturing', 'warehouse', 'marine', 'aviation']},
                    'glasses': {'name': 'Güvenlik Gözlüğü', 'icon': 'fas fa-glasses', 'category': 'eyes', 'sectors': ['construction', 'chemical', 'energy', 'petrochemical', 'aviation']},
                    
                    # Gıda Sektörü Özel PPE'leri
                    'hairnet': {'name': 'Bone/Saç Filesi', 'icon': 'fas fa-user-nurse', 'category': 'head', 'sectors': ['food']},
                    'face_mask': {'name': 'Hijyen Maskesi', 'icon': 'fas fa-head-side-mask', 'category': 'respiratory', 'sectors': ['food', 'chemical']},
                    'apron': {'name': 'Hijyen Önlüğü', 'icon': 'fas fa-tshirt', 'category': 'body', 'sectors': ['food']},
                    
                    # Kimya Sektörü Özel PPE'leri
                    'safety_suit': {'name': 'Kimyasal Tulum', 'icon': 'fas fa-user-shield', 'category': 'full_body', 'sectors': ['chemical', 'petrochemical']},
                    'chemical_suit': {'name': 'Kimyasal Koruyucu Tulum', 'icon': 'fas fa-tshirt', 'category': 'full_body', 'sectors': ['petrochemical']},
                    'respiratory_protection': {'name': 'Solunum Koruyucu', 'icon': 'fas fa-head-side-mask', 'category': 'respiratory', 'sectors': ['petrochemical']},
                    'special_gloves': {'name': 'Özel Kimyasal Eldiven', 'icon': 'fas fa-hand-paper', 'category': 'hands', 'sectors': ['petrochemical']},
                    
                    # Enerji Sektörü Özel PPE'leri
                    'insulated_gloves': {'name': 'İzole Eldiven', 'icon': 'fas fa-hand-paper', 'category': 'hands', 'sectors': ['energy']},
                    'dielectric_boots': {'name': 'Dielektrik Ayakkabı', 'icon': 'fas fa-shoe-prints', 'category': 'feet', 'sectors': ['energy']},
                    'arc_flash_suit': {'name': 'Ark Flaş Tulumu', 'icon': 'fas fa-tshirt', 'category': 'full_body', 'sectors': ['energy']},
                    'ear_protection': {'name': 'Kulak Koruyucu', 'icon': 'fas fa-headphones', 'category': 'hearing', 'sectors': ['energy', 'aviation']},
                    
                    # Denizcilik Sektörü Özel PPE'leri
                    'life_jacket': {'name': 'Can Yeleği', 'icon': 'fas fa-life-ring', 'category': 'safety', 'sectors': ['marine']},
                    'marine_helmet': {'name': 'Denizci Kaskı/Baret', 'icon': 'fas fa-hard-hat', 'category': 'head', 'sectors': ['marine']},
                    'waterproof_shoes': {'name': 'Su Geçirmez Ayakkabı', 'icon': 'fas fa-shoe-prints', 'category': 'feet', 'sectors': ['marine']},
                    
                    # Havacılık Sektörü Özel PPE'leri
                    'aviation_helmet': {'name': 'Havacılık Kaskı', 'icon': 'fas fa-hard-hat', 'category': 'head', 'sectors': ['aviation']},
                    'reflective_vest': {'name': 'Reflektör Yelek', 'icon': 'fas fa-vest', 'category': 'body', 'sectors': ['aviation']},
                    'aviation_shoes': {'name': 'Özel Havacılık Ayakkabısı', 'icon': 'fas fa-shoe-prints', 'category': 'feet', 'sectors': ['aviation']},
                    
                    # Genel PPE'ler
                    'safety_harness': {'name': 'Emniyet Kemeri', 'icon': 'fas fa-user-shield', 'category': 'fall_protection', 'sectors': ['construction']},
                    'safety_glasses': {'name': 'Güvenlik Gözlüğü', 'icon': 'fas fa-glasses', 'category': 'eyes', 'sectors': ['energy', 'petrochemical', 'aviation']}
                }
                
                # Şirket kayıt sayfası ile tam uyumlu sektör önerileri
                sector_recommendations = {
                    'construction': {
                        'required': ['helmet', 'safety_vest', 'safety_shoes', 'safety_harness'], 
                        'optional': ['gloves', 'glasses']
                    },
                    'manufacturing': {
                        'required': ['helmet', 'safety_vest', 'safety_shoes'], 
                        'optional': ['gloves']
                    },
                    'chemical': {
                        'required': ['gloves', 'glasses', 'face_mask', 'safety_suit'], 
                        'optional': ['safety_shoes']
                    },
                    'food': {
                        'required': ['hairnet', 'face_mask', 'apron'], 
                        'optional': ['gloves', 'safety_shoes']
                    },
                    'warehouse': {
                        'required': ['helmet', 'safety_vest', 'safety_shoes'], 
                        'optional': ['gloves']
                    },
                    'energy': {
                        'required': ['insulated_gloves', 'dielectric_boots', 'arc_flash_suit', 'helmet'], 
                        'optional': ['safety_glasses', 'ear_protection']
                    },
                    'petrochemical': {
                        'required': ['chemical_suit', 'respiratory_protection', 'special_gloves', 'helmet'], 
                        'optional': ['safety_glasses', 'safety_shoes']
                    },
                    'marine': {
                        'required': ['life_jacket', 'marine_helmet', 'waterproof_shoes', 'safety_vest'], 
                        'optional': ['gloves', 'safety_glasses']
                    },
                    'aviation': {
                        'required': ['aviation_helmet', 'reflective_vest', 'aviation_shoes', 'safety_glasses'], 
                        'optional': ['ear_protection', 'gloves']
                    }
                }
                
                recommendations = sector_recommendations.get(sector, {'required': ['helmet', 'safety_vest'], 'optional': ['gloves']})
                
                # Sektöre uygun PPE'leri filtrele
                sector_specific_ppe = {}
                for ppe_type, ppe_info in all_ppe_types.items():
                    if sector in ppe_info.get('sectors', []):
                        sector_specific_ppe[ppe_type] = ppe_info
                
                # Compliance settings'i parse et
                try:
                    if compliance_settings:
                        compliance_data = json.loads(compliance_settings)
                    else:
                        compliance_data = {
                            'confidence_threshold': 0.6,
                            'detection_interval': 3
                        }
                except (json.JSONDecodeError, TypeError):
                    compliance_data = {
                        'confidence_threshold': 0.6,
                        'detection_interval': 3
                    }
                
                # Sektör bilgileri
                sector_info = {
                    'construction': {'name': 'İnşaat', 'icon': 'fas fa-hard-hat', 'emoji': '🏗️'},
                    'manufacturing': {'name': 'İmalat', 'icon': 'fas fa-industry', 'emoji': '🏭'},
                    'chemical': {'name': 'Kimya', 'icon': 'fas fa-flask', 'emoji': '⚗️'},
                    'food': {'name': 'Gıda & İçecek', 'icon': 'fas fa-utensils', 'emoji': '🍕'},
                    'warehouse': {'name': 'Depo/Lojistik', 'icon': 'fas fa-warehouse', 'emoji': '📦'},
                    'energy': {'name': 'Enerji', 'icon': 'fas fa-bolt', 'emoji': '⚡'},
                    'petrochemical': {'name': 'Petrokimya', 'icon': 'fas fa-oil-can', 'emoji': '🛢️'},
                    'marine': {'name': 'Denizcilik & Tersane', 'icon': 'fas fa-ship', 'emoji': '🚢'},
                    'aviation': {'name': 'Havacılık', 'icon': 'fas fa-plane', 'emoji': '✈️'}
                }
                
                api.db.close_connection(conn)
                return jsonify({
                    'success': True,
                    'current_config': {
                        'required': current_required,
                        'optional': current_optional
                    },
                    'sector': sector,
                    'sector_info': sector_info.get(sector, {'name': sector.title(), 'icon': 'fas fa-industry', 'emoji': '🏢'}),
                    'all_ppe_types': all_ppe_types,
                    'sector_specific_ppe': sector_specific_ppe,
                    'sector_recommendations': recommendations,
                    'compliance_settings': compliance_data,
                    'required_ppe': current_required  # Backward compatibility
                })
            else:
                api.db.close_connection(conn)
                return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
            
        except Exception as e:
            logger.error(f"❌ PPE config getirme hatası: {e}")
            return jsonify({'success': False, 'error': 'Veri getirme başarısız'}), 500

    # === UNIFIED CAMERA SYNC ENDPOINT ===
    @bp.route('/api/company/<company_id>/cameras/sync', methods=['POST'])
    def sync_cameras(company_id):
        """Unified kamera senkronizasyon endpoint'i - Discovery + Config + Database"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json() or {}
            network_range = data.get('network_range', '192.168.1.0/24')
            force_sync = data.get('force_sync', False)  # Zorla yeniden sync
            
            logger.info(f"🔄 Starting unified camera sync for company {company_id}")
            
            result = {
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'company_id': company_id,
                'network_range': network_range,
                'discovery_result': {},
                'config_sync_result': {},
                'database_cameras': [],
                'total_cameras': 0,
                'mode': 'unknown'
            }
            
            # Enterprise mode
            if hasattr(api, 'camera_manager') and api.camera_manager and api.enterprise_enabled:
                try:
                    logger.info("🚀 Using Enterprise Camera Manager for sync")
                    
                    # Full camera synchronization
                    sync_result = api.camera_manager.full_camera_sync(company_id, network_range)
                    
                    if sync_result['success']:
                        # Get final camera list from database
                        final_cameras = api.camera_manager.get_database_cameras(company_id)
                        
                        result.update({
                            'success': True,
                            'discovery_result': sync_result['discovery_result'],
                            'config_sync_result': sync_result['config_sync_result'],
                            'database_cameras': final_cameras,
                            'total_cameras': len(final_cameras),
                            'mode': 'enterprise',
                            'message': 'Enterprise kamera senkronizasyonu tamamlandı'
                        })
                        
                        logger.info(f"✅ Enterprise sync complete: {len(final_cameras)} cameras in database")
                        return jsonify(result)
                    else:
                        logger.warning(f"⚠️ Enterprise sync failed: {sync_result.get('error')}")
                        result['enterprise_error'] = sync_result.get('error')
                
                except Exception as e:
                    logger.error(f"❌ Enterprise sync error: {e}")
                    result['enterprise_error'] = str(e)
            
            # Fallback mode
            logger.info("📱 Using fallback camera sync")
            result['mode'] = 'fallback'
            
            # Step 1: Network discovery
            try:
                from integrations.cameras.camera_discovery import IPCameraDiscovery
                discovery = IPCameraDiscovery()
                discovery_result = discovery.scan_network(network_range, timeout=2)
                result['discovery_result'] = discovery_result
                
                # Step 2: Sync discovered cameras to database
                if discovery_result.get('cameras'):
                    from database.database_adapter import get_camera_discovery_manager
                    discovery_manager = get_camera_discovery_manager()
                    db_sync_result = discovery_manager.sync_discovered_cameras_to_db(
                        company_id, 
                        discovery_result['cameras']
                    )
                    result['discovery_sync'] = db_sync_result
                    
            except Exception as discovery_error:
                logger.error(f"❌ Discovery failed: {discovery_error}")
                result['discovery_error'] = str(discovery_error)
            
            # Step 3: Config file sync
            try:
                from database.database_adapter import get_camera_discovery_manager
                discovery_manager = get_camera_discovery_manager()
                config_sync_result = discovery_manager.sync_config_cameras_to_db(company_id)
                result['config_sync_result'] = config_sync_result
                
            except Exception as config_error:
                logger.error(f"❌ Config sync failed: {config_error}")
                result['config_error'] = str(config_error)
            
            # Step 4: Get final camera list
            try:
                final_cameras = api.db.get_company_cameras(company_id)
                result.update({
                    'database_cameras': final_cameras,
                    'total_cameras': len(final_cameras),
                    'success': True,
                    'message': f'Fallback kamera senkronizasyonu tamamlandı: {len(final_cameras)} kamera'
                })
                
            except Exception as db_error:
                logger.error(f"❌ Database read failed: {db_error}")
                result['database_error'] = str(db_error)
            
            logger.info(f"✅ Camera sync complete: {result['total_cameras']} cameras")
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"❌ Camera sync error: {e}")
            return jsonify({
                'success': False, 
                'error': str(e), 
                'timestamp': datetime.now().isoformat()
            }), 500
    # ── Kamera Sağlık Durumu (Health Monitoring) API ───────────────────────
    @bp.route('/api/company/<company_id>/cameras/health', methods=['GET'])
    def camera_health_status(company_id):
        """Tüm kameraların gerçek zamanlı sağlık durumu — Stream Watchdog entegreli.
        
        Dönüş: her kamera için online/offline, son frame zamanı, detection durumu,
        reconnect sayısı ve genel özet istatistikler.
        """
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            import app as app_module
            
            cameras = api.db.get_company_cameras(company_id)
            now = time.time()
            
            # Watchdog instance'ını al
            watchdog = None
            watchdog_status = {'running': False, 'total_restarts': 0, 'last_check': None}
            try:
                from integrations.cameras.stream_watchdog import get_stream_watchdog
                watchdog = get_stream_watchdog()
                if watchdog:
                    watchdog_status = watchdog.get_status()
            except Exception:
                pass
            
            camera_health_list = []
            online_count = 0
            detection_active_count = 0
            
            for cam in cameras:
                camera_id = cam.get('id', cam.get('camera_id', ''))
                camera_key = f"{company_id}_{camera_id}"
                
                # Stream aktif mi?
                is_active = app_module.active_detectors.get(camera_key, False)
                
                # Son frame zamanı
                last_ts = app_module.frame_timestamps.get(camera_key)
                seconds_since_frame = round(now - last_ts, 1) if last_ts else None
                
                # Stream durumu: online (son 30s frame var), stale (30-120s), offline
                if last_ts and seconds_since_frame <= 30:
                    stream_status = 'online'
                    online_count += 1
                elif last_ts and seconds_since_frame <= 120:
                    stream_status = 'stale'
                elif is_active:
                    stream_status = 'connecting'
                else:
                    stream_status = 'offline'
                
                # Detection aktif mi?
                detection_active = is_active and stream_status in ('online', 'stale')
                if detection_active:
                    detection_active_count += 1
                
                # Reconnect bilgisi (watchdog'dan)
                reconnect_count = 0
                watchdog_cam_status = 'unknown'
                if watchdog:
                    cam_health = watchdog.get_camera_health(camera_key)
                    reconnect_count = cam_health.get('restart_count', 0)
                    watchdog_cam_status = cam_health.get('watchdog_status', 'unknown')
                
                # Hata sayısı
                failure_count = app_module.frame_failure_counts.get(camera_key, 0)
                
                # Stream URL maskeleme (güvenlik)
                ip_addr = cam.get('ip_address', '')
                masked_url = f"rtsp://***@{ip_addr}:..." if ip_addr else None
                
                camera_health_list.append({
                    'camera_id': camera_id,
                    'name': cam.get('name', f'Kamera {camera_id}'),
                    'location': cam.get('location', ''),
                    'ip_address': ip_addr,
                    'stream_status': stream_status,
                    'watchdog_status': watchdog_cam_status,
                    'detection_active': detection_active,
                    'last_frame_time': (
                        datetime.utcfromtimestamp(last_ts).isoformat() + 'Z'
                        if last_ts else None
                    ),
                    'seconds_since_last_frame': seconds_since_frame,
                    'reconnect_count': reconnect_count,
                    'consecutive_failures': failure_count,
                    'stream_url_masked': masked_url,
                })
            
            total = len(cameras)
            
            return jsonify({
                'success': True,
                'cameras': camera_health_list,
                'summary': {
                    'total': total,
                    'online': online_count,
                    'offline': total - online_count,
                    'detection_active': detection_active_count,
                },
                'watchdog': watchdog_status,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
            })
            
        except Exception as e:
            logger.error(f"❌ Camera health API error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    # ── Toplu Kamera Ekleme (Batch Provisioning) ─────────────────────────
    @bp.route('/api/company/<company_id>/cameras/batch-provision', methods=['POST'])
    def batch_provision_cameras(company_id):
        """Manuel IP listesi ile toplu kamera ekleme.
        
        ONVIF otomatik keşif kurumsal ağlarda çoğu zaman çalışmaz (multicast
        kapalı, VLAN izolasyonu). Bu endpoint, IT ekibinin verdiği IP listesini
        alıp her IP için:
          1. ONVIF bağlantısı dener (opsiyonel)
          2. Başarısızsa marka-tahmin RTSP URL'lerini dener
          3. Bulunan her kamera/kanalı DB'ye ekler
          4. Bağlantı testi sonucunu raporlar
        """
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            data = request.get_json()
            if not data or 'cameras' not in data:
                return jsonify({
                    'success': False,
                    'error': 'Geçersiz istek: "cameras" listesi gerekli',
                    'expected_format': {
                        'cameras': [
                            {'ip': '192.168.10.10', 'port': 554, 'username': 'admin', 'password': '...', 'name': 'Kamera Adı'}
                        ],
                        'use_onvif': True,
                        'auto_detect_channels': True
                    }
                }), 400
            
            camera_list = data['cameras']
            if not camera_list or not isinstance(camera_list, list):
                return jsonify({'success': False, 'error': '"cameras" boş olamaz'}), 400
            
            use_onvif = data.get('use_onvif', True)
            auto_detect_channels = data.get('auto_detect_channels', True)
            
            # Abonelik limit kontrolü
            subscription_info = api.get_subscription_info_internal(company_id)
            if not subscription_info.get('success'):
                return jsonify({'success': False, 'error': 'Abonelik bilgileri alınamadı'}), 400
            
            current_cameras = subscription_info['used_cameras']
            max_cameras = subscription_info['max_cameras']
            remaining_slots = max_cameras - current_cameras
            
            logger.info(
                f"📦 Batch provision: {len(camera_list)} IP, "
                f"kalan slot: {remaining_slots}/{max_cameras}, "
                f"ONVIF: {use_onvif}, şirket: {company_id}"
            )
            
            results = []
            total_added = 0
            
            for entry in camera_list:
                ip = entry.get('ip', '').strip()
                port = int(entry.get('port', 554))
                username = entry.get('username', '')
                password = entry.get('password', '')
                cam_name = entry.get('name', f'Kamera {ip}')
                protocol = entry.get('protocol', 'rtsp')
                
                if not ip:
                    results.append({'ip': ip, 'status': 'error', 'detail': 'IP adresi boş'})
                    continue
                
                # Kalan slot kontrolü
                if total_added >= remaining_slots:
                    results.append({
                        'ip': ip, 'status': 'skipped',
                        'detail': f'Kamera limiti aşıldı ({max_cameras})'
                    })
                    continue
                
                entry_result = {
                    'ip': ip,
                    'port': port,
                    'status': 'pending',
                    'channels_found': 0,
                    'cameras_added': [],
                    'method': 'unknown',
                    'detail': '',
                }
                
                # ── 1) ONVIF ile dene ────────────────────────────────────────
                onvif_success = False
                channels_from_onvif = []
                
                if use_onvif:
                    try:
                        from integrations.cameras.onvif_discovery import ONVIFDeviceManager
                        manager = ONVIFDeviceManager()
                        
                        # ONVIF bağlantı testi
                        conn_result = manager.test_onvif_connection(ip, port=port,
                                                                      username=username,
                                                                      password=password)
                        if conn_result.get('success'):
                            entry_result['method'] = 'onvif'
                            
                            # Kanal listesini al
                            if auto_detect_channels:
                                try:
                                    ch_result = manager.enumerate_nvr_channels(
                                        ip, username=username, password=password
                                    )
                                    channels_from_onvif = ch_result.get('channels', [])
                                except Exception:
                                    pass
                            
                            # Eğer kanal bulunamadıysa en azından stream URI al
                            if not channels_from_onvif:
                                try:
                                    profiles = manager.get_media_profiles(
                                        ip, username=username, password=password
                                    )
                                    if profiles:
                                        stream_uri = manager.get_stream_uri(
                                            ip, profiles[0].get('token', ''),
                                            username=username, password=password
                                        )
                                        channels_from_onvif = [{
                                            'channel_number': 1,
                                            'name': cam_name,
                                            'stream_uri': stream_uri.get('uri', ''),
                                        }]
                                except Exception:
                                    pass
                            
                            if channels_from_onvif:
                                onvif_success = True
                                
                    except ImportError:
                        logger.warning("⚠️ ONVIF modülü yüklü değil, RTSP probing'e geçiliyor")
                    except Exception as onvif_err:
                        logger.debug(f"ONVIF bağlantı hatası ({ip}): {onvif_err}")
                
                # ── 2) ONVIF başarısızsa → RTSP URL tahmini ─────────────────
                if not onvif_success:
                    entry_result['method'] = 'rtsp_probe'
                    
                    # Yaygın RTSP URL formatları (Hikvision, Dahua, generic)
                    rtsp_templates = [
                        # Hikvision
                        f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/101",
                        f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/1",
                        # Dahua
                        f"rtsp://{username}:{password}@{ip}:{port}/cam/realmonitor?channel=1&subtype=0",
                        # Generic ONVIF
                        f"rtsp://{username}:{password}@{ip}:{port}/stream1",
                        f"rtsp://{username}:{password}@{ip}:{port}/live",
                        f"rtsp://{username}:{password}@{ip}:{port}/h264",
                        # Auth-free variants
                        f"rtsp://{ip}:{port}/stream1",
                    ] if username and password else [
                        f"rtsp://{ip}:{port}/stream1",
                        f"rtsp://{ip}:{port}/live",
                        f"rtsp://{ip}:{port}/h264",
                    ]
                    
                    working_url = None
                    try:
                        import cv2
                        for url in rtsp_templates:
                            try:
                                cap = cv2.VideoCapture(url)
                                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                                if cap.isOpened():
                                    ret, _frame = cap.read()
                                    if ret:
                                        working_url = url
                                        cap.release()
                                        break
                                cap.release()
                            except Exception:
                                continue
                    except ImportError:
                        pass
                    
                    if working_url:
                        channels_from_onvif = [{
                            'channel_number': 1,
                            'name': cam_name,
                            'stream_uri': working_url,
                        }]
                    else:
                        # Hiçbir URL çalışmasa bile kamerayı ekle (kullanıcı sonra düzeltebilir)
                        channels_from_onvif = [{
                            'channel_number': 1,
                            'name': cam_name,
                            # Never embed credentials into the URI; credentials are stored separately.
                            'stream_uri': f"rtsp://{ip}:{port}/stream1",
                        }]
                        entry_result['detail'] = (
                            'Otomatik bağlantı testi başarısız oldu. '
                            'Kamera eklendi fakat stream URL\'si doğrulanmadı — '
                            'kamera ayarlarından manuel olarak kontrol edin.'
                        )
                
                # ── 3) Bulunan kanalları DB'ye ekle ─────────────────────────
                entry_result['channels_found'] = len(channels_from_onvif)
                
                for ch in channels_from_onvif:
                    if total_added >= remaining_slots:
                        break
                    
                    ch_number = ch.get('channel_number', 1)
                    ch_name = ch.get('name', f'{cam_name} CH{ch_number}')
                    from utils.redaction import strip_url_userinfo
                    stream_uri = strip_url_userinfo(ch.get('stream_uri', ''))
                    
                    camera_data = {
                        'name': ch_name,
                        'location': entry.get('location', ''),
                        'ip_address': ip,
                        'port': port,
                        'protocol': protocol,
                        'stream_path': stream_uri,
                        'username': username,
                        'password': password,
                        'status': 'active',
                        'channel_number': ch_number,
                    }
                    
                    try:
                        success, result = api.db.add_camera(company_id, camera_data)
                        if success:
                            entry_result['cameras_added'].append(result)
                            total_added += 1
                        else:
                            entry_result['detail'] += f' CH{ch_number} ekleme hatası: {result}.'
                    except Exception as db_err:
                        entry_result['detail'] += f' CH{ch_number} DB hatası: {db_err}.'
                
                entry_result['status'] = 'success' if entry_result['cameras_added'] else 'failed'
                results.append(entry_result)
            
            failed_count = len([r for r in results if r['status'] == 'failed'])
            
            return jsonify({
                'success': True,
                'total_submitted': len(camera_list),
                'successfully_added': total_added,
                'failed': failed_count,
                'remaining_slots': remaining_slots - total_added,
                'details': results,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
            })
            
        except Exception as e:
            logger.error(f"❌ Batch provision error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    return bp
