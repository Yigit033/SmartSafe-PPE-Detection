# SmartSafe AI — Camera & DVR Subsystem: Technical Architecture Reference

> **Audience**: AI agents, developers, future maintainers.
> **Last updated**: 2026-04-01
> **Scope**: End-to-end flow from physical DVR/NVR hardware to browser pixel.

---

## 1. System Overview

SmartSafe AI is a SaaS PPE (Personal Protective Equipment) compliance system. It connects to customer DVR/NVR devices via RTSP, pulls live video, optionally runs AI detection (hard-hat, vest, etc.), and serves the result to a Next.js frontend as MJPEG streams over HTTP.

### High-Level Data Flow

```
DVR/NVR (RTSP, port 554)
   │
   ▼
┌─────────────────────────────────────────────────┐
│  Flask Backend (port 5000)                      │
│                                                 │
│  dvr_stream_handler.py                          │
│    └─ _stream_worker thread per channel         │
│        ├─ cv2.VideoCapture(rtsp_url, TCP)       │
│        ├─ frame → JPEG → base64 → frame_buffer  │
│        └─ every 15 frames → PPE detection       │
│                                                 │
│  dvr.py (Flask Blueprint)                       │
│    └─ /mjpeg/<channel>  (multipart/x-mixed-     │
│        replace) reads frame_buffer, overlays     │
│        detection boxes, yields JPEG parts        │
│                                                 │
│  proxy-stream endpoint                          │
│    └─ same MJPEG approach but no AI overlay     │
└────────────────────┬────────────────────────────┘
                     │ HTTP (MJPEG)
                     ▼
┌─────────────────────────────────────────────────┐
│  Next.js Frontend (port 3377)                   │
│  cameras/page.tsx                               │
│    └─ <img src="…/proxy-stream"> per camera     │
│       (6 per page, paginated with ?page=N)      │
└─────────────────────────────────────────────────┘
```

### Key Constraint: Browser Connection Limit

Browsers enforce **~6 concurrent HTTP connections per origin** (same host+port). Each MJPEG `<img>` holds one persistent connection open. With 6 cameras per page this is exactly at the limit. Pagination uses `window.location.href` (full page reload) when switching pages to guarantee old MJPEG connections are fully released before new ones open.

---

## 2. Backend Architecture

### 2.1 File Map

| File | Role |
|---|---|
| `core/api/dvr.py` | Flask Blueprint — all DVR REST endpoints |
| `core/integrations/dvr/dvr_stream_handler.py` | RTSP connection, frame capture, PPE detection, MJPEG serving |
| `core/integrations/cameras/camera_integration_manager.py` | DVR lifecycle (add/remove/discover), DVRConfig/DVRChannel dataclasses |
| `core/database/database_adapter.py` | SQLite/PostgreSQL adapter — DVR, channel, stream persistence |
| `core/integrations/cameras/onvif_discovery.py` | ONVIF WS-Discovery and stream URI resolution |
| `core/integrations/dvr/dvr_ppe_integration.py` | DVR-specific PPE detection sessions |
| `core/detection/pose_aware_ppe_detector.py` | Pose-aware PPE detection (Phase 3) |
| `core/models/sh17_model_manager.py` | SH-17 dataset model for PPE class detection |

### 2.2 DVRStreamHandler — Singleton

`dvr_stream_handler.py` exports a module-level singleton:

```python
stream_handler = DVRStreamHandler()

def get_stream_handler() -> DVRStreamHandler:
    return stream_handler
```

**Critical instance state**:

| Attribute | Type | Purpose |
|---|---|---|
| `active_streams` | `Dict[stream_id, Dict]` | Per-stream metadata: status, rtsp_url, frame_count, detection_result, sector, etc. |
| `frame_buffers` | `Dict[stream_id, list[base64_jpeg]]` | Ring buffer (max 5 frames) of latest JPEG frames per stream |
| `_onvif_uri_cache` | `Dict["ip:channel", str]` | ONVIF-resolved stream URIs, never expire (process lifetime) |
| `_success_url_cache` | `Dict["ip:channel", str]` | In-memory cache of working RTSP URLs |
| `_probe_success_ttl` | `Dict[str, (str, float)]` | TTL cache for successful URL probes (default 600s) |
| `_probe_fail_ttl` | `Dict[str, (str, float)]` | TTL cache for failed probes (default 60s) |
| `_onvif_fail_cache` | `Dict[ip, float]` | Negative cache — skip ONVIF for this IP for 5 minutes after failure |
| `_probe_sem` | `Semaphore(4)` | Limits concurrent RTSP probe connections (env: DVR_PROBE_CONCURRENCY) |
| `_sh17_manager` | singleton | Lazy-init PPE model — shared across all streams |
| `_pose_detector` | singleton | Lazy-init pose-aware detector — shared across all streams |

