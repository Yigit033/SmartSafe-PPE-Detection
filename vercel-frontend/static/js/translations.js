// Language translations object
const translations = {
    en: {
        // Navbar
        features: "Features",
        sectors: "Industries",
        benefits: "Benefits",
        contact: "Contact",
        login: "Sign In",

        // Hero Section
        hero_title: "Smart Eye, Safe Work",
        hero_description: "Advanced AI security system that monitors personal protective equipment (PPE) usage in real-time and prevents workplace accidents in industrial facilities.",
        get_started: "Get Started",

        // Performance Stats
        fps_realtime: "Real-time FPS",
        performance_increase: "Performance Boost",
        concurrent_cameras: "Simultaneous Cameras",
        continuous_operation: "24/7 Operation",

        // Features Section
        features_title: "Features",
        features_subtitle: "Advanced workplace safety capabilities",
        
        // Features Tab Navigation
        performance: "Performance",
        ai: "AI Technology",
        monitoring: "Monitoring",
        integration: "Integration",
        security: "Security",
        
        // Performance Tab
        high_performance: "High Performance",
        high_performance_desc: "Real-time detection with 24.7 frames per second processing capability.",
        gpu_optimization: "GPU Optimization",
        nvidia_cuda: "NVIDIA CUDA Support",
        low_latency: "Low Latency Processing",
        
        scalability: "Scalability",
        scalability_desc: "Flexible system architecture that scales with your needs.",
        horizontal_vertical: "Horizontal & Vertical Scaling",
        multi_location: "Multi-Site Support",
        load_balancing: "Intelligent Load Balancing",
        
        system_stability: "System Reliability",
        system_stability_desc: "Guaranteed uptime with uninterrupted operation.",
        auto_backup: "Automated Backup",
        fault_tolerance: "Fault Tolerance",
        continuous_work: "24/7 Operation",
        
        // AI Tab
        ai_title: "Artificial Intelligence",
        ai_desc: "Precision detection powered by advanced deep learning models.",
        realtime_analysis: "Real-time Analysis",
        high_accuracy: "High Accuracy Detection",
        continuous_learning: "Continuous Learning",
        
        smart_analytics: "Smart Analytics",
        smart_analytics_desc: "Advanced data analysis and predictive insights.",
        anomaly_detection: "Anomaly Detection",
        behavior_analysis: "Behavioral Analysis",
        predictive_maintenance: "Predictive Maintenance",
        
        automation: "Automation",
        automation_desc: "Intelligent workflows and automated responses.",
        event_triggering: "Event-Based Triggers",
        smart_alerts: "Smart Alerts",
        auto_reporting: "Automated Reporting",

        // Monitoring Features
        multi_camera_support: "Multi-Camera Support",
        multi_camera_desc: "Simultaneous monitoring and analysis of up to 100+ cameras.",
        ip_camera_integration: "IP Camera Integration",
        auto_load_balancing: "Automatic Load Balancing",
        continuous_monitoring: "Continuous Monitoring",

        smart_alert_system: "Smart Alert System",
        alert_system_desc: "Instant notifications with customizable alert mechanisms.",
        email_notifications: "Email Notifications",
        mobile_notifications: "Mobile Notifications",

        reporting_analytics: "Reporting & Analytics",
        reporting_desc: "Comprehensive statistics and customizable reporting system.",
        custom_dashboards: "Custom Dashboards",
        excel_pdf_export: "Excel/PDF Export",
        trend_analysis: "Trend Analysis",
        
        // Integration Tab
        easy_integration: "Seamless Integration",
        easy_integration_desc: "Effortless integration with existing systems.",
        rest_api_support: "REST API Support",
        erp_integration: "ERP Integration",
        custom_integration: "Custom Integration Support",
        
        cloud_support: "Cloud Support",
        cloud_support_desc: "Flexible cloud infrastructure and hybrid solutions.",
        aws_azure_gcp: "AWS/Azure/GCP Support",
        private_cloud: "Private Cloud Solutions",
        hybrid_configuration: "Hybrid Configuration",
        
        support_247: "24/7 Support",
        support_247_desc: "Round-the-clock technical support and maintenance services.",
        live_support: "Live Support",
        remote_intervention: "Remote Assistance",
        periodic_maintenance: "Scheduled Maintenance",
        
        // Security Tab
        advanced_security: "Advanced Security",
        advanced_security_desc: "Enterprise-grade data protection with highest security standards.",
        ssl_tls_encryption: "SSL/TLS Encryption",
        role_based_access: "Role-Based Access Control",
        data_backup: "Data Backup & Recovery",
        
        user_management: "User Management",
        user_management_desc: "Comprehensive user authorization and access control.",
        multi_level_auth: "Multi-Level Authorization",
        activity_logs: "Activity Logging",
        sso_support: "Single Sign-On (SSO)",
        
        data_security: "Data Security",
        data_security_desc: "End-to-end data security and regulatory compliance.",
        gdpr_compliance: "GDPR Compliance",
        data_encryption: "Data Encryption",
        secure_storage: "Secure Storage",

        // Sectors
        sectors_title: "Industry Solutions",
        sectors_subtitle: "Tailored safety solutions for every industry",
        
        // Construction Sector
        construction: "Construction",
        helmet_detection: "Hard Hat Detection",
        vest_control: "Safety Vest Monitoring",
        safety_glasses: "Safety Glasses",
        steel_toe_boots: "Steel-Toe Boots",
        work_gloves: "Work Gloves",
        safety_harness: "Safety Harness",

        // Maritime Sector
        maritime: "Maritime & Shipyard",
        life_jacket: "Life Jacket",
        waterproof_ppe: "Waterproof PPE",
        high_protection: "High-Visibility Protection",
        helmet: "Hard Hat",
        steel_toe_shoes: "Steel-Toe Footwear",
        work_gloves_maritime: "Work Gloves",
        safety_harness_maritime: "Safety Harness",

        // Chemical Industry
        chemical: "Chemical Industry",
        mask_control: "Respiratory Protection",
        glove_detection: "Chemical-Resistant Gloves",
        protective_clothing: "Protective Clothing",

        // Manufacturing
        manufacturing: "Manufacturing",
        multi_ppe: "Multi-PPE Detection",
        instant_reporting: "Real-time Reporting",
        shift_tracking: "Shift Monitoring",

        // Food Industry
        food: "Food Industry",
        hairnet_control: "Hair Net Compliance",
        hygiene_gloves: "Hygiene Gloves",
        apron_detection: "Apron Detection",
        
        // Energy Sector
        energy: "Energy Sector",
        insulated_equipment: "Insulated Equipment",
        arc_flash_protection: "Arc Flash Protection",
        dielectric_ppe: "Dielectric PPE",
        
        // Petrochemical
        petrochemical: "Petrochemical",
        gas_mask: "Gas Mask",
        chemical_hazard: "Chemical Hazard Protection",
        special_equipment: "Specialized Equipment",
        
        // Aviation
        aviation: "Aviation",
        headset_control: "Headset Monitoring",
        antistatic_ppe: "Anti-Static PPE",

        // Benefits
        benefits_title: "Benefits",
        benefits_subtitle: "Why choose our solution",
        
        // Benefits Tab Navigation
        financial: "Financial",
        operational: "Operational",
        safety: "Safety",
        technological: "Technology",
        legal: "Compliance",

        // Financial Benefits
        financial_benefits: "Financial Benefits",
        financial_desc: "Rapid ROI and long-term financial advantages through workplace safety investments",
        accident_cost_reduction: "Accident cost reduction",
        insurance_premium_reduction: "Lower insurance premiums",
        compliance_cost_reduction: "Reduced compliance costs",
        productivity_increase: "Increased productivity",
        operational_efficiency: "Enhanced operational efficiency",
        resource_optimization: "Resource optimization",

        // Operational Benefits
        operational_benefits: "Operational Benefits",
        operational_desc: "Smart solutions that streamline processes and boost efficiency",
        realtime_monitoring: "Real-time monitoring and alert system",
        automatic_documentation: "Automated reporting and documentation",
        employee_safety: "Enhanced employee safety",
        audit_simplification: "Streamlined audit processes",
        sector_optimized: "Industry-specific optimizations",
        continuous_monitoring_247: "24/7 continuous monitoring",
        mobile_access: "Mobile app remote access",
        smart_workflow: "Intelligent workflow automation",

        // Safety Benefits
        safety_benefits: "Safety Benefits",
        safety_desc: "Comprehensive workplace safety advantages",
        proactive_risk: "Proactive risk management",
        violation_detection: "Instant violation detection and response",
        safety_awareness: "Enhanced safety awareness",
        accident_prevention: "Improved accident prevention",
        compliance_management: "Compliance management",
        safety_culture: "Strengthened safety culture",
        risk_analysis: "Advanced risk analysis",
        emergency_response: "Rapid emergency response",

        // Technology Benefits
        tech_benefits: "Technology Advantages",
        tech_desc: "Future-ready solutions powered by cutting-edge AI technology",
        ai_detection: "AI-powered precision detection",
        learning_system: "Continuously learning and evolving system",
        easy_integration: "Seamless integration and scalability",
        custom_alerts: "Customizable alert mechanisms",
        realtime_ai: "Real-time AI analysis",
        cloud_integration: "Cloud integration",
        api_support: "API support",
        mobile_compatibility: "Mobile compatibility",

        // Page Title
        page_title: "SmartSafe AI - Industrial PPE Detection System",

        // Maritime Sector Items
        maritime_life_jacket: "Life Jacket",
        maritime_waterproof: "Waterproof PPE",
        maritime_high_protection: "High-Visibility Protection",
        maritime_helmet: "Hard Hat",
        maritime_steel_toe: "Steel-Toe Boots",
        maritime_gloves: "Work Gloves",
        maritime_harness: "Safety Harness",

        // Contact Form Sectors
        sector_construction: "Construction",
        sector_chemical: "Chemical",
        sector_food: "Food & Beverage",
        sector_manufacturing: "Manufacturing",
        sector_energy: "Energy",
        sector_petrochemical: "Petrochemical",
        sector_marine: "Maritime & Shipyard",
        sector_aviation: "Aviation",
        sector_other: "Other",

        // Form Placeholders
        name_placeholder: "Your Name",
        email_placeholder: "Your Email Address",
        company_placeholder: "Company Name",
        phone_placeholder: "Phone Number",
        message_placeholder: "Your Message",
        select_sector: "Select Industry",
        send: "Send Message",
        
        // Contact Info
        contact_title: "Get in Touch",
        contact_subtitle: "Contact us for inquiries, quotes, or partnership opportunities. We'll respond promptly.",
        contact_email: "yigittilaver2000@gmail.com",
        contact_phone: "+90 (505) 020 20 95",
        contact_address: "Maslak, Istanbul",
        
        // Legal Benefits
        legal_benefits: "Legal Compliance",
        legal_desc: "Solutions ensuring full regulatory compliance and streamlined legal processes",
        legal_ohs_compliance: "Full OHS compliance",
        legal_audit_reports: "Automated audit reports",
        legal_documentation: "Legal documentation support",
        legal_certification: "Certification process assistance",
        legal_data_processing: "GDPR-compliant data processing",
        legal_audit_prep: "Audit preparation support",
        legal_reporting: "Automated legal reporting",
        legal_compliance_tracking: "Compliance tracking system",

        // Contact Form
        sector_placeholder: "Select Your Industry",
        
        // Footer
        footer_description: "Transforming workplace safety with AI-powered industrial security solutions.",
        footer_contact: "Contact",
        footer_solutions: "Solutions",
        footer_features: "Features",
        footer_sector_solutions: "Industry Solutions",
        footer_safety_benefits: "Safety Benefits",
        footer_live_demo: "Live Demo",
        footer_company_register: "Company Registration",
        footer_support: "Support",
        footer_technical_support: "Technical Support",
        footer_presales_support: "Pre-Sales Support",
        footer_demo_request: "Request Demo",
        footer_pricing: "Pricing",
        footer_sector_consulting: "Industry Consulting",
        all_rights_reserved: "© 2025 SmartSafe AI. All rights reserved.",
        privacy_policy: "Privacy Policy",
        terms_of_use: "Terms of Service"
    },
    tr: {
        // Navbar
        features: "Özellikler",
        sectors: "Sektörler",
        benefits: "Faydalar",
        contact: "İletişim",
        login: "Giriş Yap",

        // Hero Section
        hero_title: "Akıllı Göz, Güvenli İş",
        hero_description: "Endüstriyel tesislerde kişisel koruyucu donanım (KKD) kullanımını gerçek zamanlı izleyen ve iş kazalarını önleyen akıllı güvenlik sistemi.",
        get_started: "Hemen Başla",

        // Performance Stats
        fps_realtime: "FPS Gerçek Zamanlı",
        performance_increase: "Performans Artışı",
        concurrent_cameras: "Eş Zamanlı Kamera",
        continuous_operation: "Kesintisiz Çalışma",

        // Features Section
        features_title: "Özellikler",
        features_subtitle: "İş güvenliği için gelişmiş özellikler",
        
        // Features Tab Navigation
        performance: "Performans",
        ai: "Yapay Zeka",
        monitoring: "İzleme",
        integration: "Entegrasyon",
        security: "Güvenlik",
        
        // Performance Tab
        high_performance: "Yüksek Performans",
        high_performance_desc: "Saniyede 24.7 kare işleme kapasitesi ile gerçek zamanlı tespit.",
        gpu_optimization: "GPU Optimizasyonu",
        nvidia_cuda: "NVIDIA CUDA Desteği",
        low_latency: "Düşük Gecikme",
        
        scalability: "Ölçeklenebilirlik",
        scalability_desc: "İhtiyaçlara göre büyüyebilen esnek sistem mimarisi.",
        horizontal_vertical: "Yatay/Dikey Ölçeklendirme",
        multi_location: "Çok Lokasyon Desteği",
        load_balancing: "Yük Dengeleme",
        
        system_stability: "Sistem Kararlılığı",
        system_stability_desc: "Kesintisiz çalışma ve yüksek çalışma süresi garantisi.",
        auto_backup: "Otomatik Yedekleme",
        fault_tolerance: "Hata Toleransı",
        continuous_work: "7/24 Çalışma",
        
        // AI Tab
        ai_title: "Yapay Zeka",
        ai_desc: "Gelişmiş derin öğrenme modelleri ile hassas tespit.",
        realtime_analysis: "Gerçek Zamanlı Analiz",
        high_accuracy: "Yüksek Doğruluk",
        continuous_learning: "Sürekli Öğrenme",
        
        smart_analytics: "Akıllı Analitik",
        smart_analytics_desc: "İleri seviye veri analizi ve tahminleme.",
        anomaly_detection: "Anomali Tespiti",
        behavior_analysis: "Davranış Analizi",
        predictive_maintenance: "Tahminsel Bakım",
        
        automation: "Otomasyon",
        automation_desc: "Akıllı iş akışları ve otomatik aksiyonlar.",
        event_triggering: "Olay Tetikleme",
        smart_alerts: "Akıllı Alarmlar",
        auto_reporting: "Otomatik Raporlama",

        // Monitoring Features
        multi_camera_support: "Çoklu Kamera Desteği",
        multi_camera_desc: "100+ kameraya kadar eş zamanlı izleme ve analiz kapasitesi.",
        ip_camera_integration: "IP Kamera Entegrasyonu",
        auto_load_balancing: "Otomatik Yük Dengeleme",
        continuous_monitoring: "Kesintisiz İzleme",

        smart_alert_system: "Akıllı Uyarı Sistemi",
        alert_system_desc: "Anlık bildirimler ve özelleştirilebilir uyarı mekanizması.",
        email_notifications: "E-posta Bildirimleri",
        mobile_notifications: "Mobil Bildirimler",

        reporting_analytics: "Raporlama ve Analitik",
        reporting_desc: "Detaylı istatistikler ve özelleştirilebilir raporlama sistemi.",
        custom_dashboards: "Özelleştirilebilir Dashboardlar",
        excel_pdf_export: "Excel/PDF Export",
        trend_analysis: "Trend Analizi",
        
        // Integration Tab
        easy_integration: "Kolay Entegrasyon",
        easy_integration_desc: "Mevcut sistemlerle sorunsuz entegrasyon imkanı.",
        rest_api_support: "REST API Desteği",
        erp_integration: "ERP Entegrasyonu",
        custom_integration: "Özel Entegrasyon Desteği",
        
        cloud_support: "Bulut Desteği",
        cloud_support_desc: "Esnek bulut altyapısı ve hibrit çözümler.",
        aws_azure_gcp: "AWS/Azure/GCP Desteği",
        private_cloud: "Özel Bulut Çözümleri",
        hybrid_configuration: "Hibrit Yapılandırma",
        
        support_247: "7/24 Destek",
        support_247_desc: "Kesintisiz teknik destek ve bakım hizmetleri.",
        live_support: "Canlı Destek",
        remote_intervention: "Uzaktan Müdahale",
        periodic_maintenance: "Periyodik Bakım",
        
        // Security Tab
        advanced_security: "Gelişmiş Güvenlik",
        advanced_security_desc: "En üst düzey güvenlik standartları ile veri koruma.",
        ssl_tls_encryption: "SSL/TLS Şifreleme",
        role_based_access: "Rol Tabanlı Erişim",
        data_backup: "Veri Yedekleme",
        
        user_management: "Kullanıcı Yönetimi",
        user_management_desc: "Detaylı yetkilendirme ve kullanıcı kontrolü.",
        multi_level_auth: "Çok Seviyeli Yetkilendirme",
        activity_logs: "Aktivite Logları",
        sso_support: "SSO Desteği",
        
        data_security: "Veri Güvenliği",
        data_security_desc: "Uçtan uca veri güvenliği ve uyumluluk.",
        gdpr_compliance: "KVKK Uyumluluğu",
        data_encryption: "Veri Şifreleme",
        secure_storage: "Güvenli Depolama",

        // Sectors
        sectors_title: "Sektörel Çözümler",
        sectors_subtitle: "Her sektör için optimize edilmiş güvenlik çözümleri",
        
        // Construction Sector
        construction: "İnşaat Sektörü",
        helmet_detection: "Baret Tespiti",
        vest_control: "Yelek Kontrolü",
        safety_glasses: "İş Gözlüğü",
        steel_toe_boots: "Çelik Burunlu Bot",
        work_gloves: "İş Eldiveni",
        safety_harness: "Emniyet Kemeri",

        // Maritime Sector
        maritime: "Denizcilik & Tersane",
        life_jacket: "Can Yeleği",
        waterproof_ppe: "Su Geçirmez KKD",
        high_protection: "Yüksek Koruma",
        helmet: "Baret",
        steel_toe_shoes: "Çelik Burunlu Ayakkabı",
        work_gloves_maritime: "İş Eldiveni",
        safety_harness_maritime: "Emniyet Kemeri",

        // Chemical Industry
        chemical: "Kimya Endüstrisi",
        mask_control: "Maske Kontrolü",
        glove_detection: "Eldiven Tespiti",
        protective_clothing: "Koruyucu Giysi",

        // Manufacturing
        manufacturing: "Üretim Tesisleri",
        multi_ppe: "Çoklu KKD Tespiti",
        instant_reporting: "Anlık Raporlama",
        shift_tracking: "Vardiya Takibi",

        // Food Industry
        food: "Gıda Endüstrisi",
        hairnet_control: "Bone Kontrolü",
        hygiene_gloves: "Hijyen Eldiveni",
        apron_detection: "Önlük Tespiti",
        
        // Energy Sector
        energy: "Enerji",
        insulated_equipment: "İzolasyonlu Ekipman",
        arc_flash_protection: "Ark Flaş Koruması",
        dielectric_ppe: "Dielektrik KKD",
        
        // Petrochemical
        petrochemical: "Petrokimya",
        gas_mask: "Gaz Maskesi",
        chemical_hazard: "Kimyasal Tehlike",
        special_equipment: "Özel Ekipman",
        
        // Aviation
        aviation: "Havacılık",
        headset_control: "Kulaklık Kontrolü",
        antistatic_ppe: "Antistatik KKD",

        // Benefits
        benefits_title: "Faydalar",
        benefits_subtitle: "Çözümümüzün avantajları",
        
        // Benefits Tab Navigation
        financial: "Finansal",
        operational: "Operasyonel",
        safety: "İş Güvenliği",
        technological: "Teknolojik",
        legal: "Yasal",

        // Financial Benefits
        financial_benefits: "Finansal Avantajlar",
        financial_desc: "İş güvenliği yatırımınızın hızlı geri dönüşü ve uzun vadeli finansal faydaları",
        accident_cost_reduction: "İş kazası maliyetlerinin minimize edilmesi",
        insurance_premium_reduction: "Sigorta primi indirimi",
        compliance_cost_reduction: "Uyum maliyetlerinin azaltılması",
        productivity_increase: "Verimlilik artışı",
        operational_efficiency: "Operasyonel verimlilik",
        resource_optimization: "Kaynak optimizasyonu",

        // Operational Benefits
        operational_benefits: "Operasyonel Faydalar",
        operational_desc: "Süreçlerinizi optimize eden ve verimliliği artıran akıllı çözümler",
        realtime_monitoring: "Gerçek zamanlı izleme ve uyarı sistemi",
        automatic_documentation: "Otomatik raporlama ve dokümantasyon",
        employee_safety: "Çalışan güvenliğinin artırılması",
        audit_simplification: "Denetim süreçlerinin kolaylaştırılması",
        sector_optimized: "Sektöre özel optimize edilmiş çözümler",
        continuous_monitoring_247: "7/24 kesintisiz izleme",
        mobile_access: "Mobil uygulama ile uzaktan erişim",
        smart_workflow: "Akıllı iş akışı otomasyonu",

        // Safety Benefits
        safety_benefits: "İş Güvenliği Avantajları",
        safety_desc: "Kapsamlı iş güvenliği avantajları",
        proactive_risk: "Proaktif risk yönetimi",
        violation_detection: "Anlık ihlal tespiti ve müdahale",
        safety_awareness: "Çalışan güvenlik bilincinin artırılması",
        accident_prevention: "Kaza önleme oranında artış",
        compliance_management: "Uyum yönetimi",
        safety_culture: "Güvenlik kültürünün geliştirilmesi",
        risk_analysis: "Gelişmiş risk analizi",
        emergency_response: "Hızlı acil durum müdahalesi",

        // Technology Benefits
        tech_benefits: "Teknolojik Üstünlükler",
        tech_desc: "En son yapay zeka teknolojileri ile donatılmış gelecek odaklı çözümler",
        ai_detection: "Yapay zeka destekli hassas tespit",
        learning_system: "Sürekli öğrenen ve gelişen sistem",
        easy_integration: "Kolay entegrasyon ve ölçeklenebilirlik",
        custom_alerts: "Özelleştirilebilir uyarı mekanizmaları",
        realtime_ai: "Gerçek zamanlı AI analizi",
        cloud_integration: "Bulut entegrasyonu",
        api_support: "API desteği",
        mobile_compatibility: "Mobil uyumluluk",

        // Page Title
        page_title: "SmartSafe AI - Endüstriyel KKD Tespit Sistemi",

        // Maritime Sector Items
        maritime_life_jacket: "Can Yeleği",
        maritime_waterproof: "Su Geçirmez KKD",
        maritime_high_protection: "Yüksek Koruma",
        maritime_helmet: "Baret",
        maritime_steel_toe: "Çelik Burunlu Ayakkabı",
        maritime_gloves: "İş Eldiveni",
        maritime_harness: "Emniyet Kemeri",

        // Contact Form Sectors
        sector_construction: "İnşaat",
        sector_chemical: "Kimya",
        sector_food: "Gıda",
        sector_manufacturing: "Üretim",
        sector_energy: "Enerji",
        sector_petrochemical: "Petrokimya",
        sector_marine: "Denizcilik & Tersane",
        sector_aviation: "Havacılık",
        sector_other: "Diğer",

        // Form Placeholders
        name_placeholder: "Adınız",
        email_placeholder: "E-posta Adresiniz",
        company_placeholder: "Şirket Adı",
        phone_placeholder: "Telefon Numarası",
        message_placeholder: "Mesajınız",
        select_sector: "Sektör Seçin",
        send: "Gönder",
        
        // Contact Info
        contact_title: "İletişime Geçin",
        contact_subtitle: "Her türlü soru, teklif veya iş birliği için bize ulaşabilirsiniz. Size en kısa sürede dönüş yapacağız.",
        contact_email: "yigittilaver2000@gmail.com",
        contact_phone: "+90 (505) 020 20 95",
        contact_address: "Maslak, İstanbul",
        
        // Legal Benefits
        legal_benefits: "Yasal Uyumluluk",
        legal_desc: "Mevzuata tam uyumluluk ve yasal süreçlerde kolaylık sağlayan çözümler",
        legal_ohs_compliance: "İSG mevzuatına tam uyumluluk",
        legal_audit_reports: "Otomatik denetim raporları",
        legal_documentation: "Yasal dokümantasyon desteği",
        legal_certification: "Sertifikasyon süreçlerinde kolaylık",
        legal_data_processing: "KVKK uyumlu veri işleme",
        legal_audit_prep: "Denetim hazırlık desteği",
        legal_reporting: "Yasal raporlama otomasyonu",
        legal_compliance_tracking: "Uyumluluk takip sistemi",

        // Contact Form
        sector_placeholder: "Sektörünüz",
        
        // Footer
        footer_description: "Yapay zeka destekli endüstriyel güvenlik çözümleriyle iş yerinizi daha güvenli hale getiriyoruz.",
        footer_contact: "İletişim",
        footer_solutions: "Çözümlerimiz",
        footer_features: "Temel Özellikler",
        footer_sector_solutions: "Sektörel Çözümler",
        footer_safety_benefits: "İş Güvenliği Avantajları",
        footer_live_demo: "Canlı Demo",
        footer_company_register: "Şirket Kaydı",
        footer_support: "Destek",
        footer_technical_support: "Teknik Destek",
        footer_presales_support: "Satış Öncesi Destek",
        footer_demo_request: "Demo Talebi",
        footer_pricing: "Fiyatlandırma",
        footer_sector_consulting: "Sektörel Danışmanlık",
        all_rights_reserved: "© 2025 SmartSafe AI. Tüm hakları saklıdır.",
        privacy_policy: "Gizlilik Politikası",
        terms_of_use: "Kullanım Koşulları"
    }
};

