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
        self.max_retries = 5
        self.retry_delay = 5
        self.connection_timeout = 30
        self.keepalives_idle = 30
        self.keepalives_interval = 10
        self.keepalives_count = 5
    
    def get_ssl_config(self) -> Dict[str, Any]:
        """Get SSL configuration based on available certificates"""
        ssl_config = {
            'sslmode': os.getenv('SSL_MODE', 'require'),
            'keepalives': 1,
            'keepalives_idle': self.keepalives_idle,
            'keepalives_interval': self.keepalives_interval,
            'keepalives_count': self.keepalives_count,
            'connect_timeout': self.connection_timeout,
            'application_name': 'smartsafe_ppe_detection'
        }
        
        # Use system CA certificates
        ssl_config['sslrootcert'] = certifi.where()
        logger.info("Using system CA certificates for SSL verification")
        
        return ssl_config
    
    def test_connection(self, host: str, port: int) -> bool:
        """Test if database host is reachable"""
        try:
            # Create SSL context for connection test
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=certifi.where())
            
            # Try SSL connection
            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    return True
                    
        except (socket.timeout, socket.error, ssl.SSLError) as e:
            logger.error(f"Cannot reach database host {host}:{port} - {e}")
            return False
    
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
                
            except (psycopg2.Error, ConnectionError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
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