#!/usr/bin/env python3
"""
SmartSafe AI - Professional Configuration Manager
Enterprise-grade configuration management with environment support
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from datetime import datetime

class Environment(Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEMO = "demo"

class ConfigSource(Enum):
    """Configuration sources"""
    FILE = "file"
    ENVIRONMENT = "environment"
    DATABASE = "database"
    REMOTE = "remote"

@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str = "localhost"
    port: int = 5432
    database: str = "smartsafe_ai"
    username: str = "postgres"
    password: str = ""
    pool_size: int = 10
    timeout: int = 30
    ssl_mode: str = "prefer"

@dataclass
class CameraConfig:
    """Camera configuration"""
    use_real_cameras: bool = False
    auto_discovery: bool = True
    connection_timeout: int = 10
    retry_attempts: int = 3
    frame_buffer_size: int = 5
    default_resolution: str = "1280x720"
    default_fps: int = 25
    fallback_to_simulation: bool = True

@dataclass
class DetectionConfig:
    """Detection configuration"""
    model_path: str = "data/models/yolov8n.pt"
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.45
    max_detections: int = 100
    use_gpu: bool = True
    batch_size: int = 1
    input_size: tuple = (640, 640)
    enable_tracking: bool = True

@dataclass
class SecurityConfig:
    """Security configuration"""
    secret_key: str = "smartsafe-ai-secret-key-change-in-production"
    session_timeout: int = 3600
    max_login_attempts: int = 5
    password_min_length: int = 8
    require_https: bool = False
    cors_enabled: bool = True
    rate_limiting: bool = True
    jwt_expiration: int = 86400

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_enabled: bool = True
    file_path: str = "logs/smartsafe.log"
    max_file_size: str = "10MB"
    backup_count: int = 5
    json_enabled: bool = True
    console_enabled: bool = True

@dataclass
class PerformanceConfig:
    """Performance configuration"""
    max_workers: int = 4
    worker_timeout: int = 300
    memory_limit: str = "1GB"
    cpu_limit: float = 80.0
    cache_enabled: bool = True
    cache_size: int = 1000
    compression_enabled: bool = True
    async_processing: bool = True

@dataclass
class MonitoringConfig:
    """Monitoring configuration"""
    enabled: bool = True
    metrics_port: int = 9090
    health_check_interval: int = 30
    alert_thresholds: Dict[str, float] = None
    prometheus_enabled: bool = False
    grafana_enabled: bool = False

@dataclass
class SmartSafeConfig:
    """Complete SmartSafe AI configuration"""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 5000
    
    database: DatabaseConfig = None
    camera: CameraConfig = None
    detection: DetectionConfig = None
    security: SecurityConfig = None
    logging: LoggingConfig = None
    performance: PerformanceConfig = None
    monitoring: MonitoringConfig = None
    
    # Feature flags
    features: Dict[str, bool] = None
    
    # Custom settings
    custom: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize default configurations"""
        if self.database is None:
            self.database = DatabaseConfig()
        if self.camera is None:
            self.camera = CameraConfig()
        if self.detection is None:
            self.detection = DetectionConfig()
        if self.security is None:
            self.security = SecurityConfig()
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.performance is None:
            self.performance = PerformanceConfig()
        if self.monitoring is None:
            self.monitoring = MonitoringConfig(
                alert_thresholds={
                    "cpu_usage": 80.0,
                    "memory_usage": 85.0,
                    "error_rate": 5.0,
                    "response_time": 2.0
                }
            )
        if self.features is None:
            self.features = {
                "multi_tenant": True,
                "real_time_detection": True,
                "analytics": True,
                "reporting": True,
                "api_access": True,
                "mobile_app": False,
                "cloud_sync": False,
                "ai_insights": True
            }
        if self.custom is None:
            self.custom = {}

