import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def get_detection_stats(db_path='smartsafe_saas.db'):
    """Veritabanındaki tespit istatistiklerini getirir"""
    try:
        conn = sqlite3.connect(db_path)
        
        # Son 24 saatteki tespitleri al
        time_24h_ago = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Toplam istatistikler
        query = """
        SELECT 
            COUNT(*) as total_detections,
            SUM(people_detected) as total_people,
            SUM(ppe_compliant) as total_compliant,
            SUM(violations_count) as total_violations,
            AVG(confidence) as avg_confidence
        FROM detections
        WHERE timestamp >= ?
        """
        
        stats = pd.read_sql_query(query, conn, params=(time_24h_ago,))
        
        # Son 10 tespit
        recent_detections = pd.read_sql_query(
            """
            SELECT 
                camera_id,
                datetime(timestamp, 'unixepoch', 'localtime') as detection_time,
                people_detected,
                ppe_compliant,
                violations_count,
                confidence
            FROM detections 
            ORDER BY timestamp DESC 
            LIMIT 10
            """, 
            conn
        )
        
        # Kamera bazlı özet
        camera_stats = pd.read_sql_query(
            """
            SELECT 
                camera_id,
                COUNT(*) as detection_count,
                AVG(people_detected) as avg_people,
                AVG(ppe_compliant) as avg_compliant,
                AVG(violations_count) as avg_violations
            FROM detections
            WHERE timestamp >= ?
            GROUP BY camera_id
            """,
            conn,
            params=(time_24h_ago,)
        )
        
        conn.close()
        
        return {
            'overall_stats': stats.to_dict('records')[0] if not stats.empty else {},
            'recent_detections': recent_detections.to_dict('records'),
            'camera_stats': camera_stats.to_dict('records')
        }
        
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    print("🔍 SmartSafe AI - Veritabanı İstatistikleri")
    print("="*50)
    
    # Tüm veritabanlarını kontrol et
    db_files = [
        'smartsafe_saas.db',
        'smartsafe_master.db',
        'construction_safety.db',
        'logs/ppe_detection.db'
    ]
    
    for db_file in db_files:
        print(f"\n📊 Veritabanı: {db_file}")
        print("-"*30)
        
        try:
            stats = get_detection_stats(db_file)
            
            if 'error' in stats:
                print(f"  ❌ Hata: {stats['error']}")
                continue
                
            # Genel İstatistikler
            s = stats['overall_stats']
            if s:
                print("📈 Genel İstatistikler (Son 24 Saat):")
                print(f"  • Toplam Tespit: {s.get('total_detections', 0):,}")
                print(f"  • Toplam Kişi: {s.get('total_people', 0):,}")
                print(f"  • Uyumlu Kişi: {s.get('total_compliant', 0):,}")
                print(f"  • Toplam İhlal: {s.get('total_violations', 0):,}")
                print(f"  • Ortalama Güven: %{s.get('avg_confidence', 0)*100:.1f}")
            
            # Kamera İstatistikleri
            if stats['camera_stats']:
                print("\n📷 Kamera Bazında İstatistikler:")
                for cam in stats['camera_stats']:
                    print(f"  • {cam['camera_id']}:")
                    print(f"    - Tespit Sayısı: {cam.get('detection_count', 0):,}")
                    print(f"    - Ort. Kişi: {cam.get('avg_people', 0):.1f}")
                    print(f"    - Ort. Uyum: {cam.get('avg_compliant', 0):.1f}")
            
            # Son Tespitler
            if stats['recent_detections']:
                print("\n🕒 Son Tespitler:")
                for i, det in enumerate(stats['recent_detections'], 1):
                    print(f"  {i}. [{det['detection_time']}] {det['camera_id']}:")
                    print(f"     - Kişi: {det['people_detected']}, "
                          f"Uyumlu: {det['ppe_compliant']}, "
                          f"İhlal: {det['violations_count']}, "
                          f"Güven: %{det['confidence']*100:.1f}")
            
        except Exception as e:
            print(f"  ❌ Veritabanı okunurken hata: {e}")
    
    print("\n✅ Analiz tamamlandı.")
    print("Not: Veriler son 24 saati kapsamaktadır.")
