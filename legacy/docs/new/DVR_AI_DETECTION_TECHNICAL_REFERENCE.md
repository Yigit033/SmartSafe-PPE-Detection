# SmartSafe AI — Per-Channel DVR AI Detection: Technical Reference

> **Audience**: AI agents, developers, future maintainers.
> **Last updated**: 2026-04-01
> **Scope**: End-to-end flow of per-DVR-channel AI PPE detection — from the UI toggle to bounding-box overlay in the browser.
> **Prerequisite reading**: `docs/CAMERA_DVR_TECHNICAL_ARCHITECTURE.md` (stream/proxy layer).

---

## 1. Feature Summary

Users can enable/disable AI PPE detection **per DVR channel** (or regular IP camera) from the cameras page. When enabled:

1. A background detection worker reads frames, runs SH17 + PoseAware PPE inference.
2. Violation events (missing helmet, vest, etc.) are tracked, snapshotted, and persisted.
3. The browser receives a live MJPEG stream with bounding-box overlay drawn on each frame.
4. On page reload / pagination, the frontend restores which cameras have active AI from the backend.

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (Next.js, port 3377)                                          │
│                                                                          │
│  cameras/page.tsx                                                        │
│    ├─ toggleCameraAi(camera_id, currentStatus)                           │
│    │    → POST /api/company/{cid}/start-detection  { camera_id }         │
│    │    → POST /api/company/{cid}/stop-detection   { camera_id }         │
│    │                                                                     │
│    ├─ <img src=                                                          │
│    │     AI ON  → /api/company/{cid}/video-feed/{cam_id}                 │
│    │     AI OFF → /api/company/{cid}/cameras/{cam_id}/proxy-stream       │
│    │                                                                     │
│    ├─ syncAiStates() on mount                                            │
│    │    → GET /api/company/{cid}/active-detections                       │
│    │    → sets enabledAiCameras state                                    │
│    │                                                                     │
│    └─ enabledAiCameras: string[]   (React state, synced on load)         │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │ HTTP
┌──────────────────────────────▼─────────────────────────────────────────────┐
│  BACKEND  (Flask, port 5000)                                             │
│                                                                          │
│  ┌─── api/detection.py (Blueprint) ───────────────────────────────────┐  │
│  │                                                                    │  │
│  │  POST /start-detection                                             │  │
│  │    1. Validate camera exists (get_company_cameras)                 │  │
│  │    2. Resolve camera info (get_camera_by_id → get_dvr_channel_by_id)│ │
│  │    3. Check plan limits (max_cameras)                              │  │
│  │    4. Set active_detectors[camera_key] = True                      │  │
│  │    5. Spawn saas_detection_worker thread                           │  │
│  │                                                                    │  │
│  │  POST /stop-detection                                              │  │
│  │    1. Set active_detectors[camera_key] = False                     │  │
│  │    2. Release captures, clean up buffers                           │  │
│  │                                                                    │  │
│  │  GET /video-feed/{camera_id}                                       │  │
│  │    → if detection active: generate_saas_frames() (overlay MJPEG)   │  │
│  │    → if detection stopped: redirect → proxy-stream                 │  │
│  │                                                                    │  │
│  │  GET /active-detections                                            │  │
│  │    → returns list of camera_ids with active detection              │  │
│  │                                                                    │  │
│  │  GET /detection-status/{camera_id}                                 │  │
│  │    → per-camera active/inactive + recent results                   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─── app.py (Core API class) ────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │  saas_detection_worker(camera_key, camera_id, ...)                 │  │
│  │    ├─ Creates detection_results[camera_key] queue                  │  │
│  │    ├─ Calls start_saas_camera(...)                                 │  │
│  │    ├─ Loads SH17 / PoseAware model                                │  │
│  │    └─ WHILE active_detectors[key]:                                 │  │
│  │         read frame_buffers[key] → PPE detect → queue results      │  │
│  │                                                                    │  │
│  │  start_saas_camera(camera_key, camera_id, ...)                     │  │
│  │    ├─ Resolves camera_info (cameras + dvr_channels fallback)       │  │
│  │    ├─ DVR channel? → _start_dvr_detection_polling()                │  │
│  │    └─ IP camera?   → start_camera_with_alternatives()              │  │
│  │                                                                    │  │
│  │  _start_dvr_detection_polling(camera_key, ...)                     │  │
│  │    └─ Spawns _dvr_poll_worker thread:                              │  │
│  │         ├─ Checks for existing proxy stream                        │  │
│  │         │   (proxy:{company_id}:{stream_id})                       │  │
│  │         ├─ If found → reuses its frame buffer                      │  │
│  │         ├─ If not   → starts new DVR stream                        │  │
│  │         └─ WHILE active: decode b64 → cv2 frame → frame_buffers   │  │
│  │                                                                    │  │
│  │  generate_saas_frames(camera_key, ...)                             │  │
│  │    └─ WHILE active_detectors[key]:                                 │  │
│  │         frame_buffers[key] → get_detection_overlay()               │  │
│  │         → draw_saas_overlay() → JPEG encode → yield MJPEG         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─── Shared In-Memory State ─────────────────────────────────────────┐  │
│  │  active_detectors  : dict  {camera_key: bool}                      │  │
│  │  frame_buffers     : _ThreadSafeDict  {camera_key: np.ndarray}     │  │
│  │  detection_results : dict  {camera_key: Queue(maxsize=20)}         │  │
│  │  detection_threads : dict  {camera_key: {thread, config}}          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Camera Key Format

