"""
SaaS detection worker için gözlemlenebilirlik (tam emin üçlüsü desteği).

1) ROI_DEBUG — ortam değişkeni; ROI poligonu + kişi kutuları (app.py).
2) Ölçülmüş gecikme — DETECTION_LATENCY_SUMMARY_SEC > 0 ise periyodik özet (avg/min/max).
3) Saha testi — DETECTION_OBSERVABILITY_BANNER=1 ile worker başında kontrol listesi loglanır.

Hepsi isteğe bağlı; varsayılanlar üretim gürültüsünü artırmaz.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import DefaultDict, Dict, List

_lock = threading.Lock()
# camera_key -> buffer
_state: DefaultDict[str, Dict[str, object]] = defaultdict(
    lambda: {"samples": [], "last_emit": 0.0}
)

_MAX_SAMPLES = 2000


def latency_summary_interval_sec() -> float:
    raw = os.environ.get("DETECTION_LATENCY_SUMMARY_SEC", "0").strip()
    try:
        v = float(raw)
        return v if v > 0 else 0.0
    except ValueError:
        return 0.0


def record_and_maybe_emit_latency(
    logger: logging.Logger, camera_key: str, processing_time_ms: float
) -> None:
    """Her başarılı inference turundan sonra çağrılır; pencere dolunca tek INFO satırı basar."""
    interval = latency_summary_interval_sec()
    if interval <= 0:
        return

    now = time.time()
    samples_out: List[float] = []

    with _lock:
        st = _state[camera_key]
        samples: List[float] = st["samples"]  # type: ignore[assignment]
        samples.append(float(processing_time_ms))
        if len(samples) > _MAX_SAMPLES:
            del samples[: len(samples) - 1500]

        last_emit = float(st["last_emit"])
        if now - last_emit < interval:
            return
        if not samples:
            return

        st["last_emit"] = now
        samples_out = list(samples)
        st["samples"] = []

    if not samples_out:
        return

    n = len(samples_out)
    avg = sum(samples_out) / n
    mn = min(samples_out)
    mx = max(samples_out)
    logger.info(
        "📊 LATENCY_SUMMARY [%s] n=%d avg_ms=%.1f min_ms=%.1f max_ms=%.1f (interval=%.0fs)",
        camera_key,
        n,
        avg,
        mn,
        mx,
        interval,
    )


def log_worker_observability_banner(
    logger: logging.Logger, camera_id: str, camera_key: str
) -> None:
    """Worker başında bir kez: env özeti + saha testi maddeleri."""
    if os.environ.get("DETECTION_OBSERVABILITY_BANNER", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return

    roi_dbg = os.environ.get("ROI_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    lat = latency_summary_interval_sec()
    roi_log = os.environ.get("ROI_LOG_INTERVAL_SEC", "15")
    torch_dev = os.environ.get("TORCH_DEVICE", "auto")
    render_flag = bool(os.environ.get("RENDER"))

    logger.info(
        "📋 OBSERVABILITY | camera_id=%s | key=%s | TORCH_DEVICE=%s | RENDER=%s | "
        "ROI_DEBUG=%s | ROI_LOG_INTERVAL_SEC=%s | DETECTION_LATENCY_SUMMARY_SEC=%s",
        camera_id,
        camera_key,
        torch_dev,
        render_flag,
        roi_dbg,
        roi_log,
        lat if lat > 0 else "off",
    )
    logger.info(
        "📋 SAHA_TESTİ: [1] ROI_DEBUG=1 → video-feed üzerinde poligon ve yeşil=içerde/kırmızı=dışarı "
        "doğrula. [2] LATENCY_SUMMARY avg_ms hedefinize uyuyor mu izleyin. "
        "[3] ROI içi/dışı kişi sayımı ve ihlaller sahada iş kuralıyla örtüşüyor mu doğrulayın."
    )