### 2.3 Stream Lifecycle (State Machine)

```
start_stream() called
        │
        ▼
    ┌──────────┐
    │ starting  │
    └────┬─────┘
         │  _stream_worker thread launched
         ▼
   ┌───────────┐    URL discovery fails
   │  active    │◄──────────────────────── (error → reconnect loop)
   └─────┬─────┘
         │  stop_stream() or fatal errors
         ▼
   ┌───────────┐
   │  stopping  │──► stopped
   └───────────┘
         │  max reconnect failures
         ▼
   ┌───────────┐
   │   error    │  (last_error_code: NO_NETWORK | OPEN_FAILED | RECONNECT_FAILED | WORKER_EXCEPTION)
   └───────────┘
```

Transitions are tracked via `_transition()` with timestamp and reason.

---

## 3. RTSP URL Resolution Strategy

This is the most complex part. DVR brands use incompatible RTSP path conventions.

### 3.1 URL Resolution Order (per channel)

```
1. ONVIF URI Cache hit?                    → use immediately (<1ms)
2. Success URL Cache (memory) hit?         → verify with quick open (500ms)
3. Success URL Cache (database) hit?       → verify with quick open (500ms)
4. TTL success cache hit?                  → use immediately
5. TTL fail cache hit?                     → return None (skip probing)
6. ONVIF WS-Discovery                     → get URI from device (~2-5s)
7. Full Discovery (brute-force)            → try up to 18 URLs (~30-60s)
```

### 3.2 Supported RTSP URL Patterns by Brand

| Brand | Pattern Examples |
|---|---|
| **XM/Xiongmai** | `rtsp://{ip}:{port}/user={user}&password={pass}&channel={ch}&stream=0.sdp` |
| **Hikvision** | `rtsp://{user}:{pass}@{ip}:{port}/ISAPI/Streaming/channels/{ch*100+1}` |
| **Dahua** | `rtsp://{user}:{pass}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0` |
| **Generic** | `/ch{ch:02d}/main`, `/live/ch{ch:02d}`, `/stream/channel{ch}`, etc. |
| **Axis** | `/axis-media/media.amp?videocodec=h264&camera={ch}` |

Full pattern lists are in `DVRStreamHandler.__init__` → `self.dvr_url_patterns`.

### 3.3 Brand Detection

`detect_dvr_brand()` tests channel 1-2 against known URL patterns. First successful open determines brand. Returns `'xm'`, `'hikvision'`, `'dahua'`, `'generic'`.

### 3.4 URL Caching (3-Tier)

1. **Memory** (`_success_url_cache`): `Dict["ip:channel"] → url`. Fastest. Lost on restart.
2. **TTL** (`_probe_success_ttl`): Same as memory but with expiration (default 600s).
3. **Database** (`dvr_channels.rtsp_path` column): Persistent across restarts. Written via `DatabaseAdapter.update_channel_rtsp_path()`.

Cache invalidation: if a cached URL fails verification, it's evicted from memory and a full discovery runs.

### 3.5 RTSP Transport

All connections forced to **TCP** (not UDP) via environment variable:

```python
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;2000000|probesize;1000000"
```

This prevents UDP packet loss and H.265 PPS errors on Hikvision/Dahua NVRs.

### 3.6 Probe Storm Prevention

| Control | Default | Env Var |
|---|---|---|
| Concurrent probe semaphore | 4 | `DVR_PROBE_CONCURRENCY` |
| URLs tried per start_stream | 18 | `DVR_START_URL_BUDGET` |
| URLs tried per channel probe | 6 | `DVR_CHANNEL_PROBE_URL_BUDGET` |
| Parallel channel probe workers | 4 | `DVR_CHANNEL_PROBE_WORKERS` |
| Success TTL | 600s | `DVR_PROBE_TTL_SUCCESS_S` |
| Fail TTL | 60s | `DVR_PROBE_TTL_FAIL_S` |