// Initialize language handling
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing language handling...');
    
    // Initialize with stored language or default to Turkish
    const currentLang = localStorage.getItem('preferredLanguage') || 'tr';
    console.log('Initial language:', currentLang);
    
    try {
        // Update UI to reflect current language
        const languageBtn = document.querySelector('.language-btn');
        const flagImg = languageBtn.querySelector('img');
        const langText = languageBtn.querySelector('span');
        
        if (flagImg) {
            flagImg.src = `/static/images/flags/${currentLang}.png`;
            flagImg.alt = currentLang.toUpperCase();
        }
        if (langText) {
            langText.textContent = currentLang.toUpperCase();
        }

        // Update active state in dropdown
        document.querySelectorAll('.language-option').forEach(option => {
            const isActive = option.dataset.lang === currentLang;
            option.classList.toggle('active', isActive);
            option.querySelector('.fa-check').style.opacity = isActive ? '1' : '0';
        });

        // Apply translations
        updateLanguage(currentLang);
        
        // Initialize language selector
        initializeLanguageSelector();
    } catch (error) {
        console.error('Error initializing language selector:', error);
    }
});

function initializeLanguageSelector() {
    const languageBtn = document.querySelector('.language-btn');
    const languageSelector = document.querySelector('.language-selector');
    
    if (!languageBtn || !languageSelector) {
        console.error('Language selector elements not found');
        return;
    }

    console.log('Adding click event to language button');
    
    // Remove any existing click listeners
    languageBtn.removeEventListener('click', toggleDropdown);
    document.removeEventListener('click', closeDropdownOutside);
    
    // Add click listener to language button - Güvenli ekleme
    if (languageBtn) {
        languageBtn.addEventListener('click', toggleDropdown);
    }
    
    // Add click listener to document to close dropdown when clicking outside
    document.addEventListener('click', closeDropdownOutside);
    
    // Add click listeners to language options - Güvenli ekleme
    const languageOptions = document.querySelectorAll('.language-option');
    if (languageOptions && languageOptions.length > 0) {
        languageOptions.forEach(option => {
            option.removeEventListener('click', handleLanguageSelection);
            option.addEventListener('click', handleLanguageSelection);
        });
    }
}

