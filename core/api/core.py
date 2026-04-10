"""
SmartSafe AI - Core Blueprint
Landing page, app home, pricing & contact endpoints
"""

from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('core', __name__)

    @bp.route('/api/status', methods=['GET'])
    def system_status():
        """System status status endpoint"""
        return jsonify({
            'status': 'operational',
            'api': 'SmartSafe AI SaaS Engine',
            'mode': 'headless'
        })

    return bp
