"use client";

import { useEffect, useState } from "react";
import { getCompanyId, getUser } from "@/lib/session";

interface StatsData {
  active_cameras: number;
  today_violations: number;
  monthly_violations: number;
  avg_compliance_rate: number;
  active_workers: number;
  trends: {
    cameras: number;
    violations: number;
    compliance: number;
  };
}

export default function Home() {
  const [data, setData] = useState<StatsData | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const companyId = getCompanyId();
        if (!companyId) return;
        // Stats ve Events'i paralel çekelim
        const [statsRes, eventsRes] = await Promise.all([
          fetch(`http://localhost:4000/company/${companyId}/stats`),
          fetch(`http://localhost:4000/company/${companyId}/violation-events`),
        ]);

        const statsResult = await statsRes.json();
        const eventsResult = await eventsRes.json();

        setData(statsResult);
        if (eventsResult.success) {
          setEvents(eventsResult.events.slice(0, 5)); // Sadece son 5 etkinlik
        }
      } catch (error) {
        console.error("Error fetching dashboard data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    // 30 saniyede bir güncelle
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const stats = [
    {
      name: "Aktif Kameralar",
      value: data ? `${data.active_cameras || 0} / 25` : "0 / 0",
      trend: data?.trends?.cameras || 0,
      icon: "video",
      color: "text-brand-teal",
      bg: "bg-primary-50",
    },
    {
      name: "PPE Uyum Oranı",
      value: data ? `%${(data.avg_compliance_rate || 0).toFixed(1)}` : "%0.0",
      trend: data?.trends?.compliance || 0,
      icon: "shield",
      color: "text-emerald-600",
      bg: "bg-emerald-50",
    },
    {
      name: "Günlük İhlaller",
      value: data ? (data.today_violations || 0).toString() : "0",
      trend: data?.trends?.violations || 0,
      icon: "warning",
      color: "text-brand-orange",
      bg: "bg-accent-50",
    },
    {
      name: "Aktif Çalışan",
      value: data ? data.active_workers.toString() : "0",
      trend: 0,
      icon: "cpu",
      color: "text-indigo-600",
      bg: "bg-indigo-50",
    },
  ];

  return (
    <div className="space-y-8 animate-fade-in pb-12 text-slate-900" lang="tr">
      {/* Header Info */}
      <section className="flex flex-col gap-2 relative">
        {loading && (
          <div className="absolute -top-2 -right-2 h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-teal opacity-75"></span>
            <span className="relative inline-flex rounded-full h-4 w-4 bg-brand-teal"></span>
          </div>
        )}
        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
          Hoş Geldiniz,{" "}
          <span className="text-brand-teal">
            {getUser()?.username || "Kullanıcı"}
          </span>
        </h2>
        <p className="text-slate-500 font-medium text-lg">
          Bugün tesisinizdeki güvenlik durumu{" "}
          {data && data.today_violations > 5
            ? "dikkat gerektiriyor"
            : "stabil görünüyor"}
          .
        </p>
      </section>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className={`group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200/50 transition-all duration-300 hover:shadow-md hover:-translate-y-1 cursor-pointer ${loading ? "opacity-70 animate-pulse" : ""}`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest leading-none">
                  {stat.name}
                </p>
                <h3 className="mt-3 text-3xl font-black text-slate-900 tracking-tight">
                  {stat.value}
                </h3>
              </div>
              <div
                className={`${stat.bg} flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-500 group-hover:scale-110`}
              >
                <span className={`text-2xl ${stat.color}`}>
                  {stat.icon === "video" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                      />
                    </svg>
                  )}
                  {stat.icon === "shield" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                      />
                    </svg>
                  )}
                  {stat.icon === "warning" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                  )}
                  {stat.icon === "cpu" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
                      />
                    </svg>
                  )}
                </span>
              </div>
            </div>
            <div className="mt-6 flex items-center gap-3">
              <span
                className={`flex items-center gap-1 text-[10px] font-black px-2 py-1 rounded-md uppercase tracking-wider ${stat.trend >= 0 ? "text-emerald-600 bg-emerald-100" : "text-red-600 bg-red-100"}`}
              >
                {stat.trend >= 0
                  ? `↑ ${stat.trend}`
                  : `↓ ${Math.abs(stat.trend)}`}
              </span>
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">
                {stat.name === "Aktif Kameralar"
                  ? "geçen haftaya göre"
                  : "önceki güne göre"}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2" lang="tr">
        {/* Main Analytics Card */}
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
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                />
              </svg>
              <h4 className="text-sm font-bold tracking-widest uppercase">
                GÜVENLİK TRENDİ
              </h4>
            </div>
            <span className="text-[10px] font-black px-2 py-1 bg-white/20 rounded-md backdrop-blur-sm">
              KURUMSAL STANDART
            </span>
          </div>
          <div className="p-8 flex-1">
            <div className="mb-6 flex items-center justify-between border-b border-slate-100 pb-4">
              <p className="text-sm font-bold text-slate-500">
                Tesis genelindeki PPE uyumluluk oranı analizi.
              </p>
              <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
                <button className="px-3 py-1 bg-white shadow-sm rounded-md text-[10px] font-black text-slate-900 border border-slate-200 cursor-pointer">
                  GÜNLÜK
                </button>
                <button className="px-3 py-1 text-[10px] font-black text-slate-500 hover:text-slate-900 cursor-pointer">
                  HAFTALIK
                </button>
              </div>
            </div>
            <div className="flex h-[320px] items-center justify-center rounded-xl bg-slate-50 border-2 border-dashed border-slate-200">
              <div className="text-center group cursor-pointer">
                <div className="mb-3 flex justify-center">
                  <svg
                    className="h-10 w-10 text-slate-300 group-hover:text-brand-teal transition-colors"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                    />
                  </svg>
                </div>
                <p className="text-sm font-bold text-slate-400 group-hover:text-slate-600 transition-colors">
                  Analitik grafik motoru yükleniyor...
                </p>
                <p className="mt-1 text-[10px] font-black text-slate-300 uppercase tracking-widest">
                  Ağ geçidi aktif: v2.0.4
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Recent Activity Card */}
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col">
          <div className="bg-brand-orange p-4 flex items-center justify-between text-white">
            <div className="flex items-center gap-2 text-white">
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
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h4 className="text-sm font-bold tracking-widest uppercase text-white">
                SON ETKİNLİKLER
              </h4>
            </div>
            <span className="text-[10px] font-black px-2 py-1 bg-white/20 rounded-md backdrop-blur-sm text-white uppercase">
              Canlı Takip
            </span>
          </div>
          <div className="p-8 space-y-8 flex-1">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center opacity-50">
                <p className="text-sm font-bold text-slate-400">
                  Görüntülenecek etkinlik bulunamadı.
                </p>
              </div>
            ) : (
              events
                .sort((a, b) => b.start_time - a.start_time)
                .slice(0, 5)
                .map((violation, idx) => (
                  <div
                    key={violation.event_id}
                    className="group relative flex gap-6"
                  >
                    <div className="flex flex-col items-center">
                      <div
                        className={`h-4 w-4 shrink-0 rounded-full border-2 border-white ring-4 ring-offset-2 ring-opacity-10 transition-all duration-500 group-hover:scale-125 ${
                          violation.violation_type
                            .toLowerCase()
                            .includes("hardhat") ||
                          violation.violation_type
                            .toLowerCase()
                            .includes("baret")
                            ? "bg-orange-500 ring-orange-500 shadow-md shadow-orange-500/20"
                            : violation.violation_type
                                  .toLowerCase()
                                  .includes("vest") ||
                                violation.violation_type
                                  .toLowerCase()
                                  .includes("yelek")
                              ? "bg-blue-500 ring-blue-500 shadow-md shadow-blue-500/20"
                              : "bg-purple-500 ring-purple-500 shadow-md shadow-purple-500/20"
                        }`}
                      ></div>
                      {idx < Math.min(events.length, 5) - 1 && (
                        <div className="mt-2 h-full w-0.5 bg-slate-100 group-hover:bg-slate-200 transition-colors"></div>
                      )}
                    </div>
                    <div className="space-y-2 pb-6 flex-1">
                      <div className="flex items-center justify-between gap-4">
                        <p className="text-sm font-black text-slate-900 leading-none italic uppercase">
                          {violation.violation_type
                            .toLowerCase()
                            .includes("hardhat") ||
                          violation.violation_type
                            .toLowerCase()
                            .includes("baret")
                            ? "Baret İhlali Tespit Edildi"
                            : violation.violation_type
                                  .toLowerCase()
                                  .includes("vest") ||
                                violation.violation_type
                                  .toLowerCase()
                                  .includes("yelek")
                              ? "Yelek İhlali Tespit Edildi"
                              : violation.violation_type
                                    .toLowerCase()
                                    .includes("shoes") ||
                                  violation.violation_type
                                    .toLowerCase()
                                    .includes("ayakkabı")
                                ? "Ayakkabı İhlali Tespit Edildi"
                                : "Güvenlik İhlali Tespit Edildi"}
                        </p>
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest whitespace-nowrap">
                          {new Date(
                            violation.start_time * 1000,
                          ).toLocaleTimeString("tr-TR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <p className="text-xs font-bold text-slate-500 leading-relaxed uppercase">
                        <span className="text-brand-teal">
                          {violation.camera_name || violation.camera_id}
                        </span>{" "}
                        noktasında ihlal kaydedildi. Sistem üzerinden takip
                        ediliyor.
                      </p>
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] font-black text-slate-300 uppercase italic">
                          ID: {violation.event_id.slice(0, 8)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
            )}
            <a
              href="/violations"
              className="w-full flex items-center justify-center gap-2 rounded-xl border-2 border-slate-100 bg-slate-50 py-3 text-xs font-black uppercase tracking-widest text-slate-500 transition-all hover:bg-slate-900 hover:text-white hover:border-slate-900 group cursor-pointer"
            >
              TÜMÜNÜ GÖRÜNTÜLE
              <svg
                className="h-4 w-4 transform group-hover:translate-x-1 transition-transform"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M17 8l4 4m0 0l-4 4m4-4H3"
                />
              </svg>
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}
