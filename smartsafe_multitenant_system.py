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
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from flask_cors import CORS
import bcrypt

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
        self.init_database()
    
    def get_connection(self, timeout: int = 30):
        """Database connection with timeout"""
        conn = sqlite3.connect(self.db_path, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    
    def init_database(self):
        """Multi-tenant veritabanı tablolarını oluştur"""
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
                rtsp_url TEXT,
                username TEXT,
                password TEXT,
                resolution TEXT DEFAULT '1920x1080',
                fps INTEGER DEFAULT 25,
                status TEXT DEFAULT 'active',
                last_detection DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
                resolved BOOLEAN DEFAULT 0,
                resolved_by TEXT,
                resolved_at DATETIME,
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
        conn.close()
        logger.info("✅ Multi-tenant veritabanı oluşturuldu")
    
    def create_company(self, company_data: Dict) -> Tuple[bool, str]:
        """Yeni şirket kaydı"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Benzersiz şirket ID oluştur
            company_id = f"COMP_{uuid.uuid4().hex[:8].upper()}"
            
            # API key oluştur
            api_key = f"sk_{secrets.token_urlsafe(32)}"
            
            # Abonelik bitiş tarihi (1 yıl)
            subscription_end = datetime.now() + timedelta(days=365)
            
            cursor.execute('''
                INSERT INTO companies 
                (company_id, company_name, sector, contact_person, email, phone, address, 
                 max_cameras, subscription_type, subscription_end, api_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                company_id, company_data['company_name'], company_data['sector'],
                company_data['contact_person'], company_data['email'], 
                company_data.get('phone', ''), company_data.get('address', ''),
                company_data.get('max_cameras', 5), company_data.get('subscription_type', 'basic'),
                subscription_end, api_key
            ))
            
            # Varsayılan admin kullanıcısı oluştur
            user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
            password_hash = bcrypt.hashpw(
                company_data['password'].encode('utf-8'), 
                bcrypt.gensalt()
            ).decode('utf-8')
            
            cursor.execute('''
                INSERT INTO users 
                (user_id, company_id, username, email, password_hash, role, permissions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.user_id, u.company_id, u.username, u.email, u.password_hash, 
                       u.role, u.permissions, c.company_name, c.status as company_status
                FROM users u
                JOIN companies c ON u.company_id = c.company_id
                WHERE u.email = ? AND u.status = 'active' AND c.status = 'active'
            ''', (email,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and bcrypt.checkpw(password.encode('utf-8'), result[4].encode('utf-8')):
                return {
                    'user_id': result[0],
                    'company_id': result[1],
                    'username': result[2],
                    'email': result[3],
                    'role': result[5],
                    'permissions': json.loads(result[6]) if result[6] else [],
                    'company_name': result[7]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Kimlik doğrulama hatası: {e}")
            return None
    
    def create_session(self, user_id: str, company_id: str, ip_address: str, user_agent: str) -> str:
        """Oturum oluştur"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            session_id = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)
            
            cursor.execute('''
                INSERT INTO sessions 
                (session_id, user_id, company_id, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, user_id, company_id, expires_at, ip_address, user_agent))
            
            # Son giriş zamanını güncelle
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?
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
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.user_id, s.company_id, u.username, u.email, u.role, 
                       u.permissions, c.company_name
                FROM sessions s
                JOIN users u ON s.user_id = u.user_id
                JOIN companies c ON s.company_id = c.company_id
                WHERE s.session_id = ? AND s.expires_at > CURRENT_TIMESTAMP 
                      AND s.status = 'active' AND u.status = 'active' AND c.status = 'active'
            ''', (session_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
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
        """Şirket kamerası ekleme"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Önce şirketin max_cameras limitini al
            cursor.execute('''
                SELECT max_cameras FROM companies WHERE company_id = ? AND status = 'active'
            ''', (company_id,))
            
            company_result = cursor.fetchone()
            if not company_result:
                return False, "Şirket bulunamadı veya aktif değil"
            
            max_cameras = company_result[0] or 5  # Default 5 kamera
            
            # Mevcut aktif kamera sayısını al
            cursor.execute('''
                SELECT COUNT(*) FROM cameras WHERE company_id = ? AND status = 'active'
            ''', (company_id,))
            
            current_cameras = cursor.fetchone()[0]
            
            if current_cameras >= max_cameras:
                return False, f"Kamera limiti aşıldı ({current_cameras}/{max_cameras} kamera)"
            
            # Aynı isimde kamera var mı kontrol et
            cursor.execute('''
                SELECT camera_id FROM cameras 
                WHERE company_id = ? AND camera_name = ? AND status = 'active'
            ''', (company_id, camera_data['camera_name']))
            
            existing_camera = cursor.fetchone()
            if existing_camera:
                return False, f"Bu isimde kamera zaten mevcut: {camera_data['camera_name']}"
            
            # Yeni kamera ekle
            camera_id = f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
            cursor.execute('''
                INSERT INTO cameras 
                (camera_id, company_id, camera_name, location, ip_address, rtsp_url, 
                 username, password, resolution, fps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                camera_id, company_id, camera_data['camera_name'], 
                camera_data['location'], camera_data.get('ip_address', ''),
                camera_data.get('rtsp_url', ''), camera_data.get('username', ''),
                camera_data.get('password', ''), camera_data.get('resolution', '1920x1080'),
                camera_data.get('fps', 25)
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Kamera eklendi: {camera_id}")
            return True, camera_id
            
        except sqlite3.IntegrityError as e:
            logger.error(f"❌ Kamera ekleme hatası (Duplicate): {e}")
            return False, "Kamera adı zaten mevcut"
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.error(f"❌ Kamera ekleme hatası (Database Locked): {e}")
                return False, "Veritabanı meşgul, lütfen tekrar deneyin"
            else:
                logger.error(f"❌ Kamera ekleme hatası: {e}")
                return False, str(e)
        except Exception as e:
            logger.error(f"❌ Kamera ekleme hatası: {e}")
            return False, str(e)
    
    def get_company_cameras(self, company_id: str) -> List[Dict]:
        """Şirket kameralarını getir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT camera_id, camera_name, location, ip_address, resolution, 
                       fps, status, last_detection, created_at
                FROM cameras
                WHERE company_id = ? AND status = 'active'
                ORDER BY created_at DESC
            ''', (company_id,))
            
            cameras = []
            for row in cursor.fetchall():
                cameras.append({
                    'camera_id': row[0],
                    'camera_name': row[1],
                    'location': row[2],
                    'ip_address': row[3],
                    'resolution': row[4],
                    'fps': row[5],
                    'status': row[6],
                    'last_detection': row[7],
                    'created_at': row[8]
                })
            
            conn.close()
            return cameras
            
        except Exception as e:
            logger.error(f"❌ Kamera listesi getirme hatası: {e}")
            return []
    
    def get_company_stats(self, company_id: str) -> Dict:
        """Enhanced şirket istatistikleri"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Bugünkü istatistikler
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_detections,
                    SUM(total_people) as total_people,
                    SUM(compliant_people) as compliant_people,
                    SUM(violation_people) as violation_people,
                    AVG(compliance_rate) as avg_compliance_rate
                FROM detections
                WHERE company_id = ? AND date(timestamp) = date('now')
            ''', (company_id,))
            
            detection_stats = cursor.fetchone()
            
            # Aktif kamera sayısı
            cursor.execute('''
                SELECT COUNT(*) FROM cameras WHERE company_id = ? AND status = 'active'
            ''', (company_id,))
            
            active_cameras = cursor.fetchone()[0]
            
            # Bugünkü ihlal sayısı
            cursor.execute('''
                SELECT COUNT(*) FROM violations 
                WHERE company_id = ? AND date(timestamp) = date('now')
            ''', (company_id,))
            
            today_violations = cursor.fetchone()[0]
            
            # Dünkü istatistikler (trend hesaplama için)
            cursor.execute('''
                SELECT COUNT(*) FROM violations 
                WHERE company_id = ? AND date(timestamp) = date('now', '-1 day')
            ''', (company_id,))
            
            yesterday_violations = cursor.fetchone()[0] or 0
            
            # Geçen haftaki kamera sayısı
            cursor.execute('''
                SELECT COUNT(*) FROM cameras 
                WHERE company_id = ? AND created_at < date('now', '-7 days')
            ''', (company_id,))
            
            last_week_cameras = cursor.fetchone()[0] or 0
            
            # Compliance trend (son 7 günün ortalaması)
            cursor.execute('''
                SELECT AVG(compliance_rate) 
                FROM detections 
                WHERE company_id = ? AND date(timestamp) > date('now', '-7 days')
            ''', (company_id,))
            
            week_compliance = cursor.fetchone()[0] or 0
            
            # Aktif çalışan sayısı (bugün tespit edilen unique kişi sayısı)
            cursor.execute('''
                SELECT COUNT(DISTINCT track_id) 
                FROM detections 
                WHERE company_id = ? AND date(timestamp) = date('now')
            ''', (company_id,))
            
            active_workers = cursor.fetchone()[0] or 0
            
            # Aylık ihlal sayısı
            cursor.execute('''
                SELECT COUNT(*) FROM violations 
                WHERE company_id = ? AND date(timestamp) > date('now', '-30 days')
            ''', (company_id,))
            
            monthly_violations = cursor.fetchone()[0] or 0
            
            conn.close()
            
            # Trend hesaplamaları
            cameras_trend = active_cameras - last_week_cameras
            violations_trend = today_violations - yesterday_violations
            current_compliance = detection_stats[4] or 0
            compliance_trend = current_compliance - week_compliance if week_compliance > 0 else 0
            
            return {
                'total_detections': detection_stats[0] or 0,
                'total_people': detection_stats[1] or 0,
                'compliant_people': detection_stats[2] or 0,
                'violation_people': detection_stats[3] or 0,
                'compliance_rate': current_compliance,
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