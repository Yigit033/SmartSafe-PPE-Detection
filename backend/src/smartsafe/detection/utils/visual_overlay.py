"""
Visual Overlay Utilities for PPE Detection System
Professional bounding box drawing with high contrast and readability
"""

import cv2
import numpy as np
from typing import Tuple


def draw_styled_box(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    label: str,
    color: Tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2
) -> np.ndarray:
    """
    Profesyonel, yüksek kontrastlı ve okunabilir bounding box çizer.
    """
    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if x1 >= x2 or y1 >= y2:
        return frame

    # Antialiased dış kutu
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)

    # Hafif iç kenar efekti (derinlik hissi)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), 1, cv2.LINE_AA)
    frame = cv2.addWeighted(overlay, 0.2, frame, 0.8, 0)

    # --- Label ---
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = 0.55
    text_thickness = 1
    label_upper = label.upper()

    (tw, th), baseline = cv2.getTextSize(label_upper, font, font_scale, text_thickness)
    y_label = max(y1 - 8, th + 8)

    # Label arka planı: yarı saydam
    bg_color = tuple(int(c * 0.8) for c in color)
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (x1, y_label - th - baseline - 4),
        (x1 + tw + 6, y_label + baseline + 2),
        bg_color,
        -1,
        cv2.LINE_AA,
    )
    frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

    # Yazı rengi: kutu rengine göre dinamik seç
    brightness = (color[0]*0.299 + color[1]*0.587 + color[2]*0.114)
    text_color = (0, 0, 0) if brightness > 150 else (255, 255, 255)

    cv2.putText(
        frame,
        label_upper,
        (x1 + 3, y_label - 2),
        font,
        font_scale,
        text_color,
        text_thickness,
        cv2.LINE_AA,
    )

    return frame


def get_class_color(class_name: str, is_missing: bool = False) -> Tuple[int, int, int]:
    """
    PPE sınıfına göre profesyonel renk paleti.
    """
    class_name_lower = class_name.lower()

    # Eksik PPE: kırmızı tonları
    if is_missing:
        if "helmet" in class_name_lower or "baret" in class_name_lower:
            return (0, 0, 255)      # vivid red
        elif "vest" in class_name_lower or "yelek" in class_name_lower:
            return (0, 60, 255)     # orange-red
        elif "shoes" in class_name_lower or "ayakkabı" in class_name_lower:
            return (20, 20, 200)    # dark red-blue
        return (0, 0, 255)

    # Mevcut PPE
    if "helmet" in class_name_lower or "baret" in class_name_lower:
        return (0, 255, 0)          # bright green
    elif "vest" in class_name_lower or "yelek" in class_name_lower:
        return (0, 215, 255)        # amber
    elif "shoes" in class_name_lower or "ayakkabı" in class_name_lower:
        return (255, 50, 255)       # magenta
    elif "gloves" in class_name_lower or "eldiven" in class_name_lower:
        return (255, 255, 0)        # cyan
    elif "person" in class_name_lower:
        return (50, 160, 255)       # vivid blue
    else:
        return (180, 180, 180)
