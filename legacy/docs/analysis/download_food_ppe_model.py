#!/usr/bin/env python3
"""
PPE Food Manufacturing Model İndirme Scripti
============================================
Roboflow'dan gıda sektörü için PPE modelini indirir.

Sınıflar: Mask, Apron, gloves, Googles, Haircap
Kaynak: https://universe.roboflow.com/rahma-5lrz6/ppe-food-manufacturing

Kullanım:
  1. https://app.roboflow.com adresine giriş yap (ücretsiz hesap)
  2. Account > Settings > API Keys bölümünden Private API Key kopyala
  3. Bu scripti çalıştır:
     python download_food_ppe_model.py --api-key YOUR_KEY

Not: Script modeli otomatik olarak models/food_ppe/ klasörüne kaydeder.
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path


MODELS_DIR = Path(__file__).parent / "models"
FOOD_PPE_DIR = MODELS_DIR / "sh17_food_beverage" / "sh17_food_beverage_model" / "weights"
ROBOFLOW_PROJECT = "ppe-food-manufacturing"
ROBOFLOW_WORKSPACE = "rahma-5lrz6"
ROBOFLOW_VERSION = 5   # Dataset v5 (en güncel)
EXPORT_FORMAT = "yolov8"


def check_roboflow():
    """roboflow paketini kontrol et, yoksa kur."""
    try:
        import roboflow
        return True
    except ImportError:
        print("📦 roboflow paketi kuruluyor...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "roboflow", "-q"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ roboflow paketi kuruldu")
            return True
        else:
            print(f"❌ roboflow kurulum hatası: {result.stderr}")
            return False


def download_dataset(api_key: str):
    """Dataset'i indir ve YOLO formatında kaydet."""
    if not check_roboflow():
        return False

    from roboflow import Roboflow

    print(f"\n🔗 Roboflow'a bağlanılıyor...")
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)

    print(f"📥 Dataset v{ROBOFLOW_VERSION} indiriliyor ({EXPORT_FORMAT} formatında)...")

    FOOD_PPE_DIR.mkdir(parents=True, exist_ok=True)

    dataset = project.version(ROBOFLOW_VERSION).download(
        EXPORT_FORMAT,
        location=str(FOOD_PPE_DIR.parent.parent.parent),  # models/sh17_food_beverage/
        overwrite=True
    )

    print(f"✅ Dataset indirildi: {dataset.location}")
    print(f"\n📋 Sınıflar: Mask, Apron, gloves, Googles, Haircap")
    print(f"\n⚠️  Modeli kullanmak için eğitim gerekiyor!")
    print(f"   Eğitim komutu:")
    print(f"   yolo train data={dataset.location}/data.yaml model=yolov8n.pt epochs=50 imgsz=640")
    print(f"\n   Eğitim sonrası best.pt dosyasını şuraya kopyala:")
    print(f"   {FOOD_PPE_DIR}/best.pt")
    return dataset.location


def use_roboflow_api(api_key: str):
    """
    Eğitim yapmadan Roboflow API'sini inference için kullan.
    Bu seçenek yerel model yerine API'ya istek atar (internet gerektirir).
    """
    print("\n🌐 Roboflow API modu seçildi")
    print("   Model ID: ppe-food-manufacturing/3")
    print("   Endpoint: https://detect.roboflow.com/ppe-food-manufacturing/3")
    print("\n   Bu modu kullanmak için .env dosyasına ekle:")
    print(f"   ROBOFLOW_API_KEY={api_key}")
    print("   FOOD_PPE_API_MODEL=ppe-food-manufacturing/3")

    # .env dosyasını güncelle
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            content = f.read()
        if "ROBOFLOW_API_KEY" not in content:
            with open(env_path, "a") as f:
                f.write(f"\n# Gıda Sektörü Food PPE Model (Roboflow API)\n")
                f.write(f"ROBOFLOW_API_KEY={api_key}\n")
                f.write(f"FOOD_PPE_API_MODEL=ppe-food-manufacturing/3\n")
            print("\n✅ .env dosyası güncellendi!")
        else:
            print("\n⚠️  ROBOFLOW_API_KEY zaten .env içinde var")


def main():
    parser = argparse.ArgumentParser(description="PPE Food Manufacturing Model İndirici")
    parser.add_argument("--api-key", required=True, help="Roboflow Private API Key")
    parser.add_argument(
        "--mode",
        choices=["dataset", "api"],
        default="api",
        help="'dataset': Dataset indir + eğit | 'api': Roboflow API inference (default: api)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SmartSafe - Gıda Sektörü PPE Model Kurulumu")
    print("=" * 60)

    if args.mode == "api":
        use_roboflow_api(args.api_key)
        print("\n✅ API modu yapılandırıldı. Uygulamayı yeniden başlat.")
    else:
        result = download_dataset(args.api_key)
        if result:
            print(f"\n✅ Dataset hazır: {result}")
            print("⏳ Eğitim tamamlandıktan sonra best.pt dosyasını ilgili dizine kopyala.")
        else:
            print("\n❌ İndirme başarısız.")
            sys.exit(1)


if __name__ == "__main__":
    main()
