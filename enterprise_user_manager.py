#!/usr/bin/env python3
"""
🏭 INDUSTRIAL PPE DETECTION SYSTEM v3.0.0 - ENTERPRISE EDITION
👥 Enterprise User Manager

Advanced user management system with:
- User lifecycle management
- Role-based permissions
- User analytics and reporting
- Bulk user operations
- User profile management
- Department management

Author: Industrial PPE Detection Team
Date: January 2025
"""

import os
import sqlite3
import hashlib
import secrets
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import yaml
from dataclasses import dataclass
from enum import Enum
import pyotp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserRole(Enum):
    """User roles enumeration"""
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    VIEWER = "viewer"

class UserStatus(Enum):
    """User status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    LOCKED = "locked"

@dataclass
class UserProfile:
    """User profile data class"""
    id: int
    username: str
    email: str
    role: str
    department: str
    first_name: str
    last_name: str
    phone: str
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool
    mfa_enabled: bool
    failed_attempts: int
    locked_until: Optional[datetime]

class EnterpriseUserManager:
    """Enterprise User Management System"""
    
    def __init__(self, db_path: str = 'data/enterprise_auth.db'):
        """Initialize the user manager"""
        self.db_path = db_path
        self._init_database()
        logger.info("👥 Enterprise User Manager initialized")
    
    def _init_database(self):
        """Initialize user management database tables"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Enhanced users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    address TEXT,
                    emergency_contact TEXT,
                    badge_number TEXT,
                    hire_date DATE,
                    supervisor_id INTEGER,
                    profile_image_path TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (supervisor_id) REFERENCES users (id)
                )
            ''')
            
            # Departments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    manager_id INTEGER,
                    budget REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (manager_id) REFERENCES users (id)
                )
            ''')
            
            # User groups table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    permissions TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # User group memberships
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_group_memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    added_by INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (group_id) REFERENCES user_groups (id),
                    FOREIGN KEY (added_by) REFERENCES users (id),
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            # User activity log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    activity_details TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Password history
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # User preferences
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    preference_key TEXT NOT NULL,
                    preference_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, preference_key)
                )
            ''')
            
            # Insert default departments
            default_departments = [
                ("Safety", "Safety and Compliance Department", None, 50000),
                ("Production", "Production Operations", None, 150000),
                ("Maintenance", "Equipment Maintenance", None, 75000),
                ("Quality", "Quality Control", None, 60000),
                ("Administration", "Administrative Services", None, 40000)
            ]
            
            cursor.executemany('''
                INSERT OR IGNORE INTO departments (name, description, manager_id, budget)
                VALUES (?, ?, ?, ?)
            ''', default_departments)
            
            conn.commit()
            conn.close()
            
            logger.info("✅ User management database initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize user management database: {e}")
    
    def create_user(self, username: str, email: str, password: str, 
                   role: str = "operator", department: str = None, 
                   first_name: str = None, last_name: str = None,
                   phone: str = None) -> Optional[int]:
        """Create a new user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
            if cursor.fetchone():
                logger.warning(f"User {username} or email {email} already exists")
                return None
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # Insert user
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role, department, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (username, email, password_hash, role, department))
            
            user_id = cursor.lastrowid
            
            # Insert user profile
            cursor.execute('''
                INSERT INTO user_profiles (user_id, first_name, last_name, phone)
                VALUES (?, ?, ?, ?)
            ''', (user_id, first_name, last_name, phone))
            
            # Store password in history
            cursor.execute('''
                INSERT INTO password_history (user_id, password_hash)
                VALUES (?, ?)
            ''', (user_id, password_hash))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ User {username} created successfully")
            return user_id
            
        except Exception as e:
            logger.error(f"Failed to create user {username}: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[UserProfile]:
        """Get user by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.role, u.department, 
                       up.first_name, up.last_name, up.phone,
                       u.created_at, u.last_login, u.is_active, u.mfa_enabled,
                       u.failed_attempts, u.locked_until
                FROM users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
                WHERE u.id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return UserProfile(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    role=row[3],
                    department=row[4],
                    first_name=row[5],
                    last_name=row[6],
                    phone=row[7],
                    created_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    last_login=datetime.fromisoformat(row[9]) if row[9] else None,
                    is_active=bool(row[10]),
                    mfa_enabled=bool(row[11]),
                    failed_attempts=row[12],
                    locked_until=datetime.fromisoformat(row[13]) if row[13] else None
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    def get_all_users(self, include_inactive: bool = False) -> List[UserProfile]:
        """Get all users"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = '''
                SELECT u.id, u.username, u.email, u.role, u.department, 
                       up.first_name, up.last_name, up.phone,
                       u.created_at, u.last_login, u.is_active, u.mfa_enabled,
                       u.failed_attempts, u.locked_until
                FROM users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
            '''
            
            if not include_inactive:
                query += ' WHERE u.is_active = 1'
            
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            users = []
            for row in rows:
                users.append(UserProfile(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    role=row[3],
                    department=row[4],
                    first_name=row[5],
                    last_name=row[6],
                    phone=row[7],
                    created_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    last_login=datetime.fromisoformat(row[9]) if row[9] else None,
                    is_active=bool(row[10]),
                    mfa_enabled=bool(row[11]),
                    failed_attempts=row[12],
                    locked_until=datetime.fromisoformat(row[13]) if row[13] else None
                ))
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to get all users: {e}")
            return []
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Update main user table
            user_fields = ['username', 'email', 'role', 'department', 'is_active']
            user_updates = []
            user_values = []
            
            for field in user_fields:
                if field in kwargs:
                    user_updates.append(f"{field} = ?")
                    user_values.append(kwargs[field])
            
            if user_updates:
                user_values.append(user_id)
                cursor.execute(f'''
                    UPDATE users SET {', '.join(user_updates)} WHERE id = ?
                ''', user_values)
            
            # Update user profile
            profile_fields = ['first_name', 'last_name', 'phone', 'address', 
                            'emergency_contact', 'badge_number', 'hire_date']
            profile_updates = []
            profile_values = []
            
            for field in profile_fields:
                if field in kwargs:
                    profile_updates.append(f"{field} = ?")
                    profile_values.append(kwargs[field])
            
            if profile_updates:
                profile_values.append(user_id)
                cursor.execute(f'''
                    UPDATE user_profiles SET {', '.join(profile_updates)}, 
                    last_updated = CURRENT_TIMESTAMP WHERE user_id = ?
                ''', profile_values)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ User {user_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user (soft delete)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Soft delete - set is_active to 0
            cursor.execute('''
                UPDATE users SET is_active = 0 WHERE id = ?
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ User {user_id} deactivated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """Change user password"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Verify old password
            cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result or not check_password_hash(result[0], old_password):
                logger.warning(f"Invalid old password for user {user_id}")
                return False
            
            # Check password history
            cursor.execute('''
                SELECT password_hash FROM password_history 
                WHERE user_id = ? ORDER BY created_at DESC LIMIT 5
            ''', (user_id,))
            
            history = cursor.fetchall()
            new_hash = generate_password_hash(new_password)
            
            for old_hash in history:
                if check_password_hash(old_hash[0], new_password):
                    logger.warning(f"Password reuse detected for user {user_id}")
                    return False
            
            # Update password
            cursor.execute('''
                UPDATE users SET password_hash = ? WHERE id = ?
            ''', (new_hash, user_id))
            
            # Store in history
            cursor.execute('''
                INSERT INTO password_history (user_id, password_hash)
                VALUES (?, ?)
            ''', (user_id, new_hash))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Password changed for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to change password for user {user_id}: {e}")
            return False
    
    def get_user_activity(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get user activity history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT activity_type, activity_details, ip_address, timestamp
                FROM user_activity
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            activities = []
            for row in rows:
                activities.append({
                    'type': row[0],
                    'details': row[1],
                    'ip_address': row[2],
                    'timestamp': row[3]
                })
            
            return activities
            
        except Exception as e:
            logger.error(f"Failed to get user activity for {user_id}: {e}")
            return []
    
    def log_user_activity(self, user_id: int, activity_type: str, 
                         details: str = None, ip_address: str = None,
                         user_agent: str = None):
        """Log user activity"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_activity (user_id, activity_type, activity_details, 
                                         ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, activity_type, details, ip_address, user_agent))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log activity for user {user_id}: {e}")
    
    def get_users_by_department(self, department: str) -> List[UserProfile]:
        """Get users by department"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.role, u.department, 
                       up.first_name, up.last_name, up.phone,
                       u.created_at, u.last_login, u.is_active, u.mfa_enabled,
                       u.failed_attempts, u.locked_until
                FROM users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
                WHERE u.department = ? AND u.is_active = 1
            ''', (department,))
            
            rows = cursor.fetchall()
            conn.close()
            
            users = []
            for row in rows:
                users.append(UserProfile(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    role=row[3],
                    department=row[4],
                    first_name=row[5],
                    last_name=row[6],
                    phone=row[7],
                    created_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    last_login=datetime.fromisoformat(row[9]) if row[9] else None,
                    is_active=bool(row[10]),
                    mfa_enabled=bool(row[11]),
                    failed_attempts=row[12],
                    locked_until=datetime.fromisoformat(row[13]) if row[13] else None
                ))
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to get users by department {department}: {e}")
            return []
    
    def get_user_statistics(self) -> Dict:
        """Get user statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total users
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # Active users
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
            active_users = cursor.fetchone()[0]
            
            # Users by role
            cursor.execute('''
                SELECT role, COUNT(*) FROM users WHERE is_active = 1 GROUP BY role
            ''')
            roles = dict(cursor.fetchall())
            
            # Users by department
            cursor.execute('''
                SELECT department, COUNT(*) FROM users 
                WHERE is_active = 1 AND department IS NOT NULL 
                GROUP BY department
            ''')
            departments = dict(cursor.fetchall())
            
            # Recently active users (last 30 days)
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE last_login > ? AND is_active = 1
            ''', ((datetime.now() - timedelta(days=30)).isoformat(),))
            recent_active = cursor.fetchone()[0]
            
            # MFA enabled users
            cursor.execute('''
                SELECT COUNT(*) FROM users WHERE mfa_enabled = 1 AND is_active = 1
            ''')
            mfa_enabled = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'roles': roles,
                'departments': departments,
                'recent_active': recent_active,
                'mfa_enabled': mfa_enabled,
                'mfa_adoption_rate': round((mfa_enabled / active_users) * 100, 2) if active_users > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get user statistics: {e}")
            return {}
    
    def export_users_to_csv(self, filename: str) -> bool:
        """Export users to CSV file"""
        try:
            users = self.get_all_users(include_inactive=True)
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'username', 'email', 'role', 'department', 
                            'first_name', 'last_name', 'phone', 'created_at', 
                            'last_login', 'is_active', 'mfa_enabled']
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for user in users:
                    writer.writerow({
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': user.role,
                        'department': user.department,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'phone': user.phone,
                        'created_at': user.created_at.isoformat() if user.created_at else '',
                        'last_login': user.last_login.isoformat() if user.last_login else '',
                        'is_active': user.is_active,
                        'mfa_enabled': user.mfa_enabled
                    })
            
            logger.info(f"✅ Users exported to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export users: {e}")
            return False

def main():
    """Main function for testing"""
    user_manager = EnterpriseUserManager()
    
    # Test user creation
    user_id = user_manager.create_user(
        username="test_user",
        email="test@example.com",
        password="TestPassword123!",
        role="operator",
        department="Safety",
        first_name="Test",
        last_name="User",
        phone="+1234567890"
    )
    
    if user_id:
        print(f"Created user with ID: {user_id}")
        
        # Test user retrieval
        user = user_manager.get_user_by_id(user_id)
        if user:
            print(f"Retrieved user: {user.username}")
        
        # Test statistics
        stats = user_manager.get_user_statistics()
        print(f"User statistics: {stats}")

if __name__ == "__main__":
    main() 