---

## 4. ONVIF Integration

### 4.1 When Used

- **Channel discovery**: `detect_available_channels()` tries ONVIF first (fast ~2s). Falls back to parallel RTSP probing.
- **Stream start**: `start_stream()` calls `_try_onvif_stream_uri()` before using the seed URL.

### 4.2 Negative Cache

If ONVIF fails for an IP, the IP is added to `_onvif_fail_cache` with a 5-minute TTL. No ONVIF attempts for that IP until expiry. This prevents repeated 5-10s timeouts on devices that don't support ONVIF.

### 4.3 ONVIF URI Cache

Successfully resolved URIs are stored in `_onvif_uri_cache["ip:channel"]`. These never expire (process lifetime) since ONVIF URIs don't change unless the device is reconfigured.

---

## 5. Channel Discovery Flow

Triggered by `POST /api/company/{cid}/dvr/{dvr_id}/discover`.

```
1. DVRManager.discover_cameras(dvr_id, company_id)
   │
   ├── Load DVRConfig from DB if not in memory cache
   │
   ├── _discover_dvr_channels(dvr_config)
   │     Brand-specific API probing (HTTP/ISAPI/etc.)
   │     If fails → _discover_generic_channels()
   │
   ├── detect_available_channels() [DVRStreamHandler]
   │     ONVIF first → RTSP parallel probe fallback
   │     Returns List[int] of working channel numbers
   │     Filters brand-discovered channels to only those confirmed working
   │
   ├── Deep Scan: parallel find_working_url() per channel
   │     ThreadPoolExecutor(max_workers=8)
   │     Sets channel.status = 'active' if working URL found
   │     Sets channel.rtsp_path = full working RTSP URL
   │
   ├── Cleanup: delete_dvr_channel() for previously stored channels
   │     that are no longer in the active set
   │
   └── Persist: add_dvr_channel() only for active channels
```

### Result returned to frontend

```json
{
  "success": true,
  "channels": [/* only active channels */],
  "count": 8,
  "inactive_count": 4,
  "total_scanned": 12
}
```

---

## 6. MJPEG Stream Serving

### 6.1 Endpoint

`GET /api/company/{cid}/dvr/{dvr_id}/mjpeg/{channel_number}`

### 6.2 How It Works

```python
def generate():
    while True:
        frame_b64 = stream_handler.get_latest_frame(stream_id)
        if frame_b64:
            jpg_bytes = base64.b64decode(frame_b64)
            frame = cv2.imdecode(...)
            # Overlay detection bounding boxes
            detection_result = stream_handler.get_latest_detection_result(stream_id)
            if detection_result:
                frame = api.draw_saas_overlay(frame, detection_result)
            # Re-encode and yield
            yield b"--frame\r\nContent-Type: image/jpeg\r\n..." + jpg_bytes
        time.sleep(0.04)  # ~25 FPS

return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
```

### 6.3 proxy-stream Endpoint

`GET /api/company/{cid}/cameras/{camera_id}/proxy-stream`

Same MJPEG approach but **without AI overlay**. Used when AI toggle is off.

### 6.4 video-feed Endpoint

`GET /api/company/{cid}/video-feed/{camera_id}`

MJPEG **with AI overlay** (bounding boxes, compliance labels). Used when AI toggle is on.

---

## 7. PPE Detection Pipeline

### 7.1 Trigger

Every 15 frames (configurable via `detection_frequency` per stream), `_stream_worker` calls `_perform_ppe_detection(frame, stream_id)`.

### 7.2 Detection Strategy

```
1. Resolve sector from: immutable_config → stream metadata → default 'construction'
2. Resolve required_ppe from: immutable_config → sector defaults
3. Try Pose-Aware Detection (Phase 3):
     PoseAwarePPEDetector.detect_with_pose(frame, sector, confidence=0.25)
     Uses singleton _pose_detector and _sh17_manager
4. Fallback: Standard SH17 Detection:
     SH17ModelManager.detect_ppe(frame, sector, confidence=0.25)
     analyze_compliance(detections, required_ppe)
```

### 7.3 Detection Result Schema