function toggleDropdown(event) {
    event.stopPropagation();
    console.log('Language button clicked');
    
    const languageSelector = document.querySelector('.language-selector');
    const isActive = languageSelector.classList.toggle('active');
    
    console.log('Dropdown toggled:', isActive ? 'shown' : 'hidden');
}

function closeDropdownOutside(event) {
    const languageSelector = document.querySelector('.language-selector');
    const languageBtn = document.querySelector('.language-btn');
    
    if (!languageSelector || !languageBtn) return;
    
    if (!languageSelector.contains(event.target) && !languageBtn.contains(event.target)) {
        languageSelector.classList.remove('active');
        console.log('Dropdown closed from outside click');
    }
}

function handleLanguageSelection(event) {
    event.stopPropagation();
    
    const selectedLang = this.dataset.lang;
    const currentLang = localStorage.getItem('preferredLanguage');
    
    if (selectedLang === currentLang) {
        console.log('Same language selected, no change needed');
        return;
    }
    
    try {
        // Update language
        localStorage.setItem('preferredLanguage', selectedLang);
        updateLanguage(selectedLang);
        
        // Update UI
        const languageBtn = document.querySelector('.language-btn');
        const flagImg = languageBtn.querySelector('img');
        const langText = languageBtn.querySelector('span');
        
        if (flagImg) {
            flagImg.src = `/static/images/flags/${selectedLang}.png`;
            flagImg.alt = selectedLang.toUpperCase();
        }
        if (langText) {
            langText.textContent = selectedLang.toUpperCase();
        }
        
        // Update active states
        document.querySelectorAll('.language-option').forEach(option => {
            const isActive = option.dataset.lang === selectedLang;
            option.classList.toggle('active', isActive);
            option.querySelector('.fa-check').style.opacity = isActive ? '1' : '0';
        });
        
        // Close dropdown
        document.querySelector('.language-selector').classList.remove('active');
        
        console.log('Language update completed');
    } catch (error) {
        console.error('Error updating language:', error);
    }
}

