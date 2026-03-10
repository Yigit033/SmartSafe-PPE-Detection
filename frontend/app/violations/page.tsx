"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
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
  const [selectedEvent, setSelectedEvent] = useState<ViolationEvent | null>(
    null,
  );
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Calendar states
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

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

  const filteredEvents = events.filter((e) => {
    // Priority 1: Date Filter
    if (selectedDate) {
      const eventDate = new Date(e.start_time * 1000);
      const isSameDay =
        eventDate.getDate() === selectedDate.getDate() &&
        eventDate.getMonth() === selectedDate.getMonth() &&
        eventDate.getFullYear() === selectedDate.getFullYear();
      if (!isSameDay) return false;
    }

    // Priority 2: Type Filter
    if (filter !== "all") {
      return e.violation_type.toLowerCase().includes(filter.toLowerCase());
    }

    return true;
  });

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

  const getViolationBadges = (type: string) => {
    const types = type.toLowerCase().split(",");

    return (
      <div className="flex flex-col gap-1 items-start">
        {types.map((t, idx) => {
          if (
            t.includes("hardhat") ||
            t.includes("baret") ||
            t.includes("helmet")
          )
            return (
              <span
                key={idx}
                className="bg-orange-100/90 backdrop-blur-sm text-orange-600 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest border border-orange-200 shadow-sm leading-none"
              >
                BARET İHLALİ
              </span>
            );
          if (t.includes("vest") || t.includes("yelek"))
            return (
              <span
                key={idx}
                className="bg-blue-100/90 backdrop-blur-sm text-blue-600 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest border border-blue-200 shadow-sm leading-none"
              >
                YELEK İHLALİ
              </span>
            );
          if (t.includes("shoes") || t.includes("ayakkabı"))
            return (
              <span
                key={idx}
                className="bg-purple-100/90 backdrop-blur-sm text-purple-600 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest border border-purple-200 shadow-sm leading-none"
              >
                AYAKKABI İHLALİ
              </span>
            );
          return (
            <span
              key={idx}
              className="bg-red-100/90 backdrop-blur-sm text-red-600 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest border border-red-200 shadow-sm leading-none"
            >
              GENEL İHLAL
            </span>
          );
        })}
      </div>
    );
  };

  const getViolationIcons = (type: string) => {
    const types = type
      .toLowerCase()
      .split(",")
      .map((item) => item.trim());
    return (
      <div className="flex flex-col gap-2 items-end">
        {types.map((t, idx) => {
          let label = "";
          let iconColor = "";
          let iconSvg = null;

          if (
            t.includes("hardhat") ||
            t.includes("baret") ||
            t.includes("helmet")
          ) {
            label = "BARET EKSİK";
            iconColor = "bg-orange-500";
            iconSvg = (
              <path
                d="M4 11C4 7 7 4 12 4C17 4 20 7 20 11H21V13C21 14 20 15 19 15H5C4 15 3 14 3 13V11H4Z"
                fill="currentColor"
                fillOpacity="0.2"
              />
            );
          } else if (t.includes("vest") || t.includes("yelek")) {
            label = "YELEK EKSİK";
            iconColor = "bg-blue-500";
            iconSvg = (
              <path
                d="M6 3L4 6V21H20V6L18 3H14V8L12 6L10 8V3H6Z"
                fill="currentColor"
                fillOpacity="0.2"
              />
            );
          } else if (t.includes("shoes") || t.includes("ayakkabı")) {
            label = "BOT EKSİK";
            iconColor = "bg-purple-500";
            iconSvg = (
              <path
                d="M4 14L3 17V20H21V18L17 14H13V16H10V14H4Z"
                fill="currentColor"
                fillOpacity="0.2"
              />
            );
          }

          if (!label) return null;

          return (
            <div key={idx} className="group/icon relative flex items-center">
              {/* Tooltip Box */}
              <div className="absolute right-full mr-3 whitespace-nowrap px-3 py-1.5 bg-slate-900/90 backdrop-blur-sm text-white text-[10px] font-black uppercase tracking-widest rounded-lg opacity-0 translate-x-2 invisible group-hover/icon:opacity-100 group-hover/icon:translate-x-0 group-hover/icon:visible transition-all duration-300 shadow-2xl z-50 pointer-events-none border border-white/10">
                {label}
                {/* Tooltip Arrow */}
                <div className="absolute top-1/2 -right-1 -translate-y-1/2 border-l-4 border-l-slate-900/90 border-t-4 border-t-transparent border-b-4 border-b-transparent"></div>
              </div>

              {/* Icon Circle */}
              <div
                title={label}
                className={`${iconColor} text-white p-1.5 rounded-lg shadow-lg border border-white/30 flex items-center justify-center transform hover:scale-110 transition-transform cursor-help`}
              >
                <svg
                  className="w-3.5 h-3.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  {iconSvg}
                  {t.includes("hardhat") ||
                  t.includes("baret") ||
                  t.includes("helmet") ? (
                    <>
                      <path d="M3 13H21M5 15V16C5 17 6 18 7 18H17C18 18 19 17 19 16V15" />
                      <path d="M12 4V7M8 5V7M16 5V7" />
                    </>
                  ) : t.includes("vest") || t.includes("yelek") ? (
                    <>
                      <path d="M12 3V21M8 8H16M8 14H16" />
                      <path d="M4 6H20" />
                    </>
                  ) : (
                    <path d="M4 14C4 14 6 11 10 11C14 11 17 14 17 14M7 11V8M13 11V8" />
                  )}
                </svg>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Calendar Helper Logic
  const daysInMonth = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const startDayOfMonth = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), 1).getDay();

  const hasViolationOnDay = (day: number) => {
    const targetDate = new Date(
      currentMonth.getFullYear(),
      currentMonth.getMonth(),
      day,
    );
    return events.some((e) => {
      const d = new Date(e.start_time * 1000);
      return (
        d.getDate() === targetDate.getDate() &&
        d.getMonth() === targetDate.getMonth() &&
        d.getFullYear() === targetDate.getFullYear()
      );
    });
  };

  const getMonthName = (date: Date) => {
    return date
      .toLocaleString("tr-TR", { month: "long", year: "numeric" })
      .toUpperCase();
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
          {selectedDate && (
            <button
              onClick={() => setSelectedDate(null)}
              className="bg-red-50 text-red-500 px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-red-100 transition-colors flex items-center gap-2 border border-red-100"
            >
              <span className="material-symbols-rounded text-sm">
                event_busy
              </span>
              FİLTREYİ KALDIR
            </button>
          )}
          <select
            className="bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-brand-orange outline-none shadow-sm cursor-pointer"
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">TÜM İHLAL TİPLERİ</option>
            <option value="hardhat">BARET EKSİK</option>
            <option value="vest">YELEK EKSİK</option>
          </select>
        </div>
      </section>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* Left Side: Calendar & Quick Info */}
        <aside className="lg:w-80 shrink-0 space-y-6 lg:sticky lg:top-24 self-start">
          <div className="bg-white rounded-[2rem] border border-slate-200 p-6 shadow-sm">
            {/* Calendar Header */}
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                {getMonthName(currentMonth)}
              </h3>
              <div className="flex gap-1">
                <button
                  onClick={() =>
                    setCurrentMonth(
                      new Date(
                        currentMonth.getFullYear(),
                        currentMonth.getMonth() - 1,
                        1,
                      ),
                    )
                  }
                  className="p-1.5 hover:bg-slate-50 rounded-lg text-slate-400 transition-colors"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M15 19l-7-7 7-7"
                    />
                  </svg>
                </button>
                <button
                  onClick={() =>
                    setCurrentMonth(
                      new Date(
                        currentMonth.getFullYear(),
                        currentMonth.getMonth() + 1,
                        1,
                      ),
                    )
                  }
                  className="p-1.5 hover:bg-slate-50 rounded-lg text-slate-400 transition-colors"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </button>
              </div>
            </div>

            {/* Calendar Grid */}
            <div className="grid grid-cols-7 gap-1 text-center mb-2">
              {["PT", "SA", "ÇR", "PR", "CM", "CT", "PZ"].map((day) => (
                <div
                  key={day}
                  className="text-[9px] font-black text-slate-300 uppercase tracking-tighter"
                >
                  {day}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-1">
              {Array.from({
                length: (startDayOfMonth(currentMonth) + 6) % 7,
              }).map((_, i) => (
                <div key={`empty-${i}`} className="h-10"></div>
              ))}
              {Array.from({ length: daysInMonth(currentMonth) }).map((_, i) => {
                const day = i + 1;
                const isSelected =
                  selectedDate &&
                  selectedDate.getDate() === day &&
                  selectedDate.getMonth() === currentMonth.getMonth() &&
                  selectedDate.getFullYear() === currentMonth.getFullYear();
                const hasViolations = hasViolationOnDay(day);

                return (
                  <button
                    key={day}
                    onClick={() =>
                      setSelectedDate(
                        new Date(
                          currentMonth.getFullYear(),
                          currentMonth.getMonth(),
                          day,
                        ),
                      )
                    }
                    className={`h-10 relative flex flex-col items-center justify-center rounded-xl text-xs font-bold transition-all ${
                      isSelected
                        ? "bg-brand-orange text-white shadow-lg shadow-orange-100"
                        : "hover:bg-slate-50 text-slate-600"
                    }`}
                  >
                    {day}
                    {hasViolations && !isSelected && (
                      <span className="absolute bottom-1.5 w-1 h-1 bg-brand-orange rounded-full animate-pulse"></span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="bg-brand-orange/5 rounded-[2rem] border border-brand-orange/10 p-6">
            <h4 className="text-[10px] font-black text-brand-orange uppercase tracking-widest mb-4">
              BUGÜNKÜ DURUM
            </h4>
            <div className="space-y-4">
              <div>
                <p className="text-[11px] font-black text-slate-500 uppercase leading-none mb-1">
                  TOPLAM İHLAL
                </p>
                <p className="text-2xl font-black text-slate-900 italic leading-none">
                  {
                    events.filter((e) => {
                      const d = new Date(e.start_time * 1000);
                      const now = new Date();
                      return (
                        d.getDate() === now.getDate() &&
                        d.getMonth() === now.getMonth()
                      );
                    }).length
                  }{" "}
                  <span className="text-[10px] text-slate-400 not-italic uppercase tracking-widest ml-1">
                    VAKA
                  </span>
                </p>
              </div>
            </div>
          </div>
        </aside>

        {/* Right Side: Feed Grid */}
        <div className="flex-1">
          {/* Grid */}
          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-6">
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
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-6">
              {filteredEvents.map((event) => (
                <div
                  key={event.event_id}
                  onClick={() => {
                    setSelectedEvent(event);
                    setIsModalOpen(true);
                  }}
                  className="group bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-xl hover:-translate-y-1.5 transition-all duration-500 cursor-pointer min-w-0 flex flex-col h-full"
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
                    <div className="absolute top-3 right-3 z-10">
                      {getViolationIcons(event.violation_type)}
                    </div>
                    {event.count > 1 && (
                      <div className="absolute bottom-2 right-2 bg-black/60 backdrop-blur-md text-white px-1.5 py-0.5 rounded text-[8px] font-black italic">
                        {event.count} KARE
                      </div>
                    )}
                  </div>

                  {/* Info Area */}
                  <div className="p-3 mt-auto border-t border-slate-50">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">
                          KAMERA
                        </h4>
                        <p className="text-[11px] font-black text-slate-900 uppercase truncate">
                          {event.camera_name || event.camera_id}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">
                          ZAMAN
                        </h4>
                        <p className="text-[11px] font-black text-slate-800">
                          {formatTime(event.start_time).split(" ")[1]}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              {/* Large Detail Modal */}
              {isModalOpen &&
                selectedEvent &&
                mounted &&
                createPortal(
                  <div
                    className="fixed inset-0 z-[150] flex items-center justify-center p-4 md:p-8 animate-fade-in"
                    lang="tr"
                  >
                    <div
                      className="absolute inset-0 bg-slate-950/90 backdrop-blur-xl"
                      onClick={() => setIsModalOpen(false)}
                    ></div>

                    <div className="relative w-full max-w-6xl max-h-[90vh] overflow-hidden rounded-[2rem] border border-white/10 bg-white shadow-2xl flex flex-col md:flex-row">
                      {/* Image Section */}
                      <div className="flex-[5] bg-slate-900 relative group overflow-hidden">
                        <img
                          src={getSnapshotUrl(selectedEvent.snapshot_path)}
                          alt="İhlal Detay"
                          className="w-full h-full object-contain"
                          onError={(e) => {
                            (e.target as any).src =
                              "https://via.placeholder.com/800x600?text=Görsel+Bulunamadı";
                          }}
                        />

                        {/* Badges on Image */}
                        <div className="absolute top-6 left-6 scale-125 origin-top-left">
                          {getViolationBadges(selectedEvent.violation_type)}
                        </div>
                      </div>

                      {/* Details Section */}
                      <div className="flex-[2] bg-white p-8 md:p-10 flex flex-col border-l border-slate-100 min-w-[320px]">
                        <div className="mb-8 flex items-center justify-between">
                          <div>
                            <h3 className="text-[10px] font-black text-brand-orange uppercase tracking-[0.2em] mb-1">
                              İHLAL DETAYLARI
                            </h3>
                            <h2 className="text-3xl font-black text-slate-900 italic tracking-tight uppercase">
                              GÜVENLİK İHLALİ
                            </h2>
                          </div>
                          <button
                            onClick={() => setIsModalOpen(false)}
                            className="p-3 rounded-2xl bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-all"
                          >
                            <svg
                              className="w-6 h-6"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2.5}
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          </button>
                        </div>

                        <div className="space-y-6 flex-1">
                          <div className="p-5 rounded-2xl bg-slate-50 border border-slate-100 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-sm">
                              <svg
                                className="w-6 h-6"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
                                />
                              </svg>
                            </div>
                            <div>
                              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">
                                KAYNAK KAMERA
                              </p>
                              <p className="text-base font-black text-slate-900 uppercase italic leading-none">
                                {selectedEvent.camera_name ||
                                  selectedEvent.camera_id}
                              </p>
                            </div>
                          </div>

                          <div className="p-5 rounded-2xl bg-slate-50 border border-slate-100 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-sm">
                              <svg
                                className="w-6 h-6"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                                />
                              </svg>
                            </div>
                            <div>
                              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">
                                OLAY ZAMANI
                              </p>
                              <p className="text-base font-black text-slate-900 uppercase italic leading-none">
                                {formatTime(selectedEvent.start_time)}
                              </p>
                            </div>
                          </div>

                          <div className="p-5 rounded-2xl bg-slate-50 border border-slate-100">
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">
                              TESPİT EDİLEN İHLALLER
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {selectedEvent.violation_type
                                .split(",")
                                .map((t, idx) => (
                                  <div
                                    key={idx}
                                    className="bg-white border border-slate-200 px-4 py-2 rounded-xl shadow-sm flex items-center gap-2"
                                  >
                                    <div
                                      className={`w-2 h-2 rounded-full ${t.includes("hardhat") || t.includes("baret") ? "bg-orange-500" : t.includes("vest") || t.includes("yelek") ? "bg-blue-500" : "bg-purple-500"}`}
                                    ></div>
                                    <span className="text-[11px] font-black uppercase text-slate-700 italic">
                                      {t
                                        .replace("hardhat", "BARET EKSİK")
                                        .replace("vest", "YELEK EKSİK")
                                        .replace("shoes", "AYAKKABI EKSİK")
                                        .toUpperCase()}
                                    </span>
                                  </div>
                                ))}
                            </div>
                          </div>
                        </div>

                        <div className="mt-auto pt-8 flex gap-4">
                          <button
                            onClick={() => setIsModalOpen(false)}
                            className="flex-1 bg-slate-900 text-white text-[10px] font-black py-5 rounded-2xl uppercase tracking-[0.2em] hover:bg-slate-800 transition-all shadow-xl shadow-slate-200"
                          >
                            KAPAT
                          </button>
                          <button className="bg-brand-orange text-white p-5 rounded-2xl hover:bg-brand-orange/90 transition-all shadow-xl shadow-orange-100">
                            <svg
                              className="w-6 h-6"
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
                  </div>,
                  document.body,
                )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
