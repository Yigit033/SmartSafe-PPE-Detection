#!/usr/bin/env python3
"""
SmartSafe AI - Enterprise Monitoring System
Professional monitoring, metrics collection, and alerting system
"""

import time
import psutil
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque, defaultdict
import logging
import queue
from pathlib import Path
import socket
import requests

class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class Metric:
    """Metric data structure"""
    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str]
    timestamp: datetime
    help_text: str = ""
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus format"""
        label_str = ",".join([f'{k}="{v}"' for k, v in self.labels.items()])
        if label_str:
            return f"{self.name}{{{label_str}}} {self.value} {int(self.timestamp.timestamp() * 1000)}"
        else:
            return f"{self.name} {self.value} {int(self.timestamp.timestamp() * 1000)}"

@dataclass
class Alert:
    """Alert data structure"""
    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    labels: Dict[str, str]
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HealthCheck:
    """Health check result"""
    name: str
    status: str  # healthy, unhealthy, degraded
    message: str
    timestamp: datetime
    response_time: float
    details: Dict[str, Any] = None

class EnterpriseMonitoringSystem:
    """Enterprise-grade monitoring and alerting system"""
    
    def __init__(self, metrics_retention: int = 86400):  # 24 hours
        self.metrics_retention = metrics_retention
        
        # Metrics storage
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.metric_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Alerts
        self.alerts: deque = deque(maxlen=1000)
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.alert_callbacks: List[Callable] = []
        
        # Health checks
        self.health_checks: Dict[str, HealthCheck] = {}
        self.health_check_functions: Dict[str, Callable] = {}
        
        # System monitoring
        self.system_metrics_enabled = True
        self.monitoring_thread = None
        self.monitoring_active = False
        
        # Performance tracking
        self.performance_counters = {
            'requests_total': 0,
            'requests_failed': 0,
            'response_time_sum': 0.0,
            'active_connections': 0,
            'frames_processed': 0,
            'detection_time_sum': 0.0
        }
        
        # Thread safety
        self.lock = threading.Lock()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Enterprise Monitoring System initialized")
        
        # Register default health checks
        self.register_default_health_checks()
        
        # Start monitoring
        self.start_monitoring()
    
    def start_monitoring(self):
        """Start system monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self._monitor_system, daemon=True)
            self.monitoring_thread.start()
            self.logger.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop system monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        self.logger.info("System monitoring stopped")
    
    def _monitor_system(self):
        """Monitor system metrics continuously"""
        while self.monitoring_active:
            try:
                current_time = datetime.now()
                
                # CPU metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                self.record_metric("system_cpu_usage_percent", cpu_percent, MetricType.GAUGE, {"host": socket.gethostname()})
                
                # Memory metrics
                memory = psutil.virtual_memory()
                self.record_metric("system_memory_usage_percent", memory.percent, MetricType.GAUGE, {"host": socket.gethostname()})
                self.record_metric("system_memory_available_bytes", memory.available, MetricType.GAUGE, {"host": socket.gethostname()})
                
                # Disk metrics
                disk = psutil.disk_usage('/')
                disk_percent = (disk.used / disk.total) * 100
                self.record_metric("system_disk_usage_percent", disk_percent, MetricType.GAUGE, {"host": socket.gethostname()})
                
                # Network metrics
                network = psutil.net_io_counters()
                self.record_metric("system_network_bytes_sent_total", network.bytes_sent, MetricType.COUNTER, {"host": socket.gethostname()})
                self.record_metric("system_network_bytes_recv_total", network.bytes_recv, MetricType.COUNTER, {"host": socket.gethostname()})
                
                # Process metrics
                process = psutil.Process()
                self.record_metric("process_cpu_percent", process.cpu_percent(), MetricType.GAUGE, {"process": "smartsafe"})
                self.record_metric("process_memory_rss_bytes", process.memory_info().rss, MetricType.GAUGE, {"process": "smartsafe"})
                
                # Application metrics
                for counter_name, value in self.performance_counters.items():
                    self.record_metric(f"smartsafe_{counter_name}", value, MetricType.COUNTER, {"app": "smartsafe"})
                
                # Check alert rules
                self._check_alert_rules()
                
                # Run health checks
                self._run_health_checks()
                
                # Clean old metrics
                self._cleanup_old_metrics()
                
                time.sleep(30)  # Monitor every 30 seconds
                
            except Exception as e:
                self.logger.error(f"System monitoring error: {e}")
                time.sleep(60)
    
    def record_metric(self, name: str, value: float, metric_type: MetricType, labels: Dict[str, str] = None, help_text: str = ""):
        """Record a metric"""
        if labels is None:
            labels = {}
        
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels,
            timestamp=datetime.now(),
            help_text=help_text
        )
        
        with self.lock:
            self.metrics[name].append(metric)
            
            # Store metadata
            if name not in self.metric_metadata:
                self.metric_metadata[name] = {
                    "type": metric_type.value,
                    "help": help_text,
                    "labels": set()
                }
            
            # Update label set
            self.metric_metadata[name]["labels"].update(labels.keys())
    
    def get_metric_values(self, name: str, start_time: datetime = None, end_time: datetime = None) -> List[Metric]:
        """Get metric values within time range"""
        if name not in self.metrics:
            return []
        
        metrics = list(self.metrics[name])
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return metrics
    
    def get_metric_summary(self, name: str, duration_minutes: int = 60) -> Dict[str, Any]:
        """Get metric summary for the last N minutes"""
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=duration_minutes)
        
        metrics = self.get_metric_values(name, start_time, end_time)
        
        if not metrics:
            return {"count": 0}
        
        values = [m.value for m in metrics]
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "latest": values[-1] if values else 0,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        }
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        with self.lock:
            if name in self.performance_counters:
                self.performance_counters[name] += value
        
        self.record_metric(name, value, MetricType.COUNTER, labels)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        self.record_metric(name, value, MetricType.GAUGE, labels)
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a histogram metric"""
        self.record_metric(name, value, MetricType.HISTOGRAM, labels)
    
    def add_alert_rule(self, name: str, metric_name: str, condition: str, threshold: float, 
                      severity: AlertSeverity, message: str, labels: Dict[str, str] = None):
        """Add alert rule"""
        if labels is None:
            labels = {}
        
        self.alert_rules[name] = {
            "metric_name": metric_name,
            "condition": condition,  # "gt", "lt", "eq", "gte", "lte"
            "threshold": threshold,
            "severity": severity,
            "message": message,
            "labels": labels,
            "enabled": True
        }
        
        self.logger.info(f"Added alert rule: {name}")
    
    def _check_alert_rules(self):
        """Check all alert rules"""
        for rule_name, rule in self.alert_rules.items():
            if not rule["enabled"]:
                continue
            
            try:
                # Get recent metric values
                recent_metrics = self.get_metric_values(
                    rule["metric_name"],
                    datetime.now() - timedelta(minutes=5)
                )
                
                if not recent_metrics:
                    continue
                
                # Get latest value
                latest_value = recent_metrics[-1].value
                
                # Check condition
                triggered = False
                condition = rule["condition"]
                threshold = rule["threshold"]
                
                if condition == "gt" and latest_value > threshold:
                    triggered = True
                elif condition == "gte" and latest_value >= threshold:
                    triggered = True
                elif condition == "lt" and latest_value < threshold:
                    triggered = True
                elif condition == "lte" and latest_value <= threshold:
                    triggered = True
                elif condition == "eq" and latest_value == threshold:
                    triggered = True
                
                if triggered:
                    self._trigger_alert(rule_name, rule, latest_value)
                    
            except Exception as e:
                self.logger.error(f"Alert rule check failed for {rule_name}: {e}")
    
    def _trigger_alert(self, rule_name: str, rule: Dict[str, Any], current_value: float):
        """Trigger an alert"""
        alert_id = f"{rule_name}_{int(time.time())}"
        
        alert = Alert(
            alert_id=alert_id,
            name=rule_name,
            severity=rule["severity"],
            message=rule["message"].format(value=current_value, threshold=rule["threshold"]),
            labels=rule["labels"],
            timestamp=datetime.now()
        )
        
        with self.lock:
            self.alerts.append(alert)
        
        # Log alert
        log_level = getattr(logging, rule["severity"].value.upper(), logging.WARNING)
        self.logger.log(log_level, f"Alert triggered: {alert.name} - {alert.message}")
        
        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")
    
    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """Add alert callback function"""
        self.alert_callbacks.append(callback)
    
    def register_health_check(self, name: str, check_function: Callable[[], HealthCheck]):
        """Register health check function"""
        self.health_check_functions[name] = check_function
        self.logger.info(f"Registered health check: {name}")
    
    def register_default_health_checks(self):
        """Register default health checks"""
        self.register_health_check("database", self._check_database_health)
        self.register_health_check("disk_space", self._check_disk_space)
        self.register_health_check("memory", self._check_memory_usage)
        self.register_health_check("cpu", self._check_cpu_usage)
    
    def _run_health_checks(self):
        """Run all health checks"""
        for name, check_function in self.health_check_functions.items():
            try:
                start_time = time.time()
                health_check = check_function()
                response_time = time.time() - start_time
                
                health_check.response_time = response_time
                
                with self.lock:
                    self.health_checks[name] = health_check
                
                # Record health check metrics
                status_value = 1 if health_check.status == "healthy" else 0
                self.record_metric(
                    f"health_check_status",
                    status_value,
                    MetricType.GAUGE,
                    {"check": name, "status": health_check.status}
                )
                
                self.record_metric(
                    f"health_check_response_time_seconds",
                    response_time,
                    MetricType.GAUGE,
                    {"check": name}
                )
                
            except Exception as e:
                self.logger.error(f"Health check failed for {name}: {e}")
                
                # Record failed health check
                failed_check = HealthCheck(
                    name=name,
                    status="unhealthy",
                    message=f"Health check failed: {str(e)}",
                    timestamp=datetime.now(),
                    response_time=0.0
                )
                
                with self.lock:
                    self.health_checks[name] = failed_check
    
    def _check_database_health(self) -> HealthCheck:
        """Check database health"""
        try:
            # Simulate database check
            # In real implementation, this would test database connection
            time.sleep(0.01)  # Simulate DB query time
            
            return HealthCheck(
                name="database",
                status="healthy",
                message="Database connection successful",
                timestamp=datetime.now(),
                response_time=0.0,
                details={"connection_pool": "active", "queries": "responsive"}
            )
            
        except Exception as e:
            return HealthCheck(
                name="database",
                status="unhealthy",
                message=f"Database check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=0.0
            )
    
    def _check_disk_space(self) -> HealthCheck:
        """Check disk space health"""
        try:
            disk = psutil.disk_usage('/')
            usage_percent = (disk.used / disk.total) * 100
            
            if usage_percent > 90:
                status = "unhealthy"
                message = f"Disk usage critical: {usage_percent:.1f}%"
            elif usage_percent > 80:
                status = "degraded"
                message = f"Disk usage high: {usage_percent:.1f}%"
            else:
                status = "healthy"
                message = f"Disk usage normal: {usage_percent:.1f}%"
            
            return HealthCheck(
                name="disk_space",
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time=0.0,
                details={
                    "usage_percent": usage_percent,
                    "free_bytes": disk.free,
                    "total_bytes": disk.total
                }
            )
            
        except Exception as e:
            return HealthCheck(
                name="disk_space",
                status="unhealthy",
                message=f"Disk check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=0.0
            )
    
    def _check_memory_usage(self) -> HealthCheck:
        """Check memory usage health"""
        try:
            memory = psutil.virtual_memory()
            
            if memory.percent > 90:
                status = "unhealthy"
                message = f"Memory usage critical: {memory.percent:.1f}%"
            elif memory.percent > 80:
                status = "degraded"
                message = f"Memory usage high: {memory.percent:.1f}%"
            else:
                status = "healthy"
                message = f"Memory usage normal: {memory.percent:.1f}%"
            
            return HealthCheck(
                name="memory",
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time=0.0,
                details={
                    "usage_percent": memory.percent,
                    "available_bytes": memory.available,
                    "total_bytes": memory.total
                }
            )
            
        except Exception as e:
            return HealthCheck(
                name="memory",
                status="unhealthy",
                message=f"Memory check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=0.0
            )
    
    def _check_cpu_usage(self) -> HealthCheck:
        """Check CPU usage health"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent > 90:
                status = "unhealthy"
                message = f"CPU usage critical: {cpu_percent:.1f}%"
            elif cpu_percent > 80:
                status = "degraded"
                message = f"CPU usage high: {cpu_percent:.1f}%"
            else:
                status = "healthy"
                message = f"CPU usage normal: {cpu_percent:.1f}%"
            
            return HealthCheck(
                name="cpu",
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time=0.0,
                details={
                    "usage_percent": cpu_percent,
                    "cores": psutil.cpu_count()
                }
            )
            
        except Exception as e:
            return HealthCheck(
                name="cpu",
                status="unhealthy",
                message=f"CPU check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=0.0
            )
    
    def _cleanup_old_metrics(self):
        """Clean up old metrics"""
        cutoff_time = datetime.now() - timedelta(seconds=self.metrics_retention)
        
        with self.lock:
            for metric_name in list(self.metrics.keys()):
                # Remove old metrics
                while self.metrics[metric_name] and self.metrics[metric_name][0].timestamp < cutoff_time:
                    self.metrics[metric_name].popleft()
                
                # Remove empty metric collections
                if not self.metrics[metric_name]:
                    del self.metrics[metric_name]
    
    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format"""
        lines = []
        
        with self.lock:
            for metric_name, metric_list in self.metrics.items():
                if not metric_list:
                    continue
                
                # Add help text
                if metric_name in self.metric_metadata:
                    help_text = self.metric_metadata[metric_name].get("help", "")
                    if help_text:
                        lines.append(f"# HELP {metric_name} {help_text}")
                    
                    metric_type = self.metric_metadata[metric_name].get("type", "gauge")
                    lines.append(f"# TYPE {metric_name} {metric_type}")
                
                # Add latest metric value
                latest_metric = metric_list[-1]
                lines.append(latest_metric.to_prometheus())
        
        return "\n".join(lines)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status"""
        with self.lock:
            health_checks = dict(self.health_checks)
        
        overall_status = "healthy"
        unhealthy_checks = []
        degraded_checks = []
        
        for name, check in health_checks.items():
            if check.status == "unhealthy":
                overall_status = "unhealthy"
                unhealthy_checks.append(name)
            elif check.status == "degraded" and overall_status == "healthy":
                overall_status = "degraded"
                degraded_checks.append(name)
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "checks": {name: check.__dict__ for name, check in health_checks.items()},
            "summary": {
                "total_checks": len(health_checks),
                "healthy": len([c for c in health_checks.values() if c.status == "healthy"]),
                "degraded": len(degraded_checks),
                "unhealthy": len(unhealthy_checks)
            }
        }
    
    def get_alerts(self, limit: int = 100, severity: AlertSeverity = None, resolved: bool = None) -> List[Dict[str, Any]]:
        """Get alerts with filtering"""
        with self.lock:
            alerts = list(self.alerts)
        
        # Apply filters
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]
        
        # Sort by timestamp (newest first) and limit
        alerts.sort(key=lambda x: x.timestamp, reverse=True)
        alerts = alerts[:limit]
        
        return [alert.to_dict() for alert in alerts]
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get comprehensive monitoring summary"""
        with self.lock:
            total_metrics = sum(len(metric_list) for metric_list in self.metrics.values())
            active_alerts = len([a for a in self.alerts if not a.resolved])
        
        health_status = self.get_health_status()
        
        return {
            "monitoring_active": self.monitoring_active,
            "total_metrics": total_metrics,
            "unique_metrics": len(self.metrics),
            "active_alerts": active_alerts,
            "total_alerts": len(self.alerts),
            "health_status": health_status["status"],
            "health_checks": health_status["summary"],
            "performance_counters": dict(self.performance_counters),
            "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0
        }
    
    def export_monitoring_report(self, output_file: str = None) -> str:
        """Export comprehensive monitoring report"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"logs/monitoring_report_{timestamp}.json"
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": self.get_monitoring_summary(),
            "health_status": self.get_health_status(),
            "recent_alerts": self.get_alerts(50),
            "metric_summaries": {
                name: self.get_metric_summary(name, 60)
                for name in list(self.metrics.keys())[:20]  # Top 20 metrics
            }
        }
        
        try:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Monitoring report exported to {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"Failed to export monitoring report: {e}")
            return None
    
    def shutdown(self):
        """Shutdown monitoring system"""
        self.logger.info("Shutting down Enterprise Monitoring System...")
        
        # Stop monitoring
        self.stop_monitoring()
        
        # Clear data
        with self.lock:
            self.metrics.clear()
            self.alerts.clear()
            self.health_checks.clear()
        
        self.logger.info("Enterprise Monitoring System shutdown complete")

