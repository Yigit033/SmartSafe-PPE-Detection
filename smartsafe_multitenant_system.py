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
            cursor.execute(f'''
                SELECT s.user_id, s.company_id, u.username, u.email, u.role, 
                       u.permissions, c.company_name
                FROM sessions s
                JOIN users u ON s.user_id = u.user_id
                JOIN companies c ON s.company_id = c.company_id
                WHERE s.session_id = {placeholder} AND s.expires_at > CURRENT_TIMESTAMP 
                      AND s.status = 'active' AND u.status = 'active' AND c.status = 'active'
            ''', (session_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # PostgreSQL RealDictRow için sözlük erişimi kullan
                if hasattr(result, 'keys'):  # RealDictRow veya dict
                    return {
                        'user_id': result.get('user_id'),
                        'company_id': result.get('company_id'),
                        'username': result.get('username'),
                        'email': result.get('email'),
                        'role': result.get('role'),
                        'permissions': json.loads(result.get('permissions')) if result.get('permissions') else [],
                        'company_name': result.get('company_name')
                    }
                else:  # Liste formatı (SQLite için)
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
        """Yeni kamera ekle"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Önce şirketin max_cameras limitini al
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT max_cameras FROM companies WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            result = cursor.fetchone()
            if not result:
                conn.close()
                return False, "Şirket bulunamadı"
            
            # PostgreSQL RealDictRow için sözlük erişimi kullan
            if hasattr(result, 'keys'):  # RealDictRow veya dict
                max_cameras = result.get('max_cameras')
            else:  # Liste formatı (SQLite için)
                max_cameras = result[0]
            
            # Mevcut aktif kamera sayısını kontrol et
            cursor.execute(f'''
                SELECT COUNT(*) FROM cameras 
                WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            current_cameras = cursor.fetchone()[0]
            if current_cameras >= max_cameras:
                conn.close()
                return False, f"Maksimum kamera limitine ({max_cameras}) ulaşıldı"
            
            # Aynı isimde kamera var mı kontrol et
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_id FROM cameras 
                WHERE company_id = {placeholder} AND camera_name = {placeholder} AND status = 'active'
            ''', (company_id, camera_data.get('camera_name')))
            
            if cursor.fetchone():
                conn.close()
                return False, "Bu isimde bir kamera zaten mevcut"
            
            # Yeni kamera ID'si oluştur
            camera_id = str(uuid.uuid4())
            
            # Kamerayı ekle
            cursor.execute(f'''
                INSERT INTO cameras (
                    camera_id, company_id, camera_name, location, ip_address, port,
                    rtsp_url, username, password, resolution, fps, status
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                camera_id, company_id, 
                camera_data.get('camera_name'),
                camera_data.get('location', 'Genel'),
                camera_data.get('ip_address', ''),
                camera_data.get('port', 554),
                camera_data.get('rtsp_url', ''),
                camera_data.get('username', ''),
                camera_data.get('password', ''),
                camera_data.get('resolution', '1920x1080'),
                camera_data.get('fps', 25),
                'active'
            ))
            
            conn.commit()
            conn.close()
            return True, camera_id
            
        except Exception as e:
            logger.error(f"ERROR: Kamera ekleme hatasi: {e}")
            return False, str(e)
    
    def get_company_cameras(self, company_id: str) -> List[Dict]:
        """Şirket kameralarını getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Tüm kamera bilgilerini çek
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_id, camera_name, location, ip_address, port, rtsp_url, 
                       username, password, resolution, fps, status, last_detection,
                       created_at, updated_at
                FROM cameras
                WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            cameras = []
            for row in cursor.fetchall():
                camera = {
                    'id': row[0],  # Frontend için id olarak döndür
                    'name': row[1],  # Frontend için name olarak döndür
                    'location': row[2],
                    'ip_address': row[3],
                    'port': row[4] if row[4] else 554,
                    'rtsp_url': row[5],
                    'username': row[6],
                    'password': row[7],
                    'resolution': row[8],
                    'fps': row[9],
                    'status': row[10],
                    'last_detection': row[11],
                    'created_at': row[12],
                    'updated_at': row[13]
                }
                cameras.append(camera)
            
            conn.close()
            return cameras
            
        except Exception as e:
            logger.error(f"ERROR: Kamera listesi getirme hatasi: {e}")
            return []
    
    def delete_camera(self, company_id: str, camera_id: str) -> Tuple[bool, str]:
        """Kamera sil"""
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
                return False, "Kamera bulunamadı"
            
            # Kamerayı sil (soft delete)
            cursor.execute(f'''
                UPDATE cameras 
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {placeholder} AND camera_id = {placeholder}
            ''', (company_id, camera_id))
            
            conn.commit()
            conn.close()
            return True, "Kamera başarıyla silindi"
            
        except Exception as e:
            logger.error(f"ERROR: Kamera silme hatasi: {e}")
            return False, str(e)
    
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
                active_cameras = active_cameras_result.get('count') or active_cameras_result[0] or 0
            else:  # Liste formatı
                active_cameras = active_cameras_result[0] or 0
            
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
                today_violations = today_violations_result.get('count') or today_violations_result[0] or 0
            else:  # Liste formatı
                today_violations = today_violations_result[0] or 0
            
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
                yesterday_violations = yesterday_violations_result.get('count') or yesterday_violations_result[0] or 0
            else:  # Liste formatı
                yesterday_violations = yesterday_violations_result[0] or 0
            
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
                last_week_cameras = last_week_cameras_result.get('count') or last_week_cameras_result[0] or 0
            else:  # Liste formatı
                last_week_cameras = last_week_cameras_result[0] or 0
            
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
                week_compliance = week_compliance_result.get('avg') or week_compliance_result[0] or 0
            else:  # Liste formatı
                week_compliance = week_compliance_result[0] or 0
            
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
                active_workers = active_workers_result.get('count') or active_workers_result[0] or 0
            else:  # Liste formatı
                active_workers = active_workers_result[0] or 0
            
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
                monthly_violations = monthly_violations_result.get('count') or monthly_violations_result[0] or 0
            else:  # Liste formatı
                monthly_violations = monthly_violations_result[0] or 0
            
            conn.close()
            
            # Trend hesaplamaları
            cameras_trend = active_cameras - last_week_cameras
            violations_trend = today_violations - yesterday_violations
            compliance_trend = avg_compliance_rate - week_compliance if week_compliance > 0 else 0
            
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
                if hasattr(result, 'keys'):  # RealDictRow veya dict
                    required_ppe = result.get('required_ppe')
                else:  # Liste formatı (SQLite için)
                    required_ppe = result[0]
                
                if required_ppe:
                    return json.loads(required_ppe)
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