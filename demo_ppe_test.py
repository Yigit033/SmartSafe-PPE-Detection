#!/usr/bin/env python3
"""
Demo PPE Test Script
Test demo images for PPE detection
"""

import cv2
import numpy as np
from ultralytics import YOLO
import sys
import os

# SH17 PPE Dataset class names
SH17_CLASSES = {
    0: 'person', 1: 'head', 2: 'face', 3: 'glasses',
    4: 'face_mask_medical', 5: 'face_guard', 6: 'ear', 7: 'earmuffs',
    8: 'hands', 9: 'gloves', 10: 'foot', 11: 'shoes',
    12: 'safety_vest', 13: 'tools', 14: 'helmet',
    15: 'medical_suit', 16: 'safety_suit'
}

def analyze_ppe_compliance(detections):
    """Analyze PPE compliance for each person"""
    # Separate people and PPE items
    people = [d for d in detections if d['class_name'] == 'person']
    
    # PPE items to check
    ppe_items = {
        'helmet': [d for d in detections if d['class_name'] == 'helmet'],
        'safety_vest': [d for d in detections if d['class_name'] == 'safety_vest'],
        'safety_suit': [d for d in detections if d['class_name'] == 'safety_suit'],
        'glasses': [d for d in detections if d['class_name'] == 'glasses'],
        'gloves': [d for d in detections if d['class_name'] == 'gloves'],
        'face_mask_medical': [d for d in detections if d['class_name'] == 'face_mask_medical']
    }
    
    compliance_results = []
    
    for person in people:
        person_bbox = person['bbox']
        
        # Check for each PPE item
        has_helmet = any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['helmet'])
        has_vest = any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['safety_vest']) or \
                   any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['safety_suit'])
        has_glasses = any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['glasses'])
        has_gloves = any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['gloves'])
        has_mask = any(boxes_overlap(person_bbox, ppe['bbox']) for ppe in ppe_items['face_mask_medical'])
        
        # Basic compliance: helmet and vest are mandatory
        is_compliant = has_helmet and has_vest
        
        compliance_results.append({
            'person': person,
            'has_helmet': has_helmet,
            'has_vest': has_vest,
            'has_glasses': has_glasses,
            'has_gloves': has_gloves,
            'has_mask': has_mask,
            'compliant': is_compliant
        })
    
    return compliance_results

def boxes_overlap(box1, box2, threshold=0.1):
    """Check if two boxes overlap (IoU)"""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i <= x1_i or y2_i <= y1_i:
        return False
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    iou = intersection / union if union > 0 else 0
    return iou > threshold

def test_demo_image(image_path):
    """Test demo image with PPE detection"""
    print(f"🎯 Testing: {image_path}")
    
    # Check if file exists
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return
    
    # Load PPE-specific YOLO model
    try:
        # Try SH17 PPE model first
        model = YOLO('data/models/yolo9e.pt')
        model.to('cpu')
        print("✅ PPE-specific model loaded (SH17)")
    except Exception as e:
        print(f"⚠️ PPE model not found, using general model: {e}")
        try:
            model = YOLO('yolov8n.pt')
            model.to('cpu')
            print("✅ General YOLO model loaded on CPU")
        except Exception as e2:
            print(f"❌ Model load error: {e2}")
            return
    
    # Load image
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Cannot load image: {image_path}")
        return
    
    # Run detection with error handling
    try:
        results = model(image, conf=0.15, verbose=False)  # Lower confidence, no verbose
        print("✅ Detection completed")
    except Exception as e:
        print(f"❌ Detection error: {e}")
        return
    
    # Process results
    detections = []
    for result in results:
        if result.boxes is not None:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                confidence = box.conf[0].cpu().numpy()
                class_id = int(box.cls[0].cpu().numpy())
                
                # Use SH17 classes if available, otherwise model names
                if 'yolo9e' in str(model.model_name) or len(model.names) > 80:
                    class_name = SH17_CLASSES.get(class_id, f"class_{class_id}")
                else:
                    class_name = model.names[class_id]
                
                detections.append({
                    'bbox': (int(x1), int(y1), int(x2), int(y2)),
                    'confidence': float(confidence),
                    'class_name': class_name
                })
    
    # Draw results
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        class_name = det['class_name']
        confidence = det['confidence']
        
        # Color based on class
        if class_name == 'person':
            color = (255, 255, 255)  # White
        elif 'helmet' in class_name or 'hard hat' in class_name:
            color = (0, 255, 0)      # Green - Safety gear
        elif 'vest' in class_name or 'suit' in class_name:
            color = (0, 255, 0)      # Green - Safety gear
        else:
            color = (0, 255, 255)    # Yellow - Other
        
        # Draw box
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = f"{class_name} {confidence:.2f}"
        cv2.putText(image, label, (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # Analyze PPE compliance
    compliance_analysis = analyze_ppe_compliance(detections)
    
    # Show results
    print(f"📊 Found {len(detections)} objects:")
    for det in detections:
        print(f"  - {det['class_name']}: {det['confidence']:.2f}")
    
    # Show PPE compliance
    print(f"\n🔍 PPE Compliance Analysis:")
    for i, analysis in enumerate(compliance_analysis):
        status = "✅ COMPLIANT" if analysis['compliant'] else "❌ VIOLATION"
        print(f"  Person {i+1}: {status}")
        print(f"    - Helmet: {'✅' if analysis['has_helmet'] else '❌'}")
        print(f"    - Safety Vest: {'✅' if analysis['has_vest'] else '❌'}")
        print(f"    - Glasses: {'✅' if analysis['has_glasses'] else '❌'}")
        print(f"    - Gloves: {'✅' if analysis['has_gloves'] else '❌'}")
    
    # Add compliance info to image
    y_offset = 30
    for i, analysis in enumerate(compliance_analysis):
        status_text = f"Person {i+1}: {'COMPLIANT' if analysis['compliant'] else 'VIOLATION'}"
        color = (0, 255, 0) if analysis['compliant'] else (0, 0, 255)
        cv2.putText(image, status_text, (10, y_offset), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        y_offset += 30
    
    # Display image
    cv2.imshow(f'PPE Detection Demo - {os.path.basename(image_path)}', image)
    print("🎥 Press any key to close window...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    # Save result
    output_path = f"result_{os.path.basename(image_path)}"
    cv2.imwrite(output_path, image)
    print(f"💾 Result saved: {output_path}")

def main():
    """Main function"""
    print("🏭 PPE DEMO TEST")
    print("=" * 40)
    
    # Test both demo images
    demo_images = [
        "people1.jpg",
        "people2.jpg",
        "people3.jpg"
    ]
    
    for image_path in demo_images:
        test_demo_image(image_path)
        print("-" * 40)

if __name__ == "__main__":
    main() 