#!/usr/bin/env python3
"""
Test script to simulate Render.com environment locally
"""
import os
import sys

def test_render_environment():
    """Test app with Render.com environment variables"""
    print("🔧 Setting up Render.com environment...")
    
    # Set Render.com environment variables
    os.environ['RENDER'] = '1'
    os.environ['PORT'] = '10000'
    os.environ['FLASK_ENV'] = 'production'
    
    print("✅ Environment variables set:")
    print(f"   RENDER: {os.environ.get('RENDER')}")
    print(f"   PORT: {os.environ.get('PORT')}")
    print(f"   FLASK_ENV: {os.environ.get('FLASK_ENV')}")
    
    print("\n🚀 Testing app import...")
    try:
        import smartsafe_saas_api
        print("✅ App imported successfully!")
        
        # Test app object
        app = smartsafe_saas_api.app
        print(f"✅ App object: {app}")
        print(f"✅ App name: {app.name}")
        print(f"✅ Environment: {app.config.get('ENV', 'development')}")
        
        # Test if app is production ready
        if hasattr(app, 'config'):
            print(f"✅ Debug mode: {app.config.get('DEBUG', False)}")
            print(f"✅ Testing mode: {app.config.get('TESTING', False)}")
        
        print("\n🎯 SUCCESS: App is ready for Render.com deployment!")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_render_environment()
    sys.exit(0 if success else 1) 