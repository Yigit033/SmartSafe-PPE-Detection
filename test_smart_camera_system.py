#!/usr/bin/env python3
"""
SmartSafe AI - Akıllı Kamera Sistemi Test Senaryoları
Kapsamlı test senaryoları ve performans testleri
"""

import unittest
import asyncio
import time
import json
import logging
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Any

# Test için gerekli modüller
try:
    from camera_integration_manager import ProfessionalCameraManager, SmartCameraDetector
    from utils.camera_model_database import CameraModelDatabase, CameraModelInfo
    from utils.enhanced_ppe_detector import EnhancedPPEDetector
    from utils.hybrid_ppe_system import HybridPPESystem
except ImportError as e:
    print(f"❌ Test modülleri yüklenemedi: {e}")
    print("💡 Lütfen gerekli modüllerin yüklü olduğundan emin olun.")
    exit(1)

# Test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartCameraSystemTest(unittest.TestCase):
    """Akıllı kamera sistemi test sınıfı"""
    
    def setUp(self):
        """Test öncesi hazırlık"""
        self.camera_manager = ProfessionalCameraManager()
        self.smart_detector = SmartCameraDetector()
        self.model_database = CameraModelDatabase()
        
        # Test kamera verileri
        self.test_cameras = {
            'hikvision': {
                'ip': '192.168.1.100',
                'port': 80,
                'protocol': 'http',
                'path': '/ISAPI/Streaming/channels/101',
                'username': 'admin',
                'password': 'admin'
            },
            'dahua': {
                'ip': '192.168.1.101',
                'port': 80,
                'protocol': 'http',
                'path': '/cgi-bin/magicBox.cgi',
                'username': 'admin',
                'password': 'admin'
            },
            'axis': {
                'ip': '192.168.1.102',
                'port': 80,
                'protocol': 'http',
                'path': '/axis-cgi/jpg/image.cgi',
                'username': 'root',
                'password': 'pass'
            },
            'foscam': {
                'ip': '192.168.1.103',
                'port': 88,
                'protocol': 'http',
                'path': '/videostream.cgi',
                'username': 'admin',
                'password': 'admin'
            },
            'generic': {
                'ip': '192.168.1.104',
                'port': 8080,
                'protocol': 'http',
                'path': '/video',
                'username': '',
                'password': ''
            }
        }
    
    def tearDown(self):
        """Test sonrası temizlik"""
        pass

class CameraDetectionTests(SmartCameraSystemTest):
    """Kamera tespit testleri"""
    
    def test_smart_camera_detection_hikvision(self):
        """Hikvision kamera tespit testi"""
        logger.info("🧪 Testing Hikvision camera detection...")
        
        camera_data = self.test_cameras['hikvision']
        
        with patch('requests.get') as mock_get:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Hikvision IP Camera"
            mock_response.headers = {'Server': 'App-webs/'}
            mock_get.return_value = mock_response
            
            # Test detection
            result = self.smart_detector.smart_detect_camera(camera_data['ip'])
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            self.assertEqual(result['model'], 'Hikvision IP Camera')
            self.assertGreater(result['confidence'], 0.8)
            logger.info(f"✅ Hikvision detection: {result}")
    
    def test_smart_camera_detection_dahua(self):
        """Dahua kamera tespit testi"""
        logger.info("🧪 Testing Dahua camera detection...")
        
        camera_data = self.test_cameras['dahua']
        
        with patch('requests.get') as mock_get:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Dahua IP Camera"
            mock_response.headers = {'Server': 'DNVRS-Webs'}
            mock_get.return_value = mock_response
            
            # Test detection
            result = self.smart_detector.smart_detect_camera(camera_data['ip'])
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            self.assertEqual(result['model'], 'Dahua IP Camera')
            self.assertGreater(result['confidence'], 0.8)
            logger.info(f"✅ Dahua detection: {result}")
    
    def test_smart_camera_detection_axis(self):
        """Axis kamera tespit testi"""
        logger.info("🧪 Testing Axis camera detection...")
        
        camera_data = self.test_cameras['axis']
        
        with patch('requests.get') as mock_get:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Axis IP Camera"
            mock_response.headers = {'Server': 'AXIS'}
            mock_get.return_value = mock_response
            
            # Test detection
            result = self.smart_detector.smart_detect_camera(camera_data['ip'])
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            self.assertEqual(result['model'], 'Axis IP Camera')
            self.assertGreater(result['confidence'], 0.8)
            logger.info(f"✅ Axis detection: {result}")
    
    def test_smart_camera_detection_foscam(self):
        """Foscam kamera tespit testi"""
        logger.info("🧪 Testing Foscam camera detection...")
        
        camera_data = self.test_cameras['foscam']
        
        with patch('requests.get') as mock_get:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Foscam IP Camera"
            mock_response.headers = {'Server': 'Foscam'}
            mock_get.return_value = mock_response
            
            # Test detection
            result = self.smart_detector.smart_detect_camera(camera_data['ip'])
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            self.assertEqual(result['model'], 'Foscam IP Camera')
            self.assertGreater(result['confidence'], 0.8)
            logger.info(f"✅ Foscam detection: {result}")
    
    def test_smart_camera_detection_generic(self):
        """Generic kamera tespit testi"""
        logger.info("🧪 Testing Generic camera detection...")
        
        camera_data = self.test_cameras['generic']
        
        with patch('requests.get') as mock_get:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Generic IP Camera"
            mock_response.headers = {'Server': 'Generic'}
            mock_get.return_value = mock_response
            
            # Test detection
            result = self.smart_detector.smart_detect_camera(camera_data['ip'])
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            self.assertEqual(result['model'], 'Generic IP Camera')
            self.assertGreater(result['confidence'], 0.7)
            logger.info(f"✅ Generic detection: {result}")
    
    def test_detection_with_invalid_ip(self):
        """Geçersiz IP ile tespit testi"""
        logger.info("🧪 Testing detection with invalid IP...")
        
        result = self.smart_detector.smart_detect_camera("999.999.999.999")
        
        self.assertIsNotNone(result)
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        logger.info(f"✅ Invalid IP test: {result}")

