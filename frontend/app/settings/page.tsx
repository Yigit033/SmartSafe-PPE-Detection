"use client";

import { useState, useEffect } from "react";
import { getCompanyId } from "@/lib/session";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");
  const [company, setCompany] = useState<any>(null);
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

      const response = await fetch(
        `http://localhost:4000/company/${companyId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        },
      );

      const data = await response.json();
      if (data.success) {
        alert("Profil başarıyla güncellendi!");
        fetchCompanyData();
      }
    } catch (error) {
      console.error("Error updating profile:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const ppeOptions = [
    { id: "helmet", name: "Kask", icon: "hard_hat" },
    { id: "vest", name: "Yelek", icon: "vest" },
    { id: "gloves", name: "Eldiven", icon: "back_hand" },
    { id: "glasses", name: "Gözlük", icon: "visibility" },
    { id: "boots", name: "Bot", icon: "ice_skating" },
  ];

  const sections = [
    { id: "profile", name: "Şirket Profili", icon: "domain" },
    { id: "ppe", name: "PPF Konfigürasyonu", icon: "construction" },
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
        <aside className="w-full lg:w-72 flex-shrink-0">
          <nav className="flex flex-col gap-2 p-4 rounded-3xl bg-white border border-slate-200 shadow-sm">
            {sections.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`flex items-center gap-3 px-6 py-4 rounded-2xl text-sm font-black transition-all cursor-pointer ${
                  activeSection === section.id
                    ? "bg-brand-teal text-white shadow-lg shadow-brand-teal/20 translate-x-1"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <span className="material-symbols-rounded text-xl opacity-80">
                  {section.icon}
                </span>
                <span className="uppercase tracking-widest">
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

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        Sektör
                      </label>
                      <div className="relative">
                        <select
                          name="sector"
                          defaultValue={company?.sector || "manufacturing"}
                          className="w-full appearance-none rounded-2xl bg-white border border-slate-200 px-10 py-4 text-sm font-black text-slate-900 focus:border-brand-teal focus:ring-4 focus:ring-brand-teal/10 outline-none transition-all"
                        >
                          <option value="construction">🏗️ İnşaat</option>
                          <option value="manufacturing">🏭 İmalat</option>
                          <option value="chemical">🧪 Kimya</option>
                          <option value="food">🍽️ Gıda</option>
                          <option value="warehouse">📦 Depo/Lojistik</option>
                          <option value="energy">⚡ Enerji</option>
                        </select>
                        <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal text-lg">
                          industry
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
                <div className="space-y-8 max-w-4xl">
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

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {ppeOptions.map((option) => (
                      <label
                        key={option.id}
                        className="group relative bg-white border border-slate-200 p-6 rounded-2xl cursor-pointer hover:border-brand-teal transition-all"
                      >
                        <input
                          type="checkbox"
                          className="hidden peer"
                          defaultChecked={
                            option.id === "helmet" || option.id === "vest"
                          }
                        />
                        <div className="flex items-center gap-4">
                          <div className="h-14 w-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 group-hover:text-brand-teal group-hover:bg-brand-teal/5 transition-all peer-checked:bg-brand-teal peer-checked:text-white peer-checked:border-brand-teal">
                            <span className="material-symbols-rounded text-2xl">
                              {option.icon}
                            </span>
                          </div>
                          <div>
                            <h6 className="text-sm font-black text-slate-900 uppercase italic">
                              {option.name}
                            </h6>
                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tight">
                              Tespit Aktif
                            </p>
                          </div>
                        </div>
                        <div className="absolute top-4 right-4 h-6 w-6 rounded-full border-2 border-slate-200 peer-checked:bg-brand-teal peer-checked:border-brand-teal flex items-center justify-center transition-all">
                          <span className="material-symbols-rounded text-white text-xs scale-0 peer-checked:scale-100 transition-all">
                            check
                          </span>
                        </div>
                      </label>
                    ))}
                  </div>

                  <div className="pt-8 border-t border-slate-100">
                    <div className="space-y-4">
                      <h5 className="text-sm font-black text-slate-900 uppercase italic">
                        Başarı Eşiği (%)
                      </h5>
                      <div className="flex items-center gap-4">
                        <input
                          type="range"
                          className="flex-1 accent-brand-teal h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer"
                          defaultValue={85}
                        />
                        <span className="bg-brand-teal text-white font-black px-4 py-2 rounded-xl text-sm italic">
                          %85
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 font-bold leading-relaxed">
                        Bu değerin altındaki doğruluk oranları düşük güvenli
                        tespit olarak işaretlenir.
                      </p>
                    </div>
                  </div>

                  <div className="flex justify-end pt-8">
                    <button className="bg-brand-teal text-white px-10 py-4 rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 hover:-translate-y-0.5 cursor-pointer">
                      AYARLARI KAYDET
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
