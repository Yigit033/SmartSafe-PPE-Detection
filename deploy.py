#!/usr/bin/env python3
"""
SmartSafe AI - Deployment Automation Script
Automated testing and deployment to Render.com
"""

import os
import sys
import subprocess
import time
import argparse

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} successful")
            return True
        else:
            print(f"❌ {description} failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} error: {e}")
        return False

def run_quick_test():
    """Run quick deployment test"""
    print("\n🧪 Running Quick Deployment Test...")
    return run_command("python quick_deploy_test.py", "Quick deployment test")

def run_full_test():
    """Run full deployment test"""
    print("\n🧪 Running Full Deployment Test...")
    return run_command("python test_deployment.py", "Full deployment test")

def git_status():
    """Check git status"""
    print("\n📊 Checking Git Status...")
    return run_command("git status --porcelain", "Git status check")

def git_add_commit_push(message):
    """Git add, commit and push"""
    print(f"\n📤 Deploying to GitHub with message: '{message}'...")
    
    steps = [
        ("git add .", "Add files to staging"),
        (f'git commit -m "{message}"', "Commit changes"),
        ("git push origin main", "Push to GitHub")
    ]
    
    for cmd, desc in steps:
        if not run_command(cmd, desc):
            return False
    
    return True

def check_render_deployment():
    """Check if Render.com deployment is ready"""
    print("\n🚀 Render.com Deployment Tips:")
    print("=" * 40)
    print("1. 🔍 Check Render.com dashboard for deployment status")
    print("2. 📊 Monitor deployment logs in real-time")
    print("3. ⏱️ Deployment typically takes 3-5 minutes")
    print("4. 🌐 Test endpoints after deployment completes")
    print("5. 🔄 If deployment fails, check logs and re-run this script")
    print("=" * 40)

def main():
    """Main deployment function"""
    parser = argparse.ArgumentParser(description='SmartSafe AI Deployment Script')
    parser.add_argument('--quick', action='store_true', help='Run quick test only')
    parser.add_argument('--full', action='store_true', help='Run full test only')
    parser.add_argument('--deploy', action='store_true', help='Deploy to Render.com')
    parser.add_argument('--message', '-m', default='Auto deployment', help='Commit message')
    
    args = parser.parse_args()
    
    print("🚀 SmartSafe AI - Deployment Automation")
    print("=" * 50)
    
    # Quick test
    if args.quick or not (args.full or args.deploy):
        if not run_quick_test():
            print("❌ Quick test failed! Fix issues before deployment.")
            return False
    
    # Full test
    if args.full:
        if not run_full_test():
            print("❌ Full test failed! Fix issues before deployment.")
            return False
    
    # Deploy
    if args.deploy:
        print("\n🚀 Starting Deployment Process...")
        
        # Run quick test first
        if not run_quick_test():
            print("❌ Pre-deployment test failed! Aborting deployment.")
            return False
        
        # Git operations
        if not git_add_commit_push(args.message):
            print("❌ Git operations failed! Aborting deployment.")
            return False
        
        # Deployment tips
        check_render_deployment()
        
        print("\n🎉 Deployment initiated successfully!")
        print("📌 Check Render.com dashboard for deployment status")
        return True
    
    print("\n✅ All tests completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 