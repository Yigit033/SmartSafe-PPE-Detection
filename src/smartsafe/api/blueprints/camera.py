"""
SmartSafe AI - Camera Blueprint
Camera-related routes extracted from smartsafe_saas_api.py
"""

from flask import Blueprint, request, jsonify, session, redirect, render_template, render_template_string, Response
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

logger = logging.getLogger(__name__)


def create_blueprint(api):
    """Create and return the camera blueprint."""
    bp = Blueprint('camera', __name__)

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/mjpeg')
    def mjpeg_ip_camera_stream(company_id, camera_id):
        """Serve MJPEG stream for IP cameras with PPE detection overlay"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

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
            
            # Build stream URL
            if username and password:
                stream_url = f"{protocol}://{username}:{password}@{camera['ip_address']}:{port}{stream_path}"
                auth = HTTPBasicAuth(username, password)
            else:
                stream_url = f"{protocol}://{camera['ip_address']}:{port}{stream_path}"
                auth = None

            # Alternative URLs for different camera types
            alternative_urls = [
                f"{protocol}://{camera['ip_address']}:{port}/shot.jpg",
                f"{protocol}://{camera['ip_address']}:{port}/video",
                f"{protocol}://{camera['ip_address']}:{port}/mjpeg",
                f"{protocol}://{camera['ip_address']}:{port}/stream",
                f"{protocol}://{camera['ip_address']}:{port}/live"
            ]

            boundary = 'frame'
            frame_count = 0
            last_detection_time = 0
            detection_frequency = 5  # Her 5 frame'de bir detection (daha sık)

            def generate():
                nonlocal frame_count, last_detection_time
                
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
                            logger.debug(f"Primary URL failed: {e}")
                        
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
                                    logger.debug(f"Alternative URL failed {alt_url}: {e}")
                                    continue
                        
                        if frame is not None and frame.size > 0:
                            frame_count += 1
                            
                            # 🎯 PPE DETECTION - Her 5 frame'de bir detection (daha sık)
                            current_time = time.time()
                            if frame_count % 5 == 0 and (current_time - last_detection_time) > 0.2:
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
                                            from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
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

    # Şirket dashboard
    @bp.route('/company/<company_id>/dashboard', methods=['GET'])
    def company_dashboard(company_id):
        """Şirket dashboard"""
        # Oturum kontrolü
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        # Abonelik bilgilerini doğrudan backend'den al
        try:
            subscription_info = api.get_subscription_info_internal(company_id)
            if subscription_info['success']:
                # get_subscription_info_internal direkt subscription data döndürüyor, 'subscription' key'i yok
                subscription_data = subscription_info
            else:
                subscription_data = {
                    'subscription_type': 'BASIC',
                    'used_cameras': 0,
                    'max_cameras': 25,
                    'is_active': True,
                    'usage_percentage': 0
                }
        except Exception as e:
            logger.error(f"❌ Dashboard subscription info error: {e}")
            subscription_data = {
                'subscription_type': 'BASIC',
                'used_cameras': 0,
                'max_cameras': 25,
                'is_active': True,
                'usage_percentage': 0
            }
        
        return render_template_string(api.get_dashboard_template(), 
                                    company_id=company_id, 
                                    user_data=user_data,
                                    subscription_data=subscription_data)

    # Şirket istatistikleri API (Enhanced)
    @bp.route('/api/company/<company_id>/stats', methods=['GET'])
    def get_company_stats(company_id):
        """Unified şirket istatistikleri - Database'den gerçek kamera sayısı"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            # MultiTenant database'den base istatistikleri al
            stats = api.db.get_company_stats(company_id)
            
            # Gerçek kamera sayısını database'den al (unified approach)
            try:
                cameras = api.db.get_company_cameras(company_id)
                total_cameras = len(cameras)
                active_cameras = len([c for c in cameras if c.get('status') == 'active'])
                discovered_cameras = len([c for c in cameras if c.get('status') == 'discovered'])
                
                # Kamera istatistiklerini güncelle
                stats.update({
                    'active_cameras': active_cameras,
                    'total_cameras': total_cameras,
                    'discovered_cameras': discovered_cameras,
                    'inactive_cameras': total_cameras - active_cameras
                })
                
                logger.info(f"✅ Unified stats for company {company_id}: {total_cameras} cameras ({active_cameras} active, {discovered_cameras} discovered)")
                
            except Exception as camera_error:
                logger.error(f"❌ Error getting camera stats: {camera_error}")
                # Fallback to existing stats without camera updates
            
            # Enhanced stats with unified camera data
            enhanced_stats = {
                'active_cameras': stats.get('active_cameras', 0),
                'total_cameras': stats.get('total_cameras', 0),
                'discovered_cameras': stats.get('discovered_cameras', 0),
                'compliance_rate': stats.get('compliance_rate', 0),
                'today_violations': stats.get('today_violations', 0),
                'active_workers': stats.get('active_workers', 0),
                'total_detections': stats.get('total_detections', 0),
                'monthly_violations': stats.get('monthly_violations', 0),
                
                # Trend indicators - Backward compatibility
                'cameras_trend': stats.get('cameras_trend', 0),
                'compliance_trend': stats.get('compliance_trend', 0),
                'violations_trend': stats.get('violations_trend', 0),
                'workers_trend': stats.get('workers_trend', 0),
                'people_trend': stats.get('people_trend', 0),
                'fps_trend': stats.get('fps_trend', 0),
                'processing_trend': stats.get('processing_trend', 0),
                
                # Unified data source indicator
                'data_source': 'unified_database',
                'last_updated': datetime.now().isoformat()
            }
            
            return jsonify(enhanced_stats)
            
        except Exception as e:
            logger.error(f"❌ Stats error for company {company_id}: {e}")
            return jsonify({
                'error': 'İstatistikler getirilemedi',
                'details': str(e)
            }), 500

    # Şirket kameraları API
    @bp.route('/api/company/<company_id>/cameras', methods=['GET'])
    def get_company_cameras(company_id):
        """Şirket kameralarını getir - Unified Database Source"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            # Unified approach: Database'den kameraları al
            cameras = api.db.get_company_cameras(company_id)
            
            # Enterprise camera manager entegrasyonu
            if hasattr(api, 'camera_manager') and api.camera_manager:
                # Real-time status update
                for camera in cameras:
                    try:
                        # IP'den camera manager'da status kontrol et
                        if camera.get('ip_address'):
                            status_info = api._get_realtime_camera_status(camera['ip_address'])
                            if status_info:
                                camera.update(status_info)
                    except Exception as e:
                        logger.debug(f"Real-time status check failed for {camera.get('name', 'unknown')}: {e}")
            
            # Kamera sayısı ve summary bilgileri ekle
            total_cameras = len(cameras)
            active_cameras = len([c for c in cameras if c.get('status') == 'active'])
            
            result = {
                'success': True, 
                'cameras': cameras,
                'total': total_cameras,
                'active': active_cameras,
                'summary': {
                    'total_cameras': total_cameras,
                    'active_cameras': active_cameras,
                    'inactive_cameras': total_cameras - active_cameras,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
            logger.info(f"✅ Retrieved {total_cameras} cameras for company {company_id}")
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"❌ Error getting cameras for company {company_id}: {e}")
            return jsonify({'success': False, 'error': 'Kameralar getirilemedi'}), 500

    # Kamera ekleme API
    @bp.route('/api/company/<company_id>/cameras', methods=['POST'])
    def add_camera(company_id):
        """Yeni kamera ekleme"""
        try:
            logger.info(f"🚀 ADD CAMERA REQUEST STARTED")
            logger.info(f"📋 Company ID: {company_id}")
            logger.info(f"📡 Request method: {request.method}")
            logger.info(f"📡 Request headers: {dict(request.headers)}")
            logger.info(f"📡 Request data: {request.get_data()}")
            
            # Session kontrolü
            session_id = request.cookies.get('session_id')
            logger.info(f"🍪 Session ID from cookie: {session_id}")
            
            user_data = api.validate_session()
            logger.info(f"👤 User validation result: {user_data is not None}")
            if user_data:
                logger.info(f"👤 User data: {user_data}")
            
            if not user_data or user_data['company_id'] != company_id:
                logger.error(f"❌ Unauthorized access attempt")
                logger.error(f"❌ User data: {user_data}")
                logger.error(f"❌ Expected company_id: {company_id}")
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            logger.info(f"✅ User authorized successfully")
            
            # Abonelik limit kontrolü
            logger.info(f"🔍 Checking subscription limits...")
            subscription_info = api.get_subscription_info_internal(company_id)
            logger.info(f"📊 Subscription info: {subscription_info}")
                
            if not subscription_info['success']:
                logger.error(f"❌ Subscription info failed: {subscription_info}")
                return jsonify({'success': False, 'error': 'Abonelik bilgileri alınamadı'}), 400
            
            # subscription_info doğrudan tüm bilgileri içeriyor, 'subscription' key'i yok
            current_cameras = subscription_info['used_cameras']
            max_cameras = subscription_info['max_cameras']
            
            logger.info(f"📈 Camera limits - Current: {current_cameras}, Max: {max_cameras}")
            
            # Limit kontrolü
            if current_cameras >= max_cameras:
                logger.warning(f"⚠️ Camera limit reached: {current_cameras}/{max_cameras}")
                return jsonify({
                    'success': False, 
                    'error': f'Kamera limiti aşıldı! Mevcut: {current_cameras}/{max_cameras}',
                    'limit_reached': True,
                    'current_cameras': current_cameras,
                    'max_cameras': max_cameras,
                    'subscription_type': subscription_info['subscription_type']
                }), 403
            
            logger.info(f"✅ Camera limit check passed")
            
            data = request.json
            logger.info(f"📹 Raw camera data received: {data}")
            
            # Veri doğrulama - Field mapping düzeltmesi
            # Frontend'den gelen field isimleri: camera_name, camera_location, camera_ip, camera_port, camera_protocol, camera_path
            # Backend'in beklediği field isimleri: name, location, ip_address, port, protocol, stream_path
            
            # Field mapping yap
            mapped_data = {
                'name': data.get('camera_name'),
                'location': data.get('camera_location'),
                'ip_address': data.get('camera_ip'),
                'port': data.get('camera_port', 8080),
                'protocol': data.get('camera_protocol', 'http'),
                'stream_path': data.get('camera_path', '/video'),
                'username': data.get('camera_username', ''),
                'password': data.get('camera_password', '')
            }
            
            # Required fields kontrolü
            required_fields = ['name', 'location', 'ip_address']
            missing_fields = [field for field in required_fields if not mapped_data.get(field)]
            
            if missing_fields:
                logger.error(f"❌ Missing required fields: {missing_fields}")
                return jsonify({'success': False, 'error': f'Eksik alanlar: {", ".join(missing_fields)}'}), 400
            
            logger.info(f"✅ Data validation passed")
            logger.info(f"📝 Camera name: {mapped_data.get('name')}")
            logger.info(f"📍 Location: {mapped_data.get('location')}")
            logger.info(f"🌐 IP Address: {mapped_data.get('ip_address')}")
            logger.info(f"🔌 Port: {mapped_data.get('port')}")
            logger.info(f"🔐 Protocol: {mapped_data.get('protocol')}")
            logger.info(f"📁 Stream Path: {mapped_data.get('stream_path')}")
            
            # Kamera ekle
            logger.info(f"💾 Calling database add_camera function...")
            success, result = api.db.add_camera(company_id, mapped_data)
            logger.info(f"💾 Database result - Success: {success}, Result: {result}")
            
            if success:
                logger.info(f"✅ Camera added successfully with ID: {result}")
                return jsonify({'success': True, 'camera_id': result})
            else:
                logger.error(f"❌ Camera addition failed: {result}")
                return jsonify({'success': False, 'error': result}), 400
                
        except Exception as e:
            logger.error(f"💥 EXCEPTION in add_camera: {e}")
            logger.error(f"💥 Exception type: {type(e)}")
            import traceback
            logger.error(f"💥 Full traceback: {traceback.format_exc()}")
            return jsonify({'success': False, 'error': 'Kamera eklenemedi'}), 500

    # Şirket grafik verileri API
    @bp.route('/api/company/<company_id>/chart-data', methods=['GET'])
    def get_company_chart_data(company_id):
        """Şirket grafik verileri"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return jsonify({'error': 'Yetkisiz erişim'}), 401
        
        try:
            # Gerçek detection sonuçlarından grafik verilerini hesapla
            chart_data = api.calculate_real_chart_data(company_id)
            
            return jsonify(chart_data)
            
        except Exception as e:
            logger.error(f"❌ Grafik verileri yüklenemedi: {e}")
            return jsonify({'error': 'Grafik verileri yüklenemedi'}), 500

    @bp.route('/api/company/<company_id>/cameras/discover', methods=['POST'])
    def discover_cameras(company_id):
        """Unified kamera keşif ve senkronizasyon sistemi"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json() or {}
            network_range = data.get('network_range', '192.168.1.0/24')
            auto_sync = data.get('auto_sync', True)  # Otomatik DB sync
            
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
                from src.smartsafe.integrations.cameras.camera_discovery import IPCameraDiscovery
                discovery = IPCameraDiscovery()
                result = discovery.scan_network(network_range, timeout=2)
                discovered_cameras = result['cameras']
                scan_time = result['scan_time']
                
                # Auto sync to database if enabled
                if auto_sync and discovered_cameras:
                    try:
                        from src.smartsafe.database.database_adapter import get_camera_discovery_manager
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
                # Fallback: örnek veriler
                discovered_cameras = [
                    {
                        'ip': '192.168.1.101',
                        'port': 554,
                        'brand': 'Hikvision',
                        'model': 'DS-2CD2043G0-I',
                        'rtsp_url': 'rtsp://192.168.1.101:554/Streaming/Channels/101',
                        'resolution': '4MP',
                        'status': 'online',
                        'auth_required': True
                    }
                ]
                scan_time = '2.3 saniye'
            
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
                from src.smartsafe.integrations.cameras.camera_integration_manager import RealCameraManager, RealCameraConfig
                
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
            
            logger.info(f"🧠 Smart camera test for {ip_address}")
            
            try:
                from src.smartsafe.integrations.cameras.camera_integration_manager import SmartCameraDetector
                
                detector = SmartCameraDetector()
                detection_result = detector.smart_detect_camera(ip_address)
                
                if detection_result['success']:
                    # Kamera başarıyla tespit edildi, test et
                    port = detection_result.get('port', 8080)
                    protocol = detection_result.get('protocol', 'http')
                    path = detection_result.get('path', '/video')
                    
                    # Basic kamera testi
                    from src.smartsafe.integrations.cameras.camera_integration_manager import CameraSource
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
            
            logger.info(f"⚡ Quick camera test for {ip_address}:{port}")
            
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
            
            logger.info(f"🎯 Gerçek kamera testi başlatılıyor: {ip_address}:{port}")
            
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
                
                logger.info(f"🔍 Test URL: {url}")
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
            logger.info(f"🔍 Camera details for {camera_id}: {camera}")
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

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/stream')
    def camera_stream(company_id, camera_id):
        """Kamera stream sayfası"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data['company_id'] != company_id:
                return redirect(f'/company/{company_id}/login')
            
            # Kamerayı veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                return "Kamera bulunamadı", 404
            
            # Stream URL'sini oluştur
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            stream_path = camera.get('stream_path', '/video')
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            # URL oluştur - Android IP Webcam için optimize edilmiş
            if username and password:
                stream_url = f"{protocol}://{username}:{password}@{camera['ip_address']}:{port}{stream_path}"
            else:
                stream_url = f"{protocol}://{camera['ip_address']}:{port}{stream_path}"
            
            # Android IP Webcam için alternatif URL'ler
            alternative_urls = [
                f"{protocol}://{camera['ip_address']}:{port}/shot.jpg",  # Snapshot
                f"{protocol}://{camera['ip_address']}:{port}/video",     # Video stream
                f"{protocol}://{camera['ip_address']}:{port}/mjpeg",     # MJPEG
            ]
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{camera['camera_name']} - Canlı Görüntü</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ margin: 0; padding: 20px; background: #000; color: white; font-family: Arial, sans-serif; }}
                    .stream-container {{ text-align: center; }}
                    .stream-title {{ margin-bottom: 20px; font-size: 24px; }}
                    .stream-video {{ max-width: 100%; height: auto; border-radius: 10px; }}
                    .stream-info {{ margin-top: 20px; font-size: 14px; color: #ccc; }}
                    .error-message {{ color: #ff6b6b; margin-top: 20px; }}
                    .url-info {{ font-size: 12px; color: #888; margin-top: 10px; }}
                </style>
                <script>
                    let currentUrlIndex = 0;
                    const streamUrls = [
                        "{stream_url}",
                        "{alternative_urls[0]}",
                        "{alternative_urls[1]}",
                        "{alternative_urls[2]}"
                    ];
                    
                    function tryNextUrl() {{
                        currentUrlIndex++;
                        if (currentUrlIndex < streamUrls.length) {{
                            document.getElementById('stream-img').src = streamUrls[currentUrlIndex];
                            document.getElementById('url-info').textContent = 'Denenen URL: ' + streamUrls[currentUrlIndex];
                        }} else {{
                            document.getElementById('error-message').style.display = 'block';
                            document.getElementById('url-info').textContent = 'Tüm URL\\'ler denendi, görüntü alınamadı';
                        }}
                    }}
                </script>
            </head>
            <body>
                <div class="stream-container">
                    <div class="stream-title">{camera['camera_name']} - Canlı Görüntü</div>
                    <img id="stream-img" src="{stream_url}" alt="Kamera Görüntüsü" class="stream-video" 
                         onerror="tryNextUrl()">
                    <div id="error-message" class="error-message" style="display: none;">
                        <h2>Görüntü alınamadı</h2>
                        <p>Kamera bağlantısını kontrol edin</p>
                        <p>IP: {camera['ip_address']}:{port}</p>
                        <p>Protokol: {protocol}</p>
                    </div>
                    <div id="url-info" class="url-info">Denenen URL: {stream_url}</div>
                    <div class="stream-info">
                        <p>IP: {camera['ip_address']} | Konum: {camera.get('location', 'N/A')}</p>
                        <p>Son güncelleme: {camera.get('updated_at', 'N/A')}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
        except Exception as e:
            logger.error(f"Camera stream error: {e}")
            return "Stream yüklenirken hata oluştu", 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/proxy-stream')
    def proxy_camera_stream(company_id, camera_id):
        """Kamera stream'ini proxy ile getir - CORS sorunlarını çözer"""
        try:
            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in proxy_camera_stream")
                return jsonify({'success': False, 'error': 'Veritabanı başlatılamadı'}), 500
            
            if api.db is None:
                logger.error("❌ Database connection is None in proxy_camera_stream")
                return jsonify({'success': False, 'error': 'Veritabanı bağlantısı yok'}), 500
            
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
                logger.warning(f"⚠️ Camera not found: {camera_id} for company {company_id}")
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            # Stream URL'sini oluştur (kullanıcının stream_path'i - genelde MJPEG)
            protocol = camera.get('protocol', 'http')
            port = camera.get('port', 8080)
            stream_path = (camera.get('stream_path') or '/video').strip().lower()
            username = camera.get('username', '')
            password = camera.get('password', '')
            
            # Snapshot-only path'ler: tek kare döner, canlı akış değil. Proxy-stream için önce MJPEG dene.
            SNAPSHOT_PATH_SUFFIXES = (
                '/shot.jpg', '/photoaf.jpg', '/photo.jpg', '/image.jpg',
                '/snapshot.jpg', '/snapshot.cgi', '/image.cgi'
            )
            is_snapshot_path = any(stream_path.endswith(s) or stream_path == s.lstrip('/') 
                                   for s in SNAPSHOT_PATH_SUFFIXES)
            
            if username and password:
                stream_url = f"http://{username}:{password}@{camera['ip_address']}:{port}{camera.get('stream_path', '/video')}"
            else:
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
                logger.info(f"🎥 Trying primary stream URL: {stream_url}")
                try:
                    response = requests.get(stream_url, auth=auth, headers=headers, timeout=10, stream=True)
                    if response.status_code == 200:
                        logger.info(f"✅ Primary stream URL successful: {stream_url}")
                        return _stream_response(response)
                except Exception as e:
                    logger.warning(f"❌ Primary stream URL failed: {e}")
            else:
                logger.info(f"🎥 Primary path is snapshot ({stream_path}), trying MJPEG stream URLs first")
            
            for i, alt_url in enumerate(alternative_urls, 1):
                try:
                    logger.info(f"🎥 Trying alternative URL {i}/{len(alternative_urls)}: {alt_url}")
                    response = requests.get(alt_url, auth=auth, headers=headers, timeout=10, stream=True)
                    if response.status_code == 200:
                        logger.info(f"✅ Alternative URL successful: {alt_url}")
                        return _stream_response(response)
                except Exception as e:
                    logger.warning(f"❌ Alternative URL {i} failed {alt_url}: {e}")
                    continue
            
            return jsonify({'success': False, 'error': 'Kamera stream alınamadı'}), 404
            
        except Exception as e:
            logger.error(f"Proxy camera stream error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

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
                    logger.warning(f"Snapshot URL failed {url}: {e}")
                    continue
            
            # Hiçbiri çalışmazsa hata döndür
            return jsonify({'success': False, 'error': 'Kamera snapshot alınamadı'}), 404
            
        except Exception as e:
            logger.error(f"Proxy camera snapshot error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/groups', methods=['GET'])
    def get_camera_groups(company_id):
        """Kamera gruplarını getir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            # Örnek kamera grupları
            groups = [
                {
                    'group_id': 'GRP_001',
                    'name': 'Ana Giriş',
                    'location': 'Bina A - Zemin Kat',
                    'camera_count': 3,
                    'active_cameras': 3,
                    'group_type': 'entrance',
                    'created_at': '2025-01-01 10:00:00'
                },
                {
                    'group_id': 'GRP_002',
                    'name': 'İnşaat Alanı',
                    'location': 'Dış Alan - Kuzey',
                    'camera_count': 5,
                    'active_cameras': 4,
                    'group_type': 'work_area',
                    'created_at': '2025-01-01 11:00:00'
                },
                {
                    'group_id': 'GRP_003',
                    'name': 'Depo & Yükleme',
                    'location': 'Bina B - Arka',
                    'camera_count': 2,
                    'active_cameras': 2,
                    'group_type': 'storage',
                    'created_at': '2025-01-01 12:00:00'
                }
            ]
            
            return jsonify({'success': True, 'groups': groups})
            
        except Exception as e:
            print(f"❌ Camera groups error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/groups', methods=['POST'])
    def create_camera_group(company_id):
        """Yeni kamera grubu oluştur"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            if not data or not all(k in data for k in ['name', 'location', 'group_type']):
                return jsonify({'success': False, 'error': 'Grup adı, lokasyon ve tür gerekli'}), 400
            
            # Grup ID oluştur
            import uuid
            group_id = f"GRP_{uuid.uuid4().hex[:8].upper()}"
            
            return jsonify({
                'success': True,
                'message': 'Kamera grubu oluşturuldu',
                'group_id': group_id,
                'name': data['name']
            })
            
        except Exception as e:
            print(f"❌ Create camera group error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/group', methods=['PUT'])
    def assign_camera_to_group(company_id, camera_id):
        """Kamerayı gruba ata"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            group_id = data.get('group_id')
            
            if not group_id:
                return jsonify({'success': False, 'error': 'Grup ID gerekli'}), 400
            
            return jsonify({
                'success': True,
                'message': 'Kamera gruba atandı',
                'camera_id': camera_id,
                'group_id': group_id
            })
            
        except Exception as e:
            print(f"❌ Assign camera to group error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

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
                from src.smartsafe.integrations.cameras.camera_integration_manager import ProfessionalCameraManager
                
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

    @bp.route('/api/company/<company_id>/cameras/model-database', methods=['GET'])
    def get_camera_model_database(company_id):
        """Kamera modeli veritabanını getir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            try:
                from src.smartsafe.utils.camera_model_database import get_camera_database
                
                db = get_camera_database()
                models = {}
                
                for model_id in db.get_all_models():
                    model_info = db.get_model_info(model_id)
                    models[model_id] = {
                        'name': model_info.name,
                        'manufacturer': model_info.manufacturer,
                        'features': model_info.features,
                        'ports': model_info.ports,
                        'paths': model_info.paths
                    }
                
                return jsonify({
                    'success': True,
                    'models': models,
                    'total_models': len(models)
                })
                
            except Exception as e:
                logger.error(f"❌ Model database error: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Model veritabanı hatası: {str(e)}'
                }), 500
            
        except Exception as e:
            logger.error(f"❌ Model database API error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>', methods=['GET'])
    def get_camera_details(company_id, camera_id):
        """Kamera detaylarını getir"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            # Kamera detaylarını veritabanından al
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            return jsonify({
                'success': True,
                'camera': camera
            })
            
        except Exception as e:
            logger.error(f"❌ Kamera detayları hatası: {e}")
            return jsonify({'success': False, 'error': 'Kamera detayları alınamadı'}), 500

    # Kamera silme API endpoint'i
    @bp.route('/api/company/<company_id>/cameras/<camera_id>', methods=['DELETE'])
    def delete_camera(company_id, camera_id):
        """Kamera silme API endpoint'i"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            logger.info(f"🗑️ Deleting camera: {camera_id} for company: {company_id}")
            
            # Önce kameranın var olup olmadığını kontrol et
            camera_exists = api.db.get_camera_by_id(camera_id, company_id)
            if not camera_exists:
                return jsonify({
                    'success': False,
                    'message': 'Kamera bulunamadı veya zaten silinmiş'
                }), 404
            
            # Veritabanından kamerayı sil
            success = api.db.delete_camera(camera_id, company_id)
            
            if not success:
                return jsonify({
                    'success': False,
                    'message': 'Kamera silinemedi'
                }), 400
            
            # Kamera yöneticisinden kamerayı ayır
            try:
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
                camera_manager = get_camera_manager()
                
                # Kamerayı bağlantıdan ayır
                disconnect_result = camera_manager.disconnect_camera(camera_id)
                logger.info(f"🔌 Kamera bağlantısı kesildi: {disconnect_result}")
                    
            except ImportError:
                logger.info("⚠️ Enterprise camera manager bulunamadı, sadece veritabanından silindi")
            
            return jsonify({
                'success': True,
                'message': f'Kamera {camera_id} başarıyla silindi',
                'camera_id': camera_id
            })
                
        except Exception as e:
            logger.error(f"❌ Camera deletion failed: {e}")
            return jsonify({
                'success': False,
                'message': f'Kamera silinirken hata oluştu: {str(e)}'
            }), 500

    # Kamera düzenleme API endpoint'i
    @bp.route('/api/company/<company_id>/cameras/<camera_id>', methods=['PUT'])
    def update_camera(company_id, camera_id):
        """Kamera düzenleme API endpoint'i"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Geçersiz oturum'}), 401
            
            data = request.get_json()
            logger.info(f"✏️ Updating camera: {camera_id} for company: {company_id}")
            
            logger.info(f"📝 Received data: {data}")
            
            # Database'de kamerayı güncelle - frontend field names'i kullan
            camera_data = {
                'name': data.get('camera_name', data.get('name', '')),
                'location': data.get('camera_location', data.get('location', '')),
                'ip_address': data.get('camera_ip', data.get('ip_address', '')),
                'port': data.get('camera_port', data.get('port', 8080)),
                'protocol': data.get('camera_protocol', data.get('protocol', 'http')),
                'stream_path': data.get('camera_path', data.get('stream_path', '/video')),
                'username': data.get('camera_username', data.get('username', '')),
                'password': data.get('camera_password', data.get('password', ''))
            }
            
            logger.info(f"📝 Processed camera data: {camera_data}")
            
            # Database update
            success = api.db.update_camera(camera_id, company_id, camera_data)
            
            if not success:
                return jsonify({
                    'success': False,
                    'message': 'Veritabanında kamera güncellenemedi'
                }), 500
            
            try:
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
                camera_manager = get_camera_manager()
                
                # Kamera konfigürasyonunu güncelle
                if camera_id in camera_manager.camera_configs:
                    config = camera_manager.camera_configs[camera_id]
                    
                    if camera_data['name']:
                        config.name = camera_data['name']
                    if camera_data['ip_address']:
                        config.connection_url = f"{camera_data['protocol']}://{camera_data['ip_address']}:{camera_data['port']}{camera_data['stream_path']}"
                    
                    # Resolution ve FPS güncelleme (eğer varsa)
                    if 'resolution' in data:
                        res_parts = data['resolution'].split('x')
                        if len(res_parts) == 2:
                            config.resolution = (int(res_parts[0]), int(res_parts[1]))
                    
                    if 'fps' in data:
                        config.fps = int(data['fps'])
                
                return jsonify({
                    'success': True,
                    'message': 'Kamera başarıyla güncellendi',
                    'camera_id': camera_id,
                    'updated_fields': list(camera_data.keys())
                })
                    
            except ImportError:
                # Fallback: Sadece database güncellemesi
                return jsonify({
                    'success': True,
                    'message': 'Kamera başarıyla güncellendi',
                    'camera_id': camera_id,
                    'updated_fields': list(camera_data.keys())
                })
                
        except Exception as e:
            logger.error(f"❌ Camera update failed: {e}")
            return jsonify({
                'success': False,
                'message': f'Kamera güncellenirken hata oluştu: {str(e)}'
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
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
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

    @bp.route('/company/<company_id>/cameras', methods=['GET'])
    def camera_management(company_id):
        """Kamera yönetimi sayfası - Yeni Geliştirilmiş Sistem"""
        user_data = api.validate_session()
        if not user_data or user_data['company_id'] != company_id:
            return redirect(f'/company/{company_id}/login')
        
        return render_template('camera_management.html', 
                                    company_id=company_id, 
                                    user_data=user_data)

    @bp.route('/api/company/<company_id>/ppe-config', methods=['PUT'])
    def update_ppe_config(company_id):
        """Update company PPE configuration"""
        try:
            # Session kontrolü
            if not api.validate_session():
                return jsonify({'success': False, 'error': 'Oturum geçersiz'}), 401
            
            if session.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 403
            
            data = request.json
            required_ppe = data.get('required_ppe', [])
            optional_ppe = data.get('optional_ppe', [])
            confidence_threshold = data.get('confidence_threshold', 0.6)
            detection_interval = data.get('detection_interval', 3)

            
            # Geçerli PPE türleri - tam liste (24 tane) + Eski kayıtlar için uyumluluk
            valid_ppe_types = [
                'helmet', 'safety_vest', 'safety_shoes', 'gloves', 'glasses', 'hairnet',
                'face_mask', 'apron', 'safety_suit', 'chemical_suit', 'respiratory_protection',
                'special_gloves', 'insulated_gloves', 'dielectric_boots', 'arc_flash_suit',
                'ear_protection', 'life_jacket', 'marine_helmet', 'waterproof_shoes',
                'aviation_helmet', 'reflective_vest', 'aviation_shoes', 'safety_harness',
                'safety_glasses'
            ]
            
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
            
            # Validation
            if not required_ppe and not optional_ppe:
                return jsonify({'success': False, 'error': 'En az bir PPE türü seçmelisiniz'}), 400
            
            # PPE türlerini validate et ve eski kayıtları dönüştür
            all_ppe = required_ppe + optional_ppe
            normalized_ppe = []
            
            for ppe_type in all_ppe:
                # Eski kayıtları yeni formata dönüştür
                if ppe_type in ppe_type_mapping:
                    normalized_ppe.append(ppe_type_mapping[ppe_type])
                    logger.info(f"🔄 PPE türü dönüştürüldü: {ppe_type} → {ppe_type_mapping[ppe_type]}")
                elif ppe_type in valid_ppe_types:
                    normalized_ppe.append(ppe_type)
                else:
                    return jsonify({'success': False, 'error': f'Geçersiz PPE türü: {ppe_type}'}), 400
            
            # Normalize edilmiş PPE'leri güncelle
            required_ppe = [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in required_ppe]
            optional_ppe = [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in optional_ppe]
            
            # Duplicate kontrolü
            if set(required_ppe) & set(optional_ppe):
                return jsonify({'success': False, 'error': 'Bir PPE türü hem zorunlu hem opsiyonel olamaz'}), 400
            
            # PPE konfigürasyonu oluştur
            ppe_config = {
                'required': required_ppe,
                'optional': optional_ppe
            }
            
            # Compliance ayarları
            compliance_settings = {
                'confidence_threshold': float(confidence_threshold),
                'detection_interval': int(detection_interval),
                'updated_at': datetime.now().isoformat()
            }
            
            # Database güncelleme
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            # Eski PPE türlerini temizle ve yeni formata dönüştür
            cleaned_ppe_config = {
                'required': [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in ppe_config['required']],
                'optional': [ppe_type_mapping.get(ppe, ppe) if ppe in ppe_type_mapping else ppe for ppe in ppe_config['optional']]
            }
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                UPDATE companies 
                SET required_ppe = {placeholder},
                    ppe_requirements = {placeholder},
                    compliance_settings = {placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder}
            ''', (json.dumps(cleaned_ppe_config), json.dumps(cleaned_ppe_config), json.dumps(compliance_settings), company_id))
            
            if cursor.rowcount == 0:
                conn.close()
                return jsonify({'success': False, 'error': 'Şirket bulunamadı'}), 404
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ PPE config updated for company {company_id}: {len(cleaned_ppe_config['required'])} required, {len(cleaned_ppe_config['optional'])} optional")
            
            return jsonify({
                'success': True,
                'message': 'PPE konfigürasyonu başarıyla güncellendi',
                'config': {
                    'required': cleaned_ppe_config['required'],
                    'optional': cleaned_ppe_config['optional'],
                    'settings': compliance_settings
                }
            })
            
        except Exception as e:
            logger.error(f"❌ PPE config güncelleme hatası: {e}")
            return jsonify({'success': False, 'error': 'Güncelleme başarısız'}), 500

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
                
                conn.close()
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
                conn.close()
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
                from src.smartsafe.integrations.cameras.camera_discovery import IPCameraDiscovery
                discovery = IPCameraDiscovery()
                discovery_result = discovery.scan_network(network_range, timeout=2)
                result['discovery_result'] = discovery_result
                
                # Step 2: Sync discovered cameras to database
                if discovery_result.get('cameras'):
                    from src.smartsafe.database.database_adapter import get_camera_discovery_manager
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
                from src.smartsafe.database.database_adapter import get_camera_discovery_manager
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

    return bp