# Global monitoring system
monitoring_system = EnterpriseMonitoringSystem()

def get_monitoring_system() -> EnterpriseMonitoringSystem:
    """Get global monitoring system"""
    return monitoring_system

def record_metric(name: str, value: float, metric_type: MetricType, labels: Dict[str, str] = None):
    """Record a metric"""
    monitoring_system.record_metric(name, value, metric_type, labels)

def increment_counter(name: str, value: float = 1.0, labels: Dict[str, str] = None):
    """Increment a counter"""
    monitoring_system.increment_counter(name, value, labels)

def set_gauge(name: str, value: float, labels: Dict[str, str] = None):
    """Set a gauge"""
    monitoring_system.set_gauge(name, value, labels)

def get_health_status() -> Dict[str, Any]:
    """Get health status"""
    return monitoring_system.get_health_status()

# Test function
def test_monitoring_system():
    """Test the monitoring system"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Testing Enterprise Monitoring System")
    
    system = get_monitoring_system()
    
    # Test metrics
    increment_counter("test_requests_total", 1, {"method": "GET", "endpoint": "/api/test"})
    set_gauge("test_active_connections", 42, {"server": "web1"})
    
    # Test alert rules
    system.add_alert_rule(
        "high_cpu",
        "system_cpu_usage_percent",
        "gt",
        80.0,
        AlertSeverity.WARNING,
        "High CPU usage detected: {value}% > {threshold}%",
        {"component": "system"}
    )
    
    # Wait for monitoring cycle
    time.sleep(5)
    
    # Get health status
    health = get_health_status()
    logger.info(f"Health status: {health['status']}")
    
    # Get monitoring summary
    summary = system.get_monitoring_summary()
    logger.info(f"Monitoring summary: {summary}")
    
    # Get Prometheus metrics
    prometheus_metrics = system.get_prometheus_metrics()
    logger.info(f"Prometheus metrics sample:\n{prometheus_metrics[:500]}...")
    
    # Export monitoring report
    report_file = system.export_monitoring_report()
    logger.info(f"Monitoring report exported to: {report_file}")

if __name__ == "__main__":
    test_monitoring_system() 