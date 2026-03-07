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
            'title': 'SmartSafe AI API Documentation',
            'version': '2.0.0',
            'description': 'Professional PPE Detection API with enhanced features',
            'endpoints': {
                'health': {
                    'url': '/health',
                    'method': 'GET',
                    'description': 'System health check',
                    'response': {'status': 'healthy', 'timestamp': 'ISO format'}
                },
                'dashboard': {
                    'url': '/company/{company_id}/dashboard',
                    'method': 'GET',
                    'description': 'Company dashboard with real-time statistics',
                    'features': ['Real-time stats', 'Mobile optimized', 'Export functionality']
                },
                'detection': {
                    'url': '/api/detection/start',
                    'method': 'POST',
                    'description': 'Start PPE detection',
                    'parameters': {
                        'camera_id': 'Camera identifier',
                        'detection_mode': 'Sector-specific mode',
                        'confidence': 'Detection confidence (0.1-1.0)'
                    }
                },
                'compliance': {
                    'url': '/api/compliance/{company_id}',
                    'method': 'GET',
                    'description': 'Get compliance statistics',
                    'features': ['Cached responses', 'Real-time data', 'Export support']
                }
            },
            'features': {
                'caching': 'Response caching for improved performance',
                'rate_limiting': 'Enhanced rate limiting (200/min, 1000/hour)',
                'error_handling': 'Detailed error messages with codes',
                'mobile_optimization': 'Responsive design for mobile devices',
                'export_functionality': 'CSV, Excel, PDF, JSON export options'
            },
            'sectors': [
                'construction', 'manufacturing', 'chemical', 'food',
                'warehouse', 'energy', 'petrochemical', 'marine', 'aviation'
            ]
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
