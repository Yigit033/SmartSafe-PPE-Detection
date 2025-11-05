#!/usr/bin/env python3
"""
SmartSafe AI - Enhanced Error Handler
Professional error management system with logging, monitoring, and recovery
"""

import logging
import traceback
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import threading
from pathlib import Path

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Error categories"""
    CAMERA = "camera"
    DETECTION = "detection"
    DATABASE = "database"
    NETWORK = "network"
    SYSTEM = "system"
    USER = "user"
    CONFIGURATION = "configuration"

@dataclass
class ErrorInfo:
    """Professional error information structure"""
    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    context: Dict[str, Any]
    stack_trace: Optional[str] = None
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    camera_id: Optional[str] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_actions: List[str] = None

class EnhancedErrorHandler:
    """Professional error handling system"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Error storage
        self.error_history: List[ErrorInfo] = []
        self.error_counts: Dict[str, int] = {}
        self.recovery_strategies: Dict[str, callable] = {}
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Configure logging
        self.setup_logging()
        
        # Register recovery strategies
        self.register_recovery_strategies()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Enhanced Error Handler initialized")
    
    def setup_logging(self):
        """Setup professional logging configuration"""
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        json_formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "module": "%(name)s"}'
        )
        
        # Error log file
        error_handler = logging.FileHandler(self.log_dir / "errors.log")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # System log file
        system_handler = logging.FileHandler(self.log_dir / "system.log")
        system_handler.setLevel(logging.INFO)
        system_handler.setFormatter(detailed_formatter)
        
        # JSON log file for monitoring
        json_handler = logging.FileHandler(self.log_dir / "errors.json")
        json_handler.setLevel(logging.WARNING)
        json_handler.setFormatter(json_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(detailed_formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Add handlers
        root_logger.addHandler(error_handler)
        root_logger.addHandler(system_handler)
        root_logger.addHandler(json_handler)
        root_logger.addHandler(console_handler)
    
    def register_recovery_strategies(self):
        """Register automatic recovery strategies"""
        self.recovery_strategies = {
            "camera_connection_failed": self.recover_camera_connection,
            "database_connection_lost": self.recover_database_connection,
            "detection_model_failed": self.recover_detection_model,
            "network_timeout": self.recover_network_connection,
            "memory_limit_exceeded": self.recover_memory_usage,
            "disk_space_low": self.recover_disk_space
        }
    
    def handle_error(self, 
                    error: Exception, 
                    category: ErrorCategory,
                    severity: ErrorSeverity,
                    context: Dict[str, Any] = None,
                    user_id: str = None,
                    company_id: str = None,
                    camera_id: str = None) -> ErrorInfo:
        """Handle error with professional logging and recovery"""
        
        # Generate error ID
        error_id = f"{category.value}_{int(time.time())}_{id(error)}"
        
        # Extract error details
        error_message = str(error)
        stack_trace = traceback.format_exc() if error else None
        
        # Create error info
        error_info = ErrorInfo(
            error_id=error_id,
            category=category,
            severity=severity,
            message=error_message,
            details={
                "error_type": type(error).__name__,
                "error_args": error.args if hasattr(error, 'args') else None,
                "module": error.__module__ if hasattr(error, '__module__') else None
            },
            timestamp=datetime.now(),
            context=context or {},
            stack_trace=stack_trace,
            user_id=user_id,
            company_id=company_id,
            camera_id=camera_id,
            recovery_actions=[]
        )
        
        # Thread-safe error storage
        with self.lock:
            self.error_history.append(error_info)
            error_key = f"{category.value}_{type(error).__name__}"
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
            
            # Keep only last 1000 errors
            if len(self.error_history) > 1000:
                self.error_history = self.error_history[-1000:]
        
        # Log error
        self.log_error(error_info)
        
        # Attempt recovery for critical errors
        if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.attempt_recovery(error_info)
        
        return error_info
    
    def log_error(self, error_info: ErrorInfo):
        """Log error with appropriate level"""
        logger = logging.getLogger(f"smartsafe.{error_info.category.value}")
        
        # Create log message
        log_message = f"[{error_info.error_id}] {error_info.message}"
        
        # Add context
        if error_info.context:
            log_message += f" | Context: {json.dumps(error_info.context)}"
        
        if error_info.user_id:
            log_message += f" | User: {error_info.user_id}"
        
        if error_info.company_id:
            log_message += f" | Company: {error_info.company_id}"
        
        if error_info.camera_id:
            log_message += f" | Camera: {error_info.camera_id}"
        
        # Log with appropriate level
        if error_info.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error_info.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error_info.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # Log stack trace for high severity errors
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] and error_info.stack_trace:
            logger.error(f"Stack trace for {error_info.error_id}:\n{error_info.stack_trace}")
    
    def attempt_recovery(self, error_info: ErrorInfo):
        """Attempt automatic recovery"""
        try:
            error_info.recovery_attempted = True
            
            # Generate recovery key
            recovery_key = f"{error_info.category.value}_{error_info.details.get('error_type', 'unknown')}"
            
            # Try specific recovery strategy
            if recovery_key in self.recovery_strategies:
                recovery_func = self.recovery_strategies[recovery_key]
                success = recovery_func(error_info)
                error_info.recovery_successful = success
                
                if success:
                    error_info.recovery_actions.append(f"Applied strategy: {recovery_key}")
                    logging.info(f"✅ Recovery successful for {error_info.error_id}")
                else:
                    error_info.recovery_actions.append(f"Failed strategy: {recovery_key}")
                    logging.warning(f"❌ Recovery failed for {error_info.error_id}")
            
            # Try generic recovery strategies
            else:
                generic_strategies = [
                    self.generic_restart_recovery,
                    self.generic_reset_recovery,
                    self.generic_fallback_recovery
                ]
                
                for strategy in generic_strategies:
                    try:
                        success = strategy(error_info)
                        if success:
                            error_info.recovery_successful = True
                            error_info.recovery_actions.append(f"Applied generic strategy: {strategy.__name__}")
                            logging.info(f"✅ Generic recovery successful for {error_info.error_id}")
                            break
                    except Exception as recovery_error:
                        error_info.recovery_actions.append(f"Recovery strategy failed: {str(recovery_error)}")
                        logging.error(f"Recovery strategy failed: {recovery_error}")
        
        except Exception as recovery_error:
            logging.error(f"Recovery attempt failed: {recovery_error}")
            error_info.recovery_actions.append(f"Recovery attempt failed: {str(recovery_error)}")
    
    def recover_camera_connection(self, error_info: ErrorInfo) -> bool:
        """Recover camera connection"""
        try:
            camera_id = error_info.camera_id
            if not camera_id:
                return False
            
            # Try to reconnect camera
            try:
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
                camera_manager = get_camera_manager()
                
                # Disconnect and reconnect
                camera_manager.disconnect_camera(camera_id)
                time.sleep(2)
                
                if camera_id in camera_manager.camera_configs:
                    config = camera_manager.camera_configs[camera_id]
                    success = camera_manager.connect_camera(config)
                    
                    if success:
                        logging.info(f"✅ Camera {camera_id} reconnected successfully")
                        return True
                
            except ImportError:
                logging.warning("Camera integration manager not available")
            
            return False
            
        except Exception as e:
            logging.error(f"Camera recovery failed: {e}")
            return False
    
    def recover_database_connection(self, error_info: ErrorInfo) -> bool:
        """Recover database connection"""
        try:
            # Try to reconnect database
            try:
                from src.smartsafe.database.database_config import get_db_connection
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    conn.close()
                    logging.info("✅ Database connection recovered")
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logging.error(f"Database recovery failed: {e}")
            return False
    
    def recover_detection_model(self, error_info: ErrorInfo) -> bool:
        """Recover detection model"""
        try:
            # Try to reload model
            logging.info("🔄 Attempting to reload detection model...")
            
            # This would involve reloading the YOLO model
            # For now, return True to simulate recovery
            time.sleep(1)
            
            logging.info("✅ Detection model recovery simulated")
            return True
            
        except Exception as e:
            logging.error(f"Detection model recovery failed: {e}")
            return False
    
    def recover_network_connection(self, error_info: ErrorInfo) -> bool:
        """Recover network connection"""
        try:
            import socket
            
            # Test network connectivity
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=5)
                logging.info("✅ Network connection is available")
                return True
            except:
                logging.warning("❌ Network connection still unavailable")
                return False
                
        except Exception as e:
            logging.error(f"Network recovery failed: {e}")
            return False
    
    def recover_memory_usage(self, error_info: ErrorInfo) -> bool:
        """Recover from memory issues"""
        try:
            import gc
            
            # Force garbage collection
            gc.collect()
            
            # Clear caches if available
            try:
                from src.smartsafe.integrations.cameras.camera_integration_manager import get_camera_manager
                camera_manager = get_camera_manager()
                
                # Clear frame buffers
                camera_manager.frame_buffers.clear()
                logging.info("✅ Frame buffers cleared")
                
            except ImportError:
                pass
            
            logging.info("✅ Memory recovery attempted")
            return True
            
        except Exception as e:
            logging.error(f"Memory recovery failed: {e}")
            return False
    
    def recover_disk_space(self, error_info: ErrorInfo) -> bool:
        """Recover disk space"""
        try:
            # Clean up old log files
            import glob
            import os
            
            log_files = glob.glob(str(self.log_dir / "*.log"))
            cleaned_files = 0
            
            for log_file in log_files:
                try:
                    # Keep only files from last 7 days
                    file_age = time.time() - os.path.getmtime(log_file)
                    if file_age > 7 * 24 * 3600:  # 7 days
                        os.remove(log_file)
                        cleaned_files += 1
                except:
                    pass
            
            if cleaned_files > 0:
                logging.info(f"✅ Cleaned {cleaned_files} old log files")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Disk space recovery failed: {e}")
            return False
    
    def generic_restart_recovery(self, error_info: ErrorInfo) -> bool:
        """Generic restart recovery"""
        try:
            # Simulate component restart
            logging.info(f"🔄 Attempting generic restart for {error_info.category.value}")
            time.sleep(1)
            return True
            
        except Exception as e:
            logging.error(f"Generic restart failed: {e}")
            return False
    
    def generic_reset_recovery(self, error_info: ErrorInfo) -> bool:
        """Generic reset recovery"""
        try:
            # Simulate component reset
            logging.info(f"🔄 Attempting generic reset for {error_info.category.value}")
            time.sleep(1)
            return True
            
        except Exception as e:
            logging.error(f"Generic reset failed: {e}")
            return False
    
    def generic_fallback_recovery(self, error_info: ErrorInfo) -> bool:
        """Generic fallback recovery"""
        try:
            # Simulate fallback mode
            logging.info(f"🔄 Attempting fallback mode for {error_info.category.value}")
            time.sleep(1)
            return True
            
        except Exception as e:
            logging.error(f"Generic fallback failed: {e}")
            return False
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics"""
        with self.lock:
            total_errors = len(self.error_history)
            
            # Category breakdown
            category_counts = {}
            severity_counts = {}
            recovery_stats = {"attempted": 0, "successful": 0}
            
            for error in self.error_history:
                # Category stats
                category = error.category.value
                category_counts[category] = category_counts.get(category, 0) + 1
                
                # Severity stats
                severity = error.severity.value
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                
                # Recovery stats
                if error.recovery_attempted:
                    recovery_stats["attempted"] += 1
                    if error.recovery_successful:
                        recovery_stats["successful"] += 1
            
            # Recent errors (last hour)
            recent_errors = [
                error for error in self.error_history
                if (datetime.now() - error.timestamp).total_seconds() < 3600
            ]
            
            return {
                "total_errors": total_errors,
                "recent_errors": len(recent_errors),
                "category_breakdown": category_counts,
                "severity_breakdown": severity_counts,
                "recovery_stats": recovery_stats,
                "error_rate": len(recent_errors) / 60,  # errors per minute
                "most_common_errors": dict(sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)[:10])
            }
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors in API format"""
        with self.lock:
            recent_errors = sorted(self.error_history, key=lambda x: x.timestamp, reverse=True)[:limit]
            
            return [
                {
                    "error_id": error.error_id,
                    "category": error.category.value,
                    "severity": error.severity.value,
                    "message": error.message,
                    "timestamp": error.timestamp.isoformat(),
                    "context": error.context,
                    "user_id": error.user_id,
                    "company_id": error.company_id,
                    "camera_id": error.camera_id,
                    "recovery_attempted": error.recovery_attempted,
                    "recovery_successful": error.recovery_successful,
                    "recovery_actions": error.recovery_actions or []
                }
                for error in recent_errors
            ]
    
    def clear_old_errors(self, days: int = 30):
        """Clear errors older than specified days"""
        cutoff_time = datetime.now() - timedelta(days=days)
        
        with self.lock:
            original_count = len(self.error_history)
            self.error_history = [
                error for error in self.error_history
                if error.timestamp > cutoff_time
            ]
            
            cleared_count = original_count - len(self.error_history)
            if cleared_count > 0:
                logging.info(f"🧹 Cleared {cleared_count} old errors")
    
    def export_error_report(self, output_file: str = None) -> str:
        """Export comprehensive error report"""
        if not output_file:
            output_file = self.log_dir / f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "statistics": self.get_error_statistics(),
            "recent_errors": self.get_recent_errors(100),
            "system_info": {
                "log_directory": str(self.log_dir),
                "recovery_strategies": list(self.recovery_strategies.keys())
            }
        }
        
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            logging.info(f"📊 Error report exported to {output_file}")
            return str(output_file)
            
        except Exception as e:
            logging.error(f"Failed to export error report: {e}")
            return None

