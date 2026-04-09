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
from pathlib import Path
import uuid
import secrets
import bcrypt
# Lazy import to avoid circular dependency
def get_secure_db_connector():
    """Get secure DB connector when needed"""
    try:
        # Try multiple import paths for flexibility
        try:
            # Try core relative path first
            from utils.secure_database_connector import get_secure_db_connector as get_connector
            return get_connector()
        except ImportError:
            try:
                # Try legacy path (from find_by_name)
                from legacy.utils.secure_database_connector import get_secure_db_connector as get_connector
                return get_connector()
            except ImportError:
                try:
                    # Try direct utils import
                    from utils.secure_database_connector import get_secure_db_connector as get_connector
                    return get_connector()
                except ImportError:
                    logger.warning("⚠️ Could not import secure_database_connector from any path")
                    return None
    except Exception as e:
        logger.warning(f"⚠️ Error getting secure DB connector: {e}")
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


def _normalize_company_ppe_requirements_list(
    items: Any, sector: Optional[str] = None
) -> Optional[List[str]]:
    """DB/UI listesini `backend/company/sector_config.ts` id'leriyle hizalar.

    - mandatory:false olanlar çıkarılır.
    - ID'ler TS'deki gibi kalır (hairnet, apron, face_mask, …); model sınıf adlarına
      çevirme detection katmanında yapılır (bkz. sector_ppe_config.map_sh17_…).
    - Sektör biliniyorsa, yalnızca o sektör şablonunda tanımlı id'ler tutulur;
      hiçbiri eşleşmezse (eski/özel veri) liste olduğu gibi bırakılır.
    """
    if items is None:
        return None
    if not isinstance(items, list):
        return None
    if len(items) == 0:
        return []

    # Lazy import: database_adapter çok erken yüklenebilir
    from sector.sector_ppe_config import get_all_ppe_ids_for_sector, resolve_sector_config_key

    out: List[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            pid = item.get("id") or item.get("ppe_type") or item.get("type")
            if pid is None:
                continue
            if item.get("mandatory") is False:
                continue
            out.append(str(pid).strip().lower())
        else:
            s = str(item).strip().lower()
            if s:
                out.append(s)

    seen = set()
    result: List[str] = []
    for pid in out:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)

    if sector:
        sk = resolve_sector_config_key(sector)
        allowed = get_all_ppe_ids_for_sector(sk)
        if allowed:
            filtered = [x for x in result if x in allowed]
            if filtered:
                return filtered
    return result


