"""Final diagnostic: trace SH17 + Food detections vs person anatomical regions IoU."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import logging
logging.disable(logging.CRITICAL)
import cv2

from app import SmartSafeSaaSAPI
from detection.pose_aware_ppe_detector import get_pose_aware_detector, PPE_CONFIG

api = SmartSafeSaaSAPI()
api.ensure_database_initialized()
pose_detector = get_pose_aware_detector(ppe_detector=api.sh17_manager)

cap = cv2.VideoCapture(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tests', 'Videos', 'food.mp4'))
for _ in range(60):
    cap.read()
ret, frame = cap.read()
cap.release()
small = cv2.resize(frame, (int(frame.shape[1]*0.5), int(frame.shape[0]*0.5)))

# Get all detections
all_dets = api.sh17_manager.detect_ppe(small, 'food', 0.30)

# Get pose data
pose_results = pose_detector.pose_model(small, conf=0.3, verbose=False)
persons = pose_detector._extract_pose_data(pose_results, small.shape)

# Group PPE by type
ppe_by_type = {}
for det in all_dets:
    cn = str(det.get('class_name', '')).lower()
    if cn == 'person' or cn.startswith('no-'):
        continue
    for ptype, cfg in PPE_CONFIG.items():
        if any(cls in cn for cls in cfg['model_classes']):
            ppe_by_type.setdefault(ptype, []).append(det)
            break

print("=== PPE BY TYPE ===")
for ptype, items in ppe_by_type.items():
    print("  %s: %d items" % (ptype, len(items)))
    for item in items:
        bb = [int(x) for x in item.get('bbox', [])]
        mt = item.get('model_type', 'SH17')
        print("    [%s] %s conf=%.2f bbox=%s" % (mt, item.get('class_name'), item.get('confidence', 0), bb))

print("\n=== PERSON-LEVEL IoU ANALYSIS ===")
for pi, person in enumerate(persons):
    regions = person['anatomical_regions']
    pbbox = person['bbox']
    print("\nPerson %d: bbox=%s" % (pi, [int(x) for x in pbbox]))
    
    for ptype, items in ppe_by_type.items():
        cfg = PPE_CONFIG[ptype]
        region_name = cfg['region']
        region_bbox = regions.get(region_name) or regions.get('full_body') or pbbox
        
        print("  [%s] region=%s -> %s" % (ptype, region_name, [int(x) for x in region_bbox] if region_bbox else 'NONE'))
        
        best_iou_r = 0
        best_iou_p = 0
        best_item = None
        for item in items:
            dbb = item.get('bbox', [])
            if len(dbb) != 4:
                continue
            iou_r = pose_detector._calculate_iou(dbb, region_bbox)
            iou_p = pose_detector._calculate_iou(dbb, pbbox)
            if iou_r > best_iou_r:
                best_iou_r = iou_r
                best_iou_p = iou_p
                best_item = item
            print("    %s IoU_region=%.4f IoU_person=%.4f" % (item.get('class_name'), iou_r, iou_p))
        
        if best_item:
            iou_thresh = {'helmet':0.03,'haircap':0.03,'safety_vest':0.05,'safety_shoes':0.02,'gloves':0.05,'safety_glasses':0.05,'face_mask':0.05,'safety_suit':0.05}.get(ptype, 0.05)
            piou_thresh = {'helmet':0.08,'haircap':0.08,'safety_vest':0.1,'safety_shoes':0.05,'gloves':0.1,'safety_glasses':0.1,'face_mask':0.1,'safety_suit':0.1}.get(ptype, 0.1)
            match = best_iou_r > iou_thresh and best_iou_p > piou_thresh
            print("    BEST: IoU_r=%.4f(>%.3f?) IoU_p=%.4f(>%.3f?) -> %s" % (best_iou_r, iou_thresh, best_iou_p, piou_thresh, "MATCH" if match else "FAIL"))