Every in-memory dict uses `camera_key` as the primary key:

```
camera_key = f"{company_id}_{camera_id}"
```

Examples:
- IP camera: `COMP_45AF2C1A_cam_001`
- DVR channel: `COMP_45AF2C1A_dvr_1775068806411_ch10`

The `camera_id` for DVR channels is the `channel_id` from `dvr_channels` table, formatted as `{dvr_id}_ch{NN}`.

---

## 4. Start Detection — Full Sequence

### 4.1 Frontend Trigger

```
File: frontend/app/cameras/page.tsx
Function: toggleCameraAi(id, currentStatus)
```

1. **Optimistic UI update**: `setEnabledAiCameras(prev => [...prev, id])`.
2. **API call**: `POST /api/company/{cid}/start-detection` with `{ camera_id }`.
3. **Stream switch**: `setRefreshKey(Date.now())` → `<img>` src changes from `proxy-stream` to `video-feed`.

### 4.2 Backend: `start_detection` Endpoint

```
File: core/api/detection.py
Route: POST /api/company/<company_id>/start-detection
```

Sequence:
1. Validates camera exists in `get_company_cameras()` (unified list: cameras + dvr_channels).
2. Gets full camera info:
   - `api.db.get_camera_by_id(camera_id, company_id)` — checks cameras table.
   - If `None` and camera_id contains DVR pattern → `api.db.get_dvr_channel_by_id(camera_id, company_id)` — checks dvr_channels JOIN dvr_systems.
3. Checks plan limits (max concurrent detection cameras per company).
4. Sets `active_detectors[camera_key] = True` on the **same dict reference** used by all threads.
5. Spawns `saas_detection_worker` thread with `active_detectors_ref` pointing to the same dict.

### 4.3 Backend: `saas_detection_worker`

```
File: core/app.py
Method: SmartSafeAPI.saas_detection_worker(camera_key, camera_id, company_id, ...)
```

Thread lifecycle:

1. **Queue init**: `detection_results[camera_key] = Queue(maxsize=20)`.
2. **Start frame source**: `start_saas_camera(camera_key, camera_id, company_id)`.
   - If DVR channel (`is_dvr` or `camera_type == 'dvr_channel'`): calls `_start_dvr_detection_polling()`.
   - If IP camera: calls `start_camera_with_alternatives()` (OpenCV HTTP/RTSP).
3. **Model loading**: SH17ModelManager + PoseAwarePPEDetector (singleton, shared across workers).
4. **Company config**: Reads sector, required_ppe from DB (`get_company_detection_config`).
5. **Initial wait**: 5 seconds for DVR (stream needs time), 0.3 seconds for IP camera.
6. **Detection loop** (`while active_detectors[camera_key]`):
   - Read `frame_buffers[camera_key]` via `copy_frame()` (thread-safe numpy copy).
   - Every `frame_skip` (default 3) frames: run PPE detection.
   - Detection pipeline: PoseAwarePPEDetector.detect_with_pose() → SH17 fallback.
   - ViolationTracker: event-based grouping, deduplication, severity classification.
   - Snapshot capture: full-frame + person-crop on new violations.
   - DB persist: violation_events, person_violations tables.
   - Queue results: `detection_results[camera_key].put_nowait(detection_data)`.

