"""
Alert utilities for PPE Detection System
Modern notification system with email, and logging
"""

import smtplib
import logging
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import numpy as np
from datetime import datetime
import cv2

# Try to import pygame for audio support
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available - audio alerts will be disabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertManager:
    """Comprehensive alert management system"""
    
    def __init__(self, config_path: str = "configs/config.yaml"):
        """Initialize alert manager"""
        self.config = self.load_config(config_path)
        self.setup_audio()
        self.setup_email()
        
        # Alert tracking
        self.alert_history = []
        self.last_alert_times = {}
        
        logger.info("Alert Manager initialized")
    
    @staticmethod
    def load_config(config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            return {}
    
    def setup_audio(self):
        """Setup audio alert system"""
        try:
            if self.config.get('alerts', {}).get('audio_enabled', False) and PYGAME_AVAILABLE:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                self.audio_enabled = True
                logger.info("Audio system initialized")
            else:
                self.audio_enabled = False
                logger.info("Audio alerts disabled")
        except Exception as e:
            logger.error(f"Audio setup failed: {str(e)}")
            self.audio_enabled = False
    
    def setup_email(self):
        """Setup email alert system"""
        try:
            email_config = self.config.get('alerts', {}).get('email', {})
            
            if email_config.get('sender_email') and email_config.get('sender_password'):
                self.email_enabled = True
                self.smtp_server = email_config.get('smtp_server', 'smtp.gmail.com')
                self.smtp_port = email_config.get('smtp_port', 587)
                self.sender_email = email_config['sender_email']
                self.sender_password = email_config['sender_password']
                self.recipient_emails = email_config.get('recipient_emails', [])
                logger.info("Email system configured")
            else:
                self.email_enabled = False
                logger.info("Email alerts disabled - credentials not configured")
        except Exception as e:
            logger.error(f"Email setup failed: {str(e)}")
            self.email_enabled = False
    
    def generate_alert_sound(self, frequency: int = 880, duration: float = 0.5) -> np.ndarray:
        """Generate alert sound programmatically"""
        sample_rate = 22050
        frames = int(duration * sample_rate)
        
        # Generate sine wave
        t = np.linspace(0, duration, frames, False)
        wave = np.sin(2 * np.pi * frequency * t)
        
        # Add envelope to prevent clicks
        envelope = np.exp(-t * 3)  # Exponential decay
        wave = wave * envelope
        
        # Convert to 16-bit integers
        wave = (wave * 32767).astype(np.int16)
        
        return wave
    
    def play_audio_alert(self, alert_type: str = "violation"):
        """Play audio alert"""
        if not self.audio_enabled:
            return
        
        try:
            # Different sounds for different alert types
            if alert_type == "violation":
                frequency = 880  # A5 note
                duration = 0.5
            elif alert_type == "warning":
                frequency = 660  # E5 note
                duration = 0.3
            else:
                frequency = 440  # A4 note
                duration = 0.2
            
            # Generate sound
            sound_array = self.generate_alert_sound(frequency, duration)
            
            # Play sound
            sound = pygame.sndarray.make_sound(np.array([sound_array, sound_array]).T)
            sound.play()
            
            logger.info(f"Audio alert played: {alert_type}")
            
        except Exception as e:
            logger.error(f"Failed to play audio alert: {str(e)}")
    
    def send_email_alert(self, 
                        subject: str, 
                        message: str, 
                        image_path: Optional[str] = None,
                        alert_type: str = "violation") -> bool:
        """Send email alert with optional image attachment"""
        if not self.email_enabled or not self.recipient_emails:
            return False
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipient_emails)
            msg['Subject'] = subject
            
            # Add body
            body = f"""
PPE Detection System Alert

Alert Type: {alert_type.upper()}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Details:
{message}

This is an automated alert from the PPE Detection System.
Please take appropriate action to ensure workplace safety.

---
PPE Detection System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Add image if provided
            if image_path and Path(image_path).exists():
                with open(image_path, 'rb') as f:
                    img_data = f.read()
                    image = MIMEImage(img_data)
                    image.add_header('Content-Disposition', 
                                   f'attachment; filename="{Path(image_path).name}"')
                    msg.attach(image)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            text = msg.as_string()
            server.sendmail(self.sender_email, self.recipient_emails, text)
            server.quit()
            
            logger.info(f"Email alert sent to {len(self.recipient_emails)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {str(e)}")
            return False
    
    def create_alert_image(self, frame: np.ndarray, violations: List[str]) -> str:
        """Create alert image with violation information overlaid"""
        try:
            # Create a copy of the frame
            alert_frame = frame.copy()
            
            # Add alert overlay
            overlay = np.zeros_like(alert_frame)
            overlay[:, :] = (0, 0, 255)  # Red overlay
            
            # Blend overlay with frame
            alpha = 0.3
            alert_frame = cv2.addWeighted(alert_frame, 1 - alpha, overlay, alpha, 0)
            
            # Add text overlay
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.0
            color = (255, 255, 255)
            thickness = 2
            
            # Alert header
            cv2.putText(alert_frame, "PPE VIOLATION DETECTED", (50, 50), 
                       font, font_scale, color, thickness)
            
            # Timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(alert_frame, f"Time: {timestamp}", (50, 100), 
                       font, 0.7, color, thickness)
            
            # Violations
            y_offset = 150
            for i, violation in enumerate(violations):
                cv2.putText(alert_frame, f"• {violation}", (50, y_offset + i * 40), 
                           font, 0.8, color, thickness)
            
            # Save image
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_path = f"logs/alert_{timestamp_str}.jpg"
            Path("logs").mkdir(exist_ok=True)
            cv2.imwrite(image_path, alert_frame)
            
            return image_path
            
        except Exception as e:
            logger.error(f"Failed to create alert image: {str(e)}")
            return ""
    
    def trigger_comprehensive_alert(self, 
                                   track_id: int,
                                   violations: List[str],
                                   duration: float,
                                   frame: Optional[np.ndarray] = None) -> bool:
        """Trigger comprehensive alert with all configured methods"""
        try:
            # Check cooldown
            current_time = time.time()
            cooldown = self.config.get('alerts', {}).get('violation_cooldown', 10)
            
            if track_id in self.last_alert_times:
                if current_time - self.last_alert_times[track_id] < cooldown:
                    return False
            
            self.last_alert_times[track_id] = current_time
            
            # Audio alert
            if self.config.get('alerts', {}).get('audio_enabled', False) and PYGAME_AVAILABLE:
                threading.Thread(target=self.play_audio_alert, 
                               args=("violation",), daemon=True).start()
            
            # Email alert
            if self.config.get('alerts', {}).get('email_enabled', False):
                subject = f"PPE Violation Alert - Person {track_id}"
                message = f"""