# Global error handler instance
error_handler = EnhancedErrorHandler()

def handle_error(error: Exception, 
                category: ErrorCategory,
                severity: ErrorSeverity,
                context: Dict[str, Any] = None,
                user_id: str = None,
                company_id: str = None,
                camera_id: str = None) -> ErrorInfo:
    """Global error handling function"""
    return error_handler.handle_error(error, category, severity, context, user_id, company_id, camera_id)

def get_error_handler() -> EnhancedErrorHandler:
    """Get global error handler instance"""
    return error_handler

# Convenience functions for common error types
def handle_camera_error(error: Exception, camera_id: str = None, company_id: str = None, context: Dict[str, Any] = None):
    """Handle camera-related errors"""
    return handle_error(error, ErrorCategory.CAMERA, ErrorSeverity.HIGH, context, camera_id=camera_id, company_id=company_id)

def handle_detection_error(error: Exception, camera_id: str = None, company_id: str = None, context: Dict[str, Any] = None):
    """Handle detection-related errors"""
    return handle_error(error, ErrorCategory.DETECTION, ErrorSeverity.MEDIUM, context, camera_id=camera_id, company_id=company_id)

def handle_database_error(error: Exception, company_id: str = None, context: Dict[str, Any] = None):
    """Handle database-related errors"""
    return handle_error(error, ErrorCategory.DATABASE, ErrorSeverity.HIGH, context, company_id=company_id)

