#!/usr/bin/env python3
"""
Quick Performance Test & Camera Optimization
Simple test to identify performance bottlenecks
"""

import cv2
import time
import numpy as np
from ultralytics import YOLO
import torch
import threading
import os
import psutil

class QuickPerformanceTest:
    def __init__(self):
        self.frame_times = []
        self.detection_times = []
        self.model = None
        
    def test_system_info(self):
        """Test basic system information"""
        print("🖥️  SYSTEM INFORMATION:")
        print(f"   CPU Cores: {os.cpu_count()}")
        print(f"   RAM Usage: {psutil.virtual_memory().percent:.1f}%")
        print(f"   CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   GPU: {torch.cuda.get_device_name(0)}")
            print(f"   GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        print()
        
    def test_camera_speeds(self):
        """Test different camera resolutions and speeds"""
        print("🎥 CAMERA PERFORMANCE TEST:")
        
        # Test resolutions
        test_resolutions = [
            (320, 240, "QVGA"),
            (640, 480, "VGA"),
            (1280, 720, "HD"),
            (1920, 1080, "Full HD")
        ]
        
        best_fps = 0
        best_resolution = None
        
        for width, height, name in test_resolutions:
            print(f"   Testing {name} ({width}x{height})...")
            
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("   ❌ Camera not found!")
                continue
                
            # Set camera properties
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer lag
            
            # Test for 2 seconds
            start_time = time.time()
            frame_count = 0
            
            while time.time() - start_time < 2.0:
                ret, frame = cap.read()
                if ret:
                    frame_count += 1
                else:
                    break
                    
            cap.release()
            
            fps = frame_count / 2.0
            print(f"      FPS: {fps:.1f}")
            
            if fps > best_fps:
                best_fps = fps
                best_resolution = (width, height, name)
        
        print(f"   🏆 Best Resolution: {best_resolution[2]} - {best_fps:.1f} FPS")
        print()
        return best_resolution
        
    def test_model_speeds(self):
        """Test model inference speeds"""
        print("🧠 MODEL PERFORMANCE TEST:")
        
        # Test different models
        models_to_test = [
            ("data/models/yolo9e.pt", "YOLOv9-e (SH17)"),
            ("yolov8n.pt", "YOLOv8n (lightweight)"),
            ("yolov8s.pt", "YOLOv8s (medium)")
        ]
        
        best_model = None
        best_fps = 0
        
        # Test image
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        for model_path, model_name in models_to_test:
            print(f"   Testing {model_name}...")
            
            try:
                model = YOLO(model_path)
                model.to('cpu')  # Force CPU mode
                
                # Warm-up
                for _ in range(3):
                    _ = model(test_image, conf=0.3, verbose=False)
                
                # Test inference times
                inference_times = []
                for _ in range(10):
                    start_time = time.time()
                    _ = model(test_image, conf=0.3, verbose=False)
                    inference_times.append(time.time() - start_time)
                
                avg_inference_time = sum(inference_times) / len(inference_times)
                max_fps = 1.0 / avg_inference_time
                
                print(f"      Inference: {avg_inference_time*1000:.1f}ms")
                print(f"      Max FPS: {max_fps:.1f}")
                
                if max_fps > best_fps:
                    best_fps = max_fps
                    best_model = (model_path, model_name)
                    
            except Exception as e:
                print(f"      ❌ Failed to load: {str(e)}")
                continue
        
        print(f"   🏆 Best Model: {best_model[1]} - {best_fps:.1f} FPS")
        print()
        return best_model
        
    def test_live_performance(self, resolution=(640, 480), model_path="data/models/yolo9e.pt"):
        """Test live performance with optimized settings"""
        print("🎯 LIVE PERFORMANCE TEST:")
        print(f"   Resolution: {resolution[0]}x{resolution[1]}")
        print(f"   Model: {model_path}")
        print()
        
        # Load model
        try:
            model = YOLO(model_path)
            model.to('cpu')
            print("   ✅ Model loaded successfully")
        except Exception as e:
            print(f"   ❌ Model load failed: {e}")
            return
        
        # Setup camera with optimized settings
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("   ❌ Camera not found!")
            return
            
        # Optimize camera settings
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce lag
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))  # Use MJPG compression
        
        print("   🎥 Camera setup complete")
        print("   Press 'q' to quit, 'r' to show results")
        
        frame_count = 0
        start_time = time.time()
        detection_count = 0
        
        while True:
            loop_start = time.time()
            
            ret, frame = cap.read()
            if not ret:
                print("   ❌ Failed to read frame")
                break
            
            frame_count += 1
            
            # Run detection every 3rd frame for better performance
            if frame_count % 3 == 0:
                detection_start = time.time()
                results = model(frame, conf=0.3, verbose=False)
                detection_time = time.time() - detection_start
                self.detection_times.append(detection_time)
                
                # Count detections
                for result in results:
                    if result.boxes is not None:
                        detection_count += len(result.boxes)
                
                # Draw detection info
                cv2.putText(frame, f"Detections: {detection_count}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Det Time: {detection_time*1000:.1f}ms", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            
            # Calculate FPS
            loop_time = time.time() - loop_start
            self.frame_times.append(loop_time)
            
            if len(self.frame_times) > 30:
                self.frame_times.pop(0)
                
            current_fps = 1.0 / (sum(self.frame_times) / len(self.frame_times))
            
            # Draw FPS info
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (10, 110), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            
            # Show frame
            cv2.imshow('Performance Test', frame)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                self.show_results()
        
        cap.release()
        cv2.destroyAllWindows()
        
        # Final results
        total_time = time.time() - start_time
        avg_fps = frame_count / total_time
        
        print(f"\n   📊 FINAL RESULTS:")
        print(f"   Total Frames: {frame_count}")
        print(f"   Total Time: {total_time:.1f}s")
        print(f"   Average FPS: {avg_fps:.1f}")
        print(f"   Total Detections: {detection_count}")
        
        if self.detection_times:
            avg_detection_time = sum(self.detection_times) / len(self.detection_times)
            print(f"   Avg Detection Time: {avg_detection_time*1000:.1f}ms")
        
        # Performance assessment
        print(f"\n   🎯 PERFORMANCE ASSESSMENT:")
        if avg_fps >= 25:
            print("   ✅ Excellent performance (25+ FPS)")
        elif avg_fps >= 15:
            print("   ⚠️  Good performance (15-25 FPS)")
        elif avg_fps >= 10:
            print("   ⚠️  Moderate performance (10-15 FPS)")
        else:
            print("   ❌ Poor performance (<10 FPS)")
            
        self.show_recommendations(avg_fps)
        
    def show_results(self):
        """Show current performance results"""
        if self.frame_times:
            current_fps = 1.0 / (sum(self.frame_times) / len(self.frame_times))
            print(f"\n   Current FPS: {current_fps:.1f}")
            
        if self.detection_times:
            avg_detection_time = sum(self.detection_times) / len(self.detection_times)
            print(f"   Avg Detection Time: {avg_detection_time*1000:.1f}ms")
            
    def show_recommendations(self, fps):
        """Show optimization recommendations"""
        print(f"\n   💡 OPTIMIZATION RECOMMENDATIONS:")
        
        if fps < 15:
            print("   🔧 CRITICAL OPTIMIZATIONS NEEDED:")
            print("   - Use lower resolution (320x240 or 640x480)")
            print("   - Switch to lighter model (YOLOv8n)")
            print("   - Enable GPU acceleration if available")
            print("   - Reduce detection frequency (every 5th frame)")
            print("   - Close other applications")
            
        elif fps < 25:
            print("   ⚙️  MINOR OPTIMIZATIONS:")
            print("   - Consider lower resolution")
            print("   - Optimize camera settings")
            print("   - Run detection every 2nd frame")
            
        else:
            print("   ✅ Performance is good!")
            print("   - Current settings are optimal")
            print("   - Consider enabling more features")
            
        print("\n   🎥 CAMERA OPTIMIZATION TIPS:")
        print("   - Use MJPG codec for better compression")
        print("   - Set buffer size to 1 to reduce lag")
        print("   - Use lower resolution for better FPS")
        print("   - Check camera driver updates")
        
        print("\n   🧠 MODEL OPTIMIZATION TIPS:")
        print("   - Use CPU-optimized models")
        print("   - Reduce confidence threshold")
        print("   - Consider model quantization")
        print("   - Use batch processing for multiple frames")

def main():
    """Run performance tests"""
    print("🚀 QUICK PERFORMANCE ANALYSIS")
    print("=" * 50)
    
    tester = QuickPerformanceTest()
    
    # System info
    tester.test_system_info()
    
    # Camera test
    best_resolution = tester.test_camera_speeds()
    
    # Model test
    best_model = tester.test_model_speeds()
    
    # Live test
    if best_resolution and best_model:
        print(f"🎯 Running optimized live test...")
        tester.test_live_performance(
            resolution=best_resolution[:2],
            model_path=best_model[0]
        )
    else:
        print("⚠️  Using default settings for live test...")
        tester.test_live_performance()

if __name__ == "__main__":
    main() 