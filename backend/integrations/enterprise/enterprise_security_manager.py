#!/usr/bin/env python3
"""
SmartSafe AI - Enterprise Security Manager
Professional security management with authentication, authorization, and monitoring
"""

import hashlib
import secrets
import jwt  # PyJWT
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import threading
from collections import defaultdict, deque
import re
from pathlib import Path

class UserRole(Enum):
    """User roles with different permission levels"""
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"

class Permission(Enum):
    """System permissions"""
    # System administration
    SYSTEM_ADMIN = "system.admin"
    SYSTEM_CONFIG = "system.config"
    SYSTEM_MONITOR = "system.monitor"
    
    # Company management
    COMPANY_CREATE = "company.create"
    COMPANY_DELETE = "company.delete"
    COMPANY_UPDATE = "company.update"
    COMPANY_VIEW = "company.view"
    
    # User management
    USER_CREATE = "user.create"
    USER_DELETE = "user.delete"
    USER_UPDATE = "user.update"
    USER_VIEW = "user.view"
    
    # Camera management
    CAMERA_CREATE = "camera.create"
    CAMERA_DELETE = "camera.delete"
    CAMERA_UPDATE = "camera.update"
    CAMERA_VIEW = "camera.view"
    CAMERA_CONTROL = "camera.control"
    
    # Detection and monitoring
    DETECTION_START = "detection.start"
    DETECTION_STOP = "detection.stop"
    DETECTION_CONFIG = "detection.config"
    DETECTION_VIEW = "detection.view"
    
    # Reports and analytics
    REPORTS_VIEW = "reports.view"
    REPORTS_EXPORT = "reports.export"
    ANALYTICS_VIEW = "analytics.view"
    
    # API access
    API_ACCESS = "api.access"
    API_ADMIN = "api.admin"

@dataclass
class SecurityEvent:
    """Security event for auditing"""
    event_id: str
    event_type: str
    user_id: Optional[str]
    company_id: Optional[str]
    ip_address: str
    user_agent: str
    timestamp: datetime
    details: Dict[str, Any]
    severity: str = "info"  # info, warning, error, critical
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class UserSession:
    """User session information"""
    session_id: str
    user_id: str
    company_id: str
    role: UserRole
    permissions: Set[Permission]
    ip_address: str
    user_agent: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True

