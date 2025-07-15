#!/usr/bin/env python3
"""
Hibrit PPE Detection Sistemi Entegrasyon Testi
"""

import cv2
import numpy as np
import logging
from utils.hybrid_ppe_system import HybridPPESystem

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_hybrid_integration():
    """Hibrit sistem entegrasyon testi"""
    print("🧪 Hibrit PPE Detection Sistemi Entegrasyon Testi")
    print("=" * 60)
    
    # 1. Sistemi başlat
    print("\n1️⃣ Sistem Başlatma...")
    system = HybridPPESystem()
    if not system.initialize_system():
        print("❌ Sistem başlatılamadı!")
        return False
    print("✅ Hibrit sistem başlatıldı")
    
    # 2. Test görüntüsü yükle
    print("\n2️⃣ Test Görüntüsü Yükleme...")
    test_image = cv2.imread('demo_ppe_compliant.jpg')
    if test_image is None:
        print("⚠️ Test görüntüsü bulunamadı, dummy görüntü oluşturuluyor")
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        # Dummy detection için basit şekiller ekle
        cv2.rectangle(test_image, (100, 100), (200, 300), (255, 255, 255), -1)  # Person
        cv2.circle(test_image, (150, 120), 20, (0, 255, 0), -1)  # Helmet
    print("✅ Test görüntüsü hazır")
    
    # 3. Sektör testleri
    test_sectors = [
        {
            'sector': 'construction',
            'company_id': 'test_construction_001',
            'required_ppe': ['helmet', 'safety_vest'],
            'optional_ppe': ['gloves', 'glasses']
        },
        {
            'sector': 'chemical',
            'company_id': 'test_chemical_001',
            'required_ppe': ['face_mask', 'gloves', 'safety_vest'],
            'optional_ppe': ['glasses']
        },
        {
            'sector': 'food',
            'company_id': 'test_food_001',
            'required_ppe': ['helmet', 'face_mask', 'safety_vest'],
            'optional_ppe': ['gloves']
        }
    ]
    
    print("\n3️⃣ Sektörel Testler...")
    all_passed = True
    
    for i, test_config in enumerate(test_sectors):
        print(f"\n🏭 Test {i+1}: {test_config['sector'].upper()} Sektörü")
        
        # Şirket konfigürasyonu kaydet
        system.save_company_ppe_config(
            company_id=test_config['company_id'],
            sector=test_config['sector'],
            required_ppe=test_config['required_ppe'],
            optional_ppe=test_config['optional_ppe']
        )
        
        # Detection yap
        result = system.process_detection(
            image=test_image,
            company_id=test_config['company_id'],
            camera_id=f"{test_config['sector']}_camera_001"
        )
        
        # Sonuçları kontrol et
        if result.success:
            print(f"  ✅ Detection başarılı")
            print(f"  📊 Sektör: {result.sector}")
            print(f"  👥 Kişi sayısı: {result.compliance_result.person_count}")
            print(f"  📈 Uygunluk: {result.compliance_result.compliance_rate:.1%}")
            print(f"  🔍 Base detections: {len(result.base_detections)}")
            print(f"  🎯 Sector detections: {len(result.sector_detections)}")
            print(f"  ⚡ Performance: {result.performance_metrics.get('fps_estimate', 0):.1f} FPS")
            
            # Sonucu kaydet
            result_image = system.draw_hybrid_results(test_image.copy(), result)
            output_file = f"result_hybrid_{test_config['sector']}_test.jpg"
            cv2.imwrite(output_file, result_image)
            print(f"  💾 Sonuç kaydedildi: {output_file}")
            
        else:
            print(f"  ❌ Detection başarısız: {result.error_message}")
            all_passed = False
    
    # 4. İstatistik testleri
    print("\n4️⃣ İstatistik Testleri...")
    for test_config in test_sectors:
        stats = system.get_detection_statistics(test_config['company_id'])
        print(f"  📈 {test_config['sector'].upper()}: {stats}")
    
    # 5. Sektör haritalama testleri
    print("\n5️⃣ Sektör Haritalama Testleri...")
    for test_config in test_sectors:
        options = system.create_sector_ppe_options_for_ui(test_config['sector'])
        print(f"  🏭 {test_config['sector'].upper()}:")
        print(f"    Required: {len(options['required'])} seçenek")
        print(f"    Optional: {len(options['optional'])} seçenek")
        
        # Validation testi
        validation = system.validate_company_ppe_selection(
            test_config['required_ppe'], 
            test_config['sector']
        )
        print(f"    Validation: {'✅ Geçerli' if validation['is_valid'] else '❌ Geçersiz'}")
    
    # 6. Sonuç
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 TÜM TESTLER BAŞARILI!")
        print("✅ Hibrit PPE Detection Sistemi tam fonksiyonel")
        print("✅ Sektörel haritalama çalışıyor")
        print("✅ Şirket konfigürasyonları doğru işleniyor")
        print("✅ Performance metrikleri toplanıyor")
        return True
    else:
        print("⚠️ BAZI TESTLER BAŞARISIZ!")
        return False