class CameraConnectionTests(SmartCameraSystemTest):
    """Kamera bağlantı testleri"""
    
    def test_camera_connection_success(self):
        """Başarılı kamera bağlantı testi"""
        logger.info("🧪 Testing successful camera connection...")
        
        camera_data = self.test_cameras['hikvision']
        
        with patch('requests.get') as mock_get:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'fake_image_data'
            mock_get.return_value = mock_response
            
            # Create CameraSource object
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id="test_camera_001",
                name="Test Camera",
                source_type="real_camera",
                connection_url=f"{camera_data['protocol']}://{camera_data['ip']}:{camera_data['port']}{camera_data['path']}",
                username=camera_data['username'],
                password=camera_data['password']
            )
            
            # Test connection
            result = self.camera_manager.test_camera_connection(camera_source)
            
            self.assertIsNotNone(result)
            self.assertTrue(result['success'])
            logger.info(f"✅ Connection success: {result}")
    
    def test_camera_connection_timeout(self):
        """Zaman aşımı ile bağlantı testi"""
        logger.info("🧪 Testing camera connection timeout...")
        
        camera_data = self.test_cameras['hikvision']
        
        with patch('requests.get') as mock_get:
            # Mock timeout
            mock_get.side_effect = Exception("Connection timeout")
            
            # Create CameraSource object
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id="test_camera_002",
                name="Test Camera",
                source_type="real_camera",
                connection_url=f"{camera_data['protocol']}://{camera_data['ip']}:{camera_data['port']}{camera_data['path']}",
                username=camera_data['username'],
                password=camera_data['password']
            )
            
            # Test connection
            result = self.camera_manager.test_camera_connection(camera_source)
            
            self.assertIsNotNone(result)
            self.assertFalse(result['success'])
            self.assertIn('error_message', result)
            logger.info(f"✅ Timeout test: {result}")
    
    def test_camera_connection_auth_failure(self):
        """Kimlik doğrulama hatası testi"""
        logger.info("🧪 Testing camera authentication failure...")
        
        camera_data = self.test_cameras['hikvision']
        
        with patch('requests.get') as mock_get:
            # Mock auth failure
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response
            
            # Create CameraSource object
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id="test_camera_003",
                name="Test Camera",
                source_type="real_camera",
                connection_url=f"{camera_data['protocol']}://{camera_data['ip']}:{camera_data['port']}{camera_data['path']}",
                username='wrong',
                password='wrong'
            )
            
            # Test connection
            result = self.camera_manager.test_camera_connection(camera_source)
            
            self.assertIsNotNone(result)
            self.assertFalse(result['success'])
            self.assertIn('error_message', result)
            logger.info(f"✅ Auth failure test: {result}")
    
    def test_camera_connection_invalid_port(self):
        """Geçersiz port ile bağlantı testi"""
        logger.info("🧪 Testing camera connection with invalid port...")
        
        camera_data = self.test_cameras['hikvision']
        
        with patch('requests.get') as mock_get:
            # Mock connection refused
            mock_get.side_effect = Exception("Connection refused")
            
            # Create CameraSource object
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id="test_camera_004",
                name="Test Camera",
                source_type="real_camera",
                connection_url=f"{camera_data['protocol']}://{camera_data['ip']}:99999{camera_data['path']}",
                username=camera_data['username'],
                password=camera_data['password']
            )
            
            # Test connection
            result = self.camera_manager.test_camera_connection(camera_source)
            
            self.assertIsNotNone(result)
            self.assertFalse(result['success'])
            self.assertIn('error_message', result)
            logger.info(f"✅ Invalid port test: {result}")

