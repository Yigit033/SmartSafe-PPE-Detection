#!/usr/bin/env python3
"""
SmartSafe AI - Kayıtlı Şirketleri Kontrol Et
"""

import sqlite3
import os
from datetime import datetime

def check_companies():
    """Kayıtlı şirketleri listele"""
    db_path = 'smartsafe_saas.db'
    
    if not os.path.exists(db_path):
        print("❌ Database dosyası bulunamadı!")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Şirketleri getir
        cursor.execute('''
            SELECT company_id, company_name, email, sector, 
                   max_cameras, created_at, status 
            FROM companies 
            ORDER BY created_at DESC
        ''')
        companies = cursor.fetchall()
        
        print("📊 KAYITLI ŞİRKETLER")
        print("=" * 80)
        
        if not companies:
            print("❌ Henüz kayıtlı şirket yok!")
            return
        
        for i, (company_id, name, email, sector, max_cameras, created_at, status) in enumerate(companies, 1):
            print(f"{i}. ID: {company_id}")
            print(f"   Şirket: {name}")
            print(f"   Email: {email}")
            print(f"   Sektör: {sector}")
            print(f"   Max Kamera: {max_cameras}")
            print(f"   Kayıt: {created_at}")
            print(f"   Durum: {status}")
            print("-" * 60)
        
        print(f"📈 Toplam: {len(companies)} şirket kayıtlı")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == "__main__":
    check_companies() 