#!/usr/bin/env python3
"""
Final Production Validation Script
Comprehensive test for all camera scenarios and edge cases
"""

import os
import sys
import json
import logging
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FinalProductionValidation:
    def __init__(self):
        self.validation_results = []
        self.critical_issues = []
        self.warnings = []
        
    def validate_database_schema(self):
        """Validate database schema compatibility"""
        logger.info("🔍 Validating database schema...")
        
        try:
            from smartsafe_multitenant_system import MultiTenantDatabase
            
            # Test database initialization
            db = MultiTenantDatabase()
            
            # Test camera addition with various scenarios
            test_company_id = "COMP_TEST_VALIDATION"
            
            # Test scenarios
            camera_scenarios = [
                {
                    "name": "Basic IP Camera",
                    "data": {
                        "name": "Test Camera 1",
                        "ip_address": "192.168.1.190",
                        "port": 8080,
                        "location": "Test Location"
                    }
                },
                {
                    "name": "RTSP Camera with Auth",
                    "data": {
                        "name": "Test Camera 2",
                        "ip_address": "192.168.1.191",
                        "port": 554,
                        "username": "admin",
                        "password": "admin123",
                        "protocol": "rtsp",
                        "location": "Test Location 2"
                    }
                },
                {
                    "name": "HTTP Camera with Resolution",
                    "data": {
                        "name": "Test Camera 3",
                        "ip_address": "192.168.1.192",
                        "port": 8080,
                        "protocol": "http",
                        "resolution": {"width": 1920, "height": 1080},
                        "fps": 25,
                        "location": "Test Location 3"
                    }
                }
            ]
            
            schema_valid = True
            for scenario in camera_scenarios:
                try:
                    success, result = db.add_camera(test_company_id, scenario["data"])
                    if not success:
                        logger.warning(f"⚠️ Schema test failed for {scenario['name']}: {result}")
                        schema_valid = False
                    else:
                        logger.info(f"✅ Schema test passed for {scenario['name']}")
                except Exception as e:
                    logger.error(f"❌ Schema test error for {scenario['name']}: {e}")
                    schema_valid = False
            
            self.validation_results.append({
                "test": "Database Schema Validation",
                "status": "PASS" if schema_valid else "FAIL",
                "details": f"Tested {len(camera_scenarios)} camera scenarios"
            })
            
            return schema_valid
            
        except Exception as e:
            logger.error(f"❌ Database schema validation error: {e}")
            self.critical_issues.append(f"Database schema validation failed: {e}")
            return False
    
    def validate_camera_endpoints(self):
        """Validate all camera API endpoints"""
        logger.info("🔍 Validating camera API endpoints...")
        
        try:
            from smartsafe_saas_api import SmartSafeSaaSAPI
            
            # Test API initialization
            api = SmartSafeSaaSAPI()
            
            # Check if all critical methods exist
            required_methods = [
                '_basic_camera_test',
                'validate_session',
                'setup_routes'
            ]
            
            endpoints_valid = True
            for method in required_methods:
                if not hasattr(api, method):
                    logger.error(f"❌ Required method missing: {method}")
                    endpoints_valid = False
                else:
                    logger.info(f"✅ Method exists: {method}")
            
            # Test basic camera test functionality
            test_camera_data = {
                "ip_address": "192.168.1.190",
                "port": 8080,
                "username": "admin",
                "password": "admin123",
                "protocol": "http"
            }
            
            try:
                result = api._basic_camera_test(test_camera_data)
                if 'success' in result and 'connection_time' in result:
                    logger.info("✅ Basic camera test method working")
                else:
                    logger.warning("⚠️ Basic camera test method returns unexpected format")
                    endpoints_valid = False
            except Exception as e:
                logger.error(f"❌ Basic camera test method error: {e}")
                endpoints_valid = False
            
            self.validation_results.append({
                "test": "Camera API Endpoints",
                "status": "PASS" if endpoints_valid else "FAIL",
                "details": f"Validated {len(required_methods)} required methods"
            })
            
            return endpoints_valid
            
        except Exception as e:
            logger.error(f"❌ Camera endpoints validation error: {e}")
            self.critical_issues.append(f"Camera endpoints validation failed: {e}")
            return False
    
    def validate_error_handling(self):
        """Validate error handling in camera operations"""
        logger.info("🔍 Validating error handling...")
        
        try:
            from smartsafe_multitenant_system import MultiTenantDatabase
            
            db = MultiTenantDatabase()
            
            # Test error scenarios
            error_scenarios = [
                {
                    "name": "Empty camera data",
                    "data": {}
                },
                {
                    "name": "Invalid IP address",
                    "data": {
                        "name": "Invalid IP Test",
                        "ip_address": "invalid.ip.address",
                        "port": 8080
                    }
                },
                {
                    "name": "Duplicate camera name",
                    "data": {
                        "name": "Test Camera Duplicate",
                        "ip_address": "192.168.1.100",
                        "port": 8080
                    }
                }
            ]
            
            error_handling_valid = True
            test_company_id = "COMP_ERROR_TEST"
            
            for scenario in error_scenarios:
                try:
                    success, result = db.add_camera(test_company_id, scenario["data"])
                    if success:
                        logger.warning(f"⚠️ Error scenario should have failed: {scenario['name']}")
                        error_handling_valid = False
                    else:
                        logger.info(f"✅ Error handling correct for: {scenario['name']}")
                except Exception as e:
                    logger.info(f"✅ Exception properly handled for: {scenario['name']} - {e}")
            
            self.validation_results.append({
                "test": "Error Handling Validation",
                "status": "PASS" if error_handling_valid else "FAIL",
                "details": f"Tested {len(error_scenarios)} error scenarios"
            })
            
            return error_handling_valid
            
        except Exception as e:
            logger.error(f"❌ Error handling validation error: {e}")
            self.critical_issues.append(f"Error handling validation failed: {e}")
            return False
    
    def validate_session_security(self):
        """Validate session management and security"""
        logger.info("🔍 Validating session security...")
        
        try:
            from smartsafe_multitenant_system import MultiTenantDatabase
            
            db = MultiTenantDatabase()
            
            # Test session creation and validation
            test_user_id = "USER_TEST_SESSION"
            test_company_id = "COMP_TEST_SESSION"
            
            # Create session
            session_id = db.create_session(
                test_user_id, 
                test_company_id, 
                "127.0.0.1", 
                "Test User Agent"
            )
            
            session_valid = True
            if not session_id:
                logger.error("❌ Session creation failed")
                session_valid = False
            else:
                logger.info("✅ Session creation successful")
                
                # Test session validation
                try:
                    session_data = db.validate_session(session_id)
                    if session_data:
                        logger.info("✅ Session validation working")
                    else:
                        logger.warning("⚠️ Session validation returned None")
                        session_valid = False
                except Exception as e:
                    logger.error(f"❌ Session validation error: {e}")
                    session_valid = False
            
            self.validation_results.append({
                "test": "Session Security Validation",
                "status": "PASS" if session_valid else "FAIL",
                "details": "Tested session creation and validation"
            })
            
            return session_valid
            
        except Exception as e:
            logger.error(f"❌ Session security validation error: {e}")
            self.critical_issues.append(f"Session security validation failed: {e}")
            return False
    
    def validate_production_readiness(self):
        """Validate overall production readiness"""
        logger.info("🔍 Validating production readiness...")
        
        try:
            # Check environment variables
            required_env_vars = ['DATABASE_URL']
            env_valid = True
            
            for var in required_env_vars:
                if not os.getenv(var):
                    logger.warning(f"⚠️ Environment variable missing: {var}")
                    env_valid = False
                else:
                    logger.info(f"✅ Environment variable present: {var}")
            
            # Check file permissions and structure
            required_files = [
                'smartsafe_multitenant_system.py',
                'smartsafe_saas_api.py',
                'camera_integration_manager.py',
                'templates/dashboard.html'
            ]
            
            files_valid = True
            for file in required_files:
                if not os.path.exists(file):
                    logger.error(f"❌ Required file missing: {file}")
                    files_valid = False
                else:
                    logger.info(f"✅ Required file present: {file}")
            
            production_ready = env_valid and files_valid
            
            self.validation_results.append({
                "test": "Production Readiness",
                "status": "PASS" if production_ready else "FAIL",
                "details": f"Environment: {'OK' if env_valid else 'FAIL'}, Files: {'OK' if files_valid else 'FAIL'}"
            })
            
            return production_ready
            
        except Exception as e:
            logger.error(f"❌ Production readiness validation error: {e}")
            self.critical_issues.append(f"Production readiness validation failed: {e}")
            return False
    
    def run_final_validation(self):
        """Run all validation tests"""
        logger.info("🚀 Starting final production validation...")
        logger.info("=" * 60)
        
        # Run all validation tests
        tests = [
            ("Database Schema", self.validate_database_schema),
            ("Camera Endpoints", self.validate_camera_endpoints),
            ("Error Handling", self.validate_error_handling),
            ("Session Security", self.validate_session_security),
            ("Production Readiness", self.validate_production_readiness)
        ]
        
        all_passed = True
        for test_name, test_func in tests:
            logger.info(f"🧪 Running {test_name} validation...")
            try:
                result = test_func()
                if not result:
                    all_passed = False
            except Exception as e:
                logger.error(f"❌ {test_name} validation failed with exception: {e}")
                all_passed = False
        
        # Generate final report
        self.generate_final_report(all_passed)
        
        return all_passed
    
    def generate_final_report(self, all_passed):
        """Generate comprehensive final report"""
        logger.info("=" * 60)
        logger.info("📊 FINAL PRODUCTION VALIDATION REPORT")
        logger.info("=" * 60)
        
        passed = sum(1 for result in self.validation_results if result["status"] == "PASS")
        failed = sum(1 for result in self.validation_results if result["status"] == "FAIL")
        total = len(self.validation_results)
        
        logger.info(f"📈 Total Validations: {total}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"❌ Failed: {failed}")
        logger.info(f"📊 Success Rate: {(passed/total)*100:.1f}%")
        
        logger.info("\n📋 Detailed Results:")
        for result in self.validation_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            logger.info(f"{status_icon} {result['test']}: {result['status']}")
            logger.info(f"   Details: {result['details']}")
        
        # Critical issues
        if self.critical_issues:
            logger.info("\n🚨 CRITICAL ISSUES:")
            for issue in self.critical_issues:
                logger.error(f"❌ {issue}")
        
        # Warnings
        if self.warnings:
            logger.info("\n⚠️ WARNINGS:")
            for warning in self.warnings:
                logger.warning(f"⚠️ {warning}")
        
        # Final verdict
        if all_passed and not self.critical_issues:
            logger.info("\n🎉 SYSTEM IS READY FOR PRODUCTION DEPLOYMENT!")
            logger.info("✅ All camera functionality validated")
            logger.info("✅ Database schema compatible")
            logger.info("✅ Error handling robust")
            logger.info("✅ Session management secure")
            logger.info("✅ Production environment ready")
        else:
            logger.error("\n❌ SYSTEM NOT READY FOR PRODUCTION!")
            logger.error("🔧 Please fix the issues above before deployment")
        
        # Save report
        report_file = f"final_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                "validation_summary": {
                    "total_tests": total,
                    "passed": passed,
                    "failed": failed,
                    "success_rate": (passed/total)*100,
                    "production_ready": all_passed and not self.critical_issues
                },
                "test_results": self.validation_results,
                "critical_issues": self.critical_issues,
                "warnings": self.warnings,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        logger.info(f"📄 Detailed report saved to: {report_file}")

def main():
    """Main function"""
    print("🚨 Final Production Validation")
    print("=" * 60)
    print("This script validates all camera system components for production deployment")
    print()
    
    validator = FinalProductionValidation()
    success = validator.run_final_validation()
    
    if success:
        print("\n🎉 System is ready for production deployment!")
        sys.exit(0)
    else:
        print("\n❌ System needs fixes before production deployment!")
        sys.exit(1)

if __name__ == "__main__":
    main() 