#!/usr/bin/env python3
"""
Database Adapter - SQLite & PostgreSQL Support
Handles both local SQLite and production PostgreSQL
"""

import os
import sqlite3
import psycopg2
import psycopg2.extras
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid
import secrets
import bcrypt
# Lazy import to avoid circular dependency
def get_secure_db_connector():
    """Get secure DB connector when needed"""
    try:
        from src.smartsafe.utils.secure_database_connector import get_secure_db_connector
        return get_secure_db_connector()
    except ImportError:
        return None
import time
import traceback
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread-local storage for SQLite connections
_thread_local = threading.local()

@dataclass
class DatabaseConfig:
    """Database configuration"""
    database_url: str
    database_type: str  # 'sqlite' or 'postgresql'
    connection_params: Dict[str, Any]

class DatabaseAdapter:
    """Universal database adapter for SQLite and PostgreSQL"""
    
    def __init__(self):
        self.config = self._get_database_config()
        self.db_type = self.config.database_type
        self.secure_connector = get_secure_db_connector()
        self.connection_pool = None  # Will be initialized for PostgreSQL
        self._init_connection_pool()
        logger.info(f"🗄️ Database adapter initialized: {self.db_type}")
    
    def _init_connection_pool(self):
        """Initialize connection pool for PostgreSQL"""
        try:
            if self.db_type == 'postgresql' and self.secure_connector:
                # Connection pooling for PostgreSQL
                from psycopg2 import pool
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(database_url)
                    
                    # Create connection pool
                    self.connection_pool = pool.SimpleConnectionPool(
                        minconn=1,
                        maxconn=10,  # Max 10 connections
                        host=parsed.hostname,
                        port=parsed.port or 5432,
                        database=parsed.path[1:],
                        user=parsed.username,
                        password=parsed.password,
                        connect_timeout=45,  # Match secure connector timeout
                        keepalives=1,
                        keepalives_idle=10,
                        keepalives_interval=5,
                        keepalives_count=10
                    )
                    logger.info("✅ PostgreSQL connection pool initialized (min=1, max=10)")
        except Exception as e:
            logger.warning(f"⚠️ Connection pool initialization failed: {e}, will use direct connections")
    
    def _get_database_config(self) -> DatabaseConfig:
        """Get database configuration based on environment"""
        try:
            # Check for PostgreSQL configuration first
            database_url = os.getenv('DATABASE_URL')
            if database_url and database_url.startswith('postgresql://'):
                logger.info("✅ PostgreSQL configuration found")
                return DatabaseConfig(
                    database_url=database_url,
                    database_type='postgresql',
                    connection_params={'database_url': database_url}
                )
            else:
                logger.info("ℹ️ No PostgreSQL configuration found, using SQLite")
                return self._get_sqlite_config()
        except Exception as e:
            logger.warning(f"⚠️ Database config error: {e}, falling back to SQLite")
            return self._get_sqlite_config()
    
    def _get_sqlite_config(self) -> DatabaseConfig:
        """Get SQLite configuration"""
        db_path = os.getenv('SQLITE_DB_PATH', 'smartsafe_saas.db')
        return DatabaseConfig(
            database_url=db_path,
            database_type='sqlite',
            connection_params={'database_path': db_path}
        )
    
    def get_connection(self, timeout: int = 30):
        """Get database connection with thread safety and connection pooling"""
        try:
            if self.db_type == 'sqlite':
                # Create new connection for each request to avoid thread issues
                connection = sqlite3.connect(
                    self.config.database_url,
                    timeout=timeout,
                    check_same_thread=False  # Allow cross-thread usage
                )
                connection.row_factory = sqlite3.Row
                return connection
            else:  # PostgreSQL
                # Try to use connection pool first
                if self.connection_pool:
                    try:
                        conn = self.connection_pool.getconn()
                        logger.debug("✅ Got connection from pool")
                        return conn
                    except Exception as pool_error:
                        logger.warning(f"⚠️ Connection pool error: {pool_error}, using direct connection")
                
                # Fallback to direct connection via secure connector
                secure_connector = get_secure_db_connector()
                if secure_connector:
                    return secure_connector.get_connection()
                else:
                    logger.error("❌ Secure connector not available")
                    return None
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def init_database(self):
        """Initialize database tables - Production Safe with Schema Sync"""
        try:
            conn = self.get_connection()
            if conn is None:
                logger.warning("⚠️ Primary database connection failed, falling back to SQLite")
                # Force fallback to SQLite
                self.config = self._get_sqlite_config()
                self.db_type = self.config.database_type
                logger.info(f"🔄 Switched to SQLite: {self.db_type}")
                conn = self.get_connection()
                if conn is None:
                    logger.error("❌ Database initialization failed: No connection available")
                    return False
            
            # PostgreSQL için schema senkronizasyonu kontrol et
            if self.db_type == 'postgresql':
                schema_ok = self._check_and_sync_schema(conn)
                if schema_ok:
                    logger.info("✅ PostgreSQL schema synchronized successfully")
                    return True
                else:
                    logger.warning("⚠️ Schema sync failed, continuing with table creation")
            
            # PostgreSQL için temiz connection setup
            if self.db_type == 'postgresql':
                try:
                    # Fresh connection al
                    conn.close()
                    conn = self.get_connection()
                    logger.info("🔄 PostgreSQL fresh connection established")
                    logger.info("🔧 PostgreSQL autocommit already enabled in secure connector")
                    
                except Exception as e:
                    logger.warning(f"⚠️ PostgreSQL setup warning: {e}")
                    try:
                        conn = self.get_connection()
                    except Exception:
                        pass
                
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                cursor = conn.cursor()
            logger.info("🔧 Creating database tables...")
            
            # Get database-specific placeholder
            def get_placeholder(self):
                """Get database-specific placeholder for parameterized queries"""
                return '?' if self.db_type == 'sqlite' else '%s'
            
            # Companies table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS companies (
                        company_id TEXT PRIMARY KEY,
                        company_name TEXT NOT NULL,
                        sector TEXT NOT NULL,
                        contact_person TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        phone TEXT,
                        address TEXT,
                        max_cameras INTEGER DEFAULT 25,
                        subscription_type TEXT DEFAULT 'starter',
                        billing_cycle TEXT DEFAULT 'monthly',
                        subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_end TIMESTAMP,
                        next_billing_date TIMESTAMP,
                        auto_renewal BOOLEAN DEFAULT TRUE,
                        payment_method TEXT,
                        payment_status TEXT DEFAULT 'active',
                        current_balance REAL DEFAULT 0.00,
                        total_paid REAL DEFAULT 0.00,
                        last_payment_date TIMESTAMP,
                        last_payment_amount REAL,
                        status TEXT DEFAULT 'active',
                        api_key TEXT UNIQUE,
                        required_ppe TEXT,
                        profile_image TEXT,
                        logo_url TEXT,
                        sector_config TEXT,
                        ppe_requirements TEXT,
                        compliance_settings TEXT,
                        email_notifications BOOLEAN DEFAULT TRUE,
                        sms_notifications BOOLEAN DEFAULT FALSE,
                        push_notifications BOOLEAN DEFAULT TRUE,
                        violation_alerts BOOLEAN DEFAULT TRUE,
                        system_alerts BOOLEAN DEFAULT TRUE,
                        report_notifications BOOLEAN DEFAULT TRUE,
                        account_type TEXT DEFAULT 'full',
                        demo_expires_at TIMESTAMP,
                        demo_limits TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS companies (
                        company_id VARCHAR(255) PRIMARY KEY,
                        company_name VARCHAR(255) NOT NULL,
                        sector VARCHAR(100) NOT NULL,
                        contact_person VARCHAR(255) NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        phone VARCHAR(50),
                        address TEXT,
                        max_cameras INTEGER DEFAULT 25,
                        subscription_type VARCHAR(50) DEFAULT 'starter',
                        billing_cycle VARCHAR(20) DEFAULT 'monthly',
                        subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_end TIMESTAMP,
                        next_billing_date TIMESTAMP,
                        auto_renewal BOOLEAN DEFAULT TRUE,
                        payment_method VARCHAR(50),
                        payment_status VARCHAR(20) DEFAULT 'active',
                        current_balance DECIMAL(10,2) DEFAULT 0.00,
                        total_paid DECIMAL(10,2) DEFAULT 0.00,
                        last_payment_date TIMESTAMP,
                        last_payment_amount DECIMAL(10,2),
                        status VARCHAR(50) DEFAULT 'active',
                        api_key VARCHAR(255) UNIQUE,
                        required_ppe TEXT,
                        profile_image TEXT,
                        logo_url TEXT,
                        sector_config JSON,
                        ppe_requirements JSON,
                        compliance_settings JSON,
                        email_notifications BOOLEAN DEFAULT TRUE,
                        sms_notifications BOOLEAN DEFAULT FALSE,
                        push_notifications BOOLEAN DEFAULT TRUE,
                        violation_alerts BOOLEAN DEFAULT TRUE,
                        system_alerts BOOLEAN DEFAULT TRUE,
                        report_notifications BOOLEAN DEFAULT TRUE,
                        account_type VARCHAR(20) DEFAULT 'full',
                        demo_expires_at TIMESTAMP,
                        demo_limits JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create sector performance metrics table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sector_performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT,
                        sector_id TEXT,
                        date TEXT,
                        total_detections INTEGER DEFAULT 0,
                        compliance_rate REAL,
                        violations_count INTEGER DEFAULT 0,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sector_performance_metrics (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255),
                        sector_id VARCHAR(100),
                        date DATE,
                        total_detections INTEGER DEFAULT 0,
                        compliance_rate DECIMAL(5,2),
                        violations_count INTEGER DEFAULT 0,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # Create sector PPE configs table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sector_ppe_configs (
                        sector_id TEXT PRIMARY KEY,
                        sector_name TEXT,
                        mandatory_ppe TEXT,
                        optional_ppe TEXT,
                        detection_settings TEXT,

                        compliance_requirements TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sector_ppe_configs (
                        sector_id VARCHAR(100) PRIMARY KEY,
                        sector_name VARCHAR(255),
                        mandatory_ppe JSON,
                        optional_ppe JSON,
                        detection_settings JSON,

                        compliance_requirements JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # Create DVR systems table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_systems (
                        dvr_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        port INTEGER DEFAULT 80,
                        username TEXT DEFAULT 'admin',
                        password TEXT DEFAULT '',
                        dvr_type TEXT DEFAULT 'generic',
                        protocol TEXT DEFAULT 'http',
                        api_path TEXT DEFAULT '/api',
                        rtsp_port INTEGER DEFAULT 554,
                        max_channels INTEGER DEFAULT 16,
                        status TEXT DEFAULT 'inactive',
                        last_test_time TIMESTAMP,
                        connection_retries INTEGER DEFAULT 3,
                        timeout INTEGER DEFAULT 10,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_systems (
                        dvr_id VARCHAR(255) PRIMARY KEY,
                        company_id VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        ip_address VARCHAR(45) NOT NULL,
                        port INTEGER DEFAULT 80,
                        username VARCHAR(100) DEFAULT 'admin',
                        password VARCHAR(255) DEFAULT '',
                        dvr_type VARCHAR(50) DEFAULT 'generic',
                        protocol VARCHAR(10) DEFAULT 'http',
                        api_path VARCHAR(100) DEFAULT '/api',
                        rtsp_port INTEGER DEFAULT 554,
                        max_channels INTEGER DEFAULT 16,
                        status VARCHAR(50) DEFAULT 'inactive',
                        last_test_time TIMESTAMP,
                        connection_retries INTEGER DEFAULT 3,
                        timeout INTEGER DEFAULT 10,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
                    )
                ''')
            
            # Create DVR channels table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_channels (
                        channel_id TEXT PRIMARY KEY,
                        dvr_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        channel_number INTEGER NOT NULL,
                        status TEXT DEFAULT 'inactive',
                        resolution_width INTEGER DEFAULT 1920,
                        resolution_height INTEGER DEFAULT 1080,
                        fps INTEGER DEFAULT 25,
                        rtsp_path TEXT DEFAULT '',
                        http_path TEXT DEFAULT '',
                        last_test_time TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dvr_id) REFERENCES dvr_systems (dvr_id) ON DELETE CASCADE,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_channels (
                        channel_id VARCHAR(255) PRIMARY KEY,
                        dvr_id VARCHAR(255) NOT NULL,
                        company_id VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        channel_number INTEGER NOT NULL,
                        status VARCHAR(50) DEFAULT 'inactive',
                        resolution_width INTEGER DEFAULT 1920,
                        resolution_height INTEGER DEFAULT 1080,
                        fps INTEGER DEFAULT 25,
                        rtsp_path VARCHAR(255) DEFAULT '',
                        http_path VARCHAR(255) DEFAULT '',
                        last_test_time TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dvr_id) REFERENCES dvr_systems (dvr_id) ON DELETE CASCADE,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
                    )
                ''')
            
            # Create DVR streams table for active streams
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_streams (
                        stream_id TEXT PRIMARY KEY,
                        dvr_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        stream_url TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_time TIMESTAMP,
                        fps REAL DEFAULT 0,
                        frame_count INTEGER DEFAULT 0,
                        error_count INTEGER DEFAULT 0,
                        last_frame_time TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dvr_id) REFERENCES dvr_systems (dvr_id) ON DELETE CASCADE,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE,
                        FOREIGN KEY (channel_id) REFERENCES dvr_channels (channel_id) ON DELETE CASCADE
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_streams (
                        stream_id VARCHAR(255) PRIMARY KEY,
                        dvr_id VARCHAR(255) NOT NULL,
                        company_id VARCHAR(255) NOT NULL,
                        channel_id VARCHAR(255) NOT NULL,
                        stream_url TEXT NOT NULL,
                        status VARCHAR(50) DEFAULT 'active',
                        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_time TIMESTAMP,
                        fps DECIMAL(5,2) DEFAULT 0,
                        frame_count INTEGER DEFAULT 0,
                        error_count INTEGER DEFAULT 0,
                        last_frame_time TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dvr_id) REFERENCES dvr_systems (dvr_id) ON DELETE CASCADE,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE,
                        FOREIGN KEY (channel_id) REFERENCES dvr_channels (channel_id) ON DELETE CASCADE
                    )
                ''')
            
            # Add new columns if they don't exist
            if self.db_type == 'sqlite':
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN sector_config TEXT')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN ppe_requirements TEXT')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN compliance_settings TEXT')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN ppe_requirements TEXT')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN email_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN sms_notifications BOOLEAN DEFAULT FALSE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN push_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN violation_alerts BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN system_alerts BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN report_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN profile_image TEXT')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN account_type TEXT DEFAULT "full"')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN demo_expires_at TIMESTAMP')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN demo_limits TEXT')
                except:
                    pass  # Column already exists
            else:  # PostgreSQL - Batch DDL operations to avoid transaction issues
                ddl_statements = [
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sector_config JSON",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS ppe_requirements JSON", 
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS compliance_settings JSON",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS violation_alerts BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS system_alerts BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS report_notifications BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS profile_image TEXT",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS account_type VARCHAR(20) DEFAULT 'full'",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS demo_expires_at TIMESTAMP",
                    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS demo_limits JSON"
                ]
                
                for ddl in ddl_statements:
                    try:
                        cursor.execute(ddl)
                        logger.debug(f"✅ DDL executed: {ddl[:50]}...")
                    except Exception as e:
                        logger.warning(f"⚠️ DDL skipped: {ddl[:50]}... -> {e}")
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'operator',
                    permissions TEXT,
                    last_login TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    UNIQUE(company_id, username)
                )
            ''')
            
            # Cameras table - Enhanced for real camera support
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    ip_address TEXT,
                    port INTEGER DEFAULT 8080,
                    rtsp_url TEXT,
                    username TEXT,
                    password TEXT,
                    protocol TEXT DEFAULT 'http',
                    stream_path TEXT DEFAULT '/video',
                    auth_type TEXT DEFAULT 'basic',
                    resolution TEXT DEFAULT '1920x1080',
                    fps INTEGER DEFAULT 25,
                    quality INTEGER DEFAULT 80,
                    audio_enabled BOOLEAN DEFAULT FALSE,
                    night_vision BOOLEAN DEFAULT FALSE,
                    motion_detection BOOLEAN DEFAULT TRUE,
                    recording_enabled BOOLEAN DEFAULT TRUE,
                    camera_type TEXT DEFAULT 'ip_camera',
                    status TEXT DEFAULT 'active',
                    last_detection TIMESTAMP,
                    last_test_time TIMESTAMP,
                    connection_retries INTEGER DEFAULT 3,
                    timeout INTEGER DEFAULT 10,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    UNIQUE(company_id, camera_name)
                )
            ''')
            
            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (company_id) REFERENCES companies (company_id)
                )
            ''')
            
            # Eski detections tablosu kaldırıldı - Reports için yeni tablo kullanılıyor
            
            # Reports için gerekli tablolar - SQLite ve PostgreSQL uyumlu
            if self.db_type == 'sqlite':
                cursor.execute('''
                            CREATE TABLE IF NOT EXISTS violations (
                                violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                company_id TEXT NOT NULL,
                                camera_id TEXT NOT NULL,
                                worker_id TEXT,
                                missing_ppe TEXT NOT NULL,
                                violation_type TEXT NOT NULL,

                                confidence REAL DEFAULT 0,
                                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (company_id) REFERENCES companies (company_id)
                            )
                        ''')
                    
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS detections (
                        detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL,
                        camera_id TEXT NOT NULL,
                        detection_type TEXT NOT NULL,
                        confidence REAL DEFAULT 0,
                        people_detected INTEGER DEFAULT 0,
                        ppe_compliant INTEGER DEFAULT 0,
                        violations_count INTEGER DEFAULT 0,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL,
                        report_type TEXT NOT NULL,
                        report_data TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                # Alerts tablosu - Akıllı Uyarılar için
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alerts (
                        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL,
                        camera_id TEXT,
                        alert_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        resolved_at DATETIME,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                # Detections tablosuna total_people kolonu ekle
                try:
                    cursor.execute('ALTER TABLE detections ADD COLUMN total_people INTEGER DEFAULT 0')
                except Exception:
                    pass
            else:  # PostgreSQL - Production Ready
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS violations (
                        violation_id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) NOT NULL,
                        camera_id VARCHAR(255) NOT NULL,
                        worker_id VARCHAR(255),
                        missing_ppe VARCHAR(255) NOT NULL,
                        violation_type VARCHAR(255) NOT NULL,

                        confidence DECIMAL(5,2) DEFAULT 0,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS detections (
                        detection_id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) NOT NULL,
                        camera_id VARCHAR(255) NOT NULL,
                        detection_type VARCHAR(255) NOT NULL,
                        confidence DECIMAL(5,2) DEFAULT 0,
                        people_detected INTEGER DEFAULT 0,
                        ppe_compliant INTEGER DEFAULT 0,
                        violations_count INTEGER DEFAULT 0,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        report_id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) NOT NULL,
                        report_type VARCHAR(255) NOT NULL,
                        report_data JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                # Alerts tablosu - Akıllı Uyarılar için
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alerts (
                        alert_id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) NOT NULL,
                        camera_id VARCHAR(255),
                        alert_type VARCHAR(255) NOT NULL,
                        severity VARCHAR(50) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        message TEXT NOT NULL,
                        status VARCHAR(50) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                # Detections tablosuna total_people kolonu ekle
                try:
                    cursor.execute('ALTER TABLE detections ADD COLUMN total_people INTEGER DEFAULT 0')
                except Exception:
                    pass
            
            # DVR Detection Results table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_detection_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        stream_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        total_people INTEGER DEFAULT 0,
                        compliant_people INTEGER DEFAULT 0,
                        violations_count INTEGER DEFAULT 0,
                        missing_ppe TEXT,
                        detection_confidence REAL DEFAULT 0.0,
                        detection_time REAL DEFAULT 0.0,
                        frame_timestamp TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_detection_results (
                        id SERIAL PRIMARY KEY,
                        stream_id VARCHAR(255) NOT NULL,
                        company_id VARCHAR(255) NOT NULL,
                        total_people INTEGER DEFAULT 0,
                        compliant_people INTEGER DEFAULT 0,
                        violations_count INTEGER DEFAULT 0,
                        missing_ppe TEXT,
                        detection_confidence REAL DEFAULT 0.0,
                        detection_time REAL DEFAULT 0.0,
                        frame_timestamp TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # DVR Detection Sessions table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_detection_sessions (
                        session_id TEXT PRIMARY KEY,
                        dvr_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        channels TEXT NOT NULL,
                        detection_mode TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        start_time TEXT,
                        end_time TEXT,
                        total_frames_processed INTEGER DEFAULT 0,
                        total_violations_detected INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dvr_detection_sessions (
                        session_id VARCHAR(255) PRIMARY KEY,
                        dvr_id VARCHAR(255) NOT NULL,
                        company_id VARCHAR(255) NOT NULL,
                        channels TEXT NOT NULL,
                        detection_mode VARCHAR(100) NOT NULL,
                        status VARCHAR(50) DEFAULT 'active',
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        total_frames_processed INTEGER DEFAULT 0,
                        total_violations_detected INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # Create subscription history table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscription_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT,
                        subscription_type TEXT NOT NULL,
                        billing_cycle TEXT NOT NULL,
                        start_date TIMESTAMP NOT NULL,
                        end_date TIMESTAMP NOT NULL,
                        monthly_price REAL NOT NULL,
                        yearly_price REAL,
                        actual_paid REAL NOT NULL,
                        payment_method TEXT,
                        payment_status TEXT NOT NULL,
                        change_reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscription_history (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        subscription_type VARCHAR(50) NOT NULL,
                        billing_cycle VARCHAR(20) NOT NULL,
                        start_date TIMESTAMP NOT NULL,
                        end_date TIMESTAMP NOT NULL,
                        monthly_price DECIMAL(10,2) NOT NULL,
                        yearly_price DECIMAL(10,2),
                        actual_paid DECIMAL(10,2) NOT NULL,
                        payment_method VARCHAR(50),
                        payment_status VARCHAR(20) NOT NULL,
                        change_reason VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            # Create billing history table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS billing_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT,
                        invoice_number TEXT UNIQUE NOT NULL,
                        billing_date TIMESTAMP NOT NULL,
                        due_date TIMESTAMP NOT NULL,
                        amount REAL NOT NULL,
                        tax_amount REAL DEFAULT 0.00,
                        total_amount REAL NOT NULL,
                        currency TEXT DEFAULT 'USD',
                        payment_status TEXT DEFAULT 'pending',
                        payment_method TEXT,
                        paid_date TIMESTAMP,
                        invoice_pdf_path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS billing_history (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        invoice_number VARCHAR(50) UNIQUE NOT NULL,
                        billing_date TIMESTAMP NOT NULL,
                        due_date TIMESTAMP NOT NULL,
                        amount DECIMAL(10,2) NOT NULL,
                        tax_amount DECIMAL(10,2) DEFAULT 0.00,
                        total_amount DECIMAL(10,2) NOT NULL,
                        currency VARCHAR(3) DEFAULT 'USD',
                        payment_status VARCHAR(20) DEFAULT 'pending',
                        payment_method VARCHAR(50),
                        paid_date TIMESTAMP,
                        invoice_pdf_path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            # ========================================
            # VIOLATION EVENTS TABLE - Event-based violation tracking
            # ========================================
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS violation_events (
                        event_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL,
                        camera_id TEXT NOT NULL,
                        person_id TEXT NOT NULL,
                        violation_type TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL,
                        duration_seconds INTEGER,
                        snapshot_path TEXT,
                        resolution_snapshot_path TEXT,
                        severity TEXT DEFAULT 'warning',
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id),
                        FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS violation_events (
                        event_id VARCHAR(255) PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        camera_id VARCHAR(255) REFERENCES cameras(camera_id),
                        person_id VARCHAR(255) NOT NULL,
                        violation_type VARCHAR(100) NOT NULL,
                        start_time DOUBLE PRECISION NOT NULL,
                        end_time DOUBLE PRECISION,
                        duration_seconds INTEGER,
                        snapshot_path TEXT,
                        resolution_snapshot_path TEXT,
                        severity VARCHAR(20) DEFAULT 'warning',
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # ========================================
            # PERSON VIOLATIONS TABLE - Monthly violation tracking per person
            # ========================================
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS person_violations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        person_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        month TEXT NOT NULL,
                        violation_type TEXT NOT NULL,
                        violation_count INTEGER DEFAULT 0,
                        total_duration_seconds INTEGER DEFAULT 0,
                        penalty_amount REAL DEFAULT 0.0,
                        last_violation_date TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id),
                        UNIQUE(person_id, company_id, month, violation_type)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS person_violations (
                        id SERIAL PRIMARY KEY,
                        person_id VARCHAR(255) NOT NULL,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        month VARCHAR(7) NOT NULL,
                        violation_type VARCHAR(100) NOT NULL,
                        violation_count INTEGER DEFAULT 0,
                        total_duration_seconds INTEGER DEFAULT 0,
                        penalty_amount DECIMAL(10,2) DEFAULT 0.0,
                        last_violation_date TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(person_id, company_id, month, violation_type)
                    )
                ''')
            
            # ========================================
            # MONTHLY PENALTIES TABLE - Monthly penalty reports
            # ========================================
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS monthly_penalties (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL,
                        person_id TEXT,
                        month TEXT NOT NULL,
                        total_violations INTEGER DEFAULT 0,
                        total_duration_seconds INTEGER DEFAULT 0,
                        total_penalty REAL DEFAULT 0.0,
                        penalty_details TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id),
                        UNIQUE(company_id, person_id, month)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS monthly_penalties (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        person_id VARCHAR(255),
                        month VARCHAR(7) NOT NULL,
                        total_violations INTEGER DEFAULT 0,
                        total_duration_seconds INTEGER DEFAULT 0,
                        total_penalty DECIMAL(10,2) DEFAULT 0.0,
                        penalty_details JSON,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(company_id, person_id, month)
                    )
                ''')

            # Create payment methods table
            if self.db_type == 'sqlite':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payment_methods (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT,
                        payment_type TEXT NOT NULL,
                        card_last4 TEXT,
                        card_brand TEXT,
                        expiry_month INTEGER,
                        expiry_year INTEGER,
                        is_default BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payment_methods (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        payment_type VARCHAR(50) NOT NULL,
                        card_last4 VARCHAR(4),
                        card_brand VARCHAR(20),
                        expiry_month INTEGER,
                        expiry_year INTEGER,
                        is_default BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            # PostgreSQL autocommit kullanıyorsa commit'e gerek yok
            if not (self.db_type == 'postgresql' and getattr(conn, 'autocommit', False)):
                conn.commit()
                logger.info("✅ Database tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            try:
                if conn:
                    conn.rollback()
                    logger.info("🔄 Transaction rolled back due to error")
            except Exception as rollback_error:
                logger.warning(f"⚠️ Rollback error: {rollback_error}")
            return False
        finally:
            # Close connection properly
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
    
    def execute_query(self, query: str, params: tuple = None, fetch_all: bool = True) -> Any:
        """Execute database query with improved error handling and retry logic"""
        max_retries = 3
        retry_delay = 0.1  # 100ms
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                if conn is None:
                    logger.error("❌ Database connection failed")
                    return None
                
                cursor = conn.cursor()
            
                # Execute query
                cursor.execute(query, params or ())
                    
                # Handle different query types
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    result = cursor.rowcount
                    conn.commit()
                    logger.info(f"✅ Query executed successfully: {result} rows affected")
                    return result
                else:  # SELECT queries
                    if fetch_all:
                        result = cursor.fetchall()
                    else:
                        result = cursor.fetchone()
                    
                    # Check if result is empty
                    if not result:
                        logger.debug(f"ℹ️ Query returned no results")
                        return None if not fetch_all else []
                    
                    # Convert to list of dictionaries for better handling
                    try:
                        # Check if cursor.description exists (for SELECT queries)
                        if not cursor.description:
                            logger.warning(f"⚠️ No cursor description available")
                            return None if not fetch_all else []
                        
                        columns = [description[0] for description in cursor.description]
                        if fetch_all:
                            if isinstance(result, list) and len(result) > 0:
                                result = [dict(zip(columns, row)) for row in result]
                            else:
                                result = []
                        else:
                            # Single result - convert to dict
                            if isinstance(result, (tuple, list)):
                                result = dict(zip(columns, result))
                            elif hasattr(result, 'keys'):  # Already a dict-like object (PostgreSQL RealDictRow)
                                result = dict(result)
                            else:
                                result = dict(zip(columns, [result]))
                        
                        logger.debug(f"✅ Query executed successfully: {len(result) if isinstance(result, list) else 1} rows returned")
                        return result
                    except Exception as convert_error:
                        logger.error(f"❌ Result conversion error: {convert_error}")
                        return None if not fetch_all else []
                    
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"⚠️ Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"❌ Database query error: {e}")
                    logger.error(f"❌ Query traceback: {traceback.format_exc()}")
                    return None
                            
            except Exception as e:
                logger.error(f"❌ Database query error: {e}")
                logger.error(f"❌ Query traceback: {traceback.format_exc()}")
                return None
            finally:
                # Always close SQLite connections
                if conn and self.db_type == 'sqlite':
                    try:
                        conn.close()
                    except Exception as e:
                        logger.warning(f"⚠️ Error closing SQLite connection: {e}")

        logger.error(f"❌ Database query failed after {max_retries} attempts")
        return None
    
    def _check_and_sync_schema(self, conn) -> bool:
        """PostgreSQL schema'sını kontrol et ve senkronize et"""
        try:
            cursor = conn.cursor()
            
            # 1. Temel tabloların varlığını kontrol et
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('companies', 'users', 'cameras', 'sessions', 'detections', 'violations')
            """)
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            required_tables = ['companies', 'users', 'cameras', 'sessions', 'detections', 'violations']
            missing_tables = [t for t in required_tables if t not in existing_tables]
            
            if missing_tables:
                logger.warning(f"⚠️ Missing tables: {missing_tables}, will create them")
                return False
            
            # 2. companies tablosundaki kritik kolonları kontrol et
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'companies' AND table_schema = 'public'
                AND column_name IN ('account_type', 'demo_expires_at', 'demo_limits', 'billing_cycle', 'profile_image', 'ppe_requirements', 'compliance_settings')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            required_columns = ['account_type', 'demo_expires_at', 'demo_limits', 'billing_cycle', 'profile_image', 'ppe_requirements', 'compliance_settings']
            missing_columns = [c for c in required_columns if c not in existing_columns]
            
            if missing_columns:
                logger.info(f"🔧 Adding missing columns to companies table: {missing_columns}")
                
                # Eksik kolonları ekle
                column_definitions = {
                    'account_type': 'VARCHAR(20) DEFAULT \'full\'',
                    'demo_expires_at': 'TIMESTAMP',
                    'demo_limits': 'JSON',
                    'billing_cycle': 'VARCHAR(20) DEFAULT \'monthly\'',
                    'next_billing_date': 'TIMESTAMP',
                    'auto_renewal': 'BOOLEAN DEFAULT TRUE',
                    'payment_method': 'VARCHAR(50)',
                    'payment_status': 'VARCHAR(20) DEFAULT \'active\'',
                    'current_balance': 'DECIMAL(10,2) DEFAULT 0.00',
                    'total_paid': 'DECIMAL(10,2) DEFAULT 0.00',
                    'last_payment_date': 'TIMESTAMP',
                    'last_payment_amount': 'DECIMAL(10,2)',
                    'profile_image': 'TEXT',
                    'ppe_requirements': 'JSON',
                    'compliance_settings': 'JSON'
                }
                
                for column in missing_columns:
                    if column in column_definitions:
                        try:
                            cursor.execute(f'ALTER TABLE companies ADD COLUMN IF NOT EXISTS {column} {column_definitions[column]}')
                            logger.info(f"✅ Added column: {column}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to add column {column}: {e}")
            
            # 3. detections tablosundaki eksik kolonları kontrol et
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'detections' AND table_schema = 'public'
                AND column_name IN ('people_detected', 'total_people')
            """)
            existing_detection_columns = [row[0] for row in cursor.fetchall()]
            
            required_detection_columns = ['people_detected', 'total_people']
            missing_detection_columns = [c for c in required_detection_columns if c not in existing_detection_columns]
            
            if missing_detection_columns:
                logger.info(f"🔧 Adding missing columns to detections table: {missing_detection_columns}")
                for column in missing_detection_columns:
                    try:
                        if column == 'people_detected':
                            cursor.execute('ALTER TABLE detections ADD COLUMN IF NOT EXISTS people_detected INTEGER DEFAULT 0')
                        elif column == 'total_people':
                            cursor.execute('ALTER TABLE detections ADD COLUMN IF NOT EXISTS total_people INTEGER DEFAULT 0')
                        logger.info(f"✅ Added column to detections: {column}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to add column {column} to detections: {e}")
            
            # 4. Ek tabloları kontrol et
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('subscription_history', 'billing_history', 'payment_methods', 'alerts')
            """)
            existing_extra_tables = [row[0] for row in cursor.fetchall()]
            
            extra_tables = ['subscription_history', 'billing_history', 'payment_methods', 'alerts']
            missing_extra_tables = [t for t in extra_tables if t not in existing_extra_tables]
            
            if missing_extra_tables:
                logger.info(f"🔧 Creating missing extra tables: {missing_extra_tables}")
                # Bu tabloları oluşturmak için normal init_database akışına devam et
                return False
            
            logger.info("✅ PostgreSQL schema is up to date")
            return True
            
        except Exception as e:
            logger.error(f"❌ Schema sync error: {e}")
            return False

    # DVR System Methods
    def add_dvr_system(self, company_id: str, dvr_data: Dict[str, Any]) -> bool:
        """Add DVR system to database"""
        try:
            logger.info(f"🔧 Adding DVR system: {dvr_data.get('name')} for company: {company_id}")
            
            query = '''
                INSERT INTO dvr_systems (
                    dvr_id, company_id, name, ip_address, port, username, password,
                    dvr_type, protocol, api_path, rtsp_port, max_channels, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            params = (
                dvr_data['dvr_id'],
                company_id,
                dvr_data['name'],
                dvr_data['ip_address'],
                dvr_data.get('port', 80),
                dvr_data.get('username', 'admin'),
                dvr_data.get('password', ''),
                dvr_data.get('dvr_type', 'generic'),
                dvr_data.get('protocol', 'http'),
                dvr_data.get('api_path', '/api'),
                dvr_data.get('rtsp_port', 554),
                dvr_data.get('max_channels', 16),
                'active'
            )
            
            logger.info(f"🔧 SQL Query: {query}")
            logger.info(f"🔧 Parameters: {params}")
            
            result = self.execute_query(query, params, fetch_all=False)
            logger.info(f"🔧 Query result: {result}")
            
            if result is not None and result > 0:
                logger.info(f"✅ DVR system added successfully: {dvr_data.get('name')}")
                return True
            else:
                logger.error(f"❌ DVR system add failed: {dvr_data.get('name')} - rowcount: {result}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Add DVR system error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False
    
    def get_dvr_systems(self, company_id: str) -> List[Dict[str, Any]]:
        """Get all DVR systems for a company"""
        try:
            query = '''
                SELECT * FROM dvr_systems 
                WHERE company_id = ? 
                ORDER BY created_at DESC
            '''
            
            result = self.execute_query(query, (company_id,))
            if result:
                logger.info(f"✅ Retrieved {len(result)} DVR systems for company {company_id}")
            return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR systems error: {e}")
            return []
    
    def get_dvr_system(self, company_id: str, dvr_id: str) -> Optional[Dict[str, Any]]:
        """Get specific DVR system"""
        try:
            query = '''
                SELECT * FROM dvr_systems 
                WHERE company_id = ? AND dvr_id = ?
            '''
            
            result = self.execute_query(query, (company_id, dvr_id), fetch_all=False)
            if result:
                logger.info(f"✅ Retrieved DVR system: {dvr_id}")
                return result
            return None
            
        except Exception as e:
            logger.error(f"❌ Get DVR system error: {e}")
            return None
    
    def update_dvr_system(self, company_id: str, dvr_id: str, dvr_data: Dict[str, Any]) -> bool:
        """Update DVR system"""
        try:
            query = '''
                UPDATE dvr_systems 
                SET name = ?, ip_address = ?, port = ?, username = ?, password = ?,
                    dvr_type = ?, protocol = ?, api_path = ?, rtsp_port = ?, 
                    max_channels = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ? AND dvr_id = ?
            '''
            
            params = (
                dvr_data.get('name'),
                dvr_data.get('ip_address'),
                dvr_data.get('port', 80),
                dvr_data.get('username', 'admin'),
                dvr_data.get('password', ''),
                dvr_data.get('dvr_type', 'generic'),
                dvr_data.get('protocol', 'http'),
                dvr_data.get('api_path', '/api'),
                dvr_data.get('rtsp_port', 554),
                dvr_data.get('max_channels', 16),
                dvr_data.get('status', 'active'),
                company_id,
                dvr_id
            )
            
            result = self.execute_query(query, params, fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR system error: {e}")
            return False
    
    def delete_dvr_system(self, company_id: str, dvr_id: str) -> bool:
        """Delete DVR system and all related data"""
        try:
            # First delete related streams
            stream_query = '''
                DELETE FROM dvr_streams 
                WHERE company_id = ? AND dvr_id = ?
            '''
            self.execute_query(stream_query, (company_id, dvr_id), fetch_all=False)
            
            # Then delete related channels
            channel_query = '''
                DELETE FROM dvr_channels 
                WHERE company_id = ? AND dvr_id = ?
            '''
            self.execute_query(channel_query, (company_id, dvr_id), fetch_all=False)
            
            # Finally delete the DVR system
            dvr_query = '''
                DELETE FROM dvr_systems 
                WHERE company_id = ? AND dvr_id = ?
            '''
            
            result = self.execute_query(dvr_query, (company_id, dvr_id), fetch_all=False)
            logger.info(f"✅ DVR system deleted: {dvr_id}")
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Delete DVR system error: {e}")
            return False
    
    # DVR Channel Methods
    def add_dvr_channel(self, company_id: str, dvr_id: str, channel_data: Dict[str, Any]) -> bool:
        """Add DVR channel to database"""
        try:
            logger.info(f"🔧 Adding DVR channel: {channel_data.get('name')} for DVR: {dvr_id}")
            
            # Use INSERT OR REPLACE to handle conflicts
            if self.db_type == 'sqlite':
                query = '''
                    INSERT OR REPLACE INTO dvr_channels (
                        channel_id, dvr_id, company_id, name, channel_number,
                        status, resolution_width, resolution_height, fps, rtsp_path, http_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
            else:  # PostgreSQL
                query = '''
                    INSERT INTO dvr_channels (
                        channel_id, dvr_id, company_id, name, channel_number,
                        status, resolution_width, resolution_height, fps, rtsp_path, http_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        resolution_width = EXCLUDED.resolution_width,
                        resolution_height = EXCLUDED.resolution_height,
                        fps = EXCLUDED.fps,
                        rtsp_path = EXCLUDED.rtsp_path,
                        http_path = EXCLUDED.http_path,
                        updated_at = CURRENT_TIMESTAMP
                '''
            
            params = (
                channel_data['channel_id'],
                dvr_id,
                company_id,
                channel_data['name'],
                channel_data['channel_number'],
                channel_data.get('status', 'inactive'),
                channel_data.get('resolution_width', 1920),
                channel_data.get('resolution_height', 1080),
                channel_data.get('fps', 25),
                channel_data.get('rtsp_path', ''),
                channel_data.get('http_path', '')
            )
            
            logger.info(f"🔧 Channel SQL Query: {query}")
            logger.info(f"🔧 Channel Parameters: {params}")
            
            result = self.execute_query(query, params, fetch_all=False)
            logger.info(f"🔧 Channel Query result: {result}")
            
            if result is not None and result > 0:
                logger.info(f"✅ DVR channel added successfully: {channel_data.get('name')}")
                return True
            else:
                logger.error(f"❌ DVR channel add failed: {channel_data.get('name')} - rowcount: {result}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Add DVR channel error: {e}")
            import traceback
            logger.error(f"❌ Channel traceback: {traceback.format_exc()}")
            return False
    
    def get_dvr_channels(self, company_id: str, dvr_id: str) -> List[Dict[str, Any]]:
        """Get all channels for a DVR system"""
        try:
            query = '''
                SELECT * FROM dvr_channels 
                WHERE company_id = ? AND dvr_id = ? 
                ORDER BY channel_number
            '''
            
            result = self.execute_query(query, (company_id, dvr_id))
            if result:
                logger.info(f"✅ Retrieved {len(result)} channels for DVR {dvr_id}")
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR channels error: {e}")
            return []
    
    def update_dvr_channel_status(self, company_id: str, channel_id: str, status: str) -> bool:
        """Update DVR channel status"""
        try:
            query = '''
                UPDATE dvr_channels 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ? AND channel_id = ?
            '''
            
            result = self.execute_query(query, (status, company_id, channel_id), fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR channel status error: {e}")
            return False
    
    # DVR Stream Methods
    def add_dvr_stream(self, company_id: str, dvr_id: str, channel_id: str, stream_url: str) -> bool:
        """Add active DVR stream"""
        try:
            stream_id = f"stream_{dvr_id}_{channel_id}_{int(datetime.now().timestamp())}"
            
            query = '''
                INSERT INTO dvr_streams (
                    stream_id, dvr_id, company_id, channel_id, stream_url, status
                ) VALUES (?, ?, ?, ?, ?, ?)
            '''
            
            params = (stream_id, dvr_id, company_id, channel_id, stream_url, 'active')
            
            result = self.execute_query(query, params, fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Add DVR stream error: {e}")
            return False
    
    def update_dvr_stream_status(self, company_id: str, stream_id: str, status: str, fps: float = 0) -> bool:
        """Update DVR stream status"""
        try:
            query = '''
                UPDATE dvr_streams 
                SET status = ?, fps = ?, updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ? AND stream_id = ?
            '''
            
            result = self.execute_query(query, (status, fps, company_id, stream_id), fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR stream status error: {e}")
            return False
    
    def get_active_dvr_streams(self, company_id: str) -> List[Dict[str, Any]]:
        """Get active DVR streams for a company"""
        try:
            query = '''
                SELECT * FROM dvr_streams 
                WHERE company_id = ? AND status = 'active'
                ORDER BY start_time DESC
            '''
            
            result = self.execute_query(query, (company_id,))
            if result:
                logger.info(f"✅ Retrieved {len(result)} active streams for company {company_id}")
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get active DVR streams error: {e}")
            return []

    # DVR Detection Results Methods
    def add_dvr_detection_result(self, result_data: Dict[str, Any]) -> bool:
        """Add DVR detection result to database"""
        try:
            query = """
                INSERT INTO dvr_detection_results 
                (stream_id, company_id, total_people, compliant_people, violations_count, 
                 missing_ppe, detection_confidence, detection_time, frame_timestamp, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            if self.db_type == 'sqlite':
                query = query.replace('%s', '?')
            
            params = (
                result_data['stream_id'],
                result_data['company_id'],
                result_data['total_people'],
                result_data['compliant_people'],
                result_data['violations_count'],
                result_data['missing_ppe'],
                result_data['detection_confidence'],
                result_data['detection_time'],
                result_data['frame_timestamp'],
                datetime.now().isoformat()
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection result saved: {result_data['stream_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add DVR detection result error: {e}")
            return False
    
    def get_dvr_detection_results(self, stream_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get DVR detection results for a stream"""
        try:
            query = """
                SELECT * FROM dvr_detection_results 
                WHERE stream_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            if self.db_type == 'sqlite':
                query = query.replace('%s', '?')
            
            result = self.execute_query(query, (stream_id, limit))
            
            if result and isinstance(result, list):
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection results error: {e}")
            return []
    
    def add_dvr_detection_session(self, session_data: Dict[str, Any]) -> bool:
        """Add DVR detection session to database"""
        try:
            if self.db_type == 'sqlite':
                query = """
                    INSERT OR REPLACE INTO dvr_detection_sessions 
                    (session_id, dvr_id, company_id, channels, detection_mode, status, start_time, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
            else:  # PostgreSQL
                query = """
                    INSERT INTO dvr_detection_sessions 
                    (session_id, dvr_id, company_id, channels, detection_mode, status, start_time, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        start_time = EXCLUDED.start_time
                """
            
            params = (
                session_data['session_id'],
                session_data['dvr_id'],
                session_data['company_id'],
                session_data['channels'],
                session_data['detection_mode'],
                session_data['status'],
                session_data['start_time'],
                datetime.now().isoformat()
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection session saved: {session_data['session_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add DVR detection session error: {e}")
            return False
    
    def update_dvr_detection_session(self, session_id: str, update_data: Dict[str, Any]) -> bool:
        """Update DVR detection session"""
        try:
            query = """
                UPDATE dvr_detection_sessions 
                SET status = %s, end_time = %s, updated_at = %s
                WHERE session_id = %s
            """
            
            if self.db_type == 'sqlite':
                query = query.replace('%s', '?')
            
            params = (
                update_data['status'],
                update_data.get('end_time'),
                datetime.now().isoformat(),
                session_id
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection session updated: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Update DVR detection session error: {e}")
            return False
    
    def get_dvr_detection_sessions(self, company_id: str, dvr_id: str = None) -> List[Dict[str, Any]]:
        """Get DVR detection sessions"""
        try:
            if dvr_id:
                query = """
                    SELECT * FROM dvr_detection_sessions 
                    WHERE company_id = %s AND dvr_id = %s
                    ORDER BY start_time DESC
                """
                params = (company_id, dvr_id)
            else:
                query = """
                    SELECT * FROM dvr_detection_sessions 
                    WHERE company_id = %s
                    ORDER BY start_time DESC
                """
                params = (company_id,)
            
            if self.db_type == 'sqlite':
                query = query.replace('%s', '?')
            
            result = self.execute_query(query, params)
            
            if result and isinstance(result, list):
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection sessions error: {e}")
            return []
    
    # IP Camera Detection Methods
    def add_camera_detection_result(self, detection_data: Dict[str, Any]) -> bool:
        """Add IP camera detection result to database"""
        try:
            if self.db_type == 'sqlite':
                query = """
                    INSERT INTO detections (
                        company_id, camera_id, detection_type, confidence,
                        people_detected, ppe_compliant, violations_count, total_people
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
            else:  # PostgreSQL
                query = """
                    INSERT INTO detections (
                        company_id, camera_id, detection_type, confidence,
                        people_detected, ppe_compliant, violations_count, total_people
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
            
            params = (
                detection_data.get('company_id'),
                detection_data.get('camera_id'),
                detection_data.get('detection_type', 'ppe'),
                detection_data.get('confidence', 0.0),
                detection_data.get('people_detected', 0),
                detection_data.get('ppe_compliant', 0),
                detection_data.get('violations_count', 0),
                detection_data.get('total_people', 0)
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ Camera detection result saved: {detection_data.get('camera_id')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add camera detection result error: {e}")
            return False
    
    def get_camera_detection_results(self, camera_id: str, company_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get IP camera detection results"""
        try:
            if self.db_type == 'sqlite':
                query = """
                    SELECT * FROM detections
                    WHERE camera_id = ? AND company_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
            else:  # PostgreSQL
                query = """
                    SELECT * FROM detections
                    WHERE camera_id = %s AND company_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """
            
            params = (camera_id, company_id, limit)
            result = self.execute_query(query, params, fetch_all=True)
            
            if result and isinstance(result, list):
                # Convert to dict format
                detections = []
                for row in result:
                    detection = {
                        'id': row[0] if len(row) > 0 else None,
                        'camera_id': row[1] if len(row) > 1 else camera_id,
                        'company_id': row[2] if len(row) > 2 else company_id,
                        'detection_type': row[3] if len(row) > 3 else 'ppe',
                        'timestamp': row[4] if len(row) > 4 else None,
                        'confidence': row[5] if len(row) > 5 else 0.0,
                        'people_detected': row[6] if len(row) > 6 else 0,
                        'ppe_compliant': row[7] if len(row) > 7 else 0,
                        'violations_count': row[8] if len(row) > 8 else 0,
                        'total_people': row[6] if len(row) > 6 else 0,
                        'compliant_people': row[7] if len(row) > 7 else 0
                    }
                    detections.append(detection)
                return detections
            return []
            
        except Exception as e:
            logger.error(f"❌ Get camera detection results error: {e}")
            return []
    
    def get_latest_camera_detection(self, camera_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get latest detection result for a camera"""
        try:
            results = self.get_camera_detection_results(camera_id, company_id, limit=1)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"❌ Get latest camera detection error: {e}")
            return None
    
    def get_camera_by_id(self, camera_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """
        Get camera by ID and company ID
        
        Args:
            camera_id: Camera ID
            company_id: Company ID
            
        Returns:
            Camera dictionary or None if not found
        """
        try:
            if self.db_type == 'sqlite':
                query = '''
                    SELECT camera_id, company_id, camera_name, location, ip_address, 
                           port, rtsp_url, username, password, protocol, stream_path,
                           auth_type, resolution, fps, quality, audio_enabled,
                           night_vision, motion_detection, recording_enabled,
                           camera_type, status, last_detection, last_test_time,
                           connection_retries, timeout, created_at, updated_at
                    FROM cameras 
                    WHERE camera_id = ? AND company_id = ? AND status != 'deleted'
                '''
            else:  # PostgreSQL
                query = '''
                    SELECT camera_id, company_id, camera_name, location, ip_address, 
                           port, rtsp_url, username, password, protocol, stream_path,
                           auth_type, resolution, fps, quality, audio_enabled,
                           night_vision, motion_detection, recording_enabled,
                           camera_type, status, last_detection, last_test_time,
                           connection_retries, timeout, created_at, updated_at
                    FROM cameras 
                    WHERE camera_id = %s AND company_id = %s AND status != 'deleted'
                '''
            
            result = self.execute_query(query, (camera_id, company_id), fetch_one=True)
            
            if result:
                if hasattr(result, 'keys'):  # PostgreSQL RealDictRow
                    return dict(result)
                else:  # SQLite tuple or list
                    if isinstance(result, (list, tuple)) and len(result) >= 2:
                        return {
                            'camera_id': result[0],
                            'company_id': result[1],
                            'camera_name': result[2] if len(result) > 2 else None,
                            'location': result[3] if len(result) > 3 else None,
                            'ip_address': result[4] if len(result) > 4 else None,
                            'port': result[5] if len(result) > 5 else 8080,
                            'rtsp_url': result[6] if len(result) > 6 else None,
                            'username': result[7] if len(result) > 7 else None,
                            'password': result[8] if len(result) > 8 else None,
                            'protocol': result[9] if len(result) > 9 else 'http',
                            'stream_path': result[10] if len(result) > 10 else '/video',
                            'auth_type': result[11] if len(result) > 11 else 'basic',
                            'resolution': result[12] if len(result) > 12 else '1920x1080',
                            'fps': result[13] if len(result) > 13 else 25,
                            'quality': result[14] if len(result) > 14 else 80,
                            'audio_enabled': result[15] if len(result) > 15 else False,
                            'night_vision': result[16] if len(result) > 16 else False,
                            'motion_detection': result[17] if len(result) > 17 else True,
                            'recording_enabled': result[18] if len(result) > 18 else True,
                            'camera_type': result[19] if len(result) > 19 else 'ip_camera',
                            'status': result[20] if len(result) > 20 else 'active',
                            'last_detection': result[21] if len(result) > 21 else None,
                            'last_test_time': result[22] if len(result) > 22 else None,
                            'connection_retries': result[23] if len(result) > 23 else 3,
                            'timeout': result[24] if len(result) > 24 else 10,
                            'created_at': result[25] if len(result) > 25 else None,
                            'updated_at': result[26] if len(result) > 26 else None
                        }
            return None
            
        except Exception as e:
            logger.error(f"❌ Get camera by ID error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None
    
    def get_company_detection_stats(self, company_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get detection statistics for a company"""
        try:
            if self.db_type == 'sqlite':
                query = """
                    SELECT 
                        COUNT(*) as total_detections,
                        SUM(people_detected) as total_people,
                        SUM(ppe_compliant) as total_compliant,
                        SUM(violations_count) as total_violations,
                        AVG(confidence) as avg_confidence
                    FROM detections
                    WHERE company_id = ?
                    AND timestamp >= datetime('now', '-' || ? || ' hours')
                """
            else:  # PostgreSQL
                query = """
                    SELECT 
                        COUNT(*) as total_detections,
                        SUM(people_detected) as total_people,
                        SUM(ppe_compliant) as total_compliant,
                        SUM(violations_count) as total_violations,
                        AVG(confidence) as avg_confidence
                    FROM detections
                    WHERE company_id = %s
                    AND timestamp >= NOW() - INTERVAL '%s hours'
                """
            
            params = (company_id, hours)
            result = self.execute_query(query, params, fetch_all=True)
            
            if result and len(result) > 0:
                row = result[0]
                # Convert row to dict
                stats = {
                    'total_detections': row[0] if len(row) > 0 else 0,
                    'total_people': row[1] if len(row) > 1 else 0,
                    'total_compliant': row[2] if len(row) > 2 else 0,
                    'total_violations': row[3] if len(row) > 3 else 0,
                    'avg_confidence': row[4] if len(row) > 4 else 0.0
                }
                return {
                    'total_detections': stats.get('total_detections', 0) or 0,
                    'total_people': stats.get('total_people', 0) or 0,
                    'total_compliant': stats.get('total_compliant', 0) or 0,
                    'total_violations': stats.get('total_violations', 0) or 0,
                    'avg_confidence': float(stats.get('avg_confidence', 0) or 0),
                    'compliance_rate': (stats.get('total_compliant', 0) or 0) / max(stats.get('total_people', 1) or 1, 1) * 100
                }
            return {
                'total_detections': 0,
                'total_people': 0,
                'total_compliant': 0,
                'total_violations': 0,
                'avg_confidence': 0.0,
                'compliance_rate': 0.0
            }
            
        except Exception as e:
            logger.error(f"❌ Get company detection stats error: {e}")
            return {}

    # ========================================
    # VIOLATION EVENTS METHODS
    # ========================================
    
    def add_violation_event(self, event_data: Dict) -> bool:
        """Yeni ihlal event'i kaydet"""
        try:
            if self.db_type == 'sqlite':
                query = '''
                    INSERT INTO violation_events (
                        event_id, company_id, camera_id, person_id, violation_type,
                        start_time, end_time, duration_seconds, snapshot_path, severity, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
            else:  # PostgreSQL
                query = '''
                    INSERT INTO violation_events (
                        event_id, company_id, camera_id, person_id, violation_type,
                        start_time, end_time, duration_seconds, snapshot_path, severity, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                '''
            
            params = (
                event_data['event_id'],
                event_data['company_id'],
                event_data['camera_id'],
                event_data['person_id'],
                event_data['violation_type'],
                event_data['start_time'],
                event_data.get('end_time'),
                event_data.get('duration_seconds'),
                event_data.get('snapshot_path'),
                event_data.get('severity', 'warning'),
                event_data.get('status', 'active')
            )
            
            self.execute_query(query, params)
            logger.debug(f"✅ Violation event saved: {event_data['event_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add violation event error: {e}")
            return False
    
    def update_violation_event(self, event_id: str, update_data: Dict) -> bool:
        """İhlal event'ini güncelle (bittiğinde)"""
        try:
            if self.db_type == 'sqlite':
                query = '''
                    UPDATE violation_events 
                    SET end_time = ?, duration_seconds = ?, status = ?, resolution_snapshot_path = ?
                    WHERE event_id = ?
                '''
            else:  # PostgreSQL
                query = '''
                    UPDATE violation_events 
                    SET end_time = %s, duration_seconds = %s, status = %s, resolution_snapshot_path = %s
                    WHERE event_id = %s
                '''
            
            params = (
                update_data.get('end_time'),
                update_data.get('duration_seconds'),
                update_data.get('status', 'resolved'),
                update_data.get('resolution_snapshot_path'),
                event_id
            )
            
            self.execute_query(query, params)
            logger.debug(f"✅ Violation event updated: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Update violation event error: {e}")
            return False
    
    def get_active_violations(self, camera_id: Optional[str] = None, company_id: Optional[str] = None) -> List[Dict]:
        """Aktif ihlalleri getir"""
        try:
            if self.db_type == 'sqlite':
                if camera_id:
                    query = '''
                        SELECT * FROM violation_events 
                        WHERE camera_id = ? AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = (camera_id,)
                elif company_id:
                    query = '''
                        SELECT * FROM violation_events 
                        WHERE company_id = ? AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = (company_id,)
                else:
                    query = "SELECT * FROM violation_events WHERE status = 'active' ORDER BY start_time DESC"
                    params = ()
            else:  # PostgreSQL
                if camera_id:
                    query = '''
                        SELECT * FROM violation_events 
                        WHERE camera_id = %s AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = (camera_id,)
                elif company_id:
                    query = '''
                        SELECT * FROM violation_events 
                        WHERE company_id = %s AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = (company_id,)
                else:
                    query = "SELECT * FROM violation_events WHERE status = 'active' ORDER BY start_time DESC"
                    params = ()
            
            results = self.execute_query(query, params, fetch_all=True)
            
            violations = []
            for row in results:
                violations.append({
                    'event_id': row[0],
                    'company_id': row[1],
                    'camera_id': row[2],
                    'person_id': row[3],
                    'violation_type': row[4],
                    'start_time': row[5],
                    'end_time': row[6],
                    'duration_seconds': row[7],
                    'snapshot_path': row[8],
                    'severity': row[9],
                    'status': row[10]
                })
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get active violations error: {e}")
            return []
    
    def get_violation_history(self, camera_id: str, hours: int = 24, limit: int = 100) -> List[Dict]:
        """İhlal geçmişini getir"""
        try:
            import time
            cutoff_time = time.time() - (hours * 3600)
            
            if self.db_type == 'sqlite':
                query = '''
                    SELECT * FROM violation_events 
                    WHERE camera_id = ? AND start_time >= ?
                    ORDER BY start_time DESC
                    LIMIT ?
                '''
            else:  # PostgreSQL
                query = '''
                    SELECT * FROM violation_events 
                    WHERE camera_id = %s AND start_time >= %s
                    ORDER BY start_time DESC
                    LIMIT %s
                '''
            
            results = self.execute_query(query, (camera_id, cutoff_time, limit), fetch_all=True)
            
            violations = []
            for row in results:
                violations.append({
                    'event_id': row[0],
                    'company_id': row[1],
                    'camera_id': row[2],
                    'person_id': row[3],
                    'violation_type': row[4],
                    'start_time': row[5],
                    'end_time': row[6],
                    'duration_seconds': row[7],
                    'snapshot_path': row[8],
                    'severity': row[9],
                    'status': row[10]
                })
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get violation history error: {e}")
            return []
    
    # ========================================
    # PERSON VIOLATIONS METHODS
    # ========================================
    
    def update_person_violation_stats(self, person_id: str, company_id: str, violation_type: str, duration_seconds: int) -> bool:
        """Kişi ihlal istatistiklerini güncelle"""
        try:
            from datetime import datetime
            month = datetime.now().strftime('%Y-%m')
            
            if self.db_type == 'sqlite':
                # Önce mevcut kaydı kontrol et
                check_query = '''
                    SELECT id, violation_count, total_duration_seconds 
                    FROM person_violations 
                    WHERE person_id = ? AND company_id = ? AND month = ? AND violation_type = ?
                '''
                existing = self.execute_query(check_query, (person_id, company_id, month, violation_type), fetch_one=True)
                
                if existing:
                    # Güncelle
                    update_query = '''
                        UPDATE person_violations 
                        SET violation_count = violation_count + 1,
                            total_duration_seconds = total_duration_seconds + ?,
                            last_violation_date = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    '''
                    self.execute_query(update_query, (duration_seconds, existing[0]))
                else:
                    # Yeni kayıt
                    insert_query = '''
                        INSERT INTO person_violations (
                            person_id, company_id, month, violation_type,
                            violation_count, total_duration_seconds, last_violation_date
                        ) VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
                    '''
                    self.execute_query(insert_query, (person_id, company_id, month, violation_type, duration_seconds))
            else:  # PostgreSQL
                # UPSERT kullan
                query = '''
                    INSERT INTO person_violations (
                        person_id, company_id, month, violation_type,
                        violation_count, total_duration_seconds, last_violation_date
                    ) VALUES (%s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (person_id, company_id, month, violation_type)
                    DO UPDATE SET
                        violation_count = person_violations.violation_count + 1,
                        total_duration_seconds = person_violations.total_duration_seconds + EXCLUDED.total_duration_seconds,
                        last_violation_date = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                '''
                self.execute_query(query, (person_id, company_id, month, violation_type, duration_seconds))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Update person violation stats error: {e}")
            return False
    
    def get_person_monthly_violations(self, person_id: str, company_id: str, month: str) -> List[Dict]:
        """Kişinin aylık ihlal istatistiklerini getir"""
        try:
            if self.db_type == 'sqlite':
                query = '''
                    SELECT * FROM person_violations 
                    WHERE person_id = ? AND company_id = ? AND month = ?
                '''
            else:  # PostgreSQL
                query = '''
                    SELECT * FROM person_violations 
                    WHERE person_id = %s AND company_id = %s AND month = %s
                '''
            
            results = self.execute_query(query, (person_id, company_id, month), fetch_all=True)
            
            violations = []
            for row in results:
                violations.append({
                    'id': row[0],
                    'person_id': row[1],
                    'company_id': row[2],
                    'month': row[3],
                    'violation_type': row[4],
                    'violation_count': row[5],
                    'total_duration_seconds': row[6],
                    'penalty_amount': row[7],
                    'last_violation_date': row[8]
                })
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get person monthly violations error: {e}")
            return []


# Global database adapter instance
db_adapter = DatabaseAdapter()

def get_db_adapter() -> DatabaseAdapter:
    """Get global database adapter instance"""
    return db_adapter 

def get_camera_discovery_manager() -> 'CameraDiscoveryManager':
    """Get camera discovery manager instance"""
    return CameraDiscoveryManager(db_adapter)

class CameraDiscoveryManager:
    """Keşfedilen kameraları veritabanı ile senkronize etmek için manager"""
    
    def __init__(self, db_adapter: DatabaseAdapter):
        self.db_adapter = db_adapter
        self.logger = logging.getLogger(__name__)
    
    def sync_discovered_cameras_to_db(self, company_id: str, discovered_cameras: List[Dict]) -> Dict[str, Any]:
        """
        Keşfedilen kameraları veritabanına kaydet/güncelle
        
        Args:
            company_id: Şirket ID'si
            discovered_cameras: Keşfedilen kameralar listesi
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            result = {
                'total_discovered': len(discovered_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': []
            }
            
            for camera_info in discovered_cameras:
                try:
                    # Kamera bilgilerini parse et
                    camera_data = self._parse_camera_info(camera_info)
                    
                    # Veritabanında var mı kontrol et
                    existing_camera = self._check_camera_exists(
                        company_id, 
                        camera_data['ip_address'], 
                        camera_data['port']
                    )
                    
                    if existing_camera:
                        # Güncelle
                        if self._update_camera(company_id, existing_camera['camera_id'], camera_data):
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1
                    else:
                        # Yeni kamera ekle
                        if self._add_discovered_camera(company_id, camera_data):
                            result['added'] += 1
                        else:
                            result['errors'].append(f"Failed to add camera {camera_data['name']}")
                            
                except Exception as e:
                    result['errors'].append(f"Error processing camera {camera_info.get('ip', 'unknown')}: {str(e)}")
                    self.logger.error(f"Error processing camera: {e}")
            
            self.logger.info(f"✅ Camera sync complete: {result['added']} added, {result['updated']} updated")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Camera sync failed: {e}")
            return {
                'total_discovered': len(discovered_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [str(e)]
            }
    
    def _parse_camera_info(self, camera_info: Dict) -> Dict[str, Any]:
        """Keşfedilen kamera bilgisini parse et"""
        return {
            'name': camera_info.get('brand', 'Unknown') + f" Camera ({camera_info.get('ip', 'Unknown')})",
            'ip_address': camera_info.get('ip', ''),
            'port': camera_info.get('port', 554),
            'rtsp_url': camera_info.get('rtsp_url', ''),
            'location': f"Discovered - {camera_info.get('brand', 'Unknown')}",
            'resolution': camera_info.get('resolution', '1920x1080'),
            'fps': camera_info.get('fps', 25),
            'brand': camera_info.get('brand', 'Unknown'),
            'model': camera_info.get('model', 'Unknown')
        }
    
    def _check_camera_exists(self, company_id: str, ip_address: str, port: int) -> Optional[Dict]:
        """Kameranın veritabanında olup olmadığını kontrol et"""
        try:
            query = '''
                SELECT camera_id, camera_name, status 
                FROM cameras 
                WHERE company_id = ? AND ip_address = ? AND status = 'active'
            '''
            result = self.db_adapter.execute_query(query, (company_id, ip_address), fetch_one=True)
            
            if result:
                return {
                    'camera_id': result[0],
                    'camera_name': result[1],
                    'status': result[2]
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking camera existence: {e}")
            return None
    
    def _add_discovered_camera(self, company_id: str, camera_data: Dict) -> bool:
        """Yeni keşfedilen kamerayı veritabanına ekle"""
        try:
            import uuid
            
            # Yeni kamera ID'si oluştur
            camera_id = str(uuid.uuid4())
            
            # RTSP URL oluştur eğer yoksa
            if not camera_data['rtsp_url']:
                camera_data['rtsp_url'] = f"rtsp://{camera_data['ip_address']}:{camera_data['port']}/stream"
            
            query = '''
                INSERT INTO cameras (
                    camera_id, company_id, camera_name, location, ip_address, 
                    rtsp_url, resolution, fps, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'discovered', CURRENT_TIMESTAMP)
            '''
            
            params = (
                camera_id,
                company_id,
                camera_data['name'],
                camera_data['location'],
                camera_data['ip_address'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps']
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Added discovered camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to add discovered camera: {e}")
            return False
    
    def _update_camera(self, company_id: str, camera_id: str, camera_data: Dict) -> bool:
        """Mevcut kamerayı güncelle"""
        try:
            query = '''
                UPDATE cameras 
                SET camera_name = ?, location = ?, rtsp_url = ?, 
                    resolution = ?, fps = ?, updated_at = CURRENT_TIMESTAMP
                WHERE camera_id = ? AND company_id = ?
            '''
            
            params = (
                camera_data['name'],
                camera_data['location'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps'],
                camera_id,
                company_id
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Updated camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update camera: {e}")
            return False
    
    def sync_config_cameras_to_db(self, company_id: str, config_cameras: Dict) -> Dict[str, Any]:
        """
        Config dosyasındaki kameraları veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si  
            config_cameras: Config dosyasındaki kameralar
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            result = {
                'total_config': len(config_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': []
            }
            
            for camera_id, config in config_cameras.items():
                try:
                    # Config'den IP ve port çıkar
                    rtsp_url = config.get('rtsp_url', '')
                    ip_address = self._extract_ip_from_rtsp(rtsp_url)
                    port = self._extract_port_from_rtsp(rtsp_url)
                    
                    camera_data = {
                        'name': config.get('name', f'Config Camera {camera_id}'),
                        'location': config.get('location', 'Unknown'),
                        'ip_address': ip_address,
                        'port': port,
                        'rtsp_url': rtsp_url,
                        'resolution': f"{config.get('resolution', [1920, 1080])[0]}x{config.get('resolution', [1920, 1080])[1]}",
                        'fps': config.get('fps', 25),
                        'enabled': config.get('enabled', True)
                    }
                    
                    # Veritabanında var mı kontrol et
                    existing_camera = self._check_camera_by_name(company_id, camera_data['name'])
                    
                    if existing_camera:
                        # Güncelle
                        if self._update_camera(company_id, existing_camera['camera_id'], camera_data):
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1
                    else:
                        # Yeni kamera ekle
                        if self._add_config_camera(company_id, camera_id, camera_data):
                            result['added'] += 1
                        else:
                            result['errors'].append(f"Failed to add config camera {camera_data['name']}")
                            
                except Exception as e:
                    result['errors'].append(f"Error processing config camera {camera_id}: {str(e)}")
                    self.logger.error(f"Error processing config camera: {e}")
            
            self.logger.info(f"✅ Config sync complete: {result['added']} added, {result['updated']} updated")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Config sync failed: {e}")
            return {
                'total_config': len(config_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [str(e)]
            }
    
    def _extract_ip_from_rtsp(self, rtsp_url: str) -> str:
        """RTSP URL'den IP adresini çıkar"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(rtsp_url)
            return parsed.hostname or ''
        except:
            return ''
    
    def _extract_port_from_rtsp(self, rtsp_url: str) -> int:
        """RTSP URL'den port'u çıkar"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(rtsp_url)
            return parsed.port or 554
        except:
            return 554
    
    def _check_camera_by_name(self, company_id: str, camera_name: str) -> Optional[Dict]:
        """Kamerayı isimle kontrol et"""
        try:
            query = '''
                SELECT camera_id, camera_name, status 
                FROM cameras 
                WHERE company_id = ? AND camera_name = ? AND status != 'deleted'
            '''
            result = self.db_adapter.execute_query(query, (company_id, camera_name), fetch_one=True)
            
            if result:
                return {
                    'camera_id': result[0],
                    'camera_name': result[1],
                    'status': result[2]
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking camera by name: {e}")
            return None
    
    def _add_config_camera(self, company_id: str, config_camera_id: str, camera_data: Dict) -> bool:
        """Config'den kamerayı veritabanına ekle"""
        try:
            import uuid
            
            # Config camera ID'sini kullan veya yeni oluştur
            camera_id = config_camera_id if config_camera_id.startswith('CAM_') else str(uuid.uuid4())
            
            query = '''
                INSERT INTO cameras (
                    camera_id, company_id, camera_name, location, ip_address, 
                    rtsp_url, resolution, fps, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
            '''
            
            params = (
                camera_id,
                company_id,
                camera_data['name'],
                camera_data['location'],
                camera_data['ip_address'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps']
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Added config camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to add config camera: {e}")
            return False

    def update_company_logo_url(self, company_id: str, logo_url: str) -> bool:
        """Şirket logo URL'ini güncelle"""
        try:
            print(f"🔍 Database adapter - Logo URL güncelleniyor: {company_id} -> {logo_url}")
            
            query = '''
                UPDATE companies 
                SET logo_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ?
            '''
            
            print(f"🔍 Database adapter - Query: {query}")
            print(f"🔍 Database adapter - Params: ({logo_url}, {company_id})")
            
            self.db_adapter.execute_query(query, (logo_url, company_id))
            
            # Güncelleme sonrası kontrol
            print(f"🔍 Database adapter - Güncelleme sonrası kontrol...")
            check_query = "SELECT logo_url FROM companies WHERE company_id = ?"
            result = self.db_adapter.execute_query(check_query, (company_id,), fetch_one=True)
            print(f"🔍 Database adapter - Kontrol sonucu: {result}")
            
            self.logger.info(f"✅ Company logo URL updated: {company_id} -> {logo_url}")
            return True
            
        except Exception as e:
            print(f"❌ Database adapter - Logo URL güncelleme hatası: {e}")
            self.logger.error(f"❌ Failed to update company logo URL: {e}")
            return False
    
    def get_company_info(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Şirket bilgilerini getir"""
        try:
            print(f"🔍 Database adapter - get_company_info çağrıldı: {company_id}")
            
            query = '''
                SELECT company_name, sector, contact_person, email, phone, address,
                       subscription_type, subscription_start, subscription_end, max_cameras, logo_url
                FROM companies 
                WHERE company_id = ?
            '''
            
            print(f"🔍 Database adapter - Query: {query}")
            result = self.db_adapter.execute_query(query, (company_id,), fetch_one=True)
            print(f"🔍 Database adapter - Query result: {result}")
            
            if result:
                if hasattr(result, 'keys'):  # PostgreSQL RealDictRow
                    print(f"🔍 Database adapter - PostgreSQL RealDictRow formatı")
                    company_info = {
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'contact_person': result['contact_person'],
                        'email': result['email'],
                        'phone': result['phone'],
                        'address': result['address'],
                        'subscription_type': result['subscription_type'],
                        'subscription_start': result['subscription_start'],
                        'subscription_end': result['subscription_end'],
                        'max_cameras': result['max_cameras'],
                        'logo_url': result['logo_url']
                    }
                    print(f"🔍 Database adapter - Company info: {company_info}")
                    return company_info
                else:  # SQLite tuple
                    print(f"🔍 Database adapter - SQLite tuple formatı")
                    print(f"🔍 Database adapter - Result length: {len(result)}")
                    company_info = {
                        'company_name': result[0],
                        'sector': result[1],
                        'contact_person': result[2],
                        'email': result[3],
                        'phone': result[4],
                        'address': result[5],
                        'subscription_type': result[6],
                        'subscription_start': result[7],
                        'subscription_end': result[8],
                        'max_cameras': result[9],
                        'logo_url': result[10] if len(result) > 10 else None
                    }
                    print(f"🔍 Database adapter - Company info: {company_info}")
                    return company_info
            else:
                print(f"🔍 Database adapter - Query sonucu bulunamadı")
                return None
            
        except Exception as e:
            print(f"❌ Database adapter - get_company_info hatası: {e}")
            self.logger.error(f"❌ Failed to get company info: {e}")
            return None

# Global camera discovery manager instance
camera_discovery_manager = CameraDiscoveryManager(db_adapter)

def get_camera_discovery_manager() -> CameraDiscoveryManager:
    """Get global camera discovery manager instance"""
    return camera_discovery_manager 