"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCompanyId, getUser } from "@/lib/session";
import {
  formatViolationEventTitle,
  violationSnapshotUrl,
} from "@/lib/violationAssets";
import { ImageOff } from "lucide-react";

import api from "@/lib/api";
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';

function ViolationThumb({ url }: { url: string | null }) {
  const [failed, setFailed] = useState(false);
  // Sabit yatay dikdörtgen çerçeve - Koyu zemin üzerinde dikey görseli korumak için object-contain
  const frame =
    "relative w-24 shrink-0 overflow-hidden rounded-xl border border-slate-200 aspect-[4/3] bg-[#0c1221]";
  
  if (!url || failed) {
    return (
      <div
        className={`flex items-center justify-center ${frame}`}
      >
        <ImageOff className="w-8 h-8 text-slate-500" />
      </div>
    );
  }
  return (
    <div className={frame}>
      <img
        src={url}
        alt=""
        className="h-full w-full object-contain p-1"
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

// StatsData interface is now unified via generated client types where possible, 
// but we'll keep a local interface for specific dashboard needs if it maps differently.
interface StatsData {
  active_cameras: number;
  max_cameras?: number;
  today_violations: number;
  monthly_violations: number;
  avg_compliance_rate: number;
  active_workers: number;
  compliance_trend?: { day: string; rate: number }[];
  hourly_compliance?: { hour: number; rate: number }[];
  trends?: {
    cameras: number;
    violations: number;
    compliance: number;
  };
}

export default function Home() {
  const [data, setData] = useState<StatsData | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"daily" | "weekly">("weekly");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const companyId = getCompanyId();
        if (!companyId) return;

        // Encore Client kullanarak paralel veri çekme
        const [statsResult, eventsResult] = await Promise.all([
          api.company.getStats(companyId),
          api.violation.getEvents(companyId)
        ]);

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
      value: data
        ? `${data.active_cameras || 0} / ${data.max_cameras ?? 25}`
        : "0 / 0",
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
      value: data ? (data.active_workers || 0).toString() : "0",
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
                className={`flex items-center gap-1 text-[10px] font-black px-2 py-1 rounded-md uppercase tracking-wider ${
                  stat.trend === 0
                    ? "text-slate-500 bg-slate-100"
                    : stat.trend > 0
                      ? "text-emerald-600 bg-emerald-100"
                      : "text-red-600 bg-red-100"
                }`}
              >
                {stat.trend === 0
                  ? "-"
                  : stat.trend > 0
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
                <button 
                  onClick={() => setTimeRange("daily")}
                  className={`px-3 py-1 rounded-md text-[10px] font-black transition-all cursor-pointer ${
                    timeRange === "daily" 
                      ? "bg-white shadow-sm text-slate-900 border border-slate-200" 
                      : "text-slate-500 hover:text-slate-900"
                  }`}
                >
                  GÜNLÜK
                </button>
                <button 
                  onClick={() => setTimeRange("weekly")}
                  className={`px-3 py-1 rounded-md text-[10px] font-black transition-all cursor-pointer ${
                    timeRange === "weekly" 
                      ? "bg-white shadow-sm text-slate-900 border border-slate-200" 
                      : "text-slate-500 hover:text-slate-900"
                  }`}
                >
                  HAFTALIK
                </button>
              </div>
            </div>
            <div className="flex h-[320px] items-center justify-center rounded-xl bg-slate-50 border border-slate-100 p-2">
              {loading ? (
                <div className="text-center group cursor-pointer">
                  <div className="mb-3 flex justify-center">
                    <svg
                      className="h-10 w-10 text-slate-300 animate-pulse"
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
                  <p className="text-sm font-bold text-slate-400">
                    Veriler hazırlanıyor...
                  </p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart 
                    data={
                      timeRange === "daily" 
                        ? (data?.hourly_compliance || []).map(d => ({ label: String(d.hour), rate: d.rate }))
                        : (data?.compliance_trend || []).map(d => ({ label: String(d.day), rate: d.rate }))
                    }
                  >
                    <defs>
                      <linearGradient id="colorRate" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#008080" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="#008080" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis 
                      dataKey="label" 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{fill: '#94a3b8', fontSize: 10, fontWeight: 700}}
                      dy={10}
                      tickFormatter={(val) => {
                        if (timeRange === "daily") return `${val}:00`;
                        return String(val).split('-').slice(1).join('/');
                      }}
                    />
                    <YAxis 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{fill: '#94a3b8', fontSize: 10, fontWeight: 700}}
                      tickFormatter={(val) => `%${val}`}
                      domain={[0, 100]}
                    />
                    <Tooltip 
                      contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)', fontSize: '11px', fontWeight: 800}}
                      labelFormatter={(val) => timeRange === "daily" ? `Saat: ${val}:00` : `Tarih: ${val}`}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="rate" 
                      stroke="#008080" 
                      strokeWidth={3}
                      fillOpacity={1} 
                      fill="url(#colorRate)" 
                      animationDuration={1000}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
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
                .sort(
                  (a, b) =>
                    Number(b.start_time || 0) - Number(a.start_time || 0),
                )
                .slice(0, 5)
                .map((violation, idx) => {
                  const vt = String(violation.violation_type || "");
                  const vtLower = vt.toLowerCase();
                  const ringClass =
                    /hardhat|baret|helmet|no_helmet|kask/.test(vtLower)
                      ? "bg-orange-500 ring-orange-500 shadow-md shadow-orange-500/20"
                      : /vest|yelek|no_vest/.test(vtLower)
                        ? "bg-blue-500 ring-blue-500 shadow-md shadow-blue-500/20"
                        : "bg-purple-500 ring-purple-500 shadow-md shadow-purple-500/20";
                  const thumb = violationSnapshotUrl(violation.snapshot_path);
                  const started = Number(violation.start_time || 0) * 1000;
                  return (
                    <div
                      key={violation.event_id}
                      className="group relative flex gap-4 sm:gap-6"
                    >
                      <div className="flex flex-col items-center shrink-0">
                        <div
                          className={`h-4 w-4 rounded-full border-2 border-white ring-4 ring-offset-2 ring-opacity-10 transition-all duration-500 group-hover:scale-125 ${ringClass}`}
                        />
                        {idx < Math.min(events.length, 5) - 1 && (
                          <div className="mt-2 min-h-[2.5rem] w-0.5 flex-1 bg-slate-100 group-hover:bg-slate-200 transition-colors" />
                        )}
                      </div>
                      <div className="flex min-w-0 flex-1 gap-3 pb-6">
                        <ViolationThumb url={thumb} />
                        <div className="min-w-0 flex-1 space-y-2">
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-sm font-black uppercase italic leading-snug text-slate-900">
                              {formatViolationEventTitle(vt)}
                            </p>
                            <span className="shrink-0 text-[10px] font-black uppercase tracking-widest text-slate-400 whitespace-nowrap">
                              {started
                                ? new Date(started).toLocaleTimeString(
                                    "tr-TR",
                                    {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    },
                                  )
                                : "—"}
                            </span>
                          </div>
                          <p className="text-xs font-bold uppercase leading-relaxed text-slate-500">
                            <span className="text-brand-teal">
                              {violation.camera_name ||
                                violation.camera_id ||
                                "Kamera"}
                            </span>{" "}
                            noktasında ihlal kaydedildi. Sistem üzerinden takip
                            ediliyor.
                          </p>
                          <p className="text-[10px] font-black uppercase italic text-slate-300">
                            ID: {violation.event_id}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })
            )}
            <Link
              href="/violations"
              className="group flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-slate-100 bg-slate-50 py-3 text-xs font-black uppercase tracking-widest text-slate-500 transition-all hover:border-slate-900 hover:bg-slate-900 hover:text-white"
            >
              TÜMÜNÜ GÖRÜNTÜLE
              <svg
                className="h-4 w-4 transform transition-transform group-hover:translate-x-1"
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
            </Link>
          </div>
        </section>
      </div>

      {/* Footer / Version Info */}
      <footer className="flex items-center justify-between pt-8 mt-4 border-t border-slate-100">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">
          © 2026 SmartSafe AI • TÜM HAKLARI SAKLIDIR
        </p>
        <div className="flex items-center gap-3">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
            SÜRÜM: v{process.env.NEXT_PUBLIC_VERSION || "1.0.0"}
          </span>
        </div>
      </footer>
    </div>
  );
}
