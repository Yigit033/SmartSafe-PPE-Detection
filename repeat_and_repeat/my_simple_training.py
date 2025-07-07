import torch
from ultralytics import YOLO
from pathlib import Path



class MySimpleTraining:
    def __init__(self):
        """Basit training class"""
        print("🎯 My Simple Training başlatılıyor...")

        if torch.cuda.is_available():
            self.device = "cuda"
            print(f"✅ GPU bulundu: {torch.cuda.get_device_name()}")

        else:
            self.device = "cpu"
            print("❌ GPU bulunamadı, CPU kullanılıyor...")

    def create_model(self, model_name= "yolov8n.pt"):
        """Model oluşturma"""
        print(f"🔍 Model oluşturuluyor... {model_name}")

        model = YOLO(f"{model_name}.pt")
        model.to(self.device)

        return model
    
    def train_model(self, model,  epochs=5, batch_size=4):
        """Model eğitimi"""
        train_args = {
            'data': 'yolov8n.pt',  # Placeholder - normalde dataset path
            'epochs': epochs,       # ← KAÇ EPOCH?
            'batch': batch_size,    # ← BATCH SIZE?
            'device': self.device,  # ← GPU/CPU
            'imgsz': 640,          # ← Image size
            'verbose': True,       # ← Detaylı log
            'plots': True         # ← Grafikler göster
        }

        print(f"🔍 Model eğitiliyor... {train_args}")

        for key, value in train_args.items():
            print(f"   {key}: {value}")
        
        try:
            # ANA TRAINING ÇAĞRıSı - BU ÖNEMLİ!
            results = model.train(**train_args)
            
            print("✅ Training tamamlandı!")
            return results
            
        except Exception as e:
            print(f"❌ Training hatası: {e}")
            return None

    def test_different_parameters(self):
        """Farklı parametreleri test et"""
        print("🧪 Parametre testleri...")
        
        # Model oluştur
        model = self.create_model('yolov8n')
        
        # Test 1: Farklı epoch sayıları
        epoch_tests = [2, 5, 10]
        
        for epochs in epoch_tests:
            print(f"\n📊 Test: {epochs} epochs")
            
            # Training parametrelerini göster
            print(f"   Epochs: {epochs}")
            print(f"   Batch: 4")
            print(f"   Device: {self.device}")
            
            # Not: Gerçek training yapmıyoruz, sadece parametreleri anlıyoruz
            print(f"   ✅ {epochs} epoch training'i başlatılabilir")

# TEST ET
if __name__ == "__main__":
    trainer = MySimpleTraining()
    
    print("\n" + "="*50)
    print("🎯 TRAINING KAVRAMLARI ÖĞRENİMİ")
    print("="*50)
    
    # Model test
    model = trainer.create_model('yolov8n')
    
    # Parametre testleri
    trainer.test_different_parameters()
    
    print("\n🎉 Training temel kavramları öğrenildi!")



"""📚 ÖĞRENME SORULARI
1. Epoch Nedir?
Epoch: Tüm dataset üzerinden 1 kez geçmek
5 epoch = Dataset'i 5 kez görmek
Fazla epoch = Overfitting riski
Az epoch = Underfitting riski

2. Batch Size Nedir?
Batch: Aynı anda işlenen resim sayısı
batch=4 = 4 resim birden işle
Büyük batch = Daha fazla GPU memory
Küçük batch = Daha az memory, daha slow

3. Learning Rate Nedir?
Learning rate: Modelin ne kadar hızla öğreneceği
0.01 = Normal hız
0.1 = Çok hızlı (loss explode edebilir)
0.001 = Yavaş ama güvenli

"""