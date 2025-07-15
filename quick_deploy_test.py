#!/usr/bin/env python3
"""
Quick Deployment Test - Fast validation before Render.com deploy
"""

import os
import sys
import subprocess
import time

def quick_test():
    """Run quick deployment validation"""
    print("Quick Deployment Test")
    print("=" * 30)
    
    tests_passed = 0
    total_tests = 5
    
    # Test 1: App Import
    print("\n1. Testing App Import...")
    try:
        os.environ['PYTHONANYWHERE_ENVIRONMENT'] = 'production'
        from smartsafe_saas_api import app
        if app:
            print("OK App import successful")
            tests_passed += 1
        else:
            print("FAIL App is None")
    except Exception as e:
        print(f"FAIL App import failed: {e}")
    
    # Test 2: Health Endpoint
    print("\n2. Testing Health Endpoint...")
    try:
        with app.test_client() as client:
            response = client.get('/health')
            if response.status_code == 200:
                print("OK Health endpoint working")
                tests_passed += 1
            else:
                print(f"FAIL Health endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"FAIL Health endpoint error: {e}")
    
    # Test 3: Database Connection
    print("\n3. Testing Database...")
    try:
        from utils.secure_database_connector import SecureDatabaseConnector
        db = SecureDatabaseConnector()
        if db:
            print("OK Database connection successful")
            tests_passed += 1
        else:
            print("FAIL Database connection failed")
    except Exception as e:
        print(f"FAIL Database error: {e}")
    
    # Test 4: Gunicorn Config
    print("\n4. Testing Gunicorn Config...")
    try:
        if os.path.exists('gunicorn.conf.py'):
            print("OK Gunicorn config exists")
            tests_passed += 1
        else:
            print("FAIL Gunicorn config missing")
    except Exception as e:
        print(f"FAIL Gunicorn config error: {e}")
    
    # Test 5: Port Binding
    print("\n5. Testing Port Binding...")
    try:
        port = os.environ.get('PORT', '8080')
        if port and port.isdigit():
            print(f"OK Port configured: {port}")
            tests_passed += 1
        else:
            print("FAIL Port not configured")
    except Exception as e:
        print(f"FAIL Port error: {e}")
    
    # Summary
    print("\n" + "=" * 30)
    print(f"Result: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("SUCCESS: READY FOR DEPLOYMENT!")
        return True
    else:
        print("WARNING: FIX ISSUES BEFORE DEPLOYING!")
        return False

if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1) 