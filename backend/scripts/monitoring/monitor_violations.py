#!/usr/bin/env python3
"""
SmartSafe AI - Real-time Violation Monitoring
Violation events'leri canlı olarak izler
"""

import sqlite3
import time
import os
from datetime import datetime

def monitor_violations(db_path='smartsafe_saas.db', interval=5):
    """Violation events'leri canlı izle"""
    print("\n" + "="*70)
    print("🔴 CANLI VIOLATION MONITORING - Her {} saniyede güncellenir".format(interval))
    print("="*70)
    print("💡 Kamerayı açın ve ihlal oluşturun, burada canlı göreceksiniz!")
    print("⏹️  Durdurmak için: CTRL+C")
    print("="*70 + "\n")
    
    last_event_count = 0
    last_snapshot_count = 0
    
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("🔴 CANLI VIOLATION MONITORING")
            print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*70)
            
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Toplam event sayısı
                cursor.execute("SELECT COUNT(*) FROM violation_events")
                total_events = cursor.fetchone()[0]
                
                # Aktif ihlaller
                cursor.execute("SELECT COUNT(*) FROM violation_events WHERE status = 'active'")
                active_count = cursor.fetchone()[0]
                
                # Çözülmüş ihlaller
                cursor.execute("SELECT COUNT(*) FROM violation_events WHERE status = 'resolved'")
                resolved_count = cursor.fetchone()[0]
                
                # Yeni event var mı?
                if total_events > last_event_count:
                    new_count = total_events - last_event_count
                    print(f"\n🆕 YENİ EVENT! +{new_count} violation event eklendi!")
                    last_event_count = total_events
                
                print(f"\n📊 GENEL İSTATİSTİKLER:")
                print(f"   • Toplam Event: {total_events}")
                print(f"   • 🔴 Aktif: {active_count}")
                print(f"   • ✅ Çözülmüş: {resolved_count}")
                
                # Son 5 aktif ihlal
                if active_count > 0:
                    print(f"\n🔴 AKTİF İHLALLER ({active_count} adet):")
                    print("-" * 70)
                    
                    cursor.execute("""
                        SELECT 
                            event_id,
                            camera_id,
                            violation_type,
                            datetime(start_time, 'unixepoch', 'localtime') as start_time,
                            (strftime('%s', 'now') - start_time) as duration_now
                        FROM violation_events
                        WHERE status = 'active'
                        ORDER BY start_time DESC
                        LIMIT 5
                    """)
                    
                    for event_id, camera_id, v_type, start_time, duration in cursor.fetchall():
                        duration_min = int(duration // 60)
                        duration_sec = int(duration % 60)
                        print(f"   🚨 {v_type}")
                        print(f"      Event: {event_id[:20]}...")
                        print(f"      Kamera: {camera_id}")
                        print(f"      Başlangıç: {start_time}")
                        print(f"      Süre: {duration_min}dk {duration_sec}sn")
                        print()
                
                # Son 5 çözülmüş ihlal
                if resolved_count > 0:
                    print(f"\n✅ SON ÇÖZÜLMÜŞ İHLALLER:")
                    print("-" * 70)
                    
                    cursor.execute("""
                        SELECT 
                            event_id,
                            camera_id,
                            violation_type,
                            datetime(start_time, 'unixepoch', 'localtime') as start_time,
                            duration_seconds,
                            snapshot_path
                        FROM violation_events
                        WHERE status = 'resolved'
                        ORDER BY end_time DESC
                        LIMIT 5
                    """)
                    
                    for event_id, camera_id, v_type, start_time, duration, snapshot in cursor.fetchall():
                        duration_min = int(duration // 60) if duration else 0
                        duration_sec = int(duration % 60) if duration else 0
                        snapshot_status = "📸" if snapshot and os.path.exists(snapshot) else "❌"
                        
                        print(f"   ✅ {v_type}")
                        print(f"      Event: {event_id[:20]}...")
                        print(f"      Kamera: {camera_id}")
                        print(f"      Süre: {duration_min}dk {duration_sec}sn")
                        print(f"      Snapshot: {snapshot_status}")
                        print()
                
                # Snapshot sayısı
                snapshot_count = 0
                if os.path.exists('violations'):
                    for root, dirs, files in os.walk('violations'):
                        snapshot_count += len([f for f in files if f.endswith(('.jpg', '.jpeg', '.png'))])
                
                if snapshot_count > last_snapshot_count:
                    new_snapshots = snapshot_count - last_snapshot_count
                    print(f"\n📸 YENİ SNAPSHOT! +{new_snapshots} fotoğraf kaydedildi!")
                    last_snapshot_count = snapshot_count
                
                print(f"\n📸 SNAPSHOT İSTATİSTİKLERİ:")
                print(f"   • Toplam Snapshot: {snapshot_count} adet")
                if os.path.exists('violations'):
                    total_size = 0
                    for root, dirs, files in os.walk('violations'):
                        for file in files:
                            if file.endswith(('.jpg', '.jpeg', '.png')):
                                total_size += os.path.getsize(os.path.join(root, file))
                    print(f"   • Toplam Boyut: {total_size / (1024*1024):.2f} MB")
                
                conn.close()
                
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    print("\n⚠️  Violation tracking tabloları henüz oluşturulmamış!")
                    print("💡 Sunucuyu başlatın: python smartsafe_saas_api.py")
                else:
                    print(f"\n❌ Database hatası: {e}")
            
            print("\n" + "="*70)
            print(f"🔄 {interval} saniye sonra güncellenecek... (CTRL+C ile çık)")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring durduruldu.")
        print("="*70 + "\n")


if __name__ == "__main__":
    import sys
    
    interval = 5
    if len(sys.argv) > 1:
        try:
            interval = int(sys.argv[1])
        except:
            pass
    
    monitor_violations(interval=interval)
