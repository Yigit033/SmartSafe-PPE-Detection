#!/usr/bin/env python3
"""
SmartSafe AI - Automated Database Monitoring
PRODUCTION-READY CONTINUOUS DATABASE HEALTH CHECK
"""

import sqlite3
import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import hashlib
import smtplib
from email.mime.text import MIMEText

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMonitor:
    """Production database monitoring system"""
    
    def __init__(self):
        self.db_path = "smartsafe_saas.db"
        self.backup_path = "smartsafe_saas_backup.db"
        self.log_file = "logs/database_monitor.log"
        self.alert_threshold = 60  # seconds
        self.last_backup_hash = None
        self.last_check_time = None
        
    def check_database_health(self) -> Dict:
        """Comprehensive database health check"""
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "database_exists": os.path.exists(self.db_path),
            "database_size": 0,
            "database_hash": "",
            "companies_count": 0,
            "users_count": 0,
            "last_activity": None,
            "status": "unknown",
            "errors": []
        }
        
        try:
            if not health_report["database_exists"]:
                health_report["errors"].append("Database file not found")
                health_report["status"] = "critical"
                return health_report
            
            # File size check
            health_report["database_size"] = os.path.getsize(self.db_path)
            
            # Hash calculation
            with open(self.db_path, 'rb') as f:
                health_report["database_hash"] = hashlib.md5(f.read()).hexdigest()
            
            # Database content check
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            if 'companies' not in tables:
                health_report["errors"].append("Companies table missing")
                health_report["status"] = "critical"
                conn.close()
                return health_report
            
            # Count records
            cursor.execute("SELECT COUNT(*) FROM companies")
            health_report["companies_count"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            health_report["users_count"] = cursor.fetchone()[0]
            
            # Check last activity
            cursor.execute("SELECT MAX(created_at) FROM companies")
            health_report["last_activity"] = cursor.fetchone()[0]
            
            conn.close()
            
            # Health status assessment
            if health_report["companies_count"] == 0:
                health_report["status"] = "warning"
                health_report["errors"].append("No companies found")
            elif health_report["database_size"] < 1000:
                health_report["status"] = "warning"
                health_report["errors"].append("Database size too small")
            else:
                health_report["status"] = "healthy"
            
        except Exception as e:
            health_report["errors"].append(f"Database check failed: {str(e)}")
            health_report["status"] = "critical"
        
        return health_report
    
    def create_backup(self) -> bool:
        """Create database backup"""
        try:
            if os.path.exists(self.db_path):
                # Create timestamped backup
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"smartsafe_backup_{timestamp}.db"
                backup_path = os.path.join("backups", backup_name)
                
                os.makedirs("backups", exist_ok=True)
                
                import shutil
                shutil.copy2(self.db_path, backup_path)
                shutil.copy2(self.db_path, self.backup_path)
                
                logger.info(f"✅ Backup created: {backup_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            return False
    
    def monitor_changes(self) -> bool:
        """Monitor database changes"""
        try:
            current_hash = None
            if os.path.exists(self.db_path):
                with open(self.db_path, 'rb') as f:
                    current_hash = hashlib.md5(f.read()).hexdigest()
            
            if self.last_backup_hash is None:
                self.last_backup_hash = current_hash
                return True
            
            if current_hash != self.last_backup_hash:
                logger.info("🔄 Database changed - Creating backup")
                self.create_backup()
                self.last_backup_hash = current_hash
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Change monitoring failed: {e}")
            return False
    
    def log_health_report(self, report: Dict):
        """Log health report to file"""
        try:
            os.makedirs("logs", exist_ok=True)
            
            with open(self.log_file, 'a') as f:
                f.write(f"{report['timestamp']}: {report['status']} - ")
                f.write(f"Companies: {report['companies_count']}, ")
                f.write(f"Size: {report['database_size']} bytes\n")
                
                if report['errors']:
                    f.write(f"  Errors: {', '.join(report['errors'])}\n")
                
        except Exception as e:
            logger.error(f"❌ Logging failed: {e}")
    
    def run_monitoring(self, interval: int = 300):
        """Run continuous monitoring"""
        logger.info(f"🚀 Database monitoring started (interval: {interval}s)")
        
        while True:
            try:
                # Health check
                health = self.check_database_health()
                
                # Log results
                self.log_health_report(health)
                
                # Status reporting
                if health["status"] == "healthy":
                    logger.info(f"✅ Database healthy - {health['companies_count']} companies")
                elif health["status"] == "warning":
                    logger.warning(f"⚠️  Database warning: {', '.join(health['errors'])}")
                else:
                    logger.error(f"❌ Database critical: {', '.join(health['errors'])}")
                
                # Monitor changes
                self.monitor_changes()
                
                # Wait for next check
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                time.sleep(30)  # Wait before retrying

def main():
    """Main monitoring function"""
    print("🔍 SMARTSAFE AI - DATABASE MONITOR")
    print("=" * 50)
    
    monitor = DatabaseMonitor()
    
    # Single health check
    health = monitor.check_database_health()
    
    print(f"🏥 Database Health Status: {health['status'].upper()}")
    print(f"📊 Companies: {health['companies_count']}")
    print(f"👥 Users: {health['users_count']}")
    print(f"💾 Size: {health['database_size']} bytes")
    print(f"🔐 Hash: {health['database_hash'][:16]}...")
    
    if health['errors']:
        print(f"❌ Errors: {', '.join(health['errors'])}")
    
    print("\n💡 For continuous monitoring, use: python scripts/database_monitor.py --continuous")
    
    return health['status'] != 'critical'

if __name__ == "__main__":
    import sys
    
    if "--continuous" in sys.argv:
        monitor = DatabaseMonitor()
        monitor.run_monitoring()
    else:
        success = main()
        exit(0 if success else 1) 