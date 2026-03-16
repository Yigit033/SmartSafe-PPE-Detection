"""
Visual Overlay Utilities for PPE Detection System
Production-grade bounding box rendering with:
  - Corner-bracket style boxes (no full rectangle edges)
  - Semi-transparent label pills with confidence bars
  - Distinct visual treatment for PERSON vs PPE-present vs PPE-missing
  - Glow / shadow for readability on any background
  - Adaptive sizing based on frame resolution
"""

import cv2
import numpy as np
from typing import Tuple, Optional


# ─── colour palette ──────────────────────────────────────────────────────────
_POSITIVE_COLORS = {
    "person":       (50, 160, 255),   # warm orange
    "helmet":       (80, 220, 80),    # green
    "safety_vest":  (0, 215, 255),    # amber
    "vest":         (0, 215, 255),
    "safety_shoes": (255, 80, 180),   # magenta-pink
    "shoes":        (255, 80, 180),
    "gloves":       (255, 220, 50),   # cyan-ish yellow
    "safety_glasses": (255, 200, 60),
    "glasses":      (255, 200, 60),
    "goggles":      (255, 200, 60),
    "face_mask":    (255, 200, 0),    # bright cyan
    "mask":         (255, 200, 0),
    "haircap":      (230, 100, 255),  # purple
    "bone":         (230, 100, 255),
    "safety_suit":  (160, 230, 160),  # soft green
    "suit":         (160, 230, 160),
    "apron":        (160, 230, 160),
}

_NEGATIVE_COLORS = {
    "helmet":       (60, 60, 255),
    "safety_vest":  (40, 80, 255),
    "vest":         (40, 80, 255),
    "safety_shoes": (50, 50, 220),
    "shoes":        (50, 50, 220),
    "gloves":       (50, 50, 240),
    "safety_glasses": (50, 50, 255),
    "glasses":      (50, 50, 255),
    "goggles":      (50, 50, 255),
    "face_mask":    (40, 40, 240),
    "mask":         (40, 40, 240),
    "haircap":      (80, 30, 230),
    "bone":         (80, 30, 230),
    "safety_suit":  (40, 60, 230),
    "suit":         (40, 60, 230),
    "apron":        (40, 60, 230),
}

_DEFAULT_POSITIVE = (180, 180, 180)
_DEFAULT_NEGATIVE = (50, 50, 255)
_PERSON_COLOR     = (50, 160, 255)


def get_class_color(class_name: str, is_missing: bool = False) -> Tuple[int, int, int]:
    """Return BGR colour for a PPE class."""
    key = class_name.lower().replace("no-", "").replace("no_", "").strip()
    if is_missing or class_name.lower().startswith("no"):
        for token, col in _NEGATIVE_COLORS.items():
            if token in key:
                return col
        return _DEFAULT_NEGATIVE
    for token, col in _POSITIVE_COLORS.items():
        if token in key:
            return col
    return _DEFAULT_POSITIVE


# ─── adaptive sizing helpers ─────────────────────────────────────────────────

def _scale(frame: np.ndarray) -> float:
    """Return a multiplier so that visuals look right on 480p–4K frames."""
    h = frame.shape[0]
    return max(0.45, min(h / 720.0, 2.0))


# ─── corner-bracket drawing ─────────────────────────────────────────────────

def _draw_corner_brackets(
    img: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    color: Tuple[int, int, int],
    thickness: int = 2,
    corner_len: int = 18,
):
    """Draw L-shaped corner brackets instead of a full rectangle."""
    cl = corner_len
    t = thickness

    # top-left
    cv2.line(img, (x1, y1), (x1 + cl, y1), color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1, y1 + cl), color, t, cv2.LINE_AA)
    # top-right
    cv2.line(img, (x2, y1), (x2 - cl, y1), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2, y1 + cl), color, t, cv2.LINE_AA)
    # bottom-left
    cv2.line(img, (x1, y2), (x1 + cl, y2), color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1, y2 - cl), color, t, cv2.LINE_AA)
    # bottom-right
    cv2.line(img, (x2, y2), (x2 - cl, y2), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2, y2 - cl), color, t, cv2.LINE_AA)


# ─── label pill ──────────────────────────────────────────────────────────────

def _draw_label_pill(
    img: np.ndarray,
    text: str,
    x: int, y: int,
    color: Tuple[int, int, int],
    font_scale: float = 0.50,
    confidence: Optional[float] = None,
):
    """
    Draw a rounded semi-transparent pill behind the label text.
    Optionally draw a small confidence bar inside the pill.
    """
    font = cv2.FONT_HERSHEY_DUPLEX
    text_thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, text_thickness)

    pad_x, pad_y = 6, 4
    pill_w = tw + 2 * pad_x
    pill_h = th + baseline + 2 * pad_y

    if confidence is not None:
        pill_h += 5

    # Clamp so pill doesn't go above frame
    pill_y1 = max(0, y - pill_h)
    pill_y2 = pill_y1 + pill_h
    pill_x1 = x
    pill_x2 = min(img.shape[1], x + pill_w)

    # Semi-transparent background
    overlay = img[pill_y1:pill_y2, pill_x1:pill_x2].copy()
    if overlay.size == 0:
        return

    bg = np.full_like(overlay, color, dtype=np.uint8)
    blended = cv2.addWeighted(bg, 0.65, overlay, 0.35, 0)
    img[pill_y1:pill_y2, pill_x1:pill_x2] = blended

    # Text colour: white on dark pills, black on bright pills
    brightness = color[0] * 0.114 + color[1] * 0.587 + color[2] * 0.299
    txt_col = (255, 255, 255) if brightness < 160 else (20, 20, 20)

    text_y = pill_y1 + pad_y + th
    cv2.putText(img, text, (pill_x1 + pad_x, text_y), font, font_scale, txt_col, text_thickness, cv2.LINE_AA)

    # Confidence mini-bar
    if confidence is not None and confidence > 0:
        bar_y = text_y + 3
        bar_x1 = pill_x1 + pad_x
        bar_max_w = pill_w - 2 * pad_x
        bar_w = max(1, int(bar_max_w * min(confidence, 1.0)))
        bar_col = (
            int(txt_col[0] * 0.7),
            int(txt_col[1] * 0.7),
            int(txt_col[2] * 0.7),
        )
        cv2.line(img, (bar_x1, bar_y), (bar_x1 + bar_w, bar_y), bar_col, 1, cv2.LINE_AA)


