#!/usr/bin/env python3
"""
SmartSafe AI Production - Gerçek Kamera Kurulum Scripti
Production camera setup for https://smartsafeai.onrender.com/
"""

import requests
import json
import socket
import sys
from typing import Dict, List, Optional

class ProductionCameraSetup:
    """Production ortamı için kamera kurulum yardımcısı"""
    
    def __init__(self):
        self.api_base = "https://smartsafeai.onrender.com/api"
        self.web_base = "https://smartsafeai.onrender.com"
        self.session = requests.Session()
        self.company_id = None
        self.auth_token = None
    
    def print_header(self, title: str):
        """Başlık yazdır"""
        print("\n" + "="*60)
        print(f"🌐 {title}")
        print("="*60)
    
    def print_step(self, step_num: int, description: str):
        """Adım bilgisi yazdır"""
        print(f"\n📋 Adım {step_num}: {description}")
        print("-" * 50)
    
    def test_internet_connection(self) -> bool:
        """İnternet bağlantısını test et"""
        try:
            response = requests.get(self.web_base, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def test_camera_accessibility(self, ip: str, port: int) -> Dict:
        """Kamera erişilebilirlik testi"""
        result = {
            'accessible': False,
            'public_ip': None,
            'port_open': False,
            'recommendation': ''
        }
        
        try:
            # Local IP kontrolü
            if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                result['recommendation'] = 'VPN veya Port Forwarding gerekli'
                
                # Public IP'yi bul
                try:
                    pub_ip_response = requests.get('https://api.ipify.org', timeout=5)
                    result['public_ip'] = pub_ip_response.text
                except:
                    result['public_ip'] = 'Bulunamadı'
            else:
                # Public IP testi
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                port_result = sock.connect_ex((ip, port))
                sock.close()
                
                result['port_open'] = port_result == 0
                result['accessible'] = port_result == 0
                
                if not result['accessible']:
                    result['recommendation'] = 'Port forwarding veya güvenlik duvarı ayarları kontrol edin'
        
        except Exception as e:
            result['recommendation'] = f'Bağlantı hatası: {str(e)}'
        
        return result
    
    def get_company_info(self) -> Optional[str]:
        """Şirket bilgilerini al"""
        self.print_step(1, "Şirket Bilgileri")
        
        print("🏢 SmartSafe AI Production ortamında şirket bilgilerinizi girin:")
        
        company_code = input("Şirket kodu (örnek: ACME_CONSTRUCTION): ").strip()
        if not company_code:
            print("❌ Şirket kodu gerekli!")
            return None
        
        print(f"\n✅ Şirket kodu: {company_code}")
        print(f"🔗 Giriş URL'si: {self.web_base}/")
        print(f"📋 Şirket kaydı yapmak için: {self.web_base}/register")
        
        return company_code
    
    def get_camera_info(self) -> Dict:
        """Kamera bilgilerini al"""
        self.print_step(2, "Kamera Bilgileri")
        
        print("📹 Production ortamında kullanacağınız kamera bilgilerini girin:")
        
        camera_info = {}
        camera_info['name'] = input("Kamera adı (örnek: Üretim Alanı Kamera 1): ").strip() or "Production Camera 1"
        camera_info['location'] = input("Konum (örnek: Ana Üretim Alanı): ").strip() or "Production Floor"
        
        # IP adresi ve port
        camera_info['ip_address'] = input("IP adresi (örnek: 192.168.1.190 veya PUBLIC_IP): ").strip()
        camera_info['port'] = int(input("Port (örnek: 8080): ").strip() or "8080")
        
        # Kimlik doğrulama
        camera_info['username'] = input("Kullanıcı adı (boş bırakabilirsiniz): ").strip()
        camera_info['password'] = input("Parola (boş bırakabilirsiniz): ").strip()
        
        # Protokol
        protocol_choice = input("Protokol (1: HTTP, 2: HTTPS, 3: RTSP): ").strip()
        protocol_map = {'1': 'http', '2': 'https', '3': 'rtsp'}
        camera_info['protocol'] = protocol_map.get(protocol_choice, 'http')
        
        # Stream path
        camera_info['stream_path'] = input("Stream yolu (örnek: /video): ").strip() or "/video"
        
        return camera_info
    
    def analyze_network_setup(self, camera_info: Dict):
        """Ağ kurulumunu analiz et"""
        self.print_step(3, "Ağ Kurulumu Analizi")
        
        ip = camera_info['ip_address']
        port = camera_info['port']
        
        print(f"🔍 Kamera erişilebilirlik analizi:")
        print(f"   IP: {ip}")
        print(f"   Port: {port}")
        
        # Erişilebilirlik testi
        access_result = self.test_camera_accessibility(ip, port)
        
        if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
            print(f"\n⚠️  LOCAL IP ADRESI TESPİT EDİLDİ!")
            print(f"   Bu kamera local ağda (şirket içi)")
            print(f"   Public IP: {access_result['public_ip']}")
            print(f"\n🔧 Production için çözüm seçenekleri:")
            print(f"   1. 🌐 VPN Bağlantısı (Önerilen)")
            print(f"   2. 🔀 Port Forwarding")
            print(f"   3. ☁️  Cloud Kamera Servisi")
            
            self.show_setup_recommendations(camera_info, access_result)
        else:
            print(f"\n✅ PUBLIC IP ADRESI")
            if access_result['accessible']:
                print(f"   Kamera erişilebilir!")
            else:
                print(f"   ❌ Kamera erişilemiyor")
                print(f"   Öneri: {access_result['recommendation']}")
    
    def show_setup_recommendations(self, camera_info: Dict, access_result: Dict):
        """Kurulum önerilerini göster"""
        print(f"\n💡 DETAYLI KURULUM REHBERİ:")
        
        # 1. VPN Çözümü
        print(f"\n1️⃣ VPN Çözümü (Önerilen):")
        print(f"   • Şirket ağınızda VPN sunucusu kurun")
        print(f"   • SmartSafe AI sunucusuna VPN erişimi verin")
        print(f"   • Kameralar VPN üzerinden erişilebilir olacak")
        print(f"   • Güvenli ve ölçeklenebilir")
        
        # 2. Port Forwarding
        print(f"\n2️⃣ Port Forwarding (Basit):")
        print(f"   • Router ayarlarında port forwarding aktif edin")
        print(f"   • Kural: {camera_info['port']} → {camera_info['ip_address']}:{camera_info['port']}")
        print(f"   • Production'da IP: {access_result['public_ip']}")
        print(f"   • Port: {camera_info['port']}")
        
        # 3. Cloud Servis
        print(f"\n3️⃣ Cloud Kamera Servisi:")
        print(f"   • Kameranızın cloud desteği var mı kontrol edin")
        print(f"   • Cloud URL'si kullanın")
        print(f"   • Örnek: https://camera.company.com/stream")
    
    def generate_production_config(self, company_code: str, camera_info: Dict) -> Dict:
        """Production konfigürasyonu oluştur"""
        self.print_step(4, "Production Konfigürasyonu")
        
        # Kamera URL'si oluştur
        if camera_info['protocol'] == 'rtsp':
            if camera_info['username'] and camera_info['password']:
                camera_url = f"rtsp://{camera_info['username']}:{camera_info['password']}@{camera_info['ip_address']}:{camera_info['port']}{camera_info['stream_path']}"
            else:
                camera_url = f"rtsp://{camera_info['ip_address']}:{camera_info['port']}{camera_info['stream_path']}"
        else:
            camera_url = f"{camera_info['protocol']}://{camera_info['ip_address']}:{camera_info['port']}{camera_info['stream_path']}"
        
        production_config = {
            "company_code": company_code,
            "camera": {
                "name": camera_info['name'],
                "location": camera_info['location'],
                "ip_address": camera_info['ip_address'],
                "port": camera_info['port'],
                "username": camera_info['username'],
                "password": camera_info['password'],
                "protocol": camera_info['protocol'],
                "stream_path": camera_info['stream_path'],
                "camera_url": camera_url,
                "auth_type": "basic" if camera_info['username'] else "none"
            },
            "production_settings": {
                "api_endpoint": self.api_base,
                "web_dashboard": self.web_base,
                "resolution": "1280x720",
                "fps": 25,
                "quality": 80
            }
        }
        
        # Konfigürasyonu dosyaya kaydet
        config_file = f"production_camera_config_{company_code}.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(production_config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Production konfigürasyonu oluşturuldu!")
        print(f"   Dosya: {config_file}")
        print(f"   Kamera URL: {camera_url}")
        
        return production_config
    
    def show_next_steps(self, config: Dict):
        """Sonraki adımları göster"""
        self.print_step(5, "Sonraki Adımlar")
        
        print(f"🎯 Production ortamında devam etmek için:")
        
        print(f"\n1️⃣ Şirket Kaydı:")
        print(f"   • {self.web_base}/ adresine gidin")
        print(f"   • 'Şirket Kaydı' yapın")
        print(f"   • Şirket kodu: {config['company_code']}")
        
        print(f"\n2️⃣ Kamera Ekleme:")
        print(f"   • Dashboard'da 'Kamera Ekle' butonuna tıklayın")
        print(f"   • Kamera bilgilerini girin:")
        print(f"     - Adı: {config['camera']['name']}")
        print(f"     - IP: {config['camera']['ip_address']}")
        print(f"     - Port: {config['camera']['port']}")
        print(f"     - Protokol: {config['camera']['protocol']}")
        
        print(f"\n3️⃣ Kamera Testi:")
        print(f"   • 'Kamera Testi' butonuna tıklayın")
        print(f"   • Bağlantı durumunu kontrol edin")
        print(f"   • Başarılı ise 'Kamera Ekle' butonuna tıklayın")
        
        print(f"\n4️⃣ PPE Tespit:")
        print(f"   • Kamera eklendikten sonra PPE tespit otomatik başlar")
        print(f"   • Dashboard'da canlı sonuçları görüntüleyin")
        print(f"   • Raporları ve istatistikleri takip edin")
    
    def run(self):
        """Ana çalıştırma fonksiyonu"""
        self.print_header("SmartSafe AI Production - Kamera Kurulum Rehberi")
        
        print("🎯 Bu script, gerçek kameralarınızı SmartSafe AI Production ortamına")
        print("   bağlamak için gerekli bilgileri toplar ve konfigürasyon oluşturur.")
        
        print(f"\n🌐 Production URL: {self.web_base}")
        print(f"📞 Destek: yigittilaver2000@gmail.com")
        
        # İnternet bağlantısı kontrolü
        if not self.test_internet_connection():
            print("\n❌ İnternet bağlantısı yok veya SmartSafe AI erişilemiyor!")
            print(f"   Lütfen bağlantınızı kontrol edin: {self.web_base}")
            return
        
        print(f"\n✅ SmartSafe AI Production sistemi erişilebilir")
        
        # Devam etmek istiyor mu?
        response = input("\nDevam etmek istiyor musunuz? (E/h): ").strip().lower()
        if response not in ['e', 'evet', 'y', 'yes']:
            print("İşlem iptal edildi.")
            return
        
        try:
            # Şirket bilgileri
            company_code = self.get_company_info()
            if not company_code:
                return
            
            # Kamera bilgileri
            camera_info = self.get_camera_info()
            
            # Ağ analizi
            self.analyze_network_setup(camera_info)
            
            # Production konfigürasyonu
            config = self.generate_production_config(company_code, camera_info)
            
            # Sonraki adımlar
            self.show_next_steps(config)
            
            print(f"\n🎉 Kurulum hazırlığı tamamlandı!")
            print(f"   Konfigürasyon dosyası: production_camera_config_{company_code}.json")
            print(f"   Web dashboard: {self.web_base}/")
            
        except KeyboardInterrupt:
            print(f"\n\n🛑 İşlem kullanıcı tarafından iptal edildi")
        except Exception as e:
            print(f"\n❌ Hata: {e}")
            print(f"   Lütfen destek ile iletişime geçin: yigittilaver2000@gmail.com")

def main():
    """Ana fonksiyon"""
    setup = ProductionCameraSetup()
    setup.run()

if __name__ == "__main__":
    main() 