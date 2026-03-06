"use client";

import { useState, useEffect } from "react";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const companyId = "COMP_EE37F274";

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/subscription`,
      );
      const data = await response.json();
      if (data.success) {
        setSettings(data.subscription);
      }
    } catch (error) {
      console.error("Error fetching settings:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-slate-900 pb-12">
      <section className="flex flex-col gap-2">
        <h2 className="text-3xl font-extrabold tracking-tight">
          Sistem Ayarları
        </h2>
        <p className="text-slate-500 font-medium">
          Şirket profilinizi ve abonelik detaylarınızı buradan
          güncelleyebilirsiniz.
        </p>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Profile Card */}
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col">
          <div className="bg-brand-teal p-4 flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              <h4 className="text-sm font-bold tracking-widest uppercase italic">
                ŞİRKET PROFİLİ
              </h4>
            </div>
          </div>
          <div className="p-8 space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] text-slate-400 uppercase tracking-widest ml-1 text-sm font-bold italic">
                ŞİRKET ADI
              </label>
              <input
                defaultValue="SmartSafe Demo"
                className="w-full rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 text-sm font-black text-slate-900 focus:border-brand-teal/50 outline-none transition-all uppercase"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1 text-sm font-bold italic">
                İLETİŞİM E-POSTASI
              </label>
              <input
                defaultValue="dilsadselim@gmail.com"
                className="w-full rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 text-sm font-black text-slate-900 focus:border-brand-teal/50 outline-none transition-all lowercase"
              />
            </div>
            <button className="w-full bg-brand-teal text-white py-4 rounded-xl font-black text-[11px] uppercase tracking-[0.2em] shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90">
              DEĞİŞİKLİKLERİ KAYDET
            </button>
          </div>
        </section>

        {/* Subscription Card */}
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col">
          <div className="bg-brand-orange p-4 flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
              <h4 className="text-sm font-bold tracking-widest uppercase italic">
                ABONELİK PLANI
              </h4>
            </div>
          </div>
          <div className="p-8 space-y-8 flex-1">
            <div className="flex items-center justify-between items-start border-b border-slate-100 pb-4">
              <div className="flex flex-col">
                <span className="text-xs font-black text-slate-400 uppercase tracking-widest leading-none">
                  Mevcut Plan
                </span>
                <span className="text-2xl font-black text-slate-900 mt-2 uppercase italic">
                  {settings?.subscription_type || "PROFESYONEL"}
                </span>
              </div>
              <span className="bg-emerald-500 text-white text-[10px] font-black px-3 py-1.5 rounded-lg shadow-sm">
                AKTİF
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 border border-slate-200 p-6 rounded-2xl">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-tighter italic leading-none">
                  KAMERA LİMİTİ
                </p>
                <h5 className="text-2xl font-black text-slate-900 mt-3">
                  {settings?.max_cameras || 25}
                </h5>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-6 rounded-2xl">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-tighter italic leading-none">
                  OTO YENİLEME
                </p>
                <h5 className="text-2xl font-black text-emerald-600 mt-3">
                  {settings?.auto_renewal ? "AÇIK" : "KAPALI"}
                </h5>
              </div>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 flex flex-col gap-4">
              <h5 className="text-[10px] font-black text-amber-700 uppercase tracking-widest italic">
                KURUMSAL PLANA GEÇİŞ
              </h5>
              <p className="text-xs font-bold text-amber-600 leading-relaxed">
                Daha fazla kamera ve gelişmiş AI özellikleri için kurumsal plana
                yükseltebilirsiniz.
              </p>
              <button className="bg-brand-orange text-white py-3 rounded-lg font-black text-[10px] uppercase tracking-widest shadow-lg shadow-brand-orange/20 transition-all hover:bg-brand-orange/90">
                PLAN YÜKSELT
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
