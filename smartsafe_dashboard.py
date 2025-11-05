#!/usr/bin/env python3
"""
SmartSafe AI - Profesyonel Web Dashboard
İnşaat ve diğer sektörler için kaliteli dashboard sistemi
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, Response
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
from smartsafe_construction_system import ConstructionPPEDetector, ConstructionPPEConfig
from src.smartsafe.sector.smartsafe_sector_detector_factory import SectorDetectorFactory
from src.smartsafe.sector.smartsafe_sector_manager import SmartSafeSectorManager
import threading
import time
import base64
from io import BytesIO
import queue

app = Flask(__name__)
app.secret_key = 'smartsafe_ai_2024_secure_key'
CORS(app)

# Global değişkenler
sector_manager = SmartSafeSectorManager()
active_detectors = {}
detection_threads = {}
camera_captures = {}  # Kamera yakalama nesneleri
frame_buffers = {}    # Frame buffer'ları
detection_results = {} # Tespit sonuçları

class DashboardManager:
    """Dashboard yönetim sistemi"""
    
    def __init__(self):
        self.setup_static_folders()
    
    def setup_static_folders(self):
        """Statik dosya klasörlerini oluştur"""
        folders = ['templates', 'static', 'static/css', 'static/js', 'static/images']
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
    
    def create_dashboard_template(self):
        """Dashboard HTML template oluştur"""
        template_html = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartSafe AI - İnşaat Güvenlik Sistemi</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
        }
        .navbar {
            background: rgba(255,255,255,0.95) !important;
            backdrop-filter: blur(10px);
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
        }
        .navbar-brand {
            font-weight: 700;
            color: #2c3e50 !important;
            font-size: 1.5rem;
        }
        .main-container {
            margin-top: 20px;
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            background: rgba(255,255,255,0.9);
        }
        .card-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px 15px 0 0 !important;
            padding: 20px;
        }
        .stat-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .stat-card:hover {
            transform: translateY(-5px);
        }
        .stat-icon {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #2c3e50;
        }
        .stat-label {
            color: #7f8c8d;
            font-size: 0.9rem;
        }
        .compliance-good { color: #27ae60; }
        .compliance-warning { color: #f39c12; }
        .compliance-danger { color: #e74c3c; }
        .violation-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .violation-item {
            padding: 10px;
            margin-bottom: 10px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #e74c3c;
        }
        .ppe-badge {
            font-size: 0.8rem;
            margin: 2px;
            padding: 4px 8px;
        }
        .btn-custom {
            border-radius: 25px;
            padding: 10px 30px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.3s ease;
        }
        .btn-custom:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .sector-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            cursor: pointer;
            transition: transform 0.3s ease;
        }
        .sector-card:hover {
            transform: translateY(-5px);
        }
        .live-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #27ae60;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.7; }
            100% { transform: scale(1); opacity: 1; }
        }
        .alert-banner {
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 1000;
            max-width: 350px;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light fixed-top">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-hard-hat"></i> SmartSafe AI
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/"><i class="fas fa-home"></i> Ana Sayfa</a>
                <a class="nav-link" href="/construction"><i class="fas fa-building"></i> İnşaat</a>
                <a class="nav-link" href="/sectors"><i class="fas fa-industry"></i> Sektörler</a>
                <a class="nav-link" href="/reports"><i class="fas fa-chart-bar"></i> Raporlar</a>
            </div>
        </div>
    </nav>

    <div class="container main-container">
        <div class="row">
            <div class="col-12">
                <div class="text-center mb-4">
                    <h1 class="text-white display-4 fw-bold">
                        <i class="fas fa-shield-alt"></i> SmartSafe AI
                    </h1>
                    <p class="text-white-50 fs-5">İnşaat Sektörü Güvenlik İzleme Sistemi</p>
                    <span class="live-indicator"></span>
                    <span class="text-white ms-2">Canlı İzleme Aktif</span>
                </div>
            </div>
        </div>

        <!-- İstatistik Kartları -->
        <div class="row">
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-icon text-primary">
                        <i class="fas fa-users"></i>
                    </div>
                    <div class="stat-value" id="total-workers">{{ stats.total_workers }}</div>
                    <div class="stat-label">Toplam Çalışan</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-icon text-success">
                        <i class="fas fa-check-circle"></i>
                    </div>
                    <div class="stat-value compliance-good" id="compliance-rate">{{ stats.compliance_rate }}%</div>
                    <div class="stat-label">Uyum Oranı</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-icon text-warning">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="stat-value compliance-warning" id="violations-today">{{ stats.violations_today }}</div>
                    <div class="stat-label">Bugünkü İhlaller</div>
                </div>
            </div>
            <div class="col-md-3">

            </div>
        </div>

        <!-- Ana İçerik -->
        <div class="row">
            <div class="col-lg-8">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <i class="fas fa-video"></i> Canlı Kamera Görüntüleri
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Kamera Seç:</label>
                                    <select class="form-select" id="camera-select">
                                        <option value="CAM_26875D37">Cam 2 - Ana Kamera</option>
                                        <option value="CAM_A7069D2F">Cam 11 - İkinci Kamera</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Tespit Modu:</label>
                                    <select class="form-select" id="detection-mode">
                                        <option value="construction">İnşaat Modu</option>
                                        <option value="general">Genel Tespit</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="text-center">
                            <div id="camera-display" class="mb-3" style="height: 300px; background: #f8f9fa; border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                                <i class="fas fa-camera fa-3x text-muted"></i>
                                <p class="text-muted ms-3">Kamera görüntüsü burada görünecek</p>
                            </div>
                            <button class="btn btn-success btn-custom" onclick="startDetection()">
                                <i class="fas fa-play"></i> Tespiti Başlat
                            </button>
                            <button class="btn btn-danger btn-custom ms-2" onclick="stopDetection()">
                                <i class="fas fa-stop"></i> Tespiti Durdur
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <i class="fas fa-exclamation-circle"></i> Son İhlaller
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="violation-list" id="violation-list">
                            {% for violation in recent_violations %}
                            <div class="violation-item">
                                <div class="d-flex justify-content-between">
                                    <strong>{{ violation.worker_name }}</strong>
                                    <small class="text-muted">{{ violation.time }}</small>
                                </div>
                                <div class="mt-2">
                                    {% for missing_ppe in violation.missing_ppe %}
                                    <span class="badge bg-danger ppe-badge">{{ missing_ppe }}</span>
                                    {% endfor %}
                                </div>

                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- PPE Kuralları -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <i class="fas fa-hard-hat"></i> İnşaat Sektörü PPE Kuralları
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-4">
                                <div class="text-center p-3 bg-light rounded">
                                    <i class="fas fa-hard-hat fa-3x text-primary mb-2"></i>
                                    <h6>Baret/Kask</h6>
                                    <span class="badge bg-danger">Zorunlu</span>

                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center p-3 bg-light rounded">
                                    <i class="fas fa-tshirt fa-3x text-warning mb-2"></i>
                                    <h6>Güvenlik Yeleği</h6>
                                    <span class="badge bg-danger">Zorunlu</span>

                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center p-3 bg-light rounded">
                                    <i class="fas fa-socks fa-3x text-success mb-2"></i>
                                    <h6>Güvenlik Ayakkabısı</h6>
                                    <span class="badge bg-danger">Zorunlu</span>

                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Canlı veri güncelleme
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-workers').textContent = data.total_workers;
                    document.getElementById('compliance-rate').textContent = data.compliance_rate + '%';
                    document.getElementById('violations-today').textContent = data.violations_today;

                });
        }

        // Tespit fonksiyonları
        function startDetection() {
            const camera = document.getElementById('camera-select').value;
            const mode = document.getElementById('detection-mode').value;
            
            // Doğru endpoint ve parametreler
            fetch('/api/company/COMP_FF311516/start-detection', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    camera_id: camera,
                    mode: mode,
                    confidence: 0.6
                })
            })
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    showAlert('Tespit başlatıldı!', 'success');
                    // Kamera görüntüsünü güncelle
                    updateCameraDisplay();
                } else {
                    showAlert('Hata: ' + data.error, 'danger');
                }
            })
            .catch(error => {
                showAlert('Bağlantı hatası: ' + error.message, 'danger');
            });
        }
        
        function updateCameraDisplay() {
            const cameraDisplay = document.getElementById('camera-display');
            const camera = document.getElementById('camera-select').value;
            
            if (cameraDisplay) {
                cameraDisplay.innerHTML = `
                    <div class="text-center">
                        <i class="fas fa-video fa-3x text-success mb-3"></i>
                        <h5>PPE Detection Aktif</h5>
                        <p class="text-muted">Kamera ${camera} - Gerçek zamanlı tespit yapılıyor</p>
                        <div class="mt-3">
                            <span class="badge bg-success me-2">Aktif</span>
                            <span class="badge bg-info">İnşaat Modu</span>
                        </div>
                    </div>
                `;
            }
        }

        function stopDetection() {
            fetch('/api/company/COMP_FF311516/stop-detection', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    showAlert('Tespit durduruldu!', 'info');
                    // Kamera görüntüsünü sıfırla
                    resetCameraDisplay();
                } else {
                    showAlert('Hata: ' + data.error, 'danger');
                }
            })
            .catch(error => {
                showAlert('Bağlantı hatası: ' + error.message, 'danger');
            });
        }
        
        function resetCameraDisplay() {
            const cameraDisplay = document.getElementById('camera-display');
            if (cameraDisplay) {
                cameraDisplay.innerHTML = `
                    <div class="text-center">
                        <i class="fas fa-camera fa-3x text-muted mb-3"></i>
                        <p class="text-muted">Kamera görüntüsü burada görünecek</p>
                    </div>
                `;
            }
        }

        function showAlert(message, type) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} alert-dismissible fade show alert-banner`;
            alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            document.body.appendChild(alertDiv);
            
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }

        // Sayfa yüklendiğinde
        document.addEventListener('DOMContentLoaded', function() {
            updateStats();
            setInterval(updateStats, 5000); // Her 5 saniyede bir güncelle
        });
    </script>
</body>
</html>
        """
        
        with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
            f.write(template_html)

