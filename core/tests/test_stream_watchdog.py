"""Tests for StreamWatchdog."""

import time
import pytest
from integrations.cameras.stream_watchdog import StreamWatchdog


class TestStreamWatchdog:
    """StreamWatchdog birim testleri."""

    def _make_watchdog(self, **kwargs):
        """Helper: test ortamı için hızlı watchdog oluştur."""
        ts = kwargs.pop('frame_timestamps', {})
        ad = kwargs.pop('active_detectors', {})
        defaults = {
            'stale_threshold': 2,
            'check_interval': 0.5,
            'max_restarts': 3,
        }
        defaults.update(kwargs)
        return StreamWatchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            **defaults,
        )

    # ── Backoff hesaplaması ──────────────────────────────────────────────

    def test_exponential_backoff(self):
        """Backoff: 5 → 10 → 20 → 40 → 80 → 120 (max)."""
        assert StreamWatchdog._next_backoff(5) == 10
        assert StreamWatchdog._next_backoff(10) == 20
        assert StreamWatchdog._next_backoff(80) == 120
        assert StreamWatchdog._next_backoff(120) == 120  # max cap

    # ── Stale tespiti ────────────────────────────────────────────────────

    def test_healthy_stream_not_flagged(self):
        """Son 2 saniye içinde frame gelen kamera healthy kalmalı."""
        ts = {'comp_cam1': time.time()}
        ad = {'comp_cam1': True}
        wd = self._make_watchdog(frame_timestamps=ts, active_detectors=ad)

        wd._perform_check()

        state = wd._get_camera_state('comp_cam1')
        assert state['status'] == 'healthy'
        assert state['restart_count'] == 0

    def test_stale_stream_triggers_restart(self):
        """Stale threshold aşıldığında kamera restarting olmalı."""
        ts = {'comp_cam1': time.time() - 10}  # 10 saniye önce
        ad = {'comp_cam1': True}
        restart_calls = []

        def fake_restart(key):
            restart_calls.append(key)
            return True

        wd = self._make_watchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            restart_callback=fake_restart,
        )

        wd._perform_check()

        assert len(restart_calls) == 1
        assert restart_calls[0] == 'comp_cam1'

    def test_max_restart_marks_dead(self):
        """Max restart aşılınca kamera dead olmalı ve active_detectors False olmalı."""
        ts = {'comp_cam1': time.time() - 100}
        ad = {'comp_cam1': True}
        wd = self._make_watchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            restart_callback=lambda k: False,  # Restart hep başarısız
            max_restarts=2,
        )

        # İlk iki deneme
        wd._perform_check()
        assert wd._get_camera_state('comp_cam1')['restart_count'] == 1

        wd._get_camera_state('comp_cam1')['last_restart_time'] = time.time() - 200
        wd._perform_check()
        assert wd._get_camera_state('comp_cam1')['restart_count'] == 2

        # Üçüncü deneme — max aşıldı, dead olmalı
        wd._get_camera_state('comp_cam1')['last_restart_time'] = time.time() - 200
        wd._perform_check()
        assert wd._get_camera_state('comp_cam1')['status'] == 'dead'
        assert ad['comp_cam1'] is False

    # ── Recovery ─────────────────────────────────────────────────────────

    def test_recovery_resets_backoff(self):
        """Kamera düzeldiğinde (yeni frame geldiğinde) backoff sıfırlanmalı."""
        ts = {'comp_cam1': time.time() - 10}
        ad = {'comp_cam1': True}
        wd = self._make_watchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            restart_callback=lambda k: True,
        )

        # İlk kontrol: stale → restart tetiklenir
        wd._perform_check()
        state = wd._get_camera_state('comp_cam1')
        assert state['status'] == 'restarting'
        assert state['restart_count'] == 1

        # Kamera geri geldi (yeni frame geldi) — backoff süresini de geçir
        ts['comp_cam1'] = time.time()
        state['last_restart_time'] = time.time() - 200  # Backoff geçmiş sayılsın
        wd._perform_check()
        assert wd._get_camera_state('comp_cam1')['status'] == 'healthy'
        assert wd._get_camera_state('comp_cam1')['backoff_sec'] == 5  # BASE_BACKOFF

    # ── Manual reset ─────────────────────────────────────────────────────

    def test_reset_camera(self):
        """reset_camera state'i tamamen sıfırlamalı."""
        ts = {'comp_cam1': time.time() - 100}
        ad = {'comp_cam1': True}
        wd = self._make_watchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            restart_callback=lambda k: False,
            max_restarts=1,
        )

        wd._perform_check()
        wd._get_camera_state('comp_cam1')['last_restart_time'] = time.time() - 200
        wd._perform_check()
        assert wd._get_camera_state('comp_cam1')['status'] == 'dead'

        wd.reset_camera('comp_cam1')
        assert wd._get_camera_state('comp_cam1')['status'] == 'healthy'
        assert wd._get_camera_state('comp_cam1')['restart_count'] == 0

    # ── Status/events API ────────────────────────────────────────────────

    def test_get_status(self):
        """get_status doğru yapıyı döndürmeli."""
        wd = self._make_watchdog()
        status = wd.get_status()
        assert 'running' in status
        assert 'total_restarts' in status
        assert 'monitored_cameras' in status

    def test_events_recorded(self):
        """Olaylar kaydedilmeli ve get_events ile erişilebilmeli."""
        ts = {'comp_cam1': time.time() - 10}
        ad = {'comp_cam1': True}
        wd = self._make_watchdog(
            frame_timestamps=ts,
            active_detectors=ad,
            restart_callback=lambda k: True,
        )

        wd._perform_check()
        events = wd.get_events(limit=5)
        assert len(events) > 0
        assert events[0]['camera_key'] == 'comp_cam1'

    # ── Start/stop ───────────────────────────────────────────────────────

    def test_start_stop(self):
        """Watchdog başlayıp durabiliyor olmalı."""
        wd = self._make_watchdog()
        wd.start()
        assert wd.is_running is True
        wd.stop()
        assert wd.is_running is False
