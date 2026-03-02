# SH17 Integration Report

## Current Status

### Architecture (Implemented)
- **SH17ModelManager**: Singleton pattern, lazy loading, sector-based model routing
- **PoseAwarePPEDetector**: YOLOv8-Pose keypoint detection with anatomical region mapping
- **API Endpoints**: 5 SH17-specific endpoints under `/api/company/<id>/sh17/`
- **9 Sector Support**: construction, manufacturing, chemical, food_beverage, warehouse_logistics, energy, petrochemical, marine_shipyard, aviation
- **Fallback Pipeline**: Auto-fallback from SH17 to YOLOv8n (COCO person) when needed

### Models (Production)
- **SH17 weights**: Pre-trained **YOLOv9-e** from [ahmadmughees/SH17dataset](https://github.com/ahmadmughees/SH17dataset) (mAP50 70.9%, 17 PPE classes).
- **Location**: `models/sh17_base/sh17_base_model/weights/best.pt` and copied to all `models/sh17_<sector>/sh17_<sector>_model/weights/best.pt`.
- **Fallback**: `data/models/yolov8n.pt` (COCO) for person detection when sector model is unavailable.
- **Pose**: `data/models/yolov8n-pose.pt` for PoseAwarePPEDetector.

### 17 Classes (SH17)
person, head, face, glasses, face_mask_medical, face_guard, ear, earmuffs, hands, gloves, foot, shoes, safety_vest, tools, helmet, medical_suit, safety_suit

## What Works Today
1. **17-class PPE detection** via YOLOv9-e (SH17) on real industrial imagery
2. Person detection and pose estimation (fallback / PoseAware)
3. API endpoints (session-validated, company-scoped)
4. Multi-tenant database and compliance framework
5. Camera integration and MJPEG streaming

## Replacing or Updating the Model
- To use another SH17-compatible weight: overwrite `models/sh17_base/.../weights/best.pt` and copy to each sector’s `weights/` folder, or re-run your deployment script.
- Pre-trained SH17 weights (YOLOv8/v9/v10): [SH17dataset releases](https://github.com/ahmadmughees/SH17dataset/releases).

## API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/company/<id>/sh17/detect` | POST | PPE detection with sector context |
| `/api/company/<id>/sh17/compliance` | POST | Compliance analysis against required PPE |
| `/api/company/<id>/sh17/sectors` | GET | List supported sectors |
| `/api/company/<id>/sh17/performance` | GET | Model performance metrics |
| `/api/company/<id>/sh17/health` | GET | System health check |
