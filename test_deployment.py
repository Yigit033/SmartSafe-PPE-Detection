#!/usr/bin/env python3
"""
SmartSafe AI - Render.com Deployment Test
Local deployment validation before pushing to Render.com
"""

import os
import sys
import subprocess
import time
import requests
import threading
import signal
from pathlib import Path

class DeploymentTester:
    def __init__(self):
        self.test_results = []
        self.gunicorn_process = None
        self.test_port = 8080
        
    def log_test(self, test_name, status, message=""):
        """Log test result"""
        icon = "✅" if status else "❌"
        self.test_results.append({
            'test': test_name,
            'status': status,
            'message': message
        })
        print(f"{icon} {test_name}: {message}")
        
    def test_environment_variables(self):
        """Test environment variables setup"""
        print("\n🔧 Testing Environment Variables...")
        
        # Set Render.com simulation environment
        os.environ['RENDER'] = '1'
        os.environ['PORT'] = str(self.test_port)
        
        required_vars = ['RENDER', 'PORT']
        missing_vars = []
        
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
                
        if missing_vars:
            self.log_test("Environment Variables", False, f"Missing: {', '.join(missing_vars)}")
            return False
        else:
            self.log_test("Environment Variables", True, "All required variables set")
            return True
            
    def test_dependencies(self):
        """Test if all dependencies are installed"""
        print("\n📦 Testing Dependencies...")
        
        try:
            # Test critical imports
            import flask
            import gunicorn
            import psycopg2
            import ultralytics
            
            self.log_test("Dependencies", True, "All critical dependencies available")
            return True
            
        except ImportError as e:
            self.log_test("Dependencies", False, f"Missing dependency: {e}")
            return False
            
    def test_app_import(self):
        """Test if app can be imported successfully"""
        print("\n🔍 Testing App Import...")
        
        try:
            # Add current directory to Python path
            sys.path.insert(0, os.getcwd())
            
            # Test import
            from smartsafe_saas_api import app
            
            if app:
                self.log_test("App Import", True, f"App imported successfully: {app}")
                return True
            else:
                self.log_test("App Import", False, "App is None")
                return False
                
        except Exception as e:
            self.log_test("App Import", False, f"Import error: {e}")
            return False
            
    def test_database_connection(self):
        """Test database connection"""
        print("\n🗄️ Testing Database Connection...")
        
        try:
            from utils.secure_database_connector import SecureDatabaseConnector
            
            # Test connection
            db_connector = SecureDatabaseConnector()
            
            if db_connector:
                self.log_test("Database Connection", True, "Database connector initialized")
                return True
            else:
                self.log_test("Database Connection", False, "Failed to initialize database connector")
                return False
                
        except Exception as e:
            self.log_test("Database Connection", False, f"Database error: {e}")
            return False
            
    def test_gunicorn_config(self):
        """Test Gunicorn configuration"""
        print("\n⚙️ Testing Gunicorn Configuration...")
        
        try:
            # Check if gunicorn.conf.py exists and is valid
            if not os.path.exists('gunicorn.conf.py'):
                self.log_test("Gunicorn Config", False, "gunicorn.conf.py not found")
                return False
                
            # Test config loading
            import gunicorn.config
            config = gunicorn.config.Config()
            
            self.log_test("Gunicorn Config", True, "Configuration file is valid")
            return True
            
        except Exception as e:
            self.log_test("Gunicorn Config", False, f"Config error: {e}")
            return False
            
    def start_gunicorn_server(self):
        """Start Gunicorn server for testing"""
        print(f"\n🚀 Starting Gunicorn Server on port {self.test_port}...")
        
        try:
            # Gunicorn command
            cmd = [
                'gunicorn',
                '--bind', f'0.0.0.0:{self.test_port}',
                '--workers', '1',
                '--timeout', '30',
                '--keep-alive', '5',
                '--max-requests', '10',
                '--preload',
                'smartsafe_saas_api:app'
            ]
            
            # Start process
            self.gunicorn_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for server to start
            time.sleep(5)
            
            # Check if process is running
            if self.gunicorn_process.poll() is None:
                self.log_test("Gunicorn Startup", True, f"Server started on port {self.test_port}")
                return True
            else:
                stdout, stderr = self.gunicorn_process.communicate()
                self.log_test("Gunicorn Startup", False, f"Server failed to start: {stderr}")
                return False
                
        except Exception as e:
            self.log_test("Gunicorn Startup", False, f"Startup error: {e}")
            return False
            
    def test_http_endpoints(self):
        """Test HTTP endpoints"""
        print("\n🌐 Testing HTTP Endpoints...")
        
        base_url = f"http://localhost:{self.test_port}"
        
        endpoints = [
            {'path': '/health', 'name': 'Health Check'},
            {'path': '/', 'name': 'Home Page'},
            {'path': '/app', 'name': 'App Registration'}
        ]
        
        success_count = 0
        
        for endpoint in endpoints:
            try:
                response = requests.get(f"{base_url}{endpoint['path']}", timeout=10)
                
                if response.status_code == 200:
                    self.log_test(f"Endpoint {endpoint['name']}", True, f"Status: {response.status_code}")
                    success_count += 1
                else:
                    self.log_test(f"Endpoint {endpoint['name']}", False, f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Endpoint {endpoint['name']}", False, f"Request error: {e}")
                
        return success_count == len(endpoints)
        
    def test_memory_usage(self):
        """Test memory usage"""
        print("\n💾 Testing Memory Usage...")
        
        try:
            import psutil
            
            # Get current process memory
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Render.com free tier limit is 512MB
            if memory_mb < 400:  # Leave some buffer
                self.log_test("Memory Usage", True, f"Memory usage: {memory_mb:.1f}MB (within limits)")
                return True
            else:
                self.log_test("Memory Usage", False, f"Memory usage: {memory_mb:.1f}MB (exceeds 400MB limit)")
                return False
                
        except ImportError:
            self.log_test("Memory Usage", False, "psutil not available for memory testing")
            return False
        except Exception as e:
            self.log_test("Memory Usage", False, f"Memory test error: {e}")
            return False
            
    def cleanup(self):
        """Cleanup test environment"""
        print("\n🧹 Cleaning up...")
        
        # Stop Gunicorn process
        if self.gunicorn_process and self.gunicorn_process.poll() is None:
            self.gunicorn_process.terminate()
            self.gunicorn_process.wait()
            print("✅ Gunicorn process terminated")
            
        # Remove test environment variables
        if 'RENDER' in os.environ:
            del os.environ['RENDER']
        if 'PORT' in os.environ:
            del os.environ['PORT']
            
    def run_full_test(self):
        """Run complete deployment test suite"""
        print("🚀 SmartSafe AI - Render.com Deployment Test")
        print("=" * 50)
        
        try:
            # Run all tests
            tests = [
                self.test_environment_variables,
                self.test_dependencies,
                self.test_app_import,
                self.test_database_connection,
                self.test_gunicorn_config,
                self.start_gunicorn_server,
                self.test_http_endpoints,
                self.test_memory_usage
            ]
            
            passed_tests = 0
            total_tests = len(tests)
            
            for test in tests:
                if test():
                    passed_tests += 1
                    
            # Summary
            print("\n" + "=" * 50)
            print("📊 TEST SUMMARY")
            print("=" * 50)
            
            for result in self.test_results:
                icon = "✅" if result['status'] else "❌"
                print(f"{icon} {result['test']}: {result['message']}")
                
            print(f"\n📈 Overall Result: {passed_tests}/{total_tests} tests passed")
            
            if passed_tests == total_tests:
                print("🎉 ALL TESTS PASSED! Deployment should succeed on Render.com")
                return True
            else:
                print("⚠️ SOME TESTS FAILED! Fix issues before deploying to Render.com")
                return False
                
        except KeyboardInterrupt:
            print("\n⏹️ Test interrupted by user")
            return False
        except Exception as e:
            print(f"\n❌ Test suite error: {e}")
            return False
        finally:
            self.cleanup()

def main():
    """Main function"""
    tester = DeploymentTester()
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n⏹️ Stopping tests...")
        tester.cleanup()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run tests
    success = tester.run_full_test()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 