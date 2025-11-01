#!/usr/bin/env python3
"""
CUDA Fix for PPE Detection
Attempts to resolve CUDA backend issues
"""

import torch
import torchvision
import cv2
import numpy as np
from ultralytics import YOLO
import logging
import os
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_cuda_setup():
    """Check CUDA setup and capabilities"""
    logger.info("🔍 CUDA System Check:")
    logger.info(f"   PyTorch version: {torch.__version__}")
    logger.info(f"   TorchVision version: {torchvision.__version__}")
    logger.info(f"   CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        logger.info(f"   CUDA version: {torch.version.cuda}")
        logger.info(f"   GPU count: {torch.cuda.device_count()}")
        logger.info(f"   GPU name: {torch.cuda.get_device_name(0)}")
        logger.info(f"   GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        
        # Test basic CUDA operations
        try:
            x = torch.rand(5, 3).cuda()
            y = torch.rand(3, 5).cuda()
            z = torch.mm(x, y)
            logger.info("   ✅ Basic CUDA operations work")
            
            # Test torchvision operations
            boxes = torch.tensor([[0, 0, 10, 10], [5, 5, 15, 15]], dtype=torch.float32).cuda()
            scores = torch.tensor([0.9, 0.8], dtype=torch.float32).cuda()
            
            # This is where the error usually occurs
            keep = torchvision.ops.nms(boxes, scores, 0.5)
            logger.info("   ✅ TorchVision NMS works on CUDA")
            return True
            
        except Exception as e:
            logger.error(f"   ❌ CUDA operation failed: {e}")
            return False
    else:
        logger.warning("   ⚠️ CUDA not available")
        return False

def fix_cuda_backend():
    """Attempt to fix CUDA backend issues"""
    logger.info("🔧 Attempting CUDA fixes...")
    
    # Method 1: Force CPU-only NMS
    try:
        import torchvision.ops
        original_nms = torchvision.ops.nms
        
        def cpu_nms(boxes, scores, iou_threshold):
            # Force CPU computation
            return original_nms(boxes.cpu(), scores.cpu(), iou_threshold).cuda()
        
        torchvision.ops.nms = cpu_nms
        logger.info("   ✅ Applied CPU-fallback NMS patch")
        return True
        
    except Exception as e:
        logger.error(f"   ❌ NMS patch failed: {e}")
        return False

def test_optimized_cuda_detection():
    """Test detection with CUDA optimizations"""
    logger.info("🧪 Testing optimized CUDA detection...")
    
    # Load model
    try:
        model = YOLO("data/models/yolo9e.pt")
        
        # Try CUDA first
        if torch.cuda.is_available():
            logger.info("   🎯 Testing CUDA mode...")
            model.to('cuda')
            device = 'cuda'
        else:
            logger.info("   🎯 Using CPU mode...")
            model.to('cpu')
            device = 'cpu'
        
        # Test with dummy image
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Warm-up
        logger.info("   🔥 Warming up model...")
        for _ in range(3):
            try:
                _ = model(test_image, conf=0.5, verbose=False)
            except Exception as e:
                if "nms" in str(e).lower():
                    logger.warning("   ⚠️ NMS error detected, switching to CPU...")
                    model.to('cpu')
                    device = 'cpu'
                    _ = model(test_image, conf=0.5, verbose=False)
                else:
                    raise e
        
        # Performance test
        import time
        inference_times = []
        
        for i in range(10):
            start_time = time.time()
            results = model(test_image, conf=0.5, verbose=False)
            inference_time = time.time() - start_time
            inference_times.append(inference_time)
            
            if i % 3 == 0:
                logger.info(f"   Test {i+1}/10: {inference_time*1000:.1f}ms")
        
        avg_time = sum(inference_times) / len(inference_times)
        max_fps = 1.0 / avg_time
        
        logger.info(f"   📊 Results ({device} mode):")
        logger.info(f"      Average inference: {avg_time*1000:.1f}ms")
        logger.info(f"      Max FPS: {max_fps:.1f}")
        
        return True, device, max_fps
        
    except Exception as e:
        logger.error(f"   ❌ Detection test failed: {e}")
        return False, 'none', 0

def run_cuda_optimized_live():
    """Run live detection with CUDA optimizations"""
    logger.info("🎥 Starting CUDA-optimized live detection...")
    
    # Load model with best available device
    model = YOLO("data/models/yolo9e.pt")
    
    device = 'cpu'
    if torch.cuda.is_available():
        try:
            # Test CUDA compatibility
            test_img = np.random.randint(0, 255, (320, 320, 3), dtype=np.uint8)
            model.to('cuda')
            _ = model(test_img, conf=0.5, verbose=False)
            device = 'cuda'
            logger.info("   ✅ CUDA mode enabled")
        except:
            model.to('cpu')
            device = 'cpu'
            logger.info("   ⚠️ CUDA failed, using CPU")
    
    # Setup camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    logger.info(f"   🎯 Running on {device.upper()}")
    logger.info("   Press 'q' to quit")
    
    frame_count = 0
    inference_times = []
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Process every 3rd frame for better performance
        if frame_count % 3 == 0:
            start_time = time.time()
            
            # Resize for faster inference
            frame_small = cv2.resize(frame, (320, 320))
            results = model(frame_small, conf=0.4, verbose=False)
            
            inference_time = time.time() - start_time
            inference_times.append(inference_time)
            
            # Keep only last 30 measurements
            if len(inference_times) > 30:
                inference_times.pop(0)
            
            # Draw results
            detections = 0
            for result in results:
                if result.boxes is not None:
                    detections += len(result.boxes)
            
            # Performance info
            if inference_times:
                avg_inference = sum(inference_times) / len(inference_times)
                fps = 1.0 / avg_inference if avg_inference > 0 else 0
                
                cv2.putText(frame, f"Device: {device.upper()}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"Inference: {avg_inference*1000:.1f}ms", (10, 110), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                cv2.putText(frame, f"Detections: {detections}", (10, 150), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        
        cv2.imshow('CUDA Optimized PPE Detection', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    if inference_times:
        final_avg = sum(inference_times) / len(inference_times)
        final_fps = 1.0 / final_avg
        logger.info(f"   📊 Final performance ({device}):")
        logger.info(f"      Average inference: {final_avg*1000:.1f}ms")
        logger.info(f"      Average FPS: {final_fps:.1f}")

def main():
    """Main CUDA optimization function"""
    print("🚀 CUDA OPTIMIZATION FOR PPE DETECTION")
    print("=" * 50)
    
    # Check CUDA setup
    cuda_works = check_cuda_setup()
    
    if not cuda_works:
        print("\n🔧 Attempting CUDA fixes...")
        fix_cuda_backend()
    
    # Test detection performance
    print("\n🧪 Testing detection performance...")
    success, device, fps = test_optimized_cuda_detection()
    
    if success:
        print(f"\n✅ Detection test successful!")
        print(f"   Device: {device}")
        print(f"   Max FPS: {fps:.1f}")
        
        if fps > 5:
            response = input("\n🎥 Run live detection? (y/n): ").lower().strip()
            if response == 'y':
                run_cuda_optimized_live()
        else:
            print("   ⚠️ Performance too low for live detection")
    else:
        print("\n❌ Detection test failed")

if __name__ == "__main__":
    main() 