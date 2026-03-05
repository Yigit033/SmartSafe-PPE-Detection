"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";

const cameras = [
  {
    id: "CAM-01",
    name: "Ana Giriş",
    ip: "192.168.1.45",
    location: "A Kapısı",
    status: "Aktif",
    detection: "Running",
    lastActivity: "2 dk önce",
  },
  {
    id: "CAM-02",
    name: "Depo-1",
    ip: "192.168.1.46",
    location: "Lojistik Bölgesi",
    status: "Aktif",
    detection: "Stopped",
    lastActivity: "5 dk önce",
  },
  {
    id: "CAM-03",
    name: "Üretim Hattı A",
    ip: "192.168.1.47",
    location: "Hangar-2",
    status: "Pasif",
    detection: "Disabled",
    lastActivity: "1 saat önce",
  },
  {
    id: "CAM-04",
    name: "Yükleme Alanı",
    ip: "192.168.1.48",
    location: "Dış Saha",
    status: "Hata",
    detection: "Disabled",
    lastActivity: "N/A",
  },
];

export default function CamerasPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("smart");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const ModalPortal = () => {
    if (!mounted) return null;

    return createPortal(
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-black/90 backdrop-blur-md"
          onClick={() => setIsModalOpen(false)}
        ></div>
        <div className="relative w-full max-w-2xl rounded-[32px] border border-slate-800 bg-slate-950 p-8 shadow-2xl animate-fade-in card-glow overflow-y-auto max-h-[90vh]">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-bold text-white uppercase tracking-tighter italic">
              Yeni Kamera Kaydı
            </h3>
            <button
              onClick={() => setIsModalOpen(false)}
              className="text-slate-500 hover:text-white transition-all"
            >
              <svg
                className="h-6 w-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          <div className="mb-8 flex gap-2 rounded-2xl bg-slate-900/50 p-1 border border-slate-800">
            <button
              onClick={() => setActiveTab("smart")}
              className={`flex-1 rounded-xl py-3 text-[10px] font-black uppercase tracking-[0.2em] transition-all ${activeTab === "smart" ? "bg-primary-600 text-white shadow-lg" : "text-slate-500 hover:text-slate-300"}`}
            >
              Akıllı Kurulum
            </button>
            <button
              onClick={() => setActiveTab("manual")}
              className={`flex-1 rounded-xl py-3 text-[10px] font-black uppercase tracking-[0.2em] transition-all ${activeTab === "manual" ? "bg-primary-600 text-white shadow-lg" : "text-slate-500 hover:text-slate-300"}`}
            >
              Manuel Kurulum
            </button>
          </div>

          {activeTab === "smart" ? (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                    IP Adresi
                  </label>
                  <input
                    type="text"
                    placeholder="192.168.1.100"
                    className="w-full rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-white focus:border-primary-500/50 outline-none transition-all"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                    Kamera Adı
                  </label>
                  <input
                    type="text"
                    placeholder="Yeni Kamera"
                    className="w-full rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-white focus:border-primary-500/50 outline-none transition-all"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <button className="flex-1 rounded-2xl bg-slate-900 border border-slate-800 py-4 text-[10px] font-black text-white hover:border-primary-500/50 transition-all uppercase tracking-widest">
                  Akıllı Tespit Başlat
                </button>
                <button className="flex-1 rounded-2xl bg-primary-600/10 border border-primary-500/20 py-4 text-[10px] font-black text-primary-400 hover:bg-primary-600/20 transition-all uppercase tracking-widest">
                  Hızlı Test (2sn)
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {[
                { label: "Kamera Adı *", p: "Giriş" },
                { label: "IP Adresi *", p: "192.168.1.xxx" },
                { label: "Konum *", p: "Örn: Hangar" },
                { label: "Port", p: "8080" },
                { label: "Protokol", p: "HTTP" },
                { label: "Stream Path", p: "/video" },
                { label: "Kullanıcı Adı", p: "admin" },
                { label: "Parola", p: "••••••••", t: "password" },
                { label: "Model", p: "Auto Detect" },
              ].map((f) => (
                <div key={f.label} className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                    {f.label}
                  </label>
                  <input
                    type={f.t || "text"}
                    placeholder={f.p}
                    className="w-full rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-white focus:border-primary-500/50 outline-none transition-all"
                  />
                </div>
              ))}
              <div className="col-span-full flex gap-4 mt-4">
                <button className="flex-1 rounded-2xl bg-amber-500/5 border border-amber-500/20 py-4 text-[10px] font-black text-amber-500 hover:bg-amber-500/10 transition-all uppercase tracking-[0.2em]">
                  Bağlantıyı Test Et
                </button>
                <button className="flex-1 rounded-2xl bg-primary-600 py-4 text-[10px] font-black text-white shadow-xl shadow-primary-500/20 uppercase tracking-[0.2em]">
                  Kamera Kaydet
                </button>
              </div>
            </div>
          )}
        </div>
      </div>,
      document.body,
    );
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {isModalOpen && <ModalPortal />}

      {/* Header Info */}
      <section className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-3xl font-bold tracking-tight text-white drop-shadow-sm">
            Kamera Yönetimi
          </h2>
          <p className="text-slate-400">
            Tesisinizdeki tüm kameraları ve DVR sistemlerini yönetin.
          </p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 rounded-xl bg-primary-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-primary-500/20 transition-all hover:bg-primary-500 hover:scale-[1.02]"
        >
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          YENİ KAMERA EKLE
        </button>
      </section>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <div className="group card-glow overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 p-6 transition-all duration-300">
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">
            Toplam Kamera
          </p>
          <h3 className="mt-2 text-3xl font-bold text-white tracking-tight">
            24 / 25
          </h3>
        </div>
        <div className="group card-glow overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 p-6 transition-all duration-300">
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">
            Aktif Analiz
          </p>
          <h3 className="mt-2 text-3xl font-bold text-emerald-400 tracking-tight">
            18{" "}
            <span className="text-sm font-medium text-slate-500 uppercase">
              Aygıt
            </span>
          </h3>
        </div>
        <div className="group card-glow overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 p-6 transition-all duration-300">
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">
            Bağlantı Sorunu
          </p>
          <h3 className="mt-2 text-3xl font-bold text-red-400 tracking-tight">
            2{" "}
            <span className="text-sm font-medium text-slate-500 uppercase">
              Hata
            </span>
          </h3>
        </div>
      </div>

      {/* Main Table Content */}
      <section className="rounded-3xl border border-slate-800 bg-slate-900/50 p-8 card-glow">
        <div className="mb-8 flex flex-col md:flex-row gap-6 items-center justify-between">
          <h4 className="text-lg font-bold text-white italic tracking-wide uppercase">
            Mevcut Kameralar
          </h4>
          <div className="relative w-full md:w-80">
            <input
              type="text"
              placeholder="Kamera ara..."
              className="w-full rounded-xl bg-slate-950 px-10 py-2.5 text-sm font-medium text-white border border-slate-800 focus:border-primary-500/50 outline-none transition-all"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <svg
              className="absolute left-3.5 top-3 h-4 w-4 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[11px] font-black text-slate-500 uppercase tracking-widest border-b border-slate-800">
                <th className="px-6 py-4">SİSTEM BİLGİSİ</th>
                <th className="px-6 py-4">LOKASYON</th>
                <th className="px-6 py-4">BAĞLANTI</th>
                <th className="px-6 py-4 text-right">İŞLEMLER</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {cameras.map((camera) => (
                <tr key={camera.id} className="group hover:bg-white/[0.01]">
                  <td className="px-6 py-6 font-bold text-white">
                    {camera.name}
                  </td>
                  <td className="px-6 py-6 text-slate-400 text-xs font-semibold uppercase">
                    {camera.location}
                  </td>
                  <td className="px-6 py-6">
                    <span
                      className={`inline-flex items-center gap-2 text-[11px] font-black uppercase ${camera.status === "Aktif" ? "text-emerald-500" : "text-red-500"}`}
                    >
                      <span
                        className={`h-2 w-2 rounded-full ${camera.status === "Aktif" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-red-500"}`}
                      ></span>
                      {camera.status}
                    </span>
                  </td>
                  <td className="px-6 py-6 text-right">
                    <div className="flex justify-end gap-2">
                      <button className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-500 hover:text-white transition-all shadow-sm">
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                      </button>
                      <button className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-500 hover:text-red-400 transition-all shadow-sm">
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