class EnterpriseSecurityManager:
    """Enterprise-grade security management system"""
    
    def __init__(self, secret_key: str = None, session_timeout: int = 3600):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.session_timeout = session_timeout
        
        # Security storage
        self.active_sessions: Dict[str, UserSession] = {}
        self.security_events: deque = deque(maxlen=10000)
        self.failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self.blocked_ips: Dict[str, datetime] = {}
        
        # Rate limiting
        self.rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Security configuration
        self.max_failed_attempts = 5
        self.lockout_duration = timedelta(minutes=30)
        self.password_policy = {
            'min_length': 8,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_digits': True,
            'require_special': True,
            'max_age_days': 90
        }
        
        # Role-based permissions
        self.role_permissions = self._initialize_role_permissions()
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Cleanup thread
        self.cleanup_thread = None
        self.cleanup_active = False
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("🔒 Enterprise Security Manager initialized")
        
        # Start cleanup
        self.start_cleanup()
    
    def _initialize_role_permissions(self) -> Dict[UserRole, Set[Permission]]:
        """Initialize role-based permissions"""
        return {
            UserRole.SUPER_ADMIN: {
                Permission.SYSTEM_ADMIN,
                Permission.SYSTEM_CONFIG,
                Permission.SYSTEM_MONITOR,
                Permission.COMPANY_CREATE,
                Permission.COMPANY_DELETE,
                Permission.COMPANY_UPDATE,
                Permission.COMPANY_VIEW,
                Permission.USER_CREATE,
                Permission.USER_DELETE,
                Permission.USER_UPDATE,
                Permission.USER_VIEW,
                Permission.API_ADMIN,
                Permission.API_ACCESS
            },
            UserRole.COMPANY_ADMIN: {
                Permission.COMPANY_UPDATE,
                Permission.COMPANY_VIEW,
                Permission.USER_CREATE,
                Permission.USER_DELETE,
                Permission.USER_UPDATE,
                Permission.USER_VIEW,
                Permission.CAMERA_CREATE,
                Permission.CAMERA_DELETE,
                Permission.CAMERA_UPDATE,
                Permission.CAMERA_VIEW,
                Permission.CAMERA_CONTROL,
                Permission.DETECTION_START,
                Permission.DETECTION_STOP,
                Permission.DETECTION_CONFIG,
                Permission.DETECTION_VIEW,
                Permission.REPORTS_VIEW,
                Permission.REPORTS_EXPORT,
                Permission.ANALYTICS_VIEW,
                Permission.API_ACCESS
            },
            UserRole.MANAGER: {
                Permission.COMPANY_VIEW,
                Permission.USER_VIEW,
                Permission.CAMERA_VIEW,
                Permission.CAMERA_CONTROL,
                Permission.DETECTION_START,
                Permission.DETECTION_STOP,
                Permission.DETECTION_VIEW,
                Permission.REPORTS_VIEW,
                Permission.REPORTS_EXPORT,
                Permission.ANALYTICS_VIEW,
                Permission.API_ACCESS
            },
            UserRole.OPERATOR: {
                Permission.COMPANY_VIEW,
                Permission.CAMERA_VIEW,
                Permission.CAMERA_CONTROL,
                Permission.DETECTION_START,
                Permission.DETECTION_STOP,
                Permission.DETECTION_VIEW,
                Permission.REPORTS_VIEW,
                Permission.API_ACCESS
            },
            UserRole.VIEWER: {
                Permission.COMPANY_VIEW,
                Permission.CAMERA_VIEW,
                Permission.DETECTION_VIEW,
                Permission.REPORTS_VIEW
            }
        }
    
    def start_cleanup(self):
        """Start session cleanup thread"""
        if not self.cleanup_active:
            self.cleanup_active = True
            self.cleanup_thread = threading.Thread(target=self._cleanup_sessions, daemon=True)
            self.cleanup_thread.start()
            self.logger.info("🧹 Session cleanup started")
    
    def stop_cleanup(self):
        """Stop session cleanup thread"""
        self.cleanup_active = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        self.logger.info("🧹 Session cleanup stopped")
    
    def _cleanup_sessions(self):
        """Clean up expired sessions and security data"""
        while self.cleanup_active:
            try:
                current_time = datetime.now()
                
                with self.lock:
                    # Clean up expired sessions
                    expired_sessions = [
                        session_id for session_id, session in self.active_sessions.items()
                        if session.expires_at < current_time
                    ]
                    
                    for session_id in expired_sessions:
                        self.logger.info(f"🕐 Session expired: {session_id}")
                        del self.active_sessions[session_id]
                    
                    # Clean up old failed attempts
                    cutoff_time = current_time - self.lockout_duration
                    for ip in list(self.failed_attempts.keys()):
                        self.failed_attempts[ip] = [
                            attempt for attempt in self.failed_attempts[ip]
                            if attempt > cutoff_time
                        ]
                        if not self.failed_attempts[ip]:
                            del self.failed_attempts[ip]
                    
                    # Clean up expired IP blocks
                    expired_blocks = [
                        ip for ip, blocked_until in self.blocked_ips.items()
                        if blocked_until < current_time
                    ]
                    
                    for ip in expired_blocks:
                        del self.blocked_ips[ip]
                        self.logger.info(f"🔓 IP unblocked: {ip}")
                
                time.sleep(300)  # Clean up every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
                time.sleep(60)
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password with salt"""
        if salt is None:
            salt = secrets.token_urlsafe(32)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash"""
        try:
            computed_hash, _ = self.hash_password(password, salt)
            return secrets.compare_digest(password_hash, computed_hash)
        except Exception as e:
            self.logger.error(f"Password verification error: {e}")
            return False
    
    def validate_password_policy(self, password: str) -> Tuple[bool, List[str]]:
        """Validate password against security policy"""
        errors = []
        
        if len(password) < self.password_policy['min_length']:
            errors.append(f"Password must be at least {self.password_policy['min_length']} characters long")
        
        if self.password_policy['require_uppercase'] and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self.password_policy['require_lowercase'] and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self.password_policy['require_digits'] and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if self.password_policy['require_special'] and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        
        # Check for common passwords
        common_passwords = ['password', '123456', 'admin', 'smartsafe']
        if password.lower() in common_passwords:
            errors.append("Password is too common")
        
        return len(errors) == 0, errors
    
    def authenticate_user(self, username: str, password: str, ip_address: str, user_agent: str) -> Optional[UserSession]:
        """Authenticate user and create session"""
        try:
            # Check if IP is blocked
            if self.is_ip_blocked(ip_address):
                self.log_security_event(
                    "authentication_blocked",
                    None, None, ip_address, user_agent,
                    {"reason": "IP blocked", "username": username},
                    "warning"
                )
                return None
            
            # Check rate limiting
            if not self.check_rate_limit(ip_address, "auth", 5, 300):  # 5 attempts per 5 minutes
                self.log_security_event(
                    "authentication_rate_limited",
                    None, None, ip_address, user_agent,
                    {"username": username},
                    "warning"
                )
                return None
            
            # Simulate user lookup (in real implementation, this would query database)
            user_data = self._get_user_data(username)
            
            if not user_data:
                self._record_failed_attempt(ip_address)
                self.log_security_event(
                    "authentication_failed",
                    None, None, ip_address, user_agent,
                    {"reason": "User not found", "username": username},
                    "warning"
                )
                return None
            
            # Verify password
            if not self.verify_password(password, user_data['password_hash'], user_data['salt']):
                self._record_failed_attempt(ip_address)
                self.log_security_event(
                    "authentication_failed",
                    user_data['user_id'], user_data['company_id'], ip_address, user_agent,
                    {"reason": "Invalid password", "username": username},
                    "warning"
                )
                return None
            
            # Create session
            session = self._create_session(user_data, ip_address, user_agent)
            
            self.log_security_event(
                "authentication_success",
                session.user_id, session.company_id, ip_address, user_agent,
                {"username": username, "session_id": session.session_id},
                "info"
            )
            
            return session
            
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            self.log_security_event(
                "authentication_error",
                None, None, ip_address, user_agent,
                {"error": str(e), "username": username},
                "error"
            )
            return None
    
    def _get_user_data(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user data (simulated - in real implementation, query database)"""
        # Simulate users for testing
        test_users = {
            "admin": {
                "user_id": "user_001",
                "username": "admin",
                "company_id": "company_001",
                "role": UserRole.COMPANY_ADMIN,
                "password_hash": "simulated_hash",
                "salt": "simulated_salt",
                "is_active": True
            },
            "operator": {
                "user_id": "user_002",
                "username": "operator",
                "company_id": "company_001",
                "role": UserRole.OPERATOR,
                "password_hash": "simulated_hash",
                "salt": "simulated_salt",
                "is_active": True
            }
        }
        
        return test_users.get(username)
    
    def _create_session(self, user_data: Dict[str, Any], ip_address: str, user_agent: str) -> UserSession:
        """Create user session"""
        session_id = secrets.token_urlsafe(32)
        current_time = datetime.now()
        
        # Get user permissions
        role = user_data['role']
        permissions = self.role_permissions.get(role, set())
        
        session = UserSession(
            session_id=session_id,
            user_id=user_data['user_id'],
            company_id=user_data['company_id'],
            role=role,
            permissions=permissions,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=current_time,
            last_activity=current_time,
            expires_at=current_time + timedelta(seconds=self.session_timeout)
        )
        
        with self.lock:
            self.active_sessions[session_id] = session
        
        return session
    
    def validate_session(self, session_id: str, ip_address: str = None) -> Optional[UserSession]:
        """Validate session and update activity"""
        with self.lock:
            session = self.active_sessions.get(session_id)
            
            if not session:
                return None
            
            current_time = datetime.now()
            
            # Check if session is expired
            if session.expires_at < current_time:
                del self.active_sessions[session_id]
                return None
            
            # Check IP address if provided
            if ip_address and session.ip_address != ip_address:
                self.logger.warning(f"Session IP mismatch: {session_id}")
                return None
            
            # Update activity
            session.last_activity = current_time
            session.expires_at = current_time + timedelta(seconds=self.session_timeout)
            
            return session
    
    def logout_session(self, session_id: str, ip_address: str, user_agent: str):
        """Logout session"""
        with self.lock:
            session = self.active_sessions.get(session_id)
            
            if session:
                self.log_security_event(
                    "logout",
                    session.user_id, session.company_id, ip_address, user_agent,
                    {"session_id": session_id},
                    "info"
                )
                
                del self.active_sessions[session_id]
    
    def check_permission(self, session_id: str, permission: Permission) -> bool:
        """Check if session has required permission"""
        session = self.validate_session(session_id)
        
        if not session:
            return False
        
        return permission in session.permissions
    
    def require_permission(self, session_id: str, permission: Permission, ip_address: str, user_agent: str) -> bool:
        """Require permission and log if denied"""
        session = self.validate_session(session_id)
        
        if not session:
            self.log_security_event(
                "authorization_failed",
                None, None, ip_address, user_agent,
                {"reason": "Invalid session", "permission": permission.value},
                "warning"
            )
            return False
        
        if permission not in session.permissions:
            self.log_security_event(
                "authorization_failed",
                session.user_id, session.company_id, ip_address, user_agent,
                {"reason": "Insufficient permissions", "permission": permission.value, "role": session.role.value},
                "warning"
            )
            return False
        
        return True
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is blocked"""
        if ip_address in self.blocked_ips:
            return self.blocked_ips[ip_address] > datetime.now()
        return False
    
    def _record_failed_attempt(self, ip_address: str):
        """Record failed authentication attempt"""
        current_time = datetime.now()
        
        with self.lock:
            self.failed_attempts[ip_address].append(current_time)
            
            # Check if IP should be blocked
            recent_attempts = [
                attempt for attempt in self.failed_attempts[ip_address]
                if attempt > current_time - self.lockout_duration
            ]
            
            if len(recent_attempts) >= self.max_failed_attempts:
                self.blocked_ips[ip_address] = current_time + self.lockout_duration
                self.logger.warning(f"🚫 IP blocked due to failed attempts: {ip_address}")
    
    def check_rate_limit(self, identifier: str, action: str, limit: int, window: int) -> bool:
        """Check rate limiting"""
        key = f"{identifier}:{action}"
        current_time = time.time()
        
        with self.lock:
            # Clean old entries
            while self.rate_limits[key] and self.rate_limits[key][0] < current_time - window:
                self.rate_limits[key].popleft()
            
            # Check limit
            if len(self.rate_limits[key]) >= limit:
                return False
            
            # Add current request
            self.rate_limits[key].append(current_time)
            return True
    
    def log_security_event(self, event_type: str, user_id: Optional[str], company_id: Optional[str], 
                          ip_address: str, user_agent: str, details: Dict[str, Any], severity: str = "info"):
        """Log security event"""
        event = SecurityEvent(
            event_id=secrets.token_urlsafe(16),
            event_type=event_type,
            user_id=user_id,
            company_id=company_id,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.now(),
            details=details,
            severity=severity
        )
        
        with self.lock:
            self.security_events.append(event)
        
        # Log to file
        log_level = getattr(logging, severity.upper(), logging.INFO)
        self.logger.log(log_level, f"Security Event [{event.event_type}]: {event.details}")
    
    def get_security_events(self, limit: int = 100, event_type: str = None, 
                           user_id: str = None, company_id: str = None) -> List[Dict[str, Any]]:
        """Get security events with filtering"""
        with self.lock:
            events = list(self.security_events)
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        
        if company_id:
            events = [e for e in events if e.company_id == company_id]
        
        # Sort by timestamp (newest first) and limit
        events.sort(key=lambda x: x.timestamp, reverse=True)
        events = events[:limit]
        
        return [event.to_dict() for event in events]
    
    def get_active_sessions(self, company_id: str = None) -> List[Dict[str, Any]]:
        """Get active sessions"""
        with self.lock:
            sessions = list(self.active_sessions.values())
        
        if company_id:
            sessions = [s for s in sessions if s.company_id == company_id]
        
        return [
            {
                "session_id": s.session_id,
                "user_id": s.user_id,
                "company_id": s.company_id,
                "role": s.role.value,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "expires_at": s.expires_at.isoformat()
            }
            for s in sessions
        ]
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Get comprehensive security summary"""
        with self.lock:
            total_sessions = len(self.active_sessions)
            blocked_ips = len(self.blocked_ips)
            failed_attempts = sum(len(attempts) for attempts in self.failed_attempts.values())
            
            # Recent events by type
            recent_events = [e for e in self.security_events if e.timestamp > datetime.now() - timedelta(hours=24)]
            event_counts = defaultdict(int)
            for event in recent_events:
                event_counts[event.event_type] += 1
        
        return {
            "active_sessions": total_sessions,
            "blocked_ips": blocked_ips,
            "failed_attempts_24h": failed_attempts,
            "security_events_24h": len(recent_events),
            "event_types_24h": dict(event_counts),
            "password_policy": self.password_policy,
            "rate_limiting_active": True,
            "session_timeout": self.session_timeout
        }
    
    def export_security_report(self, output_file: str = None) -> str:
        """Export comprehensive security report"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"logs/security_report_{timestamp}.json"
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": self.get_security_summary(),
            "active_sessions": self.get_active_sessions(),
            "recent_events": self.get_security_events(500),
            "blocked_ips": [
                {"ip": ip, "blocked_until": blocked_until.isoformat()}
                for ip, blocked_until in self.blocked_ips.items()
            ]
        }
        
        try:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"📊 Security report exported to {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"Failed to export security report: {e}")
            return None
    
    def shutdown(self):
        """Shutdown security manager"""
        self.logger.info("🔄 Shutting down Enterprise Security Manager...")
        
        # Stop cleanup
        self.stop_cleanup()
        
        # Clear sessions
        with self.lock:
            self.active_sessions.clear()
        
        self.logger.info("✅ Enterprise Security Manager shutdown complete")

