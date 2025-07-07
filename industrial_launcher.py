#!/usr/bin/env python3
"""
Industrial PPE Detection System Launcher
Coordinates all industrial systems: Multi-camera, API, Reliability
"""

import sys
import time
import logging
import subprocess
import threading
import signal
import os
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/industrial_launcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

class IndustrialSystemLauncher:
    """Industrial System Launcher"""
    
    def __init__(self):
        self.running = False
        self.start_time = datetime.now()
        self.processes = {}
        self.system_components = {
            'multi_camera': 'industrial_multi_camera_system.py',
            'api_server': 'industrial_api_server.py',
            'reliability': 'industrial_reliability_system.py'
        }
        
        # Create logs directory
        Path("logs").mkdir(exist_ok=True)
        
        logger.info("🚀 Industrial System Launcher initialized")
    
    def start_component(self, component_name, script_path):
        """Start a system component"""
        try:
            logger.info(f"🔧 Starting {component_name}: {script_path}")
            
            # Start process
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            self.processes[component_name] = process
            logger.info(f"✅ {component_name} started successfully (PID: {process.pid})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start {component_name}: {e}")
            return False
    
    def stop_component(self, component_name):
        """Stop a system component"""
        if component_name in self.processes:
            try:
                process = self.processes[component_name]
                process.terminate()
                process.wait(timeout=10)
                
                logger.info(f"🛑 {component_name} stopped successfully")
                del self.processes[component_name]
                
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ Force killing {component_name}")
                process.kill()
                del self.processes[component_name]
            except Exception as e:
                logger.error(f"❌ Error stopping {component_name}: {e}")
    
    def check_component_health(self, component_name):
        """Check if component is healthy"""
        if component_name in self.processes:
            process = self.processes[component_name]
            return process.poll() is None
        return False
    
    def restart_component(self, component_name):
        """Restart a system component"""
        logger.info(f"🔄 Restarting {component_name}")
        
        # Stop component
        self.stop_component(component_name)
        
        # Wait a moment
        time.sleep(2)
        
        # Start component
        script_path = self.system_components[component_name]
        return self.start_component(component_name, script_path)
    
    def start_all_systems(self):
        """Start all industrial systems"""
        logger.info("🏭 Starting All Industrial Systems")
        print("🏭 INDUSTRIAL PPE DETECTION SYSTEM LAUNCHER")
        print("=" * 60)
        
        # Start systems in order
        startup_order = ['multi_camera', 'api_server', 'reliability']
        
        for component_name in startup_order:
            script_path = self.system_components[component_name]
            
            if os.path.exists(script_path):
                success = self.start_component(component_name, script_path)
                if success:
                    print(f"✅ {component_name.replace('_', ' ').title()} System: STARTED")
                else:
                    print(f"❌ {component_name.replace('_', ' ').title()} System: FAILED")
                    
                # Wait between starts
                time.sleep(3)
            else:
                logger.warning(f"⚠️ Script not found: {script_path}")
                print(f"⚠️ {component_name.replace('_', ' ').title()} System: SCRIPT NOT FOUND")
        
        print("=" * 60)
        logger.info("✅ All systems startup sequence completed")
    
    def stop_all_systems(self):
        """Stop all industrial systems"""
        logger.info("🛑 Stopping All Industrial Systems")
        print("\n🛑 STOPPING ALL INDUSTRIAL SYSTEMS")
        print("=" * 60)
        
        # Stop systems in reverse order
        shutdown_order = ['reliability', 'api_server', 'multi_camera']
        
        for component_name in shutdown_order:
            if component_name in self.processes:
                self.stop_component(component_name)
                print(f"🛑 {component_name.replace('_', ' ').title()} System: STOPPED")
            else:
                print(f"⚪ {component_name.replace('_', ' ').title()} System: NOT RUNNING")
        
        print("=" * 60)
        logger.info("✅ All systems shutdown sequence completed")
    
    def monitor_systems(self):
        """Monitor all systems and restart if needed"""
        logger.info("🔍 Starting system monitoring")
        
        while self.running:
            try:
                # Check health of all components
                for component_name in self.system_components.keys():
                    if not self.check_component_health(component_name):
                        logger.warning(f"⚠️ {component_name} appears to be down")
                        
                        # Restart component if it was supposed to be running
                        if component_name in self.processes:
                            logger.info(f"🔄 Auto-restarting {component_name}")
                            self.restart_component(component_name)
                
                # Wait before next check
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                time.sleep(10)
    
    def get_system_status(self):
        """Get comprehensive system status"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
            'components': {}
        }
        
        for component_name in self.system_components.keys():
            is_running = self.check_component_health(component_name)
            process_info = None
            
            if component_name in self.processes:
                process = self.processes[component_name]
                process_info = {
                    'pid': process.pid,
                    'return_code': process.poll()
                }
            
            status['components'][component_name] = {
                'running': is_running,
                'process_info': process_info
            }
        
        return status
    
    def start_launcher(self):
        """Start the industrial launcher"""
        self.running = True
        
        # Handle shutdown signals
        def signal_handler(signum, frame):
            logger.info("🛑 Shutdown signal received")
            self.running = False
            self.stop_all_systems()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Start all systems
            self.start_all_systems()
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self.monitor_systems,
                name="SystemMonitor",
                daemon=True
            )
            monitor_thread.start()
            
            # Main loop - display status
            print("\n📊 SYSTEM STATUS MONITOR")
            print("Press Ctrl+C to stop all systems")
            print("=" * 60)
            
            while self.running:
                try:
                    status = self.get_system_status()
                    
                    # Clear screen
                    os.system('cls' if os.name == 'nt' else 'clear')
                    
                    print(f"🏭 INDUSTRIAL PPE DETECTION SYSTEM")
                    print(f"⏰ Uptime: {status['uptime_hours']:.1f} hours")
                    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print("=" * 60)
                    
                    for component_name, component_status in status['components'].items():
                        status_icon = "🟢" if component_status['running'] else "🔴"
                        component_display = component_name.replace('_', ' ').title()
                        
                        print(f"{status_icon} {component_display} System")
                        
                        if component_status['process_info']:
                            pid = component_status['process_info']['pid']
                            print(f"   📍 PID: {pid}")
                        
                        if component_status['running']:
                            print(f"   ✅ Status: RUNNING")
                        else:
                            print(f"   ❌ Status: STOPPED")
                        
                        print()
                    
                    print("=" * 60)
                    print("🔍 System monitoring active")
                    print("⌨️  Press Ctrl+C to stop all systems")
                    
                    time.sleep(5)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Status display error: {e}")
                    time.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ Launcher error: {e}")
        finally:
            self.running = False
            self.stop_all_systems()

def main():
    """Main function"""
    print("🚀 INDUSTRIAL PPE DETECTION SYSTEM LAUNCHER")
    print("=" * 60)
    print("This launcher will start and monitor all industrial systems:")
    print("• Multi-Camera Detection System")
    print("• Industrial API Server")
    print("• 24/7 Reliability System")
    print("=" * 60)
    
    try:
        launcher = IndustrialSystemLauncher()
        launcher.start_launcher()
        
    except Exception as e:
        logger.error(f"❌ Critical launcher error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 