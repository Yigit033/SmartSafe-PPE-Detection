#!/usr/bin/env python3
"""
SmartSafe AI - Performance Optimizer
Enterprise-grade performance optimization for video streaming and detection
"""

import cv2
import numpy as np
import threading
import queue
import time
import psutil
import gc
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing as mp
from collections import deque

@dataclass
class PerformanceMetrics:
    """Performance metrics tracking"""
    fps: float = 0.0
    processing_time: float = 0.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    gpu_usage: float = 0.0
    queue_size: int = 0
    dropped_frames: int = 0
    total_frames: int = 0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class PerformanceOptimizer:
    """Enterprise-grade performance optimization system"""
    
    def __init__(self, max_workers: int = None):
        self.max_workers = max_workers or min(mp.cpu_count(), 8)
        
        # Performance tracking
        self.metrics_history: Dict[str, deque] = {}
        self.performance_thresholds = {
            'min_fps': 15.0,
            'max_processing_time': 100.0,  # ms
            'max_memory_usage': 80.0,      # %
            'max_cpu_usage': 85.0,         # %
            'max_queue_size': 10
        }
        
        # Optimization settings
        self.optimization_enabled = True
        self.adaptive_quality = True
        self.frame_skipping = True
        self.batch_processing = True
        
        # Threading
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self.processing_queues: Dict[str, queue.Queue] = {}
        self.result_queues: Dict[str, queue.Queue] = {}
        
        # Frame management
        self.frame_buffers: Dict[str, deque] = {}
        self.frame_cache: Dict[str, np.ndarray] = {}
        
        # Performance monitoring
        self.monitor_thread = None
        self.monitoring_active = False
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("🚀 Performance Optimizer initialized")
        
        # Start monitoring
        self.start_monitoring()
    
    def start_monitoring(self):
        """Start performance monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitor_thread = threading.Thread(target=self._monitor_performance, daemon=True)
            self.monitor_thread.start()
            self.logger.info("📊 Performance monitoring started")
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("📊 Performance monitoring stopped")
    
    def _monitor_performance(self):
        """Monitor system performance continuously"""
        while self.monitoring_active:
            try:
                # Collect system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent
                
                # GPU metrics (if available)
                gpu_percent = self._get_gpu_usage()
                
                # Update metrics for each camera
                for camera_id in self.processing_queues.keys():
                    metrics = PerformanceMetrics(
                        cpu_usage=cpu_percent,
                        memory_usage=memory_percent,
                        gpu_usage=gpu_percent,
                        queue_size=self.processing_queues[camera_id].qsize()
                    )
                    
                    self._update_metrics(camera_id, metrics)
                    
                    # Check for performance issues
                    self._check_performance_thresholds(camera_id, metrics)
                
                time.sleep(5)  # Monitor every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Performance monitoring error: {e}")
                time.sleep(10)
    
    def _get_gpu_usage(self) -> float:
        """Get GPU usage percentage"""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return info.gpu
        except:
            return 0.0
    
    def _update_metrics(self, camera_id: str, metrics: PerformanceMetrics):
        """Update performance metrics for camera"""
        if camera_id not in self.metrics_history:
            self.metrics_history[camera_id] = deque(maxlen=100)  # Keep last 100 metrics
        
        self.metrics_history[camera_id].append(metrics)
    
    def _check_performance_thresholds(self, camera_id: str, metrics: PerformanceMetrics):
        """Check if performance thresholds are exceeded"""
        issues = []
        
        if metrics.fps < self.performance_thresholds['min_fps']:
            issues.append(f"Low FPS: {metrics.fps:.1f}")
        
        if metrics.processing_time > self.performance_thresholds['max_processing_time']:
            issues.append(f"High processing time: {metrics.processing_time:.1f}ms")
        
        if metrics.memory_usage > self.performance_thresholds['max_memory_usage']:
            issues.append(f"High memory usage: {metrics.memory_usage:.1f}%")
        
        if metrics.cpu_usage > self.performance_thresholds['max_cpu_usage']:
            issues.append(f"High CPU usage: {metrics.cpu_usage:.1f}%")
        
        if metrics.queue_size > self.performance_thresholds['max_queue_size']:
            issues.append(f"Large queue: {metrics.queue_size}")
        
        if issues and self.optimization_enabled:
            self.logger.warning(f"⚠️ Performance issues for {camera_id}: {', '.join(issues)}")
            self._apply_optimizations(camera_id, issues)
    
    def _apply_optimizations(self, camera_id: str, issues: List[str]):
        """Apply performance optimizations"""
        try:
            # Reduce quality if FPS is low
            if any("Low FPS" in issue for issue in issues):
                self._reduce_quality(camera_id)
            
            # Skip frames if processing is slow
            if any("High processing time" in issue for issue in issues):
                self._enable_frame_skipping(camera_id)
            
            # Clear cache if memory is high
            if any("High memory usage" in issue for issue in issues):
                self._clear_memory_cache(camera_id)
            
            # Reduce queue size if too large
            if any("Large queue" in issue for issue in issues):
                self._reduce_queue_size(camera_id)
            
            self.logger.info(f"🔧 Applied optimizations for {camera_id}")
            
        except Exception as e:
            self.logger.error(f"Optimization failed for {camera_id}: {e}")
    
    def _reduce_quality(self, camera_id: str):
        """Reduce video quality to improve FPS"""
        if camera_id in self.frame_buffers:
            # This would be implemented with the camera manager
            self.logger.info(f"📉 Reducing quality for {camera_id}")
    
    def _enable_frame_skipping(self, camera_id: str):
        """Enable frame skipping to reduce processing load"""
        if camera_id in self.processing_queues:
            # Skip every other frame
            queue_obj = self.processing_queues[camera_id]
            if queue_obj.qsize() > 2:
                try:
                    queue_obj.get_nowait()  # Skip one frame
                except queue.Empty:
                    pass
            self.logger.info(f"⏭️ Enabled frame skipping for {camera_id}")
    
    def _clear_memory_cache(self, camera_id: str):
        """Clear memory cache to free up RAM"""
        if camera_id in self.frame_cache:
            del self.frame_cache[camera_id]
        
        if camera_id in self.frame_buffers:
            self.frame_buffers[camera_id].clear()
        
        # Force garbage collection
        gc.collect()
        
        self.logger.info(f"🧹 Cleared memory cache for {camera_id}")
    
    def _reduce_queue_size(self, camera_id: str):
        """Reduce queue size by dropping old frames"""
        if camera_id in self.processing_queues:
            queue_obj = self.processing_queues[camera_id]
            while queue_obj.qsize() > 5:
                try:
                    queue_obj.get_nowait()
                except queue.Empty:
                    break
            self.logger.info(f"📦 Reduced queue size for {camera_id}")
    
    def optimize_frame(self, frame: np.ndarray, camera_id: str) -> np.ndarray:
        """Optimize frame for processing"""
        if not self.optimization_enabled:
            return frame
        
        try:
            start_time = time.time()
            
            # Get current metrics
            current_metrics = self.get_current_metrics(camera_id)
            
            # Apply optimizations based on performance
            optimized_frame = frame.copy()
            
            # Resize if performance is poor
            if current_metrics and current_metrics.fps < 20:
                height, width = frame.shape[:2]
                if width > 640:
                    scale_factor = 640 / width
                    new_width = int(width * scale_factor)
                    new_height = int(height * scale_factor)
                    optimized_frame = cv2.resize(frame, (new_width, new_height))
            
            # Convert color space for faster processing
            if len(optimized_frame.shape) == 3:
                # Use BGR for OpenCV operations
                pass
            
            # Cache optimized frame
            self.frame_cache[camera_id] = optimized_frame
            
            # Update processing time
            processing_time = (time.time() - start_time) * 1000
            if camera_id in self.metrics_history and self.metrics_history[camera_id]:
                self.metrics_history[camera_id][-1].processing_time = processing_time
            
            return optimized_frame
            
        except Exception as e:
            self.logger.error(f"Frame optimization failed: {e}")
            return frame
    
    def process_frame_batch(self, frames: List[np.ndarray], camera_id: str) -> List[Dict[str, Any]]:
        """Process multiple frames in batch for better performance"""
        if not self.batch_processing or len(frames) == 1:
            # Process single frame
            return [self.process_single_frame(frames[0], camera_id)]
        
        try:
            start_time = time.time()
            results = []
            
            # Batch processing with threading
            with ThreadPoolExecutor(max_workers=min(len(frames), 4)) as executor:
                futures = []
                
                for i, frame in enumerate(frames):
                    future = executor.submit(self.process_single_frame, frame, f"{camera_id}_{i}")
                    futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=5)
                        results.append(result)
                    except Exception as e:
                        self.logger.error(f"Batch processing error: {e}")
                        results.append({"error": str(e)})
            
            # Update metrics
            processing_time = (time.time() - start_time) * 1000
            self.logger.debug(f"Batch processed {len(frames)} frames in {processing_time:.1f}ms")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")
            return [{"error": str(e)} for _ in frames]
    
    def process_single_frame(self, frame: np.ndarray, camera_id: str) -> Dict[str, Any]:
        """Process single frame with optimizations"""
        try:
            start_time = time.time()
            
            # Optimize frame
            optimized_frame = self.optimize_frame(frame, camera_id)
            
            # Simulate detection processing
            # In real implementation, this would call the detection model
            time.sleep(0.01)  # Simulate processing time
            
            # Create result
            result = {
                "camera_id": camera_id,
                "timestamp": datetime.now().isoformat(),
                "frame_shape": optimized_frame.shape,
                "processing_time": (time.time() - start_time) * 1000,
                "detections": []  # Would contain actual detections
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Frame processing failed: {e}")
            return {"error": str(e)}
    
    def create_processing_pipeline(self, camera_id: str) -> Tuple[queue.Queue, queue.Queue]:
        """Create optimized processing pipeline for camera"""
        # Input queue for frames
        input_queue = queue.Queue(maxsize=10)
        
        # Output queue for results
        output_queue = queue.Queue(maxsize=20)
        
        # Store queues
        self.processing_queues[camera_id] = input_queue
        self.result_queues[camera_id] = output_queue
        
        # Create frame buffer
        self.frame_buffers[camera_id] = deque(maxlen=5)
        
        # Start processing thread
        processing_thread = threading.Thread(
            target=self._processing_worker,
            args=(camera_id, input_queue, output_queue),
            daemon=True
        )
        processing_thread.start()
        
        self.logger.info(f"🔧 Created processing pipeline for {camera_id}")
        
        return input_queue, output_queue
    
    def _processing_worker(self, camera_id: str, input_queue: queue.Queue, output_queue: queue.Queue):
        """Worker thread for processing frames"""
        self.logger.info(f"🔄 Started processing worker for {camera_id}")
        
        frame_count = 0
        last_fps_time = time.time()
        
        while True:
            try:
                # Get frame from queue with timeout
                frame_data = input_queue.get(timeout=1)
                
                if frame_data is None:  # Shutdown signal
                    break
                
                frame, timestamp = frame_data
                
                # Process frame
                result = self.process_single_frame(frame, camera_id)
                
                # Add to output queue
                try:
                    output_queue.put_nowait((result, timestamp))
                except queue.Full:
                    # Drop oldest result if queue is full
                    try:
                        output_queue.get_nowait()
                        output_queue.put_nowait((result, timestamp))
                    except queue.Empty:
                        pass
                
                # Update FPS
                frame_count += 1
                current_time = time.time()
                if current_time - last_fps_time >= 1.0:
                    fps = frame_count / (current_time - last_fps_time)
                    
                    # Update metrics
                    if camera_id in self.metrics_history and self.metrics_history[camera_id]:
                        self.metrics_history[camera_id][-1].fps = fps
                    
                    frame_count = 0
                    last_fps_time = current_time
                
                # Mark task as done
                input_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing worker error for {camera_id}: {e}")
                time.sleep(0.1)
        
        self.logger.info(f"🔄 Processing worker stopped for {camera_id}")
    
    def add_frame(self, camera_id: str, frame: np.ndarray) -> bool:
        """Add frame to processing pipeline"""
        if camera_id not in self.processing_queues:
            self.create_processing_pipeline(camera_id)
        
        try:
            timestamp = time.time()
            
            # Add to queue (non-blocking)
            self.processing_queues[camera_id].put_nowait((frame, timestamp))
            
            # Add to frame buffer
            if camera_id in self.frame_buffers:
                self.frame_buffers[camera_id].append(frame)
            
            return True
            
        except queue.Full:
            # Queue is full, drop frame
            self.logger.debug(f"Dropped frame for {camera_id} - queue full")
            
            # Update dropped frames count
            if camera_id in self.metrics_history and self.metrics_history[camera_id]:
                self.metrics_history[camera_id][-1].dropped_frames += 1
            
            return False
        except Exception as e:
            self.logger.error(f"Failed to add frame for {camera_id}: {e}")
            return False
    
    def get_results(self, camera_id: str) -> List[Tuple[Dict[str, Any], float]]:
        """Get processing results for camera"""
        if camera_id not in self.result_queues:
            return []
        
        results = []
        result_queue = self.result_queues[camera_id]
        
        # Get all available results
        while True:
            try:
                result, timestamp = result_queue.get_nowait()
                results.append((result, timestamp))
            except queue.Empty:
                break
        
        return results
    
    def get_current_metrics(self, camera_id: str) -> Optional[PerformanceMetrics]:
        """Get current performance metrics for camera"""
        if camera_id in self.metrics_history and self.metrics_history[camera_id]:
            return self.metrics_history[camera_id][-1]
        return None
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        summary = {
            "total_cameras": len(self.processing_queues),
            "optimization_enabled": self.optimization_enabled,
            "adaptive_quality": self.adaptive_quality,
            "frame_skipping": self.frame_skipping,
            "batch_processing": self.batch_processing,
            "cameras": {}
        }
        
        for camera_id in self.metrics_history:
            if self.metrics_history[camera_id]:
                latest_metrics = self.metrics_history[camera_id][-1]
                
                # Calculate averages
                recent_metrics = list(self.metrics_history[camera_id])[-10:]  # Last 10 metrics
                avg_fps = sum(m.fps for m in recent_metrics) / len(recent_metrics)
                avg_processing_time = sum(m.processing_time for m in recent_metrics) / len(recent_metrics)
                
                summary["cameras"][camera_id] = {
                    "current_fps": latest_metrics.fps,
                    "average_fps": avg_fps,
                    "current_processing_time": latest_metrics.processing_time,
                    "average_processing_time": avg_processing_time,
                    "memory_usage": latest_metrics.memory_usage,
                    "cpu_usage": latest_metrics.cpu_usage,
                    "gpu_usage": latest_metrics.gpu_usage,
                    "queue_size": latest_metrics.queue_size,
                    "dropped_frames": latest_metrics.dropped_frames,
                    "total_frames": latest_metrics.total_frames
                }
        
        return summary
    
    def cleanup_camera(self, camera_id: str):
        """Clean up resources for camera"""
        try:
            # Stop processing
            if camera_id in self.processing_queues:
                self.processing_queues[camera_id].put(None)  # Shutdown signal
                del self.processing_queues[camera_id]
            
            if camera_id in self.result_queues:
                del self.result_queues[camera_id]
            
            if camera_id in self.frame_buffers:
                del self.frame_buffers[camera_id]
            
            if camera_id in self.frame_cache:
                del self.frame_cache[camera_id]
            
            if camera_id in self.metrics_history:
                del self.metrics_history[camera_id]
            
            self.logger.info(f"🧹 Cleaned up resources for {camera_id}")
            
        except Exception as e:
            self.logger.error(f"Cleanup failed for {camera_id}: {e}")
    
    def shutdown(self):
        """Shutdown performance optimizer"""
        self.logger.info("🔄 Shutting down Performance Optimizer...")
        
        # Stop monitoring
        self.stop_monitoring()
        
        # Clean up all cameras
        for camera_id in list(self.processing_queues.keys()):
            self.cleanup_camera(camera_id)
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=True)
        
        self.logger.info("✅ Performance Optimizer shutdown complete")

# Global performance optimizer
performance_optimizer = PerformanceOptimizer()

def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer"""
    return performance_optimizer