function updateLanguage(lang) {
    try {
        // Update HTML lang attribute
        document.documentElement.lang = lang;
        
        // Update page title
        const titleElement = document.querySelector('title[data-translate]');
        if (titleElement) {
            titleElement.textContent = translations[lang][titleElement.dataset.translate] || titleElement.textContent;
        }
        
        // Update all elements with data-translate attribute
        document.querySelectorAll('[data-translate]').forEach(element => {
            const key = element.dataset.translate;
            if (translations[lang] && translations[lang][key]) {
                if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                    element.placeholder = translations[lang][key];
                } else {
                    element.textContent = translations[lang][key];
                }
            } else {
                console.warn(`Translation missing for key: ${key} in language: ${lang}`);
            }
        });

        // Update placeholders for elements with data-translate-placeholder
        document.querySelectorAll('[data-translate-placeholder]').forEach(element => {
            const key = element.dataset.translatePlaceholder;
            if (translations[lang] && translations[lang][key]) {
                element.placeholder = translations[lang][key];
            } else {
                console.warn(`Translation missing for placeholder key: ${key} in language: ${lang}`);
            }
        });
        
        console.log(`Language updated to: ${lang}`);
    } catch (error) {
        console.error('Error in updateLanguage:', error);
    }
}

// Handle any unhandled promise rejections
window.addEventListener('unhandledrejection', function(event) {
    console.warn('Unhandled promise rejection:', event.reason);
});

// Export for use in other scripts if needed
window.updateLanguage = updateLanguage; 