# Dashboard manager
dashboard_manager = DashboardManager()
dashboard_manager.create_dashboard_template()

@app.route('/')
def index():
    """Ana sayfa"""
    # Gerçek detection sonuçlarından istatistikleri hesapla
    stats = calculate_real_stats()
    
    # Gerçek ihlal verilerini al
    recent_violations = get_recent_violations()
    
    return render_template('dashboard.html', stats=stats, recent_violations=recent_violations)

def calculate_real_stats():
    """Gerçek detection sonuçlarından istatistikleri hesapla"""
    try:
        total_workers = 0
        total_violations = 0
        total_detections = 0
        compliance_rates = []
        
        # Aktif kameralardan veri topla
        for camera_id in active_detectors:
            if active_detectors[camera_id] and camera_id in detection_results:
                try:
                    # En son sonucu al (queue'yu boşaltmadan)
                    temp_results = []
                    while not detection_results[camera_id].empty():
                        temp_results.append(detection_results[camera_id].get_nowait())
                    
                    if temp_results:
                        # En son sonucu kullan
                        latest_result = temp_results[-1]
                        total_workers += latest_result.get('total_people', 0)
                        total_violations += len(latest_result.get('violations', []))
                        total_detections += 1
                        compliance_rates.append(latest_result.get('compliance_rate', 0))
                        
                        # Sonuçları geri koy
                        for result in temp_results:
                            try:
                                detection_results[camera_id].put_nowait(result)
                            except queue.Full:
                                break
                except queue.Empty:
                    pass
        
        # İstatistikleri hesapla
        avg_compliance_rate = sum(compliance_rates) / len(compliance_rates) if compliance_rates else 0
        
        return {
            'total_workers': total_workers,
            'compliance_rate': round(avg_compliance_rate, 1),
            'violations_today': total_violations
        }
    except Exception as e:
        print(f"İstatistik hesaplama hatası: {e}")
        # Hata durumunda varsayılan değerler döndür
        return {
            'total_workers': 0,
            'compliance_rate': 0,
            'violations_today': 0
        }

