"""
Visual Overlay Utilities for PPE Detection System
Production-grade bounding box rendering with:
  - Corner-bracket style boxes (no full rectangle edges)
  - Semi-transparent label pills with confidence bars
  - Distinct visual treatment for PERSON vs PPE-present vs PPE-missing
  - Glow / shadow for readability on any background
  - Adaptive sizing based on frame resolution
"""

import os
import cv2
import numpy as np
from typing import Tuple, Optional

# ─── Unicode (Türkçe) metin için PIL/Pillow render ──────────────────────────
# cv2.putText Hershey fontları yalnızca Latin1'i render eder; Ö/ö/Ü/Ç/Ş/İ/ğ
# karakterleri "?" olarak çıkıyor. Pillow TrueType fontu ile UTF-8 metni
# ROI içinde çiziyoruz (tüm frame dönüşümü değil, sadece pill alanı).
try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

_FONT_CACHE: dict = {}

_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


def _get_pil_font(px_size: int):
    """Cache'li TrueType font getter. Bulunamazsa PIL default bitmap font."""
    if not _PIL_AVAILABLE:
        return None
    key = int(max(8, px_size))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, key)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                continue
    # Fallback — Türkçe karakter desteği sınırlı
    try:
        f = ImageFont.load_default()
        _FONT_CACHE[key] = f
        return f
    except Exception:
        return None


_TR_ASCII_MAP = str.maketrans({
    "Ö": "O", "ö": "o",
    "Ü": "U", "ü": "u",
    "Ç": "C", "ç": "c",
    "Ş": "S", "ş": "s",
    "İ": "I", "ı": "i",
    "Ğ": "G", "ğ": "g",
})


def _draw_text_unicode(
    img: np.ndarray,
    text: str,
    x: int,
    y_top: int,
    color_bgr: Tuple[int, int, int],
    px_size: int,
) -> None:
    """
    UTF-8 metni (x, y_top) top-left köşesinden itibaren çizer.
    PIL varsa TrueType ile Türkçe karakterleri doğru render eder;
    yoksa Ö/ö → O/o şeklinde ASCII fallback yapıp cv2.putText kullanır.
    Performans için frame'in yalnızca metin ROI'si dönüştürülür.
    """
    if not text:
        return
    h_img, w_img = img.shape[:2]
    if not _PIL_AVAILABLE:
        fs = max(0.35, px_size / 28.0)
        ascii_text = text.translate(_TR_ASCII_MAP)
        (tw, th), baseline = cv2.getTextSize(ascii_text, cv2.FONT_HERSHEY_DUPLEX, fs, 1)
        cv2.putText(
            img, ascii_text, (x, y_top + th),
            cv2.FONT_HERSHEY_DUPLEX, fs, color_bgr, 1, cv2.LINE_AA,
        )
        return

    font = _get_pil_font(px_size)
    if font is None:
        ascii_text = text.translate(_TR_ASCII_MAP)
        fs = max(0.35, px_size / 28.0)
        (tw, th), baseline = cv2.getTextSize(ascii_text, cv2.FONT_HERSHEY_DUPLEX, fs, 1)
        cv2.putText(
            img, ascii_text, (x, y_top + th),
            cv2.FONT_HERSHEY_DUPLEX, fs, color_bgr, 1, cv2.LINE_AA,
        )
        return

    # ROI sınırlarını hesapla
    try:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0] + 2
        th = bbox[3] - bbox[1] + 2
    except Exception:
        try:
            tw, th = font.getsize(text)  # type: ignore[attr-defined]
            tw += 2
            th += 2
        except Exception:
            tw = int(px_size * len(text) * 0.6)
            th = int(px_size * 1.2)

    x1 = max(0, x)
    y1 = max(0, y_top)
    x2 = min(w_img, x + tw)
    y2 = min(h_img, y_top + th)
    if x1 >= x2 or y1 >= y2:
        return

    roi = img[y1:y2, x1:x2]
    try:
        pil_roi = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_roi)
        rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
        draw.text((x - x1, y_top - y1), text, font=font, fill=rgb)
        img[y1:y2, x1:x2] = cv2.cvtColor(np.array(pil_roi), cv2.COLOR_RGB2BGR)
    except Exception:
        ascii_text = text.translate(_TR_ASCII_MAP)
        fs = max(0.35, px_size / 28.0)
        cv2.putText(
            img, ascii_text, (x, y_top + int(th * 0.8)),
            cv2.FONT_HERSHEY_DUPLEX, fs, color_bgr, 1, cv2.LINE_AA,
        )


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

    Text Pillow TrueType ile çizilir → Ö/ö/Ü/Ç/Ş/İ/Ğ karakterleri bozulmaz.
    """
    font = cv2.FONT_HERSHEY_DUPLEX
    text_thickness = 1
    # Pill boyutlandırması için cv2 metrikleri ASCII-normalize üzerinden
    # hesaplanır; TrueType ile çizilen Türkçe metin aynı pill içinde durur.
    sizing_text = text.translate(_TR_ASCII_MAP)
    (tw, th), baseline = cv2.getTextSize(sizing_text, font, font_scale, text_thickness)

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

    # Pillow ile Türkçe-uyumlu çizim. PIL piksel cinsinden boyut ister;
    # font_scale yaklaşık olarak cv2-Hershey oranıdır (0.5 ≈ 14 px).
    px_size = max(10, int(round(font_scale * 28)))
    text_top_y = pill_y1 + pad_y
    _draw_text_unicode(
        img, text, pill_x1 + pad_x, text_top_y, txt_col, px_size
    )

    # Confidence mini-bar
    if confidence is not None and confidence > 0:
        bar_y = text_top_y + th + 3
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

    px_size = max(11, int(round(fs * 28)))
    for txt, col in parts:
        (tw, th), _ = cv2.getTextSize(txt.translate(_TR_ASCII_MAP), font, fs, t)
        _draw_text_unicode(frame, txt, x, max(0, text_y - th), col, px_size)
        x += tw + int(20 * s)

    return frame


def draw_roi_polygon(
    frame: np.ndarray,
    polygon_px: np.ndarray,
    color: Tuple[int, int, int] = (255, 165, 0),  # Default: orange
    alpha: float = 0.30,  # Görünürlüğü artırmak için 0.15 -> 0.30
) -> np.ndarray:
    """
    Draw a semi-transparent ROI polygon on the frame.
    """
    if polygon_px is None or len(polygon_px) < 3:
        return frame

    # 1. Alanın içini yarı saydam boya
    overlay = frame.copy()
    cv2.fillPoly(overlay, [polygon_px.astype(np.int32)], color)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

    # 2. Kenar çizgilerini daha belirgin çiz (kesik çizgi efekti için ince kalınlık)
    cv2.polylines(
        frame, [polygon_px.astype(np.int32)], True, color, 4, cv2.LINE_AA
    )
    
    # 3. ROI köşelerine küçük noktalar koy (daha teknik bir görünüm)
    for pt in polygon_px:
        # OpenCV contour formatı Nx1x2 olduğu için pt[0] -> [x, y] döner
        if pt.ndim == 2 and pt.shape[0] == 1:
            px, py = pt[0]
        else:
            px, py = pt
        cv2.circle(frame, (int(px), int(py)), 3, color, -1, cv2.LINE_AA)

    return frame