# Global security manager
security_manager = EnterpriseSecurityManager()

def get_security_manager() -> EnterpriseSecurityManager:
    """Get global security manager"""
    return security_manager

def authenticate_user(username: str, password: str, ip_address: str, user_agent: str) -> Optional[UserSession]:
    """Authenticate user"""
    return security_manager.authenticate_user(username, password, ip_address, user_agent)

def validate_session(session_id: str, ip_address: str = None) -> Optional[UserSession]:
    """Validate session"""
    return security_manager.validate_session(session_id, ip_address)

def check_permission(session_id: str, permission: Permission) -> bool:
    """Check permission"""
    return security_manager.check_permission(session_id, permission)

def require_permission(session_id: str, permission: Permission, ip_address: str, user_agent: str) -> bool:
    """Require permission"""
    return security_manager.require_permission(session_id, permission, ip_address, user_agent)

# Test function
def test_security_manager():
    """Test the security manager"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🧪 Testing Enterprise Security Manager")
    
    manager = get_security_manager()
    
    # Test authentication
    session = authenticate_user("admin", "password", "192.168.1.100", "Test-Agent")
    if session:
        logger.info(f"✅ Authentication successful: {session.session_id}")
        logger.info(f"👤 User: {session.user_id}, Role: {session.role.value}")
        logger.info(f"🏢 Company: {session.company_id}")
        
        # Test permissions
        can_create_camera = check_permission(session.session_id, Permission.CAMERA_CREATE)
        logger.info(f"📹 Can create camera: {can_create_camera}")
        
        can_admin_system = check_permission(session.session_id, Permission.SYSTEM_ADMIN)
        logger.info(f"⚙️ Can admin system: {can_admin_system}")
        
        # Test session validation
        validated_session = validate_session(session.session_id, "192.168.1.100")
        logger.info(f"✅ Session validation: {validated_session is not None}")
        
    else:
        logger.error("❌ Authentication failed")
    
    # Get security summary
    summary = manager.get_security_summary()
    logger.info(f"📊 Security summary: {summary}")
    
    # Export security report
    report_file = manager.export_security_report()
    logger.info(f"📄 Security report exported to: {report_file}")

if __name__ == "__main__":
    test_security_manager() 