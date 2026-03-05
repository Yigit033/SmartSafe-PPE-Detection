"use client";

import { useEffect, useState, useRef } from "react";
import Script from "next/script";

export default function LandingPage() {
  const [activeTab, setActiveTab] = useState("performance");
  const [activeBenefitTab, setActiveBenefitTab] = useState("financial");
  const [activeSectorDot, setActiveSectorDot] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleScroll = () => {
    if (scrollRef.current) {
      const { scrollLeft, clientWidth } = scrollRef.current;
      const index = Math.round(scrollLeft / clientWidth);
      setActiveSectorDot(index);
    }
  };

  const scrollToSector = (index: number) => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        left: index * scrollRef.current.clientWidth,
        behavior: "smooth",
      });
    }
  };

  const sectorsData = [
    {
      icon: "hard-hat",
      title: "İnşaat Sektörü",
      features: [
        "Baret Tespiti",
        "Yelek Kontrolü",
        "İş Gözlüğü",
        "Çelik Burunlu Bot",
        "İş Eldiveni",
        "Emniyet Kemeri",
      ],
    },
    {
      icon: "ship",
      title: "Denizcilik & Tersane",
      features: [
        "Can Yeleği",
        "Su Geçirmez KKD",
        "Yüksek Koruma",
        "Baret",
        "Çelik Burunlu Ayakkabı",
        "İş Eldiveni",
        "Emniyet Kemeri",
      ],
    },
    {
      icon: "flask",
      title: "Kimya Endüstrisi",
      features: ["Maske Kontrolü", "Eldiven Tespiti", "Koruyucu Giysi"],
    },
    {
      icon: "industry",
      title: "Üretim Tesisleri",
      features: ["Çoklu KKD Tespiti", "Anlık Raporlama", "Vardiya Takibi"],
    },
    {
      icon: "bolt",
      title: "Enerji",
      features: [
        "İzole Eldiven",
        "Dielektrik Ayakkabı",
        "Ark Flaş Tulumu",
        "Güvenlik Kaskı",
        "Güvenlik Gözlüğü",
        "Kulak Koruyucu",
      ],
    },
    {
      icon: "gas-pump",
      title: "Petrokimya",
      features: [
        "Solunum Koruyucu",
        "Kimyasal Tulum",
        "Özel Eldiven",
        "Güvenlik Kaskı",
        "Güvenlik Gözlüğü",
        "Güvenlik Ayakkabısı",
      ],
    },
    {
      icon: "warehouse",
      title: "Depo & Lojistik",
      features: [
        "Güvenlik Kaskı",
        "Yüksek Görünürlük Yeleği",
        "Çelik Burunlu Ayakkabı",
        "İş Eldiveni",
        "Güvenlik Gözlüğü",
        "Emniyet Kemeri",
      ],
    },
    {
      icon: "plane",
      title: "Havacılık",
      features: [
        "Havacılık Kaskı",
        "Reflektör Yelek",
        "Özel Ayakkabı",
        "Güvenlik Gözlüğü",
        "Kulak Koruyucu",
        "İş Eldiveni",
      ],
    },
    {
      icon: "utensils",
      title: "Gıda Endüstrisi",
      features: ["Bone Kontrolü", "Hijyen Eldiveni", "Önlük Tespiti"],
    },
  ];

  const benefitsData: any = {
    financial: {
      icon: "coins",
      title: "Finansal Avantajlar",
      desc: "İş güvenliği yatırımınızın hızlı geri dönüşü ve uzun vadeli finansal faydaları",
      items: [
        "İş kazası maliyetlerinin minimize edilmesi",
        "Sigorta primi indirimi",
        "Uyum maliyetlerinin azaltılması",
        "Verimlilik artışı",
        "Operasyonel verimlilik",
        "Kaynak optimizasyonu",
      ],
    },
    operational: {
      icon: "cogs",
      title: "Operasyonel Faydalar",
      desc: "Süreçlerinizi optimize eden ve verimliliği artıran akıllı çözümler",
      items: [
        "Gerçek zamanlı izleme ve uyarı sistemi",
        "Otomatik raporlama ve dokümantasyon",
        "Çalışan güvenliğinin artırılması",
        "Denetim süreçlerinin kolaylaştırılması",
        "Sektöre özel optimize edilmiş çözümler",
        "7/24 kesintisiz izleme",
        "Mobil uygulama ile uzaktan erişim",
        "Akıllı iş akışı otomasyonu",
      ],
    },
    safety: {
      icon: "user-shield",
      title: "İş Güvenliği Avantajları",
      desc: "Kapsamlı iş güvenliği avantajları",
      items: [
        "Proaktif risk yönetimi",
        "Anlık ihlal tespiti ve müdahale",
        "Çalışan güvenlik bilincinin artırılması",
        "Kaza önleme oranında artış",
        "Uyum yönetimi",
        "Güvenlik kültürünün geliştirilmesi",
        "Gelişmiş risk analizi",
        "Hızlı acil durum müdahalesi",
      ],
    },
    technical: {
      icon: "microchip",
      title: "Teknolojik Üstünlükler",
      desc: "En son yapay zeka teknolojileri ile donatılmış gelecek odaklı çözümler",
      items: [
        "Yapay zeka destekli hassas tespit",
        "Sürekli öğrenen ve gelişen sistem",
        "Kolay entegrasyon ve ölçeklenebilirlik",
        "Özelleştirilebilir uyarı mekanizmaları",
        "Gerçek zamanlı AI analizi",
        "Bulut entegrasyonu",
        "API desteği",
        "Mobil uyumluluk",
      ],
    },
    legal: {
      icon: "balance-scale",
      title: "Yasal Uyumluluk",
      desc: "Mevzuata tam uyumluluk ve yasal süreçlerde kolaylık sağlayan çözümler",
      items: [
        "İSG mevzuatına tam uyumluluk",
        "Otomatik denetim raporları",
        "Yasal dokümantasyon desteği",
        "Sertifikasyon süreçlerinde kolaylık",
        "KVKK uyumlu veri işleme",
        "Denetim hazırlık desteği",
        "Yasal raporlama otomasyonu",
        "Uyumluluk takip sistemi",
      ],
    },
  };

  // Features Data from original landing.html
  const featuresData: any = {
    performance: [
      {
        icon: "tachometer-alt",
        title: "Yüksek Performans",
        desc: "Saniyede 24.7 kare işleme kapasitesi ile gerçek zamanlı tespit.",
        items: ["GPU Optimizasyonu", "NVIDIA CUDA Desteği", "Düşük Gecikme"],
      },
      {
        icon: "expand-arrows-alt",
        title: "Ölçeklenebilirlik",
        desc: "İhtiyaca göre büyüyebilen esnek sistem mimarisi.",
        items: [
          "Yatay/Dikey Ölçekleme",
          "Çoklu Lokasyon Desteği",
          "Yük Dengeleme",
        ],
      },
      {
        icon: "server",
        title: "Sistem Kararlılığı",
        desc: "Kesintisiz çalışma ve yüksek uptime garantisi.",
        items: [
          "Otomatik Yedekleme",
          "Hata Toleransı",
          "7/24 Kesintisiz Operasyon",
        ],
      },
    ],
    ai: [
      {
        icon: "brain",
        title: "Yapay Zeka",
        desc: "Gelişmiş derin öğrenme modelleri ile hassas tespit.",
        items: ["Gerçek Zamanlı Analiz", "Yüksek Doğruluk", "Sürekli Öğrenme"],
      },
      {
        icon: "chart-line",
        title: "Akıllı Analitik",
        desc: "İleri seviye veri analizi ve tahminleme.",
        items: ["Anomali Tespiti", "Davranış Analizi", "Tahminsel Bakım"],
      },
      {
        icon: "robot",
        title: "Otomasyon",
        desc: "Akıllı iş akışları ve otomatik aksiyonlar.",
        items: ["Olay Tetikleme", "Akıllı Alarmlar", "Otomatik Raporlama"],
      },
    ],
    monitoring: [
      {
        icon: "camera",
        title: "Çoklu Kamera",
        desc: "100+ kameraya kadar eş zamanlı izleme kapasitesi.",
        items: [
          "IP Kamera Entegrasyonu",
          "Otomatik Yük Dengeleme",
          "Kesintisiz İzleme",
        ],
      },
      {
        icon: "desktop",
        title: "Merkezi Kontrol",
        desc: "Tüm sistemin tek bir panelden yönetilmesi.",
        items: [
          "Kullanıcı Yetkilendirme",
          "Canlı İzleme Paneli",
          "Geçmiş Kayıt Analizi",
        ],
      },
      {
        icon: "mobile-alt",
        title: "Mobil Erişim",
        desc: "Her yerden güvenli erişim ve kontrol imkanı.",
        items: ["Mobil Uygulama", "Anlık Bildirimler", "Bulut Senkronizasyon"],
      },
    ],
    integration: [
      {
        icon: "plug",
        title: "Kolay Entegrasyon",
        desc: "Mevcut sistemlerle sorunsuz entegrasyon imkanı.",
        items: [
          "REST API Desteği",
          "ERP Entegrasyonu",
          "Kamera Donanım Desteği",
        ],
      },
      {
        icon: "cloud",
        title: "Bulut Desteği",
        desc: "Esnek bulut altyapısı ve hibrit çözümler.",
        items: [
          "AWS/Azure/GCP Desteği",
          "Özel Bulut Çözümleri",
          "Hibrit Yapılandırma",
        ],
      },
      {
        icon: "headphones",
        title: "7/24 Destek",
        desc: "Kesintisiz teknik destek ve bakım hizmetleri.",
        items: ["Canlı Destek", "Uzaktan Müdahale", "Periyodik Bakım"],
      },
    ],
    security: [
      {
        icon: "shield-alt",
        title: "Veri Güvenliği",
        desc: "En üst düzey veri koruma ve şifreleme.",
        items: ["Uçtan Uca Şifreleme", "KVKK Uyumluluğu", "Güvenli Depolama"],
      },
      {
        icon: "user-lock",
        title: "Erişim Kontrolü",
        desc: "Gelişmiş yetkilendirme ve kimlik doğrulama.",
        items: [
          "Çok Faktörlü Doğrulama",
          "Rol Bazlı Yetki",
          "Erişim Günlükleri",
        ],
      },
      {
        icon: "file-signature",
        title: "Sertifikasyon",
        desc: "Uluslararası güvenlik standartlarına uygunluk.",
        items: ["ISO 27001", "Bölgesel Regülasyonlar", "Denetim Raporları"],
      },
    ],
  };

  useEffect(() => {
    // ... hover and click logic
    const handleScroll = () => {
      const navbar = document.querySelector(".navbar");
      if (window.scrollY > 50) {
        navbar?.classList.add("scrolled");
      } else {
        navbar?.classList.remove("scrolled");
      }
    };
    window.addEventListener("scroll", handleScroll);

    // Close dropdown on click outside
    const handleClickOutside = (e: MouseEvent) => {
      const selector = document.getElementById("languageSelector");
      if (selector && !selector.contains(e.target as Node)) {
        selector.classList.remove("active");
      }
    };
    window.addEventListener("click", handleClickOutside);

    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("click", handleClickOutside);
    };
  }, []);

  return (
    <div className="landing-wrapper">
      {/* Navbar */}
      <nav className="navbar navbar-expand-lg navbar-dark fixed-top">
        <div className="container">
          <a className="navbar-brand d-flex align-items-center" href="/">
            <i className="fas fa-shield-alt me-2 text-primary"></i>
            <span className="fw-bold tracking-tight">SmartSafe AI</span>
          </a>
          <button
            className="navbar-toggler border-0"
            type="button"
            data-bs-toggle="collapse"
            data-bs-target="#navbarNav"
          >
            <span className="navbar-toggler-icon"></span>
          </button>
          <div className="collapse navbar-collapse" id="navbarNav">
            <ul className="navbar-nav ms-auto align-items-center">
              <li className="nav-item">
                <a className="nav-link" href="#features">
                  Özellikler
                </a>
              </li>
              <li className="nav-item">
                <a className="nav-link" href="#sectors">
                  Sektörler
                </a>
              </li>
              <li className="nav-item">
                <a className="nav-link" href="#benefits">
                  Faydalar
                </a>
              </li>
              <li className="nav-item">
                <a className="nav-link" href="#contact">
                  İletişim
                </a>
              </li>
              <li className="nav-item">
                <a
                  className="btn btn-primary ms-lg-3 px-4 py-2 rounded-pill shadow-sm"
                  href="http://localhost:5000/app"
                >
                  Giriş Yap
                </a>
              </li>
              {/* Language Selector */}
              <li className="nav-item">
                <div
                  className="language-selector ms-lg-3"
                  id="languageSelector"
                >
                  <button
                    className="language-btn py-1 px-3"
                    onClick={(e) => {
                      e.stopPropagation();
                      document
                        .getElementById("languageSelector")
                        ?.classList.toggle("active");
                    }}
                  >
                    <img
                      src="https://flagcdn.com/w20/tr.png"
                      id="currentFlag"
                      className="flag-icon"
                      alt="TR"
                    />
                    <span id="currentLang" className="ms-1">
                      TR
                    </span>
                    <i className="fas fa-chevron-down ms-1 small opacity-50"></i>
                  </button>
                  <div className="language-dropdown shadow">
                    <div
                      className="language-option"
                      onClick={() => {
                        (
                          document.getElementById(
                            "currentFlag",
                          ) as HTMLImageElement
                        ).src = "https://flagcdn.com/w20/tr.png";
                        (
                          document.getElementById("currentLang") as HTMLElement
                        ).innerText = "TR";
                        document
                          .getElementById("languageSelector")
                          ?.classList.remove("active");
                      }}
                    >
                      <img
                        src="https://flagcdn.com/w20/tr.png"
                        className="flag-icon"
                        alt="TR"
                      />
                      <span>Türkçe</span>
                    </div>
                    <div
                      className="language-option"
                      onClick={() => {
                        (
                          document.getElementById(
                            "currentFlag",
                          ) as HTMLImageElement
                        ).src = "https://flagcdn.com/w20/gb.png";
                        (
                          document.getElementById("currentLang") as HTMLElement
                        ).innerText = "EN";
                        document
                          .getElementById("languageSelector")
                          ?.classList.remove("active");
                      }}
                    >
                      <img
                        src="https://flagcdn.com/w20/gb.png"
                        className="flag-icon"
                        alt="EN"
                      />
                      <span>English</span>
                    </div>
                  </div>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-section">
        <div id="particles-js"></div>
        <div className="background-shapes">
          <div className="shape"></div>
          <div className="shape"></div>
          <div className="shape"></div>
          <div className="shape"></div>
          <div className="shape"></div>
          <div className="shape"></div>
          <div className="shape"></div>
        </div>
        <div className="container content-wrapper">
          <div className="row align-items-center">
            <div className="col-lg-6" data-aos="fade-right">
              <h1 className="display-4 fw-bold mb-4">
                Akıllı Göz, <span className="text-white">Güvenli İş</span>
              </h1>
              <p className="lead mb-5 text-white-50">
                Endüstriyel tesislerde kişisel koruyucu donanım (KKD)
                kullanımını gerçek zamanlı izleyen ve iş kazalarını önleyen
                akıllı güvenlik sistemi.
              </p>
              <div className="d-flex gap-3 mb-4 flex-wrap">
                <button
                  type="button"
                  className="btn btn-primary btn-lg px-4 shadow-sm"
                >
                  <i className="fas fa-play me-2"></i> Demo Talep Et
                </button>
                <a
                  href="http://localhost:5000/app"
                  className="btn btn-outline-light btn-lg px-4"
                >
                  <i className="fas fa-rocket me-2"></i> Hemen Başla
                </a>
              </div>
              <div className="d-flex gap-4 mt-2">
                <div className="d-flex align-items-center text-white-50 small">
                  <i className="fas fa-check-circle text-success me-2"></i>
                  <span>Anında erişim</span>
                </div>
                <div className="d-flex align-items-center text-white-50 small">
                  <i className="fas fa-check-circle text-success me-2"></i>
                  <span>7 gün ücretsiz</span>
                </div>
              </div>
            </div>
            <div className="col-lg-6" data-aos="fade-left">
              <div className="position-relative rounded-1 shadow-lg overflow-hidden">
                <video
                  className="img-fluid rounded-4"
                  autoPlay
                  loop
                  muted
                  playsInline
                >
                  <source
                    src="/static/videos/hero-video.mp4"
                    type="video/mp4"
                  />
                </video>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-5 bg-white">
        <div className="container">
          <div className="row text-center g-4">
            <div className="col-6 col-md-3" data-aos="zoom-in">
              <div className="p-4 border-end">
                <div className="h2 fw-bold text-primary mb-0">24.7</div>
                <div className="text-muted small">FPS Real-time</div>
              </div>
            </div>
            <div
              className="col-6 col-md-3"
              data-aos="zoom-in"
              data-aos-delay="100"
            >
              <div className="p-4 border-end">
                <div className="h2 fw-bold text-primary mb-0">37x</div>
                <div className="text-muted small">Daha Hızlı</div>
              </div>
            </div>
            <div
              className="col-6 col-md-3"
              data-aos="zoom-in"
              data-aos-delay="200"
            >
              <div className="p-4 border-end">
                <div className="h2 fw-bold text-primary mb-0">100+</div>
                <div className="text-muted small">Kamera Desteği</div>
              </div>
            </div>
            <div
              className="col-6 col-md-3"
              data-aos="zoom-in"
              data-aos-delay="300"
            >
              <div className="p-4">
                <div className="h2 fw-bold text-primary mb-0">%99.9</div>
                <div className="text-muted small">Doğruluk Payı</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="section py-5 bg-white">
        <div className="container">
          <div className="row mb-5">
            <div className="col-lg-6 mx-auto text-center" data-aos="fade-up">
              <h2 className="display-5 fw-bold mb-3">Özellikler</h2>
              <p className="lead text-muted">
                En son teknolojilerle donatılmış güvenlik sistemi
              </p>
            </div>
          </div>

          <div className="features-tabs mb-4">
            <div className="d-flex justify-content-center overflow-auto pb-3 mb-5">
              <div
                className="nav nav-pills gap-2 flex-nowrap"
                id="featuresTab"
                role="tablist"
              >
                {[
                  {
                    id: "performance",
                    icon: "tachometer-alt",
                    label: "Performans",
                  },
                  { id: "ai", icon: "brain", label: "Yapay Zeka" },
                  { id: "monitoring", icon: "desktop", label: "İzleme" },
                  { id: "integration", icon: "plug", label: "Entegrasyon" },
                  { id: "security", icon: "shield-alt", label: "Güvenlik" },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    className={`nav-link px-4 py-2 border-0 rounded-pill transition-all ${
                      activeTab === tab.id ? "active" : ""
                    }`}
                    onClick={() => setActiveTab(tab.id)}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    <i className={`fas fa-${tab.icon} me-2`}></i>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="tab-content" id="featuresTabContent">
              <div className="row g-4 overflow-hidden">
                {featuresData[activeTab]?.map((feature: any, index: number) => (
                  <div
                    key={index}
                    className="col-lg-4"
                    data-aos="fade-up"
                    data-aos-delay={index * 100}
                  >
                    <div className="glass-card feature-card-item p-4 h-100 border-0 shadow-sm rounded-4 bg-white text-start position-relative overflow-hidden">
                      <div
                        className="feature-icon mb-4 rounded-3 bg-primary bg-opacity-10 d-flex align-items-center justify-content-center"
                        style={{ width: "56px", height: "56px" }}
                      >
                        <i
                          className={`fas fa-${feature.icon} text-primary fs-4`}
                        ></i>
                      </div>
                      <h4 className="fw-bold mb-3">{feature.title}</h4>
                      <p className="text-muted small mb-4">{feature.desc}</p>
                      <ul className="feature-list list-unstyled small">
                        {feature.items.map((item: string, i: number) => (
                          <li
                            key={i}
                            className="mb-2 d-flex align-items-center"
                          >
                            <i className="fas fa-check text-success me-2 small"></i>
                            <span className="text-muted">{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Sectors Section */}
      <section id="sectors" className="sectors-section">
        <div className="container" data-aos="fade-up">
          <div className="row mb-5">
            <div className="col-lg-6 mx-auto text-center">
              <h2 className="display-5 fw-bold mb-3" lang="tr">
                Sektörel Çözümler
              </h2>
              <p className="lead text-muted">
                Her sektör için optimize edilmiş güvenlik çözümleri
              </p>
            </div>
          </div>

          <div className="sectors-scroll-container">
            <div
              className="sectors-scroll-wrapper"
              ref={scrollRef}
              onScroll={handleScroll}
            >
              {sectorsData.map((sector, index) => (
                <div key={index} className="sector-scroll-item">
                  <div className="modern-sector-card">
                    <div className="sector-icon">
                      <i className={`fas fa-${sector.icon}`}></i>
                    </div>
                    <div className="sector-content">
                      <h4 lang="tr">{sector.title}</h4>
                      <ul className="sector-features">
                        {sector.features.map((feature, fIndex) => (
                          <li key={fIndex}>
                            <i className="fas fa-check"></i>
                            <span lang="tr">{feature}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="scroll-dots">
              {Array.from({
                length: Math.ceil(sectorsData.length / 3),
              }).map((_, i) => (
                <div
                  key={i}
                  className={`scroll-dot ${
                    activeSectorDot === i ? "active" : ""
                  }`}
                  onClick={() => scrollToSector(i)}
                ></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section id="benefits" className="benefits-section section">
        <div className="container" data-aos="fade-up">
          <div className="row mb-5">
            <div className="col-lg-6 mx-auto text-center">
              <h2 className="display-5 fw-bold mb-3" lang="tr">
                Avantajlar
              </h2>
              <p className="lead text-muted">
                SmartSafe AI ile elde edeceğiniz kazanımlar
              </p>
            </div>
          </div>

          <div className="benefits-tabs mb-4">
            <div className="d-flex justify-content-center overflow-auto pb-3 mb-5">
              <div
                className="nav nav-pills gap-2 flex-nowrap"
                id="benefitsTab"
                role="tablist"
              >
                {[
                  { id: "financial", icon: "coins", label: "Finansal" },
                  { id: "operational", icon: "cogs", label: "Operasyonel" },
                  { id: "safety", icon: "user-shield", label: "İş Güvenliği" },
                  { id: "technical", icon: "microchip", label: "Teknolojik" },
                  { id: "legal", icon: "balance-scale", label: "Yasal" },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    className={`nav-link px-4 py-2 border-0 rounded-pill transition-all ${
                      activeBenefitTab === tab.id ? "active" : ""
                    }`}
                    onClick={() => setActiveBenefitTab(tab.id)}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    <i className={`fas fa-${tab.icon} me-2`}></i>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="tab-content" id="benefitsTabContent">
              <div className="row justify-content-center">
                <div className="col-lg-10">
                  <div className="benefit-card glass-card p-5 position-relative overflow-hidden">
                    <div className="benefit-header text-center mb-4">
                      <div className="benefit-icon gradient-bg mb-3">
                        <i
                          className={`fas fa-${benefitsData[activeBenefitTab].icon}`}
                        ></i>
                      </div>
                      <h3 className="mb-3" lang="tr">
                        {benefitsData[activeBenefitTab].title}
                      </h3>
                      <p className="text-muted mb-4">
                        {benefitsData[activeBenefitTab].desc}
                      </p>
                    </div>
                    <div className="row g-4">
                      <div className="col-md-6">
                        <ul className="benefit-list list-unstyled">
                          {benefitsData[activeBenefitTab].items
                            .slice(
                              0,
                              Math.ceil(
                                benefitsData[activeBenefitTab].items.length / 2,
                              ),
                            )
                            .map((item: string, i: number) => (
                              <li key={i} className="benefit-item mb-3">
                                <i className="fas fa-check-circle me-2"></i>
                                <span lang="tr">{item}</span>
                              </li>
                            ))}
                        </ul>
                      </div>
                      <div className="col-md-6">
                        <ul className="benefit-list list-unstyled">
                          {benefitsData[activeBenefitTab].items
                            .slice(
                              Math.ceil(
                                benefitsData[activeBenefitTab].items.length / 2,
                              ),
                            )
                            .map((item: string, i: number) => (
                              <li key={i} className="benefit-item mb-3">
                                <i className="fas fa-check-circle me-2"></i>
                                <span lang="tr">{item}</span>
                              </li>
                            ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section id="contact" className="contact-section py-5">
        <div className="container py-5" data-aos="fade-up">
          <div className="row justify-content-center align-items-center g-5">
            <div className="col-lg-5">
              <div className="contact-info-card glass-card p-5 h-100">
                <div className="contact-icon mb-4">
                  <i className="fas fa-envelope-open-text"></i>
                </div>
                <h2 className="fw-bold mb-3" lang="tr">
                  İletişime Geçin
                </h2>
                <p className="text-muted mb-4">
                  Her türlü soru, teklif veya iş birliği için bize
                  ulaşabilirsiniz. Size en kısa sürede dönüş yapacağız.
                </p>
                <div className="contact-details">
                  <div className="d-flex align-items-center mb-3">
                    <div className="contact-info-icon">
                      <i className="fas fa-envelope"></i>
                    </div>
                    <span className="ms-3">yigittilaver2000@gmail.com</span>
                  </div>
                  <div className="d-flex align-items-center mb-3">
                    <div className="contact-info-icon">
                      <i className="fas fa-phone"></i>
                    </div>
                    <span className="ms-3">+90 (505) 020 20 95</span>
                  </div>
                  <div className="d-flex align-items-center">
                    <div className="contact-info-icon">
                      <i className="fas fa-map-marker-alt"></i>
                    </div>
                    <span className="ms-3">Maslak, İstanbul</span>
                  </div>
                </div>
                <div className="social-links mt-5 d-flex gap-3">
                  <a href="#" className="social-link">
                    <i className="fab fa-linkedin"></i>
                  </a>
                  <a href="#" className="social-link">
                    <i className="fab fa-twitter"></i>
                  </a>
                  <a href="#" className="social-link">
                    <i className="fab fa-instagram"></i>
                  </a>
                </div>
              </div>
            </div>
            <div className="col-lg-7">
              <div className="contact-form glass-card p-5">
                <form id="contactForm">
                  <div className="row g-4">
                    <div className="col-md-6">
                      <div className="form-group">
                        <label className="form-label small fw-bold">
                          Ad Soyad
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="Adınız Soyadınız"
                          required
                        />
                      </div>
                    </div>
                    <div className="col-md-6">
                      <div className="form-group">
                        <label className="form-label small fw-bold">
                          E-posta
                        </label>
                        <input
                          type="email"
                          className="form-control"
                          placeholder="ornek@sirket.com"
                          required
                        />
                      </div>
                    </div>
                    <div className="col-12">
                      <div className="form-group">
                        <label className="form-label small fw-bold">Konu</label>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="Nasıl yardımcı olabiliriz?"
                          required
                        />
                      </div>
                    </div>
                    <div className="col-12">
                      <div className="form-group">
                        <label className="form-label small fw-bold">
                          Mesaj
                        </label>
                        <textarea
                          className="form-control"
                          rows={4}
                          placeholder="Mesajınızı buraya yazın..."
                          required
                        ></textarea>
                      </div>
                    </div>
                    <div className="col-12 mt-4">
                      <button
                        type="submit"
                        className="btn btn-primary btn-lg w-100"
                      >
                        Gönder <i className="fas fa-paper-plane ms-2"></i>
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer-section py-5">
        <div className="container py-4">
          <div className="row g-4 mb-5">
            <div className="col-lg-6">
              <div className="footer-brand mb-4">
                <h3 className="text-white mb-2">
                  <i className="fas fa-shield-alt"></i> SmartSafe AI
                </h3>
                <p className="text-white-50 small">
                  Yapay zeka destekli endüstriyel güvenlik çözümleriyle iş
                  yerinizi daha güvenli hale getiriyoruz.
                </p>
              </div>
            </div>
            <div className="col-md-4 col-lg-3">
              <h5 className="text-white mb-4">Sektörler</h5>
              <ul className="list-unstyled footer-links">
                <li className="mb-2">
                  <a
                    href="#sectors"
                    className="text-white-50 text-decoration-none small"
                  >
                    İnşaat
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#sectors"
                    className="text-white-50 text-decoration-none small"
                  >
                    Kimya
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#sectors"
                    className="text-white-50 text-decoration-none small"
                  >
                    Gıda
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#sectors"
                    className="text-white-50 text-decoration-none small"
                  >
                    Üretim
                  </a>
                </li>
              </ul>
            </div>
            <div className="col-md-4 col-lg-3">
              <h5 className="text-white mb-4">Destek</h5>
              <ul className="list-unstyled footer-links">
                <li className="mb-2">
                  <a
                    href="#contact"
                    className="text-white-50 text-decoration-none small"
                  >
                    Yardım Merkezi
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#contact"
                    className="text-white-50 text-decoration-none small"
                  >
                    İletişim
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#contact"
                    className="text-white-50 text-decoration-none small"
                  >
                    Demo Talebi
                  </a>
                </li>
                <li className="mb-2">
                  <a
                    href="#contact"
                    className="text-white-50 text-decoration-none small"
                  >
                    Fiyatlandırma
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <hr className="border-secondary opacity-25" />
          <div className="row align-items-center mt-4">
            <div className="col-md-6">
              <p className="text-white-50 small mb-0">
                © 2025 SmartSafe AI. Tüm Hakları Saklıdır.
              </p>
            </div>
            <div className="col-md-6 text-md-end">
              <a
                href="#"
                className="text-white-50 text-decoration-none small me-3"
              >
                Gizlilik Politikası
              </a>
              <a href="#" className="text-white-50 text-decoration-none small">
                Kullanım Koşulları
              </a>
            </div>
          </div>
        </div>
      </footer>

      {/* Scriptler */}
      <Script
        src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"
        strategy="afterInteractive"
      />
      <Script
        src="https://unpkg.com/aos@2.3.1/dist/aos.js"
        strategy="afterInteractive"
        onLoad={() => {
          if (typeof window !== "undefined" && (window as any).AOS) {
            (window as any).AOS.init({ duration: 800, once: true });
          }
        }}
      />
      <Script
        src="https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js"
        strategy="afterInteractive"
        onLoad={() => {
          if (typeof window !== "undefined" && (window as any).particlesJS) {
            (window as any).particlesJS("particles-js", {
              particles: {
                number: {
                  value: 60,
                  density: { enable: true, value_area: 800 },
                },
                color: { value: "#ffffff" },
                shape: { type: "circle" },
                opacity: { value: 0.3, random: true },
                size: { value: 2, random: true },
                line_linked: {
                  enable: true,
                  distance: 150,
                  color: "#ffffff",
                  opacity: 0.2,
                  width: 1,
                },
                move: {
                  enable: true,
                  speed: 1.5,
                  direction: "none",
                  random: true,
                  straight: false,
                  out_mode: "out",
                  bounce: false,
                },
              },
              interactivity: {
                detect_on: "canvas",
                events: {
                  onhover: { enable: true, mode: "repulse" },
                  resize: true,
                },
              },
              retina_detect: true,
            });
          }
        }}
      />
    </div>
  );
}
