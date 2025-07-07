#!/usr/bin/env python3
"""
SmartSafe AI - Sektörel Yönetim Sistemi
Farklı sektörler için genişletilebilir PPE detection sistemi
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class SectorConfig:
    """Sektör konfigürasyon veri modeli"""
    sector_id: str
    sector_name: str
    mandatory_ppe: Dict[str, Dict]
    optional_ppe: Dict[str, Dict]
    detection_settings: Dict
    penalty_settings: Dict
    compliance_requirements: Dict

class BaseSectorDetector(ABC):
    """Sektörel detector için temel sınıf"""
    
    def __init__(self, config: SectorConfig):
        self.config = config
        self.db_path = f"{config.sector_id}_safety.db"
        self.setup_database()
    
    @abstractmethod
    def setup_database(self):
        """Sektöre özel veritabanı kurulumu"""
        pass
    
    @abstractmethod
    def analyze_sector_compliance(self, detections: List[Dict]) -> Dict:
        """Sektöre özel uygunluk analizi"""
        pass

class SmartSafeSectorManager:
    """Tüm sektörleri yöneten ana sistem"""
    
    # Desteklenen sektörler ve konfigürasyonları
    SECTOR_CONFIGS = {
        'construction': {
            'sector_name': 'İnşaat Sektörü',
            'mandatory_ppe': {
                'helmet': {
                    'name': 'Baret/Kask',
                    'critical': True,
                    'penalty_per_violation': 100.0,
                    'detection_classes': ['helmet'],
                    'priority': 1
                },
                'safety_vest': {
                    'name': 'Güvenlik Yeleği',
                    'critical': True,
                    'penalty_per_violation': 75.0,
                    'detection_classes': ['safety_vest', 'safety_suit'],
                    'priority': 2
                },
                'safety_shoes': {
                    'name': 'Güvenlik Ayakkabısı',
                    'critical': True,
                    'penalty_per_violation': 50.0,
                    'detection_classes': ['shoes'],
                    'priority': 3
                }
            },
            'optional_ppe': {
                'gloves': {'name': 'Güvenlik Eldiveni', 'bonus_points': 10},
                'glasses': {'name': 'Güvenlik Gözlüğü', 'bonus_points': 15}
            },
            'detection_settings': {
                'confidence_threshold': 0.6,
                'detection_interval': 3,
                'violation_cooldown': 300
            },
            'penalty_settings': {
                'max_penalty_per_day': 500.0,
                'warning_before_penalty': 2,
                'escalation_factor': 1.5
            },
            'compliance_requirements': {
                'minimum_compliance_rate': 85.0,
                'critical_ppe_tolerance': 0,
                'reporting_frequency': 'daily'
            }
        },
        
        'chemical': {
            'sector_name': 'Kimya Sektörü',
            'mandatory_ppe': {
                'gloves': {
                    'name': 'Kimyasal Eldiven',
                    'critical': True,
                    'penalty_per_violation': 200.0,
                    'detection_classes': ['gloves'],
                    'priority': 1
                },
                'glasses': {
                    'name': 'Güvenlik Gözlüğü',
                    'critical': True,
                    'penalty_per_violation': 150.0,
                    'detection_classes': ['glasses'],
                    'priority': 1
                },
                'face_mask': {
                    'name': 'Solunum Maskesi',
                    'critical': True,
                    'penalty_per_violation': 300.0,
                    'detection_classes': ['face_mask_medical'],
                    'priority': 1
                },
                'safety_suit': {
                    'name': 'Kimyasal Tulum',
                    'critical': True,
                    'penalty_per_violation': 250.0,
                    'detection_classes': ['safety_suit'],
                    'priority': 2
                }
            },
            'optional_ppe': {
                'helmet': {'name': 'Baret', 'bonus_points': 10},
                'safety_shoes': {'name': 'Güvenlik Ayakkabısı', 'bonus_points': 15}
            },
            'detection_settings': {
                'confidence_threshold': 0.7,
                'detection_interval': 2,
                'violation_cooldown': 180
            },
            'penalty_settings': {
                'max_penalty_per_day': 1000.0,
                'warning_before_penalty': 1,
                'escalation_factor': 2.0
            },
            'compliance_requirements': {
                'minimum_compliance_rate': 95.0,
                'critical_ppe_tolerance': 0,
                'reporting_frequency': 'hourly'
            }
        },
        
        'food': {
            'sector_name': 'Gıda Sektörü',
            'mandatory_ppe': {
                'hairnet': {
                    'name': 'Bone/Başlık',
                    'critical': True,
                    'penalty_per_violation': 50.0,
                    'detection_classes': ['hairnet'],
                    'priority': 1
                },
                'face_mask': {
                    'name': 'Hijyen Maskesi',
                    'critical': True,
                    'penalty_per_violation': 30.0,
                    'detection_classes': ['face_mask_medical'],
                    'priority': 1
                },
                'apron': {
                    'name': 'Hijyen Önlüğü',
                    'critical': True,
                    'penalty_per_violation': 40.0,
                    'detection_classes': ['apron'],
                    'priority': 2
                }
            },
            'optional_ppe': {
                'gloves': {'name': 'Hijyen Eldiveni', 'bonus_points': 15},
                'safety_shoes': {'name': 'Kaymaz Ayakkabı', 'bonus_points': 10}
            },
            'detection_settings': {
                'confidence_threshold': 0.65,
                'detection_interval': 5,
                'violation_cooldown': 600
            },
            'penalty_settings': {
                'max_penalty_per_day': 200.0,
                'warning_before_penalty': 3,
                'escalation_factor': 1.2
            },
            'compliance_requirements': {
                'minimum_compliance_rate': 90.0,
                'critical_ppe_tolerance': 1,
                'reporting_frequency': 'daily'
            }
        },
        
        'manufacturing': {
            'sector_name': 'İmalat Sektörü',
            'mandatory_ppe': {
                'helmet': {
                    'name': 'Endüstriyel Kask',
                    'critical': True,
                    'penalty_per_violation': 80.0,
                    'detection_classes': ['helmet'],
                    'priority': 1
                },
                'safety_vest': {
                    'name': 'Reflektörlü Yelek',
                    'critical': True,
                    'penalty_per_violation': 60.0,
                    'detection_classes': ['safety_vest'],
                    'priority': 2
                },
                'gloves': {
                    'name': 'İş Eldiveni',
                    'critical': True,
                    'penalty_per_violation': 40.0,
                    'detection_classes': ['gloves'],
                    'priority': 2
                },
                'safety_shoes': {
                    'name': 'Çelik Burunlu Ayakkabı',
                    'critical': True,
                    'penalty_per_violation': 50.0,
                    'detection_classes': ['shoes'],
                    'priority': 3
                }
            },
            'optional_ppe': {
                'glasses': {'name': 'Koruyucu Gözlük', 'bonus_points': 10},
                'earmuffs': {'name': 'Kulak Koruyucu', 'bonus_points': 15}
            },
            'detection_settings': {
                'confidence_threshold': 0.65,
                'detection_interval': 4,
                'violation_cooldown': 240
            },
            'penalty_settings': {
                'max_penalty_per_day': 400.0,
                'warning_before_penalty': 2,
                'escalation_factor': 1.3
            },
            'compliance_requirements': {
                'minimum_compliance_rate': 88.0,
                'critical_ppe_tolerance': 0,
                'reporting_frequency': 'daily'
            }
        },
        
        'warehouse': {
            'sector_name': 'Depo/Lojistik',
            'mandatory_ppe': {
                'helmet': {
                    'name': 'Koruyucu Kask',
                    'critical': False,
                    'penalty_per_violation': 30.0,
                    'detection_classes': ['helmet'],
                    'priority': 2
                },
                'safety_vest': {
                    'name': 'Görünürlük Yeleği',
                    'critical': True,
                    'penalty_per_violation': 50.0,
                    'detection_classes': ['safety_vest'],
                    'priority': 1
                },
                'safety_shoes': {
                    'name': 'Güvenlik Ayakkabısı',
                    'critical': True,
                    'penalty_per_violation': 40.0,
                    'detection_classes': ['shoes'],
                    'priority': 1
                }
            },
            'optional_ppe': {
                'gloves': {'name': 'İş Eldiveni', 'bonus_points': 5}
            },
            'detection_settings': {
                'confidence_threshold': 0.6,
                'detection_interval': 6,
                'violation_cooldown': 300
            },
            'penalty_settings': {
                'max_penalty_per_day': 150.0,
                'warning_before_penalty': 3,
                'escalation_factor': 1.1
            },
            'compliance_requirements': {
                'minimum_compliance_rate': 75.0,
                'critical_ppe_tolerance': 1,
                'reporting_frequency': 'daily'
            }
        }
    }
    
    def __init__(self):
        self.active_sectors = {}
        self.master_db = "smartsafe_master.db"
        self.setup_master_database()
    
    def setup_master_database(self):
        """Ana yönetim veritabanını kur"""
        conn = sqlite3.connect(self.master_db)
        cursor = conn.cursor()
        
        # Şirketler tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                company_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                sector_id TEXT NOT NULL,
                contract_start_date TEXT,
                contract_end_date TEXT,
                total_cameras INTEGER DEFAULT 0,
                monthly_fee REAL DEFAULT 0.0,
                status TEXT DEFAULT 'active',
                created_date TEXT
            )
        ''')
        
        # Sektörel performans tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sector_performance (
                date TEXT,
                sector_id TEXT,
                total_companies INTEGER,
                total_detections INTEGER,
                total_violations INTEGER,
                total_penalties REAL,
                avg_compliance_rate REAL,
                PRIMARY KEY (date, sector_id)
            )
        ''')
        
        # Demo şirketleri ekle
        demo_companies = [
            ('COMP001', 'ABC İnşaat Ltd.', 'construction', '2024-01-01', '2024-12-31', 5, 2500.0),
            ('COMP002', 'XYZ Kimya A.Ş.', 'chemical', '2024-02-01', '2025-01-31', 8, 4000.0),
            ('COMP003', 'DEF Gıda San.', 'food', '2024-03-01', '2024-12-31', 3, 1500.0),
        ]
        
        for company_data in demo_companies:
            cursor.execute('''
                INSERT OR IGNORE INTO companies 
                (company_id, company_name, sector_id, contract_start_date, 
                 contract_end_date, total_cameras, monthly_fee, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (*company_data, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info("✅ Ana yönetim veritabanı kuruldu")
    
    def get_sector_config(self, sector_id: str) -> Optional[SectorConfig]:
        """Sektör konfigürasyonunu getir"""
        if sector_id in self.SECTOR_CONFIGS:
            config_data = self.SECTOR_CONFIGS[sector_id].copy()
            return SectorConfig(
                sector_id=sector_id,
                **config_data
            )
        return None
    
    def list_available_sectors(self) -> Dict[str, str]:
        """Mevcut sektörleri listele"""
        return {
            sector_id: config['sector_name'] 
            for sector_id, config in self.SECTOR_CONFIGS.items()
        }
    
    def register_company(self, company_name: str, sector_id: str, camera_count: int) -> Dict:
        """Yeni şirket kaydet"""
        if sector_id not in self.SECTOR_CONFIGS:
            return {'success': False, 'error': 'Geçersiz sektör'}
        
        # Şirket ID oluştur
        company_id = f"COMP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Aylık ücret hesapla (kamera başına sektörel fiyat)
        sector_pricing = {
            'construction': 500,
            'chemical': 800,
            'food': 400,
            'manufacturing': 600,
            'warehouse': 350
        }
        monthly_fee = camera_count * sector_pricing.get(sector_id, 500)
        
        try:
            conn = sqlite3.connect(self.master_db)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO companies 
                (company_id, company_name, sector_id, contract_start_date, 
                 contract_end_date, total_cameras, monthly_fee, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                company_id, company_name, sector_id,
                datetime.now().date().isoformat(),
                (datetime.now().replace(year=datetime.now().year + 1)).date().isoformat(),
                camera_count, monthly_fee, datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'company_id': company_id,
                'monthly_fee': monthly_fee,
                'sector_name': self.SECTOR_CONFIGS[sector_id]['sector_name']
            }
            
        except Exception as e:
            logger.error(f"Şirket kayıt hatası: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_sector_dashboard_data(self, sector_id: str) -> Dict:
        """Sektörel dashboard verisi"""
        config = self.get_sector_config(sector_id)
        if not config:
            return {}
        
        # Şirket sayısı
        conn = sqlite3.connect(self.master_db)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*), SUM(total_cameras), SUM(monthly_fee)
            FROM companies WHERE sector_id = ? AND status = 'active'
        ''', (sector_id,))
        
        result = cursor.fetchone()
        company_count = result[0] or 0
        total_cameras = result[1] or 0
        total_revenue = result[2] or 0.0
        
        conn.close()
        
        return {
            'sector_id': sector_id,
            'sector_name': config.sector_name,
            'total_companies': company_count,
            'total_cameras': total_cameras,
            'monthly_revenue': total_revenue,
            'mandatory_ppe_count': len(config.mandatory_ppe),
            'optional_ppe_count': len(config.optional_ppe),
            'avg_penalty_per_violation': sum(
                ppe['penalty_per_violation'] 
                for ppe in config.mandatory_ppe.values()
            ) / len(config.mandatory_ppe) if config.mandatory_ppe else 0,
            'compliance_requirements': config.compliance_requirements,
            'detection_settings': config.detection_settings
        }
    
    def generate_multi_sector_report(self) -> Dict:
        """Çok sektörlü genel rapor"""
        total_companies = 0
        total_cameras = 0
        total_revenue = 0.0
        sector_breakdown = {}
        
        for sector_id in self.SECTOR_CONFIGS.keys():
            sector_data = self.get_sector_dashboard_data(sector_id)
            
            total_companies += sector_data['total_companies']
            total_cameras += sector_data['total_cameras']
            total_revenue += sector_data['monthly_revenue']
            
            sector_breakdown[sector_id] = {
                'name': sector_data['sector_name'],
                'companies': sector_data['total_companies'],
                'cameras': sector_data['total_cameras'],
                'revenue': sector_data['monthly_revenue']
            }
        
        return {
            'report_date': datetime.now().isoformat(),
            'total_companies': total_companies,
            'total_cameras': total_cameras,
            'total_monthly_revenue': total_revenue,
            'active_sectors': len([s for s in sector_breakdown.values() if s['companies'] > 0]),
            'sector_breakdown': sector_breakdown,
            'top_sector_by_revenue': max(
                sector_breakdown.items(),
                key=lambda x: x[1]['revenue'],
                default=('none', {'revenue': 0})
            )[0] if sector_breakdown else None
        }

def main():
    """Sektörel yönetim sistemi demo"""
    print("🏭 SmartSafe AI - Sektörel Yönetim Sistemi")
    print("=" * 60)
    
    # Sektör yöneticisi
    sector_manager = SmartSafeSectorManager()
    
    # Mevcut sektörler
    print("\n📋 Desteklenen Sektörler:")
    sectors = sector_manager.list_available_sectors()
    for sector_id, sector_name in sectors.items():
        print(f"  {sector_id}: {sector_name}")
    
    # Sektörel detaylar
    print(f"\n🔍 Sektörel Konfigürasyon Detayları:")
    for sector_id in ['construction', 'chemical', 'food']:
        dashboard_data = sector_manager.get_sector_dashboard_data(sector_id)
        print(f"\n  📊 {dashboard_data['sector_name']}:")
        print(f"    - Şirket Sayısı: {dashboard_data['total_companies']}")
        print(f"    - Kamera Sayısı: {dashboard_data['total_cameras']}")
        print(f"    - Aylık Gelir: {dashboard_data['monthly_revenue']:.0f} TL")
        print(f"    - Zorunlu PPE: {dashboard_data['mandatory_ppe_count']} adet")
        print(f"    - Min. Uyum Oranı: {dashboard_data['compliance_requirements']['minimum_compliance_rate']}%")
        print(f"    - Ortalama Ceza: {dashboard_data['avg_penalty_per_violation']:.0f} TL")
    
    # Genel rapor
    print(f"\n📈 Genel Sistem Raporu:")
    general_report = sector_manager.generate_multi_sector_report()
    print(f"  📊 Toplam Şirket: {general_report['total_companies']}")
    print(f"  🎥 Toplam Kamera: {general_report['total_cameras']}")
    print(f"  💰 Aylık Toplam Gelir: {general_report['total_monthly_revenue']:.0f} TL")
    print(f"  🏭 Aktif Sektör: {general_report['active_sectors']}")
    print(f"  🏆 En Karlı Sektör: {general_report['top_sector_by_revenue']}")
    
    # Yeni şirket kayıt demo
    print(f"\n🏢 Yeni Şirket Kayıt Testi:")
    registration = sector_manager.register_company(
        company_name="Test Maden Ltd.",
        sector_id="manufacturing",
        camera_count=6
    )
    
    if registration['success']:
        print(f"  ✅ Şirket kaydedildi: {registration['company_id']}")
        print(f"  💰 Aylık Ücret: {registration['monthly_fee']} TL")
        print(f"  🏭 Sektör: {registration['sector_name']}")

if __name__ == "__main__":
    main() 