```python
{
    'detections': [{'class_name': str, 'confidence': float, 'bbox': [x1,y1,x2,y2]}, ...],
    'people_detected': int,
    'compliance_rate': int,        # 0-100
    'ppe_violations': [str, ...],  # e.g. ['no_helmet', 'no_vest']
    'timestamp': float,
    'sector': str,
    'model_type': str              # 'SH17' | 'Fallback' | 'Error'
}
```

Results are stored in `active_streams[stream_id]['detection_result']` and read by MJPEG endpoint for overlay.

---

## 8. Database Schema (DVR-Related Tables)

### 8.1 dvr_systems

| Column | Type | Notes |
|---|---|---|
| dvr_id | TEXT PK | User-defined or auto-generated |
| company_id | TEXT | Foreign key to companies |
| name | TEXT | Display name |
| ip_address | TEXT | DVR IP |
| port | INT | HTTP port (default 80) |
| username | TEXT | Login user |
| password | TEXT | Login password |
| dvr_type | TEXT | 'generic', 'hikvision', 'dahua', 'xm', 'axis' |
| protocol | TEXT | 'http' or 'https' |
| api_path | TEXT | Default '/api' |
| rtsp_port | INT | Default 554 |
| max_channels | INT | Expected channel count (updated dynamically on discover) |
| status | TEXT | 'active', 'inactive' |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 8.2 dvr_channels

| Column | Type | Notes |
|---|---|---|
| channel_id | TEXT PK | Format: `{dvr_id}_ch{NN:02d}` |
| dvr_id | TEXT | FK → dvr_systems |
| company_id | TEXT | FK → companies |
| name | TEXT | Channel display name |
| channel_number | INT | 1-based |
| status | TEXT | 'active', 'inactive', 'available' |
| resolution_width | INT | Default 1920 |
| resolution_height | INT | Default 1080 |
| fps | INT | Default 25 |
| rtsp_path | TEXT | **Cached working RTSP URL** (full URL, not just path) |
| http_path | TEXT | HTTP snapshot URL |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 8.3 dvr_streams

| Column | Type | Notes |
|---|---|---|
| company_id | TEXT | |
| dvr_id | TEXT | |
| channel_id | TEXT | |
| stream_url | TEXT | Active RTSP URL |
| created_at | TIMESTAMP | |

### 8.4 Database Adapter

`DatabaseAdapter` supports both SQLite and PostgreSQL. Detection is automatic via `DATABASE_URL` env var:
- If `DATABASE_URL` starts with `postgresql://` → PostgreSQL with connection pooling (5-100 connections)
- Otherwise → SQLite at `core/smartsafe_saas.db`

Placeholders: SQLite uses `?`, PostgreSQL uses `%s`. The adapter handles this transparently via `execute_query()`.

---

## 9. Frontend Architecture (cameras/page.tsx)

### 9.1 Stream Display

Each camera card contains:
```tsx
<img src={
  isCameraAiEnabled(camera)
    ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${camera.camera_id}?t=${refreshKey}`
    : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${camera.camera_id}/proxy-stream?t=${refreshKey}`
} />
```

The `?t=` cache-buster ensures fresh connections after refresh.

### 9.2 Pagination

