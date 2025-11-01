#!/usr/bin/env python3
"""
SmartSafe AI - Violation Tracking Doğrulama Scripti
Violation events, snapshots ve istatistikleri kontrol eder
"""

import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path

def check_violation_events(db_path='smartsafe_saas.db'):
    """Violation events tablosunu kontrol et"""
    print("\n" + "="*60)
    print("🚨 VIOLATION EVENTS KONTROLÜ")
    print("="*60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Toplam event sayısı
        cursor.execute("SELECT COUNT(*) FROM violation_events")
        total_events = cursor.fetchone()[0]
        print(f"\n📊 Toplam Violation Event: {total_events}")
        
        if total_events == 0:
            print("⚠️  Henüz hiç violation event kaydedilmemiş!")
            print("💡 Kamerayı açıp ihlal oluştuğunda kayıt yapılacak.")
            return
        
        # Aktif ihlaller
        cursor.execute("SELECT COUNT(*) FROM violation_events WHERE status = 'active'")
        active_count = cursor.fetchone()[0]
        print(f"🔴 Aktif İhlaller: {active_count}")
        
        # Çözülmüş ihlaller
        cursor.execute("SELECT COUNT(*) FROM violation_events WHERE status = 'resolved'")
        resolved_count = cursor.fetchone()[0]
        print(f"✅ Çözülmüş İhlaller: {resolved_count}")
        
        # Son 10 violation event
        print("\n📋 SON 10 VIOLATION EVENT:")
        print("-" * 60)
        
        cursor.execute("""
            SELECT 
                event_id,
                camera_id,
                person_id,
                violation_type,
                status,
                datetime(start_time, 'unixepoch', 'localtime') as start_time,
                duration_seconds,
                snapshot_path,
                resolution_snapshot_path
            FROM violation_events
            ORDER BY start_time DESC
            LIMIT 10
        """)
        
        events = cursor.fetchall()
        for i, event in enumerate(events, 1):
            event_id, camera_id, person_id, v_type, status, start_time, duration, snapshot, resolution_snapshot = event
            
            print(f"\n{i}. Event ID: {event_id[:16]}...")
            print(f"   📷 Kamera: {camera_id}")
            print(f"   👤 Kişi: {person_id[:16]}...")
            print(f"   ⚠️  İhlal: {v_type}")
            print(f"   📊 Durum: {status}")
            print(f"   🕐 Başlangıç: {start_time}")
            if duration:
                print(f"   ⏱️  Süre: {duration} saniye ({duration//60} dk {duration%60} sn)")
            if snapshot:
                snapshot_exists = "✅ VAR" if os.path.exists(snapshot) else "❌ YOK"
                print(f"   📸 İhlal Snapshot: {snapshot_exists}")
                if os.path.exists(snapshot):
                    print(f"       {snapshot}")
            if resolution_snapshot:
                resolution_exists = "✅ VAR" if os.path.exists(resolution_snapshot) else "❌ YOK"
                print(f"   ✅ Çözüm Snapshot: {resolution_exists}")
                if os.path.exists(resolution_snapshot):
                    print(f"       {resolution_snapshot}")
        
        # İhlal türlerine göre dağılım
        print("\n\n📊 İHLAL TÜRLERİNE GÖRE DAĞILIM:")
        print("-" * 60)
        cursor.execute("""
            SELECT 
                violation_type,
                COUNT(*) as count,
                AVG(duration_seconds) as avg_duration
            FROM violation_events
            WHERE duration_seconds IS NOT NULL
            GROUP BY violation_type
            ORDER BY count DESC
        """)
        
        for v_type, count, avg_dur in cursor.fetchall():
            avg_min = int(avg_dur // 60) if avg_dur else 0
            avg_sec = int(avg_dur % 60) if avg_dur else 0
            print(f"   • {v_type}: {count} adet (Ort. süre: {avg_min}dk {avg_sec}sn)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Hata: {e}")


def check_person_violations(db_path='smartsafe_saas.db'):
    """Person violations tablosunu kontrol et"""
    print("\n" + "="*60)
    print("👥 PERSON VIOLATIONS KONTROLÜ (Aylık İstatistikler)")
    print("="*60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Toplam kayıt sayısı
        cursor.execute("SELECT COUNT(*) FROM person_violations")
        total_records = cursor.fetchone()[0]
        print(f"\n📊 Toplam Kişi-İhlal Kaydı: {total_records}")
        
        if total_records == 0:
            print("⚠️  Henüz hiç person violation kaydedilmemiş!")
            print("💡 İhlaller çözüldüğünde bu tablo güncellenecek.")
            return
        
        # Bu ayki istatistikler
        current_month = datetime.now().strftime('%Y-%m')
        print(f"\n📅 BU AY ({current_month}) İSTATİSTİKLERİ:")
        print("-" * 60)
        
        cursor.execute("""
            SELECT 
                person_id,
                violation_type,
                violation_count,
                total_duration_seconds,
                penalty_amount,
                last_violation_date
            FROM person_violations
            WHERE month = ?
            ORDER BY violation_count DESC
            LIMIT 10
        """, (current_month,))
        
        records = cursor.fetchall()
        if not records:
            print("⚠️  Bu ay henüz ihlal kaydı yok.")
        else:
            for i, (person_id, v_type, count, duration, penalty, last_date) in enumerate(records, 1):
                duration_min = duration // 60 if duration else 0
                duration_sec = duration % 60 if duration else 0
                print(f"\n{i}. Kişi: {person_id[:16]}...")
                print(f"   ⚠️  İhlal: {v_type}")
                print(f"   🔢 Sayı: {count} kez")
                print(f"   ⏱️  Toplam Süre: {duration_min}dk {duration_sec}sn")
                if penalty:
                    print(f"   💰 Ceza: {penalty:.2f} TL")
                print(f"   📅 Son İhlal: {last_date}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Hata: {e}")


def check_snapshots(base_path='violations'):
    """Snapshot dosyalarını kontrol et"""
    print("\n" + "="*60)
    print("📸 SNAPSHOT DOSYALARI KONTROLÜ")
    print("="*60)
    
    if not os.path.exists(base_path):
        print(f"\n⚠️  Snapshot klasörü bulunamadı: {base_path}")
        print("💡 İlk ihlal oluştuğunda klasör otomatik oluşturulacak.")
        return
    
    # Tüm snapshot'ları bul
    snapshot_files = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                size = os.path.getsize(full_path)
                mtime = os.path.getmtime(full_path)
                snapshot_files.append((full_path, size, mtime))
    
    if not snapshot_files:
        print(f"\n⚠️  {base_path} klasöründe snapshot bulunamadı!")
        print("💡 İhlal oluştuğunda snapshot'lar buraya kaydedilecek.")
        return
    
    # Snapshot istatistikleri
    total_size = sum(s[1] for s in snapshot_files)
    print(f"\n📊 Toplam Snapshot: {len(snapshot_files)} adet")
    print(f"💾 Toplam Boyut: {total_size / (1024*1024):.2f} MB")
    print(f"📁 Klasör: {os.path.abspath(base_path)}")
    
    # Son 10 snapshot
    print("\n📋 SON 10 SNAPSHOT:")
    print("-" * 60)
    
    snapshot_files.sort(key=lambda x: x[2], reverse=True)  # Zamana göre sırala
    
    for i, (path, size, mtime) in enumerate(snapshot_files[:10], 1):
        rel_path = os.path.relpath(path, base_path)
        time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        size_kb = size / 1024
        print(f"\n{i}. {rel_path}")
        print(f"   📅 Tarih: {time_str}")
        print(f"   💾 Boyut: {size_kb:.1f} KB")
    
    # Şirket bazında dağılım
    print("\n\n📊 ŞİRKET BAZINDA SNAPSHOT DAĞILIMI:")
    print("-" * 60)
    
    company_counts = {}
    for path, _, _ in snapshot_files:
        parts = path.split(os.sep)
        if len(parts) >= 2:
            company = parts[1]  # violations/COMP_XXX/...
            company_counts[company] = company_counts.get(company, 0) + 1
    
    for company, count in sorted(company_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {company}: {count} snapshot")


def check_database_tables(db_path='smartsafe_saas.db'):
    """Database tablolarını kontrol et"""
    print("\n" + "="*60)
    print("🗄️  DATABASE TABLO KONTROLÜ")
    print("="*60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Tüm tabloları listele
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        print(f"\n📋 Toplam {len(tables)} tablo bulundu:")
        
        # Violation tracking tabloları
        violation_tables = ['violation_events', 'person_violations', 'monthly_penalties']
        
        for table_name, in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            if table_name in violation_tables:
                status = "✅" if count > 0 else "⚠️ "
                print(f"   {status} {table_name}: {count} kayıt")
            else:
                print(f"   • {table_name}: {count} kayıt")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Hata: {e}")


def main():
    """Ana kontrol fonksiyonu"""
    print("\n" + "="*60)
    print("🔍 SMARTSAFE AI - VIOLATION TRACKING SİSTEM KONTROLÜ")
    print("="*60)
    print(f"⏰ Kontrol Zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    db_path = 'smartsafe_saas.db'
    
    if not os.path.exists(db_path):
        print(f"\n❌ Veritabanı bulunamadı: {db_path}")
        print("💡 Önce sunucuyu başlatın: python smartsafe_saas_api.py")
        return
    
    # Tüm kontrolleri yap
    check_database_tables(db_path)
    check_violation_events(db_path)
    check_person_violations(db_path)
    check_snapshots('violations')
    
    print("\n" + "="*60)
    print("✅ KONTROL TAMAMLANDI!")
    print("="*60)
    print("\n💡 İPUCU:")
    print("   • Kamerayı açıp ihlal oluşturun")
    print("   • Bu scripti tekrar çalıştırın")
    print("   • Violation events ve snapshot'ları göreceksiniz")
    print("\n📝 KOMUT: python check_violations.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
