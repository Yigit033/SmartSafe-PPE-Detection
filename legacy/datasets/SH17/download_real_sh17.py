#!/usr/bin/env python3
"""
Real SH17 Dataset Downloader
SmartSafe AI - PPE Detection Real Dataset
"""

import os
import requests
import zipfile
import yaml
from pathlib import Path

def download_real_sh17():
    """Gerçek SH17 dataset'ini indir"""
    print("🚀 Gerçek SH17 Dataset İndirme Başlıyor...")
    
    # Gerçek SH17 dataset URL'leri
    dataset_urls = {
        'images': 'https://huggingface.co/datasets/SmartSafe-AI/SH17/resolve/main/images.zip',
        'labels': 'https://huggingface.co/datasets/SmartSafe-AI/SH17/resolve/main/labels.zip',
        'config': 'https://huggingface.co/datasets/SmartSafe-AI/SH17/resolve/main/SH17.yaml'
    }
    
    # Alternatif URL'ler (eğer birincisi çalışmazsa)
    fallback_urls = {
        'images': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/latest/download/SH17_images.zip',
        'labels': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/latest/download/SH17_labels.zip',
        'config': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/latest/download/SH17.yaml'
    }
    
    # Klasör yapısı oluştur
    folders = ['images', 'labels', 'configs']
    for folder in folders:
        Path(folder).mkdir(exist_ok=True)
    
    # Dataset indir
    for name, url in dataset_urls.items():
        print(f"📥 {name} indiriliyor...")
        success = False
        
        # İlk URL'yi dene
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            success = True
        except Exception as e:
            print(f"⚠️ İlk URL başarısız: {e}")
            
            # Fallback URL'yi dene
            try:
                fallback_url = fallback_urls[name]
                print(f"🔄 Fallback URL deneniyor: {fallback_url}")
                response = requests.get(fallback_url, stream=True, timeout=30)
                response.raise_for_status()
                success = True
            except Exception as e2:
                print(f"❌ Fallback URL de başarısız: {e2}")
                success = False
        
        if success:
            try:
                if name == 'config':
                    with open('configs/SH17.yaml', 'wb') as f:
                        f.write(response.content)
                else:
                    with open(f'{name}.zip', 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Zip dosyasını çıkart
                    with zipfile.ZipFile(f'{name}.zip', 'r') as zip_ref:
                        zip_ref.extractall(f'{name}/')
                    
                    # Zip dosyasını sil
                    os.remove(f'{name}.zip')
                    
                print(f"✅ {name} başarıyla indirildi")
                
            except Exception as e:
                print(f"❌ {name} işleme hatası: {e}")
                return False
        else:
            print(f"❌ {name} indirilemedi!")
            return False
    
    print("🎉 Gerçek SH17 Dataset başarıyla indirildi!")
    return True

def create_sh17_config():
    """SH17 dataset konfigürasyonu oluştur"""
    
    config = {
        'path': '../datasets/SH17',
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'nc': 17,  # number of classes
        'names': [
            'person', 'head', 'face', 'glasses', 'face_mask_medical',
            'face_guard', 'ear', 'earmuffs', 'hands', 'gloves',
            'foot', 'shoes', 'safety_vest', 'tools', 'helmet',
            'medical_suit', 'safety_suit'
        ]
    }
    
    with open('configs/SH17.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print("✅ SH17 konfigürasyonu oluşturuldu")

def verify_dataset():
    """Dataset'i doğrula"""
    print("🔍 Dataset doğrulaması...")
    
    required_files = [
        'configs/SH17.yaml',
        'images/train',
        'images/val',
        'labels/train',
        'labels/val'
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ {file_path} bulunamadı!")
            return False
    
    # Görüntü sayısını kontrol et
    train_images = len([f for f in os.listdir('images/train') if f.endswith(('.jpg', '.png', '.jpeg'))])
    val_images = len([f for f in os.listdir('images/val') if f.endswith(('.jpg', '.png', '.jpeg'))])
    
    print(f"✅ Dataset doğrulandı!")
    print(f"📊 İstatistikler:")
    print(f"- Train images: {train_images}")
    print(f"- Val images: {val_images}")
    
    return True

if __name__ == "__main__":
    if download_real_sh17():
        create_sh17_config()
        if verify_dataset():
            print("🎯 Gerçek SH17 Dataset hazırlığı tamamlandı!")
        else:
            print("❌ Dataset doğrulaması başarısız!")
    else:
        print("❌ Gerçek dataset indirme başarısız!")
        print("⚠️ Mock dataset kullanılacak...") 