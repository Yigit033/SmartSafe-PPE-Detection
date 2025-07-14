#!/usr/bin/env python3
"""
Secure Database Connector
Handles secure database connections with SSL/TLS support
"""

import os
import logging
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, Any
from pathlib import Path
import socket
import ssl
import time
import certifi
import dns.resolver

logger = logging.getLogger(__name__)

class SecureDatabaseConnector:
    """Manages secure database connections with SSL/TLS"""
    
    def __init__(self):
        # Check for render.com environment
        self.is_render = os.getenv('RENDER') == 'true'
        
        # Set SSL paths based on environment
        self.ssl_dir = Path('/opt/render/project/src/ssl')
        
        # Create SSL directory if it doesn't exist
        try:
            self.ssl_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(str(self.ssl_dir), 0o755)  # Ensure directory is accessible
        except Exception as e:
            logger.warning(f"Could not create SSL directory: {e}. Will use system CA certificates.")
            self.ssl_dir = None
            
        # Set certificate paths
        if self.ssl_dir:
            self.cert_path = self.ssl_dir / 'supabase.crt'
            self.root_cert_path = self.ssl_dir / 'root.crt'
        else:
            self.cert_path = None
            self.root_cert_path = None
        
        # Connection settings
        self.max_retries = 3  # Reduced retries for faster failure
        self.retry_delay = 1  # Reduced delay
        self.connection_timeout = 10  # Reduced timeout
        self.keepalives_idle = 30
        self.keepalives_interval = 10
        self.keepalives_count = 5

    def resolve_host(self, host: str) -> Optional[str]:
        """Resolve hostname to IP address"""
        try:
            # Try IPv4 first
            answers = dns.resolver.resolve(host, 'A')
            return str(answers[0])
        except Exception:
            try:
                # Try IPv6 if IPv4 fails
                answers = dns.resolver.resolve(host, 'AAAA')
                return str(answers[0])
            except Exception as e:
                logger.warning(f"Could not resolve host {host}: {e}")
                return None
    
    def get_ssl_config(self) -> Dict[str, Any]:
        """Get SSL configuration based on available certificates"""
        ssl_config = {
            'sslmode': 'require',  # Force SSL but don't verify certificates
            'keepalives': 1,
            'keepalives_idle': self.keepalives_idle,
            'keepalives_interval': self.keepalives_interval,
            'keepalives_count': self.keepalives_count,
            'connect_timeout': self.connection_timeout,
            'application_name': 'smartsafe_ppe_detection',
            'options': '-c statement_timeout=30000'  # 30 second statement timeout
        }
        
        # For Render.com, use prefer mode for better compatibility
        if self.is_render:
            ssl_config['sslmode'] = 'prefer'
            logger.info("Using SSL prefer mode for Render.com compatibility")
        else:
            # Use system CA certificates for local development
            ssl_config['sslrootcert'] = certifi.where()
            logger.info("Using system CA certificates for SSL verification")
        
        return ssl_config
    
    def test_connection(self, host: str, port: int) -> bool:
        """Test if database host is reachable"""
        try:
            # Simple socket test first
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                logger.info(f"✅ Network connection to {host}:{port} successful")
                return True
            else:
                logger.warning(f"⚠️ Network connection to {host}:{port} failed (code: {result})")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Connection test failed for {host}:{port}: {e}")
            # Don't fail completely, let psycopg2 handle the actual connection
            return True
    
    def get_connection(self, database_url: Optional[str] = None) -> psycopg2.extensions.connection:
        """Get database connection with retry mechanism"""
        # Get connection parameters
        if database_url:
            params = self._parse_database_url(database_url)
        else:
            # Try DATABASE_URL first
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                params = self._parse_database_url(database_url)
            else:
                # Fallback to individual parameters
                params = {
                    'host': os.getenv('SUPABASE_URL'),
                    'port': int(os.getenv('SUPABASE_PORT', '5432')),
                    'database': os.getenv('SUPABASE_DB_NAME', 'postgres'),
                    'user': os.getenv('SUPABASE_USER', 'postgres'),
                    'password': os.getenv('SUPABASE_PASSWORD')
                }
        
        if not all(params.values()):
            raise ValueError("Missing required database connection parameters")
        
        # Add SSL configuration
        params.update(self.get_ssl_config())
        
        # Try to connect with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🔄 Database connection attempt {attempt + 1}/{self.max_retries} to {params['host']}:{params['port']}")
                
                # Test network connectivity first (but don't fail on it)
                self.test_connection(params['host'], params['port'])
                
                # Try to establish connection
                conn = psycopg2.connect(
                    **params,
                    cursor_factory=psycopg2.extras.RealDictCursor
                )
                
                # Test the connection
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                
                logger.info(f"✅ Successfully connected to database at {params['host']}")
                return conn
                
            except psycopg2.OperationalError as e:
                last_error = e
                error_msg = str(e).lower()
                
                if 'timeout' in error_msg or 'connection refused' in error_msg:
                    logger.warning(f"⚠️ Connection timeout/refused on attempt {attempt + 1}: {e}")
                elif 'ssl' in error_msg:
                    logger.warning(f"⚠️ SSL error on attempt {attempt + 1}: {e}")
                    # Try without SSL verification on next attempt
                    if attempt < self.max_retries - 1:
                        params['sslmode'] = 'disable'
                        logger.info("🔄 Retrying without SSL...")
                else:
                    logger.warning(f"⚠️ Database error on attempt {attempt + 1}: {e}")
                
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (attempt + 1)
                    logger.info(f"⏳ Waiting {sleep_time} seconds before retry...")
                    time.sleep(sleep_time)
                continue
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                continue
        
        logger.error(f"❌ Failed to connect to database after {self.max_retries} attempts: {last_error}")
        raise last_error
    
    def _parse_database_url(self, url: str) -> Dict[str, Any]:
        """Parse database URL into connection parameters"""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],
            'user': parsed.username,
            'password': parsed.password
        }

# Global connector instance
secure_db = SecureDatabaseConnector()

def get_secure_db_connector() -> SecureDatabaseConnector:
    """Get global secure database connector instance"""
    return secure_db 