class ProfessionalConfigManager:
    """Enterprise-grade configuration management"""
    
    def __init__(self, config_dir: str = "configs"):
        """Initialize configuration manager"""
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger("professional_config_manager")
        
        # Detect environment
        self.environment = self.detect_environment()
        
        # Initialize configuration sources
        self.config_sources = []
        
        # Load configuration
        self.load_configuration()
        
        self.logger.info("Professional Config Manager initialized")
    
    def detect_environment(self) -> Environment:
        """Detect current environment"""
        env_name = os.getenv("SMARTSAFE_ENV", "development").lower()
        
        try:
            return Environment(env_name)
        except ValueError:
            self.logger.warning(f"Unknown environment '{env_name}', defaulting to development")
            return Environment.DEVELOPMENT
    
    def load_configuration(self):
        """Load configuration from multiple sources"""
        self.logger.info(f"Loading configuration for {self.environment.value} environment")
        
        # Start with default configuration
        self.config = SmartSafeConfig(environment=self.environment)
        
        # Load from files (in order of precedence)
        config_files = [
            "default.yaml",
            f"{self.environment.value}.yaml",
            "local.yaml",
            "override.yaml"
        ]
        
        for config_file in config_files:
            file_path = self.config_dir / config_file
            if file_path.exists():
                try:
                    self.load_from_file(file_path)
                    self.config_sources.append(ConfigSource.FILE)
                    self.logger.info(f"Loaded config from {config_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to load {config_file}: {e}")
        
        # Load from environment variables
        self.load_from_environment()
        self.config_sources.append(ConfigSource.ENVIRONMENT)
        
        # Apply environment-specific overrides
        self.apply_environment_overrides()
        
        # Validate configuration
        self.validate_configuration()
        
        self.logger.info("Configuration loaded successfully")
    
    def load_from_file(self, file_path: Path):
        """Load configuration from YAML/JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            
            # Merge with existing configuration
            self.merge_config(data)
            
        except Exception as e:
            raise Exception(f"Failed to load configuration from {file_path}: {e}")
    
    def load_from_environment(self):
        """Load configuration from environment variables"""
        env_mappings = {
            # Database
            'SMARTSAFE_DB_HOST': ('database', 'host'),
            'SMARTSAFE_DB_PORT': ('database', 'port'),
            'SMARTSAFE_DB_NAME': ('database', 'database'),
            'SMARTSAFE_DB_USER': ('database', 'username'),
            'SMARTSAFE_DB_PASSWORD': ('database', 'password'),
            
            # Camera
            'SMARTSAFE_CAMERA_REAL': ('camera', 'use_real_cameras'),
            'SMARTSAFE_CAMERA_DISCOVERY': ('camera', 'auto_discovery'),
            'SMARTSAFE_CAMERA_TIMEOUT': ('camera', 'connection_timeout'),
            
            # Detection
            'SMARTSAFE_MODEL_PATH': ('detection', 'model_path'),
            'SMARTSAFE_CONFIDENCE': ('detection', 'confidence_threshold'),
            'SMARTSAFE_USE_GPU': ('detection', 'use_gpu'),
            
            # Security
            'SMARTSAFE_SECRET_KEY': ('security', 'secret_key'),
            'SMARTSAFE_SESSION_TIMEOUT': ('security', 'session_timeout'),
            'SMARTSAFE_REQUIRE_HTTPS': ('security', 'require_https'),
            
            # Server
            'SMARTSAFE_HOST': ('host',),
            'SMARTSAFE_PORT': ('port',),
            'SMARTSAFE_DEBUG': ('debug',),
            
            # Performance
            'SMARTSAFE_WORKERS': ('performance', 'max_workers'),
            'SMARTSAFE_MEMORY_LIMIT': ('performance', 'memory_limit'),
            
            # Monitoring
            'SMARTSAFE_MONITORING': ('monitoring', 'enabled'),
            'SMARTSAFE_METRICS_PORT': ('monitoring', 'metrics_port'),
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    # Type conversion
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif value.isdigit():
                        value = int(value)
                    elif '.' in value and value.replace('.', '').isdigit():
                        value = float(value)
                    
                    # Set configuration value
                    self.set_config_value(config_path, value)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to set {env_var}: {e}")
    
    def apply_environment_overrides(self):
        """Apply environment-specific configuration overrides"""
        # Ensure all config sections are initialized
        if self.config.logging is None:
            self.config.logging = LoggingConfig()
        if self.config.security is None:
            self.config.security = SecurityConfig()
        if self.config.performance is None:
            self.config.performance = PerformanceConfig()
        if self.config.monitoring is None:
            self.config.monitoring = MonitoringConfig()
        if self.config.database is None:
            self.config.database = DatabaseConfig()
        if self.config.camera is None:
            self.config.camera = CameraConfig()
        if self.config.features is None:
            self.config.features = {}
            
        if self.environment == Environment.PRODUCTION:
            # Production overrides
            self.config.debug = False
            self.config.security.require_https = True
            self.config.logging.level = "WARNING"
            self.config.logging.console_enabled = False
            self.config.performance.cache_enabled = True
            self.config.monitoring.enabled = True
            
        elif self.environment == Environment.STAGING:
            # Staging overrides
            self.config.debug = False
            self.config.logging.level = "INFO"
            self.config.monitoring.enabled = True
            
        elif self.environment == Environment.TESTING:
            # Testing overrides
            self.config.debug = True
            self.config.database.database = "smartsafe_test"
            self.config.camera.use_real_cameras = False
            self.config.logging.level = "DEBUG"
            
        elif self.environment == Environment.DEMO:
            # Demo overrides
            self.config.debug = False
            self.config.camera.use_real_cameras = False
            self.config.camera.fallback_to_simulation = True
            self.config.features["real_time_detection"] = True
            self.config.features["analytics"] = True
            
        elif self.environment == Environment.DEVELOPMENT:
            # Development overrides
            self.config.debug = True
            self.config.logging.level = "DEBUG"
            self.config.logging.console_enabled = True
            self.config.security.require_https = False
    
    def merge_config(self, data: Dict[str, Any]):
        """Merge configuration data with existing config"""
        def merge_dict(target: dict, source: dict):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    merge_dict(target[key], value)
                else:
                    target[key] = value
        
        # Convert config to dict for merging
        config_dict = asdict(self.config)
        
        # Merge
        merge_dict(config_dict, data)
        
        # Convert back to config object with proper nested dataclass handling
        try:
            # Create nested dataclass objects
            if 'database' in config_dict:
                config_dict['database'] = DatabaseConfig(**config_dict['database'])
            if 'camera' in config_dict:
                config_dict['camera'] = CameraConfig(**config_dict['camera'])
            if 'detection' in config_dict:
                config_dict['detection'] = DetectionConfig(**config_dict['detection'])
            if 'security' in config_dict:
                config_dict['security'] = SecurityConfig(**config_dict['security'])
            if 'logging' in config_dict:
                config_dict['logging'] = LoggingConfig(**config_dict['logging'])
            if 'performance' in config_dict:
                config_dict['performance'] = PerformanceConfig(**config_dict['performance'])
            if 'monitoring' in config_dict:
                config_dict['monitoring'] = MonitoringConfig(**config_dict['monitoring'])
            
            # Handle environment enum
            if 'environment' in config_dict and isinstance(config_dict['environment'], str):
                config_dict['environment'] = Environment(config_dict['environment'])
            
            self.config = SmartSafeConfig(**config_dict)
        except Exception as e:
            self.logger.error(f"Failed to merge config: {e}")
            # Keep existing config if merge fails
            pass
    
    def set_config_value(self, path: tuple, value: Any):
        """Set configuration value by path"""
        target = self.config
        
        # Navigate to parent
        for key in path[:-1]:
            if hasattr(target, key):
                target = getattr(target, key)
            else:
                return
        
        # Set final value
        if hasattr(target, path[-1]):
            setattr(target, path[-1], value)
    
    def validate_configuration(self):
        """Validate configuration"""
        errors = []
        
        # Database validation
        if not self.config.database.host:
            errors.append("Database host is required")
        
        if not self.config.database.database:
            errors.append("Database name is required")
        
        # Security validation
        if self.environment == Environment.PRODUCTION:
            if self.config.security.secret_key == "smartsafe-ai-secret-key-change-in-production":
                errors.append("Secret key must be changed in production")
            
            if not self.config.security.require_https:
                errors.append("HTTPS should be required in production")
        
        # Detection validation
        model_path = Path(self.config.detection.model_path)
        if not model_path.exists():
            self.logger.warning(f"Detection model not found: {model_path}")
        
        # Logging validation
        log_dir = Path(self.config.logging.file_path).parent
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)
        
        self.logger.info("Configuration validation passed")
    
    def get_config(self) -> SmartSafeConfig:
        """Get current configuration"""
        return self.config
    
    def get_database_url(self) -> str:
        """Get database connection URL"""
        db = self.config.database
        return f"postgresql://{db.username}:{db.password}@{db.host}:{db.port}/{db.database}"
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == Environment.DEVELOPMENT
    
    def is_demo_mode(self) -> bool:
        """Check if running in demo mode"""
        return self.environment == Environment.DEMO
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled"""
        return self.config.features.get(feature, False)
    
    def export_config(self, output_file: str = None, format: str = "yaml") -> str:
        """Export current configuration"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.config_dir / f"config_export_{timestamp}.{format}"
        
        config_dict = asdict(self.config)
        
        # Convert enums to strings
        config_dict['environment'] = self.config.environment.value
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                if format.lower() == 'yaml':
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    json.dump(config_dict, f, indent=2, default=str)
            
            self.logger.info(f"Configuration exported to {output_file}")
            return str(output_file)
            
        except Exception as e:
            self.logger.error(f"Failed to export configuration: {e}")
            return None
    
    def reload_configuration(self):
        """Reload configuration from sources"""
        self.logger.info("Reloading configuration...")
        self.load_configuration()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary"""
        return {
            "environment": self.environment.value,
            "debug": self.config.debug,
            "host": self.config.host,
            "port": self.config.port,
            "database": {
                "host": self.config.database.host,
                "port": self.config.database.port,
                "database": self.config.database.database
            },
            "camera": {
                "use_real_cameras": self.config.camera.use_real_cameras,
                "auto_discovery": self.config.camera.auto_discovery
            },
            "features": self.config.features,
            "config_sources": [source.value for source in self.config_sources],
            "loaded_at": datetime.now().isoformat()
        }
    
    def create_default_configs(self):
        """Create default configuration files"""
        configs = {
            "default.yaml": {
                "debug": True,
                "host": "0.0.0.0",
                "port": 5000,
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "smartsafe_ai",
                    "username": "postgres",
                    "password": ""
                },
                "camera": {
                    "use_real_cameras": False,
                    "auto_discovery": True,
                    "connection_timeout": 10
                },
                "detection": {
                    "confidence_threshold": 0.5,
                    "use_gpu": True
                }
            },
            "production.yaml": {
                "debug": False,
                "security": {
                    "require_https": True,
                    "session_timeout": 1800
                },
                "logging": {
                    "level": "WARNING",
                    "console_enabled": False
                },
                "monitoring": {
                    "enabled": True,
                    "prometheus_enabled": True
                }
            },
            "demo.yaml": {
                "camera": {
                    "use_real_cameras": False,
                    "fallback_to_simulation": True
                },
                "features": {
                    "real_time_detection": True,
                    "analytics": True,
                    "reporting": True
                }
            }
        }
        
        for filename, config_data in configs.items():
            file_path = self.config_dir / filename
            if not file_path.exists():
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config_data, f, default_flow_style=False, indent=2)
                    self.logger.info(f"Created default config: {filename}")
                except Exception as e:
                    self.logger.error(f"Failed to create {filename}: {e}")

