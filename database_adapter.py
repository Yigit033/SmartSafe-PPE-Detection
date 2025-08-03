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
from utils.secure_database_connector import get_secure_db_connector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"🗄️ Database adapter initialized: {self.db_type}")
    
    def _get_database_config(self) -> DatabaseConfig:
        """Get database configuration from environment"""
        database_url = os.getenv('DATABASE_URL')
        
        # Check for DATABASE_URL first (Render.com uses this)
        if database_url and database_url.startswith('postgresql://'):
            logger.info("✅ Using DATABASE_URL for PostgreSQL connection")
            return DatabaseConfig(
                database_url=database_url,
                database_type='postgresql',
                connection_params={'database_url': database_url}
            )
        
        # Check for Supabase environment variables
        if os.getenv('SUPABASE_URL'):
            # Production: PostgreSQL (Supabase)
            host = os.getenv('SUPABASE_URL')
            port = os.getenv('SUPABASE_PORT', '5432')
            dbname = os.getenv('SUPABASE_DB_NAME', 'postgres')
            user = os.getenv('SUPABASE_USER', 'postgres')
            password = os.getenv('SUPABASE_PASSWORD')
            
            if not all([host, port, dbname, user, password]):
                logger.warning("⚠️ Missing some Supabase configuration, falling back to SQLite")
                return self._get_sqlite_config()
            
            connection_params = {
                'host': host,
                'port': int(port),
                'database': dbname,
                'user': user,
                'password': password
            }
            
            return DatabaseConfig(
                database_url=f"postgresql://{user}:{password}@{host}:{port}/{dbname}",
                database_type='postgresql',
                connection_params=connection_params
            )
        else:
            logger.info("ℹ️ No PostgreSQL configuration found, using SQLite")
            return self._get_sqlite_config()
    
    def _get_sqlite_config(self) -> DatabaseConfig:
        """Get SQLite configuration for development"""
        return DatabaseConfig(
            database_url='smartsafe_saas.db',
            database_type='sqlite',
            connection_params={'database': 'smartsafe_saas.db'}
        )
    
    def get_connection(self, timeout: int = 30):
        """Get database connection with retry mechanism"""
        try:
            if self.db_type == 'postgresql':
                # Check if we have DATABASE_URL
                if 'database_url' in self.config.connection_params:
                    # Use DATABASE_URL directly
                    import psycopg2
                    return psycopg2.connect(self.config.connection_params['database_url'])
                else:
                    # Use secure connector for Supabase
                    return self.secure_connector.get_connection()
            else:
                conn = sqlite3.connect(
                    self.config.database_url,
                    timeout=timeout
                )
                conn.row_factory = sqlite3.Row
                return conn
                
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Don't re-raise immediately, let the caller handle it
            return None
    
    def init_database(self):
        """Initialize database tables"""
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
            cursor = conn.cursor()
            
            logger.info("🔧 Creating database tables...")
            
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
                        subscription_type TEXT DEFAULT 'basic',
                        subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_end TIMESTAMP,
                        status TEXT DEFAULT 'active',
                        api_key TEXT UNIQUE,
                        required_ppe TEXT,
                        profile_image TEXT,
                        sector_config TEXT,
                        ppe_requirements TEXT,
                        compliance_settings TEXT,
                        email_notifications BOOLEAN DEFAULT TRUE,
                        sms_notifications BOOLEAN DEFAULT FALSE,
                        push_notifications BOOLEAN DEFAULT TRUE,
                        violation_alerts BOOLEAN DEFAULT TRUE,
                        system_alerts BOOLEAN DEFAULT TRUE,
                        report_notifications BOOLEAN DEFAULT TRUE,
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
                        subscription_type VARCHAR(50) DEFAULT 'basic',
                        subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_end TIMESTAMP,
                        status VARCHAR(50) DEFAULT 'active',
                        api_key VARCHAR(255) UNIQUE,
                        required_ppe TEXT,
                        profile_image TEXT,
                        sector_config JSON,
                        ppe_requirements JSON,
                        compliance_settings JSON,
                        email_notifications BOOLEAN DEFAULT TRUE,
                        sms_notifications BOOLEAN DEFAULT FALSE,
                        push_notifications BOOLEAN DEFAULT TRUE,
                        violation_alerts BOOLEAN DEFAULT TRUE,
                        system_alerts BOOLEAN DEFAULT TRUE,
                        report_notifications BOOLEAN DEFAULT TRUE,
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
                        penalty_amount REAL DEFAULT 0,
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
                        penalty_amount DECIMAL(10,2) DEFAULT 0,
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
                        penalty_settings TEXT,
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
                        penalty_settings JSON,
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
            else:  # PostgreSQL
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS sector_config JSON')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS ppe_requirements JSON')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS compliance_settings JSON')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT FALSE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS violation_alerts BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS system_alerts BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS report_notifications BOOLEAN DEFAULT TRUE')
                except:
                    pass  # Column already exists
                try:
                    cursor.execute('ALTER TABLE companies ADD COLUMN IF NOT EXISTS profile_image TEXT')
                except:
                    pass  # Column already exists
            
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
                            penalty REAL DEFAULT 0,
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
                        penalty DECIMAL(10,2) DEFAULT 0,
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
            
            # Her tablo oluşturulduktan sonra commit yap
            conn.commit()
            logger.info("✅ Database tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, query: str, params: tuple = None, fetch_all: bool = True):
        """Execute database query with error handling"""
        try:
            conn = self.get_connection()
            if conn is None:
                logger.error("❌ Database connection failed")
                return None
            
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            # For INSERT, UPDATE, DELETE operations, return rowcount
            if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                result = cursor.rowcount
                conn.commit()
                conn.close()
                return result
            
            # For SELECT operations, return data
            if fetch_all:
                result = cursor.fetchall()
            else:
                result = cursor.fetchone()
            
            conn.commit()
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"❌ Database query error: {e}")
            import traceback
            logger.error(f"❌ Query traceback: {traceback.format_exc()}")
            return None
    
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
                # Get column names
                conn = self.get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM dvr_systems LIMIT 1")
                    columns = [description[0] for description in cursor.description]
                    conn.close()
                    
                    # Create list of dictionaries from results
                    dvr_systems = []
                    for row in result:
                        dvr_systems.append(dict(zip(columns, row)))
                    return dvr_systems
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
                # Get column names
                conn = self.get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM dvr_systems LIMIT 1")
                    columns = [description[0] for description in cursor.description]
                    conn.close()
                    
                    # Create dictionary from result
                    return dict(zip(columns, result))
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
        """Delete DVR system"""
        try:
            query = '''
                DELETE FROM dvr_systems 
                WHERE company_id = ? AND dvr_id = ?
            '''
            
            result = self.execute_query(query, (company_id, dvr_id), fetch_all=False)
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
                # Get column names
                conn = self.get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM dvr_channels LIMIT 1")
                    columns = [description[0] for description in cursor.description]
                    conn.close()
                    
                    # Create list of dictionaries from results
                    channels = []
                    for row in result:
                        channels.append(dict(zip(columns, row)))
                    return channels
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
                # Get column names
                conn = self.get_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM dvr_streams LIMIT 1")
                    columns = [description[0] for description in cursor.description]
                    conn.close()
                    
                    # Create list of dictionaries from results
                    streams = []
                    for row in result:
                        streams.append(dict(zip(columns, row)))
                    return streams
            return []
            
        except Exception as e:
            logger.error(f"❌ Get active DVR streams error: {e}")
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

# Global camera discovery manager instance
camera_discovery_manager = CameraDiscoveryManager(db_adapter)

def get_camera_discovery_manager() -> CameraDiscoveryManager:
    """Get global camera discovery manager instance"""
    return camera_discovery_manager 