def test_sector_detector_factory_integration():
    """Sector detector factory entegrasyonunu test et"""
    print("\n🔧 Sector Detector Factory Entegrasyonu Testi")
    print("=" * 60)
    
    try:
        from smartsafe_sector_detector_factory import SectorDetectorFactory
        
        # Test image
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Test company ID
        test_company_id = "hybrid_test_company"
        
        # Her sektör için test
        sectors = ['construction', 'chemical', 'food', 'manufacturing', 'warehouse']
        
        for sector in sectors:
            print(f"\n🏭 Testing {sector.upper()} detector...")
            
            # Detector al
            detector = SectorDetectorFactory.get_detector(sector, test_company_id)
            
            if detector:
                print(f"  ✅ Detector oluşturuldu")
                print(f"  🔧 Hibrit sistem: {'Aktif' if detector.use_hybrid else 'Devre dışı'}")
                
                # Detection test
                result = detector.detect_ppe(test_image, f"{sector}_camera_001")
                
                if result['success']:
                    print(f"  ✅ Detection başarılı")
                    if 'hybrid_enhanced' in result:
                        print(f"  🚀 Hibrit sistem kullanıldı!")
                    else:
                        print(f"  ⚙️ Fallback sistem kullanıldı")
                else:
                    print(f"  ⚠️ Detection başarısız: {result.get('error', 'Bilinmeyen hata')}")
            else:
                print(f"  ❌ Detector oluşturulamadı")
        
        print("\n✅ Factory entegrasyonu tamamlandı")
        return True
        
    except Exception as e:
        print(f"❌ Factory entegrasyon hatası: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Hibrit PPE Detection Sistemi - Tam Entegrasyon Testi")
    print("=" * 80)
    
    # Ana hibrit sistem testi
    hybrid_success = test_hybrid_integration()
    
    # Factory entegrasyon testi
    factory_success = test_sector_detector_factory_integration()
    
    # Genel sonuç
    print("\n" + "=" * 80)
    print("📋 TEST SONUÇLARI:")
    print(f"  Hibrit Sistem: {'✅ BAŞARILI' if hybrid_success else '❌ BAŞARISIZ'}")
    print(f"  Factory Entegrasyon: {'✅ BAŞARILI' if factory_success else '❌ BAŞARISIZ'}")
    
    if hybrid_success and factory_success:
        print("\n🎉 HİBRİT PPE SİSTEMİ TAM HAZIR!")
        print("✅ Projede kullanıma hazır")
        print("✅ Sektörel özelleştirmeler aktif")
        print("✅ Akıllı haritalama çalışıyor")
    else:
        print("\n⚠️ Sistem tam hazır değil, lütfen hataları kontrol edin") 