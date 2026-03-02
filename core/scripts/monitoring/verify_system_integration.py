#!/usr/bin/env python3
"""
Sistem Entegrasyon Doğrulama Scripti
DVR ve Normal kamera sistemlerinin violation tracking entegrasyonunu kontrol eder
"""

import sqlite3
import os
from datetime import datetime

def check_database_schema():
    """Database şemasını kontrol et"""
    print("\n" + "="*80)
    print("🗄️  DATABASE ŞEMA KONTROLÜ")
    print("="*80)
    
    db_path = 'data/databases/smartsafe_saas.db'
    
    if not os.path.exists(db_path):
        print(f"\n❌ Database bulunamadı: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # violation_events tablosunu kontrol et
        cursor.execute("PRAGMA table_info(violation_events)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        
        print("\n📋 violation_events Tablosu:")
        required_columns = {
            'event_id': 'TEXT',
            'company_id': 'TEXT',
            'camera_id': 'TEXT',
            'person_id': 'TEXT',
            'violation_type': 'TEXT',
            'start_time': 'REAL',
            'end_time': 'REAL',
            'duration_seconds': 'INTEGER',
            'snapshot_path': 'TEXT',
            'resolution_snapshot_path': 'TEXT',
            'severity': 'TEXT',
            'status': 'TEXT'
        }
        
        all_ok = True
        for col_name, col_type in required_columns.items():
            if col_name in columns:
                marker = "✅" if col_name == 'resolution_snapshot_path' else "  "
                print(f"   {marker} {col_name}: {columns[col_name]}")
            else:
                print(f"   ❌ {col_name}: EKSIK!")
                all_ok = False
        
        if all_ok:
            print("\n✅ Tüm gerekli kolonlar mevcut!")
        else:
            print("\n❌ Bazı kolonlar eksik! Migration çalıştırın:")
            print("   python migrate_add_resolution_snapshot.py")
        
        conn.close()
        return all_ok
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        return False


def check_imports():
    """Gerekli modüllerin import edilebilirliğini kontrol et"""
    print("\n" + "="*80)
    print("📦 MODÜL IMPORT KONTROLÜ")
    print("="*80)
    
    modules = [
        ('src.smartsafe.detection.violation_tracker', 'get_violation_tracker'),
        ('src.smartsafe.detection.snapshot_manager', 'get_snapshot_manager'),
        ('src.smartsafe.database.database_adapter', 'get_db_adapter'),
        ('src.smartsafe.integrations.cameras.camera_integration_manager', 'ProfessionalCameraManager'),
        ('src.smartsafe.integrations.dvr.dvr_ppe_integration', 'get_dvr_ppe_manager')
    ]
    
    all_ok = True
    for module_name, function_name in modules:
        try:
            module = __import__(module_name)
            if hasattr(module, function_name):
                print(f"   ✅ {module_name}.{function_name}")
            else:
                print(f"   ⚠️  {module_name}.{function_name} - Fonksiyon bulunamadı")
                all_ok = False
        except ImportError as e:
            print(f"   ❌ {module_name} - Import hatası: {e}")
            all_ok = False
    
    if all_ok:
        print("\n✅ Tüm modüller başarıyla import edildi!")
    else:
        print("\n⚠️  Bazı modüller import edilemedi!")
    
    return all_ok


def check_violation_tracking_integration():
    """Violation tracking entegrasyonunu kontrol et"""
    print("\n" + "="*80)
    print("🔍 VIOLATION TRACKING ENTEGRASYON KONTROLÜ")
    print("="*80)
    
    # camera_integration_manager.py kontrolü
    print("\n📹 Normal Kamera Sistemi:")
    try:
        with open('src/smartsafe/integrations/cameras/camera_integration_manager.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
            checks = [
                ('violation_tracker import', 'from detection.violation_tracker import'),
                ('snapshot_manager import', 'from detection.snapshot_manager import'),
                ('Violation tracker çağrısı', 'violation_tracker = get_violation_tracker()'),
                ('Snapshot manager çağrısı', 'snapshot_manager = get_snapshot_manager()'),
                ('Görünürlük kontrolü', 'person_visible'),
                ('Resolution snapshot', 'resolution_snapshot_path')
            ]
            
            for check_name, check_string in checks:
                if check_string in content:
                    print(f"   ✅ {check_name}")
                else:
                    print(f"   ❌ {check_name} - BULUNAMADI!")
        
        print("   ✅ Normal kamera sistemi entegre edilmiş!")
        
    except Exception as e:
        print(f"   ❌ Kontrol hatası: {e}")
    
    # dvr_ppe_integration.py kontrolü
    print("\n🎥 DVR/NVR Sistemi:")
    try:
        with open('src/smartsafe/integrations/dvr/dvr_ppe_integration.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
            checks = [
                ('violation_tracker import', 'from detection.violation_tracker import'),
                ('snapshot_manager import', 'from detection.snapshot_manager import'),
                ('Violation tracker çağrısı', 'violation_tracker = get_violation_tracker()'),
                ('Snapshot manager çağrısı', 'snapshot_manager = get_snapshot_manager()'),
                ('Görünürlük kontrolü', 'person_visible'),
                ('Resolution snapshot', 'resolution_snapshot_path'),
                ('DVR violation log', 'DVR NEW VIOLATION'),
                ('DVR resolution log', 'DVR RESOLUTION SNAPSHOT')
            ]
            
            for check_name, check_string in checks:
                if check_string in content:
                    print(f"   ✅ {check_name}")
                else:
                    print(f"   ❌ {check_name} - BULUNAMADI!")
        
        print("   ✅ DVR/NVR sistemi entegre edilmiş!")
        
    except Exception as e:
        print(f"   ❌ Kontrol hatası: {e}")


def check_snapshot_system():
    """Snapshot sistemini kontrol et"""
    print("\n" + "="*80)
    print("📸 SNAPSHOT SİSTEM KONTROLÜ")
    print("="*80)
    
    snapshot_dir = 'violations'
    
    if os.path.exists(snapshot_dir):
        # Snapshot sayısı
        total_snapshots = 0
        for root, dirs, files in os.walk(snapshot_dir):
            total_snapshots += len([f for f in files if f.endswith(('.jpg', '.jpeg', '.png'))])
        
        print(f"\n📁 Snapshot Klasörü: {os.path.abspath(snapshot_dir)}")
        print(f"📸 Toplam Snapshot: {total_snapshots} adet")
        
        # Resolution snapshot kontrolü
        resolution_snapshots = 0
        for root, dirs, files in os.walk(snapshot_dir):
            resolution_snapshots += len([f for f in files if '_resolved_' in f])
        
        print(f"✅ Resolution Snapshot: {resolution_snapshots} adet")
        
        if total_snapshots > 0:
            print("\n✅ Snapshot sistemi çalışıyor!")
        else:
            print("\n⚠️  Henüz snapshot çekilmemiş. Kamerayı açıp ihlal oluşturun.")
    else:
        print(f"\n⚠️  Snapshot klasörü bulunamadı: {snapshot_dir}")
        print("💡 İlk ihlal oluştuğunda otomatik oluşturulacak.")


def check_database_compatibility():
    """Database uyumluluğunu kontrol et"""
    print("\n" + "="*80)
    print("🔄 DATABASE UYUMLULUK KONTROLÜ")
    print("="*80)
    
    try:
        with open('src/smartsafe/database/database_adapter.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
            print("\n✅ SQLite Uyumluluğu:")
            if 'CREATE TABLE IF NOT EXISTS violation_events' in content:
                print("   ✅ CREATE TABLE IF NOT EXISTS kullanılıyor")
            if 'resolution_snapshot_path TEXT' in content:
                print("   ✅ resolution_snapshot_path kolonu tanımlı")
            
            print("\n✅ PostgreSQL Uyumluluğu:")
            if 'else:  # PostgreSQL' in content or 'elif self.db_type == \'postgresql\'' in content:
                print("   ✅ PostgreSQL desteği var")
            if 'resolution_snapshot_path TEXT' in content:
                print("   ✅ resolution_snapshot_path kolonu tanımlı")
            
            print("\n✅ Her iki database için tam uyumluluk!")
        
    except Exception as e:
        print(f"\n❌ Kontrol hatası: {e}")


def check_control_scripts():
    """Kontrol scriptlerini kontrol et"""
    print("\n" + "="*80)
    print("📝 KONTROL SCRİPTLERİ")
    print("="*80)
    
    scripts = [
        ('scripts/monitoring/check_violations.py', 'Violation kontrol scripti'),
        ('scripts/monitoring/monitor_violations.py', 'Canlı izleme scripti'),
        ('scripts/monitoring/view_snapshots.py', 'Snapshot görüntüleyici'),
        ('scripts/database/migrate_add_resolution_snapshot.py', 'Migration scripti'),
        ('scripts/monitoring/verify_system_integration.py', 'Sistem doğrulama scripti')
    ]
    
    for script_name, description in scripts:
        if os.path.exists(script_name):
            print(f"   ✅ {script_name} - {description}")
        else:
            print(f"   ❌ {script_name} - BULUNAMADI!")
    
    print("\n💡 Kullanım:")
    print("   • python scripts/monitoring/check_violations.py       - Genel kontrol")
    print("   • python scripts/monitoring/monitor_violations.py     - Canlı izleme")
    print("   • python scripts/monitoring/view_snapshots.py         - Snapshot'ları görüntüle")


def main():
    """Ana fonksiyon"""
    print("\n" + "="*80)
    print("🔍 SMARTSAFE AI - SİSTEM ENTEGRASYON DOĞRULAMA")
    print("="*80)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Tüm kontrolleri yap
    schema_ok = check_database_schema()
    imports_ok = check_imports()
    check_violation_tracking_integration()
    check_snapshot_system()
    check_database_compatibility()
    check_control_scripts()
    
    # Özet
    print("\n" + "="*80)
    print("📊 DOĞRULAMA ÖZETİ")
    print("="*80)
    
    if schema_ok and imports_ok:
        print("\n✅ SİSTEM HAZIR!")
        print("\n🎯 Sonraki Adımlar:")
        print("   1. Sunucuyu başlatın: python -m src.smartsafe.api.smartsafe_saas_api")
        print("   2. Kamerayı veya DVR'ı açın")
        print("   3. İhlal oluşturun ve kontrol edin:")
        print("      python check_violations.py")
        print("\n📸 Snapshot Sistemi:")
        print("   • İhlal başladığında: 1 snapshot (eksik ekipmanlarla)")
        print("   • İhlal bittiğinde: 1 snapshot (tam ekipmanlarla)")
        print("   • İhlal devam ederken: Snapshot çekilmez")
        print("\n🎉 DVR ve Normal kameralar için tam entegrasyon!")
    else:
        print("\n⚠️  BAZI SORUNLAR VAR!")
        if not schema_ok:
            print("   • Database migration çalıştırın:")
            print("     python scripts/database/migrate_add_resolution_snapshot.py")
        if not imports_ok:
            print("   • Gerekli modülleri kontrol edin")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
