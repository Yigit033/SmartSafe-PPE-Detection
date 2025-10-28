/**
 * SmartSafe AI - Akıllı Kamera Tespit Sistemi
 * Gelişmiş kamera tespiti ve yönetimi için JavaScript fonksiyonları
 */

class SmartCameraDetection {
    constructor() {
        this.isScanning = false;
        this.scanProgress = 0;
        this.discoveredCameras = [];
        this.currentCompanyId = null;
        
        // Event listeners
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        // Akıllı tespit butonu
        const smartDetectBtn = document.getElementById('smartDetectBtn');
        if (smartDetectBtn) {
            smartDetectBtn.addEventListener('click', () => this.startSmartDetection());
        }
        
        // IP adresi ile hızlı test butonu
        const quickTestBtn = document.getElementById('quickTestBtn');
        if (quickTestBtn) {
            quickTestBtn.addEventListener('click', () => this.quickCameraTest());
        }
        
        // Ağ tarama butonu
        const networkScanBtn = document.getElementById('networkScanBtn');
        if (networkScanBtn) {
            networkScanBtn.addEventListener('click', () => this.startNetworkScan());
        }
        
        // Otomatik ekleme butonu
        const autoAddBtn = document.getElementById('autoAddBtn');
        if (autoAddBtn) {
            autoAddBtn.addEventListener('click', () => this.autoAddDiscoveredCameras());
        }
    }
    
    /**
     * Akıllı kamera tespiti başlat
     */
    async startSmartDetection() {
        const ipInput = document.getElementById('cameraIP');
        const ipAddress = ipInput ? ipInput.value.trim() : '';
        
        if (!ipAddress) {
            this.showNotification('IP adresi gerekli!', 'error');
            return;
        }
        
        if (!this.validateIPAddress(ipAddress)) {
            this.showNotification('Geçersiz IP adresi formatı!', 'error');
            return;
        }
        
        this.showLoading('Akıllı kamera tespiti başlatılıyor...');
        
        try {
            const response = await fetch(`/api/company/${this.getCompanyId()}/cameras/smart-test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ip_address: ipAddress,
                    name: `Akıllı Tespit Kamera ${ipAddress}`
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.handleSmartDetectionSuccess(result, ipAddress);
            } else {
                this.handleSmartDetectionError(result.error);
            }
            
        } catch (error) {
            this.handleSmartDetectionError(`Bağlantı hatası: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }
    
    /**
     * Akıllı tespit başarılı sonucu işle
     */
    handleSmartDetectionSuccess(result, ipAddress) {
        const detectionInfo = result.detection_info;
        const cameraConfig = result.camera_config;
        
        // Sonuçları göster
        this.showDetectionResults(detectionInfo, cameraConfig);
        
        // Form alanlarını otomatik doldur
        this.autoFillCameraForm(cameraConfig);
        
        // Başarı mesajı
        this.showNotification(
            `✅ Kamera başarıyla tespit edildi!<br>
             Model: ${detectionInfo.detected_model}<br>
             Protokol: ${detectionInfo.protocol}<br>
             Port: ${detectionInfo.port}`,
            'success'
        );
        
        // Tespit edilen kamerayı listeye ekle
        this.addToDiscoveredList(detectionInfo, cameraConfig);
    }
    
    /**
     * Akıllı tespit hatası işle
     */
    handleSmartDetectionError(error) {
        this.showNotification(`❌ Kamera tespit edilemedi: ${error}`, 'error');
        
        // Hata detaylarını göster
        this.showErrorDetails(error);
    }
    
    /**
     * Tespit sonuçlarını göster
     */
    showDetectionResults(detectionInfo, cameraConfig) {
        const resultsContainer = document.getElementById('detectionResults');
        if (!resultsContainer) return;
        
        const confidenceColor = detectionInfo.detection_confidence > 0.8 ? 'green' : 
                               detectionInfo.detection_confidence > 0.6 ? 'orange' : 'red';
        
        resultsContainer.innerHTML = `
            <div class="detection-result-card">
                <h4>🎯 Tespit Sonuçları</h4>
                <div class="result-grid">
                    <div class="result-item">
                        <span class="label">Model:</span>
                        <span class="value">${detectionInfo.detected_model}</span>
                    </div>
                    <div class="result-item">
                        <span class="label">Güven:</span>
                        <span class="value" style="color: ${confidenceColor}">
                            ${(detectionInfo.detection_confidence * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="result-item">
                        <span class="label">Protokol:</span>
                        <span class="value">${detectionInfo.protocol.toUpperCase()}</span>
                    </div>
                    <div class="result-item">
                        <span class="label">Port:</span>
                        <span class="value">${detectionInfo.port}</span>
                    </div>
                    <div class="result-item">
                        <span class="label">Path:</span>
                        <span class="value">${detectionInfo.path}</span>
                    </div>
                </div>
                <div class="stream-url">
                    <span class="label">Stream URL:</span>
                    <code>${detectionInfo.stream_url}</code>
                </div>
            </div>
        `;
        
        resultsContainer.style.display = 'block';
    }
    
    /**
     * Form alanlarını otomatik doldur
     */
    autoFillCameraForm(cameraConfig) {
        const formFields = {
            'cameraIP': cameraConfig.ip_address,
            'cameraPort': cameraConfig.port,
            'cameraProtocol': cameraConfig.protocol,
            'cameraPath': cameraConfig.path
        };
        
        for (const [fieldId, value] of Object.entries(formFields)) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.value = value;
                
                // Select element için
                if (field.tagName === 'SELECT') {
                    const option = field.querySelector(`option[value="${value}"]`);
                    if (option) {
                        option.selected = true;
                    }
                }
            }
        }
        
        // Form değişikliklerini tetikle
        this.triggerFormChange();
    }
    
