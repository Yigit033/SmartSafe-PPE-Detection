"""
SmartSafe API Blueprints
Route modules split from the monolithic smartsafe_saas_api.py
"""

from blueprints.health import create_blueprint as create_health_bp
from blueprints.core import create_blueprint as create_core_bp
from blueprints.auth import create_blueprint as create_auth_bp
from blueprints.admin import create_blueprint as create_admin_bp
from blueprints.alert import create_blueprint as create_alert_bp
from blueprints.dvr import create_blueprint as create_dvr_bp
from blueprints.camera import create_blueprint as create_camera_bp
from blueprints.detection import create_blueprint as create_detection_bp
from blueprints.report import create_blueprint as create_report_bp
from blueprints.subscription import create_blueprint as create_subscription_bp
from blueprints.onvif import create_blueprint as create_onvif_bp


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
        create_onvif_bp(api),
    ]
    for bp in blueprints:
        api.app.register_blueprint(bp)

