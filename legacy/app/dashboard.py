"""
PPE Detection System Dashboard
Modern Streamlit web interface for monitoring and control
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import yaml
import cv2
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
import logging
import base64
from typing import Dict, List, Optional

# Set page config
st.set_page_config(
    page_title="PPE Detection Dashboard",
    page_icon="🦺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern UI
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #FF6B35;
        text-align: center;
        margin-bottom: 2rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    
    .alert-card {
        background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    
    .success-card {
        background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    
    .stSelectbox > div > div {
        background-color: #f8f9fa;
    }
    
    .sidebar-content {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

class PPEDashboard:
    """PPE Detection Dashboard"""
    
    def __init__(self):
        """Initialize dashboard"""
        self.config = self.load_config()
        self.db_path = self.config.get('database', {}).get('path', 'logs/ppe_detection.db')
        
        # Initialize session state
        if 'detection_running' not in st.session_state:
            st.session_state.detection_running = False
        if 'last_update' not in st.session_state:
            st.session_state.last_update = datetime.now()
    
    @staticmethod
    @st.cache_data(ttl=60)
    def load_config():
        """Load configuration with caching"""
        try:
            with open('configs/config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            st.error("Configuration file not found!")
            return {}
    
    @st.cache_data(ttl=30)
    def get_database_connection(_self):
        """Get database connection with caching"""
        try:
            if Path(_self.db_path).exists():
                return sqlite3.connect(_self.db_path)
            else:
                st.warning("Database not found. Start detection to create database.")
                return None
        except Exception as e:
            st.error(f"Database connection failed: {str(e)}")
            return None
    
    def get_detection_stats(self) -> Dict:
        """Get detection statistics from database"""
        conn = self.get_database_connection()
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            
            # Total detections
            cursor.execute("SELECT COUNT(*) FROM detections")
            total_detections = cursor.fetchone()[0]
            
            # Recent detections (last hour)
            cursor.execute("""
                SELECT COUNT(*) FROM detections 
                WHERE timestamp > datetime('now', '-1 hour')
            """)
            recent_detections = cursor.fetchone()[0]
            
            # Violations
            cursor.execute("SELECT COUNT(*) FROM violations")
            total_violations = cursor.fetchone()[0]
            
            # Recent violations
            cursor.execute("""
                SELECT COUNT(*) FROM violations 
                WHERE timestamp > datetime('now', '-1 hour')
            """)
            recent_violations = cursor.fetchone()[0]
            
            # Active tracks
            cursor.execute("""
                SELECT COUNT(DISTINCT track_id) FROM detections 
                WHERE timestamp > datetime('now', '-5 minutes')
            """)
            active_tracks = cursor.fetchone()[0]
            
            # Compliance rate
            if total_detections > 0:
                compliance_rate = ((total_detections - total_violations) / total_detections) * 100
            else:
                compliance_rate = 0
            
            conn.close()
            
            return {
                'total_detections': total_detections,
                'recent_detections': recent_detections,
                'total_violations': total_violations,
                'recent_violations': recent_violations,
                'active_tracks': active_tracks,
                'compliance_rate': compliance_rate
            }
            
        except Exception as e:
            st.error(f"Failed to get statistics: {str(e)}")
            conn.close()
            return {}
    
    def get_violation_data(self) -> pd.DataFrame:
        """Get violation data for charts"""
        conn = self.get_database_connection()
        if not conn:
            return pd.DataFrame()
        
        try:
            # Get violations with details
            query = """
                SELECT 
                    timestamp,
                    track_id,
                    violation_type,
                    duration,
                    alert_sent
                FROM violations
                ORDER BY timestamp DESC
                LIMIT 100
            """
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['hour'] = df['timestamp'].dt.hour
                df['date'] = df['timestamp'].dt.date
            
            return df
            
        except Exception as e:
            st.error(f"Failed to get violation data: {str(e)}")
            conn.close()
            return pd.DataFrame()
    
    def get_detection_data(self) -> pd.DataFrame:
        """Get detection data for analysis"""
        conn = self.get_database_connection()
        if not conn:
            return pd.DataFrame()
        
        try:
            query = """
                SELECT 
                    timestamp,
                    track_id,
                    has_hard_hat,
                    has_safety_vest,
                    has_mask,
                    confidence
                FROM detections
                WHERE timestamp > datetime('now', '-24 hours')
                ORDER BY timestamp DESC
            """
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['hour'] = df['timestamp'].dt.hour
                df['compliant'] = df['has_hard_hat'] & df['has_safety_vest'] & df['has_mask']
            
            return df
            
        except Exception as e:
            st.error(f"Failed to get detection data: {str(e)}")
            conn.close()
            return pd.DataFrame()
    
    def render_header(self):
        """Render dashboard header"""
        st.markdown('<h1 class="main-header">🦺 PPE Detection Dashboard</h1>', 
                   unsafe_allow_html=True)
        
        # Status indicator
        if st.session_state.detection_running:
            st.success("🟢 Detection System Active")
        else:
            st.error("🔴 Detection System Inactive")
        
        st.markdown("---")
    
    def render_control_panel(self):
        """Render control panel in sidebar"""
        st.sidebar.markdown("## 🎛️ Control Panel")
        
        # Detection controls
        st.sidebar.markdown("### Detection Control")
        
        if st.sidebar.button("▶️ Start Detection", type="primary"):
            if not st.session_state.detection_running:
                st.session_state.detection_running = True
                st.sidebar.success("Detection started!")
                # Here you would start the detection process
                # threading.Thread(target=start_detection_process, daemon=True).start()
            else:
                st.sidebar.warning("Detection already running!")
        
        if st.sidebar.button("⏹️ Stop Detection"):
            if st.session_state.detection_running:
                st.session_state.detection_running = False
                st.sidebar.success("Detection stopped!")
            else:
                st.sidebar.info("Detection not running!")
        
        # Configuration
        st.sidebar.markdown("### ⚙️ Configuration")
        
        # Video source selection
        video_sources = ["Webcam (0)", "Webcam (1)", "Video File", "IP Camera"]
        selected_source = st.sidebar.selectbox("Video Source", video_sources)
        
        # Detection settings
        confidence_threshold = st.sidebar.slider(
            "Confidence Threshold", 0.1, 1.0, 0.6, 0.1
        )
        
        violation_duration = st.sidebar.slider(
            "Violation Duration (seconds)", 1, 30, 5, 1
        )
        
        # Alert settings
        st.sidebar.markdown("### 🚨 Alert Settings")
        
        audio_alerts = st.sidebar.checkbox("Audio Alerts", value=True)
        email_alerts = st.sidebar.checkbox("Email Alerts", value=False)
        
        # System info
        st.sidebar.markdown("### 📊 System Info")
        st.sidebar.info(f"Last Update: {st.session_state.last_update.strftime('%H:%M:%S')}")
        
        # Manual refresh
        if st.sidebar.button("🔄 Refresh Data"):
            st.session_state.last_update = datetime.now()
            st.rerun()
    
    def render_metrics(self):
        """Render key metrics"""
        stats = self.get_detection_stats()
        
        if not stats:
            st.warning("No data available. Start detection to see metrics.")
            return
        
        # Create metric columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="🎯 Total Detections",
                value=stats.get('total_detections', 0),
                delta=stats.get('recent_detections', 0)
            )
        
        with col2:
            st.metric(
                label="⚠️ Total Violations",
                value=stats.get('total_violations', 0),
                delta=stats.get('recent_violations', 0),
                delta_color="inverse"
            )
        
        with col3:
            st.metric(
                label="👥 Active Persons",
                value=stats.get('active_tracks', 0)
            )
        
        with col4:
            compliance_rate = stats.get('compliance_rate', 0)
            st.metric(
                label="✅ Compliance Rate",
                value=f"{compliance_rate:.1f}%",
                delta=f"{compliance_rate - 90:.1f}%" if compliance_rate > 0 else None
            )
    
    def render_real_time_charts(self):
        """Render real-time charts"""
        col1, col2 = st.columns(2)
        
        # Violations over time
        with col1:
            st.subheader("📈 Violations Over Time")
            
            violation_df = self.get_violation_data()
            
            if not violation_df.empty:
                # Group by hour
                hourly_violations = violation_df.groupby('hour').size().reset_index(name='count')
                
                fig = px.line(
                    hourly_violations, 
                    x='hour', 
                    y='count',
                    title="Violations by Hour",
                    labels={'hour': 'Hour of Day', 'count': 'Number of Violations'}
                )
                fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No violation data available")
        
        # Violation types
        with col2:
            st.subheader("🔍 Violation Types")
            
            if not violation_df.empty:
                # Count violation types
                violation_types = violation_df['violation_type'].value_counts()
                
                fig = px.pie(
                    values=violation_types.values,
                    names=violation_types.index,
                    title="Distribution of Violation Types"
                )
                fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No violation data available")
    
    def render_compliance_analysis(self):
        """Render compliance analysis"""
        st.subheader("📊 Compliance Analysis")
        
        detection_df = self.get_detection_data()
        
        if detection_df.empty:
            st.info("No detection data available")
            return
        
        # Compliance over time
        hourly_compliance = detection_df.groupby('hour').agg({
            'compliant': 'mean',
            'track_id': 'nunique'
        }).reset_index()
        
        hourly_compliance['compliance_rate'] = hourly_compliance['compliant'] * 100
        
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Compliance Rate Over Time', 'Active Persons Over Time'),
            vertical_spacing=0.1
        )
        
        # Compliance rate
        fig.add_trace(
            go.Scatter(
                x=hourly_compliance['hour'],
                y=hourly_compliance['compliance_rate'],
                mode='lines+markers',
                name='Compliance Rate (%)',
                line=dict(color='green', width=3)
            ),
            row=1, col=1
        )
        
        # Active persons
        fig.add_trace(
            go.Bar(
                x=hourly_compliance['hour'],
                y=hourly_compliance['track_id'],
                name='Active Persons',
                marker_color='blue'
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            height=600,
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        
        fig.update_xaxes(title_text="Hour of Day", row=2, col=1)
        fig.update_yaxes(title_text="Compliance Rate (%)", row=1, col=1)
        fig.update_yaxes(title_text="Number of Persons", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_recent_alerts(self):
        """Render recent alerts table"""
        st.subheader("🚨 Recent Alerts")
        
        violation_df = self.get_violation_data()
        
        if not violation_df.empty:
            # Show last 10 violations
            recent_violations = violation_df.head(10)
            
            # Format the data for display
            display_df = recent_violations.copy()
            display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            display_df['duration'] = display_df['duration'].round(1)
            display_df['alert_sent'] = display_df['alert_sent'].map({True: '✅', False: '❌'})
            
            # Rename columns for better display
            display_df = display_df.rename(columns={
                'timestamp': 'Time',
                'track_id': 'Person ID',
                'violation_type': 'Violation Type',
                'duration': 'Duration (s)',
                'alert_sent': 'Alert Sent'
            })
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No recent alerts")
    
    def render_system_status(self):
        """Render system status"""
        st.subheader("🔧 System Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📋 Configuration")
            
            config_info = {
                "Model": self.config.get('model', {}).get('name', 'N/A'),
                "Confidence Threshold": self.config.get('model', {}).get('confidence_threshold', 'N/A'),
                "Tracking": "Enabled" if self.config.get('detection', {}).get('tracking_enabled', False) else "Disabled",
                "Audio Alerts": "Enabled" if self.config.get('alerts', {}).get('audio_enabled', False) else "Disabled",
                "Email Alerts": "Enabled" if self.config.get('alerts', {}).get('email_enabled', False) else "Disabled"
            }
            
            for key, value in config_info.items():
                st.write(f"**{key}:** {value}")
        
        with col2:
            st.markdown("### 📈 Performance")
            
            # Simulate performance metrics
            performance_metrics = {
                "Average FPS": "28.5",
                "CPU Usage": "45%",
                "Memory Usage": "2.1 GB",
                "GPU Usage": "72%" if self.config.get('model', {}).get('device') == 'cuda' else "N/A",
                "Uptime": "2h 34m"
            }
            
            for key, value in performance_metrics.items():
                st.write(f"**{key}:** {value}")
    
    def run(self):
        """Run the dashboard"""
        # Header
        self.render_header()
        
        # Control panel (sidebar)
        self.render_control_panel()
        
        # Main content
        # Metrics
        self.render_metrics()
        
        st.markdown("---")
        
        # Charts
        self.render_real_time_charts()
        
        st.markdown("---")
        
        # Compliance analysis
        self.render_compliance_analysis()
        
        st.markdown("---")
        
        # Recent alerts and system status
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self.render_recent_alerts()
        
        with col2:
            self.render_system_status()
        
        # Auto-refresh
        time.sleep(5)
        st.rerun()

# Main execution
if __name__ == "__main__":
    dashboard = PPEDashboard()
    dashboard.run()
