#!/usr/bin/env python3
"""
SH17 Dataset Training Script
SmartSafe AI - PPE Detection Model Training
"""

import os
import sys
import yaml
import torch
import subprocess
from pathlib import Path
from ultralytics import YOLO

class SH17Trainer:
    def __init__(self, config_path='datasets/SH17/configs/SH17.yaml'):
        self.config_path = config_path
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"🎯 Training Device: {self.device}")
        
    def validate_dataset(self):
        """Dataset'in doğruluğunu kontrol et"""
        print("🔍 Dataset doğrulaması...")
        
        if not os.path.exists(self.config_path):
            print(f"❌ Config dosyası bulunamadı: {self.config_path}")
            return False
            
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Klasörleri kontrol et
        required_folders = ['images/train', 'images/val', 'labels/train', 'labels/val']
        for folder in required_folders:
            full_path = os.path.join(os.path.dirname(self.config_path), folder)
            if not os.path.exists(full_path):
                print(f"❌ Klasör bulunamadı: {full_path}")
                return False
                
        print("✅ Dataset doğrulaması başarılı")
        return True
        
    def train_base_model(self, epochs=100, batch_size=16):
        """SH17 dataset ile base model training"""
        print(f"🚀 Base Model Training Başlıyor...")
        print(f"📊 Epochs: {epochs}, Batch Size: {batch_size}")
        
        # YOLOv8 model yükle
        model = YOLO('yolov8n.pt')  # nano model ile başla
        
        # Training parametreleri
        results = model.train(
            data=self.config_path,
            epochs=epochs,
            batch=batch_size,
            imgsz=640,
            device=self.device,
            workers=4,
            patience=20,
            save=True,
            save_period=10,
            project='training/sh17_base',
            name='sh17_base_model',
            exist_ok=True
        )
        
        print("✅ Base model training tamamlandı!")
        return results
        
    def train_sector_specific(self, base_model_path, sector, epochs=50):
        """Sektör spesifik fine-tuning"""
        print(f"🎯 {sector} sektörü için fine-tuning...")
        
        # Sektör konfigürasyonu - TÜM SEKTÖRLER
        sector_configs = {
            'construction': {
                'classes': ['helmet', 'safety_vest', 'safety_shoes', 'gloves'],
                'focus_ratio': 0.8
            },
            'manufacturing': {
                'classes': ['helmet', 'safety_vest', 'gloves', 'safety_glasses'],
                'focus_ratio': 0.8
            },
            'chemical': {
                'classes': ['helmet', 'respirator', 'gloves', 'safety_glasses', 'medical_suit'],
                'focus_ratio': 0.9
            },
            'food_beverage': {
                'classes': ['helmet', 'safety_vest', 'gloves', 'safety_glasses', 'face_mask_medical'],
                'focus_ratio': 0.85
            },
            'warehouse_logistics': {
                'classes': ['helmet', 'safety_vest', 'gloves', 'safety_shoes'],
                'focus_ratio': 0.8
            },
            'energy': {
                'classes': ['helmet', 'safety_vest', 'safety_shoes', 'gloves', 'safety_suit'],
                'focus_ratio': 0.9
            },
            'petrochemical': {
                'classes': ['helmet', 'respirator', 'safety_vest', 'gloves', 'safety_suit', 'safety_glasses'],
                'focus_ratio': 0.95
            },
            'marine_shipyard': {
                'classes': ['helmet', 'safety_vest', 'gloves', 'safety_shoes', 'safety_glasses'],
                'focus_ratio': 0.9
            },
            'aviation': {
                'classes': ['helmet', 'safety_vest', 'gloves', 'safety_glasses', 'face_mask_medical'],
                'focus_ratio': 0.95
            }
        }
        
        if sector not in sector_configs:
            print(f"❌ Bilinmeyen sektör: {sector}")
            return None
            
        config = sector_configs[sector]
        
        # Fine-tuning
        model = YOLO(base_model_path)
        results = model.train(
            data=self.config_path,
            epochs=epochs,
            batch=8,
            imgsz=640,
            device=self.device,
            workers=4,
            patience=15,
            save=True,
            save_period=5,
            project=f'training/sh17_{sector}',
            name=f'sh17_{sector}_model',
            exist_ok=True,
            # Sektör spesifik parametreler
            classes=config['classes'],
            overlap_mask=True,
            mask_ratio=4
        )
        
        print(f"✅ {sector} sektörü fine-tuning tamamlandı!")
        return results
        
    def evaluate_model(self, model_path):
        """Model performansını değerlendir"""
        print(f"📊 Model değerlendirmesi: {model_path}")
        
        model = YOLO(model_path)
        results = model.val(
            data=self.config_path,
            device=self.device,
            conf=0.25,
            iou=0.5
        )
        
        print("✅ Model değerlendirmesi tamamlandı!")
        return results

def main():
    """Ana training süreci"""
    print("🎯 SmartSafe AI - SH17 Training Pipeline")
    print("=" * 50)
    
    trainer = SH17Trainer()
    
    # 1. Dataset doğrulama
    if not trainer.validate_dataset():
        print("❌ Dataset doğrulaması başarısız!")
        return
        
    # 2. Base model training
    print("\n🚀 1. ADIM: Base Model Training")
    base_results = trainer.train_base_model(epochs=100, batch_size=16)
    
    if base_results is None:
        print("❌ Base model training başarısız!")
        return
        
    # 3. Sektör spesifik fine-tuning - TÜM SEKTÖRLER
    sectors = ['construction', 'manufacturing', 'chemical', 'food_beverage', 'warehouse_logistics', 'energy', 'petrochemical', 'marine_shipyard', 'aviation']
    base_model_path = 'training/sh17_base/sh17_base_model/weights/best.pt'
    
    for sector in sectors:
        print(f"\n🎯 2. ADIM: {sector.upper()} Sektörü Fine-tuning")
        sector_results = trainer.train_sector_specific(
            base_model_path=base_model_path,
            sector=sector,
            epochs=50
        )
        
        if sector_results:
            # Model değerlendirmesi
            sector_model_path = f'training/sh17_{sector}/sh17_{sector}_model/weights/best.pt'
            trainer.evaluate_model(sector_model_path)
    
    print("\n🎉 Tüm training süreçleri tamamlandı!")
    print("📁 Modeller şu klasörlerde:")
    print("- Base Model: training/sh17_base/")
    print("- Construction: training/sh17_construction/")
    print("- Manufacturing: training/sh17_manufacturing/")
    print("- Chemical: training/sh17_chemical/")
    print("- Food & Beverage: training/sh17_food_beverage/")
    print("- Warehouse/Logistics: training/sh17_warehouse_logistics/")
    print("- Energy: training/sh17_energy/")
    print("- Petrochemical: training/sh17_petrochemical/")
    print("- Marine & Shipyard: training/sh17_marine_shipyard/")
    print("- Aviation: training/sh17_aviation/")

if __name__ == "__main__":
    main() 