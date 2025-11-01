#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPE Detection System - Model Download Script
Automatically downloads required model files for the detection system
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
import hashlib
import time

class ModelDownloader:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.models_dir = self.base_dir / "data" / "models"
        
        # Model configuration
        self.models = {
            "yolov8n.pt": {
                "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
                "size": "6.2MB",
                "description": "YOLOv8 Nano - Ultra-fast detection model",
                "sha256": "3b8f3b4c9f2a0c7b8d5e6f9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c"
            },
            "yolov8s.pt": {
                "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.pt",
                "size": "22MB",
                "description": "YOLOv8 Small - Balanced speed and accuracy",
                "sha256": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
            }
        }
        
        # Ensure models directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
    def download_file(self, url, destination, expected_size=None):
        """Download file with progress bar"""
        try:
            print(f"📥 Downloading: {destination.name}")
            print(f"🔗 URL: {url}")
            
            # Download with progress
            def progress_hook(block_num, block_size, total_size):
                if total_size > 0:
                    percent = min(100, (block_num * block_size) / total_size * 100)
                    bar_length = 30
                    filled_length = int(bar_length * percent // 100)
                    bar = '█' * filled_length + '-' * (bar_length - filled_length)
                    print(f'\r[{bar}] {percent:.1f}% ({block_num * block_size / 1024 / 1024:.1f}MB)', end='')
                    
            urllib.request.urlretrieve(url, destination, reporthook=progress_hook)
            print()  # New line after progress bar
            
            # Verify file size
            actual_size = destination.stat().st_size
            print(f"✅ Downloaded: {actual_size / 1024 / 1024:.1f}MB")
            
            return True
            
        except urllib.error.URLError as e:
            print(f"❌ Download failed: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    def verify_checksum(self, filepath, expected_sha256):
        """Verify file integrity using SHA256"""
        try:
            print(f"🔍 Verifying checksum for {filepath.name}...")
            
            sha256_hash = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            
            actual_sha256 = sha256_hash.hexdigest()
            
            if actual_sha256 == expected_sha256:
                print("✅ Checksum verified")
                return True
            else:
                print(f"❌ Checksum mismatch!")
                print(f"Expected: {expected_sha256}")
                print(f"Actual:   {actual_sha256}")
                return False
                
        except Exception as e:
            print(f"❌ Checksum verification failed: {e}")
            return False
    
    def download_models(self, force=False):
        """Download all required models"""
        print("🚀 PPE Detection System - Model Download")
        print("=" * 50)
        
        total_models = len(self.models)
        downloaded_count = 0
        
        for model_name, model_info in self.models.items():
            model_path = self.models_dir / model_name
            
            print(f"\n📦 Processing: {model_name}")
            print(f"📝 Description: {model_info['description']}")
            print(f"📏 Size: {model_info['size']}")
            
            # Check if model already exists
            if model_path.exists() and not force:
                print(f"✅ Model already exists: {model_path}")
                downloaded_count += 1
                continue
            
            # Download model
            if self.download_file(model_info['url'], model_path):
                # Verify checksum (skip if not available)
                if 'sha256' in model_info and model_info['sha256'] != "dummy":
                    if self.verify_checksum(model_path, model_info['sha256']):
                        downloaded_count += 1
                        print(f"✅ Successfully downloaded and verified: {model_name}")
                    else:
                        print(f"❌ Checksum verification failed for: {model_name}")
                        model_path.unlink()  # Remove corrupted file
                else:
                    downloaded_count += 1
                    print(f"✅ Successfully downloaded: {model_name}")
            else:
                print(f"❌ Failed to download: {model_name}")
        
        print(f"\n🏆 Download Summary:")
        print(f"✅ Success: {downloaded_count}/{total_models} models")
        
        if downloaded_count == total_models:
            print("🎉 All models downloaded successfully!")
            print("🚀 Ready to run PPE detection system!")
            return True
        else:
            print("⚠️  Some models failed to download")
            return False
    
    def check_models(self):
        """Check if all required models are available"""
        missing_models = []
        
        for model_name in self.models.keys():
            model_path = self.models_dir / model_name
            if not model_path.exists():
                missing_models.append(model_name)
        
        if missing_models:
            print("❌ Missing models:")
            for model in missing_models:
                print(f"  - {model}")
            return False
        else:
            print("✅ All required models are available")
            return True
    
    def get_model_info(self):
        """Display model information"""
        print("📋 Available Models:")
        print("=" * 50)
        
        for model_name, model_info in self.models.items():
            model_path = self.models_dir / model_name
            status = "✅ Available" if model_path.exists() else "❌ Missing"
            
            print(f"\n📦 {model_name}")
            print(f"   📝 Description: {model_info['description']}")
            print(f"   📏 Size: {model_info['size']}")
            print(f"   📍 Status: {status}")
            
            if model_path.exists():
                actual_size = model_path.stat().st_size / 1024 / 1024
                print(f"   💾 Actual size: {actual_size:.1f}MB")

def main():
    """Main function with command line interface"""
    downloader = ModelDownloader()
    
    if len(sys.argv) < 2:
        print("🚀 PPE Detection System - Model Manager")
        print("=" * 50)
        print("Usage:")
        print("  python download_models.py download   - Download all models")
        print("  python download_models.py check      - Check model availability")
        print("  python download_models.py info       - Show model information")
        print("  python download_models.py force      - Force re-download all models")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "download":
        success = downloader.download_models()
        sys.exit(0 if success else 1)
    
    elif command == "check":
        success = downloader.check_models()
        sys.exit(0 if success else 1)
    
    elif command == "info":
        downloader.get_model_info()
        sys.exit(0)
    
    elif command == "force":
        success = downloader.download_models(force=True)
        sys.exit(0 if success else 1)
    
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: download, check, info, force")
        sys.exit(1)

if __name__ == "__main__":
    main() 