### 4.4 DVR Frame Polling

```
File: core/app.py
Method: SmartSafeAPI._start_dvr_detection_polling(camera_key, camera_id, camera_info, ...)
```

Spawns a `_dvr_poll_worker` thread that:

1. **Resolves stream_id**: `{dvr_id}_ch{NN:02d}` from camera_info or parsed from camera_id.
2. **Checks for existing proxy stream** (proxy-stream endpoint uses `proxy:{company_id}:{stream_id}`):
   - If stream with bare `stream_id` active → reuse.
   - If `proxy:{company_id}:{stream_id}` active → reuse that instead.
   - Otherwise → start a new stream via `DVRStreamHandler.start_stream()`.
3. **Polls frames continuously** (~25 FPS):
   - `DVRStreamHandler.get_latest_frame(stream_id)` → base64 JPEG.
   - Decode: `base64.b64decode → np.frombuffer → cv2.imdecode`.
   - Write: `frame_buffers[camera_key] = frame` (thread-safe dict).
4. **Exit**: When `active_detectors[camera_key]` becomes False.

**Key design decision**: The detection poll worker does NOT open its own RTSP connection. It reads from the DVRStreamHandler's existing frame buffer, which may already be fed by a proxy-stream request. This avoids duplicate RTSP connections to the same channel.

---

## 5. Video Feed — Overlay Delivery

### 5.1 Endpoint

```
File: core/api/detection.py
Route: GET /api/company/<company_id>/video-feed/<camera_id>
```

If `active_detectors[camera_key]` is True → returns `generate_saas_frames()` as `multipart/x-mixed-replace` MJPEG.

If detection is not active → **redirects to** `/api/company/{cid}/cameras/{cam_id}/proxy-stream` (fallback to raw stream).

### 5.2 Frame Generator

```
File: core/app.py
Method: SmartSafeAPI.generate_saas_frames(camera_key, ...)
```

Loop (while detection active):
1. Read raw frame from `frame_buffers[camera_key]`.
2. Call `get_detection_overlay(camera_key)` → reads latest result from `detection_results[camera_key]` queue.
3. If overlay exists → `draw_saas_overlay(frame, overlay)`:
   - HUD bar: people count, compliance rate, sector.
   - Bounding boxes: persons (green/red), PPE items (colored by type).
   - Missing PPE labels: floating tags above person bbox.
4. JPEG encode (quality=85) → yield as MJPEG frame.
5. Frame rate: ~30 FPS (`time.sleep(0.033)`).

---

## 6. Stop Detection — Teardown

### 6.1 Frontend

`toggleCameraAi(id, true)` → `POST /api/company/{cid}/stop-detection { camera_id }`.

UI: removes `id` from `enabledAiCameras` → img src switches back to `proxy-stream`.

### 6.2 Backend

```
File: core/api/detection.py
Route: POST /api/company/<company_id>/stop-detection
```

1. Sets `active_detectors[camera_key] = False`.
2. Both `_dvr_poll_worker` and `saas_detection_worker` check this flag in their while loops → exit gracefully.
3. Cleans up: releases `camera_captures`, removes from `frame_buffers`, `detection_threads`.
4. `generate_saas_frames` loop also exits → video-feed HTTP response completes.

---

## 7. State Persistence Across Page Reloads

### Problem

`enabledAiCameras` is React state (lost on reload). Pagination uses `window.location.href` (full reload) to kill old MJPEG connections.

### Solution

```
File: frontend/app/cameras/page.tsx
Function: syncAiStates(cid, cameras)
Called from: fetchCameras() callback
```

On every page load:
1. `fetchCameras()` fetches camera list from backend.
2. After cameras arrive, calls `syncAiStates(cid, cameras)`.
3. `syncAiStates` calls `GET /api/company/{cid}/active-detections`.
4. Backend scans `active_detectors` dict, returns IDs where value is True.
5. Frontend sets `enabledAiCameras` → correct img src (`video-feed` vs `proxy-stream`) renders immediately.

### Endpoint

```
File: core/api/detection.py
Route: GET /api/company/<company_id>/active-detections
```

