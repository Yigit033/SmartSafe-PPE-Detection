#!/usr/bin/env python3
"""
SH17 API Integration
SmartSafe AI - PPE Detection API Enhancement
"""

import os
import sys
import json
import base64
import logging
import cv2
import numpy as np
from flask import Flask, request, jsonify
from models.sh17_model_manager import SH17ModelManager

logger = logging.getLogger(__name__)

class SH17API:
    def __init__(self):
        self.model_manager = SH17ModelManager()
        self.model_manager.load_models()
        self.app = Flask(__name__)
        self.setup_routes()
        
    def setup_routes(self):
        """API route'larını kur"""
        
        @self.app.route('/api/sh17/detect', methods=['POST'])
        def detect_ppe():
            """SH17 PPE tespiti"""
            try:
                data = request.get_json()
                image_data = data.get('image')
                sector = data.get('sector', 'base')
                confidence = data.get('confidence', 0.5)
                
                if not image_data:
                    return jsonify({'success': False, 'error': 'Image data required'}), 400
                
                if image_data.startswith('data:image'):
                    image_data = image_data.split(',')[1]
                
                image_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(image_bytes, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if image is None:
                    return jsonify({'success': False, 'error': 'Invalid image data'}), 400
                
                # PPE tespiti yap
                detections = self.model_manager.detect_sector_specific(
                    image, sector, confidence
                )
                
                return jsonify({
                    'success': True,
                    'detections': detections,
                    'sector': sector,
                    'total_detections': len(detections)
                })
                
            except Exception as e:
                logger.error(f"SH17 detection error: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Detection failed'
                }), 500
                
        @self.app.route('/api/sh17/compliance', methods=['POST'])
        def analyze_compliance():
            """PPE uyumluluk analizi"""
            try:
                data = request.get_json()
                image_data = data.get('image')
                sector = data.get('sector', 'construction')
                required_ppe = data.get('required_ppe', [])
                
                if not image_data:
                    return jsonify({'success': False, 'error': 'Image data required'}), 400
                
                if image_data.startswith('data:image'):
                    image_data = image_data.split(',')[1]
                
                image_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(image_bytes, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if image is None:
                    return jsonify({'success': False, 'error': 'Invalid image data'}), 400
                
                detections = self.model_manager.detect_sector_specific(
                    image, sector, 0.5
                )
                
                compliance = self.model_manager.analyze_compliance(
                    detections, required_ppe
                )
                
                return jsonify({
                    'success': True,
                    'compliance': compliance,
                    'detections': detections,
                    'sector': sector
                })
                
            except Exception as e:
                logger.error(f"Compliance analysis error: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Compliance analysis failed'
                }), 500
                
        @self.app.route('/api/sh17/sectors', methods=['GET'])
        def get_sectors():
            """Desteklenen sektörleri listele"""
            sectors = list(self.model_manager.sector_mapping.keys())
            return jsonify({
                'success': True,
                'sectors': sectors,
                'sector_mapping': self.model_manager.sector_mapping
            })
            
        @self.app.route('/api/sh17/performance', methods=['GET'])
        def get_performance():
            """Model performans metriklerini al"""
            sector = request.args.get('sector', 'base')
            performance = self.model_manager.get_model_performance(sector)
            
            return jsonify({
                'success': True,
                'sector': sector,
                'performance': performance
            })
            
        @self.app.route('/api/sh17/health', methods=['GET'])
        def health_check():
            """SH17 model sağlık kontrolü"""
            loaded_models = list(self.model_manager.models.keys())
            return jsonify({
                'success': True,
                'status': 'healthy',
                'loaded_models': loaded_models,
                'total_models': len(loaded_models),
                'device': self.model_manager.device
            })

def integrate_with_existing_api():
    """Mevcut API'ye SH17 entegrasyonu"""
    
    # Mevcut smartsafe_saas_api.py'ye eklenecek kodlar
    integration_code = '''
# SH17 Model Integration
from models.sh17_model_manager import SH17ModelManager

# Global SH17 model manager
sh17_manager = SH17ModelManager()
sh17_manager.load_models()

@app.route('/api/company/<company_id>/dvr/<dvr_id>/ppe_detection/<int:channel_number>', methods=['POST'])
def ppe_detection(company_id, dvr_id, channel_number):
    """SH17 PPE tespiti endpoint'i"""
    try:
        # Stream'den frame al
        stream_id = f"{dvr_id}_ch{channel_number:02d}"
        frame_data = stream_handler.get_latest_frame(stream_id)
        
        if not frame_data:
            return jsonify({'success': False, 'error': 'No frame available'})
            
        # Base64'ü decode et
        image_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Şirket sektörünü al
        company = database.get_company(company_id)
        sector = company.get('sector', 'construction')
        
        # PPE tespiti yap
        detections = sh17_manager.detect_sector_specific(image, sector)
        
        return jsonify({
            'success': True,
            'detections': detections,
            'sector': sector,
            'channel': channel_number
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/company/<company_id>/dvr/<dvr_id>/compliance/<int:channel_number>', methods=['POST'])
def compliance_analysis(company_id, dvr_id, channel_number):
    """PPE uyumluluk analizi"""
    try:
        data = request.get_json()
        required_ppe = data.get('required_ppe', [])
        
        # Stream'den frame al
        stream_id = f"{dvr_id}_ch{channel_number:02d}"
        frame_data = stream_handler.get_latest_frame(stream_id)
        
        if not frame_data:
            return jsonify({'success': False, 'error': 'No frame available'})
            
        # Base64'ü decode et
        image_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Şirket sektörünü al
        company = database.get_company(company_id)
        sector = company.get('sector', 'construction')
        
        # Tespit ve uyumluluk analizi
        detections = sh17_manager.detect_sector_specific(image, sector)
        compliance = sh17_manager.analyze_compliance(detections, required_ppe)
        
        return jsonify({
            'success': True,
            'compliance': compliance,
            'detections': detections,
            'sector': sector,
            'channel': channel_number
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
'''
    
    return integration_code

def main():
    """Test server'ı başlat"""
    api = SH17API()
    print("🚀 SH17 API Server başlatılıyor...")
    print("📍 Endpoints:")
    print("- POST /api/sh17/detect")
    print("- POST /api/sh17/compliance")
    print("- GET /api/sh17/sectors")
    print("- GET /api/sh17/performance")
    print("- GET /api/sh17/health")
    
    api.app.run(host='0.0.0.0', port=5001, debug=True)

if __name__ == "__main__":
    main() 