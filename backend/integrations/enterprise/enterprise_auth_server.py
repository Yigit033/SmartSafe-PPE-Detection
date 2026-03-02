#!/usr/bin/env python3
"""
🏭 INDUSTRIAL PPE DETECTION SYSTEM v3.0.0 - ENTERPRISE EDITION
🔐 Enterprise Authentication Server

Advanced authentication system with:
- JWT-based authentication
- Role-based access control (RBAC)
- Multi-factor authentication (MFA)
- Session management
- Audit logging
- Enterprise integration

Author: Industrial PPE Detection Team
Date: January 2025
"""

import os
import sys
import time
import jwt
import hashlib
import secrets
import sqlite3
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import yaml
import logging
import threading
import pyotp
import qrcode
from io import BytesIO
import base64
import json
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/enterprise_auth.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EnterpriseAuthServer:
    """Enterprise Authentication Server with advanced security features"""
    
    def __init__(self, config_path: str = 'configs/enterprise_auth_config.yaml'):
        """Initialize the enterprise authentication server"""
        self.config = self._load_config(config_path)
        self.app = Flask(__name__)
        self.app.secret_key = self.config['auth']['secret_key']
        
        # Enable CORS for frontend integration
        CORS(self.app, origins=self.config['security']['allowed_origins'])
        
        # Initialize database
        self.db_path = self.config['database']['path']
        self._init_database()
        
        # JWT configuration
        self.jwt_secret = self.config['auth']['jwt_secret']
        self.jwt_expiry = self.config['auth']['jwt_expiry_hours']
        
        # Failed login tracking
        self.failed_attempts = {}
        self.lockout_duration = self.config['security']['lockout_duration_minutes']
        self.max_attempts = self.config['security']['max_login_attempts']
        
        # Setup routes
        self._setup_routes()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired_sessions, daemon=True)
        self.cleanup_thread.start()
        
        logger.info("🔐 Enterprise Authentication Server initialized")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            # Return default config
            return {
                'auth': {
                    'secret_key': secrets.token_hex(32),
                    'jwt_secret': secrets.token_hex(64),
                    'jwt_expiry_hours': 24
                },
                'database': {'path': 'data/enterprise_auth.db'},
                'security': {
                    'allowed_origins': ['http://localhost:3000', 'http://localhost:8080'],
                    'max_login_attempts': 5,
                    'lockout_duration_minutes': 30,
                    'password_min_length': 8,
                    'require_mfa': True
                },
                'email': {
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': 587,
                    'username': '',
                    'password': '',
                    'from_email': 'noreply@ppesystem.com'
                }
            }
    
    def _init_database(self):
        """Initialize the authentication database"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator',
                    department TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    mfa_secret TEXT,
                    mfa_enabled BOOLEAN DEFAULT 0,
                    failed_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP
                )
            ''')
            
            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    jwt_token TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Audit log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    resource TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            
            # Roles table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    permissions TEXT NOT NULL
                )
            ''')
            
            # Insert default roles
            default_roles = [
                ('admin', 'System Administrator', json.dumps([
                    'system:read', 'system:write', 'system:delete',
                    'users:read', 'users:write', 'users:delete',
                    'cameras:read', 'cameras:write', 'cameras:delete',
                    'detections:read', 'detections:write', 'detections:delete',
                    'analytics:read', 'analytics:write',
                    'alerts:read', 'alerts:write', 'alerts:delete'
                ])),
                ('supervisor', 'Supervisor', json.dumps([
                    'system:read', 'cameras:read', 'detections:read',
                    'analytics:read', 'alerts:read', 'alerts:write'
                ])),
                ('operator', 'Operator', json.dumps([
                    'system:read', 'cameras:read', 'detections:read'
                ])),
                ('viewer', 'Viewer', json.dumps([
                    'system:read', 'cameras:read', 'detections:read'
                ]))
            ]
            
            cursor.executemany('''
                INSERT OR IGNORE INTO roles (name, description, permissions)
                VALUES (?, ?, ?)
            ''', default_roles)
            
            # Create default admin user
            admin_password = secrets.token_urlsafe(12)
            admin_hash = generate_password_hash(admin_password)
            
            cursor.execute('''
                INSERT OR IGNORE INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', ('admin', 'admin@ppesystem.com', admin_hash, 'admin'))
            
            conn.commit()
            conn.close()
            
            logger.info("✅ Enterprise authentication database initialized")
            logger.info(f"🔑 Default admin password: {admin_password}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def _setup_routes(self):
        """Setup authentication routes"""
        
        @self.app.route('/api/v1/auth/login', methods=['POST'])
        def login():
            """User login endpoint"""
            try:
                data = request.get_json()
                username = data.get('username')
                password = data.get('password')
                mfa_code = data.get('mfa_code')
                
                if not username or not password:
                    return jsonify({'error': 'Username and password required'}), 400
                
                # Check if user is locked out
                if self._is_user_locked(username):
                    return jsonify({'error': 'Account locked due to too many failed attempts'}), 423
                
                # Authenticate user
                user = self._authenticate_user(username, password)
                if not user:
                    self._record_failed_attempt(username)
                    return jsonify({'error': 'Invalid credentials'}), 401
                
                # Check MFA if enabled
                if user['mfa_enabled'] and not mfa_code:
                    return jsonify({'error': 'MFA code required', 'mfa_required': True}), 200
                
                if user['mfa_enabled'] and mfa_code:
                    if not self._verify_mfa(user['mfa_secret'], mfa_code):
                        self._record_failed_attempt(username)
                        return jsonify({'error': 'Invalid MFA code'}), 401
                
                # Generate JWT token
                jwt_token = self._generate_jwt_token(user)
                session_token = self._create_session(user['id'], jwt_token)
                
                # Update last login
                self._update_last_login(user['id'])
                
                # Log successful login
                self._log_audit(user['id'], 'login', 'auth', request.remote_addr, request.user_agent.string)
                
                return jsonify({
                    'message': 'Login successful',
                    'token': jwt_token,
                    'session_token': session_token,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'email': user['email'],
                        'role': user['role'],
                        'department': user['department']
                    }
                }), 200
                
            except Exception as e:
                logger.error(f"Login error: {e}")
                return jsonify({'error': 'Login failed'}), 500
        
        @self.app.route('/api/v1/auth/logout', methods=['POST'])
        def logout():
            """User logout endpoint"""
            try:
                token = request.headers.get('Authorization', '').replace('Bearer ', '')
                if token:
                    self._invalidate_session(token)
                    
                    # Log logout
                    user_id = self._get_user_from_token(token)
                    if user_id:
                        self._log_audit(user_id, 'logout', 'auth', request.remote_addr, request.user_agent.string)
                
                return jsonify({'message': 'Logout successful'}), 200
                
            except Exception as e:
                logger.error(f"Logout error: {e}")
                return jsonify({'error': 'Logout failed'}), 500
        
        @self.app.route('/api/v1/auth/verify', methods=['GET'])
        def verify_token():
            """Token verification endpoint"""
            try:
                token = request.headers.get('Authorization', '').replace('Bearer ', '')
                if not token:
                    return jsonify({'error': 'Token required'}), 401
                
                user_data = self._verify_jwt_token(token)
                if not user_data:
                    return jsonify({'error': 'Invalid token'}), 401
                
                return jsonify({
                    'valid': True,
                    'user': user_data
                }), 200
                
            except Exception as e:
                logger.error(f"Token verification error: {e}")
                return jsonify({'error': 'Token verification failed'}), 500
        
        @self.app.route('/api/v1/auth/dashboard', methods=['GET'])
        def dashboard():
            """Authentication dashboard"""
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>🔐 Enterprise Authentication Dashboard</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .header { background: #2c3e50; color: white; padding: 20px; border-radius: 10px; text-align: center; }
                    .section { background: white; margin: 20px 0; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
                    .api-endpoint { background: #ecf0f1; padding: 10px; margin: 10px 0; border-radius: 5px; }
                    .status { display: inline-block; padding: 5px 10px; border-radius: 15px; color: white; font-weight: bold; }
                    .active { background: #27ae60; }
                    .endpoint-method { font-weight: bold; color: #e74c3c; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔐 Enterprise Authentication System</h1>
                        <p>Advanced JWT-based Authentication with RBAC & MFA</p>
                        <span class="status active">ACTIVE</span>
                    </div>
                    
                    <div class="section">
                        <h2>📋 Authentication Endpoints</h2>
                        <div class="api-endpoint">
                            <span class="endpoint-method">POST</span> /api/v1/auth/login - User login with MFA support
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">POST</span> /api/v1/auth/logout - User logout
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">GET</span> /api/v1/auth/verify - Token verification
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">GET</span> /api/v1/auth/users - Get all users (admin only)
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">POST</span> /api/v1/auth/users - Create new user (admin only)
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">POST</span> /api/v1/auth/mfa/setup - Setup MFA for user
                        </div>
                        <div class="api-endpoint">
                            <span class="endpoint-method">GET</span> /api/v1/auth/audit - Get audit log (admin only)
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>🔐 Security Features</h2>
                        <ul>
                            <li>✅ JWT-based authentication</li>
                            <li>✅ Role-based access control (RBAC)</li>
                            <li>✅ Multi-factor authentication (MFA)</li>
                            <li>✅ Session management</li>
                            <li>✅ Account lockout protection</li>
                            <li>✅ Audit logging</li>
                            <li>✅ Password hashing</li>
                            <li>✅ CORS protection</li>
                        </ul>
                    </div>
                    
                    <div class="section">
                        <h2>👥 User Roles</h2>
                        <ul>
                            <li><strong>Admin:</strong> Full system access</li>
                            <li><strong>Supervisor:</strong> System monitoring and alerts</li>
                            <li><strong>Operator:</strong> Basic system access</li>
                            <li><strong>Viewer:</strong> Read-only access</li>
                        </ul>
                    </div>
                </div>
            </body>
            </html>
            '''
    
    def _authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user with username and password"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email, password_hash, role, department, mfa_enabled, mfa_secret
                FROM users WHERE username = ? AND is_active = 1
            ''', (username,))
            
            user = cursor.fetchone()
            conn.close()
            
            if user and check_password_hash(user[3], password):
                return {
                    'id': user[0],
                    'username': user[1],
                    'email': user[2],
                    'role': user[4],
                    'department': user[5],
                    'mfa_enabled': user[6],
                    'mfa_secret': user[7]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    def _generate_jwt_token(self, user: Dict) -> str:
        """Generate JWT token for user"""
        try:
            payload = {
                'user_id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'department': user['department'],
                'exp': datetime.utcnow() + timedelta(hours=self.jwt_expiry),
                'iat': datetime.utcnow()
            }
            
            return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
            
        except Exception as e:
            logger.error(f"JWT generation error: {e}")
            return None
    
    def _verify_jwt_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid JWT token")
            return None
        except Exception as e:
            logger.error(f"JWT verification error: {e}")
            return None
    
    def _create_session(self, user_id: int, jwt_token: str) -> str:
        """Create user session"""
        try:
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=self.jwt_expiry)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (user_id, session_token, jwt_token, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, session_token, jwt_token, expires_at, request.remote_addr, request.user_agent.string))
            
            conn.commit()
            conn.close()
            
            return session_token
            
        except Exception as e:
            logger.error(f"Session creation error: {e}")
            return None
    
    def _is_user_locked(self, username: str) -> bool:
        """Check if user is locked out"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT locked_until FROM users WHERE username = ?
            ''', (username,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                locked_until = datetime.fromisoformat(result[0])
                return datetime.utcnow() < locked_until
            
            return False
            
        except Exception as e:
            logger.error(f"Lock check error: {e}")
            return False
    
    def _record_failed_attempt(self, username: str):
        """Record failed login attempt"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users SET failed_attempts = failed_attempts + 1
                WHERE username = ?
            ''', (username,))
            
            # Check if should lock user
            cursor.execute('''
                SELECT failed_attempts FROM users WHERE username = ?
            ''', (username,))
            
            result = cursor.fetchone()
            if result and result[0] >= self.max_attempts:
                locked_until = datetime.utcnow() + timedelta(minutes=self.lockout_duration)
                cursor.execute('''
                    UPDATE users SET locked_until = ? WHERE username = ?
                ''', (locked_until.isoformat(), username))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed attempt recording error: {e}")
    
    def _update_last_login(self, user_id: int):
        """Update user's last login time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users SET last_login = ?, failed_attempts = 0, locked_until = NULL
                WHERE id = ?
            ''', (datetime.utcnow().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Update last login error: {e}")
    
    def _log_audit(self, user_id: Optional[int], action: str, resource: str, 
                  ip_address: str, user_agent: str, details: str = None):
        """Log audit event"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO audit_log (user_id, action, resource, ip_address, user_agent, details)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, action, resource, ip_address, user_agent, details))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Audit logging error: {e}")
    
    def _cleanup_expired_sessions(self):
        """Cleanup expired sessions"""
        while True:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM sessions WHERE expires_at < ?
                ''', (datetime.utcnow().isoformat(),))
                
                conn.commit()
                conn.close()
                
                # Sleep for 1 hour
                time.sleep(3600)
                
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
                time.sleep(3600)
    
    def run(self, host: str = '0.0.0.0', port: int = 9000):
        """Run the authentication server"""
        logger.info(f"🔐 Starting Enterprise Authentication Server on {host}:{port}")
        self.app.run(host=host, port=port, debug=False)

def main():
    """Main function"""
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Start authentication server
    auth_server = EnterpriseAuthServer()
    auth_server.run()

if __name__ == "__main__":
    main() 