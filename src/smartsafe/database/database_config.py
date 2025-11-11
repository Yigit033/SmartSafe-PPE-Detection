#!/usr/bin/env python3
"""
SmartSafe AI - Database Configuration Manager
Supabase PostgreSQL Support
"""

import os
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import certifi

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration for Supabase deployment"""
    
    def __init__(self):
        # Check for render.com environment
        self.is_render = os.getenv('RENDER') == 'true'
        self.is_production = os.getenv('FLASK_ENV') == 'production'
        
        # Set SSL certificate path based on environment
        if self.is_render:
            self.ssl_cert_path = '/opt/render/project/src/ssl/supabase.crt'
        else:
            self.ssl_cert_path = os.path.join(os.path.dirname(__file__), 'ssl', 'supabase.crt')
        
        # Supabase configuration
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_port = os.getenv('SUPABASE_PORT', '5432')
        self.supabase_db = os.getenv('SUPABASE_DB_NAME', 'postgres')
        self.supabase_user = os.getenv('SUPABASE_USER')
        self.supabase_password = os.getenv('SUPABASE_PASSWORD')
        
        # Database configuration
        if self.supabase_url and self.supabase_user and self.supabase_password:
            self.db_type = 'postgresql'
            self.host = self.supabase_url
            self.port = int(self.supabase_port)
            self.username = self.supabase_user
            self.password = self.supabase_password
            self.database_name = self.supabase_db
        else:
            # Default to SQLite for development
            self.db_type = 'sqlite'
            self.database_name = 'data/databases/smartsafe_saas.db'
            self.host = None
            self.port = None
            self.username = None
            self.password = None
    
    def get_connection_string(self) -> str:
        """Get database connection string"""
        if self.db_type == 'sqlite':
            return f'sqlite:///{self.database_name}'
        elif self.db_type == 'postgresql':
            ssl_mode = 'verify-full' if os.path.exists(self.ssl_cert_path) else 'require'
            ssl_params = f"?sslmode={ssl_mode}"
            if ssl_mode == 'verify-full':
                ssl_params += f"&sslcert={self.ssl_cert_path}"
            
            return f'postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database_name}{ssl_params}'
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def get_engine(self):
        """Get SQLAlchemy engine"""
        connection_string = self.get_connection_string()
        
        if self.db_type == 'sqlite':
            return create_engine(
                connection_string,
                poolclass=StaticPool,
                connect_args={'check_same_thread': False},
                echo=False
            )
        elif self.db_type == 'postgresql':
            connect_args = {}
            if os.path.exists(self.ssl_cert_path):
                connect_args['sslmode'] = 'verify-full'
                connect_args['sslcert'] = self.ssl_cert_path
            else:
                connect_args['sslmode'] = 'require'
            
            # 🚀 PRODUCTION POOL OPTIMIZATION - Render.com optimized
            return create_engine(
                connection_string,
                # Connection pool settings - optimized for Render.com
                pool_size=3,              # Base connections in pool
                max_overflow=1,          # Additional connections when needed
                pool_timeout=30,          # Wait 30s for available connection
                pool_recycle=1800,        # Recycle connections every 30 minutes
                pool_pre_ping=True,       # Test connections before using
                # Connection arguments
                connect_args=connect_args,
                echo=False,
                # Additional optimizations
                execution_options={
                    "isolation_level": "READ_COMMITTED"
                }
            )
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def get_raw_connection(self):
        """Get raw database connection for direct SQL operations"""
        if self.db_type == 'sqlite':
            return sqlite3.connect(self.database_name)
        elif self.db_type == 'postgresql':
            connect_args = {
                'host': self.host,
                'port': self.port,
                'user': self.username,
                'password': self.password,
                'database': self.database_name,
                'cursor_factory': RealDictCursor
            }
            
            if os.path.exists(self.ssl_cert_path):
                connect_args['sslmode'] = 'verify-full'
                connect_args['sslcert'] = self.ssl_cert_path
            else:
                connect_args['sslmode'] = 'require'
            
            return psycopg2.connect(**connect_args)
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            engine = self.get_engine()
            with engine.connect() as conn:
                if self.db_type == 'sqlite':
                    conn.execute(text("SELECT 1"))
                elif self.db_type == 'postgresql':
                    conn.execute(text("SELECT 1"))
                else:
                    return False
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database configuration info"""
        return {
            'type': self.db_type,
            'host': self.host,
            'port': self.port,
            'database': self.database_name,
            'is_railway': self.is_render, # Assuming is_railway is based on RENDER env
            'is_production': self.is_production,
            'connection_available': self.test_connection(),
            'ssl_enabled': os.path.exists(self.ssl_cert_path)
        }

# Global database config instance
db_config = DatabaseConfig()

# SQLAlchemy setup
Base = declarative_base()

def get_db_session():
    """Get database session"""
    engine = db_config.get_engine()
    Session = sessionmaker(bind=engine)
    return Session()

def init_database():
    """Initialize database tables"""
    try:
        engine = db_config.get_engine()
        
        # Create tables
        Base.metadata.create_all(engine)
        
        # Run initial data setup if needed
        with engine.connect() as conn:
            if db_config.db_type == 'sqlite':
                # SQLite setup
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id INTEGER PRIMARY KEY,
                        company_id TEXT UNIQUE,
                        company_name TEXT,
                        sector TEXT,
                        contact_person TEXT,
                        email TEXT,
                        phone TEXT,
                        address TEXT,
                        max_cameras INTEGER,
                        subscription_type TEXT,
                        subscription_start TEXT,
                        subscription_end TEXT,
                        status TEXT,
                        created_at TEXT,
                        api_key TEXT
                    )
                """))
            elif db_config.db_type == 'postgresql':
                # PostgreSQL setup
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id SERIAL PRIMARY KEY,
                        company_id VARCHAR(255) UNIQUE,
                        company_name VARCHAR(255),
                        sector VARCHAR(100),
                        contact_person VARCHAR(255),
                        email VARCHAR(255),
                        phone VARCHAR(50),
                        address TEXT,
                        max_cameras INTEGER,
                        subscription_type VARCHAR(100),
                        subscription_start TIMESTAMP,
                        subscription_end TIMESTAMP,
                        status VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        api_key VARCHAR(255)
                    )
                """))
            
            conn.commit()
        
        logger.info(f"Database initialized successfully ({db_config.db_type})")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    print("🗃️ SmartSafe AI - Database Configuration Test")
    print("=" * 50)
    
    config = DatabaseConfig()
    info = config.get_database_info()
    
    print(f"Database Type: {info['type']}")
    print(f"Host: {info['host']}")
    print(f"Port: {info['port']}")
    print(f"Database: {info['database']}")
    print(f"Railway Environment: {info['is_railway']}")
    print(f"Production Mode: {info['is_production']}")
    print(f"Connection Test: {'✅ Success' if info['connection_available'] else '❌ Failed'}")
    print(f"SSL Enabled: {info['ssl_enabled']}")
    
    if info['connection_available']:
        print("\n🚀 Database ready for Railway deployment!")
    else:
        print("\n❌ Database connection failed!") 