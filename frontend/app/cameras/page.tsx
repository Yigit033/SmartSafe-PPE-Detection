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
  const [formData, setFormData] = useState({
    name: "deneme",
    ip_address: "161.9.103.100",
    location: "med",
    port: 8080,
    protocol: "HTTP",
    stream_path: "/video",
    username: "dilsadselim@gmail.com",
    password: "",
    model: "Otomatik Tespit",
  });

  const [testResult, setTestResult] = useState<any>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("smart");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const response = await fetch(
        "http://localhost:4000/cameras/manual-test",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        },
      );
      const data = await response.json();
      setTestResult(data);
    } catch (error) {
      setTestResult({
        success: false,
        message: "Bağlantı hatası: Backend'e ulaşılamadı.",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const ModalPortal = () => {
    if (!mounted) return null;

    return createPortal(
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-black/90 backdrop-blur-md"
          onClick={() => setIsModalOpen(false)}
        ></div>
        <div className="relative w-full max-w-3xl rounded-[32px] border border-slate-800 bg-slate-950 p-8 shadow-2xl animate-fade-in card-glow overflow-y-auto max-h-[90vh]">
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Form Side */}
            <div className="space-y-6">
              {activeTab === "smart" ? (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                        IP Aralığı (CIDR)
                      </label>
                      <input
                        type="text"
                        defaultValue="192.168.1.0/24"
                        className="w-full rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-white focus:border-primary-500/50 outline-none transition-all"
                      />
                    </div>
                    <button className="w-full rounded-xl bg-primary-600/10 border border-primary-500/20 py-4 text-[10px] font-black text-primary-400 hover:bg-primary-600/20 transition-all uppercase tracking-widest">
                      Ağı Tara
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { label: "Kamera Adı *", key: "name" },
                      { label: "IP Adresi *", key: "ip_address" },
                      { label: "Konum *", key: "location" },
                      { label: "Port", key: "port", type: "number" },
                      { label: "Protokol", key: "protocol" },
                      { label: "Stream Path", key: "stream_path" },
                      { label: "Kullanıcı Adı", key: "username" },
                      { label: "Parola", key: "password", type: "password" },
                      { label: "Model", key: "model" },
                    ].map((f) => (
                      <div key={f.key} className="space-y-2">
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                          {f.label}
                        </label>
                        <input
                          type={f.type || "text"}
                          value={(formData as any)[f.key]}
                          onChange={(e) =>
                            setFormData({
                              ...formData,
                              [f.key]:
                                e.target.type === "number"
                                  ? parseInt(e.target.value)
                                  : e.target.value,
                            })
                          }
                          className="w-full rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-white focus:border-primary-500/50 outline-none transition-all"
                        />
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-4 pt-4 border-t border-slate-900">
                    <button
                      onClick={handleTestConnection}
                      disabled={isTesting}
                      className={`flex-1 flex items-center justify-center gap-2 rounded-2xl bg-amber-500/5 border border-amber-500/20 py-4 text-[10px] font-black text-amber-500 hover:bg-amber-500/10 transition-all uppercase tracking-[0.2em] ${isTesting ? "opacity-50 cursor-not-allowed" : ""}`}
                    >
                      {isTesting ? "BAĞLANILIYOR..." : "Bağlantıyı Test Et"}
                    </button>
                    <button className="flex-1 rounded-2xl bg-primary-600 py-4 text-[10px] font-black text-white shadow-xl shadow-primary-500/20 uppercase tracking-[0.2em] hover:bg-primary-500 transition-all">
                      Kamera Kaydet
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Preview Side */}
            <div className="flex flex-col gap-4">
              <div className="flex-1 min-h-[300px] rounded-3xl border border-slate-800 bg-slate-950 overflow-hidden relative flex items-center justify-center group card-glow">
                {testResult?.image_base64 ? (
                  <img
                    src={`data:image/jpeg;base64,${testResult.image_base64}`}
                    alt="Kamera Önizleme"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center space-y-4 p-8">
                    <div className="w-16 h-16 rounded-full bg-slate-900/50 border border-slate-800 flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-500">
                      <svg
                        className={`h-8 w-8 ${isTesting ? "text-amber-500 animate-pulse" : "text-slate-700"}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                        />
                      </svg>
                    </div>
                    <p className="text-[10px] font-black text-slate-600 uppercase tracking-[0.3em]">
                      {isTesting ? "GÖRÜNTÜ ALINIYOR..." : "TEST BAŞLATILMADI"}
                    </p>
                  </div>
                )}

                {/* Overlay for status */}
                {testResult && (
                  <div
                    className={`absolute top-4 left-4 px-3 py-1.5 rounded-full border text-[9px] font-black uppercase tracking-widest backdrop-blur-md shadow-2xl ${testResult.success ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-400" : "bg-red-500/20 border-red-500/40 text-red-400"}`}
                  >
                    {testResult.success ? "BAĞLANTI TAMAM" : "HATA"}
                  </div>
                )}
              </div>

              {/* Test Log Details */}
              {testResult && (
                <div className="rounded-2xl bg-slate-900/30 border border-slate-800/50 p-4 font-mono text-[9px] text-slate-500 overflow-y-auto max-h-[200px] shadow-inner">
                  <div className="flex justify-between mb-2 pb-1 border-b border-white/5">
                    <span className="text-white font-black italic tracking-widest">
                      SİSTEM GÜNLÜĞÜ
                    </span>
                    <span className="text-primary-500 font-bold tracking-tighter uppercase">
                      status: {testResult.success ? "ok" : "err"}
                    </span>
                  </div>
                  <div className="space-y-1.5 border-t border-slate-900 pt-3">
                    {testResult.message && (
                      <div className="text-white/80 italic tracking-tight">
                        {">"} {testResult.message}
                      </div>
                    )}
                    {testResult.test_results &&
                      Object.entries(testResult.test_results).map(
                        ([k, v]: any) => (
                          <div
                            key={k}
                            className="flex justify-between items-center group/log"
                          >
                            <span className="group-hover/log:text-white transition-colors uppercase tracking-tighter">
                              {k.replace("_", " ")}
                            </span>
                            <span
                              className={`font-bold ${v.status === "success" ? "text-emerald-500" : "text-red-500"}`}
                            >
                              {v.status
                                ? v.status.toUpperCase()
                                : typeof v === "object"
                                  ? "..."
                                  : String(v).toUpperCase()}
                            </span>
                          </div>
                        ),
                      )}
                  </div>
                </div>
              )}
            </div>
          </div>
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