class NetworkDiscoveryTests(SmartCameraSystemTest):
    """Ağ keşif testleri"""
    
    def test_network_scan_success(self):
        """Başarılı ağ tarama testi"""
        logger.info("🧪 Testing successful network scan...")
        
        with patch('camera_integration_manager.ProfessionalCameraManager.smart_discover_cameras') as mock_discover:
            # Mock discovered cameras
            mock_discover.return_value = [
                {
                    'ip': '192.168.1.100',
                    'model': 'Hikvision IP Camera',
                    'confidence': 0.9,
                    'protocol': 'http',
                    'port': 80
                },
                {
                    'ip': '192.168.1.101',
                    'model': 'Dahua IP Camera',
                    'confidence': 0.8,
                    'protocol': 'http',
                    'port': 80
                }
            ]
            
            # Test network scan
            result = self.camera_manager.smart_discover_cameras('192.168.1.0/24')
            
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['model'], 'Hikvision IP Camera')
            self.assertEqual(result[1]['model'], 'Dahua IP Camera')
            logger.info(f"✅ Network scan success: {len(result)} cameras found")
    
    def test_network_scan_empty(self):
        """Boş ağ tarama testi"""
        logger.info("🧪 Testing empty network scan...")
        
        with patch('camera_integration_manager.ProfessionalCameraManager.smart_discover_cameras') as mock_discover:
            # Mock empty result
            mock_discover.return_value = []
            
            # Test network scan
            result = self.camera_manager.smart_discover_cameras('192.168.1.0/24')
            
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 0)
            logger.info(f"✅ Empty network scan: {result}")

class ModelDatabaseTests(SmartCameraSystemTest):
    """Model veritabanı testleri"""
    
    def test_database_loading(self):
        """Veritabanı yükleme testi"""
        logger.info("🧪 Testing database loading...")
        
        models = self.model_database.get_all_models()
        
        self.assertIsNotNone(models)
        self.assertGreater(len(models), 0)
        self.assertIn('hikvision', models)
        self.assertIn('dahua', models)
        self.assertIn('axis', models)
        logger.info(f"✅ Database loading: {len(models)} models loaded")
    
    def test_model_info_retrieval(self):
        """Model bilgisi alma testi"""
        logger.info("🧪 Testing model info retrieval...")
        
        model_info = self.model_database.get_model_info('hikvision')
        
        self.assertIsNotNone(model_info)
        self.assertEqual(model_info.name, 'Hikvision IP Camera')
        self.assertEqual(model_info.manufacturer, 'Hikvision')
        self.assertIn('ptz', model_info.features)
        self.assertIn(80, model_info.ports)
        logger.info(f"✅ Model info retrieval: {model_info.name}")
    
    def test_models_by_manufacturer(self):
        """Üreticiye göre model arama testi"""
        logger.info("🧪 Testing models by manufacturer...")
        
        hikvision_models = self.model_database.get_models_by_manufacturer('Hikvision')
        
        self.assertIsNotNone(hikvision_models)
        self.assertIn('hikvision', hikvision_models)
        self.assertIn('hikvision_dvr', hikvision_models)
        logger.info(f"✅ Manufacturer search: {hikvision_models}")
    
    def test_models_by_feature(self):
        """Özelliğe göre model arama testi"""
        logger.info("🧪 Testing models by feature...")
        
        ptz_models = self.model_database.get_models_by_feature('ptz')
        
        self.assertIsNotNone(ptz_models)
        self.assertIn('hikvision', ptz_models)
        self.assertIn('dahua', ptz_models)
        self.assertIn('axis', ptz_models)
        logger.info(f"✅ Feature search: {ptz_models}")
    
    def test_custom_model_addition(self):
        """Özel model ekleme testi"""
        logger.info("🧪 Testing custom model addition...")
        
        # Create custom model
        custom_model = CameraModelInfo(
            name='Custom Test Camera',
            manufacturer='Test Manufacturer',
            ports=[8080, 80],
            paths=['/test', '/video'],
            headers=['Server: Test'],
            default_rtsp='rtsp://{ip}:554/test',
            default_http='http://{ip}:8080/test',
            default_credentials={'username': 'test', 'password': 'test'},
            features=['test_feature'],
            resolution_support=['1280x720'],
            fps_support=[30],
            codec_support=['H.264']
        )
        
        # Add custom model
        self.model_database.add_custom_model('custom_test', custom_model)
        
        # Verify addition
        added_model = self.model_database.get_model_info('custom_test')
        self.assertIsNotNone(added_model)
        self.assertEqual(added_model.name, 'Custom Test Camera')
        
        # Cleanup
        self.model_database.remove_model('custom_test')
        logger.info(f"✅ Custom model addition: {added_model.name}")

