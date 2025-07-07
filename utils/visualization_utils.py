"""
Visualization utilities for PPE Detection System
Drawing and display functions
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt
import seaborn as sns

def draw_detection_results(frame: np.ndarray, 
                         detections: List[Dict],
                         show_confidence: bool = True) -> np.ndarray:
    """Draw detection results on frame"""
    
    colors = {
        'person': (255, 255, 255),
        'hard_hat': (0, 255, 0),
        'safety_vest': (0, 255, 255),
        'mask': (255, 0, 255),
        'violation': (0, 0, 255)
    }
    
    for detection in detections:
        bbox = detection.get('bbox', [0, 0, 0, 0])
        class_name = detection.get('class_name', 'unknown')
        confidence = detection.get('confidence', 0.0)
        
        x1, y1, x2, y2 = [int(coord) for coord in bbox]
        color = colors.get(class_name, (128, 128, 128))
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = f"{class_name}"
        if show_confidence:
            label += f" {confidence:.2f}"
            
        cv2.putText(frame, label, (x1, y1 - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
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