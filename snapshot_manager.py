"""
SmartSafe AI - Snapshot Manager
Violation snapshot capture and storage system
"""

import os
import cv2
import logging
import numpy as np
from typing import Optional, Dict
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class SnapshotManager:
    """
    İhlal fotoğrafı yönetim sistemi
    - Violation snapshot capture
    - Organized storage (company/camera/date)
    - Image optimization
    """
    
    def __init__(self, base_path: str = "violations"):
        """
        Args:
            base_path: Snapshot'ların kaydedileceği ana klasör
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ SnapshotManager initialized: {self.base_path}")
    
    def capture_violation_snapshot(
        self,
        frame: np.ndarray,
        company_id: str,
        camera_id: str,
        person_id: str,
        violation_type: str,
        person_bbox: list,
        event_id: str
    ) -> Optional[str]:
        """
        İhlal anında snapshot çek ve kaydet
        
        Args:
            frame: Kamera frame'i
            company_id: Şirket ID
            camera_id: Kamera ID
            person_id: Kişi ID
            violation_type: İhlal tipi
            person_bbox: Kişi bounding box [x1, y1, x2, y2]
            event_id: Event ID
            
        Returns:
            Snapshot dosya yolu (başarısızsa None)
        """
        try:
            if frame is None or frame.size == 0:
                logger.warning("⚠️ Empty frame, cannot capture snapshot")
                return None
            
            # Klasör yapısı: violations/COMP_XXX/CAM_XXX/2025-10-31/
            date_str = datetime.now().strftime('%Y-%m-%d')
            snapshot_dir = self.base_path / company_id / camera_id / date_str
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            
            # Dosya adı: PERSON_XXX_no_helmet_1730400000.jpg
            timestamp = int(datetime.now().timestamp())
            filename = f"{person_id}_{violation_type}_{timestamp}.jpg"
            filepath = snapshot_dir / filename
            
            # Kişiyi crop et (bbox + padding)
            x1, y1, x2, y2 = [int(coord) for coord in person_bbox]
            
            # Padding ekle (%10)
            height, width = frame.shape[:2]
            padding_x = int((x2 - x1) * 0.1)
            padding_y = int((y2 - y1) * 0.1)
            
            x1 = max(0, x1 - padding_x)
            y1 = max(0, y1 - padding_y)
            x2 = min(width, x2 + padding_x)
            y2 = min(height, y2 + padding_y)
            
            # Crop
            person_img = frame[y1:y2, x1:x2]
            
            if person_img.size == 0:
                logger.warning("⚠️ Invalid crop region")
                return None
            
            # İhlal tipini frame'e yaz
            violation_text = self._get_violation_text(violation_type)
            timestamp_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Üst kısma bilgi paneli ekle
            panel_height = 60
            panel = np.zeros((panel_height, person_img.shape[1], 3), dtype=np.uint8)
            
            # Arka plan rengi (kırmızı - ihlal)
            panel[:] = (0, 0, 180)
            
            # Metin ekle
            cv2.putText(panel, violation_text, (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(panel, timestamp_text, (10, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            # Panel + person image birleştir
            final_img = np.vstack([panel, person_img])
            
            # Kaydet (JPEG quality: 85)
            cv2.imwrite(str(filepath), final_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            # Relative path döndür
            relative_path = str(filepath.relative_to(self.base_path))
            
            logger.info(f"📸 Snapshot saved: {relative_path}")
            return relative_path
            
        except Exception as e:
            logger.error(f"❌ Snapshot capture error: {e}")
            return None
    
    def _get_violation_text(self, violation_type: str) -> str:
        """İhlal tipini Türkçe metne çevir"""
        violation_texts = {
            'no_helmet': '⚠️ BARET EKSİK',
            'no_vest': '⚠️ YELEK EKSİK',
            'no_shoes': '⚠️ GÜVENLİK AYAKKABISI EKSİK'
        }
        return violation_texts.get(violation_type, f'⚠️ {violation_type.upper()}')
    
    def get_snapshot_path(self, relative_path: str) -> Path:
        """Relative path'ten absolute path oluştur"""
        return self.base_path / relative_path
    
    def cleanup_old_snapshots(self, days: int = 30):
        """
        Eski snapshot'ları temizle
        
        Args:
            days: Kaç günden eski snapshot'lar silinecek
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = 0
            
            for company_dir in self.base_path.iterdir():
                if not company_dir.is_dir():
                    continue
                    
                for camera_dir in company_dir.iterdir():
                    if not camera_dir.is_dir():
                        continue
                    
                    for date_dir in camera_dir.iterdir():
                        if not date_dir.is_dir():
                            continue
                        
                        try:
                            # Klasör adından tarihi parse et
                            dir_date = datetime.strptime(date_dir.name, '%Y-%m-%d')
                            
                            if dir_date < cutoff_date:
                                # Klasörü sil
                                import shutil
                                shutil.rmtree(date_dir)
                                deleted_count += 1
                                logger.info(f"🗑️ Deleted old snapshots: {date_dir}")
                        except ValueError:
                            # Geçersiz klasör adı, atla
                            continue
            
            if deleted_count > 0:
                logger.info(f"✅ Cleanup completed: {deleted_count} directories deleted")
            
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")


# Global instance
_snapshot_manager = None


def get_snapshot_manager() -> SnapshotManager:
    """Global snapshot manager instance'ı al"""
    global _snapshot_manager
    if _snapshot_manager is None:
        _snapshot_manager = SnapshotManager()
    return _snapshot_manager
