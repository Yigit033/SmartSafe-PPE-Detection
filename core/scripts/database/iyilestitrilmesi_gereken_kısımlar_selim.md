Şu anki 3 hata aynı kök probleme işaret ediyor: DVR worker’ın koştuğu Python kodu ve/veya bağlandığı Postgres, senin PgWeb’de doğruladığın PR3’lü dünya ile aynı değil. Bunun kanıtı iki yerden geliyor:

DB tarafı: Log’da hâlâ violation_events_camera_id_fkey ile FK violation görüyorsun. PR1/PR3 sonrası bu constraint’in olmaması gerekiyordu (checklist/verify script de bunu kontrol ediyor).
Kod tarafı: Repodaki güncel add_violation_event DVR için camera_id = NULL yazıyor; böyle olsaydı, violation_events_camera_id_fkey olsa bile (camera_id NULL) FK violation normalde tetiklenmezdi.
Ayrıca get_placeholder uyarısının geri gelmesi de “worker eski modülü import ediyor / eski image çalışıyor” olasılığını güçlendiriyor.

1) Repodaki doğru davranış (neden FK violation olmamalı)
core/database/database_adapter.py içinde DVR event insert’i PR3 contract’a uygun:

    def add_violation_event(self, event_data: Dict) -> bool:
        """Yeni ihlal event'i kaydet. DVR kaynağında dvr_channels eşleşmesi yoksa yazılmaz (fail-fast)."""
        try:
            camera_id = event_data['camera_id']
            company_id = event_data['company_id']
            # ...
            elif '_ch' in str(camera_id):
                dvr_channel_id = self._resolve_dvr_channel_fk(camera_id, company_id)
                if not dvr_channel_id:
                    logger.error(
                        "❌ violation_events: DVR camera_id could not be resolved to dvr_channels.channel_id "
                        f"(event_id={event_data.get('event_id')}, camera_id={camera_id}, company_id={company_id})"
                    )
                    return False
                source_type = 'dvr_channel'
            # ...
            insert_camera_id = None if source_type == 'dvr_channel' else camera_id
            # ... INSERT params include insert_camera_id ...
Yani güncel kodla DVR satırlarında camera_id NULL olmalı.

Ayrıca init kısmında Postgres’te legacy FK’yi drop etmeyi de deniyor:

            else:  # PostgreSQL
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS violation_events (
                        ...
                        source_type VARCHAR(20) NOT NULL,
                        dvr_channel_id VARCHAR(255) REFERENCES dvr_channels (channel_id),
                        ...
                        CONSTRAINT violation_events_source_shape_chk CHECK (
                            (source_type = 'camera' AND camera_id IS NOT NULL AND dvr_channel_id IS NULL)
                            OR
                            (source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL AND camera_id IS NULL)
                        )
                    )
                ''')
                try:
                    cursor.execute('''
                        ALTER TABLE violation_events
                        DROP CONSTRAINT IF EXISTS violation_events_camera_id_fkey
                    ''')
                except Exception:
                    pass
2) “person_count yok” hatası neden oluyor?
core/app.py Postgres için detections insert’inde person_count kolonu kullanıyor:

    def save_detection_to_db(self, detection_data):
        # ...
        cursor.execute(f'''
            INSERT INTO detections (
                company_id, camera_id, timestamp, person_count, 
                ppe_compliant, compliance_rate, processing_time_ms
            ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        ''', (
            detection_data['company_id'],
            detection_data['camera_id'],
            detection_data['timestamp'],
            detection_data.get('person_count', detection_data.get('people_detected', 0)),
            ...
        ))
DB şemanızda detections.person_count yoksa bu hata normal. Bu ayrı bir migration/uyum işi.

3) Şu an DVR smoke test neden bloklanıyor? (en olası 2 senaryo)
Senaryo A (en olası): Docker’da çalışan core container eski image/kod çalıştırıyor. O eski kod:
DVR için hâlâ camera_id dolduruyor (NULL değil),
belki “shadow row” yolunu deniyor,
get_placeholder metodu yok.
Senaryo B: Worker’ın bağlandığı Postgres, senin PgWeb’de verify ettiğin DB değil (farklı DATABASE_URL, farklı container network, yanlış DB). Bu durumda worker DB’sinde:
violation_events_camera_id_fkey hâlâ duruyor olabilir,
detections tablosu farklı şemada olabilir.
4) Şimdi net teşhis için senin yapacağın 3 doğrulama (PgWeb + Docker)
Bunları PgWeb’de iki farklı bağlantıda (senin kullandığın ve core container’ın kullandığı DB) çalıştır.

4.1 Worker’ın DB’sinde gerçekten hangi constraint var?
PgWeb:

SELECT current_database() AS db, current_user AS usr, inet_server_addr() AS host, inet_server_port() AS port;
SELECT conname
FROM pg_constraint
WHERE conname IN ('violation_events_camera_id_fkey', 'violation_events_source_shape_chk')
ORDER BY conname;
SELECT column_name, is_nullable
FROM information_schema.columns
WHERE table_name='violation_events'
  AND column_name IN ('camera_id','source_type','dvr_channel_id')
ORDER BY column_name;
Beklenti (PR3 sonrası):

violation_events_camera_id_fkey yok
violation_events_source_shape_chk var
source_type NOT NULL
DVR row’larında camera_id NULL.
4.2 Worker aslında hangi DB’ye bağlanıyor?
Docker core container environment’ında DATABASE_URL/connection string’i görmen lazım (hangi compose dosyasıysa orada da görebilirsin). Eğer DB URL’ler farklıysa, PgWeb’de verify ettiğin DB “doğru DB” olmayabilir.

4.3 detections tablosunda person_count var mı?
PgWeb:

SELECT column_name
FROM information_schema.columns
WHERE table_name='detections'
ORDER BY ordinal_position;
Eğer person_count yoksa, ya DB’ye migration eklenmeli ya da code people_detected/mevcut kolonlara göre yazmalı.
5) Sonuç / “Profesyonellik çerçevesinde durumumuz nedir?”
violation_events rollout (PR1–PR3) planı doğru ve DB verify script’i senin çalıştırdığın yerde doğru görünüyor.
Ama DVR smoke test halen FAIL çünkü worker tarafı ya yanlış DB’ye bağlı ya da eski kod/image çalıştırıyor. Log’daki violation_events_camera_id_fkey ve get_placeholder bunun “prod-benzeri drift” semptomu.
Ek olarak detections.person_count hatası, violation_events migration’ından bağımsız bir detections schema drift; DVR akışını “tam temiz” hale getirmek için bunu da hizalamak gerekiyor.
İstersen sonraki mesajında şu 3 çıktıyı yapıştır: (1) yukarıdaki constraint sorgularının sonucu, (2) current_database()/host/port çıktısı, (3) detections kolon listesi. Bu üçüyle hangi senaryoda olduğunuzu %100 netleştirip, sana tam nokta atışı “docker rebuild mi / env düzeltme mi / hangi migration” yolunu söyleyebilirim.