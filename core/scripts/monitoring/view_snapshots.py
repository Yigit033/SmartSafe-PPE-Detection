#!/usr/bin/env python3
"""
SmartSafe AI - Snapshot Viewer
Violation snapshot'larını görüntüler
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

def view_snapshots_with_details(db_path='smartsafe_saas.db', snapshot_dir='violations'):
    """Snapshot'ları detaylı bilgilerle göster"""
    print("\n" + "="*80)
    print("📸 VIOLATION SNAPSHOT VIEWER")
    print("="*80)
    
    if not os.path.exists(snapshot_dir):
        print(f"\n⚠️  Snapshot klasörü bulunamadı: {snapshot_dir}")
        print("💡 İlk ihlal oluştuğunda klasör otomatik oluşturulacak.")
        return
    
    # Database'den snapshot bilgilerini al
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                event_id,
                company_id,
                camera_id,
                person_id,
                violation_type,
                datetime(start_time, 'unixepoch', 'localtime') as start_time,
                duration_seconds,
                snapshot_path,
                severity,
                status
            FROM violation_events
            WHERE snapshot_path IS NOT NULL
            ORDER BY start_time DESC
        """)
        
        events = cursor.fetchall()
        
        if not events:
            print("\n⚠️  Henüz snapshot'lı violation event yok!")
            print("💡 Kamerayı açıp ihlal oluşturun.")
            return
        
        print(f"\n📊 Toplam {len(events)} snapshot'lı violation event bulundu\n")
        
        # Snapshot'ları listele
        for i, event in enumerate(events, 1):
            event_id, company_id, camera_id, person_id, v_type, start_time, duration, snapshot_path, severity, status = event
            
            print("="*80)
            print(f"📸 SNAPSHOT #{i}")
            print("-"*80)
            print(f"Event ID      : {event_id}")
            print(f"Şirket        : {company_id}")
            print(f"Kamera        : {camera_id}")
            print(f"Kişi          : {person_id}")
            print(f"İhlal Türü    : {v_type}")
            print(f"Başlangıç     : {start_time}")
            
            if duration:
                duration_min = duration // 60
                duration_sec = duration % 60
                print(f"Süre          : {duration_min}dk {duration_sec}sn")
            
            print(f"Şiddet        : {severity}")
            print(f"Durum         : {status}")
            
            # Snapshot dosya kontrolü
            if snapshot_path:
                if os.path.exists(snapshot_path):
                    file_size = os.path.getsize(snapshot_path)
                    file_size_kb = file_size / 1024
                    print(f"Snapshot      : ✅ VAR ({file_size_kb:.1f} KB)")
                    print(f"Dosya Yolu    : {snapshot_path}")
                    
                    # Dosya zamanı
                    mtime = os.path.getmtime(snapshot_path)
                    mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    print(f"Kayıt Zamanı  : {mtime_str}")
                else:
                    print(f"Snapshot      : ❌ DOSYA BULUNAMADI!")
                    print(f"Aranan Yol    : {snapshot_path}")
            else:
                print(f"Snapshot      : ⚠️  Yol kaydedilmemiş")
            
            print()
        
        conn.close()
        
        # Klasör yapısını göster
        print("\n" + "="*80)
        print("📁 SNAPSHOT KLASÖR YAPISI")
        print("="*80 + "\n")
        
        for root, dirs, files in os.walk(snapshot_dir):
            level = root.replace(snapshot_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            folder_name = os.path.basename(root)
            
            if level == 0:
                print(f"📁 {snapshot_dir}/")
            else:
                print(f"{indent}📁 {folder_name}/")
            
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                if file.endswith(('.jpg', '.jpeg', '.png')):
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path) / 1024
                    print(f"{subindent}📸 {file} ({file_size:.1f} KB)")
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")


def show_snapshot_statistics(snapshot_dir='violations'):
    """Snapshot istatistiklerini göster"""
    print("\n" + "="*80)
    print("📊 SNAPSHOT İSTATİSTİKLERİ")
    print("="*80)
    
    if not os.path.exists(snapshot_dir):
        print(f"\n⚠️  Snapshot klasörü bulunamadı: {snapshot_dir}")
        return
    
    # Tüm snapshot'ları topla
    snapshots_by_company = {}
    snapshots_by_camera = {}
    snapshots_by_date = {}
    total_size = 0
    total_count = 0
    
    for root, dirs, files in os.walk(snapshot_dir):
        for file in files:
            if file.endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                file_size = os.path.getsize(full_path)
                total_size += file_size
                total_count += 1
                
                # Klasör yapısından bilgi çıkar: violations/COMP_XXX/CAM_XXX/2025-01-01/
                parts = root.split(os.sep)
                if len(parts) >= 4:
                    company = parts[1]
                    camera = parts[2]
                    date = parts[3]
                    
                    snapshots_by_company[company] = snapshots_by_company.get(company, 0) + 1
                    snapshots_by_camera[camera] = snapshots_by_camera.get(camera, 0) + 1
                    snapshots_by_date[date] = snapshots_by_date.get(date, 0) + 1
    
    print(f"\n📸 Toplam Snapshot: {total_count} adet")
    print(f"💾 Toplam Boyut: {total_size / (1024*1024):.2f} MB")
    print(f"📏 Ortalama Boyut: {(total_size / total_count / 1024):.1f} KB" if total_count > 0 else "")
    
    if snapshots_by_company:
        print("\n\n🏢 ŞİRKET BAZINDA DAĞILIM:")
        print("-"*80)
        for company, count in sorted(snapshots_by_company.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_count) * 100
            bar = "█" * int(percentage / 2)
            print(f"   {company}: {count:4d} adet [{bar:<50}] {percentage:.1f}%")
    
    if snapshots_by_camera:
        print("\n\n📷 KAMERA BAZINDA DAĞILIM:")
        print("-"*80)
        for camera, count in sorted(snapshots_by_camera.items(), key=lambda x: x[1], reverse=True)[:10]:
            percentage = (count / total_count) * 100
            bar = "█" * int(percentage / 2)
            print(f"   {camera}: {count:4d} adet [{bar:<50}] {percentage:.1f}%")
    
    if snapshots_by_date:
        print("\n\n📅 TARİH BAZINDA DAĞILIM:")
        print("-"*80)
        for date, count in sorted(snapshots_by_date.items(), reverse=True)[:10]:
            percentage = (count / total_count) * 100
            bar = "█" * int(percentage / 2)
            print(f"   {date}: {count:4d} adet [{bar:<50}] {percentage:.1f}%")


def open_snapshot_folder():
    """Snapshot klasörünü dosya gezgininde aç"""
    snapshot_dir = 'violations'
    
    if not os.path.exists(snapshot_dir):
        print(f"\n⚠️  Snapshot klasörü bulunamadı: {snapshot_dir}")
        return
    
    abs_path = os.path.abspath(snapshot_dir)
    
    print(f"\n📁 Snapshot klasörü açılıyor...")
    print(f"   {abs_path}")
    
    try:
        if os.name == 'nt':  # Windows
            os.startfile(abs_path)
        elif os.name == 'posix':  # Linux/Mac
            os.system(f'xdg-open "{abs_path}"')
        
        print("✅ Klasör açıldı!")
    except Exception as e:
        print(f"❌ Klasör açılamadı: {e}")
        print(f"💡 Manuel olarak açın: {abs_path}")


def main():
    """Ana fonksiyon"""
    print("\n" + "="*80)
    print("🔍 SMARTSAFE AI - SNAPSHOT VIEWER")
    print("="*80)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Tüm kontrolleri yap
    view_snapshots_with_details()
    show_snapshot_statistics()
    
    print("\n" + "="*80)
    print("✅ GÖRÜNTÜLEME TAMAMLANDI!")
    print("="*80)
    
    # Klasörü aç
    response = input("\n📁 Snapshot klasörünü açmak ister misiniz? (e/h): ")
    if response.lower() in ['e', 'evet', 'y', 'yes']:
        open_snapshot_folder()
    
    print("\n💡 İPUCU:")
    print("   • Snapshot'lar violations/ klasöründe saklanır")
    print("   • Yapı: violations/COMP_XXX/CAM_XXX/YYYY-MM-DD/")
    print("   • Her snapshot violation event ile ilişkilidir")
    print("\n📝 KOMUT: python view_snapshots.py")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
