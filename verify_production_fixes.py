#!/usr/bin/env python3
"""
Production Fixes Verification Script
Verifies all production deployment fixes are in place
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class ProductionVerifier:
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.results = {
            'passed': [],
            'failed': [],
            'warnings': []
        }
    
    def print_header(self, text):
        print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
        print(f"{BOLD}{BLUE}{text}{RESET}")
        print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
    
    def print_success(self, text):
        print(f"{GREEN}✅ {text}{RESET}")
        self.results['passed'].append(text)
    
    def print_error(self, text):
        print(f"{RED}❌ {text}{RESET}")
        self.results['failed'].append(text)
    
    def print_warning(self, text):
        print(f"{YELLOW}⚠️  {text}{RESET}")
        self.results['warnings'].append(text)
    
    def check_file_exists(self, file_path, description):
        """Check if file exists"""
        full_path = self.root_dir / file_path
        if full_path.exists():
            self.print_success(f"{description} exists: {file_path}")
            return True
        else:
            self.print_error(f"{description} missing: {file_path}")
            return False
    
    def check_file_contains(self, file_path, search_text, description):
        """Check if file contains specific text"""
        full_path = self.root_dir / file_path
        if not full_path.exists():
            self.print_error(f"File not found: {file_path}")
            return False
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if search_text in content:
                    self.print_success(f"{description} found in {file_path}")
                    return True
                else:
                    self.print_error(f"{description} NOT found in {file_path}")
                    return False
        except Exception as e:
            self.print_error(f"Error reading {file_path}: {e}")
            return False
    
    def verify_new_files(self):
        """Verify new files were created"""
        self.print_header("1. NEW FILES VERIFICATION")
        
        files = [
            ('download_models.py', 'Model downloader script'),
            ('production_config.py', 'Production configuration'),
            ('PRODUCTION_FIX_SUMMARY.md', 'Production fix summary'),
            ('DEPLOYMENT_INSTRUCTIONS.md', 'Deployment instructions'),
            ('QUICK_REFERENCE.md', 'Quick reference guide'),
            ('TESTING_GUIDE.md', 'Testing guide'),
            ('verify_production_fixes.py', 'Verification script')
        ]
        
        for file_path, description in files:
            self.check_file_exists(file_path, description)
    
    def verify_model_loading_fixes(self):
        """Verify model loading fixes"""
        self.print_header("2. MODEL LOADING FIXES VERIFICATION")
        
        # Check download_models.py
        self.check_file_contains(
            'download_models.py',
            'def download_models',
            'download_models.py has download function'
        )
        
        # Check sh17_model_manager.py enhancements
        self.check_file_contains(
            'models/sh17_model_manager.py',
            'docker_model_paths',
            'sh17_model_manager.py has Docker path resolution'
        )
        
        self.check_file_contains(
            'models/sh17_model_manager.py',
            '/app/data/models',
            'sh17_model_manager.py checks /app/data/models'
        )
        
        # Check Dockerfile updates
        self.check_file_contains(
            'Dockerfile',
            'python download_models.py',
            'Dockerfile runs download_models.py'
        )
    
    def verify_database_fixes(self):
        """Verify database connection fixes"""
        self.print_header("3. DATABASE CONNECTION FIXES VERIFICATION")
        
        # Check database_adapter.py
        self.check_file_contains(
            'src/smartsafe/database/database_adapter.py',
            'def get_secure_db_connector',
            'database_adapter.py has get_secure_db_connector function'
        )
        
        self.check_file_contains(
            'src/smartsafe/database/database_adapter.py',
            'connection_pool',
            'database_adapter.py has connection pooling'
        )
        
        # Check secure_database_connector.py
        self.check_file_contains(
            'utils/secure_database_connector.py',
            'connection_timeout = 45',
            'secure_database_connector.py has 45s timeout'
        )
        
        self.check_file_contains(
            'utils/secure_database_connector.py',
            'max_retries = 5',
            'secure_database_connector.py has 5 retries'
        )
    
    def verify_deployment_fixes(self):
        """Verify deployment configuration fixes"""
        self.print_header("4. DEPLOYMENT CONFIGURATION FIXES VERIFICATION")
        
        # Check render.yaml
        self.check_file_contains(
            'render.yaml',
            'python -m src.smartsafe.api.smartsafe_saas_api',
            'render.yaml has correct startCommand'
        )
        
        self.check_file_contains(
            'render.yaml',
            'python download_models.py',
            'render.yaml runs model download'
        )
    
    def verify_error_handling(self):
        """Verify error handling improvements"""
        self.print_header("5. ERROR HANDLING VERIFICATION")
        
        # Check smartsafe_saas_api.py
        self.check_file_contains(
            'src/smartsafe/api/smartsafe_saas_api.py',
            '@app.route(\'/health\'',
            'smartsafe_saas_api.py has health check endpoint'
        )
        
        self.check_file_contains(
            'src/smartsafe/api/smartsafe_saas_api.py',
            '@self.app.errorhandler(500)',
            'smartsafe_saas_api.py has 500 error handler'
        )
        
        self.check_file_contains(
            'src/smartsafe/api/smartsafe_saas_api.py',
            '@self.app.errorhandler(502)',
            'smartsafe_saas_api.py has 502 error handler'
        )
        
        self.check_file_contains(
            'src/smartsafe/api/smartsafe_saas_api.py',
            '@self.app.errorhandler(Exception)',
            'smartsafe_saas_api.py has generic exception handler'
        )
    
    def verify_production_config(self):
        """Verify production configuration"""
        self.print_header("6. PRODUCTION CONFIGURATION VERIFICATION")
        
        self.check_file_contains(
            'production_config.py',
            'class ProductionConfig',
            'production_config.py has ProductionConfig class'
        )
        
        self.check_file_contains(
            'production_config.py',
            'MODEL_CACHE_ENABLED',
            'production_config.py has model cache setting'
        )
        
        self.check_file_contains(
            'production_config.py',
            'LAZY_LOADING_ENABLED',
            'production_config.py has lazy loading setting'
        )
    
    def verify_documentation(self):
        """Verify documentation is complete"""
        self.print_header("7. DOCUMENTATION VERIFICATION")
        
        docs = [
            ('PRODUCTION_FIX_SUMMARY.md', 'Production fix summary'),
            ('DEPLOYMENT_INSTRUCTIONS.md', 'Deployment instructions'),
            ('QUICK_REFERENCE.md', 'Quick reference'),
            ('TESTING_GUIDE.md', 'Testing guide')
        ]
        
        for file_path, description in docs:
            self.check_file_exists(file_path, description)
    
    def print_summary(self):
        """Print verification summary"""
        self.print_header("VERIFICATION SUMMARY")
        
        total_passed = len(self.results['passed'])
        total_failed = len(self.results['failed'])
        total_warnings = len(self.results['warnings'])
        total_tests = total_passed + total_failed
        
        print(f"{GREEN}✅ Passed: {total_passed}/{total_tests}{RESET}")
        if total_failed > 0:
            print(f"{RED}❌ Failed: {total_failed}/{total_tests}{RESET}")
        if total_warnings > 0:
            print(f"{YELLOW}⚠️  Warnings: {total_warnings}{RESET}")
        
        print(f"\n{BOLD}Overall Status:{RESET}")
        if total_failed == 0:
            print(f"{GREEN}{BOLD}✅ ALL CHECKS PASSED - READY FOR PRODUCTION{RESET}")
            return True
        else:
            print(f"{RED}{BOLD}❌ SOME CHECKS FAILED - REVIEW REQUIRED{RESET}")
            print(f"\n{BOLD}Failed Checks:{RESET}")
            for failure in self.results['failed']:
                print(f"  {RED}❌ {failure}{RESET}")
            return False
    
    def run_all_checks(self):
        """Run all verification checks"""
        print(f"\n{BOLD}{BLUE}SmartSafe AI - Production Deployment Verification{RESET}")
        print(f"{BLUE}Started: {datetime.now().isoformat()}{RESET}\n")
        
        self.verify_new_files()
        self.verify_model_loading_fixes()
        self.verify_database_fixes()
        self.verify_deployment_fixes()
        self.verify_error_handling()
        self.verify_production_config()
        self.verify_documentation()
        
        success = self.print_summary()
        
        print(f"\n{BLUE}Completed: {datetime.now().isoformat()}{RESET}\n")
        
        return success

def main():
    """Main entry point"""
    verifier = ProductionVerifier()
    success = verifier.run_all_checks()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
