#!/usr/bin/env python3
"""
SmartSafe AI — FFmpeg Stream Reader

Production-grade RTSP stream reader using FFmpeg subprocess.
Replaces cv2.VideoCapture for better reconnect, stability, and HW decode.

Advantages over cv2.VideoCapture:
  • TCP transport (more stable than UDP)
  • Separate process per stream — one crash doesn't affect the system
  • Buffer control via pipe
  • Sub-stream support (default 640x360 for detection)
  • Graceful shutdown and auto-restart
"""

import subprocess
import shutil
import threading
import time
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# FFmpeg binary search path
_FFMPEG_PATH: Optional[str] = None


def _find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg binary — cache the result."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is not None:
        return _FFMPEG_PATH if _FFMPEG_PATH != '' else None

    path = shutil.which('ffmpeg')
    if path:
        _FFMPEG_PATH = path
    else:
        # Windows: try common installation paths
        import os
        for candidate in [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\ffmpeg-8.0-essentials_build\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ffmpeg', 'bin', 'ffmpeg.exe'),
        ]:
            if os.path.isfile(candidate):
                _FFMPEG_PATH = candidate
                break

    if _FFMPEG_PATH:
        logger.info(f"✅ FFmpeg found: {_FFMPEG_PATH}")
    else:
        _FFMPEG_PATH = ''  # cache negative result
        logger.warning("⚠️ FFmpeg not found — will fall back to cv2.VideoCapture")

    return _FFMPEG_PATH if _FFMPEG_PATH != '' else None


class FFmpegStreamReader:
    """
    Read RTSP streams via FFmpeg subprocess, outputting raw BGR24 frames.

    Usage:
        reader = FFmpegStreamReader("rtsp://admin:pass@192.168.1.64:554/...", 640, 360)
        reader.start()
        while reader.is_alive():
            frame = reader.read_frame()
            if frame is not None:
                # ... process frame ...
        reader.stop()
    """

    def __init__(
        self,
        rtsp_url: str,
        width: int = 640,
        height: int = 360,
        fps: int = 5,
        transport: str = 'tcp',
        timeout: int = 10,
    ):
        self.url = rtsp_url
        self.width = width
        self.height = height
        self.fps = fps
        self.transport = transport
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self._frame_size = width * height * 3  # BGR24
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None
        self._frames_read: int = 0

    def start(self) -> bool:
        """Start FFmpeg subprocess. Returns True on success."""
        ffmpeg_bin = _find_ffmpeg()
        if not ffmpeg_bin:
            return False

        cmd = [
            ffmpeg_bin,
            '-hide_banner',
            '-loglevel', 'warning',
            # input options
            '-rtsp_transport', self.transport,
            '-stimeout', str(self.timeout * 1_000_000),  # μs
            '-i', self.url,
            # output options
            '-vf', f'scale={self.width}:{self.height}',
            '-r', str(self.fps),       # output fps limit
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-an',                     # no audio
            '-',                       # stdout
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self._frame_size * 8,  # ~8 frame buffer
            )
            self._stopped.clear()
            self._start_time = time.time()
            self._frames_read = 0
            logger.info(f"🎬 FFmpeg started: {self.width}x{self.height}@{self.fps}fps | {self.url[:80]}...")
            return True
        except FileNotFoundError:
            logger.error(f"❌ FFmpeg binary not found: {ffmpeg_bin}")
            return False
        except Exception as e:
            logger.error(f"❌ FFmpeg start error: {e}")
            return False

    def read_frame(self) -> Optional[np.ndarray]:
        """Read one BGR24 frame. Returns None if stream ended or error."""
        if not self.process or self._stopped.is_set():
            return None

        try:
            raw = self.process.stdout.read(self._frame_size)
            if raw is None or len(raw) < self._frame_size:
                return None  # stream ended
            self._frames_read += 1
            return np.frombuffer(raw, dtype=np.uint8).reshape(
                (self.height, self.width, 3)
            )
        except Exception:
            return None

    def is_alive(self) -> bool:
        """Check if FFmpeg subprocess is still running."""
        if self._stopped.is_set():
            return False
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self):
        """Gracefully stop FFmpeg subprocess."""
        self._stopped.set()
        if self.process:
            try:
                self.process.stdout.close()
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception:
                pass
            finally:
                self.process = None
        logger.info(f"🛑 FFmpeg stopped | frames read: {self._frames_read}")

    def get_stats(self) -> dict:
        """Return reader statistics."""
        uptime = time.time() - self._start_time if self._start_time else 0
        return {
            'alive': self.is_alive(),
            'frames_read': self._frames_read,
            'uptime_sec': round(uptime, 1),
            'resolution': f'{self.width}x{self.height}',
            'fps_target': self.fps,
            'fps_actual': round(self._frames_read / uptime, 1) if uptime > 1 else 0,
        }

    def __del__(self):
        self.stop()


# ── cv2 fallback wrapper ────────────────────────────────────────────────────

class CV2StreamReader:
    """
    Fallback stream reader using cv2.VideoCapture.
    Same API as FFmpegStreamReader for easy swapping.
    """

    def __init__(self, rtsp_url: str, width: int = 640, height: int = 360,
                 fps: int = 5, **_kwargs):
        import cv2
        self.url = rtsp_url
        self.width = width
        self.height = height
        self.fps = fps
        self.cap: Optional[cv2.VideoCapture] = None
        self._stopped = threading.Event()
        self._frames_read = 0
        self._start_time: Optional[float] = None

    def start(self) -> bool:
        import cv2
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            return False
        self._start_time = time.time()
        self._stopped.clear()
        self._frames_read = 0
        logger.info(f"📹 cv2 fallback stream opened: {self.url[:80]}...")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        import cv2
        if self._stopped.is_set() or self.cap is None:
            return None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        self._frames_read += 1
        return frame

    def is_alive(self) -> bool:
        return (not self._stopped.is_set()) and self.cap is not None and self.cap.isOpened()

    def stop(self):
        self._stopped.set()
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info(f"🛑 cv2 fallback stopped | frames: {self._frames_read}")

    def get_stats(self) -> dict:
        uptime = time.time() - self._start_time if self._start_time else 0
        return {
            'alive': self.is_alive(),
            'frames_read': self._frames_read,
            'uptime_sec': round(uptime, 1),
            'resolution': f'{self.width}x{self.height}',
            'fps_target': self.fps,
            'fps_actual': round(self._frames_read / uptime, 1) if uptime > 1 else 0,
        }


def create_stream_reader(rtsp_url: str, width: int = 640, height: int = 360,
                         fps: int = 5, prefer_ffmpeg: bool = True, **kwargs):
    """
    Factory: create the best available stream reader.
    Returns FFmpegStreamReader if ffmpeg is available, else CV2StreamReader.
    """
    if prefer_ffmpeg and _find_ffmpeg():
        return FFmpegStreamReader(rtsp_url, width, height, fps, **kwargs)
    return CV2StreamReader(rtsp_url, width, height, fps)
