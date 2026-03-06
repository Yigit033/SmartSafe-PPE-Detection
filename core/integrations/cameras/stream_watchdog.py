"""
SmartSafe AI — Stream Watchdog

Tüm aktif kamera stream'lerini izler ve sorun tespit ettiğinde otomatik
müdahale eder:
  • Stale stream tespiti  (N saniye boyunca yeni frame gelmemişse)
  • Exponential-backoff ile otomatik yeniden bağlanma
  • Kalıcı arıza sonrası kamerayı "dead" olarak işaretleme
  • Tüm olayları loglama + API erişimi için olay listesi tutma

Kullanım:
    from integrations.cameras.stream_watchdog import get_stream_watchdog
    watchdog = get_stream_watchdog()
    watchdog.start()  # Daemon thread olarak çalışır
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Varsayılan Yapılandırma ─────────────────────────────────────────────────
STALE_THRESHOLD_SEC = 30        # Bu süre boyunca frame gelmezse "stale" sayılır
CHECK_INTERVAL_SEC = 10         # Watchdog kontrol sıklığı
MAX_RESTART_ATTEMPTS = 10       # Bir kamera için toplam restart denemesi
BASE_BACKOFF_SEC = 5            # İlk backoff bekleme süresi
MAX_BACKOFF_SEC = 120           # Maksimum backoff süresi
MAX_EVENT_HISTORY = 500         # Bellekte tutulan olay sayısı


class StreamWatchdog:
    """Aktif kamera stream'lerini izleyip sorunlu olanları yeniden başlatan
    daemon servisi.

    Bağımlılıklar inject edilir (frame_timestamps dict, restart callback)
    böylece farklı ortamlarda (test, prod) kullanılabilir.
    """

    def __init__(
        self,
        frame_timestamps: Dict[str, float],
        active_detectors: Dict[str, bool],
        restart_callback: Optional[Callable[[str], bool]] = None,
        stale_threshold: float = STALE_THRESHOLD_SEC,
        check_interval: float = CHECK_INTERVAL_SEC,
        max_restarts: int = MAX_RESTART_ATTEMPTS,
    ):
        """
        Args:
            frame_timestamps: camera_key → son frame zamanı (epoch).
                              Detection worker her frame aldığında günceller.
            active_detectors: camera_key → bool. Worker aktifse True.
            restart_callback: camera_key alıp yeniden başlatma yapan fonksiyon.
                              Başarılıysa True döner.
            stale_threshold:  Kaç saniye frame gelmezse stale sayılsın.
            check_interval:   Watchdog kontrol periyodu (saniye).
            max_restarts:     Bir kamera için max toplam restart denemesi.
        """
        self._frame_ts = frame_timestamps
        self._active = active_detectors
        self._restart_cb = restart_callback
        self._stale_threshold = stale_threshold
        self._check_interval = check_interval
        self._max_restarts = max_restarts

        # camera_key → restart bilgileri
        self._camera_state: Dict[str, Dict[str, Any]] = {}
        # Olay geçmişi (API erişimi için)
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # İstatistikler
        self._total_restarts = 0
        self._last_check_time: Optional[float] = None

    # ── Kamera state yönetimi ───────────────────────────────────────────────

    def _get_camera_state(self, camera_key: str) -> Dict[str, Any]:
        """Kamera için watchdog state'ini döndür, yoksa oluştur."""
        if camera_key not in self._camera_state:
            self._camera_state[camera_key] = {
                'restart_count': 0,
                'last_restart_time': None,
                'status': 'healthy',       # healthy | stale | restarting | dead
                'backoff_sec': BASE_BACKOFF_SEC,
                'first_stale_time': None,
            }
        return self._camera_state[camera_key]

    # ── Olay kayıt ──────────────────────────────────────────────────────────

    def _add_event(self, event_type: str, camera_key: str, detail: str = ''):
        with self._lock:
            event = {
                'time': datetime.now(timezone.utc).isoformat(),
                'type': event_type,
                'camera_key': camera_key,
                'detail': detail,
            }
            self._events.append(event)
            if len(self._events) > MAX_EVENT_HISTORY:
                self._events = self._events[-MAX_EVENT_HISTORY:]
            logger.info(f"[StreamWatchdog] {event_type}: {camera_key} — {detail}")

    # ── Backoff hesaplaması ──────────────────────────────────────────────────

    @staticmethod
    def _next_backoff(current: float) -> float:
        """Exponential backoff: 5 → 10 → 20 → 40 → 80 → 120 (max)."""
        return min(current * 2, MAX_BACKOFF_SEC)

    # ── Ana kontrol döngüsü ─────────────────────────────────────────────────

    def _check_loop(self):
        """Daemon thread olarak çalışır; periyodik olarak stream sağlığını
        kontrol eder."""
        logger.info("[StreamWatchdog] ✅ Watchdog daemon başlatıldı "
                     f"(stale_threshold={self._stale_threshold}s, "
                     f"check_interval={self._check_interval}s)")

        while self._running:
            try:
                self._perform_check()
            except Exception as exc:
                logger.error(f"[StreamWatchdog] ❌ Kontrol döngüsü hatası: {exc}")
            time.sleep(self._check_interval)

    def _perform_check(self):
        """Tek bir kontrol iterasyonu."""
        now = time.time()
        self._last_check_time = now

        # Aktif kameraları al
        active_keys = [k for k, v in self._active.items() if v]

        for camera_key in active_keys:
            state = self._get_camera_state(camera_key)

            # Zaten "dead" olarak işaretlenmişse tekrar deneme
            if state['status'] == 'dead':
                continue

            # "restarting" durumundaysa backoff süresi dolmamışsa atla
            if state['status'] == 'restarting':
                if (state['last_restart_time'] and
                        now - state['last_restart_time'] < state['backoff_sec']):
                    continue
                # Backoff süresi dolduysa — kontrol et, hâlâ stale mı?

            last_ts = self._frame_ts.get(camera_key)

            # Hiç frame timestamp yoksa henüz başlamamış olabilir; grace period
            if last_ts is None:
                if state.get('first_stale_time') is None:
                    state['first_stale_time'] = now
                elif now - state['first_stale_time'] > self._stale_threshold * 2:
                    # 2× stale threshold geçti, hiç frame gelmedi → restart dene
                    self._handle_stale(camera_key, state, now)
                continue

            seconds_since_frame = now - last_ts

            if seconds_since_frame <= self._stale_threshold:
                # Sağlıklı
                if state['status'] != 'healthy':
                    self._add_event('recovered', camera_key,
                                    f"Stream normale döndü ({seconds_since_frame:.0f}s)")
                    state['status'] = 'healthy'
                    state['backoff_sec'] = BASE_BACKOFF_SEC
                    state['first_stale_time'] = None
                continue

            # Stale tespit edildi
            self._handle_stale(camera_key, state, now)

    def _handle_stale(self, camera_key: str, state: Dict, now: float):
        """Stale stream için müdahale mantığı."""
        if state['restart_count'] >= self._max_restarts:
            if state['status'] != 'dead':
                state['status'] = 'dead'
                self._active[camera_key] = False
                self._add_event(
                    'dead', camera_key,
                    f"Maksimum restart denemesine ulaşıldı ({self._max_restarts}). "
                    f"Kamera 'dead' olarak işaretlendi."
                )
            return

        state['status'] = 'restarting'
        state['restart_count'] += 1
        state['last_restart_time'] = now
        self._total_restarts += 1

        backoff = state['backoff_sec']
        self._add_event(
            'restart', camera_key,
            f"Deneme {state['restart_count']}/{self._max_restarts} — "
            f"sonraki backoff {self._next_backoff(backoff):.0f}s"
        )

        # Restart callback'i çağır
        success = False
        if self._restart_cb:
            try:
                success = self._restart_cb(camera_key)
            except Exception as exc:
                logger.error(f"[StreamWatchdog] ❌ Restart callback hatası "
                             f"({camera_key}): {exc}")

        if success:
            self._add_event('restart_success', camera_key, "Callback başarılı")
            state['backoff_sec'] = BASE_BACKOFF_SEC
        else:
            self._add_event('restart_failed', camera_key,
                            f"Callback başarısız, backoff → {self._next_backoff(backoff):.0f}s")
            state['backoff_sec'] = self._next_backoff(backoff)

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self):
        """Watchdog'u daemon thread olarak başlat."""
        if self._running:
            logger.warning("[StreamWatchdog] Zaten çalışıyor")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop,
            name='StreamWatchdog',
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Watchdog'u durdur."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._check_interval + 2)
            self._thread = None
        logger.info("[StreamWatchdog] 🛑 Durduruldu")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """Watchdog özet durumu (API erişimi için)."""
        return {
            'running': self._running,
            'total_restarts': self._total_restarts,
            'last_check': (
                datetime.fromtimestamp(self._last_check_time, tz=timezone.utc).isoformat()
                if self._last_check_time else None
            ),
            'monitored_cameras': len([
                k for k, v in self._active.items() if v
            ]),
            'camera_states': {
                k: {
                    'status': s['status'],
                    'restart_count': s['restart_count'],
                    'backoff_sec': s['backoff_sec'],
                }
                for k, s in self._camera_state.items()
            },
        }

    def get_camera_health(self, camera_key: str) -> Dict[str, Any]:
        """Tek bir kameranın watchdog açısından sağlık durumu."""
        state = self._get_camera_state(camera_key)
        last_ts = self._frame_ts.get(camera_key)
        now = time.time()
        return {
            'camera_key': camera_key,
            'watchdog_status': state['status'],
            'restart_count': state['restart_count'],
            'last_frame_ts': last_ts,
            'seconds_since_last_frame': (
                round(now - last_ts, 1) if last_ts else None
            ),
            'backoff_sec': state['backoff_sec'],
            'is_active': self._active.get(camera_key, False),
        }

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Son olayları döndür (en yeni → en eski)."""
        with self._lock:
            return list(reversed(self._events[-limit:]))

    def reset_camera(self, camera_key: str):
        """Bir kameranın watchdog state'ini sıfırla (dead → tekrar denenebilir)."""
        if camera_key in self._camera_state:
            self._camera_state[camera_key] = {
                'restart_count': 0,
                'last_restart_time': None,
                'status': 'healthy',
                'backoff_sec': BASE_BACKOFF_SEC,
                'first_stale_time': None,
            }
            self._add_event('reset', camera_key, "Watchdog state sıfırlandı (manuel)")


# ── Singleton instance ──────────────────────────────────────────────────────

_watchdog_instance: Optional[StreamWatchdog] = None
_watchdog_lock = threading.Lock()


def init_stream_watchdog(
    frame_timestamps: Dict[str, float],
    active_detectors: Dict[str, bool],
    restart_callback: Optional[Callable[[str], bool]] = None,
) -> StreamWatchdog:
    """StreamWatchdog singleton'ını oluştur ve döndür."""
    global _watchdog_instance
    with _watchdog_lock:
        if _watchdog_instance is None:
            _watchdog_instance = StreamWatchdog(
                frame_timestamps=frame_timestamps,
                active_detectors=active_detectors,
                restart_callback=restart_callback,
            )
        return _watchdog_instance


def get_stream_watchdog() -> Optional[StreamWatchdog]:
    """Mevcut watchdog instance'ını döndür (henüz init edilmediyse None)."""
    return _watchdog_instance
