#!/usr/bin/env python3
"""
SmartSafe AI - Profesyonel Web Dashboard
İnşaat ve diğer sektörler için kaliteli dashboard sistemi
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
from smartsafe_construction_system import ConstructionPPEDetector, ConstructionPPEConfig
from smartsafe_sector_manager import SmartSafeSectorManager
import threading
import time

app = Flask(__name__)
app.secret_key = 'smartsafe_ai_2024_secure_key'
CORS(app)

# Global değişkenler
sector_manager = SmartSafeSectorManager()
active_detectors = {}
detection_threads = {}

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
                <div class="stat-card text-center">
                    <div class="stat-icon text-danger">
                        <i class="fas fa-lira-sign"></i>
                    </div>
                    <div class="stat-value compliance-danger" id="total-penalty">{{ stats.total_penalty }} TL</div>
                    <div class="stat-label">Toplam Ceza</div>
                </div>
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
                                        <option value="0">Kamera 1 - Ana Giriş</option>
                                        <option value="1">Kamera 2 - İnşaat Sahası</option>
                                        <option value="2">Kamera 3 - Depo Alanı</option>
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
                                <div class="mt-2">
                                    <small class="text-danger">
                                        <i class="fas fa-lira-sign"></i> {{ violation.penalty }} TL
                                    </small>
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
                                    <p class="mt-2 mb-0">Ceza: 100 TL</p>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center p-3 bg-light rounded">
                                    <i class="fas fa-tshirt fa-3x text-warning mb-2"></i>
                                    <h6>Güvenlik Yeleği</h6>
                                    <span class="badge bg-danger">Zorunlu</span>
                                    <p class="mt-2 mb-0">Ceza: 75 TL</p>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center p-3 bg-light rounded">
                                    <i class="fas fa-socks fa-3x text-success mb-2"></i>
                                    <h6>Güvenlik Ayakkabısı</h6>
                                    <span class="badge bg-danger">Zorunlu</span>
                                    <p class="mt-2 mb-0">Ceza: 50 TL</p>
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
                    document.getElementById('total-penalty').textContent = data.total_penalty + ' TL';
                });
        }

        // Tespit fonksiyonları
        function startDetection() {
            const camera = document.getElementById('camera-select').value;
            const mode = document.getElementById('detection-mode').value;
            
            fetch('/api/start-detection', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({camera: camera, mode: mode})
            })
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    showAlert('Tespit başlatıldı!', 'success');
                } else {
                    showAlert('Hata: ' + data.error, 'danger');
                }
            });
        }

        function stopDetection() {
            fetch('/api/stop-detection', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if(data.success) {
                        showAlert('Tespit durduruldu!', 'info');
                    }
                });
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
    # Demo verileri
    stats = {
        'total_workers': 12,
        'compliance_rate': 78,
        'violations_today': 5,
        'total_penalty': 425
    }
    
    recent_violations = [
        {
            'worker_name': 'Ahmet Yılmaz',
            'time': '14:30',
            'missing_ppe': ['Baret', 'Güvenlik Yeleği'],
            'penalty': 175
        },
        {
            'worker_name': 'Mehmet Kaya',
            'time': '13:45',
            'missing_ppe': ['Güvenlik Ayakkabısı'],
            'penalty': 50
        },
        {
            'worker_name': 'Ali Demir',
            'time': '12:20',
            'missing_ppe': ['Baret'],
            'penalty': 100
        }
    ]
    
    return render_template('dashboard.html', stats=stats, recent_violations=recent_violations)

@app.route('/api/stats')
def get_stats():
    """İstatistikleri getir"""
    try:
        # Gerçek veri burada hesaplanacak
        stats = {
            'total_workers': 12,
            'compliance_rate': 78,
            'violations_today': 5,
            'total_penalty': 425
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-detection', methods=['POST'])
def start_detection():
    """Tespit başlat"""
    try:
        data = request.json
        camera_id = data.get('camera', '0')
        mode = data.get('mode', 'construction')
        
        # Tespit thread'i başlat
        if camera_id not in detection_threads:
            detection_threads[camera_id] = threading.Thread(
                target=run_detection,
                args=(camera_id, mode),
                daemon=True
            )
            detection_threads[camera_id].start()
        
        return jsonify({'success': True, 'message': 'Tespit başlatıldı'})
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
        
        return jsonify({'success': True, 'message': 'Tespit durduruldu'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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

def run_detection(camera_id, mode):
    """Tespit çalıştır"""
    active_detectors[camera_id] = True
    
    if mode == 'construction':
        config = ConstructionPPEConfig()
        detector = ConstructionPPEDetector(config)
        
        # Demo image testleri
        test_images = ['people1.jpg', 'people2.jpg', 'people3.jpg']
        
        while active_detectors.get(camera_id, False):
            for image_path in test_images:
                if not active_detectors.get(camera_id, False):
                    break
                
                if os.path.exists(image_path):
                    image = cv2.imread(image_path)
                    if image is not None:
                        result = detector.detect_construction_ppe(image, camera_id)
                        # Sonuçları işle
                        print(f"Kamera {camera_id}: {result['analysis']['compliance_rate']:.1f}% uyum")
                
                time.sleep(5)  # 5 saniye bekle
    
    print(f"Kamera {camera_id} tespiti durduruldu")

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