def get_recent_violations():
    """Gerçek ihlal verilerini al"""
    try:
        recent_violations = []
        
        # Aktif kameralardan ihlal verilerini topla
        for camera_id in active_detectors:
            if active_detectors[camera_id] and camera_id in detection_results:
                try:
                    # En son sonucu al
                    temp_results = []
                    while not detection_results[camera_id].empty():
                        temp_results.append(detection_results[camera_id].get_nowait())
                    
                    if temp_results:
                        latest_result = temp_results[-1]
                        violations = latest_result.get('violations', [])
                        
                        for violation in violations:
                            recent_violations.append({
                                'worker_name': violation.get('worker_id', 'Bilinmeyen Çalışan'),
                                'time': datetime.now().strftime('%H:%M'),
                                'missing_ppe': violation.get('missing_ppe', ['Bilinmeyen'])
                            })
                        
                        # Sonuçları geri koy
                        for result in temp_results:
                            try:
                                detection_results[camera_id].put_nowait(result)
                            except queue.Full:
                                break
                except queue.Empty:
                    pass
        
        # En son 5 ihlali döndür
        return recent_violations[-5:] if recent_violations else []
        
    except Exception as e:
        print(f"İhlal verisi alma hatası: {e}")
        return []

@app.route('/api/stats')
def get_stats():
    """İstatistikleri getir"""
    try:
        # Gerçek detection sonuçlarından istatistik hesapla
        total_workers = 0
        total_violations = 0
        total_detections = 0
        compliance_rates = []
        
        # Aktif kameralardan veri topla
        for camera_id in active_detectors:
            if active_detectors[camera_id] and camera_id in detection_results:
                try:
                    # En son sonucu al (queue'yu boşaltmadan)
                    temp_results = []
                    while not detection_results[camera_id].empty():
                        temp_results.append(detection_results[camera_id].get_nowait())
                    
                    if temp_results:
                        # En son sonucu kullan
                        latest_result = temp_results[-1]
                        total_workers += latest_result.get('total_people', 0)
                        total_violations += len(latest_result.get('violations', []))
                        total_detections += 1
                        compliance_rates.append(latest_result.get('compliance_rate', 0))
                        
                        # Sonuçları geri koy
                        for result in temp_results:
                            try:
                                detection_results[camera_id].put_nowait(result)
                            except queue.Full:
                                break
                except queue.Empty:
                    pass
        
        # İstatistikleri hesapla
        avg_compliance_rate = sum(compliance_rates) / len(compliance_rates) if compliance_rates else 0
        
        stats = {
            'total_workers': total_workers,
            'compliance_rate': round(avg_compliance_rate, 1),
            'violations_today': total_violations
        }
        
        return jsonify(stats)
    except Exception as e:
        # Hata durumunda varsayılan değerler döndür
        return jsonify({
            'total_workers': 0,
            'compliance_rate': 0,
            'violations_today': 0,

        })

