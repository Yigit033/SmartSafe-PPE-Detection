#!/usr/bin/env python3
"""
SmartSafe AI - Real Camera System Test
Test script for real camera integration with IP, port, username, password support
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from camera_integration_manager import RealCameraManager, RealCameraConfig
from database_adapter import get_db_adapter
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_real_camera_system():
    """Test the real camera system with sample data from screenshot"""
    
    print("🎥 SmartSafe AI - Real Camera System Test")
    print("=" * 50)
    
    # Initialize real camera manager
    real_camera_manager = RealCameraManager()
    
    # Test camera configuration based on screenshot (192.168.1.190:8080)
    test_camera_config = RealCameraConfig(
        camera_id="TEST_REAL_CAM_001",
        name="Test Real Camera - 192.168.1.190",
        ip_address="192.168.1.190",
        port=8080,
        username="admin",  # Common default
        password="admin",  # Common default
        protocol="http",
        stream_path="/video",
        auth_type="basic",
        resolution=(1920, 1080),
        fps=25,
        quality=80,
        motion_detection=True,
        recording_enabled=True
    )
    
    print(f"📹 Testing camera: {test_camera_config.name}")
    print(f"   IP: {test_camera_config.ip_address}:{test_camera_config.port}")
    print(f"   Stream URL: {test_camera_config.get_stream_url()}")
    print(f"   MJPEG URL: {test_camera_config.get_mjpeg_url()}")
    
    # Test connection
    print("\n🔍 Testing camera connection...")
    test_result = real_camera_manager.test_real_camera_connection(test_camera_config)
    
    if test_result['success']:
        print(f"✅ Camera connection successful!")
        print(f"   Connection time: {test_result['connection_time']:.2f}s")
        print(f"   Stream quality: {test_result['stream_quality']}")
        print(f"   Supported features: {test_result['supported_features']}")
        
        # Try to add camera to manager
        print("\n📝 Adding camera to manager...")
        success, message = real_camera_manager.add_real_camera(test_camera_config)
        
        if success:
            print(f"✅ Camera added successfully: {message}")
            
            # Get camera status
            status = real_camera_manager.get_real_camera_status(test_camera_config.camera_id)
            print(f"📊 Camera status: {status}")
            
        else:
            print(f"❌ Failed to add camera: {message}")
            
    else:
        print(f"❌ Camera connection failed: {test_result['error']}")
        
        # Test with different common configurations
        print("\n🔄 Trying alternative configurations...")
        
        # Test without authentication
        test_camera_config.username = ""
        test_camera_config.password = ""
        test_camera_config.auth_type = "none"
        
        print(f"   Testing without authentication...")
        test_result2 = real_camera_manager.test_real_camera_connection(test_camera_config)
        
        if test_result2['success']:
            print(f"✅ Connection successful without auth!")
        else:
            print(f"❌ Still failed: {test_result2['error']}")
            
            # Test RTSP
            test_camera_config.protocol = "rtsp"
            test_camera_config.port = 554
            test_camera_config.stream_path = "/stream"
            
            print(f"   Testing RTSP protocol...")
            test_result3 = real_camera_manager.test_real_camera_connection(test_camera_config)
            
            if test_result3['success']:
                print(f"✅ RTSP connection successful!")
            else:
                print(f"❌ RTSP also failed: {test_result3['error']}")

def test_form_data_processing():
    """Test form data processing like from the web interface"""
    
    print("\n" + "=" * 50)
    print("🌐 Testing Form Data Processing")
    print("=" * 50)
    
    # Sample form data from web interface
    form_data = {
        'name': 'Production Camera 1',
        'ip_address': '192.168.1.190',
        'port': 8080,
        'username': 'admin',
        'password': 'password123',
        'protocol': 'http',
        'stream_path': '/video',
        'auth_type': 'basic',
        'width': 1920,
        'height': 1080,
        'fps': 25,
        'quality': 80,
        'audio_enabled': False,
        'night_vision': False,
        'motion_detection': True,
        'recording_enabled': True,
        'location': 'Production Floor A'
    }
    
    real_camera_manager = RealCameraManager()
    
    print(f"📝 Processing form data for: {form_data['name']}")
    
    # Create camera config from form data
    camera_config = real_camera_manager.create_real_camera_from_form(form_data)
    
    print(f"✅ Camera config created:")
    print(f"   Name: {camera_config.name}")
    print(f"   IP: {camera_config.ip_address}:{camera_config.port}")
    print(f"   Protocol: {camera_config.protocol}")
    print(f"   Auth: {camera_config.auth_type}")
    print(f"   Resolution: {camera_config.resolution}")
    print(f"   Stream URL: {camera_config.get_stream_url()}")
    
    # Test the configuration
    print(f"\n🔍 Testing form-generated config...")
    test_result = real_camera_manager.test_real_camera_connection(camera_config)
    
    if test_result['success']:
        print(f"✅ Form data test successful!")
        print(f"   Connection time: {test_result['connection_time']:.2f}s")
    else:
        print(f"❌ Form data test failed: {test_result['error']}")

def test_database_integration():
    """Test database integration with new camera schema"""
    
    print("\n" + "=" * 50)
    print("💾 Testing Database Integration")
    print("=" * 50)
    
    try:
        # Get database adapter
        db_adapter = get_db_adapter()
        
        # Test camera data
        camera_data = {
            'name': 'DB Test Camera',
            'ip_address': '192.168.1.190',
            'port': 8080,
            'username': 'admin',
            'password': 'admin',
            'protocol': 'http',
            'stream_path': '/video',
            'auth_type': 'basic',
            'width': 1920,
            'height': 1080,
            'fps': 25,
            'quality': 80,
            'audio_enabled': False,
            'night_vision': False,
            'motion_detection': True,
            'recording_enabled': True,
            'location': 'Test Location'
        }
        
        # Test database connection
        print("🔍 Testing database connection...")
        
        # Try to get companies (should work if DB is set up)
        query = "SELECT COUNT(*) FROM companies"
        result = db_adapter.execute_query(query, fetch_all=False)
        
        if result:
            print(f"✅ Database connection successful")
            # Handle different result types
            if isinstance(result, (list, tuple)):
                count = result[0] if result else 0
            else:
                # For sqlite3.Row objects
                count = result[0] if hasattr(result, '__getitem__') else 0
            print(f"   Companies in database: {count}")
        else:
            print("❌ Database connection failed")
            
    except Exception as e:
        print(f"❌ Database test error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Real Camera System Tests...")
    
    # Run tests
    test_real_camera_system()
    test_form_data_processing()
    test_database_integration()
    
    print("\n" + "=" * 50)
    print("✅ Real Camera System Tests Complete!")
    print("=" * 50) 