    /**
     * Hızlı kamera testi
     */
    async quickCameraTest() {
        const ipInput = document.getElementById('cameraIP');
        const ipAddress = ipInput ? ipInput.value.trim() : '';
        
        if (!ipAddress) {
            this.showNotification('IP adresi gerekli!', 'error');
            return;
        }
        
        this.showLoading('Hızlı test yapılıyor...');
        
        try {
            // Önce akıllı tespit yap
            const smartResult = await this.performSmartDetection(ipAddress);
            
            if (smartResult.success) {
                // Tespit edilen bilgilerle normal test yap
                const testResult = await this.performCameraTest(smartResult.camera_config);
                
                if (testResult.success) {
                    this.showNotification('✅ Kamera testi başarılı!', 'success');
                } else {
                    this.showNotification(`❌ Kamera testi başarısız: ${testResult.error}`, 'error');
                }
            } else {
                this.showNotification(`❌ Kamera tespit edilemedi: ${smartResult.error}`, 'error');
            }
            
        } catch (error) {
            this.showNotification(`❌ Test hatası: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    /**
     * Ağ tarama başlat
     */
    async startNetworkScan() {
        if (this.isScanning) {
            this.showNotification('Tarama zaten devam ediyor!', 'warning');
            return;
        }
        
        this.isScanning = true;
        this.scanProgress = 0;
        this.discoveredCameras = [];
        
        this.updateScanUI();
        this.showLoading('Ağ taraması başlatılıyor...');
        
        try {
            const response = await fetch(`/api/company/${this.getCompanyId()}/cameras/smart-discover`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    network_range: '192.168.1.0/24'
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.handleNetworkScanSuccess(result);
            } else {
                this.handleNetworkScanError(result.error);
            }
            
        } catch (error) {
            this.handleNetworkScanError(`Tarama hatası: ${error.message}`);
        } finally {
            this.isScanning = false;
            this.hideLoading();
            this.updateScanUI();
        }
    }
    
    /**
     * Ağ tarama başarılı sonucu işle
     */
    handleNetworkScanSuccess(result) {
        this.discoveredCameras = result.cameras || [];
        
        this.showNotification(
            `✅ Ağ taraması tamamlandı! ${this.discoveredCameras.length} kamera bulundu.`,
            'success'
        );
        
        this.displayDiscoveredCameras();
        this.updateScanProgress(100);
    }
    
    /**
     * Ağ tarama hatası işle
     */
    handleNetworkScanError(error) {
        this.showNotification(`❌ Ağ taraması başarısız: ${error}`, 'error');
        this.updateScanProgress(0);
    }
    
    /**
     * Keşfedilen kameraları göster
     */
    displayDiscoveredCameras() {
        const container = document.getElementById('discoveredCameras');
        if (!container) return;
        
        if (this.discoveredCameras.length === 0) {
            container.innerHTML = '<p class="no-cameras">Keşfedilen kamera bulunamadı.</p>';
            return;
        }
        
        let html = '<div class="discovered-cameras-grid">';
        
        this.discoveredCameras.forEach((camera, index) => {
            const confidenceColor = camera.confidence > 0.8 ? 'green' : 
                                   camera.confidence > 0.6 ? 'orange' : 'red';
            
            html += `
                <div class="camera-card" data-index="${index}">
                    <div class="camera-header">
                        <h4>${camera.model}</h4>
                        <span class="confidence" style="color: ${confidenceColor}">
                            ${(camera.confidence * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="camera-details">
                        <p><strong>IP:</strong> ${camera.ip}</p>
                        <p><strong>Protokol:</strong> ${camera.protocol.toUpperCase()}</p>
                        <p><strong>Port:</strong> ${camera.port}</p>
                        <p><strong>Path:</strong> ${camera.path}</p>
                    </div>
                    <div class="camera-actions">
                        <button class="btn btn-sm btn-primary" onclick="smartDetection.testCamera(${index})">
                            Test Et
                        </button>
                        <button class="btn btn-sm btn-success" onclick="smartDetection.addCamera(${index})">
                            Ekle
                        </button>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        container.innerHTML = html;
    }
    
    /**
     * Keşfedilen kamerayı test et
     */
    async testCamera(index) {
        const camera = this.discoveredCameras[index];
        if (!camera) return;
        
        this.showLoading(`${camera.ip} test ediliyor...`);
        
        try {
            const result = await this.performSmartDetection(camera.ip);
            
            if (result.success) {
                this.showNotification(`✅ ${camera.ip} testi başarılı!`, 'success');
            } else {
                this.showNotification(`❌ ${camera.ip} testi başarısız: ${result.error}`, 'error');
            }
            
        } catch (error) {
            this.showNotification(`❌ Test hatası: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    /**
     * Keşfedilen kamerayı ekle
     */
    async addCamera(index) {
        const camera = this.discoveredCameras[index];
        if (!camera) return;
        
        this.showLoading(`${camera.ip} ekleniyor...`);
        
        try {
            const cameraData = {
                name: `${camera.model} ${camera.ip}`,
                ip_address: camera.ip,
                port: camera.port,
                protocol: camera.protocol,
                stream_path: camera.path,
                username: '',
                password: ''
            };
            
            const response = await fetch(`/api/company/${this.getCompanyId()}/cameras`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(cameraData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`✅ ${camera.ip} başarıyla eklendi!`, 'success');
                this.discoveredCameras.splice(index, 1);
                this.displayDiscoveredCameras();
            } else {
                this.showNotification(`❌ Ekleme başarısız: ${result.error}`, 'error');
            }
            
        } catch (error) {
            this.showNotification(`❌ Ekleme hatası: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    /**
     * Otomatik kamera ekleme
     */
    async autoAddDiscoveredCameras() {
        if (this.discoveredCameras.length === 0) {
            this.showNotification('Eklenecek kamera bulunamadı!', 'warning');
            return;
        }
        
        const confirmed = confirm(`${this.discoveredCameras.length} kamerayı otomatik olarak eklemek istiyor musunuz?`);
        if (!confirmed) return;
        
        this.showLoading('Kamerlar otomatik ekleniyor...');
        
        let successCount = 0;
        let errorCount = 0;
        
        for (let i = 0; i < this.discoveredCameras.length; i++) {
            try {
                await this.addCamera(i);
                successCount++;
            } catch (error) {
                errorCount++;
            }
        }
        
        this.hideLoading();
        
        this.showNotification(
            `✅ Otomatik ekleme tamamlandı!<br>
             Başarılı: ${successCount}<br>
             Başarısız: ${errorCount}`,
            successCount > 0 ? 'success' : 'error'
        );
    }
    
    /**
     * Yardımcı fonksiyonlar
     */
    validateIPAddress(ip) {
        const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
        return ipRegex.test(ip);
    }
    
    getCompanyId() {
        if (!this.currentCompanyId) {
            // URL'den company ID'yi al
            const pathParts = window.location.pathname.split('/');
            const companyIndex = pathParts.indexOf('company');
            if (companyIndex !== -1 && pathParts[companyIndex + 1]) {
                this.currentCompanyId = pathParts[companyIndex + 1];
            }
        }
        return this.currentCompanyId || 'DEFAULT_COMPANY';
    }
    
    showLoading(message) {
        const loadingEl = document.getElementById('loadingOverlay');
        if (loadingEl) {
            loadingEl.querySelector('.loading-message').textContent = message;
            loadingEl.style.display = 'flex';
        }
    }
    
    hideLoading() {
        const loadingEl = document.getElementById('loadingOverlay');
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = message;
        
        document.body.appendChild(notification);
        
        // 5 saniye sonra kaldır
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
    
    updateScanUI() {
        const scanBtn = document.getElementById('networkScanBtn');
        const progressBar = document.getElementById('scanProgress');
        
        if (scanBtn) {
            scanBtn.textContent = this.isScanning ? 'Taranıyor...' : 'Ağ Tara';
            scanBtn.disabled = this.isScanning;
        }
        
        if (progressBar) {
            progressBar.style.width = `${this.scanProgress}%`;
            progressBar.textContent = `${this.scanProgress}%`;
        }
    }
    
    updateScanProgress(progress) {
        this.scanProgress = progress;
        this.updateScanUI();
    }
    
    triggerFormChange() {
        // Form değişiklik event'ini tetikle
        const event = new Event('change', { bubbles: true });
        document.querySelector('#cameraIP').dispatchEvent(event);
    }
    
    async performSmartDetection(ipAddress) {
        const response = await fetch(`/api/company/${this.getCompanyId()}/cameras/smart-test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip_address: ipAddress })
        });
        return await response.json();
    }
    
    async performCameraTest(cameraConfig) {
        const response = await fetch(`/api/company/${this.getCompanyId()}/cameras/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cameraConfig)
        });
        return await response.json();
    }
}

// Global instance
const smartDetection = new SmartCameraDetection();

// Sayfa yüklendiğinde başlat
document.addEventListener('DOMContentLoaded', () => {
    console.log('🎥 Smart Camera Detection System initialized');
}); 