#!/usr/bin/env python3
"""
SH17 Dataset Download Script
SmartSafe AI - PPE Detection Dataset
"""

import os
import requests
import zipfile
import yaml
from pathlib import Path

def download_sh17_dataset():
    """SH17 dataset'ini indir ve hazırla"""
    
    print("🚀 SH17 Dataset İndirme Başlıyor...")
    
    # Dataset URL'leri
    dataset_urls = {
        'images': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/download/v1.0/SH17_images.zip',
        'labels': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/download/v1.0/SH17_labels.zip',
        'config': 'https://github.com/SmartSafe-AI/SH17-dataset/releases/download/v1.0/SH17.yaml'
    }
    
    # Klasör yapısı oluştur
    folders = ['images', 'labels', 'configs']
    for folder in folders:
        Path(folder).mkdir(exist_ok=True)
    
    # Dataset indir
    for name, url in dataset_urls.items():
        print(f"📥 {name} indiriliyor...")
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
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
            print(f"❌ {name} indirme hatası: {e}")
            return False
    
    print("🎉 SH17 Dataset başarıyla indirildi!")
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

if __name__ == "__main__":
    if download_sh17_dataset():
        create_sh17_config()
        print("🎯 SH17 Dataset hazırlığı tamamlandı!")
    else:
        print("❌ Dataset indirme başarısız!") 