No session required. Returns:
```json
{
  "success": true,
  "active_camera_ids": ["dvr_1775068806411_ch09", "dvr_1775068806411_ch10"]
}
```

---

## 8. Database: DVR Channel + Violation Persistence

### 8.1 FK Constraint Resolution

**Problem**: `violation_events.camera_id` had a FOREIGN KEY referencing `cameras(camera_id)`. DVR channel IDs exist only in `dvr_channels` table, not `cameras`.

**Solution** (PR1 → PR3):
- PostgreSQL: `ALTER TABLE violation_events DROP CONSTRAINT IF EXISTS violation_events_camera_id_fkey` runs at table init.
- `violation_events`: `source_type` (`camera` | `dvr_channel`), `dvr_channel_id` → `dvr_channels`, no shadow `cameras` rows. **PR3:** CHECK + `source_type NOT NULL`, DVR satırlarında `camera_id` NULL; `add_violation_event` DVR’da yalnızca `dvr_channel_id` yazar (fail-fast korunur). API `getEvents` `source_type` ile ayrı join; `camera_id` cevapta geri uyum için `dvr_channel_id` ile doldurulur.

### 8.2 get_dvr_channel_by_id

```
File: core/database/database_adapter.py
Method: DatabaseAdapter.get_dvr_channel_by_id(channel_id, company_id)
```

SQL: `SELECT ... FROM dvr_channels dc JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id WHERE dc.channel_id = ? AND dc.company_id = ?`

Returns a camera-shaped dict with:
- `camera_id` (= channel_id)
- `ip_address`, `port`, `username`, `password` (from dvr_systems)
- `stream_path`, `rtsp_url` (= rtsp_path from dvr_channels)
- `protocol`: always `'rtsp'`
- `camera_type`: `'dvr_channel'`
- `is_dvr`: `True`
- `dvr_id`, `channel_number`: DVR-specific fields

### 8.3 Violation Storage Path

```
violation_events:
  event_id    = VIO_{camera_id}_{person_id}_{timestamp}
  company_id  = COMP_45AF2C1A
  camera_id   = dvr_1775068806411_ch10
  person_id   = PERSON_A1B2C3D4
  violation_type = no_helmet,no_vest
  snapshot_path = COMP_45AF2C1A/dvr_1775068806411_ch10/2026-04-01/PERSON_xxx_no_helmet_123.jpg
```

---

## 9. Detection Pipeline Detail

### 9.1 Model Hierarchy

```
Priority 1: PoseAwarePPEDetector.detect_with_pose(frame, sector, confidence)
  → Uses YOLOv8-Pose for skeleton detection
  → Maps PPE items to body zones (head→helmet, torso→vest, etc.)
  → Returns dict: {people_detected, compliance_rate, ppe_violations, detections}
  → Can return list (legacy format) — caller must normalize

Priority 2: SH17ModelManager.detect_ppe(frame, sector, confidence)
  → Direct YOLO detection without pose mapping
  → Returns list of detections

Fallback: Empty results if both fail
```

### 9.2 Result Normalization

`detect_with_pose()` may return either `dict` or `list`:

```python
# In dvr_stream_handler.py _perform_ppe_detection():
result = self._pose_detector.detect_with_pose(frame, sector, confidence=0.25)
if isinstance(result, dict):
    return result
if isinstance(result, list):
    # Normalize to dict format
    return {
        'detections': result,
        'people_detected': len([d for d in result if d.get('class_name') == 'person']),
        'compliance_rate': 100,
        'ppe_violations': [],
        ...
    }
```

The same normalization exists in `saas_detection_worker` (app.py).

### 9.3 ViolationTracker

```
File: core/detection/violation_tracker.py
```

Event-based tracking per person:
- Groups detections by `person_id` (assigned via pose/bbox matching).
- New violation → snapshot + DB insert.
- Violation resolved → duration calculation + resolution snapshot + DB update.
- Monthly stats tracking in `person_violations` table.

### 9.4 Sector-Based PPE Requirements

Each company has a sector (food, construction, chemical, etc.) that determines required PPE:

```python
SECTOR_DEFAULT_PPE = {
    'food':         ['haircap', 'face_mask', 'gloves', 'safety_suit'],
    'construction': ['helmet', 'safety_vest', 'safety_shoes'],
    'chemical':     ['helmet', 'safety_vest', 'safety_glasses', 'gloves'],
    ...
}
```

