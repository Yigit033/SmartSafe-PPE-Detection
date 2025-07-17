#!/usr/bin/env python3
"""
SmartSafe AI - Gerçek Kamera Sistemi Hızlı Başlangıç
Quick start script for real camera system setup
"""

import sys
import os
import subprocess
import time
from datetime import datetime

def print_header(title):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"🚀 {title}")
    print("="*60)

def print_step(step_num, description):
    """Print step information"""
    print(f"\n📋 Adım {step_num}: {description}")
    print("-" * 50)

def run_command(command, description):
    """Run a command and return success status"""
    print(f"⚡ {description}")
    print(f"   Komut: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ Başarılı")
            return True
        else:
            print(f"   ❌ Hata: {result.stderr}")
            return False
    except Exception as e:
        print(f"   ❌ Hata: {e}")
        return False

def setup_company_and_user():
    """Setup company and user"""
    print_step(1, "Şirket ve Kullanıcı Kurulumu")
    
    # Company setup
    company_code = input("Şirket kodu (örnek: ACME_CONSTRUCTION): ").strip() or "ACME_CONSTRUCTION"
    company_name = input("Şirket adı (örnek: ACME İnşaat): ").strip() or "ACME İnşaat"
    
    setup_code = f'''
from smartsafe_multitenant_system import MultiTenantDatabase
import uuid

db = MultiTenantDatabase()

# Şirket oluştur
try:
    company_id = db.create_company("{company_code}", "{company_name}", "Türkiye", "construction", 10)
    print(f"✅ Şirket oluşturuldu: {{company_id}}")
except Exception as e:
    print(f"⚠️ Şirket zaten var veya hata: {{e}}")

# Admin kullanıcı oluştur
try:
    user_id = db.create_user("{company_code}", "admin", "admin@{company_code.lower()}.com", "admin123", "admin")
    print(f"✅ Admin kullanıcı oluşturuldu: {{user_id}}")
except Exception as e:
    print(f"⚠️ Kullanıcı zaten var veya hata: {{e}}")

print(f"🔑 Giriş Bilgileri:")
print(f"   Şirket: {company_code}")
print(f"   Kullanıcı: admin")
print(f"   Parola: admin123")
'''
    
    # Write and execute setup script
    with open('temp_setup.py', 'w', encoding='utf-8') as f:
        f.write(setup_code)
    
    success = run_command('python temp_setup.py', 'Şirket ve kullanıcı oluşturuluyor')
    
    # Clean up
    if os.path.exists('temp_setup.py'):
        os.remove('temp_setup.py')
    
    return success, company_code

def setup_test_cameras():
    """Setup test cameras"""
    print_step(2, "Test Kamerası Kurulumu")
    
    print("📹 Test kamerası bilgilerini girin:")
    camera_name = input("Kamera adı (örnek: Test Kamera 1): ").strip() or "Test Kamera 1"
    camera_ip = input("IP adresi (örnek: 192.168.1.190): ").strip() or "192.168.1.190"
    camera_port = input("Port (örnek: 8080): ").strip() or "8080"
    camera_username = input("Kullanıcı adı (boş bırakabilirsiniz): ").strip()
    camera_password = input("Parola (boş bırakabilirsiniz): ").strip()
    
    # Test camera connection
    test_code = f'''
from camera_integration_manager import RealCameraManager, RealCameraConfig
import sys

# Kamera konfigürasyonu
camera_config = RealCameraConfig(
    camera_id="TEST_CAM_001",
    name="{camera_name}",
    ip_address="{camera_ip}",
    port={camera_port},
    username="{camera_username}",
    password="{camera_password}",
    protocol="http",
    stream_path="/video",
    auth_type="basic" if "{camera_username}" else "none"
)

# Test bağlantı
camera_manager = RealCameraManager()
print(f"🔍 Kamera bağlantısı test ediliyor: {{camera_config.name}}")
print(f"   IP: {{camera_config.ip_address}}:{{camera_config.port}}")
print(f"   Stream URL: {{camera_config.get_stream_url()}}")

test_result = camera_manager.test_real_camera_connection(camera_config)

if test_result['success']:
    print("✅ Kamera bağlantısı başarılı!")
    print(f"   Bağlantı süresi: {{test_result['connection_time']:.2f}}s")
    print(f"   Stream kalitesi: {{test_result['stream_quality']}}")
    
    # Kamera bilgilerini kaydet
    import json
    camera_data = {{
        'name': camera_config.name,
        'ip_address': camera_config.ip_address,
        'port': camera_config.port,
        'username': camera_config.username,
        'password': camera_config.password,
        'protocol': camera_config.protocol,
        'stream_path': camera_config.stream_path,
        'auth_type': camera_config.auth_type,
        'resolution': '1920x1080',
        'fps': 25,
        'location': 'Test Alanı'
    }}
    
    with open('test_camera_config.json', 'w', encoding='utf-8') as f:
        json.dump(camera_data, f, indent=2, ensure_ascii=False)
    
    print("💾 Kamera konfigürasyonu test_camera_config.json dosyasına kaydedildi")
    sys.exit(0)
else:
    print(f"❌ Kamera bağlantısı başarısız: {{test_result['error']}}")
    print("💡 Çözüm önerileri:")
    print("   1. IP adresini kontrol edin")
    print("   2. Port numarasını doğrulayın")
    print("   3. Kamera açık ve ağa bağlı olduğundan emin olun")
    print("   4. Güvenlik duvarı ayarlarını kontrol edin")
    sys.exit(1)
'''
    
    # Write and execute test script
    with open('temp_camera_test.py', 'w', encoding='utf-8') as f:
        f.write(test_code)
    
    success = run_command('python temp_camera_test.py', 'Kamera bağlantısı test ediliyor')
    
    # Clean up
    if os.path.exists('temp_camera_test.py'):
        os.remove('temp_camera_test.py')
    
    return success