Person ID: {track_id}
Violations: {', '.join(violations)}
Duration: {duration:.1f} seconds

Immediate action required to ensure workplace safety compliance.
                """
                
                # Create alert image if frame is provided
                image_path = ""
                if frame is not None:
                    image_path = self.create_alert_image(frame, violations)
                
                threading.Thread(target=self.send_email_alert, 
                               args=(subject, message, image_path, "violation"), 
                               daemon=True).start()
            
            # Log alert
            alert_record = {
                'timestamp': datetime.now().isoformat(),
                'track_id': track_id,
                'violations': violations,
                'duration': duration,
                'alert_methods': []
            }
            
            if self.audio_enabled:
                alert_record['alert_methods'].append('audio')
            if self.email_enabled:
                alert_record['alert_methods'].append('email')
            
            self.alert_history.append(alert_record)
            
            logger.warning(f"COMPREHENSIVE ALERT TRIGGERED - Person {track_id}: {', '.join(violations)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to trigger comprehensive alert: {str(e)}")
            return False
    
    def get_alert_statistics(self) -> Dict:
        """Get alert statistics"""
        try:
            if not self.alert_history:
                return {}
            
            # Count alerts by type
            violation_counts = {}
            for alert in self.alert_history:
                for violation in alert['violations']:
                    violation_counts[violation] = violation_counts.get(violation, 0) + 1
            
            # Get recent alerts
            recent_alerts = [alert for alert in self.alert_history 
                           if (datetime.now() - datetime.fromisoformat(alert['timestamp'])).seconds < 3600]
            
            stats = {
                'total_alerts': len(self.alert_history),
                'recent_alerts_1h': len(recent_alerts),
                'violation_breakdown': violation_counts,
                'last_alert': self.alert_history[-1]['timestamp'] if self.alert_history else None,
                'most_common_violation': max(violation_counts.items(), key=lambda x: x[1])[0] if violation_counts else None
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get alert statistics: {str(e)}")
            return {}
    
    def test_alert_system(self) -> Dict[str, bool]:
        """Test all alert systems"""
        results = {}
        
        # Test audio
        try:
            if self.audio_enabled:
                self.play_audio_alert("warning")
                results['audio'] = True
                logger.info("Audio test: PASSED")
            else:
                results['audio'] = False
                logger.info("Audio test: SKIPPED (disabled)")
        except Exception as e:
            results['audio'] = False
            logger.error(f"Audio test: FAILED - {str(e)}")
        
        # Test email
        try:
            if self.email_enabled:
                success = self.send_email_alert(
                    "PPE Detection System Test",
                    "This is a test alert from the PPE Detection System. If you receive this email, the alert system is working correctly.",
                    alert_type="test"
                )
                results['email'] = success
                logger.info(f"Email test: {'PASSED' if success else 'FAILED'}")
            else:
                results['email'] = False
                logger.info("Email test: SKIPPED (disabled)")
        except Exception as e:
            results['email'] = False
            logger.error(f"Email test: FAILED - {str(e)}")
        
        return results

# Usage example and testing
if __name__ == "__main__":
    # Initialize alert manager
    alert_manager = AlertManager()
    
    # Test alert system
    print("Testing Alert System...")
    test_results = alert_manager.test_alert_system()
    
    print("\nTest Results:")
    for system, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {system.upper()}: {status}")
    
    # Get statistics
    stats = alert_manager.get_alert_statistics()
    print(f"\nAlert Statistics: {stats}")
    
    print("\nAlert Manager test completed!")