@app.route('/api/start-detection', methods=['POST'])
def start_detection():
    """Tespit başlat"""
    try:
        data = request.json
        camera_id = data.get('camera', '0')
        mode = data.get('mode', 'construction')
        confidence = data.get('confidence', 0.5)
        
        # Kamera zaten aktifse durdur
        if camera_id in active_detectors and active_detectors[camera_id]:
            return jsonify({'success': False, 'error': 'Kamera zaten aktif'})
        
        # Kamera aktif olarak işaretle
        active_detectors[camera_id] = True
        
        # Kamera worker thread'ini başlat
        camera_thread = threading.Thread(
            target=camera_worker,
            args=(camera_id,),
            daemon=True
        )
        camera_thread.start()
        
        # Tespit thread'ini başlat - confidence parametresi ile
        detection_thread = threading.Thread(
                target=run_detection,
            args=(camera_id, mode, confidence),
                daemon=True
            )
        detection_thread.start()
        
        detection_threads[camera_id] = {
            'camera_thread': camera_thread,
            'detection_thread': detection_thread,
            'config': {
                'mode': mode,
                'confidence': confidence
            }
        }
        
        return jsonify({
            'success': True, 
            'message': f'Kamera {camera_id} tespiti başlatıldı (Confidence: {confidence})',
            'video_url': f'/api/video-feed/{camera_id}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stop-detection', methods=['POST'])
def stop_detection():
    """Tespit durdur"""
    try:
        # Tüm tespit thread'lerini durdur
        for camera_id in list(detection_threads.keys()):
            if camera_id in active_detectors:
                active_detectors[camera_id] = False
                del detection_threads[camera_id]
        
        # Kamera yakalama nesnelerini serbest bırak
        for camera_id in list(camera_captures.keys()):
            if camera_captures[camera_id] is not None:
                camera_captures[camera_id].release()
                del camera_captures[camera_id]
        
        return jsonify({'success': True, 'message': 'Tespit durduruldu'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/video-feed/<camera_id>')
def video_feed(camera_id):
    """Video stream endpoint"""
    return Response(generate_frames(camera_id),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera-frame/<camera_id>')
def get_camera_frame(camera_id):
    """Tek frame al - MJPEG için"""
    try:
        if camera_id in frame_buffers and frame_buffers[camera_id] is not None:
            # Frame'i base64 encode et
            _, buffer = cv2.imencode('.jpg', frame_buffers[camera_id])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return jsonify({
                'success': True,
                'frame': frame_base64,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'success': False, 'error': 'Kamera aktif değil'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/detection-results/<camera_id>')
def get_detection_results(camera_id):
    """Detection sonuçlarını al"""
    try:
        if camera_id in detection_results and not detection_results[camera_id].empty():
            # En son detection sonucunu al
            try:
                latest_result = detection_results[camera_id].get_nowait()
                return jsonify({
                    'success': True,
                    'result': latest_result
                })
            except queue.Empty:
                return jsonify({
                    'success': True,
                    'result': None,
                    'message': 'Henüz tespit sonucu yok'
                })
        else:
            return jsonify({
                'success': True,
                'result': None,
                'message': 'Kamera aktif değil veya sonuç yok'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_frames(camera_id):
    """Video frame generator"""
    while True:
        try:
            if camera_id in frame_buffers and frame_buffers[camera_id] is not None:
                # Frame'i JPEG olarak encode et
                ret, buffer = cv2.imencode('.jpg', frame_buffers[camera_id])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                else:
                    # Boş frame gönder
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
            else:
                # Kamera aktif değilse boş frame gönder
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
            
            time.sleep(0.033)  # ~30 FPS
            
        except Exception as e:
            print(f"Frame generation error: {e}")
            break

def setup_camera(camera_id):
    """Kamera kurulumu"""
    try:
        # Kamera ID'sini integer'a çevir
        cam_index = int(camera_id)
        
        # Kamera yakalama nesnesi oluştur
        cap = cv2.VideoCapture(cam_index)
        
        if not cap.isOpened():
            print(f"Kamera {camera_id} açılamadı")
            return None
        
        # Kamera ayarları
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        print(f"Kamera {camera_id} başarıyla kuruldu")
        return cap
        
    except Exception as e:
        print(f"Kamera kurulum hatası: {e}")
        return None

def camera_worker(camera_id):
    """Kamera worker thread'i"""
    print(f"Kamera {camera_id} worker başlatılıyor...")
    
    cap = setup_camera(camera_id)
    if cap is None:
        return
    
    camera_captures[camera_id] = cap
    frame_buffers[camera_id] = None
    
    try:
        while active_detectors.get(camera_id, False):
            ret, frame = cap.read()
            if ret:
                # Frame'i buffer'a kaydet
                frame_buffers[camera_id] = frame.copy()
            else:
                print(f"Kamera {camera_id} frame okunamadı")
                break
            
            time.sleep(0.01)  # CPU yükünü azalt
            
    except Exception as e:
        print(f"Kamera {camera_id} worker hatası: {e}")
    finally:
        if cap:
            cap.release()
        if camera_id in camera_captures:
            del camera_captures[camera_id]
        if camera_id in frame_buffers:
            del frame_buffers[camera_id]
        print(f"Kamera {camera_id} worker durduruldu")

@app.route('/construction')
def construction_dashboard():
    """İnşaat sektörü dashboard"""
    config = ConstructionPPEConfig()
    detector = ConstructionPPEDetector(config)
    
    # Günlük rapor
    daily_report = detector.generate_daily_report()
    
    return render_template('construction.html', 
                         config=config, 
                         daily_report=daily_report)

@app.route('/sectors')
def sectors_dashboard():
    """Sektörler dashboard"""
    sectors = sector_manager.list_available_sectors()
    general_report = sector_manager.generate_multi_sector_report()
    
    return render_template('sectors.html', 
                         sectors=sectors, 
                         general_report=general_report)

@app.route('/reports')
def reports_dashboard():
    """Raporlar dashboard"""
    return render_template('reports.html')

def run_detection(camera_id, mode, confidence=0.5):
    """Sektörel tespit çalıştır"""
    print(f"Tespit sistemi başlatılıyor - Kamera: {camera_id}, Sektör: {mode}, Confidence: {confidence}")
    
    # Detection sonuçları için queue oluştur
    detection_results[camera_id] = queue.Queue(maxsize=10)
    
    # Sektörel detector al
    try:
        detector = SectorDetectorFactory.get_detector(mode)
        if detector:
            print(f"✅ {mode.upper()} sektörü detector başlatıldı - Kamera: {camera_id}")
        else:
            print(f"⚠️ {mode.upper()} detector yüklenemedi, construction kullanılacak")
            detector = SectorDetectorFactory.get_detector('construction')
    except Exception as e:
        print(f"❌ Sektörel detector hatası: {e}, construction kullanılacak")
        detector = SectorDetectorFactory.get_detector('construction')
    
    if detector:
        frame_count = 0
        last_detection_time = time.time()
        
        while active_detectors.get(camera_id, False):
            try:
                # Frame buffer'dan frame al
                if camera_id in frame_buffers and frame_buffers[camera_id] is not None:
                    frame = frame_buffers[camera_id].copy()
                    frame_count += 1
                    
                    # Her 5 frame'de bir tespit yap (performans için)
                    if frame_count % 5 == 0:
                        current_time = time.time()
                        
                        # Sektörel PPE tespiti yap
                        result = detector.detect_ppe(frame, camera_id)
                        
                        # Sonuçları kaydet
                        detection_data = {
                            'camera_id': camera_id,
                            'timestamp': datetime.now().isoformat(),
                            'frame_count': frame_count,
                            'compliance_rate': result['analysis']['compliance_rate'],
                            'total_people': result['analysis']['total_people'],
                            'violations': result['analysis']['violations'],
                            'processing_time': current_time - last_detection_time,
                            'sector': result.get('sector', mode)
                        }
                        
                        # Queue'ya ekle
                        try:
                            detection_results[camera_id].put_nowait(detection_data)
                        except queue.Full:
                            # Queue doluysa eski sonucu çıkar, yenisini ekle
                            try:
                                detection_results[camera_id].get_nowait()
                            except queue.Empty:
                                pass
                            detection_results[camera_id].put_nowait(detection_data)
                        
                        # Tespit sonucunu frame'e çiz
                        annotated_frame = draw_sector_detection_results(frame, result)
                        frame_buffers[camera_id] = annotated_frame
                        
                        last_detection_time = current_time
                        
                        print(f"Kamera {camera_id} ({result.get('sector', mode)}): {result['analysis']['compliance_rate']:.1f}% uyum, "
                              f"{result['analysis']['total_people']} kişi")
                
                time.sleep(0.1)  # CPU yükünü azalt
                
            except Exception as e:
                print(f"Tespit hatası - Kamera {camera_id}: {e}")
                time.sleep(1)
    
    print(f"Kamera {camera_id} tespiti durduruldu")

def draw_sector_detection_results(image, detection_result):
    """Sektörel detection sonuçlarını görüntü üzerine çiz"""
    try:
        # Kopyasını al
        result_image = image.copy()
        height, width = result_image.shape[:2]
        
        # Sektör bilgisi
        sector = detection_result.get('sector', 'unknown')
        sector_names = {
            'construction': 'İnşaat',
            'food': 'Gıda', 
            'chemical': 'Kimya',
            'manufacturing': 'İmalat',
            'warehouse': 'Depo'
        }
        sector_name = sector_names.get(sector, sector.upper())
        
        # Başlık bilgisi
        cv2.putText(result_image, f"SmartSafe AI - {sector_name} Sektörü", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Uygunluk oranı
        compliance_rate = detection_result['analysis'].get('compliance_rate', 0)
        color = (0, 255, 0) if compliance_rate > 80 else (0, 165, 255) if compliance_rate > 60 else (0, 0, 255)
        cv2.putText(result_image, f"Uygunluk: {compliance_rate:.1f}%", 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Kişi sayısı
        total_people = detection_result['analysis'].get('total_people', 0)
        cv2.putText(result_image, f"Kişi: {total_people}", 
                   (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # İhlal sayısı
        violations = detection_result['analysis'].get('violations', [])
        cv2.putText(result_image, f"İhlal: {len(violations)}", 
                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        

        
        # Zaman damgası
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(result_image, timestamp, 
                   (width - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return result_image
        
    except Exception as e:
        print(f"Draw sector detection results hatası: {e}")
        return image

if __name__ == '__main__':
    print("🌐 SmartSafe AI - Professional Web Dashboard")
    print("=" * 60)
    print("✅ İnşaat sektörü özelleştirilmiş dashboard")
    print("✅ Çok sektörlü yönetim sistemi")
    print("✅ Gerçek zamanlı monitoring")
    print("✅ Profesyonel UI/UX tasarım")
    print("=" * 60)
    print("🚀 Dashboard başlatılıyor...")
    print("📱 Erişim: http://localhost:5000")
    print("🏗️ İnşaat Dashboard: http://localhost:5000/construction")
    print("🏭 Sektörler: http://localhost:5000/sectors")
    print("📊 Raporlar: http://localhost:5000/reports")
    
    app.run(debug=True, host='0.0.0.0', port=5000) 