class DatabaseAdapter:
    """Universal database adapter for SQLite and PostgreSQL"""
    
    def __init__(self):
        self.config = self._get_database_config()
        self.db_type = self.config.database_type
        self.secure_connector = get_secure_db_connector()
        self.connection_pool = None  # Will be initialized for PostgreSQL
        self._init_connection_pool()
        logger.info(f"🗄️ Database adapter initialized: {self.db_type}")

    def get_placeholder(self) -> str:
        """Parametre placeholder'ı (SQLite ? / PostgreSQL %s)."""
        return "?" if self.db_type == "sqlite" else "%s"

    def _init_connection_pool(self):
        """Initialize connection pool for PostgreSQL"""
        try:
            if self.db_type == 'postgresql':
                # Connection pooling for PostgreSQL
                database_url = self.config.database_url
                if database_url:
                    try:
                        from urllib.parse import urlparse
                        # Handle potential issues with postgresql:// vs postgres://
                        if database_url.startswith('postgres://'):
                            database_url = database_url.replace('postgres://', 'postgresql://', 1)
                            
                        parsed = urlparse(database_url)
                        
                        from psycopg2 import pool
                        try:
                            minconn = max(1, int(os.getenv("DB_POOL_MINCONN", "5")))
                            maxconn = max(minconn, int(os.getenv("DB_POOL_MAXCONN", "100")))
                        except ValueError:
                            minconn, maxconn = 5, 100
                        # Thread-safe connection pool (single process → one adapter via get_db_adapter())
                        self.connection_pool = pool.ThreadedConnectionPool(
                            minconn=minconn,
                            maxconn=maxconn,
                            host=parsed.hostname,
                            port=parsed.port or 5432,
                            database=parsed.path[1:],
                            user=parsed.username,
                            password=parsed.password,
                            connect_timeout=10
                        )
                        logger.info(
                            f"✅ PostgreSQL threaded connection pool initialized ({minconn}-{maxconn})"
                        )
                    except Exception as pool_error:
                        logger.warning(f"⚠️ Connection pool initialization failed: {pool_error}, will use direct connections")
                else:
                    logger.warning("⚠️ DATABASE_URL not set, skipping connection pool")
        except Exception as e:
            logger.warning(f"⚠️ Connection pool initialization failed: {e}, will use direct connections")
    
    def _get_database_config(self) -> DatabaseConfig:
        """Get database configuration based on environment"""
        try:
            # Check for PostgreSQL configuration first
            database_url = os.getenv('DATABASE_URL')
            if database_url and (database_url.startswith('postgresql://') or database_url.startswith('postgres://')):
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
        """Get SQLite configuration - Pointing to core directory"""
        # __file__ is core/database/database_adapter.py
        # root_dir should now be core
        core_dir = Path(__file__).resolve().parents[1]
        default_db_path = str(core_dir / 'smartsafe_saas.db')
        
        db_path = os.getenv('SQLITE_DB_PATH', default_db_path)
        return DatabaseConfig(
            database_url=db_path,
            database_type='sqlite',
            connection_params={'database_path': db_path}
        )
    
    def health_check(self) -> bool:
        """Lightweight health check (SELECT 1) to verify DB connectivity.

        Used by ensure_database_initialized() to detect dead connections after long idle periods.
        """
        conn = None
        try:
            conn = self.get_connection(timeout=5)
            cursor = conn.cursor()
            if self.db_type == 'sqlite':
                cursor.execute('SELECT 1')
            else:
                cursor.execute('SELECT 1')
            cursor.fetchone()
            return True
        except Exception as e:
            logger.warning(f"⚠️ Database health check failed: {e}")
            return False
        finally:
            try:
                if conn is not None:
                    self.close_connection(conn)
            except Exception:
                pass
    
    def close_connection(self, conn):
        """Close database connection and return to pool if applicable"""
        try:
            if conn is None:
                return
            
            if self.db_type == 'sqlite':
                conn.close()
            elif self.connection_pool:
                # Havuzdan gelip gelmediğini kontrol et
                try:
                    # ThreadedConnectionPool için putconn
                    self.connection_pool.putconn(conn)
                    logger.debug("✅ Connection returned to pool")
                except Exception:
                    # Havuz dışı (direct) bir bağlantıysa veya hata varsa kapat
                    try:
                        conn.close()
                    except:
                        pass
            else:
                try:
                    conn.close()
                except:
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Error closing connection: {e}")
    
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
                try:
                    secure_connector = get_secure_db_connector()
                    if secure_connector:
                        return secure_connector.get_connection()
                    else:
                        # Direct PostgreSQL attempt before failing to SQLite
                        database_url = self.config.database_url
                        if database_url and database_url.startswith('postgresql://'):
                            try:
                                logger.info("🔌 Attempting direct psycopg2 connection as fallback")
                                conn = psycopg2.connect(database_url)
                                return conn
                            except Exception as direct_err:
                                logger.warning(f"⚠️ Direct PostgreSQL connection failed: {direct_err}")

                        logger.warning("⚠️ Secure connector not available")
                        # Return None instead of permanent SQLite switch to allow for error reporting
                        return None
                except Exception as e:
                    logger.warning(f"⚠️ PostgreSQL connection failed: {e}")
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
                    self.close_connection(conn)
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
                    group_id TEXT,
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
            
            # Camera Groups table - Added for specific PPE configurations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS camera_groups (
                    group_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    ppe_config JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id)
                )
            ''')
            
            # Ensure group_id exists in cameras table
            try:
                cursor.execute('ALTER TABLE cameras ADD COLUMN group_id TEXT')
            except Exception:
                pass
            
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
                        camera_id TEXT,
                        person_id TEXT NOT NULL,
                        violation_type TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL,
                        duration_seconds INTEGER,
                        snapshot_path TEXT,
                        resolution_snapshot_path TEXT,
                        severity TEXT DEFAULT 'warning',
                        status TEXT DEFAULT 'active',
                        source_type TEXT NOT NULL,
                        dvr_channel_id TEXT REFERENCES dvr_channels (channel_id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (company_id)
                    )
                ''')
                self.ensure_violation_events_pr1_expand(cursor)
                self.ensure_violation_events_pr3_contract(cursor)
            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS violation_events (
                        event_id VARCHAR(255) PRIMARY KEY,
                        company_id VARCHAR(255) REFERENCES companies(company_id),
                        camera_id VARCHAR(255),
                        person_id VARCHAR(255) NOT NULL,
                        violation_type VARCHAR(100) NOT NULL,
                        start_time DOUBLE PRECISION NOT NULL,
                        end_time DOUBLE PRECISION,
                        duration_seconds INTEGER,
                        snapshot_path TEXT,
                        resolution_snapshot_path TEXT,
                        severity VARCHAR(20) DEFAULT 'warning',
                        status VARCHAR(20) DEFAULT 'active',
                        source_type VARCHAR(20) NOT NULL,
                        dvr_channel_id VARCHAR(255) REFERENCES dvr_channels (channel_id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT violation_events_source_shape_chk CHECK (
                            (source_type = 'camera' AND camera_id IS NOT NULL AND dvr_channel_id IS NULL)
                            OR
                            (source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL AND camera_id IS NULL)
                        )
                    )
                ''')
                try:
                    cursor.execute('''
                        ALTER TABLE violation_events
                        DROP CONSTRAINT IF EXISTS violation_events_camera_id_fkey
                    ''')
                except Exception:
                    pass
                self.ensure_violation_events_pr1_expand(cursor)
                self.ensure_violation_events_pr3_contract(cursor)

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
                    self.close_connection(conn)
            except Exception:
                pass
    
    def execute_query(
        self,
        query: str,
        params: tuple = None,
        fetch_all: bool = True,
        fetch_one: bool = False,
    ) -> Any:
        """Execute database query with improved error handling and retry logic.
        
        Contract:
        - For SELECT:
          - fetch_one=True  -> returns single row as dict (or None)
          - fetch_all=True  -> returns list[dict] (possibly empty)
          - fetch_all=False -> returns single row as dict (or None)  (legacy behavior)
        - For INSERT/UPDATE/DELETE: returns cursor.rowcount (int)
        
        Notes:
        - fetch_one takes precedence over fetch_all to avoid ambiguous calls.
        """
        max_retries = 3
        retry_delay = 0.1  # 100ms

        # Normalize flags (fetch_one wins).
        if fetch_one:
            fetch_all = False
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                if conn is None:
                    logger.error("❌ Database connection failed")
                    return None
                
                cursor = conn.cursor()
            
                # Execute query
                # Convert SQLite style '?' placeholders to PostgreSQL '%s' style if needed
                if self.db_type == 'postgresql' and '?' in query:
                    query = query.replace('?', '%s')
                    logger.debug(f"🔄 Converted query to PostgreSQL style: {query}")
                
                cursor.execute(query, params or ())
                    
                # Handle different query types
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    result = cursor.rowcount
                    conn.commit()
                    logger.debug(f"✅ Query executed successfully: {result} rows affected")
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
                # RELEASE CONNECTION TO POOL OR CLOSE IT
                if conn:
                    try:
                        self.close_connection(conn)
                    except Exception as e:
                        logger.warning(f"⚠️ Error releasing connection: {e}")

        logger.error(f"❌ Database query failed after {max_retries} attempts")
        return None

    def ensure_violation_events_pr1_expand(self, cursor) -> None:
        """
        PR1 Expand: source_type, dvr_channel_id, camera_id nullable (+ PostgreSQL FK).
        Idempotent; Encore migration ile aynı hedef şema (Python-only init senaryosu).
        """
        try:
            if self.db_type == "postgresql":
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'violation_events'
                    )
                """)
                if not cursor.fetchone()[0]:
                    return
                cursor.execute(
                    "ALTER TABLE violation_events ADD COLUMN IF NOT EXISTS source_type VARCHAR(20)"
                )
                cursor.execute(
                    "ALTER TABLE violation_events ADD COLUMN IF NOT EXISTS dvr_channel_id VARCHAR(255)"
                )
                cursor.execute(
                    "ALTER TABLE violation_events ALTER COLUMN camera_id DROP NOT NULL"
                )
                cursor.execute("""
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'violation_events_dvr_channel_id_fkey'
                      ) THEN
                        ALTER TABLE violation_events
                          ADD CONSTRAINT violation_events_dvr_channel_id_fkey
                          FOREIGN KEY (dvr_channel_id) REFERENCES dvr_channels (channel_id);
                      END IF;
                    END $$;
                """)
            else:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='violation_events'"
                )
                if not cursor.fetchone():
                    return
                cursor.execute("PRAGMA table_info(violation_events)")
                colnames = {row[1] for row in cursor.fetchall()}
                if "source_type" not in colnames:
                    cursor.execute(
                        "ALTER TABLE violation_events ADD COLUMN source_type TEXT"
                    )
                if "dvr_channel_id" not in colnames:
                    cursor.execute("""
                        ALTER TABLE violation_events ADD COLUMN dvr_channel_id TEXT
                        REFERENCES dvr_channels (channel_id)
                    """)
        except Exception as e:
            logger.warning(f"⚠️ ensure_violation_events_pr1_expand: {e}")

    def ensure_violation_events_pr3_contract(self, cursor) -> None:
        """
        PR3 Contract: DVR satırlarında camera_id temizliği; PostgreSQL'de ayrıca NOT NULL,
        CHECK ve partial index (migration 3 ile uyumlu). SQLite'ta yalnızca veri düzeltmesi.
        """
        try:
            if self.db_type == "sqlite":
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='violation_events'"
                )
                if not cursor.fetchone():
                    return
                try:
                    cursor.execute(
                        "UPDATE violation_events SET camera_id = NULL WHERE source_type = 'dvr_channel'"
                    )
                except Exception as ue:
                    logger.debug(f"SQLite violation_events PR3 DVR camera_id clear: {ue}")
                return
        except Exception as e:
            logger.warning(f"⚠️ ensure_violation_events_pr3_contract (sqlite): {e}")
            return

        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'violation_events'
                )
            """)
            if not cursor.fetchone()[0]:
                return
            cursor.execute(
                "UPDATE violation_events SET camera_id = NULL WHERE source_type = 'dvr_channel'"
            )
            try:
                cursor.execute(
                    "ALTER TABLE violation_events ALTER COLUMN source_type SET NOT NULL"
                )
            except Exception as ne:
                logger.warning(
                    f"⚠️ violation_events source_type NOT NULL (PR2 gerekli olabilir): {ne}"
                )
            cursor.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'violation_events_source_shape_chk'
                  ) THEN
                    ALTER TABLE violation_events
                      ADD CONSTRAINT violation_events_source_shape_chk CHECK (
                        (source_type = 'camera' AND camera_id IS NOT NULL AND dvr_channel_id IS NULL)
                        OR
                        (source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL AND camera_id IS NULL)
                      );
                  END IF;
                END $$;
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_violation_events_active_camera
                ON violation_events (company_id, start_time DESC)
                WHERE source_type = 'camera' AND status = 'active'
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_violation_events_active_dvr
                ON violation_events (company_id, dvr_channel_id, start_time DESC)
                WHERE source_type = 'dvr_channel' AND status = 'active'
            """)
        except Exception as e:
            logger.warning(f"⚠️ ensure_violation_events_pr3_contract: {e}")
    
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

            # 3b. violation_events PR1 genişletme (migration ile aynı; Python-only deploy senaryosu)
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'violation_events'
                    )
                """)
                if cursor.fetchone()[0]:
                    self.ensure_violation_events_pr1_expand(cursor)
                    self.ensure_violation_events_pr3_contract(cursor)
            except Exception as e:
                logger.warning(f"⚠️ violation_events PR1 expand (schema sync): {e}")
            
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

            dup = self.execute_query(
                "SELECT dvr_id FROM dvr_systems WHERE company_id = ? AND ip_address = ?",
                (company_id, dvr_data["ip_address"]),
                fetch_one=True,
            )
            if dup:
                logger.warning(
                    "⚠️ Bu şirket için bu IP ile kayıtlı bir DVR zaten var; "
                    f"company_id={company_id} ip={dvr_data.get('ip_address')}"
                )
                return False

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
            new_ip = dvr_data.get("ip_address")
            if new_ip:
                conflict = self.execute_query(
                    "SELECT dvr_id FROM dvr_systems WHERE company_id = ? AND ip_address = ? AND dvr_id <> ?",
                    (company_id, new_ip, dvr_id),
                    fetch_one=True,
                )
                if conflict:
                    logger.warning(
                        "⚠️ Bu şirket için bu IP başka bir DVR kaydında kullanılıyor; "
                        f"company_id={company_id} ip={new_ip}"
                    )
                    return False

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
    def delete_dvr_channel(self, company_id: str, dvr_id: str, channel_id: str) -> bool:
        """Delete a DVR channel from database"""
        try:
            placeholder = '?' if self.db_type == 'sqlite' else '%s'
            query = f"DELETE FROM dvr_channels WHERE company_id = {placeholder} AND dvr_id = {placeholder} AND channel_id = {placeholder}"
            self.execute_query(query, (company_id, dvr_id, channel_id))
            logger.info(f"✅ DVR channel deleted: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting DVR channel {channel_id}: {e}")
            return False

    def add_dvr_channel(self, company_id: str, dvr_id: str, channel_data: Dict[str, Any]) -> bool:
        """Add DVR channel to database"""
        try:
            from utils.redaction import redact_url
            logger.debug(f"🔧 Adding DVR channel: {channel_data.get('name')} for DVR: {dvr_id}")
            
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
            
            logger.debug(f"🔧 Channel SQL Query: {query}")
            # Never log credentials/URLs verbatim (RTSP/HTTP may include user:pass)
            safe_params = list(params)
            if len(safe_params) >= 11:
                safe_params[9] = redact_url(str(safe_params[9]))   # rtsp_path
                safe_params[10] = redact_url(str(safe_params[10]))  # http_path
            logger.debug(f"🔧 Channel Parameters: {tuple(safe_params)}")
            
            result = self.execute_query(query, params, fetch_all=False)
            logger.debug(f"🔧 Channel Query result: {result}")
            
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
            
            if result and isinstance(result, list) and len(result) > 0:
                # execute_query zaten dict döndürüyor, kontrol et
                detections = []
                for row in result:
                    if isinstance(row, dict):
                        # Zaten dict formatında
                        detection = {
                            'id': row.get('id'),
                            'camera_id': row.get('camera_id', camera_id),
                            'company_id': row.get('company_id', company_id),
                            'detection_type': row.get('detection_type', 'ppe'),
                            'timestamp': row.get('timestamp'),
                            'confidence': row.get('confidence', 0.0),
                            'people_detected': row.get('people_detected', 0),
                            'ppe_compliant': row.get('ppe_compliant', 0),
                            'violations_count': row.get('violations_count', 0),
                            'total_people': row.get('people_detected', 0),
                            'compliant_people': row.get('ppe_compliant', 0)
                        }
                    else:
                        # Tuple/list formatında (fallback)
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
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_latest_camera_detection(self, camera_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get latest detection result for a camera"""
        try:
            results = self.get_camera_detection_results(camera_id, company_id, limit=1)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"❌ Get latest camera detection error: {e}")
            return None
    
    def get_camera_group_config(self, group_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get PPE configuration for a specific camera group"""
        try:
            if self.db_type == 'sqlite':
                query = "SELECT ppe_config FROM camera_groups WHERE group_id = ? AND company_id = ?"
            else:  # PostgreSQL
                query = "SELECT ppe_config FROM camera_groups WHERE group_id = %s AND company_id = %s"
            
            result = self.execute_query(query, (group_id, company_id), fetch_one=True)
            
            if result:
                if isinstance(result, dict):
                    ppe_config = result.get('ppe_config')
                else:
                    ppe_config = result[0]
                
                if isinstance(ppe_config, str):
                    try:
                        import json
                        return json.loads(ppe_config)
                    except:
                        return None
                return ppe_config
            return None
        except Exception as e:
            logger.error(f"❌ Get camera group config error: {e}")
            return None

    # ========================================
    # RTSP URL CACHING METHODS
    # ========================================

    def update_channel_rtsp_path(
        self,
        ip_address: str,
        channel_number: int,
        rtsp_path: str,
        *,
        company_id: str | None = None,
    ) -> bool:
        """Başarılı RTSP URL'yi dvr_channels tablosuna kaydet.
        
        DVR stream handler bir kanalın çalışan URL'sini bulduğunda bu methodu çağırır.
        Bir sonraki bağlantıda sistem bu URL'yi doğrudan kullanarak
        26 farklı URL'yi denemek yerine anında bağlanır.
        
        Args:
            ip_address: DVR'ın IP adresi
            channel_number: Kanal numarası
            rtsp_path: Çalışan tam RTSP URL
            
        Returns:
            True: Başarıyla kaydedildi, False: Hata oluştu
        """
        try:
            from utils.redaction import redact_url
            # Resolve dvr_id (and optionally company) from dvr_systems
            if company_id:
                dvr_lookup_q = "SELECT dvr_id FROM dvr_systems WHERE ip_address = ? AND company_id = ?"
                dvr_lookup_params = (ip_address, company_id)
            else:
                # Without company_id this can be ambiguous in multi-tenant setups.
                # We'll only proceed if there's exactly one DVR for that IP.
                dvr_lookup_q = "SELECT dvr_id, company_id FROM dvr_systems WHERE ip_address = ?"
                dvr_lookup_params = (ip_address,)

            dvr_rows = self.execute_query(dvr_lookup_q, dvr_lookup_params, fetch_all=True)
            if not dvr_rows:
                logger.debug(f"ℹ️ DVR system not found for IP {ip_address}, skipping URL cache")
                return False

            if company_id:
                # dvr_rows may be list[dict] (fetch_all=True)
                dvr_id = dvr_rows[0].get('dvr_id') if isinstance(dvr_rows[0], dict) else dvr_rows[0][0]
            else:
                unique_dvr_ids = set()
                for r in dvr_rows:
                    if isinstance(r, dict):
                        unique_dvr_ids.add(r.get('dvr_id'))
                    elif isinstance(r, (list, tuple)) and r:
                        unique_dvr_ids.add(r[0])
                if len(unique_dvr_ids) != 1:
                    logger.warning(
                        f"⚠️ RTSP cache write skipped due to ambiguous DVR lookup for ip={ip_address} "
                        f"(found {len(unique_dvr_ids)} dvrs). Pass company_id to update_channel_rtsp_path()."
                    )
                    return False
                dvr_id = next(iter(unique_dvr_ids))

            # Update using a join on dvr_systems to avoid mismatches and keep
            # ip_address/company_id as the primary identity.
            if self.db_type == 'sqlite':
                if company_id:
                    update_query = """
                        UPDATE dvr_channels
                        SET rtsp_path = ?, updated_at = datetime('now')
                        WHERE channel_id IN (
                            SELECT dc.channel_id
                            FROM dvr_channels dc
                            JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                            WHERE ds.ip_address = ? AND ds.company_id = ? AND dc.channel_number = ?
                        )
                    """
                    affected = self.execute_query(update_query, (rtsp_path, ip_address, company_id, channel_number))
                else:
                    update_query = """
                        UPDATE dvr_channels
                        SET rtsp_path = ?, updated_at = datetime('now')
                        WHERE channel_id IN (
                            SELECT dc.channel_id
                            FROM dvr_channels dc
                            JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                            WHERE ds.ip_address = ? AND dc.channel_number = ?
                        )
                    """
                    affected = self.execute_query(update_query, (rtsp_path, ip_address, channel_number))
            else:  # PostgreSQL
                if company_id:
                    update_query = """
                        UPDATE dvr_channels dc
                        SET rtsp_path = %s, updated_at = NOW()
                        FROM dvr_systems ds
                        WHERE dc.dvr_id = ds.dvr_id
                        AND ds.ip_address = %s AND ds.company_id = %s AND dc.channel_number = %s
                    """
                    affected = self.execute_query(update_query, (rtsp_path, ip_address, company_id, channel_number))
                else:
                    update_query = """
                        UPDATE dvr_channels dc
                        SET rtsp_path = %s, updated_at = NOW()
                        FROM dvr_systems ds
                        WHERE dc.dvr_id = ds.dvr_id
                        AND ds.ip_address = %s AND dc.channel_number = %s
                    """
                    affected = self.execute_query(update_query, (rtsp_path, ip_address, channel_number))

            if affected is None:
                logger.warning(
                    f"⚠️ RTSP cache update failed (no rowcount): ip={ip_address} ch{channel_number} "
                    f"url={redact_url(str(rtsp_path))}"
                )
                return False
            if affected > 0:
                logger.info(f"✅ RTSP URL cached in DB: {ip_address} ch{channel_number}")
                return True

            # UPDATE matched no row: common during parallel discovery before channels are persisted.
            if company_id:
                cid_company = company_id
            else:
                r0 = dvr_rows[0]
                if isinstance(r0, dict):
                    cid_company = r0.get("company_id")
                elif isinstance(r0, (list, tuple)) and len(r0) > 1:
                    cid_company = r0[1]
                else:
                    cid_company = None
            if not cid_company:
                logger.warning(
                    f"⚠️ RTSP cache upsert skipped (no company_id): ip={ip_address} ch{channel_number} "
                    f"url={redact_url(str(rtsp_path))}"
                )
                return False

            channel_id = f"{dvr_id}_ch{channel_number:02d}"
            name = f"Channel {channel_number}"
            http_path = f"/ch{channel_number:02d}/snapshot"
            if self.db_type == "sqlite":
                upsert_query = """
                    INSERT OR REPLACE INTO dvr_channels (
                        channel_id, dvr_id, company_id, name, channel_number,
                        status, resolution_width, resolution_height, fps, rtsp_path, http_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            else:
                upsert_query = """
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
                """
            upsert_params = (
                channel_id,
                dvr_id,
                cid_company,
                name,
                channel_number,
                "active",
                1920,
                1080,
                25,
                rtsp_path,
                http_path,
            )
            ins = self.execute_query(upsert_query, upsert_params, fetch_all=False)
            if ins is not None and ins > 0:
                logger.info(
                    f"✅ RTSP URL upserted in DB (no prior channel row): {ip_address} ch{channel_number}"
                )
                return True
            logger.warning(
                f"⚠️ RTSP cache upsert did not affect rows: ip={ip_address} ch{channel_number} "
                f"url={redact_url(str(rtsp_path))}"
            )
            return False
        except Exception as e:
            logger.warning(f"⚠️ Failed to cache RTSP URL in DB: {e}")
            return False

    def get_channel_cached_rtsp_path(
        self,
        ip_address: str,
        channel_number: int,
        *,
        company_id: str | None = None,
    ) -> Optional[str]:
        """Veritabanında kayıtlı başarılı RTSP URL'yi getir.
        
        Args:
            ip_address: DVR'ın IP adresi
            channel_number: Kanal numarası
            
        Returns:
            Kayıtlı RTSP URL veya None
        """
        try:
            if self.db_type == 'sqlite':
                query = """
                    SELECT dc.rtsp_path FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE ds.ip_address = ? AND dc.channel_number = ?
                    AND dc.rtsp_path IS NOT NULL AND dc.rtsp_path != ''
                """
                if company_id:
                    query = query.replace("WHERE ds.ip_address = ? AND dc.channel_number = ?", "WHERE ds.ip_address = ? AND ds.company_id = ? AND dc.channel_number = ?")
                    params = (ip_address, company_id, channel_number)
                else:
                    # Guard against multi-tenant ambiguity: if multiple DVRs share this IP, don't guess.
                    dvr_count = self.execute_query(
                        "SELECT dvr_id FROM dvr_systems WHERE ip_address = ?",
                        (ip_address,),
                        fetch_all=True,
                    )
                    if isinstance(dvr_count, list) and len(dvr_count) > 1:
                        return None
                    params = (ip_address, channel_number)
            else:  # PostgreSQL
                query = """
                    SELECT dc.rtsp_path FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE ds.ip_address = %s AND dc.channel_number = %s
                    AND dc.rtsp_path IS NOT NULL AND dc.rtsp_path != ''
                """
                if company_id:
                    query = query.replace("WHERE ds.ip_address = %s AND dc.channel_number = %s", "WHERE ds.ip_address = %s AND ds.company_id = %s AND dc.channel_number = %s")
                    params = (ip_address, company_id, channel_number)
                else:
                    dvr_count = self.execute_query(
                        "SELECT dvr_id FROM dvr_systems WHERE ip_address = %s",
                        (ip_address,),
                        fetch_all=True,
                    )
                    if isinstance(dvr_count, list) and len(dvr_count) > 1:
                        return None
                    params = (ip_address, channel_number)

            result = self.execute_query(query, params, fetch_one=True)
            if result:
                if isinstance(result, dict):
                    return result.get('rtsp_path')
                return result[0] if isinstance(result, (list, tuple)) and len(result) > 0 else None
            return None
        except Exception as e:
            logger.debug(f"ℹ️ Could not retrieve cached RTSP URL: {e}")
            return None

    def update_camera_group_id(self, camera_id: str, company_id: str, group_id: str) -> bool:
        """Update camera's group ID"""
        try:
            if self.db_type == 'sqlite':
                query = "UPDATE cameras SET group_id = ?, updated_at = datetime('now') WHERE camera_id = ? AND company_id = ?"
            else:  # PostgreSQL
                query = "UPDATE cameras SET group_id = %s, updated_at = NOW() WHERE camera_id = %s AND company_id = %s"
            
            params = (group_id, camera_id, company_id)
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ Camera group ID updated for camera: {camera_id} to group: {group_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Update camera group ID error: {e}")
            return False

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
                    SELECT camera_id, company_id, group_id, camera_name, location, ip_address, 
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
                    SELECT camera_id, company_id, group_id, camera_name, location, ip_address, 
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
                            'group_id': result[2] if len(result) > 2 else None,
                            'camera_name': result[3] if len(result) > 3 else None,
                            'location': result[4] if len(result) > 4 else None,
                            'ip_address': result[5] if len(result) > 5 else None,
                            'port': result[6] if len(result) > 6 else 8080,
                            'rtsp_url': result[7] if len(result) > 7 else None,
                            'username': result[8] if len(result) > 8 else None,
                            'password': result[9] if len(result) > 9 else None,
                            'protocol': result[10] if len(result) > 10 else 'http',
                            'stream_path': result[11] if len(result) > 11 else '/video',
                            'auth_type': result[12] if len(result) > 12 else 'basic',
                            'resolution': result[13] if len(result) > 13 else '1920x1080',
                            'fps': result[14] if len(result) > 14 else 25,
                            'quality': result[15] if len(result) > 15 else 80,
                            'audio_enabled': result[16] if len(result) > 16 else False,
                            'night_vision': result[17] if len(result) > 17 else False,
                            'motion_detection': result[18] if len(result) > 18 else True,
                            'recording_enabled': result[19] if len(result) > 19 else True,
                            'camera_type': result[20] if len(result) > 20 else 'ip_camera',
                            'status': result[21] if len(result) > 21 else 'active',
                            'last_detection': result[22] if len(result) > 22 else None,
                            'last_test_time': result[23] if len(result) > 23 else None,
                            'connection_retries': result[24] if len(result) > 24 else 3,
                            'timeout': result[25] if len(result) > 25 else 10,
                            'created_at': result[26] if len(result) > 26 else None,
                            'updated_at': result[27] if len(result) > 27 else None
                        }
            return None
            
        except Exception as e:
            logger.error(f"❌ Get camera by ID error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None

    def get_dvr_channel_by_id(self, channel_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get DVR channel info by ID and company ID, formatted as a camera object"""
        try:
            if self.db_type == 'sqlite':
                query = '''
                    SELECT dc.channel_id, dc.company_id, NULL as group_id, dc.name as camera_name,
                           dc.channel_number as channel_number, dc.dvr_id as dvr_id,
                           'DVR: ' || ds.name as location, ds.ip_address, ds.rtsp_port as port, 
                           dc.rtsp_path as rtsp_url, ds.username, ds.password, 'rtsp' as protocol, 
                           dc.rtsp_path as stream_path, 'basic' as auth_type, 
                           (dc.resolution_width || 'x' || dc.resolution_height) as resolution, 
                           dc.fps, 80 as quality, FALSE as audio_enabled, FALSE as night_vision, 
                           TRUE as motion_detection, TRUE as recording_enabled, 
                           'dvr_channel' as camera_type, dc.status, NULL as last_detection, 
                           dc.last_test_time, 3 as connection_retries, 10 as timeout, 
                           dc.created_at, dc.updated_at
                    FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE dc.channel_id = ? AND dc.company_id = ?
                '''
            else:  # PostgreSQL
                query = '''
                    SELECT dc.channel_id, dc.company_id, NULL as group_id, dc.name as camera_name,
                           dc.channel_number as channel_number, dc.dvr_id as dvr_id,
                           CONCAT('DVR: ', ds.name) as location, ds.ip_address, ds.rtsp_port as port, 
                           dc.rtsp_path as rtsp_url, ds.username, ds.password, 'rtsp' as protocol, 
                           dc.rtsp_path as stream_path, 'basic' as auth_type, 
                           CONCAT(dc.resolution_width, 'x', dc.resolution_height) as resolution, 
                           dc.fps, 80 as quality, FALSE as audio_enabled, FALSE as night_vision, 
                           TRUE as motion_detection, TRUE as recording_enabled, 
                           'dvr_channel' as camera_type, dc.status, NULL as last_detection, 
                           dc.last_test_time, 3 as connection_retries, 10 as timeout, 
                           dc.created_at, dc.updated_at
                    FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE dc.channel_id = %s AND dc.company_id = %s
                '''
            
            result = self.execute_query(query, (channel_id, company_id), fetch_one=True)
            
            if result:
                if hasattr(result, 'keys') or isinstance(result, dict):  # PostgreSQL RealDictRow
                    camera = dict(result)
                    camera['is_dvr'] = True
                    return camera
                else:  # SQLite tuple/list
                    return {
                        'camera_id': result[0],
                        'company_id': result[1],
                        'group_id': result[2],
                        'camera_name': result[3],
                        'channel_number': result[4],
                        'dvr_id': result[5],
                        'location': result[6],
                        'ip_address': result[7],
                        'port': result[8],
                        'rtsp_url': result[9],
                        'username': result[10],
                        'password': result[11],
                        'protocol': result[12],
                        'stream_path': result[13],
                        'auth_type': result[14],
                        'resolution': result[15],
                        'fps': result[16],
                        'quality': result[17],
                        'audio_enabled': result[18],
                        'night_vision': result[19],
                        'motion_detection': result[20],
                        'recording_enabled': result[21],
                        'camera_type': result[22],
                        'status': result[23],
                        'is_dvr': True
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Get dvr channel by ID error: {e}")
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
            
            if result and isinstance(result, list) and len(result) > 0:
                row = result[0]
                # Convert row to dict - execute_query zaten dict döndürüyor
                if isinstance(row, dict):
                    stats = {
                        'total_detections': row.get('total_detections', 0) or 0,
                        'total_people': row.get('total_people', 0) or 0,
                        'total_compliant': row.get('total_compliant', 0) or 0,
                        'total_violations': row.get('total_violations', 0) or 0,
                        'avg_confidence': float(row.get('avg_confidence', 0.0)) or 0.0
                    }
                else:
                    # Tuple/list formatında (fallback)
                    stats = {
                        'total_detections': row[0] if len(row) > 0 else 0,
                        'total_people': row[1] if len(row) > 1 else 0,
                        'total_compliant': row[2] if len(row) > 2 else 0,
                        'total_violations': row[3] if len(row) > 3 else 0,
                        'avg_confidence': float(row[4]) if len(row) > 4 else 0.0
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

    def _resolve_dvr_channel_fk(self, camera_id: str, company_id: str) -> Optional[str]:
        """
        violation_events.camera_id (örn. işlemci stream_id dvr_{dvr_id}_ch01) değerini
        dvr_channels.channel_id (genelde {dvr_id}_ch01) ile eşleştirir.
        """
        sid = str(camera_id)
        info = self.get_dvr_channel_by_id(sid, company_id)
        if info:
            pk = info.get("channel_id") or info.get("camera_id")
            if pk:
                return str(pk)
        if sid.startswith("dvr_") and "_ch" in sid:
            stripped = sid[4:]
            info2 = self.get_dvr_channel_by_id(stripped, company_id)
            if info2:
                pk2 = info2.get("channel_id") or info2.get("camera_id")
                if pk2:
                    return str(pk2)
                return stripped
        return None

    def _viol_events_match_camera_sql(
        self, camera_id: str, company_id: Optional[str]
    ) -> Tuple[str, Tuple[Any, ...]]:
        """
        PR3: DVR satırlarında DB camera_id NULL; stream/camera anahtarı ile arama için
        camera_id kolonu VEYA dvr_channel_id (çözülmüş channel pk) eşleşmesi.
        """
        ph = self.get_placeholder()
        dvr_pk: Optional[str] = None
        if company_id and "_ch" in str(camera_id):
            dvr_pk = self._resolve_dvr_channel_fk(camera_id, company_id)
        if dvr_pk:
            return (
                f"(camera_id = {ph} OR dvr_channel_id = {ph})",
                (camera_id, dvr_pk),
            )
        return (f"camera_id = {ph}", (camera_id,))

    def add_violation_event(self, event_data: Dict) -> bool:
        """Yeni ihlal event'i kaydet. DVR kaynağında dvr_channels eşleşmesi yoksa yazılmaz (fail-fast)."""
        try:
            camera_id = event_data['camera_id']
            company_id = event_data['company_id']

            explicit_st = event_data.get('source_type')
            explicit_dc = event_data.get('dvr_channel_id')

            if explicit_st == 'camera':
                source_type = 'camera'
                dvr_channel_id = None
            elif explicit_st == 'dvr_channel':
                if not explicit_dc or not str(explicit_dc).strip():
                    logger.error(
                        "❌ violation_events: source_type=dvr_channel but dvr_channel_id missing "
                        f"(event_id={event_data.get('event_id')}, company_id={company_id})"
                    )
                    return False
                row = self.get_dvr_channel_by_id(str(explicit_dc), company_id)
                if not row:
                    logger.error(
                        "❌ violation_events: dvr_channel_id not found in dvr_channels for company "
                        f"(event_id={event_data.get('event_id')}, dvr_channel_id={explicit_dc}, company_id={company_id})"
                    )
                    return False
                pk = row.get('channel_id') or row.get('camera_id')
                source_type = 'dvr_channel'
                dvr_channel_id = str(pk) if pk else str(explicit_dc)
            elif '_ch' in str(camera_id):
                dvr_channel_id = self._resolve_dvr_channel_fk(camera_id, company_id)
                if not dvr_channel_id:
                    logger.error(
                        "❌ violation_events: DVR camera_id could not be resolved to dvr_channels.channel_id "
                        f"(event_id={event_data.get('event_id')}, camera_id={camera_id}, company_id={company_id})"
                    )
                    return False
                source_type = 'dvr_channel'
            else:
                source_type = 'camera'
                dvr_channel_id = None

            insert_camera_id = None if source_type == 'dvr_channel' else camera_id

            if self.db_type == 'sqlite':
                query = '''
                    INSERT INTO violation_events (
                        event_id, company_id, camera_id, person_id, violation_type,
                        start_time, end_time, duration_seconds, snapshot_path, severity, status,
                        source_type, dvr_channel_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
            else:  # PostgreSQL
                query = '''
                    INSERT INTO violation_events (
                        event_id, company_id, camera_id, person_id, violation_type,
                        start_time, end_time, duration_seconds, snapshot_path, severity, status,
                        source_type, dvr_channel_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                '''
            
            params = (
                event_data['event_id'],
                company_id,
                insert_camera_id,
                event_data['person_id'],
                event_data['violation_type'],
                event_data['start_time'],
                event_data.get('end_time'),
                event_data.get('duration_seconds'),
                event_data.get('snapshot_path'),
                event_data.get('severity', 'warning'),
                event_data.get('status', 'active'),
                source_type,
                dvr_channel_id,
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
                    cam_clause, cam_params = self._viol_events_match_camera_sql(
                        camera_id, company_id
                    )
                    query = f'''
                        SELECT * FROM violation_events 
                        WHERE {cam_clause} AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = cam_params
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
                    cam_clause, cam_params = self._viol_events_match_camera_sql(
                        camera_id, company_id
                    )
                    query = f'''
                        SELECT * FROM violation_events 
                        WHERE {cam_clause} AND status = 'active'
                        ORDER BY start_time DESC
                    '''
                    params = cam_params
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
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    # Zaten dict formatında
                    violation = {
                        'event_id': row.get('event_id'),
                        'company_id': row.get('company_id'),
                        'camera_id': row.get('camera_id'),
                        'person_id': row.get('person_id'),
                        'violation_type': row.get('violation_type'),
                        'start_time': row.get('start_time'),
                        'end_time': row.get('end_time'),
                        'duration_seconds': row.get('duration_seconds'),
                        'snapshot_path': row.get('snapshot_path'),
                        'severity': row.get('severity'),
                        'status': row.get('status')
                    }
                else:
                    # Tuple/list formatında (fallback)
                    violation = {
                        'event_id': row[0] if len(row) > 0 else None,
                        'company_id': row[1] if len(row) > 1 else None,
                        'camera_id': row[2] if len(row) > 2 else None,
                        'person_id': row[3] if len(row) > 3 else None,
                        'violation_type': row[4] if len(row) > 4 else None,
                        'start_time': row[5] if len(row) > 5 else None,
                        'end_time': row[6] if len(row) > 6 else None,
                        'duration_seconds': row[7] if len(row) > 7 else None,
                        'snapshot_path': row[8] if len(row) > 8 else None,
                        'severity': row[9] if len(row) > 9 else None,
                        'status': row[10] if len(row) > 10 else None
                    }
                violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get active violations error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_violation_history(
        self,
        camera_id: str,
        hours: int = 24,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[Dict]:
        """İhlal geçmişini getir (DVR için company_id verilirse dvr_channel_id eşlemesi yapılır)."""
        try:
            import time
            cutoff_time = time.time() - (hours * 3600)
            cam_clause, cam_params = self._viol_events_match_camera_sql(camera_id, company_id)

            if self.db_type == 'sqlite':
                query = f'''
                    SELECT * FROM violation_events 
                    WHERE {cam_clause} AND start_time >= ?
                    ORDER BY start_time DESC
                    LIMIT ?
                '''
            else:  # PostgreSQL
                query = f'''
                    SELECT * FROM violation_events 
                    WHERE {cam_clause} AND start_time >= %s
                    ORDER BY start_time DESC
                    LIMIT %s
                '''
            
            results = self.execute_query(
                query, (*cam_params, cutoff_time, limit), fetch_all=True
            )
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    # Zaten dict formatında
                    violation = {
                        'event_id': row.get('event_id'),
                        'company_id': row.get('company_id'),
                        'camera_id': row.get('camera_id'),
                        'person_id': row.get('person_id'),
                        'violation_type': row.get('violation_type'),
                        'start_time': row.get('start_time'),
                        'end_time': row.get('end_time'),
                        'duration_seconds': row.get('duration_seconds'),
                        'snapshot_path': row.get('snapshot_path'),
                        'severity': row.get('severity'),
                        'status': row.get('status')
                    }
                else:
                    # Tuple/list formatında (fallback)
                    violation = {
                        'event_id': row[0] if len(row) > 0 else None,
                        'company_id': row[1] if len(row) > 1 else None,
                        'camera_id': row[2] if len(row) > 2 else None,
                        'person_id': row[3] if len(row) > 3 else None,
                        'violation_type': row[4] if len(row) > 4 else None,
                        'start_time': row[5] if len(row) > 5 else None,
                        'end_time': row[6] if len(row) > 6 else None,
                        'duration_seconds': row[7] if len(row) > 7 else None,
                        'snapshot_path': row[8] if len(row) > 8 else None,
                        'severity': row[9] if len(row) > 9 else None,
                        'status': row[10] if len(row) > 10 else None
                    }
                violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get violation history error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    # ========================================
    # PERSON VIOLATIONS METHODS
    # ========================================
    
    def update_person_violation_stats(self, person_id: str, company_id: str, violation_type: str, duration_seconds: int) -> bool:
        """Kişi ihlal istatistiklerini güncelle (Çoklu ihlal destekli)"""
        try:
            from datetime import datetime
            month = datetime.now().strftime('%Y-%m')
            
            # Çoklu ihlal desteği: Virgülle ayrılmış tipleri tek tek işle
            v_types = [v.strip() for v in violation_type.split(',')] if ',' in violation_type else [violation_type]
            
            success = True
            for v_type in v_types:
                if not v_type: continue
                
                if self.db_type == 'sqlite':
                    # Önce mevcut kaydı kontrol et
                    check_query = '''
                        SELECT id, violation_count, total_duration_seconds 
                        FROM person_violations 
                        WHERE person_id = ? AND company_id = ? AND month = ? AND violation_type = ?
                    '''
                    existing = self.execute_query(check_query, (person_id, company_id, month, v_type), fetch_one=True)
                    
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
                        self.execute_query(insert_query, (person_id, company_id, month, v_type, duration_seconds))
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
                    self.execute_query(query, (person_id, company_id, month, v_type, duration_seconds))
            
            return success
            
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
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    # Zaten dict formatında
                    violation = {
                        'id': row.get('id'),
                        'person_id': row.get('person_id'),
                        'company_id': row.get('company_id'),
                        'month': row.get('month'),
                        'violation_type': row.get('violation_type'),
                        'violation_count': row.get('violation_count'),
                        'total_duration_seconds': row.get('total_duration_seconds'),
                        'penalty_amount': row.get('penalty_amount'),
                        'last_violation_date': row.get('last_violation_date')
                    }
                else:
                    # Tuple/list formatında (fallback)
                    violation = {
                        'id': row[0] if len(row) > 0 else None,
                        'person_id': row[1] if len(row) > 1 else None,
                        'company_id': row[2] if len(row) > 2 else None,
                        'month': row[3] if len(row) > 3 else None,
                        'violation_type': row[4] if len(row) > 4 else None,
                        'violation_count': row[5] if len(row) > 5 else None,
                        'total_duration_seconds': row[6] if len(row) > 6 else None,
                        'penalty_amount': row[7] if len(row) > 7 else None,
                        'last_violation_date': row[8] if len(row) > 8 else None
                    }
                violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get person monthly violations error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_company_detection_config(self, company_id: str) -> Dict[str, Any]:
        """Single source of truth for sector + required_ppe.

        - Sector comes from `companies.sector`
        - required_ppe comes from `companies.ppe_requirements` (if configured),
          otherwise caller may fallback to sector defaults.

        UI format: [{"id":"hairnet","mandatory":true}, ...] — sadece mandatory:true olanlar;
        `mandatory:false` (ör. eldiven) pose-aware zorunlu listesine alınmaz.
        """
        try:
            query = "SELECT sector, ppe_requirements FROM companies WHERE company_id = ?"
            row = self.execute_query(query, (company_id,), fetch_one=True)
            if not row or not isinstance(row, dict):
                return {}

            sector = (row.get("sector") or "").strip()
            raw_ppe = row.get("ppe_requirements")

            required_ppe = None
            if raw_ppe is not None:
                # sqlite may store JSON as TEXT; postgres as JSON already
                if isinstance(raw_ppe, str):
                    s = raw_ppe.strip()
                    if s in ("", "null", "{}"):
                        raw_ppe = None
                    else:
                        try:
                            raw_ppe = json.loads(raw_ppe)
                        except Exception:
                            raw_ppe = None

            inner_list = None
            if isinstance(raw_ppe, dict):
                inner_list = (
                    raw_ppe.get("required_ppe")
                    or raw_ppe.get("mandatory_ppe")
                    or raw_ppe.get("mandatory")
                )
            elif isinstance(raw_ppe, list):
                inner_list = raw_ppe

            if inner_list is not None:
                required_ppe = _normalize_company_ppe_requirements_list(
                    inner_list, sector=sector or None
                )

            return {
                "sector": sector or None,
                "required_ppe": required_ppe,
            }
        except Exception:
            return {}


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
            camera_id = f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
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
            camera_id = config_camera_id if config_camera_id.startswith('CAM_') else f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
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


# ── Process-wide singletons (one PG pool per process, thread-safe) ─────────
_db_adapter_instance: Optional[DatabaseAdapter] = None
_db_adapter_lock = threading.Lock()

_camera_discovery_manager_instance: Optional[CameraDiscoveryManager] = None
_camera_discovery_manager_lock = threading.Lock()


def get_db_adapter() -> DatabaseAdapter:
    """Return the shared DatabaseAdapter (lazy init, double-checked lock)."""
    global _db_adapter_instance
    if _db_adapter_instance is None:
        with _db_adapter_lock:
            if _db_adapter_instance is None:
                _db_adapter_instance = DatabaseAdapter()
    return _db_adapter_instance


def get_camera_discovery_manager() -> CameraDiscoveryManager:
    """Return the shared CameraDiscoveryManager bound to get_db_adapter()."""
    global _camera_discovery_manager_instance
    if _camera_discovery_manager_instance is None:
        with _camera_discovery_manager_lock:
            if _camera_discovery_manager_instance is None:
                _camera_discovery_manager_instance = CameraDiscoveryManager(get_db_adapter())
    return _camera_discovery_manager_instance