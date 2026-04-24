"use client";

import { useState, useEffect } from "react";
import { getCompanyId } from "@/lib/session";
import api from "@/lib/api";
import core from "@/lib/core";
import { useConfirm } from "@/context/ConfirmContext";
import { 
  Building2, 
  Hammer, 
  Bell, 
  CreditCard, 
  ShieldCheck, 
  Lock, 
  User, 
  Mail, 
  Phone, 
  MapPin, 
  BellRing, 
  SendHorizontal, 
  Users, 
  ChevronDown, 
  AlertTriangle, 
  Factory, 
  Check, 
  HardHat, 
  Shirt, 
  Hand, 
  Eye, 
  Footprints, 
  VenetianMask, 
  UserSquare, 
  Accessibility, 
  Shield, 
  Headphones, 
  Waves,
  Box,
  LogOut,
  Rocket,
  OctagonAlert
} from "lucide-react";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");
  const [company, setCompany] = useState<any>(null);
  const [ppeRequirements, setPpeRequirements] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [systemBotUsername, setSystemBotUsername] = useState<string>("");
  const [notificationSettings, setNotificationSettings] = useState({
    email_notifications: false,
    sms_notifications: false,
    push_notifications: false,
    violation_alerts: true,
    telegram_notifications: false,
    telegram_bot_token: "",
    telegram_chat_id: ""
  });
  const companyId = getCompanyId();
  const { confirm } = useConfirm();

  useEffect(() => {
    fetchCompanyData();
  }, []);

  const fetchCompanyData = async () => {
    setIsLoading(true);
    try {
      const data = await api.company.getById(companyId);
      if (data.success) {
        setCompany(data.company);
        if ((data as any).system_bot_username) {
          setSystemBotUsername((data as any).system_bot_username);
        }
        setNotificationSettings({
          email_notifications: data.company.email_notifications || false,
          sms_notifications: data.company.sms_notifications || false,
          push_notifications: data.company.push_notifications || false,
          violation_alerts: data.company.violation_alerts !== false, // Default true
          telegram_notifications: data.company.telegram_notifications || false,
          telegram_bot_token: data.company.telegram_bot_token || "",
          telegram_chat_id: data.company.telegram_chat_id || ""
        });
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
      const data = await api.company.updateProfile(companyId, { 
        ...updates, 
        ppe_requirements: ppeRequirements 
      } as any);

      if (data.success) {
        await confirm({
          title: "BAŞARILI",
          message: "Şirket profil bilgileriniz başarıyla güncellendi.",
          confirmText: "TAMAM",
          type: "info"
        });
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
      const data = await api.company.updateProfile(companyId, { 
        sector: company?.sector,
        ppe_requirements: ppeRequirements 
      } as any);

      if (data.success) {
        await confirm({
          title: "KONFİGÜRASYON GÜNCELLENDİ",
          message: "PPE gereksinimleri ve sektör ayarlarınız sisteme kaydedildi.",
          confirmText: "TAMAM",
          type: "info"
        });
        fetchCompanyData();
      }
    } catch (error) {
      console.error("Error updating PPE config:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleUpdateNotifications = async () => {
    setIsSaving(true);
    try {
      const data = await api.company.updateNotifications(companyId, notificationSettings);
      if (data.success) {
        await confirm({
          title: "BİLDİRİMLER GÜNCELLENDİ",
          message: "Bildirim tercihleriniz başarıyla sisteme yansıtıldı.",
          confirmText: "TAMAM",
          type: "info"
        });
        fetchCompanyData();
      }
    } catch (error) {
      console.error("Error updating notifications:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSendTestNotification = async () => {
    try {
      const data = await core.sendTestNotification(companyId!);
      if (data.success) {
        await confirm({
          title: "BAĞLANTI DOĞRULANDI",
          message: "Test bildirimi gönderildi! Lütfen Telegram'ı kontrol edin.",
          confirmText: "HARİKA",
          type: "info"
        });
      } else {
        await confirm({
          title: "GÖNDERİLEMEDİ",
          message: "Hata: " + (data.error || "Bildirim gönderilemedi."),
          confirmText: "TEKRAR DENE",
          type: "danger"
        });
      }
    } catch (error) {
      console.error("Error sending test notification:", error);
      await confirm({
        title: "SİSTEM HATASI",
        message: "Bildirim servisine şu an ulaşılamıyor.",
        confirmText: "TAMAM",
        type: "danger"
      });
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

  const ppeOptionsMap: Record<string, { name: string; icon: any }> = {
    helmet: { name: "Kask/Baret", icon: HardHat },
    safety_helmet: { name: "Güvenlik Kaskı", icon: HardHat },
    vest: { name: "Güvenlik Yeleği", icon: Shirt },
    safety_vest: { name: "Yelek", icon: Shirt },
    gloves: { name: "Koruyucu Eldiven", icon: Hand },
    glasses: { name: "Güvenlik Gözlüğü", icon: Eye },
    safety_glasses: { name: "Gözlük", icon: Eye },
    shoes: { name: "Emniyet Ayakkabısı", icon: Footprints },
    boots: { name: "Emniyet Botu", icon: Footprints },
    safety_shoes: { name: "İş Ayakkabısı", icon: Footprints },
    mask: { name: "Maske", icon: VenetianMask },
    face_mask: { name: "Maske", icon: VenetianMask },
    hairnet: { name: "Bone", icon: UserSquare },
    apron: { name: "Önlük", icon: Accessibility },
    safety_suit: { name: "İş Tulumu", icon: Shield },
    headset: { name: "Koruyucu Kulaklık", icon: Headphones },
    earmuffs: { name: "Kulaklık", icon: Headphones },
    gas_mask: { name: "Gaz Maskesi", icon: VenetianMask },
    life_jacket: { name: "Can Yeleği", icon: Waves },
    insulated_gloves: { name: "İzole Eldiven", icon: Hand },
    dielectric_boots: { name: "Dielektrik Bot", icon: Footprints },
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
        icon: defined?.icon || Box,
        mandatory: !!req?.mandatory
      };
    });
  };

  const sections = [
    { id: "profile", name: "Şirket Profili", icon: Building2 },
    { id: "ppe", name: "PPE Konfigürasyonu", icon: Hammer },
    { id: "notifications", name: "Bildirimler", icon: Bell },
    { id: "subscription", name: "Abonelik", icon: CreditCard },
    { id: "security", name: "Güvenlik", icon: ShieldCheck },
  ];

  const cleanChatId = async (val: string) => {
    let clean = val.trim();
    setNotificationSettings(prev => ({ ...prev, telegram_chat_id: clean }));

    // Eğer bir URL veya aday bir username ise Backend'den gerçek ID'yi çekmeyi dene
    if (clean.includes("t.me") || (clean.length > 3 && !/^-?\d+$/.test(clean))) {
      try {
        const res = await (api.company as any).resolveTelegramChatId({
          chat_id_or_url: clean,
          bot_token: notificationSettings.telegram_bot_token || undefined
        });
        
        if (res.success && res.chat_id) {
          setNotificationSettings(prev => ({ ...prev, telegram_chat_id: res.chat_id! }));
        }
      } catch (e) {
        // Hata durumunda sessizce devam et, kullanıcı manuel girebilir
        console.debug("Telegram resolution failed:", e);
      }
    }
  };

  if (isLoading && !company) {
    return (
      <div className="flex flex-col gap-8 animate-pulse pb-12" lang="tr">
        {/* Header Skeleton */}
        <section className="space-y-3">
          <div className="h-10 w-48 bg-slate-200 rounded-2xl"></div>
          <div className="h-6 w-96 bg-slate-100 rounded-full"></div>
        </section>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar Skeleton */}
          <aside className="w-full lg:w-80 flex-shrink-0">
            <div className="h-[400px] bg-white border border-slate-200 rounded-3xl p-6 shadow-sm space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-14 w-full bg-slate-50 rounded-2xl"></div>
              ))}
            </div>
          </aside>

          {/* Content Skeleton */}
          <main className="flex-1 min-w-0">
            <div className="h-[600px] bg-white border border-slate-200 rounded-[2.5rem] shadow-sm flex flex-col overflow-hidden">
              <div className="h-32 bg-brand-teal/10 p-8 flex flex-col gap-4">
                <div className="h-8 w-48 bg-brand-teal/20 rounded-xl"></div>
                <div className="h-4 w-96 bg-slate-200/50 rounded-full"></div>
              </div>
              <div className="p-10 space-y-8">
                <div className="grid grid-cols-2 gap-8">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="space-y-3">
                      <div className="h-3 w-20 bg-slate-100 rounded-full ml-1"></div>
                      <div className="h-14 w-full bg-slate-50 rounded-2xl"></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </main>
        </div>
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
                <section.icon
                  className={`w-5 h-5 transition-transform ${
                    activeSection === section.id
                      ? "scale-110"
                      : "opacity-80 group-hover:scale-110 group-hover:opacity-100"
                  }`}
                />
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
                        <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 w-5 h-5" />
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
                        <Building2 className="absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal w-5 h-5" />
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
                        <User className="absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal w-5 h-5" />
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
                        <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal w-5 h-5" />
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
                        <Phone className="absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal w-5 h-5" />
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
                        <MapPin className="absolute left-4 top-10 text-brand-teal w-5 h-5" />
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
                <div className="space-y-8 max-w-4xl p-8">
                  <div className="p-8 rounded-3xl bg-slate-50 border border-slate-200 space-y-8">
                    {/* İhlal Uyarıları (Global) */}
                    <div className="flex items-center justify-between p-4 rounded-3xl bg-white border border-slate-100 shadow-sm">
                      <div className="flex items-center gap-4">
                        <div className="h-14 w-14 rounded-2xl bg-brand-teal/10 flex items-center justify-center text-brand-teal">
                          <BellRing className="w-6 h-6" />
                        </div>
                        <div>
                          <h5 className="text-sm font-black text-slate-900 uppercase italic">
                            İhlal Uyarıları
                          </h5>
                          <p className="text-[11px] text-slate-500 font-bold">
                            Tüm ihlal bildirimlerini genel olarak aç/kapat.
                          </p>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        className="w-14 h-7 bg-slate-200 rounded-full appearance-none checked:bg-brand-teal relative cursor-pointer before:absolute before:h-6 before:w-6 before:bg-white before:rounded-full before:top-0.5 before:left-0.5 checked:before:left-7 transition-all shadow-inner"
                        checked={notificationSettings.violation_alerts}
                        onChange={(e) => setNotificationSettings({...notificationSettings, violation_alerts: e.target.checked})}
                      />
                    </div>

                    <div className="h-px bg-slate-200 ml-4 mr-4" />

                    {/* Telegram Seksiyonu */}
                    <div className="space-y-6">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className="h-14 w-14 rounded-2xl bg-sky-500/10 flex items-center justify-center text-sky-500">
                            <SendHorizontal className="w-6 h-6" />
                          </div>
                          <div>
                            <h5 className="text-sm font-black text-slate-900 uppercase italic">
                              Telegram Bildirimleri
                            </h5>
                            <p className="text-[11px] text-slate-500 font-bold">
                              Anlık ihlal fotoğraflarını Telegram üzerinden al.
                            </p>
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          className="w-14 h-7 bg-slate-200 rounded-full appearance-none checked:bg-sky-500 relative cursor-pointer before:absolute before:h-6 before:w-6 before:bg-white before:rounded-full before:top-0.5 before:left-0.5 checked:before:left-7 transition-all shadow-inner"
                          checked={notificationSettings.telegram_notifications}
                          onChange={(e) => setNotificationSettings({...notificationSettings, telegram_notifications: e.target.checked})}
                        />
                      </div>

                      {notificationSettings.telegram_notifications && (
                        <div className="space-y-6 pl-18 animate-in fade-in slide-in-from-top-2 duration-300">
                          
                          {/* SİHİRLİ BAĞLANTI KUTUSU */}
                          <div className="bg-gradient-to-br from-sky-400 to-sky-600 p-8 rounded-[2.5rem] text-white shadow-xl shadow-sky-500/20 relative overflow-hidden group">
                            <div className="absolute -right-4 -bottom-4 opacity-20 group-hover:scale-110 transition-transform duration-700">
                                <SendHorizontal className="text-[120px] font-black" />
                            </div>

                            <div className="relative z-10 space-y-4">
                              <h4 className="text-lg font-black uppercase italic tracking-tighter">Hızlı Kurulum</h4>
                              <p className="text-xs font-bold opacity-90 leading-relaxed max-w-[280px]">
                                Hiçbir ayarla uğraşmadan, tek tıklamayla bildirimleri telefonunuza bağlayın.
                              </p>
                              
                              <div className="flex flex-wrap gap-4">
                                <button 
                                  onClick={() => window.open(`https://t.me/${systemBotUsername || 'smartsafeaibot'}?start=${companyId}`, '_blank')}
                                  className="bg-white text-sky-500 px-6 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg hover:scale-[1.02] active:scale-95 transition-all flex items-center gap-3"
                                >
                                  <User className="w-5 h-5" />
                                  Kendi Hesabıma Bağla
                                </button>

                                <button 
                                  onClick={() => window.open(`https://t.me/${systemBotUsername || 'smartsafeaibot'}?startgroup=${companyId}`, '_blank')}
                                  className="bg-sky-400 text-white px-6 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg hover:scale-[1.02] active:scale-95 transition-all flex items-center gap-3 border border-sky-300"
                                >
                                  <Users className="w-5 h-5" />
                                  Gruba / Kanala Ekle
                                </button>

                                <button 
                                  onClick={handleSendTestNotification}
                                  className="bg-sky-700 text-white px-6 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg hover:scale-[1.02] active:scale-95 transition-all flex items-center gap-3 border border-sky-600"
                                >
                                  <SendHorizontal className="w-5 h-5" />
                                  Test Bağlantısı Yolla
                                </button>
                              </div>

                              <div className="pt-2">
                                <p className="text-[10px] font-medium opacity-80 italic text-white/90">
                                  * Gruba ekledikten sonra botun mesaj yetkisi olduğundan emin olun. Bağlantı otomatik kurulacaktır.
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* GELİŞMİŞ AYARLAR (Opsiyonel) */}
                          <details className="group">
                            <summary className="text-[10px] font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-600 transition-colors list-none flex items-center gap-2">
                              <ChevronDown className="w-4 h-4 group-open:rotate-180 transition-transform" />
                              Manuel / Gelişmiş Ayarlar
                            </summary>
                            
                            <div className="grid grid-cols-1 gap-4 pt-4 mt-2 border-t border-slate-100 italic transition-all">
                              <div className="space-y-2">
                                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest ml-1">
                                  Bot Token (Cihaza Özel - Boş bırakılırsa sistem botu kullanılır)
                                </label>
                                <input
                                  type="password"
                                  value={notificationSettings.telegram_bot_token}
                                  onChange={(e) => setNotificationSettings({...notificationSettings, telegram_bot_token: e.target.value})}
                                  placeholder="Kendi botunuzu kullanmak isterseniz giriniz..."
                                  className="w-full rounded-2xl bg-white border border-slate-200 px-6 py-4 text-xs font-black text-slate-900 focus:border-sky-500 focus:ring-4 focus:ring-sky-500/10 outline-none transition-all"
                                />
                              </div>
                              <div className="space-y-2">
                                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest ml-1">
                                  Chat ID (User veya Grup ID)
                                </label>
                                <input
                                  type="text"
                                  value={notificationSettings.telegram_chat_id}
                                  onChange={(e) => cleanChatId(e.target.value)}
                                  placeholder="-100123456789 veya @kanaladi"
                                  className="w-full rounded-2xl bg-white border border-slate-200 px-6 py-4 text-xs font-black text-slate-900 focus:border-sky-500 focus:ring-4 focus:ring-sky-500/10 outline-none transition-all"
                                />
                                {notificationSettings.telegram_chat_id.includes("+") && (
                                  <p className="text-[10px] text-amber-600 font-bold ml-1 animate-pulse">
                                    ⚠️ Bu bir davet linki. Lütfen botu gruba ekleyip sayısal ID'yi (-100...) giriniz.
                                  </p>
                                )}
                              </div>
                            </div>
                          </details>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex justify-end pt-4">
                    <button
                      onClick={handleUpdateNotifications}
                      disabled={isSaving}
                      className="bg-brand-teal text-white px-10 py-4 rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 hover:-translate-y-0.5 disabled:opacity-50 cursor-pointer"
                    >
                      {isSaving ? "KAYDEDİLİRYOR..." : "BİLDİRİM AYARLARINI KAYDET"}
                    </button>
                  </div>
                </div>
              )}

              {activeSection === "ppe" && (
                <div className="space-y-10 max-w-4xl">
                  <div className="bg-amber-50 border border-amber-200 p-6 rounded-2xl flex gap-4">
                    <AlertTriangle className="text-amber-500 w-8 h-8" />
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
                        <Factory className="absolute left-4 top-1/2 -translate-y-1/2 text-brand-teal w-5 h-5 z-20 pointer-events-none" />
                        <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 w-5 h-5 z-20 pointer-events-none group-hover:text-brand-teal transition-colors font-black" />
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
                            <option.icon className="w-24 h-24 font-black" />
                          </div>

                          <div className="flex items-center gap-4 relative z-10 w-full">
                            <div className={`h-14 w-14 rounded-2xl border flex-shrink-0 flex items-center justify-center transition-all shadow-sm ${
                              isMandatory 
                                ? "bg-brand-teal text-white border-brand-teal" 
                                : "bg-slate-50 text-slate-400 border-slate-200 group-hover:text-brand-teal group-hover:bg-brand-teal/5"
                            }`}>
                              <option.icon className="w-6 h-6" />
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
                            <Check className={`text-white w-4 h-4 transition-all font-black ${
                              isMandatory ? "scale-100" : "scale-0"
                            }`} />
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
                        <Rocket className="w-8 h-8" />
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
                          <OctagonAlert className="w-6 h-6" />
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
