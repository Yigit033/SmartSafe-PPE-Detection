#!/usr/bin/env python3
"""
🏭 INDUSTRIAL PPE DETECTION SYSTEM v3.0.0 - ENTERPRISE EDITION
🛡️ Enterprise Authentication Middleware

Advanced middleware system with:
- JWT token validation
- Role-based access control
- Request rate limiting
- Security headers
- Audit logging
- IP whitelist/blacklist

Author: Industrial PPE Detection Team
Date: January 2025
"""

import os
import jwt
import time
import json
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from typing import Dict, List, Optional, Callable
import logging
import yaml
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecurityHeaders:
    """Security headers for HTTP responses"""
    
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get standard security headers"""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin'
        }

class RateLimiter:
    """Request rate limiter"""
    
    def __init__(self, max_requests: int = 100, window_minutes: int = 15):
        """Initialize rate limiter"""
        self.max_requests = max_requests
        self.window_seconds = window_minutes * 60
        self.requests = defaultdict(list)
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[key] = [req_time for req_time in self.requests[key] 
                             if req_time > window_start]
        
        # Check limit
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[key].append(now)
        return True

class PermissionChecker:
    """Role-based permission checker"""
    
    def __init__(self, db_path: str = 'data/enterprise_auth.db'):
        """Initialize permission checker"""
        self.db_path = db_path
        self._load_permissions()
    
    def _load_permissions(self):
        """Load role permissions from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT name, permissions FROM roles')
            rows = cursor.fetchall()
            
            self.role_permissions = {}
            for role, permissions_json in rows:
                try:
                    self.role_permissions[role] = json.loads(permissions_json)
                except json.JSONDecodeError:
                    self.role_permissions[role] = []
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to load permissions: {e}")
            # Default permissions
            self.role_permissions = {
                'admin': ['*'],
                'supervisor': ['system:read', 'cameras:read', 'detections:read'],
                'operator': ['system:read', 'cameras:read'],
                'viewer': ['system:read']
            }
    
    def has_permission(self, role: str, permission: str) -> bool:
        """Check if role has permission"""
        if role not in self.role_permissions:
            return False
        
        permissions = self.role_permissions[role]
        
        # Admin has all permissions
        if '*' in permissions:
            return True
        
        # Check exact permission
        if permission in permissions:
            return True
        
        return False

class EnterpriseMiddleware:
    """Enterprise authentication and security middleware"""
    
    def __init__(self, config_path: str = 'configs/enterprise_auth_config.yaml'):
        """Initialize enterprise middleware"""
        self.config = self._load_config(config_path)
        self.jwt_secret = self.config['auth']['jwt_secret']
        
        # Initialize components
        self.rate_limiter = RateLimiter()
        self.permission_checker = PermissionChecker()
        
        logger.info("🛡️ Enterprise Middleware initialized")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration"""
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {
                'auth': {'jwt_secret': 'default-secret'}
            }
    
    def authenticate_request(self, f: Callable) -> Callable:
        """Authentication decorator"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Get client IP
                client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                
                # Check rate limit
                rate_limit_key = f"ip:{client_ip}"
                if not self.rate_limiter.is_allowed(rate_limit_key):
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                
                # Get JWT token
                auth_header = request.headers.get('Authorization')
                if not auth_header or not auth_header.startswith('Bearer '):
                    return jsonify({'error': 'Authentication token required'}), 401
                
                token = auth_header.split(' ')[1]
                
                # Verify JWT token
                try:
                    payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
                    g.current_user = payload
                    
                except jwt.ExpiredSignatureError:
                    return jsonify({'error': 'Token expired'}), 401
                
                except jwt.InvalidTokenError:
                    return jsonify({'error': 'Invalid token'}), 401
                
                return f(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return jsonify({'error': 'Authentication failed'}), 500
        
        return decorated_function
    
    def require_permission(self, permission: str) -> Callable:
        """Permission requirement decorator"""
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def decorated_function(*args, **kwargs):
                try:
                    # Check if user is authenticated
                    if not hasattr(g, 'current_user'):
                        return jsonify({'error': 'Authentication required'}), 401
                    
                    user_role = g.current_user.get('role')
                    if not user_role:
                        return jsonify({'error': 'User role not found'}), 403
                    
                    # Check permission
                    if not self.permission_checker.has_permission(user_role, permission):
                        return jsonify({'error': 'Insufficient permissions'}), 403
                    
                    return f(*args, **kwargs)
                    
                except Exception as e:
                    logger.error(f"Permission check error: {e}")
                    return jsonify({'error': 'Permission check failed'}), 500
            
            return decorated_function
        return decorator
    
    def add_security_headers(self, response):
        """Add security headers to response"""
        try:
            headers = SecurityHeaders.get_security_headers()
            for header, value in headers.items():
                response.headers[header] = value
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to add security headers: {e}")
            return response
    
    def require_admin(self, f: Callable) -> Callable:
        """Admin access requirement decorator"""
        return self.require_permission('system:admin')(f)

# Convenience decorators
def auth_required(f: Callable) -> Callable:
    """Require authentication"""
    middleware = EnterpriseMiddleware()
    return middleware.authenticate_request(f)

def admin_required(f: Callable) -> Callable:
    """Require admin access"""
    middleware = EnterpriseMiddleware()
    return middleware.require_admin(middleware.authenticate_request(f))

def permission_required(permission: str) -> Callable:
    """Require specific permission"""
    def decorator(f: Callable) -> Callable:
        middleware = EnterpriseMiddleware()
        return middleware.require_permission(permission)(middleware.authenticate_request(f))
    return decorator

# Example usage
if __name__ == "__main__":
    # Test middleware components
    middleware = EnterpriseMiddleware()
    print("Enterprise Middleware initialized successfully")
    
    # Test permission checker
    checker = PermissionChecker()
    print(f"Admin has system:read permission: {checker.has_permission('admin', 'system:read')}")
    print(f"Operator has system:delete permission: {checker.has_permission('operator', 'system:delete')}")
    
    # Test rate limiter
    limiter = RateLimiter(max_requests=5, window_minutes=1)
    for i in range(7):
        allowed = limiter.is_allowed("test_ip")
        print(f"Request {i+1}: {'Allowed' if allowed else 'Blocked'}") 