# ─── public API ──────────────────────────────────────────────────────────────

_label_registry: list = []


def reset_label_registry():
    """Call once per frame before drawing any boxes to reset overlap tracking."""
    global _label_registry
    _label_registry = []


def _find_non_overlapping_y(x: int, desired_y: int, pill_h: int, pill_w: int) -> int:
    """Shift *desired_y* upward/downward so the pill doesn't overlap existing pills."""
    global _label_registry
    margin = 2

    candidate = desired_y
    for _ in range(20):
        conflict = False
        for (rx, ry, rw, rh) in _label_registry:
            if abs(x - rx) < max(pill_w, rw) and abs(candidate - ry) < (pill_h + rh) // 2 + margin:
                conflict = True
                candidate = ry - pill_h - margin
                break
        if not conflict:
            break

    candidate = max(0, candidate)
    _label_registry.append((x, candidate, pill_w, pill_h))
    return candidate


def draw_styled_box(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    label: str,
    color: Tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
    confidence: Optional[float] = None,
    is_person: bool = False,
    is_missing: bool = False,
) -> np.ndarray:
    """
    Production-grade bounding box renderer.

    - PERSON boxes: thin dashed rectangle + small label
    - PPE present: corner brackets (green family) + label pill with confidence bar
    - PPE missing: corner brackets (red family) + pulsing-style thicker line + label pill
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    if x1 >= x2 or y1 >= y2:
        return frame

    s = _scale(frame)
    t = max(1, int(thickness * s))
    corner_len = max(8, int(20 * s))
    font_scale = max(0.35, 0.48 * s)

    # Pre-calculate pill dimensions for deconfliction
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 1)
    pad_x, pad_y = 6, 4
    pill_w = tw + 2 * pad_x
    pill_h = th + baseline + 2 * pad_y + (5 if confidence is not None else 0)

    label_y = _find_non_overlapping_y(x1, y1, pill_h, pill_w)

    if is_person:
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, max(1, t - 1), cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        _draw_label_pill(frame, label, x1, label_y, color, font_scale * 0.85, confidence)
    elif is_missing:
        overlay = frame.copy()
        fill_alpha = 0.12
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, fill_alpha, frame, 1.0 - fill_alpha, 0, frame)
        _draw_corner_brackets(frame, x1, y1, x2, y2, color, t + 1, corner_len)
        _draw_label_pill(frame, label, x1, label_y, color, font_scale, confidence)
    else:
        _draw_corner_brackets(frame, x1, y1, x2, y2, color, t, corner_len)
        _draw_label_pill(frame, label, x1, label_y, color, font_scale, confidence)

    return frame


def draw_hud_bar(
    frame: np.ndarray,
    people: int,
    compliant: int,
    compliance_rate: float,
    violations_count: int = 0,
    sector: Optional[str] = None,
) -> np.ndarray:
    """
    Draw a modern semi-transparent top HUD bar with key stats.
    """
    h, w = frame.shape[:2]
    s = _scale(frame)
    bar_h = max(32, int(38 * s))

    # Semi-transparent dark bar
    overlay = frame[:bar_h, :].copy()
    dark = np.zeros_like(overlay, dtype=np.uint8)
    blended = cv2.addWeighted(dark, 0.60, overlay, 0.40, 0)
    frame[:bar_h, :] = blended

    font = cv2.FONT_HERSHEY_DUPLEX
    fs = max(0.38, 0.44 * s)
    t = 1

    # Compliance colour
    if compliance_rate >= 80:
        comp_col = (80, 230, 80)
    elif compliance_rate >= 50:
        comp_col = (60, 200, 255)
    else:
        comp_col = (80, 80, 255)

    # Status dot
    dot_r = max(4, int(6 * s))
    cv2.circle(frame, (dot_r + 8, bar_h // 2), dot_r, comp_col, -1, cv2.LINE_AA)

    x = dot_r * 2 + 18
    text_y = int(bar_h * 0.65)

    parts = [
        (f"People: {people}", (220, 220, 220)),
        (f"Compliant: {compliant}", comp_col),
        (f"Compliance: {compliance_rate:.0f}%", comp_col),
    ]
    if violations_count > 0:
        parts.append((f"Violations: {violations_count}", (80, 80, 255)))
    if sector:
        parts.append((f"Sector: {sector.upper()}", (180, 180, 180)))

    for txt, col in parts:
        cv2.putText(frame, txt, (x, text_y), font, fs, col, t, cv2.LINE_AA)
        tw = cv2.getTextSize(txt, font, fs, t)[0][0]
        x += tw + int(20 * s)

    return frame
