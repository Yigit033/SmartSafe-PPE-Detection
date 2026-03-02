#!/usr/bin/env python3
"""
Database Migration: Add resolution_snapshot_path column
Mevcut violation_events tablosuna resolution_snapshot_path kolonu ekler
"""

import sqlite3
import os
from datetime import datetime

def migrate_database(db_path='smartsafe_saas.db'):
    """Add resolution_snapshot_path column to violation_events table"""
    
    print("\n" + "="*70)
    print("🔄 DATABASE MIGRATION - Add Resolution Snapshot Path")
    print("="*70)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Database: {db_path}\n")
    
    if not os.path.exists(db_path):
        print(f"❌ Database bulunamadı: {db_path}")
        return False
    
    try:
        # Backup oluştur
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"💾 Backup oluşturuluyor: {backup_path}")
        
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup oluşturuldu!\n")
        
        # Database'e bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Mevcut kolonları kontrol et
        cursor.execute("PRAGMA table_info(violation_events)")
        columns = [col[1] for col in cursor.fetchall()]
        
        print("📋 Mevcut kolonlar:")
        for col in columns:
            print(f"   • {col}")
        
        # resolution_snapshot_path var mı kontrol et
        if 'resolution_snapshot_path' in columns:
            print("\n⚠️  resolution_snapshot_path kolonu zaten mevcut!")
            print("✅ Migration gerekli değil.")
            conn.close()
            return True
        
        print("\n🔄 resolution_snapshot_path kolonu ekleniyor...")
        
        # Yeni kolonu ekle
        cursor.execute("""
            ALTER TABLE violation_events 
            ADD COLUMN resolution_snapshot_path TEXT
        """)
        
        conn.commit()
        
        # Doğrulama
        cursor.execute("PRAGMA table_info(violation_events)")
        new_columns = [col[1] for col in cursor.fetchall()]
        
        if 'resolution_snapshot_path' in new_columns:
            print("✅ Kolon başarıyla eklendi!\n")
            
            print("📋 Yeni kolon listesi:")
            for col in new_columns:
                marker = "🆕" if col == 'resolution_snapshot_path' else "  "
                print(f"   {marker} {col}")
            
            # İstatistikler
            cursor.execute("SELECT COUNT(*) FROM violation_events")
            total_events = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM violation_events WHERE status = 'resolved'")
            resolved_events = cursor.fetchone()[0]
            
            print(f"\n📊 İstatistikler:")
            print(f"   • Toplam Event: {total_events}")
            print(f"   • Çözülmüş Event: {resolved_events}")
            print(f"   • Yeni snapshot'lar: {resolved_events} event için çekilecek")
            
            conn.close()
            
            print("\n" + "="*70)
            print("✅ MIGRATION BAŞARILI!")
            print("="*70)
            print("\n💡 Sonraki Adımlar:")
            print("   1. Sunucuyu yeniden başlatın: python smartsafe_saas_api.py")
            print("   2. Kamerayı açın ve ihlal oluşturun")
            print("   3. İhlal bittiğinde resolution snapshot çekilecek")
            print("   4. Kontrol edin: python check_violations.py")
            print("\n" + "="*70 + "\n")
            
            return True
        else:
            print("❌ Kolon eklenemedi!")
            conn.close()
            return False
            
    except Exception as e:
        print(f"\n❌ Migration hatası: {e}")
        print(f"💡 Backup'tan geri yükleyebilirsiniz: {backup_path}")
        return False


def rollback_migration(db_path='smartsafe_saas.db', backup_path=None):
    """Rollback migration using backup"""
    
    if not backup_path:
        # En son backup'ı bul
        import glob
        backups = glob.glob(f"{db_path}.backup_*")
        if not backups:
            print("❌ Backup bulunamadı!")
            return False
        backup_path = sorted(backups)[-1]
    
    print(f"\n🔄 Rollback yapılıyor...")
    print(f"📁 Backup: {backup_path}")
    
    try:
        import shutil
        shutil.copy2(backup_path, db_path)
        print("✅ Rollback başarılı!")
        return True
    except Exception as e:
        print(f"❌ Rollback hatası: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        # Rollback mode
        db_path = sys.argv[2] if len(sys.argv) > 2 else 'smartsafe_saas.db'
        backup_path = sys.argv[3] if len(sys.argv) > 3 else None
        rollback_migration(db_path, backup_path)
    else:
        # Normal migration
        db_path = sys.argv[1] if len(sys.argv) > 1 else 'smartsafe_saas.db'
        migrate_database(db_path)
