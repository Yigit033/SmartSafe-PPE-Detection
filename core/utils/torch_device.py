"""
Merkezi PyTorch inference cihazı seçimi (SH17, pose, worker logları, semaphore boyutu).

Ortam değişkenleri
------------------
TORCH_DEVICE (varsayılan ``auto``)
    * ``auto`` — ``torch.cuda.is_available()`` ise ``cuda``, değilse ``cpu``
    * ``cpu`` — CPU zorunlu
    * ``cuda`` — ilk CUDA cihazı (CUDA yoksa ``cpu`` + uyarı)
    * ``cuda:N`` — N indeksli GPU (geçersiz / CUDA yoksa ``cpu`` + uyarı)

RENDER
    Herhangi bir değer set edilmişse (ör. Render.com) her zaman ``cpu`` — platform GPU sunmaz.

İlk başarılı ``resolve_inference_device()`` çağrısı süreç genelinde sonucu önbelleğe alır.
Üretimde cihazı değiştirmek için süreci ``TORCH_DEVICE`` ile yeniden başlatın.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    import torch
except ImportError:
    torch = None

_resolved: Optional[str] = None


def _emit(
    logger: Optional[logging.Logger], level: int, msg: str, *args: object
) -> None:
    log = logger if logger is not None else logging.getLogger(__name__)
    log.log(level, msg, *args)


def resolve_inference_device(logger: Optional[logging.Logger] = None) -> str:
    """
    Ultralytics / SH17 ile uyumlu cihaz dizisi döndürür: ``cpu``, ``cuda`` veya ``cuda:N``.
    """
    global _resolved
    if _resolved is not None:
        return _resolved

    if os.environ.get("RENDER"):
        _resolved = "cpu"
        _emit(
            logger,
            logging.INFO,
            "🖥️ Inference device: cpu (RENDER set — barındırıcı GPU kullanılmaz)",
        )
        return _resolved

    raw_in = (os.environ.get("TORCH_DEVICE") or "auto").strip()
    token = raw_in.lower()

    if token in ("", "auto"):
        if torch is None:
            _resolved = "cpu"
            _emit(
                logger,
                logging.INFO,
                "🖥️ Inference device: cpu (auto — torch yüklü değil)",
            )
            return _resolved
        if torch.cuda.is_available():
            _resolved = "cuda"
            try:
                name = torch.cuda.get_device_name(0)
            except Exception:
                name = "unknown"
            _emit(
                logger,
                logging.INFO,
                "🖥️ Inference device: cuda (auto) — GPU 0: %s",
                name,
            )
            return _resolved
        _resolved = "cpu"
        _emit(
            logger,
            logging.INFO,
            "🖥️ Inference device: cpu (auto — CUDA kullanılamıyor)",
        )
        return _resolved

    if token == "cpu":
        _resolved = "cpu"
        _emit(logger, logging.INFO, "🖥️ Inference device: cpu (TORCH_DEVICE=cpu)")
        return _resolved

    if torch is None:
        _resolved = "cpu"
        _emit(
            logger,
            logging.WARNING,
            "🖥️ TORCH_DEVICE=%s istendi ancak torch yok — cpu kullanılıyor",
            raw_in,
        )
        return _resolved

    if token == "cuda":
        if not torch.cuda.is_available():
            _resolved = "cpu"
            _emit(
                logger,
                logging.WARNING,
                "🖥️ TORCH_DEVICE=cuda ancak CUDA yok — cpu kullanılıyor",
            )
            return _resolved
        _resolved = "cuda"
        _emit(logger, logging.INFO, "🖥️ Inference device: cuda (TORCH_DEVICE=cuda)")
        return _resolved

    if token.startswith("cuda:"):
        suffix = token[5:].strip()
        try:
            idx = int(suffix)
        except ValueError:
            _resolved = "cpu"
            _emit(
                logger,
                logging.WARNING,
                "🖥️ Geçersiz TORCH_DEVICE=%r — cpu kullanılıyor",
                raw_in,
            )
            return _resolved
        if not torch.cuda.is_available():
            _resolved = "cpu"
            _emit(
                logger,
                logging.WARNING,
                "🖥️ TORCH_DEVICE=%s ancak CUDA yok — cpu kullanılıyor",
                raw_in,
            )
            return _resolved
        n = torch.cuda.device_count()
        if idx < 0 or idx >= n:
            _resolved = "cpu"
            _emit(
                logger,
                logging.WARNING,
                "🖥️ TORCH_DEVICE=%s geçersiz (device_count=%d) — cpu kullanılıyor",
                raw_in,
                n,
            )
            return _resolved
        _resolved = f"cuda:{idx}"
        try:
            name = torch.cuda.get_device_name(idx)
        except Exception:
            name = "unknown"
        _emit(
            logger,
            logging.INFO,
            "🖥️ Inference device: %s — %s",
            _resolved,
            name,
        )
        return _resolved

    _resolved = "cpu"
    _emit(
        logger,
        logging.WARNING,
        "🖥️ Bilinmeyen TORCH_DEVICE=%r — cpu kullanılıyor",
        raw_in,
    )
    return _resolved
