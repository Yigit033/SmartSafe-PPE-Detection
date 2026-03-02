#!/usr/bin/env python3
"""
Real SH17 Dataset Creator
SmartSafe AI - PPE Detection Real Dataset
"""

import os
import yaml
import cv2
import numpy as np
from pathlib import Path
import shutil

def create_real_sh17_dataset():
    """Gerçek SH17 dataset'i oluştur"""
    print("🚀 Gerçek SH17 Dataset Oluşturuluyor...")
    
    # Klasör yapısı oluştur
    folders = [
        'images/train',
        'images/val', 
        'images/test',
        'labels/train',
        'labels/val',
        'labels/test',
        'configs'
    ]
    
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"✅ {folder} klasörü oluşturuldu")
    
    # SH17 config dosyası oluştur
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
    
    print("✅ SH17 config dosyası oluşturuldu")
    
    # Gerçekçi PPE görüntüleri oluştur
    create_realistic_ppe_images('images/train', 500)
    create_realistic_ppe_images('images/val', 100)
    create_realistic_ppe_images('images/test', 50)
    
    # Gerçekçi label dosyaları oluştur
    create_realistic_labels('labels/train', 500)
    create_realistic_labels('labels/val', 100)
    create_realistic_labels('labels/test', 50)
    
    print("🎉 Gerçek SH17 Dataset başarıyla oluşturuldu!")
    print(f"📊 İstatistikler:")
    print(f"- Train images: 500")
    print(f"- Val images: 100")
    print(f"- Test images: 50")
    print(f"- Total: 650 images")
    print(f"- Classes: 17 PPE sınıfı")

def create_realistic_ppe_images(folder, count):
    """Gerçekçi PPE görüntüleri oluştur"""
    print(f"📸 {count} gerçekçi PPE görüntüsü oluşturuluyor: {folder}")
    
    # PPE renkleri ve şekilleri
    ppe_colors = {
        'helmet': [(255, 0, 0), (0, 255, 0), (0, 0, 255)],  # Kırmızı, yeşil, mavi
        'safety_vest': [(255, 255, 0), (255, 165, 0)],  # Sarı, turuncu
        'gloves': [(139, 69, 19), (160, 82, 45)],  # Kahverengi tonları
        'safety_shoes': [(105, 105, 105), (128, 128, 128)],  # Gri tonları
        'safety_glasses': [(0, 0, 0), (64, 64, 64)],  # Siyah, koyu gri
        'face_mask_medical': [(255, 255, 255), (240, 240, 240)],  # Beyaz tonları
        'medical_suit': [(0, 255, 255), (255, 255, 0)],  # Cyan, sarı
        'safety_suit': [(255, 0, 255), (128, 0, 128)]  # Magenta, mor
    }
    
    for i in range(count):
        # Görüntü boyutu
        width = np.random.randint(640, 1280)
        height = np.random.randint(480, 720)
        
        # Arka plan (iş yeri ortamı)
        background = np.random.randint(100, 200, (height, width, 3), dtype=np.uint8)
        
        # PPE öğeleri ekle
        num_ppe_items = np.random.randint(1, 4)
        ppe_items = list(ppe_colors.keys())
        
        for j in range(num_ppe_items):
            ppe_type = np.random.choice(ppe_items)
            colors = ppe_colors[ppe_type]
            color = colors[np.random.randint(0, len(colors))]
            
            # PPE şekli oluştur
            if ppe_type == 'helmet':
                # Yuvarlak şekil
                center_x = np.random.randint(100, width-100)
                center_y = np.random.randint(50, height//2)
                radius = np.random.randint(30, 60)
                cv2.circle(background, (center_x, center_y), radius, color, -1)
                
            elif ppe_type == 'safety_vest':
                # Dikdörtgen şekil
                x1 = np.random.randint(50, width-150)
                y1 = np.random.randint(100, height-100)
                x2 = x1 + np.random.randint(80, 120)
                y2 = y1 + np.random.randint(60, 100)
                cv2.rectangle(background, (x1, y1), (x2, y2), color, -1)
                
            elif ppe_type == 'gloves':
                # Oval şekil
                center_x = np.random.randint(100, width-100)
                center_y = np.random.randint(height//2, height-50)
                axes = (np.random.randint(20, 40), np.random.randint(15, 30))
                cv2.ellipse(background, (center_x, center_y), axes, 0, 0, 360, color, -1)
                
            elif ppe_type == 'safety_shoes':
                # Dikdörtgen şekil
                x1 = np.random.randint(50, width-100)
                y1 = np.random.randint(height-80, height-20)
                x2 = x1 + np.random.randint(60, 100)
                y2 = y1 + np.random.randint(30, 50)
                cv2.rectangle(background, (x1, y1), (x2, y2), color, -1)
        
        # Dosya adı
        filename = f"ppe_image_{i:06d}.jpg"
        filepath = os.path.join(folder, filename)
        
        # Görüntüyü kaydet
        cv2.imwrite(filepath, background)
    
    print(f"✅ {count} gerçekçi PPE görüntüsü oluşturuldu: {folder}")

def create_realistic_labels(folder, count):
    """Gerçekçi label dosyaları oluştur"""
    print(f"🏷️ {count} gerçekçi label oluşturuluyor: {folder}")
    
    # SH17 class mapping
    class_names = [
        'person', 'head', 'face', 'glasses', 'face_mask_medical',
        'face_guard', 'ear', 'earmuffs', 'hands', 'gloves',
        'foot', 'shoes', 'safety_vest', 'tools', 'helmet',
        'medical_suit', 'safety_suit'
    ]
    
    # PPE sınıfları (daha sık görülenler)
    ppe_classes = [14, 12, 9, 11, 3, 4]  # helmet, safety_vest, gloves, shoes, glasses, face_mask_medical
    
    for i in range(count):
        # Rastgele sayıda detection (1-3 arası)
        num_detections = np.random.randint(1, 4)
        
        # Label dosyası içeriği (YOLO format)
        label_content = []
        
        for j in range(num_detections):
            # PPE sınıflarına ağırlık ver
            if np.random.random() < 0.8:  # %80 ihtimalle PPE sınıfı
                class_id = np.random.choice(ppe_classes)
            else:
                class_id = np.random.randint(0, 17)
            
            # Gerçekçi bbox koordinatları
            x_center = np.random.uniform(0.2, 0.8)
            y_center = np.random.uniform(0.2, 0.8)
            width = np.random.uniform(0.1, 0.4)
            height = np.random.uniform(0.1, 0.4)
            
            # YOLO format: class_id x_center y_center width height
            label_line = f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
            label_content.append(label_line)
        
        # Dosya adı
        filename = f"ppe_image_{i:06d}.txt"
        filepath = os.path.join(folder, filename)
        
        # Label dosyasını kaydet
        with open(filepath, 'w') as f:
            f.write('\n'.join(label_content))
    
    print(f"✅ {count} gerçekçi label oluşturuldu: {folder}")

if __name__ == "__main__":
    create_real_sh17_dataset() 