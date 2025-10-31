#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test IP Webcam bağlantısı
"""

import requests
import socket

def get_local_ip():
    """Bilgisayarın local IP adresini al"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        return f"Hata: {e}"

def test_camera_connection(ip, port=8080):
    """Kamera bağlantısını test et"""
    print(f"\n{'='*60}")
    print(f"🎥 Kamera Bağlantı Testi")
    print(f"{'='*60}")
    print(f"📍 Test edilen adres: {ip}:{port}")
    print(f"💻 Bilgisayarın local IP'si: {get_local_ip()}")
    print(f"{'='*60}\n")
    
    # Test edilecek path'ler
    paths = [
        '/video',
        '/shot.jpg',
        '/videofeed',
        '/photoaf.jpg',
        '/photo.jpg',
    ]
    
    for path in paths:
        url = f"http://{ip}:{port}{path}"
        try:
            print(f"🔍 Test ediliyor: {url}")
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                print(f"   ✅ BAŞARILI! Status: {response.status_code}")
                print(f"   📦 Content-Type: {response.headers.get('content-type', 'N/A')}")
                print(f"   📏 Content-Length: {len(response.content)} bytes")
                print(f"\n{'='*60}")
                print(f"✨ ÇALIŞAN URL BULUNDU: {url}")
                print(f"{'='*60}\n")
                return url
            else:
                print(f"   ⚠️  Status: {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"   ❌ TIMEOUT - Bağlantı zaman aşımına uğradı")
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ BAĞLANTI HATASI - {str(e)[:80]}")
        except Exception as e:
            print(f"   ❌ HATA - {str(e)[:80]}")
        print()
    
    print(f"{'='*60}")
    print(f"❌ Hiçbir URL çalışmadı!")
    print(f"{'='*60}\n")
    
    print("🔧 Kontrol Listesi:")
    print("   1. Telefon ve bilgisayar aynı WiFi ağında mı?")
    print("   2. IP Webcam uygulaması çalışıyor mu?")
    print("   3. IP adresi doğru mu? (Uygulamada gösterilen adresi kullan)")
    print("   4. Firewall kamera erişimini engelliyor olabilir mi?")
    print()
    
    return None

if __name__ == '__main__':
    print("\n🚀 IP Webcam Bağlantı Test Aracı")
    print("="*60)
    
    # Kullanıcıdan IP al
    ip = input("\n📱 IP Webcam'de gösterilen IP adresini girin (örn: 192.168.1.100): ").strip()
    port = input("🔌 Port numarasını girin (varsayılan: 8080): ").strip() or "8080"
    
    try:
        port = int(port)
        test_camera_connection(ip, port)
    except ValueError:
        print("❌ Geçersiz port numarası!")
    except KeyboardInterrupt:
        print("\n\n👋 Test iptal edildi.")