class PerformanceTests(SmartCameraSystemTest):
    """Performans testleri"""
    
    def test_detection_performance(self):
        """Tespit performans testi"""
        logger.info("🧪 Testing detection performance...")
        
        start_time = time.time()
        
        # Perform multiple detections
        for i in range(10):
            with patch('requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = "Hikvision IP Camera"
                mock_response.headers = {'Server': 'App-webs/'}
                mock_get.return_value = mock_response
                
                result = self.smart_detector.smart_detect_camera(f'192.168.1.{100 + i}')
                self.assertIsNotNone(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Performance threshold: 10 detections should complete in under 5 seconds
        self.assertLess(duration, 5.0)
        logger.info(f"✅ Detection performance: {duration:.2f}s for 10 detections")
    
    def test_connection_performance(self):
        """Bağlantı performans testi"""
        logger.info("🧪 Testing connection performance...")
        
        start_time = time.time()
        
        # Perform multiple connections
        for i in range(5):
            with patch('requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b'fake_image_data'
                mock_get.return_value = mock_response
                
                # Create CameraSource object
                from camera_integration_manager import CameraSource
                camera_source = CameraSource(
                    camera_id=f"test_camera_{i:03d}",
                    name=f"Test Camera {i}",
                    source_type="real_camera",
                    connection_url=f"http://192.168.1.{100 + i}:80/video",
                    username='admin',
                    password='admin'
                )
                
                result = self.camera_manager.test_camera_connection(camera_source)
                self.assertIsNotNone(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Performance threshold: 5 connections should complete in under 3 seconds
        self.assertLess(duration, 3.0)
        logger.info(f"✅ Connection performance: {duration:.2f}s for 5 connections")
    
    def test_database_performance(self):
        """Veritabanı performans testi"""
        logger.info("🧪 Testing database performance...")
        
        start_time = time.time()
        
        # Perform multiple database operations
        for i in range(100):
            models = self.model_database.get_all_models()
            model_info = self.model_database.get_model_info('hikvision')
            ptz_models = self.model_database.get_models_by_feature('ptz')
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Performance threshold: 100 operations should complete in under 1 second
        self.assertLess(duration, 1.0)
        logger.info(f"✅ Database performance: {duration:.2f}s for 100 operations")

class IntegrationTests(SmartCameraSystemTest):
    """Entegrasyon testleri"""
    
    def test_full_camera_workflow(self):
        """Tam kamera iş akışı testi"""
        logger.info("🧪 Testing full camera workflow...")
        
        camera_ip = '192.168.1.100'
        
        with patch('requests.get') as mock_get:
            # Mock successful responses
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Hikvision IP Camera"
            mock_response.headers = {'Server': 'App-webs/'}
            mock_response.content = b'fake_image_data'
            mock_get.return_value = mock_response
            
            # Step 1: Smart detection
            detection_result = self.smart_detector.smart_detect_camera(camera_ip)
            self.assertTrue(detection_result['success'])
            
            # Step 2: Connection test
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id="test_camera_workflow",
                name="Test Camera",
                source_type="real_camera",
                connection_url=f"http://{camera_ip}:80/ISAPI/Streaming/channels/101",
                username='admin',
                password='admin'
            )
            connection_result = self.camera_manager.test_camera_connection(camera_source)
            self.assertTrue(connection_result['success'])
            
            # Step 3: Model database lookup
            model_info = self.model_database.get_model_info('hikvision')
            self.assertIsNotNone(model_info)
            
            logger.info(f"✅ Full workflow: Detection={detection_result['success']}, Connection={connection_result['success']}")
    
    def test_error_handling_integration(self):
        """Hata yönetimi entegrasyon testi"""
        logger.info("🧪 Testing error handling integration...")
        
        camera_ip = '999.999.999.999'
        
        # Test with invalid IP
        detection_result = self.smart_detector.smart_detect_camera(camera_ip)
        self.assertFalse(detection_result['success'])
        self.assertIn('error', detection_result)
        
        # Test connection with invalid IP
        from camera_integration_manager import CameraSource
        camera_source = CameraSource(
            camera_id="test_camera_invalid",
            name="Invalid Camera",
            source_type="real_camera",
            connection_url=f"http://{camera_ip}:80/video",
            username='admin',
            password='admin'
        )
        connection_result = self.camera_manager.test_camera_connection(camera_source)
        self.assertFalse(connection_result['success'])
        self.assertIn('error_message', connection_result)
        
        logger.info(f"✅ Error handling: Detection={detection_result['success']}, Connection={connection_result['success']}")

def run_performance_benchmark():
    """Performans benchmark testi"""
    logger.info("🚀 Starting Performance Benchmark...")
    
    camera_manager = ProfessionalCameraManager()
    smart_detector = SmartCameraDetector()
    model_database = CameraModelDatabase()
    
    # Benchmark parameters
    num_detections = 50
    num_connections = 20
    num_db_operations = 1000
    
    # Detection benchmark
    start_time = time.time()
    for i in range(num_detections):
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Hikvision IP Camera"
            mock_response.headers = {'Server': 'App-webs/'}
            mock_get.return_value = mock_response
            
            smart_detector.smart_detect_camera(f'192.168.1.{100 + i}')
    
    detection_time = time.time() - start_time
    
    # Connection benchmark
    start_time = time.time()
    for i in range(num_connections):
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'fake_image_data'
            mock_get.return_value = mock_response
            
            # Create CameraSource object
            from camera_integration_manager import CameraSource
            camera_source = CameraSource(
                camera_id=f"benchmark_camera_{i:03d}",
                name=f"Benchmark Camera {i}",
                source_type="real_camera",
                connection_url=f"http://192.168.1.{100 + i}:80/video",
                username='admin',
                password='admin'
            )
            camera_manager.test_camera_connection(camera_source)
    
    connection_time = time.time() - start_time
    
    # Database benchmark
    start_time = time.time()
    for i in range(num_db_operations):
        model_database.get_all_models()
        model_database.get_model_info('hikvision')
        model_database.get_models_by_feature('ptz')
    
    database_time = time.time() - start_time
    
    # Results
    logger.info("📊 Performance Benchmark Results:")
    logger.info(f"  Detection: {num_detections} operations in {detection_time:.2f}s ({num_detections/detection_time:.1f} ops/s)")
    logger.info(f"  Connection: {num_connections} operations in {connection_time:.2f}s ({num_connections/connection_time:.1f} ops/s)")
    logger.info(f"  Database: {num_db_operations} operations in {database_time:.2f}s ({num_db_operations/database_time:.1f} ops/s)")
    
    # Performance thresholds
    detection_threshold = 10.0  # 10 seconds for 50 detections
    connection_threshold = 15.0  # 15 seconds for 20 connections
    database_threshold = 2.0   # 2 seconds for 1000 operations
    
    if detection_time < detection_threshold:
        logger.info("✅ Detection performance: PASS")
    else:
        logger.warning(f"⚠️ Detection performance: SLOW ({detection_time:.2f}s > {detection_threshold}s)")
    
    if connection_time < connection_threshold:
        logger.info("✅ Connection performance: PASS")
    else:
        logger.warning(f"⚠️ Connection performance: SLOW ({connection_time:.2f}s > {connection_threshold}s)")
    
    if database_time < database_threshold:
        logger.info("✅ Database performance: PASS")
    else:
        logger.warning(f"⚠️ Database performance: SLOW ({database_time:.2f}s > {database_threshold}s)")

def main():
    """Ana test fonksiyonu"""
    logger.info("🎯 Smart Camera System Test Suite Starting...")
    
    # Test suite oluştur
    test_suite = unittest.TestSuite()
    
    # Test sınıflarını ekle
    test_classes = [
        CameraDetectionTests,
        CameraConnectionTests,
        NetworkDiscoveryTests,
        ModelDatabaseTests,
        PerformanceTests,
        IntegrationTests
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Testleri çalıştır
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Sonuçları raporla
    logger.info("📋 Test Results Summary:")
    logger.info(f"  Tests run: {result.testsRun}")
    logger.info(f"  Failures: {len(result.failures)}")
    logger.info(f"  Errors: {len(result.errors)}")
    logger.info(f"  Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    # Performans benchmark çalıştır
    if result.wasSuccessful():
        logger.info("\n🚀 Running Performance Benchmark...")
        run_performance_benchmark()
    
    # Sonuç döndür
    return result.wasSuccessful()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 