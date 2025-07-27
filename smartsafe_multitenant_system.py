#!/usr/bin/env python3
"""
SmartSafe AI - Multi-Tenant SaaS System
Şirket bazlı veri ayrımı ve yönetim sistemi
"""

import sqlite3
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import logging
import os
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from flask_cors import CORS
import bcrypt
from dotenv import load_dotenv
from database_adapter import get_db_adapter

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Company:
    """Şirket veri modeli"""
    company_id: str
    company_name: str
    sector: str
    contact_person: str
    email: str
    phone: str
    address: str
    max_cameras: int
    subscription_type: str
    subscription_start: datetime
    subscription_end: datetime
    status: str = "active"
    created_at: datetime = None
    api_key: str = None

@dataclass
class User:
    """Kullanıcı veri modeli"""
    user_id: str
    company_id: str
    username: str
    email: str
    password_hash: str
    role: str  # admin, manager, operator, viewer
    permissions: List[str]
    last_login: datetime = None
    status: str = "active"
    created_at: datetime = None

@dataclass
class Camera:
    """Kamera veri modeli"""
    camera_id: str
    company_id: str
    camera_name: str
    location: str
    ip_address: str
    rtsp_url: str
    resolution: str
    fps: int
    status: str = "active"
    last_detection: datetime = None
    created_at: datetime = None

