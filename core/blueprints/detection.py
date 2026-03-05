"""
SmartSafe AI - Detection Blueprint
SH17 PPE Detection & Live Detection endpoints
"""

from flask import Blueprint, request, jsonify, session, redirect, render_template_string, Response
import logging
import os
import json
import threading
import queue
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Lazy import to avoid circular import: smartsafe_saas_api -> blueprints -> detection -> smartsafe_saas_api
def _get_detection_state():
    from core.app import (
        active_detectors,
        detection_threads,
        camera_captures,
        frame_buffers,
        detection_results,
        live_violation_state,
    )
    return {
        'active_detectors': active_detectors,
        'detection_threads': detection_threads,
        'camera_captures': camera_captures,
        'frame_buffers': frame_buffers,
        'detection_results': detection_results,
        'live_violation_state': live_violation_state,
    }


def create_blueprint(api):
    bp = Blueprint('detection', __name__)

    # =========================================================================
    # SH17 PPE DETECTION ENDPOINTS
    # =========================================================================

    @bp.route('/api/company/<company_id>/sh17/detect', methods=['POST'])
    def sh17_ppe_detection(company_id):
        """SH17 PPE Detection - 17 sınıf tespiti"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            data = request.get_json()
            image_data = data.get('image')
            sector = data.get('sector', 'base')
            confidence_threshold = data.get('confidence', 0.5)
            
            if not image_data:
                return jsonify({'error': 'Image data required'}), 400
            
            import base64
            import cv2
            import numpy as np
            
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return jsonify({'error': 'Invalid image data'}), 400
            
            if not getattr(api, 'sh17_manager', None):
                return jsonify({'success': False, 'error': 'SH17 system unavailable'}), 503
            detections = api.sh17_manager.detect_ppe(image, sector, confidence_threshold)
            
            return jsonify({
                'success': True,
                'detections': detections,
                'sector': sector,
                'confidence_threshold': confidence_threshold,
                'total_detections': len(detections)
            })
            
        except Exception as e:
            logger.error(f"❌ SH17 detection error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/sh17/compliance', methods=['POST'])
    def sh17_compliance_analysis(company_id):
        """SH17 Compliance Analysis - Sektör bazlı uyumluluk"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            data = request.get_json()
            image_data = data.get('image')
            sector = data.get('sector', 'construction')
            required_ppe = data.get('required_ppe', ['helmet', 'safety_vest', 'gloves'])
            
            if not image_data:
                return jsonify({'error': 'Image data required'}), 400
            
            import base64
            import cv2
            import numpy as np
            
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return jsonify({'error': 'Invalid image data'}), 400
            
            if not getattr(api, 'sh17_manager', None):
                return jsonify({'success': False, 'error': 'SH17 system unavailable'}), 503
            
            detections = api.sh17_manager.detect_ppe(image, sector, 0.5)
            compliance_result = api.sh17_manager.analyze_compliance(detections, required_ppe)
            
            return jsonify({
                'success': True,
                'compliance': compliance_result,
                'detections': detections,
                'sector': sector,
                'required_ppe': required_ppe
            })
            
        except Exception as e:
            logger.error(f"❌ SH17 compliance analysis error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/sh17/sectors', methods=['GET'])
    def get_sh17_sectors(company_id):
        """Get available SH17 sectors"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            sectors = [
                'construction', 'manufacturing', 'chemical', 
                'food_beverage', 'warehouse_logistics', 'energy',
                'petrochemical', 'marine_shipyard', 'aviation'
            ]
            
            return jsonify({
                'success': True,
                'sectors': sectors,
                'total_sectors': len(sectors)
            })
            
        except Exception as e:
            logger.error(f"❌ Get SH17 sectors error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/sh17/performance', methods=['GET'])
    def get_sh17_performance(company_id):
        """Get SH17 model performance metrics"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            if not getattr(api, 'sh17_manager', None):
                return jsonify({'success': False, 'error': 'SH17 system unavailable'}), 503
            performance = api.sh17_manager.get_model_performance()
            
            return jsonify({
                'success': True,
                'performance': performance
            })
            
        except Exception as e:
            logger.error(f"❌ Get SH17 performance error: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/sh17/health', methods=['GET'])
    def sh17_health_check(company_id):
        """SH17 system health check"""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            if not getattr(api, 'sh17_manager', None):
                return jsonify({'success': False, 'status': 'unavailable', 'reason': 'SH17 not initialized'}), 200
            models_loaded = len(api.sh17_manager.models) > 0
            try:
                import torch as _torch
                gpu_available = _torch.cuda.is_available()
            except ImportError:
                gpu_available = False
            
            return jsonify({
                'success': True,
                'status': 'healthy',
                'models_loaded': models_loaded,
                'gpu_available': gpu_available,
                'total_models': len(api.sh17_manager.models),
                'device': str(api.sh17_manager.device)
            })
            
        except Exception as e:
            logger.error(f"❌ SH17 health check error: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # PROFESSIONAL SAAS LIVE DETECTION SYSTEM
    # =========================================================================

    @bp.route('/api/company/<company_id>/live-detection', methods=['GET'])
    def live_detection_dashboard(company_id):
        """SaaS Canlı Tespit Dashboard"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return redirect(f'/company/{company_id}/login')
            
            cameras = api.db.get_company_cameras(company_id)
            
            conn = api.db.get_connection()
            cursor = conn.cursor()
            
            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            cursor.execute(f'''
                SELECT company_name, sector, required_ppe
                FROM companies WHERE company_id = {placeholder}
            ''', (company_id,))
            
            company_data = cursor.fetchone()
            conn.close()
            
            if not company_data:
                return redirect('/')
            
            if hasattr(company_data, 'keys'):
                company_name = company_data['company_name']
                sector = company_data['sector']
                required_ppe = company_data['required_ppe']
            else:
                company_name = company_data[0]
                sector = company_data[1]
                required_ppe = company_data[2]
            
            ppe_config = []
            if required_ppe:
                try:
                    ppe_data = json.loads(required_ppe)
                    if isinstance(ppe_data, dict):
                        ppe_config = ppe_data.get('required', [])
                    else:
                        ppe_config = ppe_data
                except:
                    ppe_config = ['helmet', 'vest']
            
            return render_template_string(api.get_live_detection_template(), 
                                        company_id=company_id,
                                        company_name=company_name,
                                        sector=sector,
                                        cameras=cameras,
                                        ppe_config=ppe_config,
                                        user_data=user_data)
            
        except Exception as e:
            logger.error(f"❌ Live detection dashboard error: {e}")
            return redirect(f'/company/{company_id}/dashboard')

    @bp.route('/api/company/<company_id>/start-detection', methods=['POST'])
    def start_detection(company_id):
        """Şirket için tespit başlat - SaaS Edition"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            data = request.get_json() or {}
            camera_id = data.get('camera_id')
            detection_mode = data.get('mode', 'ppe')
            confidence = data.get('confidence', 0.5)
            
            logger.info(f"🎯 Start detection request: camera_id={camera_id}, data={data}")
            
            if not camera_id:
                logger.warning(f"⚠️ Start detection: camera_id missing in request data")
                return jsonify({'success': False, 'error': 'Kamera ID gerekli'}), 400
            
            cameras = api.db.get_company_cameras(company_id)
            camera_exists = any(cam['camera_id'] == camera_id for cam in cameras)
            
            if not camera_exists:
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            camera = api.db.get_camera_by_id(camera_id, company_id)
            if not camera:
                logger.error(f"❌ Start detection: Camera not found: {camera_id}")
                return jsonify({'success': False, 'error': 'Kamera bulunamadı'}), 404
            
            camera_status = camera.get('status', 'active')
            logger.info(f"📹 Camera status: {camera_status} for camera: {camera_id}")
            
            if camera_status == 'inactive':
                logger.warning(f"⚠️ Start detection: Camera {camera_id} is inactive")
                return jsonify({
                    'success': False, 
                    'error': 'Kamera pasif durumda. Önce kamerayı aktif yapın.',
                    'camera_status': 'inactive'
                }), 400
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            if camera_key in state['active_detectors'] and state['active_detectors'][camera_key]:
                return jsonify({'success': False, 'error': 'Kamera zaten aktif'})

            # ── Plan bazlı kamera limiti ─────────────────────────────────────
            # Şirketin aktif planından gerçek sınırı al (SaaS davranışı)
            import core.app as _api_mod
            active_count = sum(1 for v in state['active_detectors'].values() if v)

            # Şirket kaydından plan bazlı max_cameras oku
            company_info = api.db.get_company(company_id) if hasattr(api, 'db') else None
            if company_info:
                # Önce şirketin kendi max_cameras değeri
                plan_max = int(company_info.get('max_cameras') or 25)
                # Demo hesapsa demo_limits'i kontrol et
                if company_info.get('account_type') == 'demo':
                    try:
                        demo_limits = company_info.get('demo_limits')
                        if isinstance(demo_limits, str):
                            import json as _json
                            demo_limits = _json.loads(demo_limits) if demo_limits else {}
                        plan_max = int((demo_limits or {}).get('max_cameras', 2))
                    except Exception:
                        plan_max = 2  # Demo default: 2 kamera
            else:
                plan_max = getattr(_api_mod, 'MAX_CONCURRENT_CAMERAS', 25)

            # Şirkete özgün aktif sayısı (diğer şirket kamerleri sayılmaz)
            company_active = sum(
                1 for k, v in state['active_detectors'].items()
                if v and k.startswith(f"{company_id}_")
            )
            if company_active >= plan_max:
                logger.warning(f"⚠️ {company_id} kamera planı dolu: {company_active}/{plan_max}")
                return jsonify({
                    'success': False,
                    'error': f'Planınızdaki maksimum kamera sayısına ({plan_max}) ulaştınız. '
                             f'Planınızı yükseltin veya aktif bir kamerayı durdurun.',
                    'active_cameras': company_active,
                    'max_cameras': plan_max,
                    'plan': (company_info or {}).get('subscription_type', 'starter')
                }), 429

            # Aynı process'te worker'ın gördüğü dict'i set et (referans tutarlılığı)
            state['active_detectors'][camera_key] = True
            import core.app as _api_mod
            _api_mod.active_detectors[camera_key] = True
            logger.info(f"✅ active_detectors[{camera_key}] = True set before thread start")
            # Worker'ın aynı dict referansını görmesi için açıkça geçir (reloader/çift app senaryosu)
            active_detectors_ref = state['active_detectors']
            detection_thread = threading.Thread(
                target=api.saas_detection_worker,
                args=(camera_key, camera_id, company_id, detection_mode, confidence, active_detectors_ref),
                daemon=True
            )
            detection_thread.start()
            
            state['detection_threads'][camera_key] = {
                'thread': detection_thread,
                'config': {
                    'mode': detection_mode,
                    'confidence': confidence,
                    'started_at': datetime.now().isoformat()
                }
            }
            
            return jsonify({
                'success': True,
                'message': f'Kamera {camera_id} tespiti başlatıldı',
                'camera_id': camera_id,
                'detection_mode': detection_mode,
                'confidence': confidence,
                'stream_url': f'/api/company/{company_id}/camera-stream/{camera_id}'
            })
            
        except Exception as e:
            logger.error(f"❌ Detection start error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/stop-detection', methods=['POST'])
    def stop_detection(company_id):
        """Şirket için tespit durdur - Tek kamera veya tüm kameralar"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            data = request.get_json() or {}
            camera_id = data.get('camera_id')
            logger.info(f"🛑 stop_detection called: company_id={company_id}, camera_id={camera_id}")
            
            if camera_id:
                camera_key = f"{company_id}_{camera_id}"
                state = _get_detection_state()
                if camera_key in state['active_detectors'] and state['active_detectors'][camera_key]:
                    logger.info(f"🛑 Stopping detection for camera: {camera_id}")
                    state['active_detectors'][camera_key] = False
                    
                    if camera_key in state['detection_threads']:
                        del state['detection_threads'][camera_key]
                    
                    if camera_key in state['camera_captures'] and state['camera_captures'][camera_key] is not None:
                        try:
                            state['camera_captures'][camera_key].release()
                        except: pass
                        del state['camera_captures'][camera_key]
                    
                    if camera_key in state['frame_buffers']:
                        del state['frame_buffers'][camera_key]
                    
                    logger.info(f"✅ Detection stopped for camera: {camera_id}")
                    return jsonify({'success': True, 'message': f'Kamera {camera_id} detection durduruldu'})
                else:
                    return jsonify({'success': True, 'message': f'Kamera {camera_id} zaten durdurulmuş'})
            else:
                state = _get_detection_state()
                keys_to_remove = []
                for camera_key in list(state['active_detectors'].keys()):
                    if camera_key.startswith(f"{company_id}_"):
                        state['active_detectors'][camera_key] = False
                        keys_to_remove.append(camera_key)
                
                for camera_key in keys_to_remove:
                    if camera_key in state['camera_captures'] and state['camera_captures'][camera_key] is not None:
                        try:
                            state['camera_captures'][camera_key].release()
                        except: pass
                        del state['camera_captures'][camera_key]
                    if camera_key in state['frame_buffers']:
                        del state['frame_buffers'][camera_key]
                    if camera_key in state['detection_threads']:
                        del state['detection_threads'][camera_key]
                
                return jsonify({'success': True, 'message': 'Tüm kameralar durduruldu'})
        except Exception as e:
            logger.error(f"❌ Stop detection error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/detection-status/<camera_id>')
    def detection_status(company_id, camera_id):
        """Tespit durumu API - Optimized with error handling"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            try:
                is_active = camera_key in state['active_detectors'] and state['active_detectors'].get(camera_key, False)
            except Exception:
                is_active = False
            
            try:
                thread_info = state['detection_threads'].get(camera_key, {})
                if 'thread' in thread_info:
                    thread_info = {k: v for k, v in thread_info.items() if k != 'thread'}
            except Exception:
                thread_info = {}
            
            recent_results = []
            try:
                if camera_key in state['detection_results']:
                    queue_obj = state['detection_results'][camera_key]
                    max_items = 10
                    while len(recent_results) < max_items:
                        try:
                            result = queue_obj.get_nowait()
                            recent_results.append(result)
                        except:
                            break
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'camera_id': camera_id,
                'is_active': is_active,
                'thread_info': thread_info,
                'recent_results': recent_results[-10:] if recent_results else []
            })
            
        except Exception as e:
            logger.error(f"❌ Detection status error: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error',
                'camera_id': camera_id
            }), 500

    @bp.route('/api/company/<company_id>/live-stats')
    def live_stats(company_id):
        """Canlı istatistikler API"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'error': 'Yetkisiz erişim'}), 401
            
            active_cameras = []
            state = _get_detection_state()
            for key, active in state['active_detectors'].items():
                if key.startswith(f"{company_id}_") and active:
                    camera_id = key.split('_', 1)[1]
                    active_cameras.append(camera_id)
            
            conn = api.db.get_connection()
            cursor = conn.cursor()

            placeholder = api.db.get_placeholder() if hasattr(api.db, 'get_placeholder') else '?'
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()

            cursor.execute(f'''
                SELECT COUNT(*) FROM detections
                WHERE company_id = {placeholder}
                AND timestamp >= {placeholder}
            ''', (company_id, one_hour_ago))

            recent_detections = cursor.fetchone()
            recent_detections = recent_detections[0] if recent_detections else 0

            cursor.execute(f'''
                SELECT COUNT(*) FROM violations
                WHERE company_id = {placeholder}
                AND timestamp >= {placeholder}
            ''', (company_id, one_hour_ago))

            recent_violations = cursor.fetchone()
            recent_violations = recent_violations[0] if recent_violations else 0

            compliance_rate = 0
            if recent_detections > 0:
                compliance_rate = max(0, (recent_detections - recent_violations) / recent_detections * 100)

            conn.close()
            
            return jsonify({
                'success': True,
                'stats': {
                    'active_cameras': len(active_cameras),
                    'active_camera_ids': active_cameras,
                    'recent_detections': recent_detections,
                    'recent_violations': recent_violations,
                    'compliance_rate': round(compliance_rate, 1),
                    'system_status': 'active' if active_cameras else 'idle',
                    'timestamp': datetime.now().isoformat()
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Live stats error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/detection-results/<camera_id>')
    def get_detection_results(company_id, camera_id):
        """Detection sonuçlarını al - Production uyumlu"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            if camera_key in state['detection_results'] and not state['detection_results'][camera_key].empty():
                try:
                    latest_result = state['detection_results'][camera_key].get_nowait()
                    
                    return jsonify({
                        'success': True,
                        'result': {
                            'total_people': latest_result.get('total_people', 0),
                            'compliance_rate': latest_result.get('compliance_rate', 0),
                            'violations': latest_result.get('violations', []),
                            'processing_time': latest_result.get('processing_time', 0),
                            'processing_time_ms': latest_result.get('processing_time_ms', 0),
                            'detection_count': latest_result.get('detection_count', 0),
                            'frame_count': latest_result.get('frame_count', 0),
                            'timestamp': latest_result.get('timestamp', ''),
                            'detection_mode': latest_result.get('detection_mode', 'general')
                        }
                    })
                except queue.Empty:
                    return jsonify({
                        'success': True,
                        'result': {
                            'total_people': 0,
                            'compliance_rate': 100,
                            'violations': [],
                            'processing_time': 0,
                            'processing_time_ms': 0,
                            'detection_count': 0,
                            'frame_count': 0,
                            'timestamp': datetime.now().isoformat(),
                            'detection_mode': 'general'
                        },
                        'message': 'Henüz tespit sonucu yok'
                    })
            else:
                return jsonify({
                    'success': True,
                    'result': {
                        'total_people': 0,
                        'compliance_rate': 100,
                        'violations': [],
                        'processing_time': 0,
                        'processing_time_ms': 0,
                        'detection_count': 0,
                        'frame_count': 0,
                        'timestamp': datetime.now().isoformat(),
                        'detection_mode': 'general'
                    },
                    'message': 'Kamera aktif değil veya sonuç yok'
                })
        except Exception as e:
            logger.error(f"❌ Detection results endpoint hatası: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/video-feed/<camera_id>')
    def get_video_feed(company_id, camera_id):
        """Video feed endpoint"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            ad_ref = state['active_detectors']
            
            return Response(
                api.generate_saas_frames(camera_key, company_id, camera_id, active_detectors_ref=ad_ref),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
                
        except Exception as e:
            logger.error(f"❌ Video feed hatası: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # LIVE DETECTION DASHBOARD API ENDPOINTS
    # =========================================================================

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/detection/history', methods=['GET'])
    def get_camera_detection_history(company_id, camera_id):
        """Get detection history for a camera"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            limit = request.args.get('limit', 100, type=int)
            
            from core.database.database_adapter import get_db_adapter
            db = get_db_adapter()
            results = db.get_camera_detection_results(camera_id, company_id, limit)
            
            return jsonify({
                'success': True,
                'camera_id': camera_id,
                'results': results,
                'total_count': len(results)
            })
            
        except Exception as e:
            logger.error(f"❌ Get detection history error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/detection/latest', methods=['GET'])
    def get_camera_latest_detection(company_id, camera_id):
        """Get latest detection result for a camera - Optimized with error handling"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            if camera_key in state['detection_results'] and not state['detection_results'][camera_key].empty():
                temp = []
                try:
                    while True:
                        r = state['detection_results'][camera_key].get_nowait()
                        temp.append(r)
                except queue.Empty:
                    pass
                if temp:
                    latest = temp[-1]
                    for r in temp[-5:]:
                        try:
                            state['detection_results'][camera_key].put_nowait(r)
                        except queue.Full:
                            break
                    return jsonify({
                        'success': True,
                        'camera_id': camera_id,
                        'detection': latest
                    })
            
            try:
                from core.database.database_adapter import get_db_adapter
                db = get_db_adapter()
                
                if not api.ensure_database_initialized():
                    return jsonify({
                        'success': False,
                        'error': 'Database not available',
                        'camera_id': camera_id
                    }), 503
                
                result = db.get_latest_camera_detection(camera_id, company_id)
                
                if result:
                    return jsonify({
                        'success': True,
                        'camera_id': camera_id,
                        'detection': result
                    })
                else:
                    return jsonify({
                        'success': True,
                        'camera_id': camera_id,
                        'detection': None,
                        'message': 'No detection results found'
                    })
                    
            except Exception as db_err:
                logger.error(f"❌ Database error in get_latest_detection: {db_err}", exc_info=True)
                return jsonify({
                    'success': True,
                    'camera_id': camera_id,
                    'detection': None,
                    'message': 'Database temporarily unavailable'
                }), 200
            
        except Exception as e:
            logger.error(f"❌ Get latest detection error: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error',
                'camera_id': camera_id
            }), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/violations/active', methods=['GET'])
    def get_camera_active_violations(company_id, camera_id):
        """Get active violations for a camera (real-time list)"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401

            from core.database.database_adapter import get_db_adapter
            db = get_db_adapter()
            violations = db.get_active_violations(camera_id=camera_id, company_id=company_id)

            return jsonify({
                'success': True,
                'camera_id': camera_id,
                'count': len(violations),
                'violations': violations
            })
        except Exception as e:
            logger.error(f"❌ Get camera active violations error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/detection/stats', methods=['GET'])
    def get_company_detection_stats(company_id):
        """Get detection statistics for company"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            hours = request.args.get('hours', 24, type=int)
            
            from core.database.database_adapter import get_db_adapter
            db = get_db_adapter()
            stats = db.get_company_detection_stats(company_id, hours)
            
            return jsonify({
                'success': True,
                'company_id': company_id,
                'hours': hours,
                'stats': stats
            })
            
        except Exception as e:
            logger.error(f"❌ Get detection stats error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/cameras/<camera_id>/detection/stream', methods=['GET'])
    def get_detection_stream(company_id, camera_id):
        """Get live detection stream with overlay"""
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
            camera_key = f"{company_id}_{camera_id}"
            state = _get_detection_state()
            if state['active_detectors'].get(camera_key):
                return Response(
                    api.generate_saas_frames(camera_key, company_id, camera_id, active_detectors_ref=state['active_detectors']),
                    mimetype='multipart/x-mixed-replace; boundary=frame'
                )
            
            # Tespit kapalıyken tarayıcıyı doğrudan proxy-stream'e yönlendir.
            # Böylece sunucu kendine istek atmaz (deadlock/timeout olmaz); Kamera Detayları ile aynı akış kullanılır.
            proxy_stream_path = f"/api/company/{company_id}/cameras/{camera_id}/proxy-stream"
            logger.info(f"🔗 Detection kapalı, proxy-stream'e yönlendiriliyor: {proxy_stream_path}")
            return redirect(proxy_stream_path)
            
        except Exception as e:
            logger.error(f"❌ Detection stream endpoint error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    return bp
