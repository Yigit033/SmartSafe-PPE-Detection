#!/usr/bin/env python3
"""
Production Camera System Test
Comprehensive test for camera functionality in production environment
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionCameraTest:
    def __init__(self):
        self.base_url = "https://smartsafeai.onrender.com"
        self.test_company_id = "COMP_E0326033"  # Test company
        self.test_results = []
        
    def test_camera_add_endpoint(self):
        """Test camera addition endpoint"""
        logger.info("🧪 Testing camera addition endpoint...")
        
        test_camera_data = {
            "name": "Test Camera Production",
            "ip_address": "192.168.1.190",
            "port": 8080,
            "username": "admin",
            "password": "admin123",
            "protocol": "http",
            "stream_path": "/video",
            "auth_type": "basic",
            "location": "Test Location",
            "width": 1920,
            "height": 1080,
            "fps": 25,
            "quality": 80,
            "audio_enabled": False,
            "night_vision": False,
            "motion_detection": True,
            "recording_enabled": True
        }
        
        try:
            url = f"{self.base_url}/api/company/{self.test_company_id}/cameras"
            response = requests.post(url, json=test_camera_data, timeout=30)
            
            result = {
                "test": "Camera Add Endpoint",
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text,
                "timestamp": datetime.now().isoformat()
            }
            
            self.test_results.append(result)
            
            if response.status_code == 200:
                logger.info("✅ Camera add endpoint test passed")
            else:
                logger.error(f"❌ Camera add endpoint test failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Camera add endpoint test error: {e}")
            self.test_results.append({
                "test": "Camera Add Endpoint",
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def test_camera_test_endpoint(self):
        """Test camera testing endpoint"""
        logger.info("🧪 Testing camera test endpoint...")
        
        test_data = {
            "ip_address": "192.168.1.190",
            "port": 8080,
            "username": "admin",
            "password": "admin123",
            "protocol": "http",
            "stream_path": "/video",
            "auth_type": "basic"
        }
        
        try:
            url = f"{self.base_url}/api/company/{self.test_company_id}/cameras/test"
            response = requests.post(url, json=test_data, timeout=30)
            
            result = {
                "test": "Camera Test Endpoint",
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text,
                "timestamp": datetime.now().isoformat()
            }
            
            self.test_results.append(result)
            
            if response.status_code == 200:
                logger.info("✅ Camera test endpoint test passed")
            else:
                logger.error(f"❌ Camera test endpoint test failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Camera test endpoint test error: {e}")
            self.test_results.append({
                "test": "Camera Test Endpoint",
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def test_camera_list_endpoint(self):
        """Test camera list endpoint"""
        logger.info("🧪 Testing camera list endpoint...")
        
        try:
            url = f"{self.base_url}/api/company/{self.test_company_id}/cameras"
            response = requests.get(url, timeout=30)
            
            result = {
                "test": "Camera List Endpoint",
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text,
                "timestamp": datetime.now().isoformat()
            }
            
            self.test_results.append(result)
            
            if response.status_code == 200:
                logger.info("✅ Camera list endpoint test passed")
            else:
                logger.error(f"❌ Camera list endpoint test failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Camera list endpoint test error: {e}")
            self.test_results.append({
                "test": "Camera List Endpoint",
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def test_company_stats_endpoint(self):
        """Test company stats endpoint"""
        logger.info("🧪 Testing company stats endpoint...")
        
        try:
            url = f"{self.base_url}/api/company/{self.test_company_id}/stats"
            response = requests.get(url, timeout=30)
            
            result = {
                "test": "Company Stats Endpoint",
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text,
                "timestamp": datetime.now().isoformat()
            }
            
            self.test_results.append(result)
            
            if response.status_code == 200:
                logger.info("✅ Company stats endpoint test passed")
            else:
                logger.error(f"❌ Company stats endpoint test failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Company stats endpoint test error: {e}")
            self.test_results.append({
                "test": "Company Stats Endpoint",
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def test_dashboard_access(self):
        """Test dashboard access"""
        logger.info("🧪 Testing dashboard access...")
        
        try:
            url = f"{self.base_url}/company/{self.test_company_id}/dashboard"
            response = requests.get(url, timeout=30)
            
            result = {
                "test": "Dashboard Access",
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "status_code": response.status_code,
                "response_length": len(response.text) if response.status_code == 200 else 0,
                "timestamp": datetime.now().isoformat()
            }
            
            self.test_results.append(result)
            
            if response.status_code == 200:
                logger.info("✅ Dashboard access test passed")
            else:
                logger.error(f"❌ Dashboard access test failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Dashboard access test error: {e}")
            self.test_results.append({
                "test": "Dashboard Access",
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def run_all_tests(self):
        """Run all production tests"""
        logger.info("🚀 Starting production camera system tests...")
        logger.info(f"📍 Testing against: {self.base_url}")
        logger.info(f"🏢 Test company: {self.test_company_id}")
        logger.info("=" * 60)
        
        # Run all tests
        self.test_dashboard_access()
        self.test_company_stats_endpoint()
        self.test_camera_list_endpoint()
        self.test_camera_test_endpoint()
        self.test_camera_add_endpoint()
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate test report"""
        logger.info("=" * 60)
        logger.info("📊 PRODUCTION CAMERA SYSTEM TEST REPORT")
        logger.info("=" * 60)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        errors = sum(1 for result in self.test_results if result["status"] == "ERROR")
        total = len(self.test_results)
        
        logger.info(f"📈 Total Tests: {total}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"❌ Failed: {failed}")
        logger.info(f"⚠️ Errors: {errors}")
        logger.info(f"📊 Success Rate: {(passed/total)*100:.1f}%")
        
        logger.info("\n📋 Detailed Results:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            logger.info(f"{status_icon} {result['test']}: {result['status']}")
            if result["status"] != "PASS":
                if "error" in result:
                    logger.info(f"   Error: {result['error']}")
                elif "status_code" in result:
                    logger.info(f"   Status Code: {result['status_code']}")
        
        # Save report to file
        report_file = f"production_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                "test_summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "success_rate": (passed/total)*100
                },
                "test_results": self.test_results,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        logger.info(f"📄 Detailed report saved to: {report_file}")
        
        # Final verdict
        if passed == total:
            logger.info("🎉 ALL TESTS PASSED! Camera system is ready for production!")
            return True
        else:
            logger.error("❌ SOME TESTS FAILED! Camera system needs fixes before production!")
            return False

def main():
    """Main function"""
    print("🚨 Production Camera System Test")
    print("=" * 60)
    print("This script tests all camera functionality in production environment")
    print(f"Target: https://smartsafeai.onrender.com")
    print()
    
    tester = ProductionCameraTest()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 Production camera system is ready!")
        sys.exit(0)
    else:
        print("\n❌ Production camera system needs fixes!")
        sys.exit(1)

if __name__ == "__main__":
    main() 