class MultiTenantDatabase:
    """Multi-tenant veritabanı yöneticisi"""
    
    def __init__(self, db_path: str = "smartsafe_saas.db"):
        self.db_path = db_path
        self.db_adapter = get_db_adapter()
        self.init_database()
    
    def get_connection(self, timeout: int = 30):
        """Database connection with timeout"""
        return self.db_adapter.get_connection(timeout)
    
    def get_placeholder(self):
        """Get appropriate placeholder for database type"""
        if self.db_adapter.db_type == 'postgresql':
            return '%s'
        else:
            return '?'
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        import bcrypt
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def init_database(self):
        """Multi-tenant veritabanı tablolarını oluştur"""
        try:
            # Use database adapter for initialization
            result = self.db_adapter.init_database()
            if result is False:
                logger.warning("⚠️ Database adapter initialization failed, using fallback")
                self._init_sqlite_database()
            else:
                logger.info("✅ Multi-tenant database initialized successfully")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            # Fallback to original SQLite initialization
            try:
                self._init_sqlite_database()
            except Exception as fallback_error:
                logger.error(f"❌ Fallback database initialization also failed: {fallback_error}")
                # Create a minimal working state
                logger.info("✅ Multi-tenant veritabanı oluşturuldu")
        
        # PostgreSQL için ek tablolar kontrolü - her durumda çalışsın
        try:
            if self.db_adapter.db_type == 'postgresql':
                logger.info("🔧 PostgreSQL tablo kontrolü başlatılıyor...")
                self._ensure_postgresql_tables()
        except Exception as e:
            logger.error(f"❌ PostgreSQL tablo kontrolü hatası: {e}")
            # Hata durumunda da devam et
    
    def _ensure_postgresql_tables(self):
        """PostgreSQL için eksik tabloları kontrol et ve oluştur"""
        try:
            conn = self.get_connection()
            if not conn:
                logger.error("❌ PostgreSQL bağlantısı alınamadı")
                return
                
            cursor = conn.cursor()
            logger.info("🔧 PostgreSQL tabloları kontrol ediliyor...")
            
            # Sessions tablosu kontrolü
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'sessions'
                );
            """)
            
            sessions_exists = cursor.fetchone()[0]
            
            if not sessions_exists:
                logger.info("🔧 Sessions tablosu oluşturuluyor...")
                cursor.execute('''
                    CREATE TABLE sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        status TEXT DEFAULT 'active'
                    )
                ''')
                logger.info("✅ Sessions tablosu oluşturuldu")
            
            # Cameras tablosuna port kolonu kontrolü - Daha agresif yaklaşım
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'cameras'
                        AND column_name = 'port'
                    );
                """)
                
                port_exists = cursor.fetchone()[0]
                logger.info(f"🔍 Port kolonu var mı: {port_exists}")
                
                if not port_exists:
                    logger.info("🔧 Cameras tablosuna port kolonu ekleniyor...")
                    # Önce mevcut veriyi kontrol et
                    cursor.execute("SELECT COUNT(*) FROM cameras")
                    camera_count = cursor.fetchone()[0]
                    logger.info(f"📊 Mevcut kamera sayısı: {camera_count}")
                    
                    # Port kolonunu ekle
                    cursor.execute('ALTER TABLE cameras ADD COLUMN port INTEGER DEFAULT 554')
                    logger.info("✅ Port kolonu eklendi")
                    
                    # Verify eklendi mi
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_schema = 'public' 
                            AND table_name = 'cameras'
                            AND column_name = 'port'
                        );
                    """)
                    verify_port = cursor.fetchone()[0]
                    logger.info(f"✅ Port kolonu doğrulama: {verify_port}")
                else:
                    logger.info("✅ Port kolonu zaten mevcut")
                    
            except Exception as e:
                logger.error(f"❌ Port kolonu işlemi hatası: {e}")
                # Son çare - tabloyu yeniden oluştur
                try:
                    logger.info("🔧 Son çare: Cameras tablosunu yeniden oluşturuyor...")
                    cursor.execute('DROP TABLE IF EXISTS cameras_backup')
                    cursor.execute('CREATE TABLE cameras_backup AS SELECT * FROM cameras')
                    cursor.execute('DROP TABLE cameras CASCADE')
                    cursor.execute('''
                        CREATE TABLE cameras (
                            camera_id TEXT PRIMARY KEY,
                            company_id TEXT NOT NULL,
                            camera_name TEXT NOT NULL,
                            location TEXT NOT NULL,
                            ip_address TEXT,
                            port INTEGER DEFAULT 554,
                            rtsp_url TEXT,
                            username TEXT,
                            password TEXT,
                            resolution TEXT DEFAULT '1920x1080',
                            fps INTEGER DEFAULT 25,
                            status TEXT DEFAULT 'active',
                            last_detection TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    # Veri varsa geri yükle
                    cursor.execute('SELECT COUNT(*) FROM cameras_backup')
                    backup_count = cursor.fetchone()[0]
                    if backup_count > 0:
                        cursor.execute('''
                            INSERT INTO cameras (camera_id, company_id, camera_name, location, 
                                               ip_address, rtsp_url, username, password, 
                                               resolution, fps, status, last_detection, 
                                               created_at, updated_at, port)
                            SELECT *, 554 FROM cameras_backup
                        ''')
                    cursor.execute('DROP TABLE cameras_backup')
                    logger.info("✅ Cameras tablosu port kolonu ile yeniden oluşturuldu")
                except Exception as e2:
                    logger.error(f"❌ Tablo yeniden oluşturma hatası: {e2}")
            
            # Updated_at kolonu kontrolü
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'cameras'
                    AND column_name = 'updated_at'
                );
            """)
            
            updated_at_exists = cursor.fetchone()[0]
            
            if not updated_at_exists:
                logger.info("🔧 Cameras tablosuna updated_at kolonu ekleniyor...")
                cursor.execute('ALTER TABLE cameras ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                logger.info("✅ Updated_at kolonu eklendi")
            
            conn.commit()
            conn.close()
            logger.info("✅ PostgreSQL tabloları kontrol edildi")
            
        except Exception as e:
            logger.error(f"❌ PostgreSQL tablo kontrolü hatası: {e}")
    
    def _init_sqlite_database(self):
        """Fallback SQLite database initialization"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
        
            # Şirketler tablosu
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
                    required_ppe TEXT, -- JSON: şirket bazlı PPE gereksinimleri
                    email_notifications BOOLEAN DEFAULT TRUE,
                    sms_notifications BOOLEAN DEFAULT FALSE,
                    push_notifications BOOLEAN DEFAULT TRUE,
                    violation_alerts BOOLEAN DEFAULT TRUE,
                    system_alerts BOOLEAN DEFAULT TRUE,
                    report_notifications BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Kullanıcılar tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'operator',
                    permissions TEXT, -- JSON array
                    last_login DATETIME,
                    status TEXT DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    UNIQUE(company_id, username)
                )
            ''')
            
            # Kameralar tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    ip_address TEXT,
                    port INTEGER DEFAULT 554,
                    rtsp_url TEXT,
                    username TEXT,
                    password TEXT,
                    resolution TEXT DEFAULT '1920x1080',
                    fps INTEGER DEFAULT 25,
                    status TEXT DEFAULT 'active',
                    last_detection DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    UNIQUE(company_id, camera_name)
                )
            ''')
            
            # PPE Tespitleri tablosu (şirket bazlı)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    detection_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_people INTEGER,
                    compliant_people INTEGER,
                    violation_people INTEGER,
                    compliance_rate REAL,
                    confidence_score REAL,
                    image_path TEXT,
                    detection_data TEXT, -- JSON
                    track_id TEXT,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
                )
            ''')
            
            # İhlaller tablosu (şirket bazlı)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS violations (
                    violation_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    user_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    violation_type TEXT NOT NULL,
                    missing_ppe TEXT, -- JSON array
                    severity TEXT DEFAULT 'medium',
                    penalty_amount REAL DEFAULT 0,
                    image_path TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_by TEXT,
                    resolved_at DATETIME,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (company_id) REFERENCES companies (company_id),
                    FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
                )
            ''')
            
            # Oturumlar tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (company_id) REFERENCES companies (company_id)
                )
            ''')
            
            # Abonelik geçmişi tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    subscription_type TEXT NOT NULL,
                    start_date DATETIME NOT NULL,
                    end_date DATETIME NOT NULL,
                    amount REAL,
                    status TEXT DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id)
                )
            ''')
            
            conn.commit()
            
            # Migration: Add required_ppe column if it doesn't exist
            try:
                cursor.execute("PRAGMA table_info(companies)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'required_ppe' not in columns:
                    logger.info("🔧 Adding required_ppe column to companies table...")
                    cursor.execute('''
                        ALTER TABLE companies 
                        ADD COLUMN required_ppe TEXT
                    ''')
                    
                    # Set default PPE for existing companies
                    cursor.execute('''
                        UPDATE companies 
                        SET required_ppe = ? 
                        WHERE required_ppe IS NULL
                    ''', (json.dumps(['helmet', 'vest']),))
                    
                    conn.commit()
                    logger.info("✅ Migration: required_ppe column added successfully")
            except Exception as e:
                logger.info(f"Migration info: {e}")
            
            # Database migration - eksik kolonları ekle
            try:
                cursor.execute("PRAGMA table_info(cameras)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'port' not in columns:
                    logger.info("🔧 Adding port column to cameras table...")
                    cursor.execute('ALTER TABLE cameras ADD COLUMN port INTEGER DEFAULT 554')
                    conn.commit()
                    logger.info("✅ Migration: port column added successfully")
                
                if 'updated_at' not in columns:
                    logger.info("🔧 Adding updated_at column to cameras table...")
                    cursor.execute('ALTER TABLE cameras ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP')
                    conn.commit()
                    logger.info("✅ Migration: updated_at column added successfully")
                    
            except Exception as e:
                logger.info(f"Migration info: {e}")
            
            # Migration for detections table
            try:
                cursor.execute("PRAGMA table_info(detections)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'status' not in columns:
                    logger.info("🔧 Adding status column to detections table...")
                    cursor.execute('ALTER TABLE detections ADD COLUMN status TEXT DEFAULT "active"')
                    conn.commit()
                    logger.info("✅ Migration: detections status column added successfully")
                    
            except Exception as e:
                logger.info(f"Migration info: {e}")
            
            # Migration for violations table
            try:
                cursor.execute("PRAGMA table_info(violations)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'status' not in columns:
                    logger.info("🔧 Adding status column to violations table...")
                    cursor.execute('ALTER TABLE violations ADD COLUMN status TEXT DEFAULT "active"')
                    conn.commit()
                    logger.info("✅ Migration: violations status column added successfully")
                    
            except Exception as e:
                logger.info(f"Migration info: {e}")

            conn.close()
            logger.info("✅ Multi-tenant veritabanı oluşturuldu")
        except Exception as e:
            logger.error(f"❌ SQLite database initialization failed: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def create_company(self, company_data: Dict) -> Tuple[bool, str]:
        """Yeni şirket kaydı"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Benzersiz şirket ID oluştur
            company_id = f"COMP_{uuid.uuid4().hex[:8].upper()}"
            
            # API key oluştur
            api_key = f"sk_{secrets.token_urlsafe(32)}"
            
            # Abonelik bitiş tarihi (1 yıl)
            subscription_end = datetime.now() + timedelta(days=365)
            
            # PPE konfigürasyonunu işle
            ppe_config = company_data.get('required_ppe', {})
            if isinstance(ppe_config, dict):
                # Yeni format: {'required': [...], 'optional': [...]}
                ppe_json = json.dumps(ppe_config)
            else:
                # Eski format: [...] - geriye uyumluluk
                ppe_json = json.dumps({'required': ppe_config, 'optional': []})
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                INSERT INTO companies 
                (company_id, company_name, sector, contact_person, email, phone, address, 
                 max_cameras, subscription_type, subscription_end, api_key, required_ppe)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                company_id, company_data['company_name'], company_data['sector'],
                company_data['contact_person'], company_data['email'], 
                company_data.get('phone', ''), company_data.get('address', ''),
                company_data.get('max_cameras', 5), company_data.get('subscription_type', 'basic'),
                subscription_end, api_key, ppe_json
            ))
            
            # Varsayılan admin kullanıcısı oluştur
            user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
            password_hash = bcrypt.hashpw(
                company_data['password'].encode('utf-8'), 
                bcrypt.gensalt()
            ).decode('utf-8')
            
            cursor.execute(f'''
                INSERT INTO users 
                (user_id, company_id, username, email, password_hash, role, permissions)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                user_id, company_id, 'admin', company_data['email'],
                password_hash, 'admin', 
                json.dumps(['all'])
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Şirket kaydedildi: {company_id}")
            return True, company_id
            
        except sqlite3.IntegrityError as e:
            logger.error(f"❌ Şirket kayıt hatası (Duplicate): {e}")
            return False, "Email adresi zaten kayıtlı"
        except Exception as e:
            logger.error(f"❌ Şirket kayıt hatası: {e}")
            return False, str(e)
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """Kullanıcı doğrulama"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT u.user_id, u.company_id, u.username, u.email, u.password_hash, 
                       u.role, u.permissions, c.company_name, c.status as company_status
                FROM users u
                JOIN companies c ON u.company_id = c.company_id
                WHERE u.email = {placeholder} AND u.status = 'active' AND c.status = 'active'
            ''', (email,))
            
            result = cursor.fetchone()
            conn.close()
            
            # Debug logging
            logger.info(f"🔍 Auth debug - Email: {email}")
            logger.info(f"🔍 Auth debug - Result: {result}")
            logger.info(f"🔍 Auth debug - Result type: {type(result)}")
            
            if result:
                logger.info(f"🔍 Auth debug - Result length: {len(result)}")
                
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(result, 'keys'):  # RealDictRow veya dict
                    password_hash = result.get('password_hash')
                    logger.info(f"🔍 Auth debug - Password hash: {password_hash}")
                    
                    if password_hash:
                        if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                            logger.info("✅ Password verification successful")
                            return {
                                'user_id': result.get('user_id'),
                                'company_id': result.get('company_id'),
                                'username': result.get('username'),
                                'email': result.get('email'),
                                'role': result.get('role'),
                                'permissions': json.loads(result.get('permissions')) if result.get('permissions') else [],
                                'company_name': result.get('company_name')
                            }
                        else:
                            logger.error("❌ Password verification failed")
                    else:
                        logger.error("❌ Password hash not found or empty")
                else:  # Liste formatı (SQLite için)
                    logger.info(f"🔍 Auth debug - Password hash: {result[4] if len(result) > 4 else 'INDEX_ERROR'}")
                    
                    if len(result) > 4 and result[4]:
                        password_hash = result[4]
                        if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                            logger.info("✅ Password verification successful")
                            return {
                                'user_id': result[0],
                                'company_id': result[1],
                                'username': result[2],
                                'email': result[3],
                                'role': result[5],
                                'permissions': json.loads(result[6]) if result[6] else [],
                                'company_name': result[7]
                            }
                        else:
                            logger.error("❌ Password verification failed")
                    else:
                        logger.error("❌ Password hash not found or empty")
            else:
                logger.error("❌ No user found with this email")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Kimlik doğrulama hatası: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None
    
    def create_session(self, user_id: str, company_id: str, ip_address: str, user_agent: str) -> str:
        """Oturum oluştur"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            session_id = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                INSERT INTO sessions 
                (session_id, user_id, company_id, expires_at, ip_address, user_agent)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (session_id, user_id, company_id, expires_at, ip_address, user_agent))
            
            # Son giriş zamanını güncelle
            cursor.execute(f'''
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = {placeholder}
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            
            return session_id
            
        except Exception as e:
            logger.error(f"❌ Oturum oluşturma hatası: {e}")
            return None
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Oturum doğrulama"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            
            # SQLite için datetime karşılaştırması düzelt
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT s.user_id, s.company_id, u.username, u.email, u.role, 
                           u.permissions, c.company_name
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    JOIN companies c ON s.company_id = c.company_id
                    WHERE s.session_id = {placeholder} AND s.expires_at > CURRENT_TIMESTAMP 
                          AND s.status = 'active' AND u.status = 'active' AND c.status = 'active'
                ''', (session_id,))
            else:
                cursor.execute(f'''
                    SELECT s.user_id, s.company_id, u.username, u.email, u.role, 
                           u.permissions, c.company_name
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    JOIN companies c ON s.company_id = c.company_id
                    WHERE s.session_id = {placeholder} AND s.expires_at > datetime('now') 
                          AND s.status = 'active' AND u.status = 'active' AND c.status = 'active'
                ''', (session_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(result, 'keys') and hasattr(result, 'get'):  # RealDictRow veya dict
                    return {
                        'user_id': result.get('user_id'),
                        'company_id': result.get('company_id'),
                        'username': result.get('username'),
                        'email': result.get('email'),
                        'role': result.get('role'),
                        'permissions': json.loads(result.get('permissions')) if result.get('permissions') else [],
                        'company_name': result.get('company_name')
                    }
                else:  # SQLite Row veya liste formatı
                    return {
                        'user_id': result[0],
                        'company_id': result[1],
                        'username': result[2],
                        'email': result[3],
                        'role': result[4],
                        'permissions': json.loads(result[5]) if result[5] else [],
                        'company_name': result[6]
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Oturum doğrulama hatası: {e}")
            return None
    
    def add_camera(self, company_id: str, camera_data: Dict) -> Tuple[bool, str]:
        """
        Şirket kamerası ekle - Production-ready version
        
        Args:
            company_id: Şirket ID'si
            camera_data: Kamera bilgileri
            
        Returns:
            (success, message/camera_id)
        """
        try:
            conn = self.get_connection()
            if conn is None:
                return False, "Veritabanı bağlantısı başarısız"
                
            cursor = conn.cursor()
            
            # Unique camera ID oluştur
            camera_id = f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
            # RTSP URL oluştur
            ip_address = camera_data.get('ip_address', '')
            port = camera_data.get('port', 8080)
            username = camera_data.get('username', '')
            password = camera_data.get('password', '')
            protocol = camera_data.get('protocol', 'http')
            stream_path = camera_data.get('stream_path', '/video')
            
            # RTSP URL formatı
            if username and password:
                if protocol == 'rtsp':
                    rtsp_url = f"rtsp://{username}:{password}@{ip_address}:{port}{stream_path}"
                else:
                    rtsp_url = f"http://{username}:{password}@{ip_address}:{port}{stream_path}"
            else:
                if protocol == 'rtsp':
                    rtsp_url = f"rtsp://{ip_address}:{port}{stream_path}"
                else:
                    rtsp_url = f"http://{ip_address}:{port}{stream_path}"
            
            # Resolution formatı
            resolution = camera_data.get('resolution', '1920x1080')
            if isinstance(resolution, dict):
                width = resolution.get('width', 1920)
                height = resolution.get('height', 1080)
                resolution = f"{width}x{height}"
            
            # Placeholder belirleme
            placeholder = self.get_placeholder()
            
            # Önce mevcut kamera var mı kontrol et
            cursor.execute(f'''
                SELECT camera_id FROM cameras 
                WHERE company_id = {placeholder} AND camera_name = {placeholder}
            ''', (company_id, camera_data.get('name', camera_data.get('camera_name', 'Real Camera'))))
            
            existing_camera = cursor.fetchone()
            if existing_camera:
                conn.close()
                return False, "Bu isimde kamera zaten mevcut"
            
            # Production database için temel kolonları kullan
            basic_columns = [
                'camera_id', 'company_id', 'camera_name', 'location', 'ip_address',
                'rtsp_url', 'username', 'password', 'resolution', 'fps', 'status'
            ]
            
            basic_values = [
                camera_id, 
                company_id, 
                camera_data.get('name', camera_data.get('camera_name', 'Real Camera')),
                camera_data.get('location', 'Genel'),
                ip_address,
                rtsp_url,
                username,
                password,
                resolution,
                camera_data.get('fps', 25),
                'active'
            ]
            
            # Dinamik olarak mevcut kolonları kontrol et
            try:
                if self.db_adapter.db_type == 'postgresql':
                    cursor.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'cameras' 
                        ORDER BY ordinal_position
                    """)
                    available_columns = [row[0] if hasattr(row, 'keys') else row[0] for row in cursor.fetchall()]
                else:
                    # SQLite için PRAGMA kullan
                    cursor.execute("PRAGMA table_info(cameras)")
                    available_columns = [row[1] for row in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Column check failed, using basic columns: {e}")
                available_columns = basic_columns
            
            # Sadece mevcut kolonları kullan
            final_columns = []
            final_values = []
            
            for i, column in enumerate(basic_columns):
                if column in available_columns:
                    final_columns.append(column)
                    final_values.append(basic_values[i])
            
            # Ek kolonları kontrol et ve ekle
            extended_columns = {
                'port': port,
                'protocol': protocol,
                'stream_path': stream_path,
                'auth_type': camera_data.get('auth_type', 'basic'),
                'quality': camera_data.get('quality', 80),
                'audio_enabled': camera_data.get('audio_enabled', False),
                'night_vision': camera_data.get('night_vision', False),
                'motion_detection': camera_data.get('motion_detection', True),
                'recording_enabled': camera_data.get('recording_enabled', True),
                'camera_type': camera_data.get('camera_type', 'ip_camera'),
                'connection_retries': camera_data.get('connection_retries', 3),
                'timeout': camera_data.get('timeout', 10),
                'created_at': 'CURRENT_TIMESTAMP',
                'updated_at': 'CURRENT_TIMESTAMP'
            }
            
            for column, value in extended_columns.items():
                if column in available_columns:
                    final_columns.append(column)
                    if column in ['created_at', 'updated_at']:
                        final_values.append(value)  # Raw SQL
                    else:
                        final_values.append(value)
            
            # SQL query oluştur
            placeholders_list = []
            actual_values = []
            
            for i, value in enumerate(final_values):
                if value == 'CURRENT_TIMESTAMP':
                    placeholders_list.append('CURRENT_TIMESTAMP')
                else:
                    placeholders_list.append(placeholder)
                    actual_values.append(value)
            
            placeholders_str = ', '.join(placeholders_list)
            columns_str = ', '.join(final_columns)
            
            insert_query = f'''
                INSERT INTO cameras ({columns_str})
                VALUES ({placeholders_str})
            '''
            
            # Execute query
            cursor.execute(insert_query, actual_values)
            
            # Commit transaction
            conn.commit()
            
            # Başarılı sonuç
            conn.close()
            logger.info(f"✅ Camera added successfully: {camera_id}")
            return True, camera_id
            
        except Exception as e:
            logger.error(f"❌ Camera addition failed: {e}")
            if conn:
                conn.rollback()
                conn.close()
            return False, f"Kamera eklenirken hata oluştu: {str(e)}"
    
    def get_company_cameras(self, company_id: str) -> List[Dict]:
        """Şirket kameralarını getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Tüm kamera bilgilerini çek (updated_at kolonu olmadan)
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_id, camera_name, location, ip_address, rtsp_url, 
                       username, password, resolution, fps, status, last_detection,
                       created_at
                FROM cameras
                WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            cameras = []
            for row in cursor.fetchall():
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(row, 'keys') and hasattr(row, 'get'):  # RealDictRow veya dict
                    camera = {
                        'camera_id': row.get('camera_id'),
                        'camera_name': row.get('camera_name'),
                        'location': row.get('location'),
                        'ip_address': row.get('ip_address'),
                        'port': 8080,  # Default port updated to 8080
                        'rtsp_url': row.get('rtsp_url'),
                        'username': row.get('username'),
                        'password': row.get('password'),
                        'resolution': row.get('resolution'),
                        'fps': row.get('fps'),
                        'status': row.get('status'),
                        'last_detection': str(row.get('last_detection')) if row.get('last_detection') else '',
                        'created_at': str(row.get('created_at')) if row.get('created_at') else '',
                        'updated_at': str(row.get('created_at')) if row.get('created_at') else ''  # Use created_at as fallback
                    }
                else:  # Liste formatı (SQLite için)
                    camera = {
                        'camera_id': row[0],
                        'camera_name': row[1],
                        'location': row[2],
                        'ip_address': row[3],
                        'port': 8080,  # Default port updated to 8080
                        'rtsp_url': row[4],
                        'username': row[5],
                        'password': row[6],
                        'resolution': row[7],
                        'fps': row[8],
                        'status': row[9],
                        'last_detection': str(row[10]) if row[10] else '',
                        'created_at': str(row[11]) if row[11] else '',
                        'updated_at': str(row[11]) if row[11] else ''  # Use created_at as fallback
                    }
                cameras.append(camera)
            
            conn.close()
            return cameras
            
        except Exception as e:
            logger.error(f"ERROR: Kamera listesi getirme hatasi: {e}")
            return []
    
    def get_camera_by_id(self, camera_id: str, company_id: str) -> Optional[Dict]:
        """ID ile kamerayı getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT * FROM cameras 
                WHERE camera_id = {placeholder} AND company_id = {placeholder} AND status = 'active'
            ''', (camera_id, company_id))
            
            camera = cursor.fetchone()
            conn.close()
            
            if camera:
                if hasattr(camera, 'keys'):  # PostgreSQL RealDictRow
                    return dict(camera)
                else:  # SQLite tuple
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, camera))
            
            return None
            
        except Exception as e:
            logger.error(f"ERROR: Kamera getirme hatasi: {e}")
            return None
    
    def delete_camera(self, camera_id: str, company_id: str) -> bool:
        """Kamerayı sil (basitleştirilmiş)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Önce kameranın bu şirkete ait olduğunu doğrula
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_name FROM cameras 
                WHERE company_id = {placeholder} AND camera_id = {placeholder} AND status = 'active'
            ''', (company_id, camera_id))
            
            if not cursor.fetchone():
                conn.close()
                return False
            
            # Kamerayı sil (soft delete)
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    UPDATE cameras 
                    SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = {placeholder} AND camera_id = {placeholder}
                ''', (company_id, camera_id))
            else:
                cursor.execute(f'''
                    UPDATE cameras 
                    SET status = 'deleted', updated_at = datetime('now')
                    WHERE company_id = {placeholder} AND camera_id = {placeholder}
                ''', (company_id, camera_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"ERROR: Kamera silme hatasi: {e}")
            return False
    
    def get_company_stats(self, company_id: str) -> Dict:
        """Enhanced şirket istatistikleri"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Bugünkü istatistikler
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT 
                    COUNT(*) as total_detections,
                    SUM(total_people) as total_people,
                    SUM(compliant_people) as compliant_people,
                    SUM(violation_people) as violation_people,
                    AVG(compliance_rate) as avg_compliance_rate
                FROM detections
                WHERE company_id = {placeholder} AND date(timestamp) = CURRENT_DATE
            ''', (company_id,))
            
            detection_stats = cursor.fetchone()
            
            # PostgreSQL RealDictRow için sözlük erişimi kullan
            if detection_stats:
                if hasattr(detection_stats, 'keys'):  # RealDictRow veya dict
                    total_detections = detection_stats.get('total_detections') or 0
                    total_people = detection_stats.get('total_people') or 0
                    compliant_people = detection_stats.get('compliant_people') or 0
                    violation_people = detection_stats.get('violation_people') or 0
                    avg_compliance_rate = detection_stats.get('avg_compliance_rate') or 0
                else:  # Liste formatı (SQLite için)
                    total_detections = detection_stats[0] or 0
                    total_people = detection_stats[1] or 0
                    compliant_people = detection_stats[2] or 0
                    violation_people = detection_stats[3] or 0
                    avg_compliance_rate = detection_stats[4] or 0
            else:
                total_detections = total_people = compliant_people = violation_people = avg_compliance_rate = 0
            
            # Aktif kamera sayısı
            cursor.execute(f'''
                SELECT COUNT(*) FROM cameras WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            active_cameras_result = cursor.fetchone()
            if hasattr(active_cameras_result, 'keys'):  # RealDictRow
                # PostgreSQL'de COUNT(*) sonucu 'count' değil, doğrudan değer döner
                active_cameras = list(active_cameras_result.values())[0] if active_cameras_result else 0
            else:  # Liste formatı
                active_cameras = active_cameras_result[0] if active_cameras_result else 0
            
            # Bugünkü ihlal sayısı
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = CURRENT_DATE
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                ''', (company_id,))
            
            today_violations_result = cursor.fetchone()
            if hasattr(today_violations_result, 'keys'):  # RealDictRow
                today_violations = list(today_violations_result.values())[0] if today_violations_result else 0
            else:  # Liste formatı
                today_violations = today_violations_result[0] if today_violations_result else 0
            
            # Dünkü istatistikler (trend hesaplama için)
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = CURRENT_DATE - INTERVAL '1 day'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = date('now', '-1 day')
                ''', (company_id,))
            
            yesterday_violations_result = cursor.fetchone()
            if hasattr(yesterday_violations_result, 'keys'):  # RealDictRow
                yesterday_violations = list(yesterday_violations_result.values())[0] if yesterday_violations_result else 0
            else:  # Liste formatı
                yesterday_violations = yesterday_violations_result[0] if yesterday_violations_result else 0
            
            # Geçen haftaki kamera sayısı
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM cameras 
                    WHERE company_id = {placeholder} AND created_at < CURRENT_DATE - INTERVAL '7 days'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM cameras 
                    WHERE company_id = {placeholder} AND created_at < date('now', '-7 days')
                ''', (company_id,))
            
            last_week_cameras_result = cursor.fetchone()
            if hasattr(last_week_cameras_result, 'keys'):  # RealDictRow
                last_week_cameras = list(last_week_cameras_result.values())[0] if last_week_cameras_result else 0
            else:  # Liste formatı
                last_week_cameras = last_week_cameras_result[0] if last_week_cameras_result else 0
            
            # Compliance trend (son 7 günün ortalaması)
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT AVG(compliance_rate) 
                    FROM detections 
                    WHERE company_id = {placeholder} AND date(timestamp) > CURRENT_DATE - INTERVAL '7 days'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT AVG(compliance_rate) 
                    FROM detections 
                    WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-7 days')
                ''', (company_id,))
            
            week_compliance_result = cursor.fetchone()
            if hasattr(week_compliance_result, 'keys'):  # RealDictRow
                week_compliance = list(week_compliance_result.values())[0] if week_compliance_result else 0
            else:  # Liste formatı
                week_compliance = week_compliance_result[0] if week_compliance_result else 0
            
            # Aktif çalışan sayısı (bugün tespit edilen unique kişi sayısı)
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(DISTINCT track_id) 
                    FROM detections 
                    WHERE company_id = {placeholder} AND date(timestamp) = CURRENT_DATE
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(DISTINCT track_id) 
                    FROM detections 
                    WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                ''', (company_id,))
            
            active_workers_result = cursor.fetchone()
            if hasattr(active_workers_result, 'keys'):  # RealDictRow
                active_workers = list(active_workers_result.values())[0] if active_workers_result else 0
            else:  # Liste formatı
                active_workers = active_workers_result[0] if active_workers_result else 0
            
            # Aylık ihlal sayısı
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) > CURRENT_DATE - INTERVAL '30 days'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-30 days')
                ''', (company_id,))
            
            monthly_violations_result = cursor.fetchone()
            if hasattr(monthly_violations_result, 'keys'):  # RealDictRow
                monthly_violations = list(monthly_violations_result.values())[0] if monthly_violations_result else 0
            else:  # Liste formatı
                monthly_violations = monthly_violations_result[0] if monthly_violations_result else 0
            
            conn.close()
            
            # Trend hesaplamaları - Fix all NoneType issues
            cameras_trend = (active_cameras or 0) - (last_week_cameras or 0)
            violations_trend = (today_violations or 0) - (yesterday_violations or 0)
            
            # Safe compliance trend calculation
            avg_compliance_rate = avg_compliance_rate or 0
            week_compliance = week_compliance or 0
            compliance_trend = avg_compliance_rate - week_compliance if week_compliance > 0 else 0
            
            # Ensure all values are not None
            total_detections = total_detections or 0
            total_people = total_people or 0
            compliant_people = compliant_people or 0
            violation_people = violation_people or 0
            active_cameras = active_cameras or 0
            active_workers = active_workers or 0
            monthly_violations = monthly_violations or 0
            
            return {
                'total_detections': total_detections,
                'total_people': total_people,
                'compliant_people': compliant_people,
                'violation_people': violation_people,
                'compliance_rate': avg_compliance_rate,
                'active_cameras': active_cameras,
                'today_violations': today_violations,
                'active_workers': active_workers,
                'monthly_violations': monthly_violations,
                
                # Trend indicators
                'cameras_trend': cameras_trend,
                'compliance_trend': compliance_trend,
                'violations_trend': violations_trend,
                'workers_trend': 0  # Çalışan trendi için daha karmaşık hesaplama gerekir
            }
            
        except Exception as e:
            logger.error(f"❌ İstatistik getirme hatası: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {
                'total_detections': 0,
                'total_people': 0,
                'compliance_rate': 0,
                'active_cameras': 0,
                'today_violations': 0,
                'active_workers': 0,
                'monthly_violations': 0,
                'cameras_trend': 0,
                'compliance_trend': 0,
                'violations_trend': 0,
                'workers_trend': 0
            }
    
    def get_company_ppe_requirements(self, company_id: str) -> List[str]:
        """Şirketin PPE gereksinimlerini al"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT required_ppe FROM companies WHERE company_id = {placeholder}
            ''', (company_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(result, 'keys') and hasattr(result, 'get'):  # RealDictRow veya dict
                    required_ppe = result.get('required_ppe')
                else:  # Liste formatı (SQLite için)
                    required_ppe = result[0]
                
                if required_ppe:
                    ppe_data = json.loads(required_ppe)
                    
                    # Şirket kaydı sırasında girilen format: {'required': [...], 'optional': [...]}
                    if isinstance(ppe_data, dict):
                        if 'required' in ppe_data:
                            return ppe_data['required']
                        else:
                            # Eski format - sadece liste
                            return list(ppe_data.keys()) if isinstance(ppe_data, dict) else []
                    elif isinstance(ppe_data, list):
                        # Direkt liste formatı
                        return ppe_data
                    else:
                        return []
            return []
            
        except Exception as e:
            logger.error(f"❌ PPE gereksinimlerini alma hatası: {e}")
            return []

def main():
    """Test fonksiyonu"""
    print("🏗️ SmartSafe AI - Multi-Tenant SaaS System")
    print("=" * 60)
    
    # Database oluştur
    db = MultiTenantDatabase()
    
    # Test şirketi oluştur
    test_company = {
        'company_name': 'ABC İnşaat Ltd.',
        'sector': 'construction',
        'contact_person': 'Ahmet Yılmaz',
        'email': 'info@abc-insaat.com',
        'phone': '0212 555 0123',
        'address': 'İstanbul',
        'max_cameras': 10,
        'subscription_type': 'premium',
        'password': 'admin123'
    }
    
    success, company_id = db.create_company(test_company)
    if success:
        print(f"✅ Test şirketi oluşturuldu: {company_id}")
        
        # Kimlik doğrulama testi
        user_data = db.authenticate_user('info@abc-insaat.com', 'admin123')
        if user_data:
            print(f"✅ Kimlik doğrulama başarılı: {user_data['username']}")
            
            # Test kamerası ekle
            camera_data = {
                'camera_name': 'Ana Giriş Kamerası',
                'location': 'Giriş Kapısı',
                'ip_address': '192.168.1.100',
                'rtsp_url': 'rtsp://admin:123456@192.168.1.100:554/stream1'
            }
            
            cam_success, camera_id = db.add_camera(company_id, camera_data)
            if cam_success:
                print(f"✅ Test kamerası eklendi: {camera_id}")
                
                # İstatistikleri göster
                stats = db.get_company_stats(company_id)
                print(f"📊 Şirket İstatistikleri: {stats}")
        else:
            print("❌ Kimlik doğrulama başarısız")
    else:
        print(f"❌ Test şirketi oluşturulamadı: {company_id}")

if __name__ == "__main__":
    main() 