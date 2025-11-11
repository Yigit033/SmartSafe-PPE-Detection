#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPE Detection System - Model Download Script
Automatically downloads required model files for the detection system
Production-ready with proper error handling and logging
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
import hashlib
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ModelDownloader:
    def __init__(self):
        # Determine base directory - works in both local and Docker environments
        self.base_dir = Path(__file__).parent.resolve()
        
        # Create models directory in standard location
        self.models_dir = self.base_dir / "data" / "models"
        
        # Also support /app/data/models for Docker
        if os.path.exists('/app'):
            self.docker_models_dir = Path('/app/data/models')
            self.docker_models_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.docker_models_dir = None
        
        # Model configuration - YOLOv8 models for production
        self.models = {
            "yolov8n.pt": {
                "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
                "size": "6.2MB",
                "description": "YOLOv8 Nano - Ultra-fast detection model",
            },
            "yolov8s.pt": {
                "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt",
                "size": "22MB",
                "description": "YOLOv8 Small - Balanced speed and accuracy",
            },
            "yolov8m.pt": {
                "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt",
                "size": "49MB",
                "description": "YOLOv8 Medium - Higher accuracy",
            }
        }
        
        # Ensure models directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Models directory: {self.models_dir}")
        
    def download_file(self, url, destination, expected_size=None):
        """Download file with progress bar and retry logic"""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"📥 Downloading (attempt {attempt + 1}/{max_retries}): {destination.name}")
                logger.info(f"🔗 URL: {url}")
                
                # Download with progress
                def progress_hook(block_num, block_size, total_size):
                    if total_size > 0:
                        percent = min(100, (block_num * block_size) / total_size * 100)
                        bar_length = 30
                        filled_length = int(bar_length * percent // 100)
                        bar = '█' * filled_length + '-' * (bar_length - filled_length)
                        print(f'\r[{bar}] {percent:.1f}% ({block_num * block_size / 1024 / 1024:.1f}MB)', end='', flush=True)
                
                urllib.request.urlretrieve(url, destination, reporthook=progress_hook)
                print()  # New line after progress bar
                
                # Verify file exists and has content
                if destination.exists():
                    actual_size = destination.stat().st_size
                    if actual_size > 1000000:  # At least 1MB
                        logger.info(f"✅ Downloaded: {actual_size / 1024 / 1024:.1f}MB")
                        return True
                    else:
                        logger.warning(f"⚠️ File too small: {actual_size} bytes, retrying...")
                        destination.unlink()
                        
            except urllib.error.URLError as e:
                logger.warning(f"⚠️ Download failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                continue
            except Exception as e:
                logger.warning(f"⚠️ Unexpected error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue
        
        logger.error(f"❌ Failed to download after {max_retries} attempts: {destination.name}")
        return False
    
    def download_models(self, force=False):
        """Download all required models"""
        logger.info("=" * 60)
        logger.info("🚀 PPE Detection System - Model Download")
        logger.info("=" * 60)
        
        total_models = len(self.models)
        downloaded_count = 0
        
        for model_name, model_info in self.models.items():
            model_path = self.models_dir / model_name
            
            logger.info(f"\n📦 Processing: {model_name}")
            logger.info(f"📝 Description: {model_info['description']}")
            logger.info(f"📏 Size: {model_info['size']}")
            
            # Check if model already exists
            if model_path.exists() and not force:
                file_size = model_path.stat().st_size / 1024 / 1024
                logger.info(f"✅ Model already exists: {model_path} ({file_size:.1f}MB)")
                downloaded_count += 1
                
                # Also copy to Docker location if needed
                if self.docker_models_dir and self.docker_models_dir != self.models_dir:
                    docker_model_path = self.docker_models_dir / model_name
                    if not docker_model_path.exists():
                        try:
                            import shutil
                            shutil.copy2(model_path, docker_model_path)
                            logger.info(f"📋 Copied to Docker location: {docker_model_path}")
                        except Exception as e:
                            logger.warning(f"⚠️ Could not copy to Docker location: {e}")
                continue
            
            # Download model
            if self.download_file(model_info['url'], model_path):
                downloaded_count += 1
                logger.info(f"✅ Successfully downloaded: {model_name}")
                
                # Also copy to Docker location if needed
                if self.docker_models_dir and self.docker_models_dir != self.models_dir:
                    docker_model_path = self.docker_models_dir / model_name
                    try:
                        import shutil
                        shutil.copy2(model_path, docker_model_path)
                        logger.info(f"📋 Copied to Docker location: {docker_model_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not copy to Docker location: {e}")
            else:
                logger.error(f"❌ Failed to download: {model_name}")
        
        logger.info("\n" + "=" * 60)
        logger.info(f"🏆 Download Summary:")
        logger.info(f"✅ Success: {downloaded_count}/{total_models} models")
        logger.info("=" * 60)
        
        if downloaded_count == total_models:
            logger.info("🎉 All models downloaded successfully!")
            logger.info("🚀 Ready to run PPE detection system!")
            return True
        elif downloaded_count > 0:
            logger.warning("⚠️ Some models failed to download, but system can continue with available models")
            return True  # Allow partial success
        else:
            logger.error("❌ No models downloaded - system may not work properly")
            return False
    
    def check_models(self):
        """Check if all required models are available"""
        missing_models = []
        available_models = []
        
        for model_name in self.models.keys():
            model_path = self.models_dir / model_name
            if model_path.exists():
                size_mb = model_path.stat().st_size / 1024 / 1024
                available_models.append(f"{model_name} ({size_mb:.1f}MB)")
            else:
                missing_models.append(model_name)
        
        logger.info("=" * 60)
        logger.info("📋 Model Status Report")
        logger.info("=" * 60)
        
        if available_models:
            logger.info("✅ Available models:")
            for model in available_models:
                logger.info(f"   - {model}")
        
        if missing_models:
            logger.warning("❌ Missing models:")
            for model in missing_models:
                logger.warning(f"   - {model}")
            return False
        else:
            logger.info("✅ All required models are available")
            return True
    
    def get_model_info(self):
        """Display model information"""
        logger.info("=" * 60)
        logger.info("📋 Available Models Information")
        logger.info("=" * 60)
        
        for model_name, model_info in self.models.items():
            model_path = self.models_dir / model_name
            status = "✅ Available" if model_path.exists() else "❌ Missing"
            
            logger.info(f"\n📦 {model_name}")
            logger.info(f"   📝 Description: {model_info['description']}")
            logger.info(f"   📏 Size: {model_info['size']}")
            logger.info(f"   📍 Status: {status}")
            
            if model_path.exists():
                actual_size = model_path.stat().st_size / 1024 / 1024
                logger.info(f"   💾 Actual size: {actual_size:.1f}MB")

def main():
    """Main function with command line interface"""
    downloader = ModelDownloader()
    
    if len(sys.argv) < 2:
        # Default: download models
        success = downloader.download_models()
        sys.exit(0 if success else 1)
    
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
        logger.error(f"❌ Unknown command: {command}")
        logger.info("Available commands: download, check, info, force")
        sys.exit(1)

if __name__ == "__main__":
    main()
