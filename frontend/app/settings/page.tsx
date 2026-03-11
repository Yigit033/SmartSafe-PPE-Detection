"use client";

import { useState, useEffect } from "react";
import { getCompanyId } from "@/lib/session";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");
  const [company, setCompany] = useState<any>(null);
  const [ppeRequirements, setPpeRequirements] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const companyId = getCompanyId();

  useEffect(() => {
    fetchCompanyData();
  }, []);

  const fetchCompanyData = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}`,
      );
      const data = await response.json();
      if (data.success) {
        setCompany(data.company);
        // PPE gereksinimlerini ayıkla
        try {
          const reqs = typeof data.company.ppe_requirements === 'string' 
            ? JSON.parse(data.company.ppe_requirements) 
            : data.company.ppe_requirements;
          setPpeRequirements(reqs || []);
        } catch (e) {
          setPpeRequirements([]);
        }
      }
    } catch (error) {
      console.error("Error fetching company data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const formData = new FormData(e.currentTarget as HTMLFormElement);
      const updates = Object.fromEntries(formData.entries());
      
      // PPE seçimlerini de her ihtimale karşı pakete dahil et
      const response = await fetch(
        `http://localhost:4000/company/${companyId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            ...updates, 
            ppe_requirements: ppeRequirements 
          }),
        },
      );

      const data = await response.json();
      if (data.success) {
        alert("Profil başarıyla güncellendi!");
        // Sektör değişmişse PPE de değişeceği için hepsini yenile
        await fetchCompanyData();
      }
    } catch (error) {
      console.error("Error updating profile:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const SECTOR_DEFAULTS: Record<string, any[]> = {
    construction: [
      { id: "helmet", name: "Baret/Kask", mandatory: true, priority: 1 },
      { id: "safety_vest", name: "Güvenlik Yeleği", mandatory: true, priority: 2 },
      { id: "safety_shoes", name: "Güvenlik Ayakkabısı", mandatory: true, priority: 3 },
      { id: "gloves", name: "Güvenlik Eldiveni", mandatory: false, priority: 2 },
    ],
    manufacturing: [
      { id: "helmet", name: "Endüstriyel Kask", mandatory: true, priority: 1 },
      { id: "safety_vest", name: "Reflektörlü Yelek", mandatory: true, priority: 2 },
      { id: "gloves", name: "İş Eldiveni", mandatory: true, priority: 2 },
      { id: "safety_shoes", name: "Çelik Burunlu Ayakkabı", mandatory: true, priority: 3 },
    ],
    chemical: [
      { id: "gloves", name: "Kimyasal Eldiven", mandatory: true, priority: 1 },
      { id: "glasses", name: "Koruyucu Gözlük", mandatory: true, priority: 1 },
      { id: "face_mask", name: "Solunum Maskesi", mandatory: true, priority: 1 },
      { id: "safety_suit", name: "Kimyasal Tulum", mandatory: true, priority: 2 },
    ],
    food: [
      { id: "hairnet", name: "Bone/Başlık", mandatory: true, priority: 1 },
      { id: "face_mask", name: "Hijyen Maskesi", mandatory: true, priority: 1 },
      { id: "apron", name: "Hijyen Önlüğü", mandatory: true, priority: 2 },
      { id: "gloves", name: "Hijyen Eldiveni", mandatory: false, priority: 2 },
    ],
    maritime: [
      { id: "life_jacket", name: "Can Yeleği", mandatory: true, priority: 1 },
      { id: "helmet", name: "Gemi Kaskı", mandatory: true, priority: 1 },
      { id: "shoes", name: "Kaymaz Gemi Botu", mandatory: true, priority: 2 },
      { id: "gloves", name: "Çalışma Eldiveni", mandatory: false, priority: 2 },
    ],
    energy: [
      { id: "helmet", name: "Dielektrik Baret", mandatory: true, priority: 1 },
      { id: "insulated_gloves", name: "İzole Eldiven", mandatory: true, priority: 1 },
      { id: "safety_helmet", name: "Güvenlik Kaskı", mandatory: true, priority: 2 },
    ],
    petrochemical: [
      { id: "gas_mask", name: "Gaz Maskesi", mandatory: true, priority: 1 },
      { id: "safety_suit", name: "Kimyasal Tulum", mandatory: true, priority: 1 },
      { id: "face_mask", name: "Maske", mandatory: true, priority: 1 },
      { id: "gloves", name: "Kimyasal Eldiven", mandatory: true, priority: 2 },
    ],
    marine: [
      { id: "life_jacket", name: "Can Yeleği", mandatory: true, priority: 1 },
      { id: "safety_suit", name: "Su Geçirmez Tulum", mandatory: true, priority: 1 },
      { id: "helmet", name: "Güvenlik Kaskı", mandatory: true, priority: 2 },
      { id: "shoes", name: "Güvenlik Ayakkabısı", mandatory: true, priority: 2 },
    ],
    aviation: [
      { id: "headset", name: "Koruyucu Kulaklık", mandatory: true, priority: 1 },
      { id: "safety_suit", name: "Antistatik Tulum", mandatory: true, priority: 1 },
      { id: "shoes", name: "Güvenlik Ayakkabısı", mandatory: true, priority: 2 },
      { id: "glasses", name: "Güvenlik Gözlüğü", mandatory: true, priority: 2 },
    ]
  };

  const handleSectorChange = (newSector: string) => {
    // 1. ANLIK GÜNCELLEME (Frontend State)
    // Sadece state'i güncelleyerek kullanıcının seçimine hazırlık yapıyoruz.
    // Backend'e asıl kayıt "Ayarları Kaydet" butonunda yapılacak.
    const defaults = SECTOR_DEFAULTS[newSector] || [];
    setPpeRequirements(defaults);
    setCompany((prev: any) => prev ? { ...prev, sector: newSector } : null);
  };

  const handleUpdatePPE = async () => {
    setIsSaving(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            sector: company?.sector,
            ppe_requirements: ppeRequirements 
          }),
        },
      );

      const data = await response.json();
      if (data.success) {
        alert("PPE konfigürasyonu ve sektör başarıyla güncellendi!");
        fetchCompanyData();
      }
    } catch (error) {
      console.error("Error updating PPE config:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const togglePPE = (id: string) => {
    setPpeRequirements(prev => {
      const exists = prev.find((p: any) => p.id === id);
      if (exists) {
        return prev.map((p: any) => p.id === id ? { ...p, mandatory: !p.mandatory } : p);
      } else {
        const option = ppeOptionsMap[id];
        return [...prev, { id, name: option?.name || id, mandatory: true, priority: 2 }];
      }
    });
  };

  const ppeOptionsMap: Record<string, { name: string; icon: string }> = {
    helmet: { name: "Kask/Baret", icon: "engineering" },
    safety_helmet: { name: "Güvenlik Kaskı", icon: "engineering" },
    vest: { name: "Güvenlik Yeleği", icon: "checkroom" },
    safety_vest: { name: "Yelek", icon: "checkroom" },
    gloves: { name: "Koruyucu Eldiven", icon: "back_hand" },
    glasses: { name: "Güvenlik Gözlüğü", icon: "visibility" },
    safety_glasses: { name: "Gözlük", icon: "visibility" },
    shoes: { name: "Emniyet Ayakkabısı", icon: "ice_skating" },
    boots: { name: "Emniyet Botu", icon: "ice_skating" },
    safety_shoes: { name: "İş Ayakkabısı", icon: "ice_skating" },
    mask: { name: "Maske", icon: "medical_mask" },
    face_mask: { name: "Maske", icon: "medical_mask" },
    hairnet: { name: "Bone", icon: "face_6" },
    apron: { name: "Önlük", icon: "accessibility_new" },
    safety_suit: { name: "İş Tulumu", icon: "settings_accessibility" },
    headset: { name: "Koruyucu Kulaklık", icon: "headset" },
    earmuffs: { name: "Kulaklık", icon: "headset" },
    gas_mask: { name: "Gaz Maskesi", icon: "masks" },
    life_jacket: { name: "Can Yeleği", icon: "water_lux" },
    insulated_gloves: { name: "İzole Eldiven", icon: "back_hand" },
    dielectric_boots: { name: "Dielektrik Bot", icon: "ice_skating" },
  };

  const getDisplayPpes = () => {
    // Şirketin mevcut PPE gereksinimlerini ve temel PPE havuzunu birleştir
    const currentIds = ppeRequirements.map((p: any) => p.id);
    const baseIds = ["helmet", "vest", "gloves", "shoes"];
    const allIds = Array.from(new Set([...currentIds, ...baseIds]));

    return allIds.map(id => {
      const defined = ppeOptionsMap[id];
      const req = ppeRequirements.find((p: any) => p.id === id);
      
      return {
        id,
        // Önce sektörden gelen ismi (Gemi Kaskı vb.) kullan, yoksa genel havuzdan al
        name: req?.name || defined?.name || id.charAt(0).toUpperCase() + id.slice(1),
        icon: defined?.icon || "inventory_2",
        mandatory: !!req?.mandatory
      };
    });
  };

  const sections = [
    { id: "profile", name: "Şirket Profili", icon: "domain" },
    { id: "ppe", name: "PPE Konfigürasyonu", icon: "construction" },
    { id: "notifications", name: "Bildirimler", icon: "notifications" },
    { id: "subscription", name: "Abonelik", icon: "payments" },
    { id: "security", name: "Güvenlik", icon: "security" },
  ];

  if (isLoading && !company) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-brand-teal"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8 animate-fade-in pb-12" lang="tr">
      <section className="flex flex-col gap-2">
        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
          Ayarlar
        </h2>
        <p className="text-slate-500 font-medium">
          Sistem tercihlerini ve şirket yapılandırmasını buradan yönetin.
        </p>
      </section>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* Sidebar Navigation */}
        <aside className="w-full lg:w-80 flex-shrink-0">
          <nav className="flex flex-col gap-2 p-3 rounded-3xl bg-white border border-slate-200 shadow-sm">
            {sections.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`flex items-center gap-3 px-4 py-4 rounded-2xl text-xs font-black transition-all cursor-pointer text-left group ${
                  activeSection === section.id
                    ? "bg-brand-teal text-white shadow-lg shadow-brand-teal/20 translate-x-1"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <span
                  className={`material-symbols-rounded text-xl transition-transform ${
                    activeSection === section.id
                      ? "scale-110"
                      : "opacity-80 group-hover:scale-110 group-hover:opacity-100"
                  }`}
                >
                  {section.icon}
                </span>
                <span className="uppercase tracking-widest leading-tight flex-1">
                  {section.name}
                </span>
              </button>
            ))}
          </nav>
        </aside>

        {/* Content Area */}
        <main className="flex-1 min-w-0">
          <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden min-h-[600px] flex flex-col">
            {/* dynamic header */}
            <div
              className={`p-8 text-white ${
                activeSection === "security"
                  ? "bg-red-500"
                  : activeSection === "subscription"
                    ? "bg-brand-orange"
                    : "bg-brand-teal"
              }`}
            >
              <h3 className="text-2xl font-black uppercase italic tracking-tight">
                {sections.find((s) => s.id === activeSection)?.name}
              </h3>
              <p className="opacity-90 text-sm font-bold mt-1">
                {activeSection === "profile" &&
                  "Şirket temel bilgilerini ve iletişim detaylarını yönetin."}
                {activeSection === "ppe" &&
                  "Kullanılacak PPE ekipmanlarını ve başarı eşiklerini ayarlayın."}
                {activeSection === "notifications" &&
                  "Sistem uyarıları ve rapor bilgilendirme tercihlerini seçin."}
                {activeSection === "subscription" &&
                  "Mevcut planınızı görüntüleyin ve aboneliğinizi yönetin."}
                {activeSection === "security" &&
                  "Hesap güvenliği ve hassas sistem ayarlarını yapılandırın."}
              </p>
            </div>

            <div className="p-8 flex-1">
              {activeSection === "profile" && (
                <form
                  onSubmit={handleUpdateProfile}
                  className="space-y-8 max-w-4xl"
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Şirket ID
                      </label>
                      <div className="relative">
                        <input
                          readOnly
                          value={company?.company_id || ""}
                          className="w-full rounded-2xl bg-slate-50 border border-slate-200 px-10 py-4 text-sm font-black text-slate-400 outline-none cursor-not-allowed"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-lg">
                          lock
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Şirket Adı
                      </label>
                      <div className="relative">
                        <input
                          name="company_name"
                          defaultValue={company?.company_name || ""}
                          className="w-full rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-lg">
                          domain
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        İletişim Kişisi
                      </label>
                      <div className="relative">
                        <input
                          name="contact_person"
                          defaultValue={company?.contact_person || ""}
                          className="w-full rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-lg">
                          person
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Email Adresi
                      </label>
                      <div className="relative">
                        <input
                          name="email"
                          defaultValue={company?.email || ""}
                          className="w-full rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-lg">
                          mail
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Telefon
                      </label>
                      <div className="relative">
                        <input
                          name="phone"
                          defaultValue={company?.phone || ""}
                          className="w-full rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-lg">
                          call
                        </span>
                      </div>
                    </div>


                    <div className="col-span-full space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Adres Bilgisi
                      </label>
                      <div className="relative">
                        <textarea
                          name="address"
                          rows={3}
                          defaultValue={company?.address || ""}
                          className="w-full rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        />
                        <span className="material-symbols-rounded absolute left-4 top-10 text-brand-teal text-lg">
                          location_on
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end border-t border-slate-100 pt-8 mt-8">
                    <button
                      disabled={isSaving}
                      className="bg-brand-teal text-white px-10 py-4 rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 hover:-translate-y-0.5 disabled:opacity-50 cursor-pointer"
                    >
                      {isSaving ? "KAYDEDİLİRYOR..." : "DEĞİŞİKLİKLERİ KAYDET"}
                    </button>
                  </div>
                </form>
              )}

              {activeSection === "notifications" && (
                <div className="space-y-8 max-w-2xl">
                  <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 space-y-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-brand-teal">
                          <span className="material-symbols-rounded">mail</span>
                        </div>
                        <div>
                          <h5 className="text-sm font-black text-slate-900 uppercase">
                            E-posta Bildirimleri
                          </h5>
                          <p className="text-xs text-slate-500 font-bold">
                            İhlal durumlarında anlık e-posta gönder.
                          </p>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        className="w-12 h-6 bg-slate-200 rounded-full appearance-none checked:bg-brand-teal relative cursor-pointer before:absolute before:h-5 before:w-5 before:bg-white before:rounded-full before:top-0.5 before:left-0.5 checked:before:left-6 transition-all"
                        defaultChecked
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-brand-teal">
                          <span className="material-symbols-rounded">sms</span>
                        </div>
                        <div>
                          <h5 className="text-sm font-black text-slate-900 uppercase">
                            SMS Bildirimleri
                          </h5>
                          <p className="text-xs text-slate-500 font-bold">
                            Kritik ihlalleri telefonuna ilet.
                          </p>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        className="w-12 h-6 bg-slate-200 rounded-full appearance-none checked:bg-brand-teal relative cursor-pointer before:absolute before:h-5 before:w-5 before:bg-white before:rounded-full before:top-0.5 before:left-0.5 checked:before:left-6 transition-all"
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeSection === "ppe" && (
                <div className="space-y-10 max-w-4xl">
                  <div className="bg-amber-50 border border-amber-200 p-6 rounded-2xl flex gap-4">
                    <span className="material-symbols-rounded text-amber-500 text-3xl">
                      warning
                    </span>
                    <div>
                      <h5 className="text-sm font-black text-amber-800 uppercase italic">
                        Zorunlu PPE Seçimi
                      </h5>
                      <p className="text-xs text-amber-700/70 font-bold mt-1">
                        Seçilen ekipmanlar kameralarda tespit edilmediğinde
                        sistem ihlal olarak kaydedecektir.
                      </p>
                    </div>
                  </div>
                  {/* Yeni Sektör Seçimi Alanı */}
                  <div className="bg-slate-50 p-8 rounded-[2.5rem] border border-slate-100 flex flex-col md:flex-row items-center gap-8 mb-4 animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex-1 space-y-3 w-full">
                      <label className="text-[11px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Tesis Çalışma Sektörü
                      </label>
                      <div className="relative group overflow-hidden rounded-2xl shadow-sm">
                        <select
                          value={company?.sector || ""}
                          onChange={(e) => handleSectorChange(e.target.value)}
                          className="w-full appearance-none rounded-2xl bg-white border border-slate-200 px-12 py-5 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all cursor-pointer relative z-10"
                        >
                          <option value="">Sektör Seçiniz...</option>
                          <option value="construction">🏗️ İnşaat</option>
                          <option value="manufacturing">🏭 İmalat</option>
                          <option value="chemical">🧪 Kimya</option>
                          <option value="food">🍽️ Gıda</option>
                          <option value="warehouse">📦 Lojistik / Depolama</option>
                          <option value="energy">⚡ Enerji</option>
                          <option value="petrochemical">🛢️ Petrokimya</option>
                          <option value="marine">🚢 Denizcilik / Tersane</option>
                          <option value="aviation">✈️ Havacılık</option>
                        </select>
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-xl z-20 pointer-events-none">
                          factory
                        </span>
                        <span className="material-symbols-rounded absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-xl z-20 pointer-events-none group-hover:text-brand-teal transition-colors font-black">
                          expand_more
                        </span>
                      </div>
                    </div>
                    <div className="flex-[1.5] text-slate-500">
                      <p className="text-sm font-medium leading-relaxed">
                        Sektör değişikliği, tesisiniz için <span className="text-brand-teal font-black">varsayılan PPE kurallarını</span> ve <span className="text-brand-teal font-black">uyumluluk ayarlarını</span> otomatik olarak günceller.
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {getDisplayPpes().map((option) => {
                      const isMandatory = option.mandatory;
                      return (
                        <label
                          key={option.id}
                          className="group relative bg-white border border-slate-200 p-6 rounded-[2rem] cursor-pointer hover:border-brand-teal transition-all overflow-hidden"
                        >
                          <input
                            type="checkbox"
                            checked={!!isMandatory}
                            onChange={() => togglePPE(option.id)}
                            className="hidden"
                          />
                          {/* Background Decoration */}
                          <div className="absolute -right-4 -bottom-4 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity pointer-events-none">
                            <span className="material-symbols-rounded text-8xl font-black">
                              {option.icon}
                            </span>
                          </div>

                          <div className="flex items-center gap-4 relative z-10 w-full">
                            <div className={`h-14 w-14 rounded-2xl border flex-shrink-0 flex items-center justify-center transition-all shadow-sm ${
                              isMandatory 
                                ? "bg-brand-teal text-white border-brand-teal" 
                                : "bg-slate-50 text-slate-400 border-slate-200 group-hover:text-brand-teal group-hover:bg-brand-teal/5"
                            }`}>
                              <span className="material-symbols-rounded text-2xl">
                                {option.icon}
                              </span>
                            </div>
                            <div className="flex-1 pr-8">
                              <h6 className="text-[12px] leading-tight font-black text-slate-900 uppercase italic break-words">
                                {option.name}
                              </h6>
                              <p className="text-[9px] text-slate-400 font-bold uppercase tracking-tight mt-0.5">
                                {isMandatory ? "ZORUNLU" : "OPSİYONEL"}
                              </p>
                            </div>
                          </div>
                          <div className={`absolute top-1/2 -translate-y-1/2 right-6 h-6 w-6 rounded-full border-2 flex items-center justify-center transition-all z-20 shadow-sm ${
                            isMandatory ? "bg-brand-teal border-brand-teal" : "border-slate-200"
                          }`}>
                            <span className={`material-symbols-rounded text-white text-[10px] transition-all font-black ${
                              isMandatory ? "scale-100" : "scale-0"
                            }`}>
                              check
                            </span>
                          </div>
                        </label>
                      );
                    })}
                  </div>


                  <div className="flex justify-end pt-8">
                    <button 
                      onClick={handleUpdatePPE}
                      disabled={isSaving}
                      className="bg-brand-teal text-white px-10 py-4 rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 hover:-translate-y-0.5 cursor-pointer disabled:opacity-50"
                    >
                      {isSaving ? "KAYDEDİLİYOR..." : "AYARLARI KAYDET"}
                    </button>
                  </div>
                </div>
              )}

              {activeSection === "subscription" && (
                <div className="space-y-8 max-w-4xl">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="bg-slate-50 border border-slate-200 rounded-3xl p-8 space-y-6">
                      <div className="flex justify-between items-start">
                        <div className="space-y-1">
                          <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                            Mevcut Plan
                          </span>
                          <h4 className="text-3xl font-black text-slate-900 uppercase italic">
                            {company?.subscription_type || "PROFESYONEL"}
                          </h4>
                        </div>
                        <span className="bg-emerald-500 text-white text-[10px] font-black px-4 py-2 rounded-xl shadow-lg shadow-emerald-500/20">
                          AKTİF
                        </span>
                      </div>
                      <div className="pt-6 border-t border-slate-200 grid grid-cols-2 gap-4">
                        <div>
                          <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                            Kamera Limiti
                          </span>
                          <p className="text-xl font-black mt-1">
                            {company?.max_cameras || 25} ADET
                          </p>
                        </div>
                        <div>
                          <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                            Yenileme
                          </span>
                          <p className="text-xl font-black mt-1 text-emerald-600">
                            OTO
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-brand-orange to-orange-600 rounded-3xl p-8 text-white space-y-6 shadow-xl shadow-brand-orange/20">
                      <div className="h-14 w-14 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center">
                        <span className="material-symbols-rounded text-3xl font-black">
                          rocket_launch
                        </span>
                      </div>
                      <h4 className="text-xl font-black uppercase italic tracking-tight">
                        Kurumsal Güce Geçin!
                      </h4>
                      <p className="text-sm font-bold opacity-90 leading-relaxed">
                        Sınırsız kamera, 7/24 teknik destek ve size özel yapay
                        zeka modelleri için teklif alın.
                      </p>
                      <button className="w-full bg-white text-brand-orange py-4 rounded-2xl font-black text-[11px] uppercase tracking-widest transition-all hover:scale-[1.02] cursor-pointer">
                        TEKLİF AL
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {activeSection === "security" && (
                <div className="space-y-12 max-w-4xl">
                  <div className="space-y-6">
                    <h4 className="text-lg font-black text-slate-900 uppercase italic">
                      Şifre Değiştir
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                          Mevcut Şifre
                        </label>
                        <input
                          type="password"
                          placeholder="••••••••"
                          className="w-full rounded-2xl bg-white border border-slate-200 px-6 py-4 text-sm font-black text-slate-900 focus:border-red-500 focus:ring-4 focus:ring-red-500/10 outline-none transition-all"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                          Yeni Şifre
                        </label>
                        <input
                          type="password"
                          placeholder="••••••••"
                          className="w-full rounded-2xl bg-white border border-slate-200 px-6 py-4 text-sm font-black text-slate-900 focus:border-red-500 focus:ring-4 focus:ring-red-500/10 outline-none transition-all"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <button className="bg-red-500 text-white px-8 py-3 rounded-xl font-black text-[10px] uppercase tracking-widest shadow-lg shadow-red-500/20 hover:bg-red-600 hover:-translate-y-0.5 transition-all cursor-pointer">
                        ŞİFREYİ GÜNCELLE
                      </button>
                    </div>
                  </div>

                  <div className="pt-12 border-t border-slate-100 space-y-6">
                    <div className="p-8 rounded-3xl bg-red-50 border border-red-100 space-y-4">
                      <div className="flex gap-4 items-start">
                        <div className="p-3 bg-red-500 rounded-2xl text-white">
                          <span className="material-symbols-rounded">
                            dangerous
                          </span>
                        </div>
                        <div>
                          <h4 className="text-lg font-black text-red-600 uppercase italic">
                            Tehlikeli Bölge
                          </h4>
                          <p className="text-sm font-bold text-red-500/70">
                            Tüm verileriniz kalıcı olarak silinecektir. Lütfen
                            dikkatli olun.
                          </p>
                        </div>
                      </div>
                      <button className="bg-white text-red-500 border border-red-200 px-8 py-4 rounded-2xl font-black text-[11px] uppercase tracking-widest hover:bg-red-500 hover:text-white transition-all cursor-pointer">
                        HESABI TAMAMEN SİL
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
