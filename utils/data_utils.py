"""
Data utilities for PPE Detection System
Modern dataset handling with Roboflow integration
"""

import os
import yaml
import requests
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from urllib.parse import urlparse
import cv2
import numpy as np
from PIL import Image
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PPEDataLoader:
    """Modern data loader for PPE detection datasets"""
    
    def __init__(self, config_path: str = "configs/config.yaml"):
        """Initialize data loader with configuration"""
        self.config = self.load_config(config_path)
        self.data_dir = Path(self.config['paths']['dataset'])
        self.processed_dir = Path(self.config['paths']['processed_data'])
        
        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def load_config(config_path: str) -> Dict:
        """Load YAML configuration file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            return {}
    
    def download_roboflow_dataset(self, 
                                  workspace: str = "roboflow-jvuqo", 
                                  project: str = "construction-site-safety",
                                  version: int = 1,
                                  api_key: Optional[str] = None) -> bool:
        """
        Download PPE dataset from Roboflow
        Modern approach with proper error handling
        """
        try:
            # Roboflow dataset URL construction
            if api_key:
                url = f"https://universe.roboflow.com/{workspace}/{project}/dataset/{version}/download/yolov8"
                headers = {"Authorization": f"Bearer {api_key}"}
            else:
                # Public dataset URL (example)
                url = f"https://public.roboflow.com/{workspace}/{project}/dataset/{version}/download/yolov8"
                headers = {}
            
            logger.info(f"Downloading PPE dataset from Roboflow...")
            logger.info(f"URL: {url}")
            
            # Download with progress
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            # Save to data directory
            zip_path = self.data_dir / "ppe_dataset.zip"
            total_size = int(response.headers.get('content-length', 0))
            
            with open(zip_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\rDownloading: {progress:.1f}%", end="", flush=True)
            
            print("\nDownload completed!")
            
            # Extract dataset
            logger.info("Extracting dataset...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.data_dir)
            
            # Clean up zip file
            zip_path.unlink()
            
            logger.info("Dataset download and extraction completed!")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading dataset: {str(e)}")
            return False
    
    def create_sample_dataset(self) -> bool:
        """Create a sample dataset structure for testing"""
        try:
            # Create sample directory structure
            sample_dirs = [
                "train/images",
                "train/labels", 
                "valid/images",
                "valid/labels",
                "test/images",
                "test/labels"
            ]
            
            for dir_path in sample_dirs:
                (self.data_dir / dir_path).mkdir(parents=True, exist_ok=True)
            
            # Create data.yaml for YOLOv8
            data_yaml = {
                'path': str(self.data_dir.absolute()),
                'train': 'train/images',
                'val': 'valid/images', 
                'test': 'test/images',
                'names': {
                    0: 'person',
                    1: 'hard_hat',
                    2: 'safety_vest',
                    3: 'mask',
                    4: 'no_hard_hat',
                    5: 'no_safety_vest',
                    6: 'no_mask'
                },
                'nc': 7  # number of classes
            }
            
            with open(self.data_dir / "data.yaml", 'w') as f:
                yaml.dump(data_yaml, f, default_flow_style=False)
            
            logger.info("Sample dataset structure created!")
            return True
            
        except Exception as e:
            logger.error(f"Error creating sample dataset: {str(e)}")
            return False
    
    def validate_dataset(self) -> Dict[str, int]:
        """Validate dataset structure and count files"""
        stats = {
            'train_images': 0,
            'train_labels': 0,
            'valid_images': 0,
            'valid_labels': 0,
            'test_images': 0,
            'test_labels': 0
        }
        
        try:
            # Count files in each directory
            for split in ['train', 'valid', 'test']:
                img_dir = self.data_dir / split / 'images'
                label_dir = self.data_dir / split / 'labels'
                
                if img_dir.exists():
                    stats[f'{split}_images'] = len(list(img_dir.glob('*.[jJ][pP][gG]'))) + \
                                               len(list(img_dir.glob('*.[pP][nN][gG]')))
                
                if label_dir.exists():
                    stats[f'{split}_labels'] = len(list(label_dir.glob('*.txt')))
            
            logger.info(f"Dataset validation complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error validating dataset: {str(e)}")
            return stats
    
    def preprocess_images(self, target_size: Tuple[int, int] = (640, 640)) -> bool:
        """Preprocess images for training"""
        try:
            for split in ['train', 'valid', 'test']:
                img_dir = self.data_dir / split / 'images'
                processed_dir = self.processed_dir / split / 'images'
                processed_dir.mkdir(parents=True, exist_ok=True)
                
                if not img_dir.exists():
                    continue
                    
                image_files = list(img_dir.glob('*.[jJ][pP][gG]')) + \
                             list(img_dir.glob('*.[pP][nN][gG]'))
                
                for img_path in image_files:
                    try:
                        # Load and resize image
                        img = cv2.imread(str(img_path))
                        if img is None:
                            continue
                            
                        # Resize maintaining aspect ratio
                        h, w = img.shape[:2]
                        aspect_ratio = w / h
                        
                        if aspect_ratio > 1:
                            new_w = target_size[0]
                            new_h = int(target_size[0] / aspect_ratio)
                        else:
                            new_h = target_size[1]
                            new_w = int(target_size[1] * aspect_ratio)
                        
                        img_resized = cv2.resize(img, (new_w, new_h))
                        
                        # Pad to target size
                        pad_h = (target_size[1] - new_h) // 2
                        pad_w = (target_size[0] - new_w) // 2
                        
                        img_padded = cv2.copyMakeBorder(
                            img_resized, pad_h, target_size[1] - new_h - pad_h,
                            pad_w, target_size[0] - new_w - pad_w,
                            cv2.BORDER_CONSTANT, value=[114, 114, 114]
                        )
                        
                        # Save processed image
                        output_path = processed_dir / img_path.name
                        cv2.imwrite(str(output_path), img_padded)
                        
                    except Exception as e:
                        logger.warning(f"Error processing {img_path}: {str(e)}")
                        continue
            
            logger.info("Image preprocessing completed!")
            return True
            
        except Exception as e:
            logger.error(f"Error in image preprocessing: {str(e)}")
            return False

def get_dataset_statistics(data_dir: str) -> pd.DataFrame:
    """Get comprehensive dataset statistics"""
    try:
        data_path = Path(data_dir)
        stats_data = []
        
        for split in ['train', 'valid', 'test']:
            img_dir = data_path / split / 'images'
            label_dir = data_path / split / 'labels'
            
            if img_dir.exists() and label_dir.exists():
                images = list(img_dir.glob('*.[jJ][pP][gG]')) + \
                        list(img_dir.glob('*.[pP][nN][gG]'))
                labels = list(label_dir.glob('*.txt'))
                
                # Count class instances
                class_counts = {i: 0 for i in range(7)}
                
                for label_file in labels:
                    try:
                        with open(label_file, 'r') as f:
                            for line in f:
                                class_id = int(line.strip().split()[0])
                                if class_id in class_counts:
                                    class_counts[class_id] += 1
                    except:
                        continue
                
                stats_data.append({
                    'split': split,
                    'images': len(images),
                    'labels': len(labels),
                    **{f'class_{i}': count for i, count in class_counts.items()}
                })
        
        return pd.DataFrame(stats_data)
        
    except Exception as e:
        logger.error(f"Error getting dataset statistics: {str(e)}")
        return pd.DataFrame()

# Usage example
if __name__ == "__main__":
    # Initialize data loader
    loader = PPEDataLoader()
    
    # Create sample dataset structure
    loader.create_sample_dataset()
    
    # Validate dataset
    stats = loader.validate_dataset()
    print(f"Dataset stats: {stats}") 