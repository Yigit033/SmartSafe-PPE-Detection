"""
SmartSafe AI - Sistem Sabitleri (Constants)
Bu dosya, .env dosyasında kalabalık yapan ve her seferinde paylaşılması gereken 
sistem yapılandırmalarını içerir. Sırlar (Secrets) hala .env dosyasında tutulmalıdır.
"""

import os
from typing import Dict, Any

# Application Configuration
FLASK_ENV = "development"
FLASK_DEBUG = True
BCRYPT_LOG_ROUNDS = 12

# File Upload
MAX_CONTENT_LENGTH = 16777216  # 16MB
UPLOAD_FOLDER = "static/uploads"

# Performance & Resource Management
CACHE_DURATION = 300  # 5 minutes
MAX_CONCURRENT_CAMERAS = 32
DEFAULT_FRAME_SKIP = 3
DVR_INITIAL_WAIT = 0.5
STANDARD_INITIAL_WAIT = 0.1
DETECTION_QUEUE_SIZE = 20
CPU_REDUCTION_SLEEP = 0.01
FPS_30_SLEEP = 0.033
RENDER_RELOAD_DELAY = 1.0

# Network & Timeouts
SOCKET_TIMEOUT = 2
API_REQUEST_TIMEOUT = 5
SNAPSHOT_TIMEOUT = 5
WORKING_URL_TIMEOUT = 3
PROXY_STREAM_CONNECT_TIMEOUT_S = 20
DVR_PROBE_TTL_FAIL_S = 120
TELEGRAM_TIMEOUT = 30
TELEGRAM_PHOTO_TIMEOUT = 15
TELEGRAM_RETRY_DELAY = 10
TELEGRAM_POLLING_TIMEOUT = 35
LOG_FILE_ENABLED = 1
LOG_FILE_MAX_DAYS = 30
REQUEST_LOG_LEVEL = "INFO"

# Database Configuration
DB_POOL_MINCONN = 5
DB_POOL_MAXCONN = 100
DB_CONNECTION_TIMEOUT = 30
DB_CACHE_TTL = 60
DEFAULT_MAX_CAMERAS = 25

# Detection Configuration
DETECTION_CONFIDENCE_THRESHOLD = 0.5
DETECTION_MODEL_PATH = "models/yolo9e.pt"
DETECTION_DECISION_ENGINE = 1
HELMET_PIXEL_THRESHOLD = 0.05
VEST_PIXEL_THRESHOLD = 0.08
RESCUE_CONFIDENCE_THRESHOLD = 0.20

# Temporal PPE Gating (N-of-M + track-based hysteresis)
TEMPORAL_PPE_GATING = 1
PPE_N_OF_M_M = 10
PPE_N_OF_M_N = 8
PPE_FORGIVE_WINDOW = 3
PPE_HYSTERESIS_EXTRA = 2
PPE_TRACK_TTL_S = 10

# Specific overrides for face_mask (often more flicker-prone)
MASK_N_OF_M_M = 20
MASK_N_OF_M_N = 18
MASK_FORGIVE_WINDOW = 8
MASK_HYSTERESIS_EXTRA = 5

# Logging & Observability
LOG_LEVEL = "INFO"
LOG_FILE = "logs/smartsafe.log"
ROI_LOG_INTERVAL_SEC = 15
ROI_AUTO_EXPAND_X_THRESHOLD = 0.80
OPENCV_FFMPEG_LOGLEVEL = -8
OPENCV_LOG_LEVEL = "ERROR"
TORCH_DEVICE = "auto"
PPE_LOG_SUMMARY_EVERY_S = 2.0
PPE_LOG_GROUP_FLUSH_EVERY_S = 10.0
PPE_DETECTION_CADENCE = 1
PERSON_QUALITY_GATE = 1

# Overlay Rendering
# Default: draw only PERSON bbox + warning labels (clean UI). Set to 1 for detailed PPE boxes.
OVERLAY_SHOW_PPE_BOXES = 0

# PostgreSQL connection pool
DB_POOL_MINCONN = 5
DB_POOL_MAXCONN = 100

# Email Configuration (Sunucu Ayarları)
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True

# API Rate Limiting
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 3600  # 1 hour

# Roboflow / Food PPE Configuration
FOOD_PPE_API_MODEL = "ppe-food-manufacturing/3"
FOOD_PPE_LOCAL_MODEL = "models/sh17_food_beverage/sh17_food_beverage_model/weights/best.pt"
FOOD_PPE_CONFIDENCE = 0.15

