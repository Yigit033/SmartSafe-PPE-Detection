#!/usr/bin/env python3
"""
PythonAnywhere Setup Script
Geçici çözüm - sonra Render.com'a geri döneceğiz
"""

import os
import sys

def setup_pythonanywhere():
    """PythonAnywhere için environment setup"""
    print("🐍 PythonAnywhere Setup - Temporary Solution")
    print("=" * 50)
    print("📝 NOT: Bu geçici çözüm - sonra Render.com'a geri döneceğiz")
    print("=" * 50)
    
    # PythonAnywhere environment variables
    os.environ['PYTHONANYWHERE_ENVIRONMENT'] = 'production'
    os.environ['FLASK_ENV'] = 'production'
    os.environ['PORT'] = '8080'
    
    # Database URL (Supabase)
    os.environ['DATABASE_URL'] = 'postgresql://postgres.nbxntohihcwruwlnthfb:6818.yigit.98@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require'
    
    print("✅ Environment variables set for PythonAnywhere")
    print("✅ Database URL configured (Supabase)")
    print("✅ Production mode enabled")
    
    return True

def test_app():
    """App'i test et"""
    print("\n🧪 Testing app import...")
    
    try:
        # Environment setup
        setup_pythonanywhere()
        
        # App import
        from smartsafe_saas_api import app
        
        print("✅ App imported successfully")
        print(f"✅ App name: {app.name}")
        print(f"✅ Environment: {app.config.get('ENV', 'development')}")
        print(f"✅ Debug mode: {app.config.get('DEBUG', False)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 PythonAnywhere Setup Test")
    
    if test_app():
        print("\n🎉 SUCCESS: Ready for PythonAnywhere deployment!")
        print("\n📋 Next Steps:")
        print("1. Go to pythonanywhere.com")
        print("2. Create free account")
        print("3. Upload your code")
        print("4. Create web app")
        print("5. Set environment variables")
        print("\n💡 Remember: This is temporary - we'll move to Render.com later!")
    else:
        print("\n❌ FAILED: Fix errors before deployment") 