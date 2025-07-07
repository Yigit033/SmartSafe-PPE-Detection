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
        logger.info(f"🗄️ Database adapter initialized: {self.db_type}")
    
    def _get_database_config(self) -> DatabaseConfig:
        """Get database configuration from environment"""
        database_url = os.getenv('DATABASE_URL')
        
        if database_url and database_url.startswith('postgresql://'):
            # Production: PostgreSQL (Supabase)
            return DatabaseConfig(
                database_url=database_url,
                database_type='postgresql',
                connection_params=self._parse_postgres_url(database_url)
            )
        else:
            # Development: SQLite
            return DatabaseConfig(
                database_url='smartsafe_saas.db',
                database_type='sqlite',
                connection_params={'database': 'smartsafe_saas.db'}
            )
    
    def _parse_postgres_url(self, url: str) -> Dict[str, str]:
        """Parse PostgreSQL URL into connection parameters"""
        # postgresql://user:password@host:port/database
        import urllib.parse as urlparse
        
        parsed = urlparse.urlparse(url)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading /
            'user': parsed.username,
            'password': parsed.password,
            'sslmode': 'require'
        }
    
    def get_connection(self, timeout: int = 30):
        """Get database connection"""
        try:
            if self.db_type == 'postgresql':
                conn = psycopg2.connect(**self.config.connection_params)
                conn.autocommit = False
                return conn
            else:
                conn = sqlite3.connect(
                    self.config.database_url,
                    timeout=timeout,
                    check_same_thread=False
                )
                conn.row_factory = sqlite3.Row
                return conn
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def execute_query(self, query: str, params: Tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        """Execute database query with universal syntax"""
        try:
            conn = self.get_connection()
            
            if self.db_type == 'postgresql':
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                # Convert SQLite syntax to PostgreSQL
                query = self._convert_query_syntax(query)
            else:
                cursor = conn.cursor()
            
            cursor.execute(query, params)
            
            result = None
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            
            conn.commit()
            conn.close()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Query execution failed: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            raise
    
    def _convert_query_syntax(self, query: str) -> str:
        """Convert SQLite syntax to PostgreSQL syntax"""
        if self.db_type != 'postgresql':
            return query
        
        # Common conversions
        conversions = {
            'AUTOINCREMENT': 'SERIAL',
            'INTEGER PRIMARY KEY AUTOINCREMENT': 'SERIAL PRIMARY KEY',
            'DATETIME DEFAULT CURRENT_TIMESTAMP': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'TEXT': 'TEXT',
            'BOOLEAN': 'BOOLEAN',
            'REAL': 'REAL'
        }
        
        converted_query = query
        for sqlite_syntax, postgres_syntax in conversions.items():
            converted_query = converted_query.replace(sqlite_syntax, postgres_syntax)
        
        return converted_query
    
    def init_database(self):
        """Initialize database tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            logger.info("🔧 Creating database tables...")
            
            # Companies table
            if self.db_type == 'postgresql':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS companies (
                        company_id TEXT PRIMARY KEY,
                        company_name TEXT NOT NULL,
                        sector TEXT NOT NULL,
                        contact_person TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        phone TEXT,
                        address TEXT,
                        max_cameras INTEGER DEFAULT 5,
                        subscription_type TEXT DEFAULT 'basic',
                        subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_end TIMESTAMP,
                        status TEXT DEFAULT 'active',
                        api_key TEXT UNIQUE,
                        required_ppe TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS companies (
                        company_id TEXT PRIMARY KEY,
                        company_name TEXT NOT NULL,
                        sector TEXT NOT NULL,
                        contact_person TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        phone TEXT,
                        address TEXT,
                        max_cameras INTEGER DEFAULT 5,
                        subscription_type TEXT DEFAULT 'basic',
                        subscription_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                        subscription_end DATETIME,
                        status TEXT DEFAULT 'active',
                        api_key TEXT UNIQUE,
                        required_ppe TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
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
            
            # Cameras table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    ip_address TEXT,
                    rtsp_url TEXT,
                    username TEXT,
                    password TEXT,
                    resolution TEXT DEFAULT '1920x1080',
                    fps INTEGER DEFAULT 25,
                    status TEXT DEFAULT 'active',
                    last_detection TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    UNIQUE(company_id, camera_name)
                )
            ''')
            
            # Detections table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    detection_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_people INTEGER,
                    compliant_people INTEGER,
                    violation_people INTEGER,
                    compliance_rate REAL,
                    confidence_score REAL,
                    image_path TEXT,
                    detection_data TEXT,
                    track_id TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
                )
            ''')
            
            # Violations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS violations (
                    violation_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    user_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    violation_type TEXT NOT NULL,
                    missing_ppe TEXT,
                    severity TEXT DEFAULT 'medium',
                    penalty_amount REAL DEFAULT 0,
                    image_path TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_by TEXT,
                    resolved_at TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
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
            
            conn.commit()
            conn.close()
            
            logger.info("✅ Database tables created successfully")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

# Global database adapter instance
db_adapter = DatabaseAdapter()

def get_db_adapter() -> DatabaseAdapter:
    """Get global database adapter instance"""
    return db_adapter 