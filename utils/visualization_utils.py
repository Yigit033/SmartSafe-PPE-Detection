"""
Visualization utilities for PPE Detection System
Drawing and display functions
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt
import seaborn as sns
from utils.visual_overlay import draw_styled_box, get_class_color

def draw_detection_results(frame: np.ndarray, 
                         detections: List[Dict],
                         show_confidence: bool = True) -> np.ndarray:
    """Draw detection results on frame"""
    
    for detection in detections:
        bbox = detection.get('bbox', [0, 0, 0, 0])
        class_name = detection.get('class_name', 'unknown')
        confidence = detection.get('confidence', 0.0)
        is_missing = detection.get('missing', False)
        
        x1, y1, x2, y2 = [int(coord) for coord in bbox]
        
        # Renk belirleme
        color = get_class_color(class_name, is_missing=is_missing)
        
        # Label hazırla
        label = f"{class_name}"
        if show_confidence:
            label += f" {confidence:.2f}"
        
        # Profesyonel bounding box çiz
        frame = draw_styled_box(frame, x1, y1, x2, y2, label, color)
    
    return frame

def create_status_overlay(frame: np.ndarray, 
                         status_info: Dict) -> np.ndarray:
    """Create status information overlay"""
    
    overlay = frame.copy()
    
    # Add status information
    y_offset = 30
    for key, value in status_info.items():
        text = f"{key}: {value}"
        cv2.putText(overlay, text, (10, y_offset), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        y_offset += 25
    
    return overlay 