# PPE Detection Utilities Package
"""
Utility functions and classes for PPE Detection System
"""

# Core utilities - always available
from .data_utils import *
from .detection_utils import *
from .tracking_utils import *
from .alert_utils import *

# Optional utilities - lazy loaded to avoid startup issues
def get_visualization_utils():
    """Get visualization utilities when needed"""
    try:
        from . import visualization_utils
        return visualization_utils
    except ImportError:
        return None

def get_secure_db_connector():
    """Get secure DB connector when needed"""
    try:
        from . import secure_database_connector
        return secure_database_connector.get_secure_db_connector()
    except ImportError:
        return None

__version__ = "1.0.0"
__author__ = "PPE Detection Team" 