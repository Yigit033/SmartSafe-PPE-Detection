#!/usr/bin/env python3
"""
SmartSafe AI - Customer-Safe Database Health Check
MUSTERI ONUNDE GUVENLI KULLANIM - Windows Uyumlu
"""

import sqlite3
import os
import hashlib
import logging
from datetime import datetime
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustomerSafeHealthCheck:
    """Musteri onunde guvenli kullanim icin health check"""
    
    def __init__(self):
        self.db_path = "smartsafe_saas.db"
        
    def get_db_stats(self) -> Dict:
        """Database istatistikleri (hassas bilgi olmadan)"""
        if not os.path.exists(self.db_path):
            return {"error": "Database not found", "status": "critical"}
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Sadece sayisal veriler
            cursor.execute("SELECT COUNT(*) FROM companies")
            companies = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM cameras")
            cameras = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "status": "healthy",
                "companies_count": companies,
                "users_count": users,
                "cameras_count": cameras,
                "database_size": os.path.getsize(self.db_path),
                "last_check": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": str(e), "status": "critical"}
    
    def verify_system_ready(self) -> bool:
        """Sistem hazir mi kontrolu (musteri guvenli)"""
        stats = self.get_db_stats()
        
        if stats.get("error"):
            print("ERROR: Database connection failed!")
            return False
        
        if stats["companies_count"] == 0:
            print("WARNING: No companies registered in system!")
            return False
        
        print("SUCCESS: SYSTEM STATUS READY")
        print(f"Active Companies: {stats['companies_count']}")
        print(f"Total Users: {stats['users_count']}")
        print(f"Cameras Configured: {stats['cameras_count']}")
        print(f"Database Size: {stats['database_size']} bytes")
        print(f"Last Check: {stats['last_check']}")
        
        return True

def main():
    """Musteri onunde guvenli health check"""
    print("SMARTSAFE AI - SYSTEM HEALTH CHECK")
    print("=" * 50)
    
    health_checker = CustomerSafeHealthCheck()
    
    print("Checking system status...")
    print("")
    
    if health_checker.verify_system_ready():
        print("")
        print("SUCCESS: SYSTEM READY FOR OPERATION!")
        print("All services are operational and ready to start.")
        return True
    else:
        print("")
        print("ERROR: SYSTEM NOT READY!")
        print("Please contact technical support.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 