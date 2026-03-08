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

# Lazy import to avoid circular import: core/app.py -> api -> detection -> core/app.py
def _get_detection_state():
    from app import (
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
            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in start_detection")
                return jsonify({'success': False, 'error': 'Veritabanı başlatılamadı'}), 500

            # user_data = api.validate_session()
            # if not user_data or user_data.get('company_id') != company_id:
            #     return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
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
            import app as _api_mod
            active_count = sum(1 for v in state['active_detectors'].values() if v)

            # Şirket kaydından plan bazlı max_cameras oku
            company_info = api.db.get_company_info(company_id) if hasattr(api, 'db') and hasattr(api.db, 'get_company_info') else None
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
            import app as _api_mod
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

    # ── Toplu Detection Başlatma (Seçili Kameralar) ──────────────────────
    @bp.route('/api/company/<company_id>/start-detection-batch', methods=['POST'])
    def start_detection_batch(company_id):
        """Birden fazla kamera için aynı anda detection başlat."""
        try:
            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in start_detection_batch")
                return jsonify({'success': False, 'error': 'Veritabanı başlatılamadı'}), 500

            # user_data = api.validate_session()
            # if not user_data or user_data.get('company_id') != company_id:
            #     return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
            data = request.get_json() or {}
            camera_ids = data.get('camera_ids', [])
            detection_mode = data.get('mode', 'ppe')
            confidence = data.get('confidence', 0.5)
            
            if not camera_ids or not isinstance(camera_ids, list):
                return jsonify({
                    'success': False,
                    'error': '"camera_ids" listesi gerekli',
                    'expected_format': {
                        'camera_ids': ['cam_001', 'cam_002'],
                        'mode': 'ppe',
                        'confidence': 0.5
                    }
                }), 400
            
            logger.info(f"🎯 Batch detection start: {len(camera_ids)} kamera, şirket: {company_id}")
            
            # Kameraları doğrula
            cameras = api.db.get_company_cameras(company_id)
            valid_camera_ids = {cam['camera_id'] for cam in cameras}
            
            # Plan limiti kontrolü
            import app as _api_mod
            state = _get_detection_state()
            company_active = sum(
                1 for k, v in state['active_detectors'].items()
                if v and k.startswith(f"{company_id}_")
            )
            
            company_info = api.db.get_company_info(company_id) if hasattr(api, 'db') and hasattr(api.db, 'get_company_info') else None
            if company_info:
                plan_max = int(company_info.get('max_cameras') or 25)
                if company_info.get('account_type') == 'demo':
                    try:
                        demo_limits = company_info.get('demo_limits')
                        if isinstance(demo_limits, str):
                            import json as _json
                            demo_limits = _json.loads(demo_limits) if demo_limits else {}
                        plan_max = int((demo_limits or {}).get('max_cameras', 2))
                    except Exception:
                        plan_max = 2
            else:
                plan_max = getattr(_api_mod, 'MAX_CONCURRENT_CAMERAS', 25)
            
            remaining_slots = plan_max - company_active
            
            results = []
            started = 0
            
            for camera_id in camera_ids:
                # Geçerli kamera mı?
                if camera_id not in valid_camera_ids:
                    results.append({'camera_id': camera_id, 'status': 'error', 'detail': 'Kamera bulunamadı'})
                    continue
                
                camera_key = f"{company_id}_{camera_id}"
                
                # Zaten aktif mi?
                if camera_key in state['active_detectors'] and state['active_detectors'][camera_key]:
                    results.append({'camera_id': camera_id, 'status': 'already_active', 'detail': 'Zaten çalışıyor'})
                    continue
                
                # Limit aşıldı mı?
                if started >= remaining_slots:
                    results.append({'camera_id': camera_id, 'status': 'skipped', 'detail': f'Plan limiti ({plan_max}) aşıldı'})
                    continue
                
                # Kamerayı başlat
                try:
                    state['active_detectors'][camera_key] = True
                    _api_mod.active_detectors[camera_key] = True
                    
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
                    
                    started += 1
                    results.append({'camera_id': camera_id, 'status': 'started', 'detail': 'Başarıyla başlatıldı'})
                    
                except Exception as cam_err:
                    state['active_detectors'][camera_key] = False
                    _api_mod.active_detectors[camera_key] = False
                    results.append({'camera_id': camera_id, 'status': 'error', 'detail': str(cam_err)})
            
            return jsonify({
                'success': True,
                'total_requested': len(camera_ids),
                'started': started,
                'already_active': len([r for r in results if r['status'] == 'already_active']),
                'failed': len([r for r in results if r['status'] == 'error']),
                'skipped': len([r for r in results if r['status'] == 'skipped']),
                'remaining_slots': remaining_slots - started,
                'details': results,
                'detection_mode': detection_mode,
                'confidence': confidence,
            })
            
        except Exception as e:
            logger.error(f"❌ Batch detection start error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/stop-detection', methods=['POST'])
    def stop_detection(company_id):
        """Şirket için tespit durdur - Tek kamera veya tüm kameralar"""
        try:
            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                logger.error("❌ Database initialization failed in stop_detection")
                return jsonify({'success': False, 'error': 'Veritabanı başlatılamadı'}), 500

            # user_data = api.validate_session()
            # if not user_data or user_data.get('company_id') != company_id:
            #     return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
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
            # Database initialization kontrolü
            if not api.ensure_database_initialized():
                return jsonify({'success': False, 'error': 'Veritabanı başlatılamadı'}), 500

            # user_data = api.validate_session()
            # if not user_data or user_data.get('company_id') != company_id:
            #     return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
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
            # user_data = api.validate_session()
            # if not user_data or user_data.get('company_id') != company_id:
            #     return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401
            
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
            
            from database.database_adapter import get_db_adapter
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
                from database.database_adapter import get_db_adapter
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

            from database.database_adapter import get_db_adapter
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
            
            from database.database_adapter import get_db_adapter
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

    # =========================================================================
    # SSE — Real-Time Violation Feed (Phase 2.1)
    # =========================================================================

    @bp.route('/api/company/<company_id>/violations/stream', methods=['GET'])
    def violation_sse_stream(company_id):
        """Server-Sent Events endpoint — canlı ihlal bildirimleri.

        Bağlanan her browser client, aynı bağlantı üzerinden anlık ihlal
        mesajları alır.  Hem IP kamera (frame_buffers/detection_results) hem de
        DVR (dvr_ppe_manager.dvr_processor.results_queue) kaynaklarını dinler.
        """
        user_data = api.validate_session()
        if not user_data or user_data.get('company_id') != company_id:
            return jsonify({'error': 'Unauthorized'}), 401

        def event_generator():
            import json as _json
            from integrations.dvr.dvr_ppe_integration import get_dvr_ppe_manager
            dvr_ppe = get_dvr_ppe_manager()
            state = _get_detection_state()

            # Bağlantı başarılı mesajı
            yield f"data: {_json.dumps({'type': 'connected', 'company_id': company_id})}\n\n"

            while True:
                try:
                    # 1) DVR violation queue'su
                    try:
                        item = dvr_ppe.dvr_processor.results_queue.get_nowait()
                        ppe_result = item.get('ppe_result', {})
                        violations = ppe_result.get('ppe_violations', [])
                        if violations:
                            event = {
                                'type': 'violation',
                                'source': 'dvr',
                                'stream_id': item.get('stream_id'),
                                'timestamp': item.get('timestamp'),
                                'violations': violations,
                                'detection_system': item.get('detection_system', 'Klasik'),
                                'people_detected': ppe_result.get('people_detected', 0),
                                'violations_count': len(violations),
                            }
                            yield f"data: {_json.dumps(event)}\n\n"
                    except Exception:
                        pass  # Queue boş

                    # 2) IP Kamera detection_results queue'ları
                    for cam_key, q in list(state['detection_results'].items()):
                        if not cam_key.startswith(f"{company_id}_"):
                            continue
                        try:
                            result = q.get_nowait()
                            vlist = result.get('violations', [])
                            if vlist:
                                cam_id = cam_key.split('_', 1)[1]
                                event = {
                                    'type': 'violation',
                                    'source': 'camera',
                                    'camera_id': cam_id,
                                    'timestamp': result.get('timestamp'),
                                    'violations': vlist,
                                    'people_detected': result.get('total_people', 0),
                                    'violations_count': len(vlist),
                                    'compliance_rate': result.get('compliance_rate', 100),
                                }
                                yield f"data: {_json.dumps(event)}\n\n"
                        except Exception:
                            pass

                    # Heartbeat — bağlantının canlı olduğunu bildir
                    yield ": heartbeat\n\n"

                    import time as _t
                    _t.sleep(1.0)

                except GeneratorExit:
                    break
                except Exception as e:
                    logger.error(f"SSE generator error: {e}")
                    import time as _t
                    _t.sleep(2)

        return Response(
            event_generator(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',   # Nginx buffering'i devre dışı bırak
                'Connection': 'keep-alive',
            }
        )

    # =========================================================================
    # BATCH STOP (Phase 2.4)
    # =========================================================================

    @bp.route('/api/company/<company_id>/stop-detection-batch', methods=['POST'])
    def stop_detection_batch(company_id):
        """Seçili kameraları toplu durdur.

        Body: {"camera_ids": ["cam_001", "cam_002"]}
        camera_ids boş veya yok → şirketin tüm aktif kameraları durdurulur.
        """
        try:
            user_data = api.validate_session()
            if not user_data or user_data.get('company_id') != company_id:
                return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 401

            import app as _api_mod
            data = request.get_json() or {}
            camera_ids = data.get('camera_ids', [])

            state = _get_detection_state()
            stopped = []
            not_active = []
            failed = []

            # Durdurulacak kamera_key listesini belirle
            if camera_ids:
                keys_to_stop = [f"{company_id}_{cid}" for cid in camera_ids]
            else:
                keys_to_stop = [
                    k for k, v in state['active_detectors'].items()
                    if k.startswith(f"{company_id}_") and v
                ]

            for camera_key in keys_to_stop:
                cam_id = camera_key.split('_', 1)[1] if '_' in camera_key else camera_key
                try:
                    if not state['active_detectors'].get(camera_key, False):
                        not_active.append(cam_id)
                        continue

                    state['active_detectors'][camera_key] = False
                    _api_mod.active_detectors[camera_key] = False

                    if camera_key in state['camera_captures'] and state['camera_captures'][camera_key]:
                        try:
                            state['camera_captures'][camera_key].release()
                        except Exception:
                            pass
                        del state['camera_captures'][camera_key]

                    state['frame_buffers'].pop(camera_key, None)
                    state['detection_threads'].pop(camera_key, None)
                    stopped.append(cam_id)

                except Exception as err:
                    logger.error(f"❌ Batch stop error for {camera_key}: {err}")
                    failed.append(cam_id)

            logger.info(f"🛑 Batch stop: {len(stopped)} durduruldu, {len(not_active)} zaten duruyordu, {len(failed)} hata")
            return jsonify({
                'success': True,
                'stopped': stopped,
                'not_active': not_active,
                'failed': failed,
                'total_stopped': len(stopped),
            })

        except Exception as e:
            logger.error(f"❌ Batch stop error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    return bp