def optimize_frame(frame: np.ndarray, camera_id: str) -> np.ndarray:
    """Optimize frame for processing"""
    return performance_optimizer.optimize_frame(frame, camera_id)

def add_frame_for_processing(camera_id: str, frame: np.ndarray) -> bool:
    """Add frame to processing pipeline"""
    return performance_optimizer.add_frame(camera_id, frame)

def get_processing_results(camera_id: str) -> List[Tuple[Dict[str, Any], float]]:
    """Get processing results for camera"""
    return performance_optimizer.get_results(camera_id)

def get_performance_metrics(camera_id: str) -> Optional[PerformanceMetrics]:
    """Get performance metrics for camera"""
    return performance_optimizer.get_current_metrics(camera_id)

# Test function
def test_performance_optimizer():
    """Test the performance optimizer"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🧪 Testing Performance Optimizer")
    
    optimizer = get_performance_optimizer()
    
    # Create test frames
    test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    camera_id = "test_camera"
    
    # Test frame optimization
    optimized_frame = optimize_frame(test_frame, camera_id)
    logger.info(f"📐 Original frame shape: {test_frame.shape}")
    logger.info(f"📐 Optimized frame shape: {optimized_frame.shape}")
    
    # Test processing pipeline
    for i in range(10):
        success = add_frame_for_processing(camera_id, test_frame)
        logger.info(f"🎬 Frame {i+1} added: {success}")
        time.sleep(0.1)
    
    # Wait for processing
    time.sleep(2)
    
    # Get results
    results = get_processing_results(camera_id)
    logger.info(f"📊 Processed {len(results)} frames")
    
    # Get performance metrics
    metrics = get_performance_metrics(camera_id)
    if metrics:
        logger.info(f"⚡ Current FPS: {metrics.fps:.1f}")
        logger.info(f"⏱️ Processing time: {metrics.processing_time:.1f}ms")
        logger.info(f"💾 Memory usage: {metrics.memory_usage:.1f}%")
    
    # Get performance summary
    summary = optimizer.get_performance_summary()
    logger.info(f"📈 Performance summary: {summary}")
    
    # Cleanup
    optimizer.cleanup_camera(camera_id)
    
    logger.info("✅ Performance Optimizer test completed")

if __name__ == "__main__":
    test_performance_optimizer() 