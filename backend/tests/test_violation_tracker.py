"""Tests for ViolationTracker thread safety and core logic."""
import threading
import time
from src.smartsafe.detection.violation_tracker import ViolationTracker


def test_tracker_init():
    vt = ViolationTracker(cooldown_period=30)
    assert vt.cooldown_period == 30
    assert hasattr(vt, '_lock')


def test_iou_calculation():
    vt = ViolationTracker()
    iou = vt.calculate_iou([0, 0, 10, 10], [5, 5, 15, 15])
    assert 0.0 < iou < 1.0

    perfect = vt.calculate_iou([0, 0, 10, 10], [0, 0, 10, 10])
    assert abs(perfect - 1.0) < 0.01

    no_overlap = vt.calculate_iou([0, 0, 5, 5], [10, 10, 20, 20])
    assert no_overlap == 0.0


def test_process_detection_returns_tuple():
    vt = ViolationTracker()
    new_v, ended_v = vt.process_detection(
        camera_id='cam1',
        company_id='company1',
        person_bbox=[10, 10, 100, 200],
        violations=['Baret eksik']
    )
    assert isinstance(new_v, list)
    assert isinstance(ended_v, list)


def test_get_active_violations_empty():
    vt = ViolationTracker()
    active = vt.get_active_violations()
    assert isinstance(active, list)
    assert len(active) == 0


def test_concurrent_access():
    """ViolationTracker should handle concurrent access without errors."""
    vt = ViolationTracker()
    errors = []

    def worker(cam_id):
        try:
            for i in range(20):
                vt.process_detection(
                    camera_id=cam_id,
                    company_id='company1',
                    person_bbox=[10 + i, 10 + i, 100 + i, 200 + i],
                    violations=['Baret eksik']
                )
                vt.get_active_violations(cam_id)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(f'cam{j}',)) for j in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(errors) == 0, f"Thread errors: {errors}"