def add_camera_to_database(company_code):
    """Add camera to database"""
    print_step(3, "Kamerayı Veritabanına Ekleme")
    
    if not os.path.exists('test_camera_config.json'):
        print("❌ Kamera konfigürasyon dosyası bulunamadı")
        return False
    
    add_code = f'''
from smartsafe_multitenant_system import MultiTenantDatabase
import json

# Kamera konfigürasyonunu yükle
with open('test_camera_config.json', 'r', encoding='utf-8') as f:
    camera_data = json.load(f)

# Veritabanına ekle
db = MultiTenantDatabase()
success, result = db.add_camera("{company_code}", camera_data)

if success:
    print(f"✅ Kamera veritabanına eklendi: {{result}}")
    print(f"   Kamera adı: {{camera_data['name']}}")
    print(f"   IP adresi: {{camera_data['ip_address']}}:{{camera_data['port']}}")
else:
    print(f"❌ Kamera eklenirken hata: {{result}}")
'''
    
    # Write and execute add script
    with open('temp_add_camera.py', 'w', encoding='utf-8') as f:
        f.write(add_code)
    
    success = run_command('python temp_add_camera.py', 'Kamera veritabanına ekleniyor')
    
    # Clean up
    if os.path.exists('temp_add_camera.py'):
        os.remove('temp_add_camera.py')
    
    return success

def start_system():
    """Start the SmartSafe AI system"""
    print_step(4, "Sistem Başlatma")
    
    print("🌐 SmartSafe AI web arayüzü başlatılıyor...")
    print("   URL: http://localhost:5000")
    print("   Ctrl+C ile durdurabilirsiniz")
    
    input("\nDevam etmek için Enter'a basın...")
    
    try:
        subprocess.run(['python', 'smartsafe_saas_api.py'], check=True)
    except KeyboardInterrupt:
        print("\n\n🛑 Sistem durduruldu")
    except Exception as e:
        print(f"\n❌ Sistem başlatma hatası: {e}")

def main():
    """Main function"""
    print_header("SmartSafe AI - Gerçek Kamera Sistemi Hızlı Başlangıç")
    
    print("🎯 Bu script aşağıdaki adımları gerçekleştirir:")
    print("   1. Şirket ve kullanıcı oluşturma")
    print("   2. Test kamerası bağlantısı")
    print("   3. Kamerayı veritabanına ekleme")
    print("   4. Web arayüzünü başlatma")
    
    print("\n⚠️  Gereksinimler:")
    print("   - Python 3.8+ kurulu")
    print("   - requirements.txt yüklü")
    print("   - Test kamerası ağda erişilebilir")
    
    response = input("\nDevam etmek istiyor musunuz? (E/h): ").strip().lower()
    if response not in ['e', 'evet', 'y', 'yes']:
        print("İşlem iptal edildi.")
        return
    
    # Step 1: Setup company and user
    success, company_code = setup_company_and_user()
    if not success:
        print("❌ Şirket kurulumu başarısız")
        return
    
    # Step 2: Setup test cameras
    success = setup_test_cameras()
    if not success:
        print("❌ Kamera testi başarısız")
        return
    
    # Step 3: Add camera to database
    success = add_camera_to_database(company_code)
    if not success:
        print("❌ Kamera veritabanına eklenemedi")
        return
    
    # Step 4: Start system
    print("\n🎉 Kurulum tamamlandı!")
    print(f"   Şirket: {company_code}")
    print(f"   Giriş: admin / admin123")
    print(f"   URL: http://localhost:5000")
    
    start_system()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 İşlem kullanıcı tarafından iptal edildi")
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        print("Lütfen REAL_CAMERA_DEPLOYMENT_GUIDE.md dosyasını kontrol edin") 