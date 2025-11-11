#!/usr/bin/env python3
"""
Production Configuration - SmartSafe AI
Optimized settings for Render.com deployment
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ProductionConfig:
    """Production environment configuration"""
    
    # Environment detection
    IS_PRODUCTION = os.environ.get('RENDER') is not None
    IS_DEVELOPMENT = not IS_PRODUCTION
    
    # Flask configuration
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smartsafe-production-key-change-in-production')
    
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    SQLITE_DB_PATH = os.environ.get('SQLITE_DB_PATH', 'smartsafe_saas.db')
    
    # Model configuration
    MODEL_CACHE_ENABLED = IS_PRODUCTION
    LAZY_LOADING_ENABLED = IS_PRODUCTION
    MODEL_DEVICE = 'cpu'  # Force CPU to avoid CUDA issues
    
    # Model paths - Production optimized
    MODEL_PATHS = {
        'base': 'yolov8n.pt',
        'construction': 'yolov8s.pt',
        'manufacturing': 'yolov8m.pt',
        'chemical': 'yolov8n.pt',
        'food_beverage': 'yolov8n.pt',
        'warehouse_logistics': 'yolov8s.pt',
        'energy': 'yolov8n.pt',
        'petrochemical': 'yolov8n.pt',
        'marine_shipyard': 'yolov8n.pt',
        'aviation': 'yolov8n.pt'
    }
    
    # Model search paths - Production
    MODEL_SEARCH_PATHS = [
        '/app/data/models',
        '/opt/render/project/src/data/models',
        'data/models',
        '.'
    ]
    
    # Connection pool configuration
    DB_POOL_MIN_CONNECTIONS = 1
    DB_POOL_MAX_CONNECTIONS = 10
    DB_CONNECTION_TIMEOUT = 45  # Render.com cold start
    DB_POOL_RECYCLE = 300  # 5 minutes
    
    # Retry configuration
    MAX_RETRIES = 5
    RETRY_DELAY = 2  # Exponential backoff
    
    # Keepalive configuration
    KEEPALIVES_ENABLED = True
    KEEPALIVES_IDLE = 10
    KEEPALIVES_INTERVAL = 5
    KEEPALIVES_COUNT = 10
    
    # SSL configuration
    SSL_MODE = os.environ.get('SSL_MODE', 'require')
    SSL_CERT_PATH = '/opt/render/project/src/ssl/supabase.crt'
    
    # API configuration
    API_TIMEOUT = 120  # 2 minutes
    API_MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Detection configuration
    DETECTION_CONFIDENCE_THRESHOLD = 0.25
    DETECTION_NMS_THRESHOLD = 0.45
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.sendgrid.net')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', True)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'apikey')
    MAIL_PASSWORD = os.environ.get('SENDGRID_API_KEY', '')
    
    # Logging configuration
    LOG_LEVEL = logging.WARNING if IS_PRODUCTION else logging.INFO
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'logs/smartsafe.log'
    
    # Cache configuration
    CACHE_ENABLED = IS_PRODUCTION
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Session configuration
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # CORS configuration
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    CORS_ALLOW_HEADERS = ['Content-Type', 'Authorization']
    CORS_EXPOSE_HEADERS = ['Content-Type', 'X-Total-Count']
    
    # Rate limiting
    RATE_LIMIT_ENABLED = IS_PRODUCTION
    RATE_LIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    
    @classmethod
    def get_model_path(cls, sector='base', model_name=None):
        """Get model path with fallback logic"""
        if model_name is None:
            model_name = cls.MODEL_PATHS.get(sector, 'yolov8n.pt')
        
        # Try each search path
        for search_path in cls.MODEL_SEARCH_PATHS:
            full_path = os.path.join(search_path, model_name)
            if os.path.exists(full_path):
                logger.info(f"✅ Found model at: {full_path}")
                return full_path
        
        # If not found, return default (will trigger auto-download)
        logger.warning(f"⚠️ Model not found: {model_name}, will attempt auto-download")
        return model_name
    
    @classmethod
    def validate_production_settings(cls):
        """Validate production settings"""
        errors = []
        
        if cls.IS_PRODUCTION:
            # Check required environment variables
            if not os.environ.get('DATABASE_URL'):
                errors.append("DATABASE_URL not set in production")
            
            if not os.environ.get('SECRET_KEY'):
                logger.warning("⚠️ SECRET_KEY not set, using default (INSECURE)")
            
            if not os.environ.get('SENDGRID_API_KEY'):
                logger.warning("⚠️ SENDGRID_API_KEY not set, email will use SMTP")
        
        # Log configuration
        logger.info(f"🎯 Production mode: {cls.IS_PRODUCTION}")
        logger.info(f"🎯 Model cache enabled: {cls.MODEL_CACHE_ENABLED}")
        logger.info(f"🎯 Lazy loading enabled: {cls.LAZY_LOADING_ENABLED}")
        logger.info(f"🎯 Database connection timeout: {cls.DB_CONNECTION_TIMEOUT}s")
        logger.info(f"🎯 Max retries: {cls.MAX_RETRIES}")
        
        if errors:
            error_msg = "Production configuration errors:\n" + "\n".join(f"- {e}" for e in errors)
            logger.warning(error_msg)
        
        return len(errors) == 0

# Initialize configuration
config = ProductionConfig()
config.validate_production_settings()
