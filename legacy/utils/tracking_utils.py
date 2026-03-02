"""
Tracking utilities for PPE Detection System
Person tracking and trajectory analysis
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
import cv2
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PersonTracker:
    """Simple person tracking utilities"""
    
    def __init__(self):
        """Initialize tracker"""
        self.tracks = {}
        self.next_id = 1
        
    def update_tracks(self, detections: List[Dict]) -> List[Dict]:
        """Update tracking information"""
        # Simple tracking implementation
        for detection in detections:
            if 'track_id' not in detection:
                detection['track_id'] = self.next_id
                self.next_id += 1
        
        return detections
    
    def get_track_history(self, track_id: int) -> List[Tuple[int, int]]:
        """Get tracking history for a person"""
        return self.tracks.get(track_id, [])

def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points"""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)

def smooth_trajectory(points: List[Tuple[float, float]], window_size: int = 5) -> List[Tuple[float, float]]:
    """Smooth tracking trajectory using moving average"""
    if len(points) < window_size:
        return points
    
    smoothed = []
    for i in range(len(points)):
        start_idx = max(0, i - window_size // 2)
        end_idx = min(len(points), i + window_size // 2 + 1)
        
        x_avg = sum(p[0] for p in points[start_idx:end_idx]) / (end_idx - start_idx)
        y_avg = sum(p[1] for p in points[start_idx:end_idx]) / (end_idx - start_idx)
        
        smoothed.append((x_avg, y_avg))
    
    return smoothed 