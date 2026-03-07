#!/usr/bin/env python3
"""
SmartSafe AI — ONVIF Blueprint
API routes for ONVIF device discovery, connection testing, and camera auto-provisioning.
"""

from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('onvif', __name__)

    # =========================================================================
    # ONVIF DISCOVERY
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/discover', methods=['POST'])
    def onvif_discover(company_id):
        """
        Discover ONVIF devices on the local network.

        Request body (optional):
            { "timeout": 4.0, "network_range": "192.168.1.0/24" }

        Returns list of discovered devices.
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            data = request.get_json(silent=True) or {}
            timeout = data.get('timeout', 4.0)
            network_range = data.get('network_range', None)

            devices = manager.discover_devices(
                timeout=float(timeout),
                network_range=network_range,
            )

            result = {
                'success': True,
                'devices': devices,
                'total_count': len(devices),
            }

            if not devices:
                result['warning'] = (
                    'ONVIF multicast discovery hiçbir cihaz bulamadı. '
                    'Kurumsal ağlarda multicast genellikle kapalıdır veya '
                    'kamera ağı VLAN ile izole edilmiş olabilir. '
                    'Alternatif: IT ekibinizden kamera IP listesini alın ve '
                    '"batch-provision" endpoint\'ini kullanarak toplu ekleyin. '
                    f'Endpoint: POST /api/company/{company_id}/cameras/batch-provision'
                )

            return jsonify(result)
        except Exception as e:
            logger.error(f"❌ ONVIF discover error: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'fallback_suggestion': (
                    'ONVIF keşfi başarısız oldu. Kurumsal ağlarda bu yaygındır. '
                    'IT ekibinden kamera IP listesi alarak '
                    f'POST /api/company/{company_id}/cameras/batch-provision '
                    'endpoint\'ini kullanabilirsiniz.'
                )
            }), 500

    # =========================================================================
    # DEVICE INFO
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/device/<ip>', methods=['GET'])
    def onvif_device_info(company_id, ip):
        """
        Get ONVIF device information.

        Query params: port (default 80), username, password
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            port = request.args.get('port', 80, type=int)
            username = request.args.get('username', 'admin')
            password = request.args.get('password', 'admin')

            info = manager.get_device_info(ip, port, username, password)

            return jsonify({
                'success': True,
                'device': info,
            })
        except Exception as e:
            logger.error(f"❌ ONVIF device info error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # PROFILES & STREAM URI
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/profiles/<ip>', methods=['GET'])
    def onvif_profiles(company_id, ip):
        """Get media profiles for an ONVIF device."""
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            port = request.args.get('port', 80, type=int)
            username = request.args.get('username', 'admin')
            password = request.args.get('password', 'admin')

            profiles = manager.get_profiles(ip, port, username, password)

            return jsonify({
                'success': True,
                'profiles': profiles,
                'total_count': len(profiles),
            })
        except Exception as e:
            logger.error(f"❌ ONVIF profiles error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/api/company/<company_id>/onvif/stream-uri/<ip>', methods=['GET'])
    def onvif_stream_uri(company_id, ip):
        """
        Get RTSP stream URI directly from the ONVIF device.

        Query params: port, username, password, profile_index (default 0)
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            port = request.args.get('port', 80, type=int)
            username = request.args.get('username', 'admin')
            password = request.args.get('password', 'admin')
            profile_index = request.args.get('profile_index', 0, type=int)

            uri = manager.get_stream_uri(ip, port, username, password, profile_index)

            if uri:
                return jsonify({'success': True, 'stream_uri': uri})
            else:
                return jsonify({'success': False, 'error': 'Stream URI alınamadı'}), 404

        except Exception as e:
            logger.error(f"❌ ONVIF stream-uri error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # NVR CHANNEL ENUMERATION
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/channels/<ip>', methods=['GET'])
    def onvif_channels(company_id, ip):
        """
        Enumerate all channels on an NVR/DVR via ONVIF.

        Returns list of channels with stream URIs — ready to use.
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            port = request.args.get('port', 80, type=int)
            username = request.args.get('username', 'admin')
            password = request.args.get('password', 'admin')

            channels = manager.enumerate_channels(ip, port, username, password)

            return jsonify({
                'success': True,
                'channels': channels,
                'total_count': len(channels),
            })
        except Exception as e:
            logger.error(f"❌ ONVIF channels error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # CONNECTION TEST
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/test', methods=['POST'])
    def onvif_test_connection(company_id):
        """
        Test ONVIF connection to a device.

        Request body: { "ip": "192.168.1.100", "port": 80, "username": "admin", "password": "..." }
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            data = request.get_json()
            if not data or 'ip' not in data:
                return jsonify({'success': False, 'error': 'IP adresi gerekli'}), 400

            result = manager.test_connection(
                ip=data['ip'],
                port=data.get('port', 80),
                username=data.get('username', 'admin'),
                password=data.get('password', 'admin'),
            )

            return jsonify(result)

        except Exception as e:
            logger.error(f"❌ ONVIF test error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # =========================================================================
    # AUTO-PROVISION: DISCOVER + ADD ALL CAMERAS
    # =========================================================================

    @bp.route('/api/company/<company_id>/onvif/auto-provision', methods=['POST'])
    def onvif_auto_provision(company_id):
        """
        Auto-discover ONVIF devices and provision them as cameras.

        This is the turnkey endpoint: one click → all cameras added.

        Request body: { "username": "admin", "password": "...", "timeout": 4.0 }
        """
        user_data = api.validate_session()
        if not user_data:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            manager = get_onvif_manager()

            data = request.get_json() or {}
            username = data.get('username', 'admin')
            password = data.get('password', 'admin')
            timeout = data.get('timeout', 4.0)
            network_range = data.get('network_range', None)

            # Step 1: Discover
            devices = manager.discover_devices(
                timeout=float(timeout),
                network_range=network_range,
            )

            provisioned = []
            errors = []

            for device in devices:
                ip = device['ip']
                port = device.get('port', 80)

                try:
                    # Step 2: Get channels for each device
                    channels = manager.enumerate_channels(ip, port, username, password)

                    if not channels:
                        # Single camera (not NVR) — get a single stream URI
                        uri = manager.get_stream_uri(ip, port, username, password)
                        if uri:
                            channels = [{
                                'channel_number': 1,
                                'name': f"{device.get('manufacturer', 'Camera')} @ {ip}",
                                'stream_uri': uri,
                                'width': 0,
                                'height': 0,
                            }]

                    for ch in channels:
                        if not ch.get('stream_uri'):
                            continue

                        camera_name = ch.get('name', f"Camera {ip} Ch{ch['channel_number']}")
                        camera_data = {
                            'name': camera_name,
                            'ip_address': ip,
                            'port': port,
                            'username': username,
                            'rtsp_url': ch['stream_uri'],
                            'camera_type': 'onvif',
                            'channel_number': ch['channel_number'],
                            'resolution': f"{ch.get('width', 0)}x{ch.get('height', 0)}",
                            'manufacturer': device.get('manufacturer', 'Unknown'),
                            'model': device.get('model', 'Unknown'),
                            'onvif_port': port,
                            'status': 'active',
                        }

                        # Add to database
                        try:
                            api.ensure_database_initialized()
                            camera_id = api.db.add_camera(company_id, camera_data)
                            camera_data['camera_id'] = camera_id
                            provisioned.append(camera_data)
                            logger.info(
                                f"✅ ONVIF auto-provision: {camera_name} eklendi (ID: {camera_id})"
                            )
                        except Exception as db_err:
                            errors.append({
                                'ip': ip,
                                'channel': ch['channel_number'],
                                'error': str(db_err),
                            })

                except Exception as dev_err:
                    errors.append({'ip': ip, 'error': str(dev_err)})

            result = {
                'success': True,
                'provisioned': provisioned,
                'provisioned_count': len(provisioned),
                'errors': errors,
                'discovered_devices': len(devices),
            }

            if not devices:
                result['warning'] = (
                    'ONVIF auto-discovery hiçbir cihaz bulamadı. '
                    'Bunun en sık sebebi: kurumsal ağlarda multicast kapalıdır '
                    'veya kamera ağı VLAN ile izole edilmiştir. '
                    'Çözüm: IT ekibinden kamera IP listesini alın ve '
                    f'"batch-provision" endpoint\'ini kullanın: '
                    f'POST /api/company/{company_id}/cameras/batch-provision'
                )
            elif not provisioned and errors:
                result['warning'] = (
                    'Cihazlar bulundu fakat kamera eklenemedi. '
                    'Kullanıcı adı/şifre doğru olduğundan emin olun. '
                    'Alternatif olarak batch-provision endpoint\'ini deneyebilirsiniz.'
                )

            return jsonify(result)

        except Exception as e:
            logger.error(f"❌ ONVIF auto-provision error: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'fallback_suggestion': (
                    'ONVIF otomatik provizyon başarısız oldu. '
                    'Manuel IP listesi ile toplu ekleme yapabilirsiniz: '
                    f'POST /api/company/{company_id}/cameras/batch-provision'
                )
            }), 500

    return bp
