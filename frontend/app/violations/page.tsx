"use client";

import { useEffect, useState } from "react";
import { getCompanyId } from "@/lib/session";

interface ViolationEvent {
  event_id: string;
  company_id: string;
  camera_id: string;
  camera_name?: string;
  violation_type: string;
  start_time: number;
  end_time: number;
  snapshot_path: string;
  count: number;
  status: string;
}

export default function ViolationsPage() {
  const [events, setEvents] = useState<ViolationEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const companyId = getCompanyId();
        if (!companyId) return;
        const response = await fetch(
          `http://localhost:4000/company/${companyId}/violation-events`,
        );
        const result = await response.json();
        if (result.success) {
          setEvents(result.events);
        }
      } catch (error) {
        console.error("Error fetching events:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, []);

  const filteredEvents =
    filter === "all"
      ? events
      : events.filter((e) =>
          e.violation_type.toLowerCase().includes(filter.toLowerCase()),
        );

  // Resim URL'ini oluştur (Doğrudan Frontend/Public üzerinden çekmek için)
  const getSnapshotUrl = (path: string) => {
    if (!path) return "https://via.placeholder.com/400x300?text=Snapshot+Yok";
    // Path: COMP_XXX/CAM_XXX/2025-10-31/file.jpg şeklinde geliyor
    // Docker'da ../storage klasörünü frontend/public/storage altına mount ettik
    return `/storage/violations/${path}`;
  };

  const formatTime = (ts: number) => {
    const date = new Date(ts * 1000);
    return date.toLocaleString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    });
  };

  const getViolationBadge = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes("hardhat") || t.includes("baret") || t.includes("helmet"))
      return (
        <span className="bg-orange-100 text-orange-600 px-2 py-1 rounded-md text-[10px] font-black uppercase tracking-widest border border-orange-200">
          BARET İHLALİ
        </span>
      );
    if (t.includes("vest") || t.includes("yelek"))
      return (
        <span className="bg-blue-100 text-blue-600 px-2 py-1 rounded-md text-[10px] font-black uppercase tracking-widest border border-blue-200">
          YELEK İHLALİ
        </span>
      );
    return (
      <span className="bg-red-100 text-red-600 px-2 py-1 rounded-md text-[10px] font-black uppercase tracking-widest border border-red-200">
        GENEL İHLAL
      </span>
    );
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12" lang="tr">
      {/* Header */}
      <section className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
            İhlal <span className="text-brand-orange">Takip Akışı</span>
          </h2>
          <p className="text-slate-500 font-medium text-lg mt-1">
            Tesis genelindeki aktif ve geçmiş güvenlik ihlalleri.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            className="bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-brand-orange outline-none shadow-sm cursor-pointer"
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">TÜM İHLAL TİPLERİ</option>
            <option value="hardhat">BARET EKSİK</option>
            <option value="vest">YELEK EKSİK</option>
          </select>
          <button className="bg-white border border-slate-200 p-2.5 rounded-xl hover:bg-slate-50 transition-colors shadow-sm">
            <svg
              className="w-5 h-5 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </section>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-slate-100 p-2 h-48 animate-pulse min-w-0"
            >
              <div className="bg-slate-100 rounded-lg h-24 mb-2"></div>
              <div className="h-3 bg-slate-100 rounded w-1/2 mb-1"></div>
              <div className="h-2 bg-slate-100 rounded w-1/3"></div>
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 bg-white rounded-3xl border-2 border-dashed border-slate-200">
          <div className="bg-slate-50 p-6 rounded-full mb-4">
            <svg
              className="w-12 h-12 text-slate-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <p className="text-xl font-bold text-slate-400">
            Henüz bir ihlal tespiti bulunmuyor.
          </p>
          <p className="text-sm text-slate-300 uppercase tracking-widest mt-2">
            SİSTEM AKTİF - KAMERALAR İZLENİYOR
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {filteredEvents.map((event) => (
            <div
              key={event.event_id}
              className="group bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-pointer min-w-0"
            >
              {/* Snapshot Area */}
              <div className="relative aspect-video overflow-hidden bg-slate-900 border-b border-slate-100">
                <img
                  src={getSnapshotUrl(event.snapshot_path)}
                  alt="İhlal Snapshot"
                  className="w-full h-full object-contain group-hover:scale-110 transition-transform duration-700"
                  onError={(e) => {
                    (e.target as any).src =
                      "https://via.placeholder.com/400x300?text=Görsel+Bulunamadı";
                  }}
                />
                <div className="absolute top-2 left-2 scale-75 origin-top-left">
                  {getViolationBadge(event.violation_type)}
                </div>
                {event.count > 1 && (
                  <div className="absolute bottom-2 right-2 bg-black/60 backdrop-blur-md text-white px-1.5 py-0.5 rounded text-[8px] font-black italic">
                    {event.count} KARE
                  </div>
                )}
              </div>

              {/* Info Area */}
              <div className="p-2.5 space-y-2">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 pr-2">
                    <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-tight leading-tight truncate">
                      {event.camera_name || event.camera_id}
                    </h4>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[10px] font-black text-slate-800 leading-none">
                      {formatTime(event.start_time)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 pt-1 border-t border-slate-50">
                  <button className="flex-1 bg-slate-50 hover:bg-slate-100 text-slate-600 text-[8px] font-black py-1.5 rounded-md transition-colors uppercase tracking-widest truncate">
                    DETAY
                  </button>
                  <button className="bg-brand-orange/10 hover:bg-brand-orange/20 text-brand-orange p-1.5 rounded-md transition-colors">
                    <svg
                      className="w-3.5 h-3.5"
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
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