- **6 cameras per page** (matches browser's ~6 connection limit per origin)
- Page stored in URL: `?page=1`, `?page=2` (1-based in URL, 0-based internally)
- `currentPage` derived from `useSearchParams()`
- Page changes use `window.location.href = ...` (full reload) to guarantee MJPEG connections are released
- Search/group filter changes reset page to 1 via `useEffect` with `prevFiltersRef` guard

### 9.3 Page Reload on Pagination (Why)

SPA navigation (`router.push`) does not reliably close MJPEG `<img>` HTTP connections. Chrome may keep TCP connections alive even after DOM removal. `window.location.href` assignment forces a full navigation → browser drops all connections → page 2 streams connect cleanly.

### 9.4 Suspense Wrapper

`useSearchParams()` requires a Suspense boundary in Next.js App Router:

```tsx
export default function CamerasPage() {
  return (
    <Suspense fallback={<div>Yükleniyor...</div>}>
      <CamerasContent />
    </Suspense>
  );
}
```

### 9.5 AI Toggle

Toggle button per camera calls:
```
POST /api/company/{cid}/start-detection   { camera_id }
POST /api/company/{cid}/stop-detection    { camera_id }
```

Then switches `<img src>` between `video-feed` (with AI overlay) and `proxy-stream` (raw).

### 9.6 Preview Modal

Full-screen modal opens an MJPEG stream for a single camera. Includes:
- AI toggle
- Zone designer (polygon ROI on video)
- Stream refresh button

### 9.7 DVR Management Modal

Lists registered DVRs with discover/delete actions. Discover triggers channel scanning on backend.

---

## 10. API Endpoint Reference

### DVR System Management

| Method | Path | Description |
|---|---|---|
| POST | `/api/company/{cid}/dvr/add` | Register a new DVR |
| GET | `/api/company/{cid}/dvr/list` | List all DVRs |
| GET | `/api/company/{cid}/dvr/{dvr_id}/info` | Get DVR details |
| DELETE | `/api/company/{cid}/dvr/{dvr_id}/delete` | Remove DVR + channels |
| GET | `/api/company/{cid}/dvr/{dvr_id}/test` | Connection test (ONVIF + RTSP) |
| GET | `/api/company/{cid}/dvr/{dvr_id}/status` | DVR status |

### Channel Operations

| Method | Path | Description |
|---|---|---|
| POST | `/api/company/{cid}/dvr/{dvr_id}/discover` | Scan for active channels |
| GET | `/api/company/{cid}/dvr/{dvr_id}/channels` | List channels (DB-first, fallback to max_channels) |
| GET | `/api/company/{cid}/dvr/{dvr_id}/channels/health` | Per-channel health ping with thumbnails |

### Stream Endpoints

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/company/{cid}/dvr/{dvr_id}/stream/{ch}` | Start stream, wait for active, return info |
| POST | `/api/company/{cid}/dvr/{dvr_id}/stream/{ch}/stop` | Stop stream |
| GET | `/api/company/{cid}/dvr/{dvr_id}/frame/{ch}` | Single JPEG frame (base64 JSON) |
| GET | `/api/company/{cid}/dvr/{dvr_id}/mjpeg/{ch}` | **MJPEG stream** (multipart/x-mixed-replace) |
| GET | `/api/company/{cid}/dvr/{dvr_id}/previews` | Grid preview thumbnails for N channels |

### Detection Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/company/{cid}/dvr/{dvr_id}/detection/start` | Start PPE detection session |
| POST | `/api/company/{cid}/dvr/{dvr_id}/detection/stop` | Stop detection session |
| GET | `/api/company/{cid}/dvr/{dvr_id}/detection/status` | Detection status |
| GET | `/api/company/{cid}/dvr/{dvr_id}/detection/results` | Detection results with violations |

### Media Gateway

| Method | Path | Description |
|---|---|---|
| GET | `/api/company/{cid}/dvr/{dvr_id}/gateway/config` | Gateway configuration |
| GET | `/api/company/{cid}/dvr/{dvr_id}/gateway/urls/{ch}` | Resolved gateway URLs |

### Report

| Method | Path | Description |
|---|---|---|
| GET | `/api/company/{cid}/dvr/{dvr_id}/report/pdf` | HTML report with print button |

### Utility

| Method | Path | Description |
|---|---|---|
| GET | `/api/dvr/brands` | List supported DVR brands + RTSP templates |

---

## 11. Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | _(none)_ | PostgreSQL connection string |
| `SQLITE_DB_PATH` | `core/smartsafe_saas.db` | SQLite file path |
| `DVR_PROBE_CONCURRENCY` | 4 | Max simultaneous RTSP probe connections |
| `DVR_START_URL_BUDGET` | 18 | Max URLs to try when starting a stream |
| `DVR_CHANNEL_PROBE_URL_BUDGET` | 6 | Max URLs to try per channel during discovery |
| `DVR_CHANNEL_PROBE_WORKERS` | 4 | ThreadPool workers for parallel channel probing |
| `DVR_PROBE_TTL_SUCCESS_S` | 600 | Seconds to cache successful probe results |
| `DVR_PROBE_TTL_FAIL_S` | 60 | Seconds to cache failed probe results |

---

## 12. Known Issues & Caveats

### 12.1 Browser MJPEG Connection Limit

Each MJPEG `<img>` consumes one HTTP connection. Chrome/Edge limit ~6 per origin. Pagination is set to 6 per page and uses full page reload to release connections.

### 12.2 ONVIF Not Universally Supported

Many budget DVRs (XM/Xiongmai) don't implement ONVIF or implement it incorrectly. The system gracefully falls back to RTSP brute-force probing with a 5-minute negative cache per IP.

### 12.3 RTSP URL Brute-Force Cost

First-time channel discovery can take 30-60 seconds (probing up to 18 URLs × N channels). Subsequent connections use cached URLs (<500ms). Cache persists across restarts via database.

### 12.4 Model Memory

PPE models (SH17 + Pose) are lazily initialized as singletons. This prevents RAM/GPU explosion with multi-channel DVRs but means the first detection per process is slower.

### 12.5 Detection Result on List

There is a known but unresolved log error: `'list' object has no attribute 'get'` in the detection/PPE compliance path. This occurs when `detections` is a list but code expects a dict. Non-fatal (wrapped in try/except), but compliance data may be incomplete for affected frames.

### 12.6 Auth Method

DVR HTTP API requests use digest-first, basic-fallback authentication (`DVRConfig.make_request()`). RTSP URLs embed credentials either in the authority (`user:pass@ip`) or in query string (`/user=X&password=Y`) depending on brand.

---

## 13. Thread Model

| Thread | Lifetime | Purpose |
|---|---|---|
| Main (Flask) | Process | Handles HTTP requests |
| `_stream_worker` (per stream) | Until stop or fatal error | Reads RTSP frames, buffers JPEG, runs detection |
| ThreadPoolExecutor (discover) | Per discover call | Parallel channel probing (max 8 workers) |
| ThreadPoolExecutor (detect_available_channels) | Per call | Parallel RTSP probe (max 4 workers) |
| MJPEG generator (per client) | Per HTTP connection | Reads from frame_buffer, yields JPEG parts |

All stream worker threads are **daemon threads** (die with process).

### Lock Discipline

A single `threading.Lock` (`self._lock`) protects `active_streams` and `frame_buffers` reads/writes in `DVRStreamHandler`. The `_probe_sem` semaphore (default 4) limits concurrent RTSP `VideoCapture` opens to prevent network/CPU storms.

---

## 14. DVR/Camera Registration Data Model

### DVRConfig (dataclass)

```
dvr_id, name, ip_address, port(80), username('admin'), password,
dvr_type('generic'), protocol('http'), api_path('/api'),
rtsp_port(554), max_channels(16), status('inactive'),
last_test_time, connection_retries(3), timeout(10), auth_method('auto')
```

### DVRChannel (dataclass)

```
channel_id, name, dvr_id, channel_number,
status('inactive'), resolution(1920,1080), fps(25),
rtsp_path, http_path, last_test_time
```

### stream_id Format

`{dvr_id}_ch{channel_number:02d}` — e.g., `mydvr_ch03`

### channel_id Format

Same as stream_id: `{dvr_id}_ch{channel_number:02d}`

---

## 15. Quick Reference: Adding a New DVR Brand

1. Add URL patterns to `dvr_url_patterns` dict in `DVRStreamHandler.__init__`
2. Add brand detection logic in `detect_dvr_brand()`
3. Add brand-specific URL generation in `generate_rtsp_urls()` (the brand-specific extension block at the bottom)
4. If the brand has a proprietary HTTP API for channel listing, add a method in `DVRManager._discover_dvr_channels()`
5. Test with `GET /api/company/{cid}/dvr/{dvr_id}/test`

---

## 16. Appendix: Stream ID → URL Resolution Flowchart

```
Browser requests: GET /api/company/X/dvr/Y/mjpeg/3
                          │
                          ▼
             dvr.py: mjpeg_dvr_stream()
                          │
               stream_id = "Y_ch03"
                          │
          ┌───────────────┴───────────────┐
          │ stream already active?         │
          │ (stream_handler.get_status)    │
          ├── YES ──► serve from buffer    │
          │                                │
          ├── NO ──► start_stream()        │
          │    │                           │
          │    ├─ ONVIF URI cache hit?     │
          │    │   YES → use ONVIF URI     │
          │    │   NO  → use seed URL      │
          │    │                           │
          │    └─ _stream_worker spawns    │
          │       │                        │
          │       ├─ Cache URL hit?        │
          │       │   YES → verify+use     │
          │       │   NO  → full discovery │
          │       │         (26+ URLs)     │
          │       │                        │
          │       └─ active → frame loop   │
          │          + PPE every 15 frames │
          └────────────────────────────────┘
                          │
                          ▼
             generate() yields MJPEG frames
             with detection overlay
```