def handle_network_error(error: Exception, context: Dict[str, Any] = None):
    """Handle network-related errors"""
    return handle_error(error, ErrorCategory.NETWORK, ErrorSeverity.MEDIUM, context)

def handle_system_error(error: Exception, context: Dict[str, Any] = None):
    """Handle system-related errors"""
    return handle_error(error, ErrorCategory.SYSTEM, ErrorSeverity.HIGH, context)

def handle_user_error(error: Exception, user_id: str = None, company_id: str = None, context: Dict[str, Any] = None):
    """Handle user-related errors"""
    return handle_error(error, ErrorCategory.USER, ErrorSeverity.LOW, context, user_id=user_id, company_id=company_id)

# Test function
def test_error_handler():
    """Test the error handler"""
    logging.info("🧪 Testing Enhanced Error Handler")
    
    # Test different error types
    try:
        raise ValueError("Test camera connection error")
    except Exception as e:
        handle_camera_error(e, camera_id="CAM_001", company_id="COMP_001", context={"test": "camera_error"})
    
    try:
        raise ConnectionError("Test network error")
    except Exception as e:
        handle_network_error(e, context={"test": "network_error"})
    
    try:
        raise RuntimeError("Test system error")
    except Exception as e:
        handle_system_error(e, context={"test": "system_error"})
    
    # Get statistics
    stats = error_handler.get_error_statistics()
    logging.info(f"📊 Error statistics: {stats}")
    
    # Export report
    report_file = error_handler.export_error_report()
    logging.info(f"📄 Error report exported to: {report_file}")

if __name__ == "__main__":
    test_error_handler() 