# Global configuration manager
config_manager = ProfessionalConfigManager()

def get_config() -> SmartSafeConfig:
    """Get global configuration"""
    return config_manager.get_config()

def get_config_manager() -> ProfessionalConfigManager:
    """Get global configuration manager"""
    return config_manager

def is_production() -> bool:
    """Check if running in production"""
    return config_manager.is_production()

def is_development() -> bool:
    """Check if running in development"""
    return config_manager.is_development()

def is_demo_mode() -> bool:
    """Check if running in demo mode"""
    return config_manager.is_demo_mode()

def is_feature_enabled(feature: str) -> bool:
    """Check if feature is enabled"""
    return config_manager.is_feature_enabled(feature)

# Test function
def test_config_manager():
    """Test the configuration manager"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Testing Professional Configuration Manager")
    
    # Create default configs
    config_manager.create_default_configs()
    
    # Get configuration
    config = get_config()
    logger.info(f"Current environment: {config.environment.value}")
    logger.info(f"Debug mode: {config.debug}")
    logger.info(f"Use real cameras: {config.camera.use_real_cameras}")
    
    # Test feature flags
    logger.info(f"Multi-tenant enabled: {is_feature_enabled('multi_tenant')}")
    logger.info(f"Analytics enabled: {is_feature_enabled('analytics')}")
    
    # Get summary
    summary = config_manager.get_config_summary()
    logger.info(f"Config summary: {summary}")
    
    # Export configuration
    export_file = config_manager.export_config()
    logger.info(f"Configuration exported to: {export_file}")

if __name__ == "__main__":
    test_config_manager() 