DB override: `companies.ppe_requirements` (JSON) takes precedence if defined.

---

## 10. Thread Architecture

Per active AI camera, the following threads exist:

| Thread | Purpose | Lifecycle |
|---|---|---|
| `saas_detection_worker` | PPE inference loop | Lives while `active_detectors[key]` is True |
| `_dvr_poll_worker` (DVR only) | Reads frames from DVRStreamHandler → frame_buffers | Lives while `active_detectors[key]` is True |
| `_stream_worker` (DVRStreamHandler) | RTSP capture → DVR frame_buffers | May outlive detection (shared with proxy-stream) |
| `generate_saas_frames` (generator) | MJPEG frame yield | Lives while HTTP connection open AND detection active |

### Thread-Safe Shared State

```python
frame_buffers = _ThreadSafeDict()   # Lock-protected dict subclass
active_detectors = {}                # Plain dict — Python GIL protects simple reads/writes
detection_results = {}               # Values are Queue objects (inherently thread-safe)
```

`_ThreadSafeDict` provides:
- `__setitem__`, `__getitem__`, `__contains__`: lock-protected.
- `copy_frame(key)`: returns `frame.copy()` under lock (prevents numpy array mutation during read).

---

## 11. Stream ID Conventions

| Context | Format | Example |
|---|---|---|
| Proxy-stream endpoint | `proxy:{company_id}:{camera_id}` | `proxy:COMP_45AF2C1A:dvr_1775068806411_ch09` |
| Detection poll worker (prefers proxy) | `{dvr_id}_ch{NN:02d}` or proxy format | `dvr_1775068806411_ch09` |
| DVRStreamHandler frame_buffers key | Same as stream_id | `proxy:COMP_45AF2C1A:dvr_1775068806411_ch09` |
| App-level frame_buffers key | `{company_id}_{camera_id}` | `COMP_45AF2C1A_dvr_1775068806411_ch09` |
| active_detectors key | `{company_id}_{camera_id}` | `COMP_45AF2C1A_dvr_1775068806411_ch09` |

The poll worker checks both formats to reuse an existing proxy stream rather than opening a duplicate RTSP connection.

---

## 12. Overlay Drawing

```
File: core/app.py
Methods: draw_saas_overlay(), draw_hud_bar(), reset_label_registry()
```

### HUD Bar (top of frame)
- People count, compliant count, compliance %, sector name.
- Color-coded: green (>80%), yellow (50-80%), red (<50%).

### Bounding Boxes
Draw order (for correct z-stacking):
1. Person rectangles (green if compliant, red if violating).
2. Positive PPE items (blue/green boxes with label).
3. Missing PPE items (red boxes with "MISSING: {item}" label).

### Label Deconfliction
`reset_label_registry()` / label registry prevents overlapping text labels by tracking used positions and offsetting new labels vertically.

---

## 13. Known Issues & Design Decisions

### 13.1 First Detection Latency
The first PPE detection per worker takes 25-40 seconds due to:
- SH17 model weight loading (first call).
- PoseAware detector initialization.
- CUDA/CPU warm-up.

Subsequent detections: 1-3 seconds.

**Mitigation**: During warm-up, `video-feed` serves raw frames without overlay (frames still flow from DVR poll worker).

### 13.2 Browser Connection Limits
Chrome limits ~6 concurrent HTTP connections per origin. MJPEG streams (both proxy-stream and video-feed) each consume 1 connection.

**Mitigation**: Pagination uses `window.location.href` (full page reload) to terminate all old connections before opening new ones.

### 13.3 Dual Stream Avoidance
Without the proxy-stream reuse logic, enabling AI detection would open a second RTSP connection to the same DVR channel. The `_dvr_poll_worker` checks for existing `proxy:{cid}:{stream_id}` streams first.

### 13.4 Detection Worker Exit Diagnostics
On exit, the worker logs:
```
🛑 SaaS Detection durduruldu - Kamera: {cam_id} | active_detectors[{key}]={val} | frame_count={n} | detection_count={n} | id(ad)={id}
```
This helps diagnose whether the exit was intentional (user stop) or a dict reference mismatch (Flask reloader).

---

