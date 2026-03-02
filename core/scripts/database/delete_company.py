#!/usr/bin/env python3
"""
SmartSafe AI - Manuel Şirket Silme
Admin kullanımı için
"""

import sqlite3
import os
from datetime import datetime

def list_companies():
    """Kayıtlı şirketleri listele"""
    db_path = 'smartsafe_saas.db'
    
    if not os.path.exists(db_path):
        print("❌ Database dosyası bulunamadı!")
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT company_id, company_name, email, sector, created_at 
            FROM companies 
            WHERE status = 'active'
            ORDER BY created_at DESC
        ''')
        companies = cursor.fetchall()
        
        if not companies:
            print("❌ Aktif şirket bulunamadı!")
            return []
        
        print("📊 AKTİF ŞİRKETLER")
        print("=" * 80)
        
        for i, (company_id, name, email, sector, created_at) in enumerate(companies, 1):
            print(f"{i}. ID: {company_id}")
            print(f"   Şirket: {name}")
            print(f"   Email: {email}")
            print(f"   Sektör: {sector}")
            print(f"   Kayıt: {created_at}")
            print("-" * 60)
        
        conn.close()
        return companies
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        return []

def delete_company(company_id):
    """Şirket ve ilgili tüm verileri sil"""
    db_path = 'smartsafe_saas.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Şirket var mı kontrol et
        cursor.execute('SELECT company_name FROM companies WHERE company_id = ?', (company_id,))
        company = cursor.fetchone()
        
        if not company:
            print(f"❌ Şirket ID '{company_id}' bulunamadı!")
            return False
        
        company_name = company[0]
        
        # Silme işlemini başlat
        print(f"🗑️  Şirket siliniyor: {company_name}")
        
        # İlgili verileri sil (CASCADE mantığı)
        tables_to_clean = [
            ('detections', 'Tespit kayıtları'),
            ('violations', 'İhlal kayıtları'),
            ('cameras', 'Kameralar'),
            ('users', 'Kullanıcılar'),
            ('sessions', 'Oturum kayıtları'),
            ('companies', 'Şirket kaydı')
        ]
        
        for table, description in tables_to_clean:
            cursor.execute(f'DELETE FROM {table} WHERE company_id = ?', (company_id,))
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"   ✅ {description}: {deleted_count} kayıt silindi")
        
        # Değişiklikleri kaydet
        conn.commit()
        conn.close()
        
        print(f"🎉 Şirket '{company_name}' başarıyla silindi!")
        return True
        
    except Exception as e:
        print(f"❌ Silme hatası: {e}")
        return False

def main():
    """Ana program"""
    print("🔧 SmartSafe AI - Şirket Silme Aracı")
    print("=" * 50)
    
    while True:
        print("\nSeçenekler:")
        print("1. Kayıtlı şirketleri listele")
        print("2. Şirket sil")
        print("3. Çıkış")
        
        choice = input("\nSeçiminiz (1-3): ").strip()
        
        if choice == '1':
            companies = list_companies()
            
        elif choice == '2':
            company_id = input("Silinecek şirket ID'sini girin: ").strip()
            if company_id:
                confirm = input(f"⚠️  '{company_id}' şirketi SİLİNECEK! Emin misiniz? (evet/hayır): ").strip().lower()
                if confirm == 'evet':
                    delete_company(company_id)
                else:
                    print("❌ Silme işlemi iptal edildi.")
            else:
                print("❌ Geçersiz şirket ID!")
                
        elif choice == '3':
            print("👋 Görüşürüz!")
            break
        else:
            print("❌ Geçersiz seçim!")

if __name__ == "__main__":
    main() 