# Telegram Configuration
DEFAULT_TELEGRAM_BOT_USERNAME = "smartsafeaibot"

# Subscription & Business Logic
FREE_TRIAL_DAYS = 7
SUBSCRIPTION_YEAR_DAYS = 365
SUBSCRIPTION_EXTENDED_DAYS = 7 + 365

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:3377',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3377',
    'http://localhost:8000',
    'http://localhost:5577',
    'http://127.0.0.1:5577',
    'http://localhost:8088',
    'http://127.0.0.1:8088',
    'https://getsmartsafeai.com',
    'https://www.getsmartsafeai.com',
    'https://app.getsmartsafeai.com',
    'https://*.vercel.app'
]

# Person Filter & Confidence
OSD_PERSON_FILTER = 1
POSE_PERSON_CONFIDENCE = 0.60
POSE_REQUIRE_PERSON = 1
SH17_PERSON_DISABLED = 1

# Camera Discovery
CAMERA_DISCOVERY_ADMIN_ONLY = 1
CAMERA_DISCOVERY_REQUIRE_EXPLICIT_RANGE = 1
CAMERA_DISCOVERY_MIN_INTERVAL_S = 600
CAMERA_DISCOVERY_MAX_WORKERS = 10

# DVR Probing
DVR_PROBE_CONCURRENCY = 2
DVR_START_URL_BUDGET = 12

# PPE Configuration — Single source of truth for all PPE types.
PPE_CONFIG: Dict[str, Dict[str, Any]] = {
    'helmet': {
        'model_classes': ['helmet', 'hard_hat', 'hardhat', 'baret'],
        'region': 'head',
        'pos_label': 'Baret',
        'neg_label': 'Baret YOK',
        'violation_tr': 'Baret eksik',
        'default_critical': True,
    },
    'safety_vest': {
        'model_classes': ['safety_vest', 'vest', 'yelek'],
        'region': 'torso',
        'pos_label': 'Yelek',
        'neg_label': 'Yelek YOK',
        'violation_tr': 'Yelek eksik',
        'default_critical': True,
    },
    'safety_shoes': {
        'model_classes': ['safety_shoes', 'shoes', 'shoe', 'ayakkabı', 'ayakkabi'],
        'region': 'feet',
        'pos_label': 'Ayakkabı',
        'neg_label': 'Ayakkabı YOK',
        'violation_tr': 'Güvenlik ayakkabısı eksik',
        'default_critical': True,
    },
    'gloves': {
        'model_classes': ['gloves'],
        'region': 'hands',
        'pos_label': 'Eldiven',
        'neg_label': 'Eldiven YOK',
        'violation_tr': 'Eldiven eksik',
        'default_critical': False,
    },
    'safety_glasses': {
        'model_classes': ['safety_glasses', 'glasses', 'googles', 'goggles', 'gozluk'],
        'region': 'head',
        'pos_label': 'Gözlük',
        'neg_label': 'Gözlük YOK',
        'violation_tr': 'Gözlük eksik',
        'default_critical': False,
    },
    'face_mask': {
        'model_classes': ['face_mask_medical', 'face_mask', 'mask'],
        'region': 'head',
        'pos_label': 'Maske',
        'neg_label': 'Maske YOK',
        'violation_tr': 'Maske eksik',
        'default_critical': False,
    },
    'safety_suit': {
        'model_classes': ['safety_suit', 'medical_suit', 'apron', 'suit', 'tulum', 'onluk'],
        'region': 'torso',
        'pos_label': 'Önlük',
        'neg_label': 'Önlük YOK',
        'violation_tr': 'Koruyucu tulum eksik',
        'default_critical': False,
    },
    'haircap': {
        'model_classes': ['haircap', 'bone', 'file', 'kep', 'hairnet', 'hair_net'],
        'region': 'head',
        'pos_label': 'Bone',
        'neg_label': 'Bone YOK',
        'violation_tr': 'Saç filesi/Bone eksik',
        'default_critical': True,
    },
}


def inject_to_environ():
    """
    Bu modüldeki tüm BÜYÜK_HARF değişkenleri os.environ içine enjekte eder.
    Böylece mevcut kod os.environ.get veya os.getenv ile bu değerlere erişmeye devam edebilir.
    """
    import os
    for key, value in globals().items():
        if key.isupper() and not key.startswith("_") and key != "PPE_CONFIG":
            # os.environ sadece string kabul eder
            os.environ[key] = str(value)
