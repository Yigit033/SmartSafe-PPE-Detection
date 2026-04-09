#!/usr/bin/env python3
"""
Port ve network bağlantısı kontrol scripti
"""
import socket
import subprocess
import sys

def check_port(port):
    """Port'un açık olup olmadığını kontrol et"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('0.0.0.0', port))
        sock.close()
        
        if result == 0:
            print(f"✅ Port {port} AÇIK ve dinliyor")
            return True
        else:
            print(f"❌ Port {port} KAPALI veya kullanımda değil")
            return False
    except Exception as e:
        print(f"❌ Port kontrolü hatası: {e}")
        return False

def get_local_ip():
    """Lokal IP adresini al"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "Bulunamadı"

def check_firewall_windows(port):
    """Windows firewall kuralını kontrol et"""
    try:
        cmd = f'netsh advfirewall firewall show rule name="SmartSafe Port {port}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if "No rules match" in result.stdout or result.returncode != 0:
            print(f"⚠️  Firewall kuralı bulunamadı. Oluşturuluyor...")
            
            # Inbound rule ekle
            cmd_add = f'netsh advfirewall firewall add rule name="SmartSafe Port {port}" dir=in action=allow protocol=TCP localport={port}'
            result_add = subprocess.run(cmd_add, shell=True, capture_output=True, text=True)
            
            if result_add.returncode == 0:
                print(f"✅ Firewall kuralı eklendi: Port {port}")
                return True
            else:
                print(f"❌ Firewall kuralı eklenemedi: {result_add.stderr}")
                print("⚠️  Lütfen yönetici olarak çalıştırın!")
                return False
        else:
            print(f"✅ Firewall kuralı mevcut: Port {port}")
            return True
    except Exception as e:
        print(f"❌ Firewall kontrolü hatası: {e}")
        return False

def main():
    print("=" * 60)
    print("🔍 SmartSafe Network Kontrol")
    print("=" * 60)
    
    # Lokal IP
    local_ip = get_local_ip()
    print(f"\n📍 Lokal IP: {local_ip}")
    
    # Port kontrolü
    ports = [5577, 10000]
    print(f"\n🔌 Port Kontrolü:")
    for port in ports:
        check_port(port)
    
    # Firewall kontrolü (sadece Windows)
    if sys.platform == 'win32':
        print(f"\n🛡️  Windows Firewall Kontrolü:")
        for port in ports:
            check_firewall_windows(port)
    
    print("\n" + "=" * 60)
    print("📝 Erişim URL'leri:")
    print(f"   - Lokal: http://localhost:5577/")
    print(f"   - Lokal IP: http://{local_ip}:5577/")
    print(f"   - Harici: http://161.9.126.42:5577/")
    print("=" * 60)
    
    print("\n💡 Sorun devam ederse:")
    print("   1. Sunucu çalışıyor mu kontrol edin: python smartsafe_saas_api.py")
    print("   2. Firewall ayarlarını kontrol edin")
    print("   3. Router port forwarding ayarlarını kontrol edin (161.9.126.42)")
    print("   4. VPN veya proxy kullanıyorsanız devre dışı bırakın")

if __name__ == "__main__":
    main()
