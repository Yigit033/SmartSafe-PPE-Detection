"""
SmartSafe AI - Production CUDA Handler
Handles CUDA/GPU issues in production environment
"""

import os
import logging
import torch
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProductionCUDAHandler:
    """Production CUDA/GPU handler for deployment"""
    
    def __init__(self):
        self.cuda_available = False
        self.device = 'cpu'
        self.cuda_test_passed = False
        self._test_cuda_availability()
    
    def _test_cuda_availability(self):
        """Test CUDA availability for production"""
        try:
            # Check if CUDA is available
            if torch.cuda.is_available():
                logger.info("✅ CUDA detected in production environment")
                
                # Test CUDA functionality
                try:
                    test_tensor = torch.zeros(1, 3, 640, 640).cuda()
                    _ = test_tensor * 2  # Simple operation test
                    self.cuda_available = True
                    self.device = 'cuda'
                    self.cuda_test_passed = True
                    logger.info("✅ CUDA test passed in production")
                except Exception as cuda_error:
                    logger.warning(f"⚠️ CUDA test failed in production: {cuda_error}")
                    self.cuda_available = False
                    self.device = 'cpu'
                    self.cuda_test_passed = False
            else:
                logger.info("ℹ️ CUDA not available in production, using CPU")
                self.cuda_available = False
                self.device = 'cpu'
                self.cuda_test_passed = False
                
        except Exception as e:
            logger.error(f"❌ CUDA availability test failed: {e}")
            self.cuda_available = False
            self.device = 'cpu'
            self.cuda_test_passed = False
    
    def get_safe_device(self) -> str:
        """Get safe device for production"""
        return self.device
    
    def is_cuda_safe(self) -> bool:
        """Check if CUDA is safe to use in production"""
        return self.cuda_test_passed
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get device information for production"""
        info = {
            'device': self.device,
            'cuda_available': self.cuda_available,
            'cuda_test_passed': self.cuda_test_passed,
            'production_safe': self.device == 'cpu' or self.cuda_test_passed
        }
        
        if self.cuda_available and self.cuda_test_passed:
            try:
                info['gpu_name'] = torch.cuda.get_device_name(0)
                info['gpu_memory'] = torch.cuda.get_device_properties(0).total_memory
                info['gpu_count'] = torch.cuda.device_count()
            except Exception as e:
                logger.warning(f"⚠️ GPU info retrieval failed: {e}")
        
        return info
    
    def create_safe_model(self, model_class, *args, **kwargs):
        """Create model with safe device assignment"""
        try:
            model = model_class(*args, **kwargs)
            
            # Safe device assignment
            if self.cuda_test_passed:
                try:
                    model = model.to('cuda')
                    logger.info("✅ Model assigned to CUDA successfully")
                except Exception as device_error:
                    logger.warning(f"⚠️ CUDA assignment failed: {device_error}, using CPU")
                    model = model.to('cpu')
            else:
                model = model.to('cpu')
                logger.info("✅ Model assigned to CPU (production safe)")
            
            return model
            
        except Exception as e:
            logger.error(f"❌ Model creation failed: {e}")
            return None
    
    def safe_inference(self, model, input_data, *args, **kwargs):
        """Safe inference with error handling"""
        try:
            # Try CUDA inference if available
            if self.cuda_test_passed and self.device == 'cuda':
                try:
                    result = model(input_data, *args, **kwargs)
                    logger.debug("✅ CUDA inference successful")
                    return result
                except Exception as cuda_error:
                    logger.warning(f"⚠️ CUDA inference failed: {cuda_error}, falling back to CPU")
                    # Fallback to CPU
                    model = model.to('cpu')
                    result = model(input_data, *args, **kwargs)
                    logger.info("✅ CPU inference successful (fallback)")
                    return result
            else:
                # CPU inference
                result = model(input_data, *args, **kwargs)
                logger.debug("✅ CPU inference successful")
                return result
                
        except Exception as e:
            logger.error(f"❌ Inference failed: {e}")
            return None

def get_production_cuda_handler() -> ProductionCUDAHandler:
    """Get production CUDA handler instance"""
    return ProductionCUDAHandler()

def test_production_cuda():
    """Test CUDA functionality for production"""
    handler = ProductionCUDAHandler()
    
    print("🚀 Production CUDA Test")
    print("=" * 40)
    
    device_info = handler.get_device_info()
    
    print(f"Device: {device_info['device']}")
    print(f"CUDA Available: {device_info['cuda_available']}")
    print(f"CUDA Test Passed: {device_info['cuda_test_passed']}")
    print(f"Production Safe: {device_info['production_safe']}")
    
    if 'gpu_name' in device_info:
        print(f"GPU Name: {device_info['gpu_name']}")
        print(f"GPU Memory: {device_info['gpu_memory'] / 1024**3:.1f} GB")
        print(f"GPU Count: {device_info['gpu_count']}")
    
    if device_info['production_safe']:
        print("✅ Production deployment ready!")
    else:
        print("⚠️ Using CPU fallback for production")
    
    return handler

if __name__ == "__main__":
    test_production_cuda() 