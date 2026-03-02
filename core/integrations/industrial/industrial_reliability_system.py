#!/usr/bin/env python3
"""
Industrial 24/7 Reliability System
Ensures continuous operation with auto-restart, health monitoring, and failover
"""

import sys
import os
import time
import logging
import psutil
import threading
import subprocess
import json
import yaml
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import requests
from typing import Dict, List, Optional, Any
import schedule
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import socket
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/reliability_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class IndustrialReliabilitySystem:
    """24/7 Industrial Reliability System"""
    
    def __init__(self, config_path: str = "configs/industrial_config.yaml"):
        self.config_path = config_path
        self.config = self.load_config()
        self.running = False
        self.start_time = datetime.now()
        
        # System monitoring
        self.system_processes = {}
        self.health_checks = {
            'cpu_usage': 0,
            'memory_usage': 0,
            'disk_usage': 0,
            'gpu_temperature': 0,
            'system_uptime': 0
        }
        
        # Alert system
        self.alert_history = []
        self.last_alert_times = {}
        
        # Database
        self.db_path = "logs/reliability_system.db"
        self.init_database()
        
        # Process monitoring
        self.critical_processes = [
            'industrial_multi_camera_system.py',
            'industrial_api_server.py'
        ]
        
        logger.info("🔧 Industrial Reliability System initialized")
    
    def load_config(self) -> dict:
        """Load configuration"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return yaml.safe_load(f)
            return self.get_default_config()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> dict:
        """Get default reliability configuration"""
        return {
            'health_monitoring': {
                'enabled': True,
                'check_interval': 10,
                'thresholds': {
                    'cpu_usage': 90,
                    'memory_usage': 85,
                    'disk_usage': 80,
                    'temperature': 70
                },
                'auto_restart': {
                    'enabled': True,
                    'conditions': [
                        'cpu_usage > 95 for 300 seconds',
                        'memory_usage > 95 for 300 seconds',
                        'no_cameras_active for 60 seconds'
                    ]
                }
            },
            'alerts': {
                'enabled': True,
                'email': {
                    'enabled': False,
                    'smtp_server': 'smtp.gmail.com',
                    'port': 587,
                    'username': 'alerts@company.com',
                    'password': 'your_password',
                    'recipients': ['admin@company.com']
                }
            }
        }
    
    def init_database(self):
        """Initialize reliability database"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # System health table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_usage REAL,
                    memory_usage REAL,
                    disk_usage REAL,
                    gpu_temperature REAL,
                    system_uptime REAL,
                    active_processes INTEGER,
                    status TEXT
                )
            ''')
            
            # Restart events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS restart_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT,
                    reason TEXT,
                    process_name TEXT,
                    success BOOLEAN
                )
            ''')
            
            # Alert history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alert_type TEXT,
                    severity TEXT,
                    message TEXT,
                    resolved BOOLEAN DEFAULT FALSE
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Reliability database initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def check_system_health(self) -> Dict[str, Any]:
        """Comprehensive system health check"""
        try:
            # CPU usage
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            
            # GPU temperature (if available)
            gpu_temp = 0
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_temp = gpus[0].temperature
            except:
                pass
            
            # System uptime
            boot_time = psutil.boot_time()
            uptime = time.time() - boot_time
            
            # Active processes
            active_processes = len([p for p in psutil.process_iter() 
                                   if any(proc in p.name() for proc in self.critical_processes)])
            
            # Overall health status
            status = "healthy"
            if cpu_usage > 90 or memory_usage > 85 or disk_usage > 80:
                status = "warning"
            if cpu_usage > 95 or memory_usage > 95:
                status = "critical"
            
            health_data = {
                'timestamp': datetime.now(),
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'gpu_temperature': gpu_temp,
                'system_uptime': uptime,
                'active_processes': active_processes,
                'status': status
            }
            
            # Store in database
            self.store_health_data(health_data)
            
            return health_data
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'timestamp': datetime.now(),
                'cpu_usage': 0,
                'memory_usage': 0,
                'disk_usage': 0,
                'gpu_temperature': 0,
                'system_uptime': 0,
                'active_processes': 0,
                'status': 'error'
            }
    
    def store_health_data(self, health_data: Dict[str, Any]):
        """Store health data in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO system_health 
                (timestamp, cpu_usage, memory_usage, disk_usage, gpu_temperature, system_uptime, active_processes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                health_data['timestamp'],
                health_data['cpu_usage'],
                health_data['memory_usage'],
                health_data['disk_usage'],
                health_data['gpu_temperature'],
                health_data['system_uptime'],
                health_data['active_processes'],
                health_data['status']
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store health data: {e}")
    
    def check_critical_processes(self) -> List[str]:
        """Check if critical processes are running"""
        missing_processes = []
        
        for process_name in self.critical_processes:
            found = False
            for proc in psutil.process_iter():
                try:
                    if process_name in proc.name() or process_name in ' '.join(proc.cmdline()):
                        found = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not found:
                missing_processes.append(process_name)
        
        return missing_processes
    
    def restart_process(self, process_name: str) -> bool:
        """Restart a critical process"""
        try:
            logger.info(f"🔄 Restarting process: {process_name}")
            
            # Kill existing process if running
            self.kill_process(process_name)
            
            # Wait a moment
            time.sleep(2)
            
            # Start new process
            if process_name.endswith('.py'):
                # Python script
                cmd = [sys.executable, process_name]
            else:
                # System command
                cmd = [process_name]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.getcwd()
            )
            
            # Store process reference
            self.system_processes[process_name] = process
            
            # Log restart event
            self.log_restart_event(process_name, "auto_restart", "Process restarted successfully", True)
            
            logger.info(f"✅ Process restarted successfully: {process_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to restart process {process_name}: {e}")
            self.log_restart_event(process_name, "auto_restart", f"Restart failed: {e}", False)
            return False
    
    def kill_process(self, process_name: str):
        """Kill a process by name"""
        try:
            for proc in psutil.process_iter():
                try:
                    if process_name in proc.name() or process_name in ' '.join(proc.cmdline()):
                        proc.terminate()
                        proc.wait(timeout=5)
                        logger.info(f"🔴 Terminated process: {process_name}")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue
        except Exception as e:
            logger.error(f"Failed to kill process {process_name}: {e}")
    
    def log_restart_event(self, process_name: str, event_type: str, reason: str, success: bool):
        """Log restart event to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO restart_events (timestamp, event_type, reason, process_name, success)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now(), event_type, reason, process_name, success))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log restart event: {e}")
    
    def send_alert(self, alert_type: str, severity: str, message: str):
        """Send alert notification"""
        try:
            # Rate limiting - don't send same alert too frequently
            current_time = datetime.now()
            last_alert_key = f"{alert_type}_{severity}"
            
            if last_alert_key in self.last_alert_times:
                time_diff = (current_time - self.last_alert_times[last_alert_key]).total_seconds()
                if time_diff < 300:  # 5 minutes
                    return
            
            self.last_alert_times[last_alert_key] = current_time
            
            # Log alert
            logger.warning(f"🚨 ALERT [{severity}] {alert_type}: {message}")
            
            # Store in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alert_history (timestamp, alert_type, severity, message)
                VALUES (?, ?, ?, ?)
            ''', (current_time, alert_type, severity, message))
            conn.commit()
            conn.close()
            
            # Send email if configured
            if self.config.get('alerts', {}).get('email', {}).get('enabled', False):
                self.send_email_alert(alert_type, severity, message)
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def send_email_alert(self, alert_type: str, severity: str, message: str):
        """Send email alert"""
        try:
            email_config = self.config['alerts']['email']
            
            msg = MIMEMultipart()
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = f"[{severity}] Industrial PPE System Alert: {alert_type}"
            
            body = f"""
            Industrial PPE Detection System Alert
            
            Alert Type: {alert_type}
            Severity: {severity}
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Message:
            {message}
            
            System Information:
            - Uptime: {(datetime.now() - self.start_time).total_seconds() / 3600:.1f} hours
            - CPU Usage: {self.health_checks.get('cpu_usage', 0):.1f}%
            - Memory Usage: {self.health_checks.get('memory_usage', 0):.1f}%
            
            Please check the system immediately.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(email_config['smtp_server'], email_config['port'])
            server.starttls()
            server.login(email_config['username'], email_config['password'])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"📧 Email alert sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def auto_restart_system(self):
        """Auto-restart system if needed"""
        try:
            health = self.check_system_health()
            
            # Check thresholds
            thresholds = self.config['health_monitoring']['thresholds']
            
            restart_needed = False
            restart_reason = ""
            
            # Critical CPU usage
            if health['cpu_usage'] > 95:
                restart_needed = True
                restart_reason = f"Critical CPU usage: {health['cpu_usage']:.1f}%"
            
            # Critical memory usage
            elif health['memory_usage'] > 95:
                restart_needed = True
                restart_reason = f"Critical memory usage: {health['memory_usage']:.1f}%"
            
            # No active processes
            elif health['active_processes'] == 0:
                restart_needed = True
                restart_reason = "No critical processes active"
            
            if restart_needed:
                logger.warning(f"⚠️ Auto-restart triggered: {restart_reason}")
                self.send_alert("AUTO_RESTART", "HIGH", restart_reason)
                
                # Restart critical processes
                for process_name in self.critical_processes:
                    self.restart_process(process_name)
                
                # Wait and verify
                time.sleep(10)
                new_health = self.check_system_health()
                
                if new_health['active_processes'] > 0:
                    logger.info("✅ Auto-restart successful")
                    self.send_alert("AUTO_RESTART", "INFO", "System restarted successfully")
                else:
                    logger.error("❌ Auto-restart failed")
                    self.send_alert("AUTO_RESTART", "CRITICAL", "Auto-restart failed - manual intervention required")
            
        except Exception as e:
            logger.error(f"Auto-restart system error: {e}")
    
    def monitor_network_connectivity(self):
        """Monitor network connectivity"""
        try:
            # Test internet connectivity
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            
            # Test API server connectivity
            try:
                response = requests.get("http://localhost:8080/", timeout=5)
                if response.status_code != 200:
                    self.send_alert("API_SERVER", "WARNING", "API server not responding correctly")
            except:
                self.send_alert("API_SERVER", "WARNING", "API server not accessible")
                
        except socket.error:
            self.send_alert("NETWORK", "WARNING", "Network connectivity issues detected")
    
    def cleanup_old_data(self):
        """Clean up old data from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Keep only last 30 days of health data
            cursor.execute('''
                DELETE FROM system_health 
                WHERE timestamp < datetime('now', '-30 days')
            ''')
            
            # Keep only last 90 days of restart events
            cursor.execute('''
                DELETE FROM restart_events 
                WHERE timestamp < datetime('now', '-90 days')
            ''')
            
            # Keep only last 90 days of alerts
            cursor.execute('''
                DELETE FROM alert_history 
                WHERE timestamp < datetime('now', '-90 days')
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info("🧹 Database cleanup completed")
            
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")
    
    def start_monitoring(self):
        """Start 24/7 monitoring"""
        self.running = True
        logger.info("🔍 24/7 Reliability monitoring started")
        
        # Schedule regular tasks
        schedule.every(10).seconds.do(self.check_system_health)
        schedule.every(30).seconds.do(self.auto_restart_system)
        schedule.every(5).minutes.do(self.monitor_network_connectivity)
        schedule.every().day.at("03:00").do(self.cleanup_old_data)
        
        # Initial system check
        self.send_alert("SYSTEM_START", "INFO", "Industrial Reliability System started")
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
            self.running = False
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        self.send_alert("SYSTEM_STOP", "INFO", "Industrial Reliability System stopped")
        logger.info("🛑 24/7 Reliability monitoring stopped")
    
    def get_system_report(self) -> Dict[str, Any]:
        """Get comprehensive system report"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Recent health data
            cursor.execute('''
                SELECT * FROM system_health 
                ORDER BY timestamp DESC LIMIT 10
            ''')
            recent_health = cursor.fetchall()
            
            # Recent restart events
            cursor.execute('''
                SELECT * FROM restart_events 
                ORDER BY timestamp DESC LIMIT 10
            ''')
            recent_restarts = cursor.fetchall()
            
            # Recent alerts
            cursor.execute('''
                SELECT * FROM alert_history 
                ORDER BY timestamp DESC LIMIT 10
            ''')
            recent_alerts = cursor.fetchall()
            
            conn.close()
            
            return {
                'system_uptime': (datetime.now() - self.start_time).total_seconds() / 3600,
                'current_health': self.health_checks,
                'recent_health': recent_health,
                'recent_restarts': recent_restarts,
                'recent_alerts': recent_alerts,
                'critical_processes': self.critical_processes,
                'missing_processes': self.check_critical_processes()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate system report: {e}")
            return {}

def main():
    """Main function"""
    print("🔧 INDUSTRIAL 24/7 RELIABILITY SYSTEM")
    print("=" * 50)
    print("✅ Continuous system monitoring")
    print("✅ Auto-restart capabilities")
    print("✅ Health check automation")
    print("✅ Alert notifications")
    print("✅ Process failover management")
    print("=" * 50)
    
    # Handle shutdown gracefully
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal")
        reliability_system.stop_monitoring()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize reliability system
        reliability_system = IndustrialReliabilitySystem()
        
        # Start monitoring
        reliability_system.start_monitoring()
        
    except Exception as e:
        logger.error(f"❌ Reliability system error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 