## 14. API Endpoint Summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/company/{cid}/start-detection` | None* | Start AI detection for a camera |
| POST | `/api/company/{cid}/stop-detection` | None* | Stop AI detection for a camera |
| POST | `/api/company/{cid}/start-detection-batch` | None* | Start detection for multiple cameras |
| POST | `/api/company/{cid}/stop-detection-batch` | Session | Stop detection for multiple cameras |
| GET | `/api/company/{cid}/video-feed/{cam_id}` | None* | MJPEG stream with AI overlay |
| GET | `/api/company/{cid}/active-detections` | None* | List of camera IDs with active AI |
| GET | `/api/company/{cid}/detection-status/{cam_id}` | None* | Per-camera detection status |
| GET | `/api/company/{cid}/detection-results/{cam_id}` | Session | Latest detection result |
| GET | `/api/company/{cid}/cameras/{cam_id}/proxy-stream` | None* | Raw MJPEG stream (no AI) |
| GET | `/api/company/{cid}/violations/stream` | Session | SSE real-time violation feed |

*Session validation is commented out in development; should be re-enabled for production.

---

## 15. File Reference

| File | Role |
|---|---|
| `frontend/app/cameras/page.tsx` | UI: camera grid, AI toggle, pagination, stream display |
| `core/api/detection.py` | Flask blueprint: start/stop detection, video-feed, active-detections |
| `core/api/camera.py` | Flask blueprint: proxy-stream, camera CRUD, stream-status |
| `core/app.py` | Core API class: detection worker, DVR poll worker, frame generator, overlay drawing |
| `core/integrations/dvr/dvr_stream_handler.py` | DVRStreamHandler: RTSP capture, frame buffers, inline PPE detection |
| `core/database/database_adapter.py` | DB adapter: violation_events, dvr_channels, cameras, shadow rows |
| `core/services/multitenant_system.py` | Unified camera list (cameras + dvr_channels), company info |
| `core/detection/violation_tracker.py` | Event-based violation grouping and lifecycle |
| `core/detection/pose_aware_ppe_detector.py` | Pose-aware PPE detection (YOLOv8-Pose + SH17) |
| `core/models/sh17_model_manager.py` | SH17 PPE detection model manager |
| `core/detection/snapshot_manager.py` | Violation snapshot capture and storage |

---

## 16. Appendix: Data Flow Diagram (AI Toggle ON)

```
User clicks "AI VIEW" on Channel 10
         │
         ▼
toggleCameraAi("dvr_xxx_ch10", false)
         │
    ┌────┴────────────────────────────────┐
    │ 1. Optimistic UI update             │
    │    enabledAiCameras += "dvr_xxx_ch10"│
    │ 2. POST /start-detection            │
    │ 3. img.src → /video-feed/dvr_xxx_ch10│
    └────┬────────────────────────────────┘
         │
         ▼
   start_detection endpoint
         │
    ┌────┴─────────────────────────────────────┐
    │ active_detectors[key] = True              │
    │ spawn saas_detection_worker thread        │
    └────┬─────────────────────────────────────┘
         │
         ├──── saas_detection_worker ──────────────────┐
         │     │                                        │
         │     ├─ start_saas_camera()                   │
         │     │   └─ _start_dvr_detection_polling()    │
         │     │       └─ _dvr_poll_worker thread ◄─────┤
         │     │           │                             │
         │     │           ├─ Find proxy stream          │
         │     │           │  (proxy:COMP:dvr_xxx_ch10)  │
         │     │           │                             │
         │     │           └─ LOOP: get_latest_frame()   │
         │     │              → decode → frame_buffers   │
         │     │                                         │
         │     ├─ Load SH17 + PoseAware model            │
         │     │  (25-40s first time)                    │
         │     │                                         │
         │     └─ LOOP: read frame_buffers               │
         │         → PPE detect every 3 frames           │
         │         → detection_results queue             │
         │         → ViolationTracker → DB               │
         │                                               │
         ├──── generate_saas_frames ◄───── video-feed ──┤
         │     │                                         │
         │     └─ LOOP: read frame_buffers               │
         │         → get_detection_overlay()              │
         │         → draw_saas_overlay() [bbox, HUD]     │
         │         → yield MJPEG frame to browser        │
         │                                               │
         └─────────────────────────────────────────────────
```
