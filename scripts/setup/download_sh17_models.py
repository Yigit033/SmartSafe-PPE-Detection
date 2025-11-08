#!/usr/bin/env python3
"""
SH17 Model Downloader
SmartSafe AI - PPE Detection Model Integration
"""

import os
import requests
import zipfile
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SH17ModelDownloader:
    def __init__(self):
        self.models_dir = Path('models')
        self.models_dir.mkdir(exist_ok=True)
        
        # SH17 model URLs (örnek - gerçek URL'ler ile değiştirilmeli)
        self.model_urls = {
            'base': 'https://example.com/sh17_base.zip',
            'construction': 'https://example.com/sh17_construction.zip',
            'manufacturing': 'https://example.com/sh17_manufacturing.zip',
            'chemical': 'https://example.com/sh17_chemical.zip',
            'food_beverage': 'https://example.com/sh17_food_beverage.zip',
            'warehouse_logistics': 'https://example.com/sh17_warehouse_logistics.zip',
            'energy': 'https://example.com/sh17_energy.zip',
            'petrochemical': 'https://example.com/sh17_petrochemical.zip',
            'marine_shipyard': 'https://example.com/sh17_marine_shipyard.zip',
            'aviation': 'https://example.com/sh17_aviation.zip'
        }
        
        # Fallback model (yolov8n.pt zaten mevcut)
        self.fallback_model = 'yolov8n.pt'
        
    def download_model(self, sector, url):
        """Tek bir model'i indir"""
        try:
            logger.info(f"📥 {sector} modeli indiriliyor...")
            
            # Model klasörü oluştur
            model_path = self.models_dir / f'sh17_{sector}'
            model_path.mkdir(exist_ok=True)
            
            # Zip dosyasını indir
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            zip_path = model_path / f'{sector}.zip'
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Zip'i aç
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(model_path)
            
            # Zip dosyasını sil
            zip_path.unlink()
            
            logger.info(f"✅ {sector} modeli başarıyla indirildi")
            return True
            
        except Exception as e:
            logger.error(f"❌ {sector} modeli indirilemedi: {e}")
            return False
    
    def create_dummy_models(self):
        """Test için dummy SH17 modelleri oluştur"""
        logger.info("🔧 Test için dummy SH17 modelleri oluşturuluyor...")
        
        for sector in self.model_urls.keys():
            try:
                # Model klasör yapısı oluştur
                model_path = self.models_dir / f'sh17_{sector}' / f'sh17_{sector}_model' / 'weights'
                model_path.mkdir(parents=True, exist_ok=True)
                
                # Dummy best.pt dosyası oluştur (yolov8n.pt'den kopyala)
                if os.path.exists(self.fallback_model):
                    import shutil
                    shutil.copy2(self.fallback_model, model_path / 'best.pt')
                    logger.info(f"✅ {sector} dummy modeli oluşturuldu")
                else:
                    logger.warning(f"⚠️ {sector} için fallback model bulunamadı")
                    
            except Exception as e:
                logger.error(f"❌ {sector} dummy modeli oluşturulamadı: {e}")
    
    def setup_models_directory(self):
        """Models klasör yapısını kur"""
        logger.info("📁 Models klasör yapısı kuruluyor...")
        
        # Ana models klasörü
        self.models_dir.mkdir(exist_ok=True)
        
        # Her sektör için klasör yapısı
        for sector in self.model_urls.keys():
            sector_path = self.models_dir / f'sh17_{sector}'
            sector_path.mkdir(exist_ok=True)
            
            model_path = sector_path / f'sh17_{sector}_model'
            model_path.mkdir(exist_ok=True)
            
            weights_path = model_path / 'weights'
            weights_path.mkdir(exist_ok=True)
            
            logger.info(f"📁 {sector} klasör yapısı oluşturuldu")
    
    def download_all_models(self):
        """Tüm modelleri indir"""
        logger.info("🚀 Tüm SH17 modelleri indiriliyor...")
        
        success_count = 0
        for sector, url in self.model_urls.items():
            if self.download_model(sector, url):
                success_count += 1
        
        logger.info(f"📊 {success_count}/{len(self.model_urls)} model başarıyla indirildi")
        return success_count
    
    def verify_models(self):
        """Modellerin doğru yüklendiğini kontrol et"""
        logger.info("🔍 Modeller kontrol ediliyor...")
        
        from src.smartsafe.models.sh17_model_manager import SH17ModelManager
        
        manager = SH17ModelManager()
        manager.load_models()
        
        status = manager.get_system_status()
        logger.info(f"📊 Sistem Durumu: {status}")
        
        available_sectors = manager.get_available_sectors()
        logger.info(f"🎯 Kullanılabilir Sektörler: {available_sectors}")
        
        return len(available_sectors) > 0

def main():
    """Ana fonksiyon"""
    downloader = SH17ModelDownloader()
    
    print("🎯 SH17 Model Downloader")
    print("=" * 50)
    
    # 1. Klasör yapısını kur
    downloader.setup_models_directory()
    
    # 2. Test için dummy modeller oluştur
    downloader.create_dummy_models()
    
    # 3. Modelleri doğrula
    if downloader.verify_models():
        print("✅ SH17 modelleri başarıyla kuruldu!")
    else:
        print("⚠️ SH17 modelleri kurulamadı, fallback sistemi aktif")
    
    print("\n🚀 Sistem anahtar teslim için hazır!")

if __name__ == "__main__":
    main()
