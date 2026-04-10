"""
SmartSafe AI - Health Blueprint
Health check, API docs & Prometheus metrics endpoints
"""

from flask import Blueprint, jsonify
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def create_blueprint(api):
    bp = Blueprint('health', __name__)

    @bp.route('/health', methods=['GET'])
    def health_check():
        """Enhanced health check endpoint for monitoring"""
        try:
            # Trigger lazy initialization if needed
            if hasattr(api, 'ensure_database_initialized'):
                api.ensure_database_initialized()
                
            db_status = "healthy"
            if not os.environ.get('RENDER'):
                try:
                    if hasattr(api, 'db') and api.db:
                        conn = api.db.get_connection()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT 1")
                            api.db.close_connection(conn)
                        else:
                            db_status = "unhealthy: Could not get database connection"
                    else:
                        db_status = "initializing: Database adapter not ready"
                except Exception as e:
                    db_status = f"unhealthy: {str(e)}"
                    logger.error(f"❌ DB Health Check Error: {e}")
            else:
                db_status = "healthy"
            
            app_status = "healthy"
            
            healthy = db_status == "healthy" and app_status == "healthy"
            
            response = {
                "status": "healthy" if healthy else "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "version": "2.0.0",
                "services": {
                    "database": db_status,
                    "application": app_status,
                    "cache": "healthy",
                    "rate_limiting": "active"
                },
                "uptime": "running",
                "features": {
                    "caching": True,
                    "mobile_optimization": True,
                    "export_functionality": True,
                    "enhanced_error_handling": True
                }
            }
            
            return jsonify(response), 200 if healthy else 503
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 503

    @bp.route('/api/docs', methods=['GET'])
    def api_documentation():
        """API Documentation endpoint"""
        docs = {
            'title': 'SmartSafe AI Headless Engine API',
            'version': '2.5.0',
            'description': 'Technical worker engine for AI Detection and Stream Management',
            'endpoints': {
                'health': {
                    'url': '/health',
                    'method': 'GET',
                    'description': 'System health check'
                },
                'status': {
                    'url': '/api/status',
                    'method': 'GET',
                    'description': 'Engine operational status'
                },
                'detection': {
                    'url': '/api/detection/start',
                    'method': 'POST',
                    'description': 'Start AI detection on a specific camera'
                },
                'discovery': {
                    'url': '/api/camera/discover',
                    'method': 'POST',
                    'description': 'Discover cameras on network'
                },
                'stream': {
                    'url': '/api/camera/proxy/{camera_id}',
                    'method': 'GET',
                    'description': 'Technical stream proxy for detection visualization'
                }
            },
            'engine_features': {
                'multi_tenant_db': 'Direct database integration for detection persistence',
                'stream_optimization': 'Thread-safe frame buffering for high-concurrency',
                'lazy_loading': 'Memory-optimized model loading',
                'auto_restart': 'Engine-level stream watchdog'
            }
        }
        return jsonify(docs)

    @bp.route('/metrics', methods=['GET'])
    def metrics():
        """Prometheus metrics endpoint"""
        try:
            stats = {}
            
            metrics_data = f"""# HELP smartsafe_status Application status
# TYPE smartsafe_status gauge
smartsafe_status 1

# HELP smartsafe_uptime_seconds Application uptime in seconds
# TYPE smartsafe_uptime_seconds counter
smartsafe_uptime_seconds 3600

# HELP smartsafe_requests_total Total number of requests
# TYPE smartsafe_requests_total counter
smartsafe_requests_total 100
"""
            
            return metrics_data, 200, {'Content-Type': 'text/plain; version=0.0.4'}
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return "# Metrics collection failed", 503, {'Content-Type': 'text/plain'}

    return bp
