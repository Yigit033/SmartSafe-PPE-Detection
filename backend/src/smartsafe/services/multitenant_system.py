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
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import json
import logging
import os
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from flask_cors import CORS
import bcrypt
from dotenv import load_dotenv
from src.smartsafe.database.database_adapter import get_db_adapter

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
                    
                # Protocol kolonu kontrolü
                try:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_schema = 'public' 
                            AND table_name = 'cameras'
                            AND column_name = 'protocol'
                        );
                    """)
                    
                    protocol_exists = cursor.fetchone()[0]
                    logger.info(f"🔍 Protocol kolonu var mı: {protocol_exists}")
                    
                    if not protocol_exists:
                        logger.info("🔧 Cameras tablosuna protocol kolonu ekleniyor...")
                        cursor.execute('ALTER TABLE cameras ADD COLUMN protocol TEXT DEFAULT \'http\'')
                        logger.info("✅ Protocol kolonu eklendi")
                    else:
                        logger.info("✅ Protocol kolonu zaten mevcut")
                        
                except Exception as e:
                    logger.error(f"❌ Protocol kolonu işlemi hatası: {e}")
                    
                # Stream_path kolonu kontrolü
                try:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_schema = 'public' 
                            AND table_name = 'cameras'
                            AND column_name = 'stream_path'
                        );
                    """)
                    
                    stream_path_exists = cursor.fetchone()[0]
                    logger.info(f"🔍 Stream_path kolonu var mı: {stream_path_exists}")
                    
                    if not stream_path_exists:
                        logger.info("🔧 Cameras tablosuna stream_path kolonu ekleniyor...")
                        cursor.execute('ALTER TABLE cameras ADD COLUMN stream_path TEXT DEFAULT \'/video\'')
                        logger.info("✅ Stream_path kolonu eklendi")
                    else:
                        logger.info("✅ Stream_path kolonu zaten mevcut")
                        
                except Exception as e:
                    logger.error(f"❌ Stream_path kolonu işlemi hatası: {e}")
                    
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
                            protocol TEXT DEFAULT 'http',
                            stream_path TEXT DEFAULT '/video',
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
            try:
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
                else:
                    logger.info("✅ Updated_at kolonu zaten mevcut")
            except Exception as e:
                logger.error(f"❌ Updated_at kolonu kontrolü hatası: {e}")
                # Son çare - tabloyu yeniden oluştur
                try:
                    logger.info("🔧 Son çare: Cameras tablosunu updated_at ile yeniden oluşturuyor...")
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
                    logger.info("✅ Cameras tablosu updated_at kolonu ile yeniden oluşturuldu")
                except Exception as e2:
                    logger.error(f"❌ Tablo yeniden oluşturma hatası: {e2}")
            
            # Detections tablosu için migration - compliance_rate, compliant_people, violation_people
            try:
                # compliance_rate kolonu kontrolü
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'detections'
                        AND column_name = 'compliance_rate'
                    );
                """)
                compliance_rate_exists = cursor.fetchone()[0]
                
                if not compliance_rate_exists:
                    logger.info("🔧 Detections tablosuna compliance_rate kolonu ekleniyor...")
                    cursor.execute('ALTER TABLE detections ADD COLUMN compliance_rate REAL')
                    conn.commit()
                    logger.info("✅ compliance_rate kolonu eklendi")
                else:
                    logger.info("✅ compliance_rate kolonu zaten mevcut")
                
                # compliant_people kolonu kontrolü
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'detections'
                        AND column_name = 'compliant_people'
                    );
                """)
                compliant_people_exists = cursor.fetchone()[0]
                
                if not compliant_people_exists:
                    logger.info("🔧 Detections tablosuna compliant_people kolonu ekleniyor...")
                    cursor.execute('ALTER TABLE detections ADD COLUMN compliant_people INTEGER DEFAULT 0')
                    conn.commit()
                    logger.info("✅ compliant_people kolonu eklendi")
                else:
                    logger.info("✅ compliant_people kolonu zaten mevcut")
                
                # violation_people kolonu kontrolü
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'detections'
                        AND column_name = 'violation_people'
                    );
                """)
                violation_people_exists = cursor.fetchone()[0]
                
                if not violation_people_exists:
                    logger.info("🔧 Detections tablosuna violation_people kolonu ekleniyor...")
                    cursor.execute('ALTER TABLE detections ADD COLUMN violation_people INTEGER DEFAULT 0')
                    conn.commit()
                    logger.info("✅ violation_people kolonu eklendi")
                else:
                    logger.info("✅ violation_people kolonu zaten mevcut")
                
                # track_id kolonu kontrolü
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'detections'
                        AND column_name = 'track_id'
                    );
                """)
                track_id_exists = cursor.fetchone()[0]
                
                if not track_id_exists:
                    logger.info("🔧 Detections tablosuna track_id kolonu ekleniyor...")
                    cursor.execute('ALTER TABLE detections ADD COLUMN track_id TEXT')
                    conn.commit()
                    logger.info("✅ track_id kolonu eklendi")
                else:
                    logger.info("✅ track_id kolonu zaten mevcut")
                
                # Mevcut veriler için compliance_rate hesapla (eğer NULL ise)
                try:
                    cursor.execute('''
                        UPDATE detections 
                        SET compliance_rate = CASE 
                            WHEN people_detected > 0 THEN (ppe_compliant::FLOAT / people_detected::FLOAT * 100.0)
                            ELSE 0 
                        END
                        WHERE compliance_rate IS NULL AND people_detected > 0
                    ''')
                    conn.commit()
                    logger.info("✅ Mevcut veriler için compliance_rate hesaplandı")
                except Exception as e:
                    logger.info(f"Migration info (compliance_rate calculation): {e}")
                
                # Mevcut veriler için compliant_people hesapla (eğer NULL ise)
                try:
                    cursor.execute('''
                        UPDATE detections 
                        SET compliant_people = ppe_compliant
                        WHERE compliant_people IS NULL AND ppe_compliant IS NOT NULL
                    ''')
                    conn.commit()
                    logger.info("✅ Mevcut veriler için compliant_people hesaplandı")
                except Exception as e:
                    logger.info(f"Migration info (compliant_people calculation): {e}")
                
                # Mevcut veriler için violation_people hesapla (eğer NULL ise)
                try:
                    cursor.execute('''
                        UPDATE detections 
                        SET violation_people = violations_count
                        WHERE violation_people IS NULL AND violations_count IS NOT NULL
                    ''')
                    conn.commit()
                    logger.info("✅ Mevcut veriler için violation_people hesaplandı")
                except Exception as e:
                    logger.info(f"Migration info (violation_people calculation): {e}")
                    
            except Exception as e:
                logger.error(f"❌ Detections tablosu migration hatası: {e}")
            
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
                    max_cameras INTEGER DEFAULT 25,
                    subscription_type TEXT DEFAULT 'starter',
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
                    protocol TEXT DEFAULT 'http',
                    stream_path TEXT DEFAULT '/video',
                    rtsp_url TEXT,
                    username TEXT,
                    password TEXT,
                    resolution TEXT DEFAULT '1920x1080',
                    fps INTEGER DEFAULT 25,
                    status TEXT DEFAULT 'active',
                    last_detection DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (company_id)
                )
            ''')
            
            # Eksik kolonları ekle (eğer yoksa)
            try:
                cursor.execute("ALTER TABLE cameras ADD COLUMN protocol TEXT DEFAULT 'http'")
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute("ALTER TABLE cameras ADD COLUMN stream_path TEXT DEFAULT '/video'")
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            # PPE Tespitleri tablosu (şirket bazlı)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    detection_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    detection_type TEXT DEFAULT 'PPE',
                    confidence REAL DEFAULT 0,
                    people_detected INTEGER DEFAULT 0,
                    ppe_compliant INTEGER DEFAULT 0,
                    violations_count INTEGER DEFAULT 0,
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
            
            # Database migration - Yeni kolonları ekle (varsa hata vermesin)
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN detection_type TEXT DEFAULT "PPE"')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN track_id TEXT')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN confidence REAL DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN people_detected INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN ppe_compliant INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN violations_count INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            try:
                cursor.execute('ALTER TABLE violations ADD COLUMN worker_id TEXT')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE violations ADD COLUMN penalty REAL DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE violations ADD COLUMN confidence REAL DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
                
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN compliant_people INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN violation_people INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            try:
                cursor.execute('ALTER TABLE detections ADD COLUMN compliance_rate REAL')
            except sqlite3.OperationalError:
                pass  # Kolon zaten var
            
            # Mevcut veriler için compliance_rate hesapla (eğer NULL ise)
            try:
                cursor.execute('''
                    UPDATE detections 
                    SET compliance_rate = CASE 
                        WHEN people_detected > 0 THEN (ppe_compliant * 100.0 / people_detected)
                        ELSE 0 
                    END
                    WHERE compliance_rate IS NULL AND people_detected > 0
                ''')
                conn.commit()
            except Exception as e:
                logger.info(f"Migration info (compliance_rate calculation): {e}")
            
            # Mevcut veriler için compliant_people hesapla (eğer NULL ise)
            try:
                cursor.execute('''
                    UPDATE detections 
                    SET compliant_people = ppe_compliant
                    WHERE compliant_people IS NULL AND ppe_compliant IS NOT NULL
                ''')
                conn.commit()
            except Exception as e:
                logger.info(f"Migration info (compliant_people calculation): {e}")
            
            # Mevcut veriler için violation_people hesapla (eğer NULL ise)
            try:
                cursor.execute('''
                    UPDATE detections 
                    SET violation_people = violations_count
                    WHERE violation_people IS NULL AND violations_count IS NOT NULL
                ''')
                conn.commit()
            except Exception as e:
                logger.info(f"Migration info (violation_people calculation): {e}")
            
            # İhlaller tablosu (şirket bazlı)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS violations (
                    violation_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    worker_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    violation_type TEXT NOT NULL,
                    missing_ppe TEXT NOT NULL,
                    penalty REAL DEFAULT 0,
                    confidence REAL DEFAULT 0,
                    user_id TEXT,
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
            
            # Migration: Add updated_at column to cameras table if it doesn't exist
            try:
                cursor.execute("PRAGMA table_info(cameras)")
                camera_columns = [column[1] for column in cursor.fetchall()]
                
                if 'updated_at' not in camera_columns:
                    logger.info("🔧 Adding updated_at column to cameras table...")
                    cursor.execute('''
                        ALTER TABLE cameras 
                        ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    ''')
                    
                    conn.commit()
                    logger.info("✅ Migration: updated_at column added to cameras table")
            except Exception as e:
                logger.info(f"Cameras migration info: {e}")
            
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
            if company_data.get('account_type') == 'demo':
                # Demo hesaplar için özel ID formatı
                company_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            else:
                # Normal hesaplar için mevcut format
                company_id = f"COMP_{uuid.uuid4().hex[:8].upper()}"
            
            # API key oluştur
            api_key = f"sk_{secrets.token_urlsafe(32)}"
            
            # Abonelik bitiş tarihi
            if company_data.get('account_type') == 'demo':
                # Demo hesaplar için 7 gün
                subscription_end = datetime.now() + timedelta(days=7)
            else:
                # Normal hesaplar için 7 gün ücretsiz + 1 yıl ücretli
                subscription_end = datetime.now() + timedelta(days=7 + 365)
            
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
                 max_cameras, subscription_type, billing_cycle, subscription_end, api_key, required_ppe,
                 account_type, demo_expires_at, demo_limits, ppe_requirements, compliance_settings)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ''', (
                company_id, company_data['company_name'], company_data['sector'],
                company_data['contact_person'], company_data['email'], 
                company_data.get('phone', ''), company_data.get('address', ''),
                company_data.get('max_cameras', 25), company_data.get('subscription_type', 'basic'),
                company_data.get('billing_cycle', 'monthly'), subscription_end, api_key, ppe_json,
                company_data.get('account_type', 'full'), company_data.get('demo_expires_at'), company_data.get('demo_limits'),
                company_data.get('ppe_requirements', '{}'), company_data.get('compliance_settings', '{}')
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
                
                # PostgreSQL ve SQLite için uyumlu kontrol
                if hasattr(result, 'keys') and hasattr(result, 'get'):  # PostgreSQL RealDictRow
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
                else:  # SQLite Row veya liste formatı
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
    
    def authenticate_demo_user(self, demo_id: str, email: str, password: str) -> Optional[Dict]:
        """Demo kullanıcı doğrulama - PostgreSQL ve SQLite uyumlu"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            
            # PostgreSQL ve SQLite için uyumlu query
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT u.user_id, u.company_id, u.username, u.email, u.password_hash, 
                           u.role, u.permissions, c.company_name, c.status as company_status,
                           c.subscription_type, c.demo_expires_at
                    FROM users u
                    JOIN companies c ON u.company_id = c.company_id
                    WHERE u.email = {placeholder} AND u.company_id = {placeholder} 
                    AND u.status = 'active' AND c.status = 'active'
                    AND c.subscription_type = 'demo'
                ''', (email, demo_id))
            else:
                cursor.execute(f'''
                    SELECT u.user_id, u.company_id, u.username, u.email, u.password_hash, 
                           u.role, u.permissions, c.company_name, c.status as company_status,
                           c.subscription_type, c.demo_expires_at
                    FROM users u
                    JOIN companies c ON u.company_id = c.company_id
                    WHERE u.email = {placeholder} AND u.company_id = {placeholder} 
                    AND u.status = 'active' AND c.status = 'active'
                    AND c.subscription_type = 'demo'
                ''', (email, demo_id))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # Demo hesap süresi kontrolü - PostgreSQL ve SQLite uyumlu
                demo_expires_at = None
                if self.db_adapter.db_type == 'postgresql':
                    demo_expires_at = result.get('demo_expires_at') if hasattr(result, 'get') else result[10] if len(result) > 10 else None
                else:
                    demo_expires_at = result[10] if len(result) > 10 else None
                
                if demo_expires_at:
                    try:
                        if isinstance(demo_expires_at, str):
                            if 'T' in demo_expires_at:
                                # ISO format with timezone
                                demo_expires_at = datetime.fromisoformat(demo_expires_at.replace('Z', '+00:00'))
                            elif '.' in demo_expires_at:
                                # SQLite format with microseconds
                                demo_expires_at = datetime.strptime(demo_expires_at, '%Y-%m-%d %H:%M:%S.%f')
                            else:
                                # Standard format
                                demo_expires_at = datetime.strptime(demo_expires_at, '%Y-%m-%d %H:%M:%S')
                        
                        if datetime.now() > demo_expires_at:
                            logger.warning(f"⚠️ Demo hesap süresi dolmuş: {demo_id}")
                            return None
                    except Exception as date_error:
                        logger.error(f"❌ Demo süre kontrol hatası: {date_error}")
                
                # Şifre doğrulama - PostgreSQL ve SQLite uyumlu
                password_hash = None
                if self.db_adapter.db_type == 'postgresql':
                    if hasattr(result, 'keys') and hasattr(result, 'get'):
                        password_hash = result.get('password_hash')
                    else:
                        password_hash = result[4] if len(result) > 4 else None
                else:
                    password_hash = result[4] if len(result) > 4 else None
                
                if password_hash and bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                    logger.info(f"✅ Demo kullanıcı doğrulandı: {demo_id}")
                    
                    # PostgreSQL ve SQLite için uyumlu veri döndürme
                    if self.db_adapter.db_type == 'postgresql':
                        if hasattr(result, 'keys') and hasattr(result, 'get'):
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
                        return {
                            'user_id': result[0],
                            'company_id': result[1],
                            'username': result[2],
                            'email': result[3],
                            'role': result[5],
                            'permissions': json.loads(result[6]) if result[6] else [],
                            'company_name': result[7]
                        }
                
                logger.error("❌ Demo kullanıcı şifre doğrulaması başarısız")
            else:
                logger.error(f"❌ Demo kullanıcı bulunamadı: {demo_id} - {email}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Demo kullanıcı doğrulama hatası: {e}")
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
            
            # Son giriş zamanını güncelle - PostgreSQL ve SQLite uyumlu
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = {placeholder}
                ''', (user_id,))
            else:
                cursor.execute(f'''
                    UPDATE users SET last_login = datetime('now') WHERE user_id = {placeholder}
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
            logger.info(f"🔧 DATABASE ADD CAMERA STARTED")
            logger.info(f"📋 Company ID: {company_id}")
            logger.info(f"📹 Camera data: {camera_data}")
            
            conn = self.get_connection()
            if conn is None:
                logger.error(f"❌ Database connection failed")
                return False, "Veritabanı bağlantısı başarısız"
                
            cursor = conn.cursor()
            logger.info(f"💾 Database connection established")
            
            # Unique camera ID oluştur
            camera_id = f"CAM_{uuid.uuid4().hex[:8].upper()}"
            logger.info(f"🆔 Generated camera ID: {camera_id}")
            
            # RTSP URL oluştur
            ip_address = camera_data.get('ip_address', '')
            
            # IP adresi kontrolü
            if not ip_address:
                logger.error("❌ IP adresi eksik")
                return False, "IP adresi gerekli"
            
            # IP adresi format kontrolü
            import re
            ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            if not re.match(ip_pattern, ip_address):
                logger.error(f"❌ Geçersiz IP adresi formatı: {ip_address}")
                return False, f"'{ip_address}' geçerli bir IP adresi değil. Örnek: 192.168.1.100"
            
            port = camera_data.get('port', 8080)
            username = camera_data.get('username', '')
            password = camera_data.get('password', '')
            protocol = camera_data.get('protocol', 'http')
            stream_path = camera_data.get('stream_path', '/video')
            
            logger.info(f"📝 Camera details:")
            logger.info(f"   - IP: {ip_address}")
            logger.info(f"   - Port: {port}")
            logger.info(f"   - Protocol: {protocol}")
            logger.info(f"   - Stream Path: {stream_path}")
            logger.info(f"   - Username: {username}")
            logger.info(f"   - Password: {'*' * len(password) if password else 'None'}")
            
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
            
            # Önce mevcut kamera var mı kontrol et (hem active hem deleted kameralar)
            camera_name = camera_data.get('name', camera_data.get('camera_name', 'Real Camera'))
            logger.info(f"🔍 Checking for existing camera with name: {camera_name}")
            
            cursor.execute(f'''
                SELECT camera_id, status FROM cameras 
                WHERE company_id = {placeholder} AND camera_name = {placeholder}
            ''', (company_id, camera_name))
            
            existing_camera = cursor.fetchone()
            if existing_camera:
                existing_camera_id, existing_status = existing_camera
                if existing_status == 'active':
                    logger.warning(f"⚠️ Active camera with name '{camera_name}' already exists")
                    conn.close()
                    return False, f"'{camera_name}' isimli kamera zaten mevcut. Farklı bir isim kullanın."
                elif existing_status == 'deleted':
                    logger.info(f"🔄 Found deleted camera with same name '{camera_name}', will reuse the record")
                    # Silinmiş kamerayı yeniden aktif hale getir
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute(f'''
                            UPDATE cameras 
                            SET status = 'active', 
                                location = {placeholder},
                                ip_address = {placeholder},
                                port = {placeholder},
                                protocol = {placeholder},
                                stream_path = {placeholder},
                                rtsp_url = {placeholder},
                                username = {placeholder},
                                password = {placeholder},
                                resolution = {placeholder},
                                fps = {placeholder},
                                updated_at = CURRENT_TIMESTAMP
                            WHERE camera_id = {placeholder}
                        ''', (
                            camera_data.get('location', 'Genel'),
                            ip_address,
                            port,
                            protocol,
                            stream_path,
                            rtsp_url,
                            username,
                            password,
                            resolution,
                            camera_data.get('fps', 25),
                            existing_camera_id
                        ))
                    else:
                        cursor.execute(f'''
                            UPDATE cameras 
                            SET status = 'active', 
                                location = {placeholder},
                                ip_address = {placeholder},
                                port = {placeholder},
                                protocol = {placeholder},
                                stream_path = {placeholder},
                                rtsp_url = {placeholder},
                                username = {placeholder},
                                password = {placeholder},
                                resolution = {placeholder},
                                fps = {placeholder},
                                updated_at = datetime('now')
                            WHERE camera_id = {placeholder}
                        ''', (
                            camera_data.get('location', 'Genel'),
                            ip_address,
                            port,
                            protocol,
                            stream_path,
                            rtsp_url,
                            username,
                            password,
                            resolution,
                            camera_data.get('fps', 25),
                            existing_camera_id
                        ))
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"✅ Successfully reactivated deleted camera: {existing_camera_id}")
                    return True, existing_camera_id
            
            logger.info(f"✅ No existing camera found with this name")
            
            # Production database için temel kolonları kullan
            basic_columns = [
                'camera_id', 'company_id', 'camera_name', 'location', 'ip_address',
                'port', 'protocol', 'stream_path', 'rtsp_url', 'username', 'password', 
                'resolution', 'fps', 'status'
            ]
            
            basic_values = [
                camera_id, 
                company_id, 
                camera_name,
                camera_data.get('location', 'Genel'),
                ip_address,
                port,
                protocol,
                stream_path,
                rtsp_url,
                username,
                password,
                resolution,
                camera_data.get('fps', 25),
                'active'
            ]
            
            logger.info(f"📊 Prepared values:")
            logger.info(f"   - Camera Name: {camera_name}")
            logger.info(f"   - Location: {camera_data.get('location', 'Genel')}")
            logger.info(f"   - RTSP URL: {rtsp_url}")
            logger.info(f"   - Resolution: {resolution}")
            logger.info(f"   - FPS: {camera_data.get('fps', 25)}")
            
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
            
            # Tüm kamera bilgilerini çek (protocol ve stream_path dahil)
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_id, camera_name, location, ip_address, rtsp_url, 
                       username, password, resolution, fps, status, last_detection,
                       created_at, protocol, stream_path, port
                FROM cameras
                WHERE company_id = {placeholder} AND status != 'deleted'
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
                        'port': row.get('port', 8080),  # Use actual port from database
                        'protocol': row.get('protocol', 'http'),  # Use actual protocol from database
                        'stream_path': row.get('stream_path', '/video'),  # Use actual stream_path from database
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
                        'port': row[14] if len(row) > 14 else 8080,  # Use actual port from database
                        'protocol': row[12] if len(row) > 12 else 'http',  # Use actual protocol from database
                        'stream_path': row[13] if len(row) > 13 else '/video',  # Use actual stream_path from database
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
            # Explicit column selection for better compatibility
            cursor.execute(f'''
                SELECT camera_id, camera_name, location, ip_address, port, protocol, stream_path,
                       rtsp_url, username, password, resolution, fps, status, last_detection,
                       created_at, updated_at
                FROM cameras 
                WHERE camera_id = {placeholder} AND company_id = {placeholder} AND status != 'deleted'
            ''', (camera_id, company_id))
            
            camera = cursor.fetchone()
            
            if camera:
                if hasattr(camera, 'keys') and hasattr(camera, 'get'):  # PostgreSQL RealDictRow
                    result = {
                        'camera_id': camera.get('camera_id'),
                        'camera_name': camera.get('camera_name'),
                        'location': camera.get('location'),
                        'ip_address': camera.get('ip_address'),
                        'port': camera.get('port', 8080),
                        'protocol': camera.get('protocol', 'http'),
                        'stream_path': camera.get('stream_path', '/video'),
                        'rtsp_url': camera.get('rtsp_url'),
                        'username': camera.get('username'),
                        'password': camera.get('password'),
                        'resolution': camera.get('resolution'),
                        'fps': camera.get('fps'),
                        'status': camera.get('status'),
                        'last_detection': str(camera.get('last_detection')) if camera.get('last_detection') else '',
                        'created_at': str(camera.get('created_at')) if camera.get('created_at') else '',
                        'updated_at': str(camera.get('updated_at')) if camera.get('updated_at') else str(camera.get('created_at', ''))
                    }
                else:  # SQLite tuple
                    result = {
                        'camera_id': camera[0] if len(camera) > 0 else '',
                        'camera_name': camera[1] if len(camera) > 1 else '',
                        'location': camera[2] if len(camera) > 2 else '',
                        'ip_address': camera[3] if len(camera) > 3 else '',
                        'port': camera[4] if len(camera) > 4 else 8080,
                        'protocol': camera[5] if len(camera) > 5 else 'http',
                        'stream_path': camera[6] if len(camera) > 6 else '/video',
                        'rtsp_url': camera[7] if len(camera) > 7 else '',
                        'username': camera[8] if len(camera) > 8 else '',
                        'password': camera[9] if len(camera) > 9 else '',
                        'resolution': camera[10] if len(camera) > 10 else '',
                        'fps': camera[11] if len(camera) > 11 else 25,
                        'status': camera[12] if len(camera) > 12 else '',
                        'last_detection': str(camera[13]) if len(camera) > 13 and camera[13] else '',
                        'created_at': str(camera[14]) if len(camera) > 14 and camera[14] else '',
                        'updated_at': str(camera[15]) if len(camera) > 15 and camera[15] else (str(camera[14]) if len(camera) > 14 and camera[14] else '')
                    }
                conn.close()
                return result
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"ERROR: Kamera getirme hatasi: {e}")
            if 'conn' in locals():
                conn.close()
            return None
    
    def update_camera(self, camera_id: str, company_id: str, camera_data: Dict) -> bool:
        """Kamerayı güncelle"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Önce kameranın bu şirkete ait olduğunu doğrula
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_name FROM cameras 
                WHERE company_id = {placeholder} AND camera_id = {placeholder} AND status != 'deleted'
            ''', (company_id, camera_id))
            
            if not cursor.fetchone():
                conn.close()
                return False
            
            # Kamerayı güncelle
            if self.db_adapter.db_type == 'postgresql':
                try:
                    cursor.execute(f'''
                        UPDATE cameras 
                        SET camera_name = {placeholder}, location = {placeholder}, ip_address = {placeholder},
                            port = {placeholder}, protocol = {placeholder}, stream_path = {placeholder},
                            username = {placeholder}, password = {placeholder}, updated_at = CURRENT_TIMESTAMP
                        WHERE company_id = {placeholder} AND camera_id = {placeholder}
                    ''', (
                        camera_data.get('name', ''),
                        camera_data.get('location', ''),
                        camera_data.get('ip_address', ''),
                        camera_data.get('port', 8080),
                        camera_data.get('protocol', 'http'),
                        camera_data.get('stream_path', '/video'),
                        camera_data.get('username', ''),
                        camera_data.get('password', ''),
                        company_id, camera_id
                    ))
                except Exception as e:
                    logger.error(f"❌ PostgreSQL update hatası: {e}")
                    # Updated_at kolonu yoksa ekle
                    if "updated_at" in str(e).lower():
                        logger.info("🔧 Updated_at kolonu ekleniyor...")
                        cursor.execute('ALTER TABLE cameras ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                        # Tekrar dene
                        cursor.execute(f'''
                            UPDATE cameras 
                            SET camera_name = {placeholder}, location = {placeholder}, ip_address = {placeholder},
                                port = {placeholder}, protocol = {placeholder}, stream_path = {placeholder},
                                username = {placeholder}, password = {placeholder}, updated_at = CURRENT_TIMESTAMP
                            WHERE company_id = {placeholder} AND camera_id = {placeholder}
                        ''', (
                            camera_data.get('name', ''),
                            camera_data.get('location', ''),
                            camera_data.get('ip_address', ''),
                            camera_data.get('port', 8080),
                            camera_data.get('protocol', 'http'),
                            camera_data.get('stream_path', '/video'),
                            camera_data.get('username', ''),
                            camera_data.get('password', ''),
                            company_id, camera_id
                        ))
            else:
                cursor.execute(f'''
                    UPDATE cameras 
                    SET camera_name = {placeholder}, location = {placeholder}, ip_address = {placeholder},
                        port = {placeholder}, protocol = {placeholder}, stream_path = {placeholder},
                        username = {placeholder}, password = {placeholder}, updated_at = datetime('now')
                    WHERE company_id = {placeholder} AND camera_id = {placeholder}
                ''', (
                    camera_data.get('name', ''),
                    camera_data.get('location', ''),
                    camera_data.get('ip_address', ''),
                    camera_data.get('port', 8080),
                    camera_data.get('protocol', 'http'),
                    camera_data.get('stream_path', '/video'),
                    camera_data.get('username', ''),
                    camera_data.get('password', ''),
                    company_id, camera_id
                ))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Updated camera: {camera_data.get('name', 'Unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Kamera güncelleme hatası: {e}")
            return False
    
    def delete_camera(self, camera_id: str, company_id: str) -> bool:
        """Kamerayı sil (basitleştirilmiş)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Önce kameranın bu şirkete ait olduğunu doğrula
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT camera_name FROM cameras 
                WHERE company_id = {placeholder} AND camera_id = {placeholder} AND status != 'deleted'
            ''', (company_id, camera_id))
            
            if not cursor.fetchone():
                conn.close()
                return False
            
            # Kamerayı sil (soft delete)
            if self.db_adapter.db_type == 'postgresql':
                try:
                    cursor.execute(f'''
                        UPDATE cameras 
                        SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                        WHERE company_id = {placeholder} AND camera_id = {placeholder}
                    ''', (company_id, camera_id))
                except Exception as e:
                    logger.error(f"❌ PostgreSQL delete hatası: {e}")
                    # Updated_at kolonu yoksa ekle
                    if "updated_at" in str(e).lower():
                        logger.info("🔧 Updated_at kolonu ekleniyor...")
                        cursor.execute('ALTER TABLE cameras ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                        # Tekrar dene
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
    
    def update_camera_status(self, camera_id: str, company_id: str, new_status: str) -> bool:
        """Kamera durumunu güncelle (aktif/pasif)"""
        try:
            logger.info(f"🔄 Updating camera status: {camera_id} to {new_status}")
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            
            # Kameranın var olduğunu kontrol et
            cursor.execute(f'''
                SELECT camera_name, status FROM cameras 
                WHERE company_id = {placeholder} AND camera_id = {placeholder}
            ''', (company_id, camera_id))
            
            result = cursor.fetchone()
            if not result:
                logger.error(f"❌ Camera not found in database: {camera_id}")
                conn.close()
                return False
            
            current_status = result[1] if len(result) > 1 else 'unknown'
            logger.info(f"📹 Current status in DB: {current_status}, updating to: {new_status}")
            
            # Durumu güncelle
            if self.db_adapter.db_type == 'postgresql':
                try:
                    cursor.execute(f'''
                        UPDATE cameras 
                        SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP
                        WHERE company_id = {placeholder} AND camera_id = {placeholder}
                    ''', (new_status, company_id, camera_id))
                except Exception as e:
                    logger.error(f"❌ PostgreSQL status update hatası: {e}")
                    # Updated_at kolonu yoksa ekle
                    if "updated_at" in str(e).lower():
                        logger.info("🔧 Updated_at kolonu ekleniyor...")
                        cursor.execute('ALTER TABLE cameras ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                        # Tekrar dene
                        cursor.execute(f'''
                            UPDATE cameras 
                            SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP
                            WHERE company_id = {placeholder} AND camera_id = {placeholder}
                        ''', (new_status, company_id, camera_id))
            else:
                cursor.execute(f'''
                    UPDATE cameras 
                    SET status = {placeholder}, updated_at = datetime('now')
                    WHERE company_id = {placeholder} AND camera_id = {placeholder}
                ''', (new_status, company_id, camera_id))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Camera status updated successfully in database")
            return True
            
        except Exception as e:
            logger.error(f"ERROR: Kamera status güncelleme hatasi: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def get_company_info(self, company_id: str) -> Optional[Dict]:
        """Şirket bilgilerini getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT company_id, company_name, sector, contact_person, email, phone, address,
                       max_cameras, subscription_type, subscription_start, subscription_end,
                       status, created_at, api_key
                FROM companies 
                WHERE company_id = {placeholder}
            ''', (company_id,))
            
            result = cursor.fetchone()
            
            if result:
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(result, 'keys'):  # PostgreSQL Row object
                    company_info = {
                        'company_id': result['company_id'],
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'contact_person': result['contact_person'],
                        'email': result['email'],
                        'phone': result['phone'],
                        'address': result['address'],
                        'max_cameras': result['max_cameras'],
                        'subscription_type': result['subscription_type'],
                        'subscription_start': result['subscription_start'],
                        'subscription_end': result['subscription_end'],
                        'status': result['status'],
                        'created_at': result['created_at'],
                        'api_key': result['api_key']
                    }
                else:  # SQLite tuple
                    company_info = {
                        'company_id': result[0],
                        'company_name': result[1],
                        'sector': result[2],
                        'contact_person': result[3],
                        'email': result[4],
                        'phone': result[5],
                        'address': result[6],
                        'max_cameras': result[7],
                        'subscription_type': result[8],
                        'subscription_start': result[9],
                        'subscription_end': result[10],
                        'status': result[11],
                        'created_at': result[12],
                        'api_key': result[13]
                    }
                
                return company_info
            else:
                logger.warning(f"⚠️ Company not found: {company_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Get company info error: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_active_camera_count(self, company_id: str) -> int:
        """Şirketin aktif kamera sayısını getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            cursor.execute(f'''
                SELECT COUNT(*) FROM cameras 
                WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            result = cursor.fetchone()
            
            if result:
                if hasattr(result, 'keys'):  # PostgreSQL Row object
                    return list(result.values())[0] or 0
                else:  # SQLite tuple
                    return result[0] or 0
            else:
                return 0
                
        except Exception as e:
            logger.error(f"❌ Get active camera count error: {e}")
            return 0
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_company_stats(self, company_id: str) -> Dict:
        """Enhanced şirket istatistikleri"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Bugünkü istatistikler
            placeholder = self.get_placeholder()
            
            try:
                # Önce kolonların varlığını kontrol et ve yoksa ekle
                try:
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'detections' AND table_schema = 'public'
                        """)
                        columns = [row[0] if isinstance(row, (list, tuple)) else (row['column_name'] if hasattr(row, 'get') else str(row)) for row in cursor.fetchall()]
                    else:
                        cursor.execute("PRAGMA table_info(detections)")
                        columns = [row[1] for row in cursor.fetchall()]  # SQLite PRAGMA returns (cid, name, type, notnull, dflt_value, pk)
                except Exception as e:
                    logger.warning(f"⚠️ Column check hatası, varsayılan kolonlar kullanılıyor: {e}")
                    columns = []  # Kolon kontrolü başarısız, güvenli varsayılanlar kullan
                
                # Eksik kolonları ekle
                if 'compliance_rate' not in columns:
                    try:
                        if self.db_adapter.db_type == 'postgresql':
                            cursor.execute('ALTER TABLE detections ADD COLUMN compliance_rate REAL')
                        else:
                            cursor.execute('ALTER TABLE detections ADD COLUMN compliance_rate REAL')
                        conn.commit()
                        logger.info("✅ compliance_rate kolonu eklendi (runtime migration)")
                        columns.append('compliance_rate')
                    except Exception as e:
                        logger.warning(f"⚠️ compliance_rate kolonu eklenemedi: {e}")
                
                if 'compliant_people' not in columns:
                    try:
                        if self.db_adapter.db_type == 'postgresql':
                            cursor.execute('ALTER TABLE detections ADD COLUMN compliant_people INTEGER DEFAULT 0')
                        else:
                            cursor.execute('ALTER TABLE detections ADD COLUMN compliant_people INTEGER DEFAULT 0')
                        conn.commit()
                        logger.info("✅ compliant_people kolonu eklendi (runtime migration)")
                        columns.append('compliant_people')
                    except Exception as e:
                        logger.warning(f"⚠️ compliant_people kolonu eklenemedi: {e}")
                
                if 'violation_people' not in columns:
                    try:
                        if self.db_adapter.db_type == 'postgresql':
                            cursor.execute('ALTER TABLE detections ADD COLUMN violation_people INTEGER DEFAULT 0')
                        else:
                            cursor.execute('ALTER TABLE detections ADD COLUMN violation_people INTEGER DEFAULT 0')
                        conn.commit()
                        logger.info("✅ violation_people kolonu eklendi (runtime migration)")
                        columns.append('violation_people')
                    except Exception as e:
                        logger.warning(f"⚠️ violation_people kolonu eklenemedi: {e}")
                
                # track_id kolonunu kontrol et ve ekle
                if 'track_id' not in columns:
                    try:
                        if self.db_adapter.db_type == 'postgresql':
                            cursor.execute('ALTER TABLE detections ADD COLUMN track_id TEXT')
                        else:
                            cursor.execute('ALTER TABLE detections ADD COLUMN track_id TEXT')
                        conn.commit()
                        logger.info("✅ track_id kolonu eklendi (runtime migration)")
                        columns.append('track_id')
                    except Exception as e:
                        logger.warning(f"⚠️ track_id kolonu eklenemedi: {e}")
                
                # Kolon durumlarını kontrol et (try bloğu içinde)
                has_compliance_rate = 'compliance_rate' in columns
                has_compliant_people = 'compliant_people' in columns
                has_violation_people = 'violation_people' in columns
                has_track_id = 'track_id' in columns
                
                # SQLite ve PostgreSQL için farklı sorgular
                if self.db_adapter.db_type == 'postgresql':
                    if has_compliance_rate:
                        compliance_calc = f"AVG(COALESCE(compliance_rate, CASE WHEN people_detected > 0 THEN (ppe_compliant::FLOAT / people_detected::FLOAT * 100.0) ELSE 0 END))"
                    else:
                        compliance_calc = "CASE WHEN SUM(people_detected) > 0 THEN (SUM(ppe_compliant)::FLOAT / SUM(people_detected)::FLOAT * 100.0) ELSE 0 END"
                    
                    compliant_people_col = "COALESCE(SUM(ppe_compliant), SUM(compliant_people), 0)" if has_compliant_people else "SUM(ppe_compliant)"
                    violation_people_col = "COALESCE(SUM(violations_count), SUM(violation_people), 0)" if has_violation_people else "SUM(violations_count)"
                    
                    cursor.execute(f'''
                        SELECT 
                            COUNT(*) as total_detections,
                            COALESCE(SUM(people_detected), SUM(total_people), 0) as total_people,
                            {compliant_people_col} as compliant_people,
                            {violation_people_col} as violation_people,
                            CASE 
                                WHEN COUNT(*) > 0 AND SUM(people_detected) > 0 
                                THEN {compliance_calc}
                                ELSE 0 
                            END as avg_compliance_rate
                        FROM detections
                        WHERE company_id = {placeholder} AND DATE(timestamp) = CURRENT_DATE
                    ''', (company_id,))
                else:
                    # SQLite için
                    if has_compliance_rate:
                        compliance_calc = "AVG(COALESCE(compliance_rate, CASE WHEN people_detected > 0 THEN (ppe_compliant * 100.0 / people_detected) ELSE 0 END))"
                    else:
                        compliance_calc = "CASE WHEN SUM(people_detected) > 0 THEN (SUM(ppe_compliant) * 100.0 / SUM(people_detected)) ELSE 0 END"
                    
                    compliant_people_col = "COALESCE(SUM(ppe_compliant), SUM(compliant_people), 0)" if has_compliant_people else "SUM(ppe_compliant)"
                    violation_people_col = "COALESCE(SUM(violations_count), SUM(violation_people), 0)" if has_violation_people else "SUM(violations_count)"
                    
                    cursor.execute(f'''
                        SELECT 
                            COUNT(*) as total_detections,
                            COALESCE(SUM(people_detected), SUM(total_people), 0) as total_people,
                            {compliant_people_col} as compliant_people,
                            {violation_people_col} as violation_people,
                            CASE 
                                WHEN COUNT(*) > 0 AND SUM(people_detected) > 0 
                                THEN {compliance_calc}
                                ELSE 0 
                            END as avg_compliance_rate
                        FROM detections
                        WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                    ''', (company_id,))
                
                detection_stats = cursor.fetchone()
            except Exception as e:
                logger.warning(f"⚠️ Detections query hatası, varsayılan değerler kullanılıyor: {e}")
                detection_stats = None
            
            # PostgreSQL RealDictRow için sözlük erişimi kullan
            # has_compliance_rate değişkenini try bloğu dışında da kullanabilmek için
            has_compliance_rate = False
            has_compliant_people = False
            has_violation_people = False
            
            if detection_stats:
                if hasattr(detection_stats, 'keys') and hasattr(detection_stats, 'get'):  # RealDictRow veya dict
                    total_detections = detection_stats.get('total_detections') or 0
                    total_people = detection_stats.get('total_people') or 0
                    compliant_people = detection_stats.get('compliant_people') or 0
                    violation_people = detection_stats.get('violation_people') or 0
                    avg_compliance_rate = detection_stats.get('avg_compliance_rate') or 0
                else:  # Liste formatı (SQLite için)
                    total_detections = detection_stats[0] or 0 if len(detection_stats) > 0 else 0
                    total_people = detection_stats[1] or 0 if len(detection_stats) > 1 else 0
                    compliant_people = detection_stats[2] or 0 if len(detection_stats) > 2 else 0
                    violation_people = detection_stats[3] or 0 if len(detection_stats) > 3 else 0
                    avg_compliance_rate = detection_stats[4] or 0 if len(detection_stats) > 4 else 0
            else:
                total_detections = total_people = compliant_people = violation_people = avg_compliance_rate = 0
            
            # Aktif kamera sayısı
            cursor.execute(f'''
                SELECT COUNT(*) FROM cameras WHERE company_id = {placeholder} AND status = 'active'
            ''', (company_id,))
            
            active_cameras_result = cursor.fetchone()
            if hasattr(active_cameras_result, 'keys') and hasattr(active_cameras_result, 'values'):  # RealDictRow
                # PostgreSQL'de COUNT(*) sonucu 'count' değil, doğrudan değer döner
                active_cameras = list(active_cameras_result.values())[0] if active_cameras_result else 0
            else:  # Liste formatı (SQLite için)
                active_cameras = active_cameras_result[0] if active_cameras_result else 0
            
            # Bugünkü ihlal sayısı
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND DATE(timestamp) = CURRENT_DATE
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                ''', (company_id,))
            
            today_violations_result = cursor.fetchone()
            if hasattr(today_violations_result, 'keys') and hasattr(today_violations_result, 'values'):  # RealDictRow
                today_violations = list(today_violations_result.values())[0] if today_violations_result else 0
            else:  # Liste formatı (SQLite için)
                today_violations = today_violations_result[0] if today_violations_result else 0
            
            # Dünkü istatistikler (trend hesaplama için)
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) = date('now', '-1 day')
                ''', (company_id,))
            
            yesterday_violations_result = cursor.fetchone()
            if hasattr(yesterday_violations_result, 'keys') and hasattr(yesterday_violations_result, 'values'):  # RealDictRow
                yesterday_violations = list(yesterday_violations_result.values())[0] if yesterday_violations_result else 0
            else:  # Liste formatı (SQLite için)
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
            if hasattr(last_week_cameras_result, 'keys') and hasattr(last_week_cameras_result, 'values'):  # RealDictRow
                last_week_cameras = list(last_week_cameras_result.values())[0] if last_week_cameras_result else 0
            else:  # Liste formatı (SQLite için)
                last_week_cameras = last_week_cameras_result[0] if last_week_cameras_result else 0
            
            # Compliance trend (son 7 günün ortalaması)
            # Kolon kontrolü yaparak güvenli sorgu
            try:
                # Önce kolonların varlığını tekrar kontrol et (compliance_rate için)
                try:
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = 'detections' AND table_schema = 'public'
                                AND column_name = 'compliance_rate'
                            )
                        """)
                        has_compliance_rate = cursor.fetchone()[0]
                    else:
                        cursor.execute("PRAGMA table_info(detections)")
                        columns_info = cursor.fetchall()
                        has_compliance_rate = any(row[1] == 'compliance_rate' for row in columns_info)
                except Exception:
                    has_compliance_rate = False
                
                if self.db_adapter.db_type == 'postgresql':
                    if has_compliance_rate:
                        # PostgreSQL: compliance_rate varsa kullan
                        cursor.execute(f'''
                            SELECT 
                                CASE 
                                    WHEN COUNT(*) > 0 AND SUM(people_detected) > 0 
                                    THEN AVG(COALESCE(compliance_rate, 
                                        CASE WHEN people_detected > 0 
                                        THEN (ppe_compliant::FLOAT / people_detected::FLOAT * 100.0) 
                                        ELSE 0 END))
                                    ELSE 0 
                                END as avg_compliance
                            FROM detections 
                            WHERE company_id = {placeholder} AND DATE(timestamp) > CURRENT_DATE - INTERVAL '7 days'
                        ''', (company_id,))
                    else:
                        # PostgreSQL: compliance_rate yoksa hesapla
                        cursor.execute(f'''
                            SELECT 
                                CASE 
                                    WHEN SUM(people_detected) > 0 
                                    THEN (SUM(ppe_compliant)::FLOAT / NULLIF(SUM(people_detected), 0)::FLOAT * 100.0)
                                    ELSE 0 
                                END as avg_compliance
                            FROM detections 
                            WHERE company_id = {placeholder} AND DATE(timestamp) > CURRENT_DATE - INTERVAL '7 days'
                        ''', (company_id,))
                else:
                    # SQLite için
                    if has_compliance_rate:
                        # SQLite: compliance_rate varsa kullan
                        cursor.execute(f'''
                            SELECT 
                                CASE 
                                    WHEN COUNT(*) > 0 AND SUM(people_detected) > 0 
                                    THEN AVG(COALESCE(compliance_rate, 
                                        CASE WHEN people_detected > 0 
                                        THEN (ppe_compliant * 100.0 / people_detected) 
                                        ELSE 0 END))
                                    ELSE 0 
                                END as avg_compliance
                            FROM detections 
                            WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-7 days')
                        ''', (company_id,))
                    else:
                        # SQLite: compliance_rate yoksa hesapla
                        cursor.execute(f'''
                            SELECT 
                                CASE 
                                    WHEN SUM(people_detected) > 0 
                                    THEN (SUM(ppe_compliant) * 100.0 / NULLIF(SUM(people_detected), 0))
                                    ELSE 0 
                                END as avg_compliance
                            FROM detections 
                            WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-7 days')
                        ''', (company_id,))
            except Exception as e:
                # Eğer compliance_rate kolonu yoksa, sadece hesaplama yap
                logger.warning(f"⚠️ Compliance rate query hatası, basit hesaplama kullanılıyor: {e}")
                if self.db_adapter.db_type == 'postgresql':
                    cursor.execute(f'''
                        SELECT 
                            CASE 
                                WHEN SUM(people_detected) > 0 
                                THEN (SUM(ppe_compliant)::FLOAT / NULLIF(SUM(people_detected), 0)::FLOAT * 100.0)
                                ELSE 0 
                            END as avg_compliance
                        FROM detections 
                        WHERE company_id = {placeholder} AND DATE(timestamp) > CURRENT_DATE - INTERVAL '7 days'
                    ''', (company_id,))
                else:
                    cursor.execute(f'''
                        SELECT 
                            CASE 
                                WHEN SUM(people_detected) > 0 
                                THEN (SUM(ppe_compliant) * 100.0 / NULLIF(SUM(people_detected), 0))
                                ELSE 0 
                            END as avg_compliance
                    FROM detections 
                    WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-7 days')
                ''', (company_id,))
            
            week_compliance_result = cursor.fetchone()
            if hasattr(week_compliance_result, 'keys') and hasattr(week_compliance_result, 'values'):  # RealDictRow
                week_compliance = list(week_compliance_result.values())[0] if week_compliance_result else 0
            else:  # Liste formatı (SQLite için)
                week_compliance = week_compliance_result[0] if week_compliance_result and len(week_compliance_result) > 0 else 0
            
            # NULL kontrolü
            if week_compliance is None:
                week_compliance = 0
            
            # Aktif çalışan sayısı (bugün tespit edilen unique kişi sayısı)
            # track_id kolonu varsa kullan, yoksa people_detected kullan
            try:
                # Önce track_id kolonunun varlığını kontrol et
                has_track_id = False
                try:
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = 'detections' AND table_schema = 'public'
                                AND column_name = 'track_id'
                            )
                        """)
                        has_track_id = cursor.fetchone()[0]
                    else:
                        cursor.execute("PRAGMA table_info(detections)")
                        columns_info = cursor.fetchall()
                        has_track_id = any(row[1] == 'track_id' for row in columns_info)
                except Exception:
                    has_track_id = False
                
                if has_track_id:
                    # track_id kolonu varsa kullan
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute(f'''
                            SELECT COUNT(DISTINCT track_id) 
                            FROM detections 
                            WHERE company_id = {placeholder} AND DATE(timestamp) = CURRENT_DATE
                            AND track_id IS NOT NULL
                        ''', (company_id,))
                    else:
                        cursor.execute(f'''
                            SELECT COUNT(DISTINCT track_id) 
                            FROM detections 
                            WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                            AND track_id IS NOT NULL
                        ''', (company_id,))
                else:
                    # track_id kolonu yoksa, people_detected kullan (yaklaşık değer)
                    if self.db_adapter.db_type == 'postgresql':
                        cursor.execute(f'''
                            SELECT COALESCE(SUM(people_detected), 0)
                            FROM detections 
                            WHERE company_id = {placeholder} AND DATE(timestamp) = CURRENT_DATE
                        ''', (company_id,))
                    else:
                        cursor.execute(f'''
                            SELECT COALESCE(SUM(people_detected), 0)
                            FROM detections 
                            WHERE company_id = {placeholder} AND date(timestamp) = date('now')
                        ''', (company_id,))
                
                active_workers_result = cursor.fetchone()
                if hasattr(active_workers_result, 'keys') and hasattr(active_workers_result, 'values'):  # RealDictRow
                    active_workers = list(active_workers_result.values())[0] if active_workers_result else 0
                else:  # Liste formatı (SQLite için)
                    active_workers = active_workers_result[0] if active_workers_result and len(active_workers_result) > 0 else 0
                
                # NULL kontrolü
                if active_workers is None:
                    active_workers = 0
            except Exception as e:
                logger.warning(f"⚠️ Active workers query hatası, varsayılan değer kullanılıyor: {e}")
                active_workers = 0
            
            # Aylık ihlal sayısı
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND DATE(timestamp) > CURRENT_DATE - INTERVAL '30 days'
                ''', (company_id,))
            else:
                cursor.execute(f'''
                    SELECT COUNT(*) FROM violations 
                    WHERE company_id = {placeholder} AND date(timestamp) > date('now', '-30 days')
                ''', (company_id,))
            
            monthly_violations_result = cursor.fetchone()
            if hasattr(monthly_violations_result, 'keys') and hasattr(monthly_violations_result, 'values'):  # RealDictRow
                monthly_violations = list(monthly_violations_result.values())[0] if monthly_violations_result else 0
            else:  # Liste formatı (SQLite için)
                monthly_violations = monthly_violations_result[0] if monthly_violations_result and len(monthly_violations_result) > 0 else 0
            
            # NULL kontrolü
            if monthly_violations is None:
                monthly_violations = 0
            
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
            today_violations = today_violations or 0
            yesterday_violations = yesterday_violations or 0
            last_week_cameras = last_week_cameras or 0
            
            result = {
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
            
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"❌ İstatistik getirme hatası: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            if 'conn' in locals():
                try:
                    conn.close()
                except:
                    pass
            return {
                'total_detections': 0,
                'total_people': 0,
                'compliant_people': 0,
                'violation_people': 0,
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

    def get_subscription_info(self, company_id):
        """Şirket abonelik bilgilerini getir"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            # Şirket abonelik bilgilerini al
            cursor.execute(f"""
                SELECT subscription_type, billing_cycle, subscription_start, subscription_end, 
                       max_cameras, created_at, company_name, sector, payment_status, 
                       auto_renewal, next_billing_date
                FROM companies 
                WHERE company_id = {placeholder}
            """, (company_id,))
            
            result = cursor.fetchone()
            
            if result:
                # Kamera kullanımını al
                cameras = self.get_company_cameras(company_id)
                used_cameras = len(cameras)
                
                # PostgreSQL Row object vs SQLite tuple compatibility
                if hasattr(result, 'keys'):  # PostgreSQL Row object
                    subscription_end = result['subscription_end']
                    subscription_start = result['subscription_start']
                    subscription_info = {
                        'subscription_type': result['subscription_type'] or 'basic',
                        'billing_cycle': result['billing_cycle'] or 'monthly',
                        'subscription_start': subscription_start,
                        'payment_status': result['payment_status'] or 'active',
                        'auto_renewal': result['auto_renewal'],
                        'next_billing_date': result['next_billing_date'],
                        'max_cameras': result['max_cameras'] or 25,
                        'created_at': result['created_at'] if result['created_at'] else None,
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'used_cameras': used_cameras,
                    }
                else:  # SQLite tuple
                    # subscription_type, billing_cycle, subscription_start, subscription_end, max_cameras, created_at, company_name, sector, payment_status, auto_renewal, next_billing_date
                    subscription_end = result[3]
                    subscription_start = result[2]
                    subscription_info = {
                        'subscription_type': result[0] or 'basic',
                        'billing_cycle': result[1] or 'monthly',
                        'subscription_start': subscription_start,
                        'payment_status': result[8] or 'active',
                        'auto_renewal': result[9],
                        'next_billing_date': result[10],
                        'max_cameras': result[4] or 25,
                        'created_at': result[5] if result[5] else None,
                        'company_name': result[6],
                        'sector': result[7],
                        'used_cameras': used_cameras,
                    }
                
                # Plan fiyat bilgilerini ekle
                plan_prices = {
                    'starter': {'monthly': 99, 'yearly': 990, 'cameras': 25},
                    'professional': {'monthly': 299, 'yearly': 2990, 'cameras': 100},
                    'enterprise': {'monthly': 599, 'yearly': 5990, 'cameras': 500}
                }
                
                current_plan = subscription_info['subscription_type'].lower()
                billing_cycle = subscription_info['billing_cycle']
                
                if current_plan in plan_prices:
                    subscription_info['current_price'] = plan_prices[current_plan][billing_cycle]
                    subscription_info['monthly_price'] = plan_prices[current_plan]['monthly']
                    subscription_info['yearly_price'] = plan_prices[current_plan]['yearly']
                else:
                    subscription_info['current_price'] = 99
                    subscription_info['monthly_price'] = 99
                    subscription_info['yearly_price'] = 990
                
                # Abonelik durumunu kontrol et
                is_active = True
                days_remaining = 0
                
                if subscription_end:
                    try:
                        if isinstance(subscription_end, str):
                            # Handle different date formats including microseconds
                            if 'T' in subscription_end:  # ISO format with timezone
                                subscription_end = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                            elif '.' in subscription_end:  # SQLite format with microseconds: '2025-08-01 22:14:59.075710'
                                subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
                            else:  # Standard format: '2025-08-01 22:14:59'
                                subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S')
                            
                            days_remaining = (subscription_end - datetime.now()).days
                            is_active = days_remaining > 0
                            
                            logger.info(f"🔍 Subscription end: {subscription_end}, days remaining: {days_remaining}, is_active: {is_active}")
                    except Exception as date_error:
                        logger.error(f"❌ Date parsing error: {date_error}")
                        logger.error(f"❌ Raw subscription_end value: {subscription_end}")
                        is_active = True
                        days_remaining = 0
                
                # Ortak alanları ekle
                # Format subscription_start date
                subscription_start = subscription_info.get('created_at')
                if subscription_start and isinstance(subscription_start, str):
                    try:
                        if '.' in subscription_start:  # SQLite format with microseconds
                            subscription_start = datetime.strptime(subscription_start, '%Y-%m-%d %H:%M:%S.%f').isoformat()
                        else:  # Standard format
                            subscription_start = datetime.strptime(subscription_start, '%Y-%m-%d %H:%M:%S').isoformat()
                    except Exception as e:
                        logger.error(f"❌ Subscription start date parsing error: {e}")
                        subscription_start = None
                
                subscription_info.update({
                    'subscription_start': subscription_start,
                    'subscription_end': subscription_end.isoformat() if subscription_end else None,
                    'is_active': is_active,
                    'days_remaining': days_remaining,
                    'usage_percentage': (used_cameras / (subscription_info['max_cameras'] or 25)) * 100
                })
                
                conn.close()
                return {
                    'success': True,
                    'subscription': subscription_info
                }
            else:
                conn.close()
                return {'success': False, 'error': 'Şirket bulunamadı'}
                
        except Exception as e:
            logger.error(f"❌ Internal abonelik bilgileri getirme hatası: {e}")
            if 'conn' in locals():
                try:
                    conn.close()
                except:
                    pass
            return {'success': False, 'error': 'Veri getirme başarısız'}

    def update_company_logo_url(self, company_id: str, logo_url: str) -> bool:
        """Şirket logo URL'ini güncelle"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            
            # Timestamp fonksiyonu - PostgreSQL ve SQLite uyumlu
            if self.db_adapter.db_type == 'postgresql':
                cursor.execute(f"""
                    UPDATE companies 
                    SET logo_url = {placeholder}, updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = {placeholder}
                """, (logo_url, company_id))
            else:
                cursor.execute(f"""
                    UPDATE companies 
                    SET logo_url = {placeholder}, updated_at = datetime('now')
                    WHERE company_id = {placeholder}
                """, (logo_url, company_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Company logo URL updated: {company_id} -> {logo_url}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update company logo URL: {e}")
            return False

    def get_company_info(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Şirket bilgilerini getir (cache'lenmiş)"""
        # Cache kontrolü - her frame'de DB sorgusu yapmamak için
        if not hasattr(self, '_company_info_cache'):
            self._company_info_cache = {}
            self._company_info_cache_time = {}
        
        cache_key = company_id
        cache_ttl = 60  # 60 saniye cache
        
        # Cache'den kontrol et
        if cache_key in self._company_info_cache:
            cache_time = self._company_info_cache_time.get(cache_key, 0)
            if (datetime.now().timestamp() - cache_time) < cache_ttl:
                logger.debug(f"🔍 Company info cache hit: {company_id}")
                return self._company_info_cache[cache_key]
        
        try:
            logger.debug(f"🔍 MultiTenantDatabase - get_company_info çağrıldı: {company_id}")
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = self.get_placeholder()
            
            query = f'''
                SELECT company_name, sector, contact_person, email, phone, address,
                       subscription_type, subscription_start, subscription_end, max_cameras, logo_url
                FROM companies 
                WHERE company_id = {placeholder}
            '''
            
            cursor.execute(query, (company_id,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                # SQLite Row vs PostgreSQL RealDictRow tespiti
                if isinstance(result, sqlite3.Row):
                    # SQLite Row - dict-like ama tuple gibi de erişilebilir
                    logger.debug(f"🔍 MultiTenantDatabase - SQLite Row formatı")
                    company_info = {
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'contact_person': result['contact_person'],
                        'email': result['email'],
                        'phone': result['phone'],
                        'address': result['address'],
                        'subscription_type': result['subscription_type'],
                        'subscription_start': result['subscription_start'],
                        'subscription_end': result['subscription_end'],
                        'max_cameras': result['max_cameras'],
                        'logo_url': result['logo_url'] if len(result) > 10 else None
                    }
                elif hasattr(result, 'keys') and not isinstance(result, (tuple, list)):
                    # PostgreSQL RealDictRow
                    logger.debug(f"🔍 MultiTenantDatabase - PostgreSQL RealDictRow formatı")
                    company_info = {
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'contact_person': result['contact_person'],
                        'email': result['email'],
                        'phone': result['phone'],
                        'address': result['address'],
                        'subscription_type': result['subscription_type'],
                        'subscription_start': result['subscription_start'],
                        'subscription_end': result['subscription_end'],
                        'max_cameras': result['max_cameras'],
                        'logo_url': result['logo_url']
                    }
                else:  # SQLite tuple
                    logger.debug(f"🔍 MultiTenantDatabase - SQLite tuple formatı")
                    company_info = {
                        'company_name': result[0],
                        'sector': result[1],
                        'contact_person': result[2],
                        'email': result[3],
                        'phone': result[4],
                        'address': result[5],
                        'subscription_type': result[6],
                        'subscription_start': result[7],
                        'subscription_end': result[8],
                        'max_cameras': result[9],
                        'logo_url': result[10] if len(result) > 10 else None
                    }
                
                # Cache'e kaydet
                self._company_info_cache[cache_key] = company_info
                self._company_info_cache_time[cache_key] = datetime.now().timestamp()
                
                logger.debug(f"🔍 MultiTenantDatabase - Company info cached: {company_id}")
                return company_info
            else:
                logger.debug(f"🔍 MultiTenantDatabase - Query sonucu bulunamadı")
                return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get company info: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_subscription_info_internal(self, company_id):
        """Şirket abonelik bilgilerini internal API için getir"""
        return self.get_subscription_info(company_id)

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
                    'max_cameras': 100,
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