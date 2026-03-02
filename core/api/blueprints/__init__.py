"""
SmartSafe API Blueprints
Route modules split from the monolithic smartsafe_saas_api.py
"""

from api.blueprints.health import create_blueprint as create_health_bp
from api.blueprints.core import create_blueprint as create_core_bp
from api.blueprints.auth import create_blueprint as create_auth_bp
from api.blueprints.admin import create_blueprint as create_admin_bp
from api.blueprints.alert import create_blueprint as create_alert_bp
from api.blueprints.dvr import create_blueprint as create_dvr_bp
from api.blueprints.camera import create_blueprint as create_camera_bp
from api.blueprints.detection import create_blueprint as create_detection_bp
from api.blueprints.report import create_blueprint as create_report_bp
from api.blueprints.subscription import create_blueprint as create_subscription_bp


def register_all_blueprints(api):
    """Register all blueprints with the Flask app via the API server instance."""
    blueprints = [
        create_health_bp(api),
        create_core_bp(api),
        create_auth_bp(api),
        create_admin_bp(api),
        create_alert_bp(api),
        create_dvr_bp(api),
        create_camera_bp(api),
        create_detection_bp(api),
        create_report_bp(api),
        create_subscription_bp(api),
    ]
    for bp in blueprints:
        api.app.register_blueprint(bp)
