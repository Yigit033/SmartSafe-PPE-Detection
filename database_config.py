#!/usr/bin/env python3
"""
SmartSafe AI - Database Configuration Manager
Railway PostgreSQL Support
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

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration for Railway deployment"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.is_railway = os.getenv('RAILWAY_ENVIRONMENT_NAME') is not None
        self.is_production = os.getenv('FLASK_ENV') == 'production'
        
        # Database configuration
        if self.database_url:
            parsed = urlparse(self.database_url)
            self.db_type = parsed.scheme
            self.host = parsed.hostname
            self.port = parsed.port
            self.username = parsed.username
            self.password = parsed.password
            self.database_name = parsed.path.lstrip('/')
        else:
            # Default to SQLite for development
            self.db_type = 'sqlite'
            self.database_name = 'smartsafe_saas.db'
            self.host = None
            self.port = None
            self.username = None
            self.password = None
    
    def get_connection_string(self) -> str:
        """Get database connection string"""
        if self.database_url:
            return self.database_url
        
        if self.db_type == 'sqlite':
            return f'sqlite:///{self.database_name}'
        elif self.db_type == 'postgresql':
            return f'postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database_name}'
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
            return create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False
            )
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def get_raw_connection(self):
        """Get raw database connection for direct SQL operations"""
        if self.db_type == 'sqlite':
            return sqlite3.connect(self.database_name)
        elif self.db_type == 'postgresql':
            return psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database_name,
                cursor_factory=RealDictCursor
            )
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
            'is_railway': self.is_railway,
            'is_production': self.is_production,
            'connection_available': self.test_connection()
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
    
    if info['connection_available']:
        print("\n🚀 Database ready for Railway deployment!")
    else:
        print("\n❌ Database connection failed!") 