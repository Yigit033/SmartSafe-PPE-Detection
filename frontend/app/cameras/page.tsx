"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";

// Mock data for initial state
const INITIAL_CAMERAS = [
  {
    camera_id: "CAM-01",
    camera_name: "Ana Giriş",
    ip_address: "192.168.1.45",
    location: "A Kapısı",
    status: "active",
    created_at: new Date().toISOString(),
  },
];

export default function CamerasPage() {
  const [cameras, setCameras] = useState<any[]>(INITIAL_CAMERAS);
  const [searchTerm, setSearchTerm] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("smart");
  const [mounted, setMounted] = useState(false);

  const [formData, setFormData] = useState({
    camera_name: "",
    camera_location: "",
    camera_ip: "",
    camera_port: 80,
    camera_protocol: "http",
    camera_path: "/video",
    camera_username: "",
    camera_password: "",
  });

  const companyId = "COMP_EE37F274"; // Temporary hardcoded ID

  useEffect(() => {
    setMounted(true);
    fetchCameras();
  }, []);

  const fetchCameras = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/cameras`,
      );
      const data = await response.json();
      if (data.success) {
        setCameras(data.cameras);
      }
    } catch (error) {
      console.error("Error fetching cameras:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/cameras`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        },
      );
      const data = await response.json();
      if (data.success) {
        setIsModalOpen(false);
        fetchCameras();
        // Reset form
        setFormData({
          camera_name: "",
          camera_location: "",
          camera_ip: "",
          camera_port: 80,
          camera_protocol: "http",
          camera_path: "/video",
          camera_username: "",
          camera_password: "",
        });
      } else {
        alert(data.error || "Kamera oluşturulamadı.");
      }
    } catch (error) {
      console.error("Error creating camera:", error);
    }
  };

  const handleDeleteCamera = async (cameraId: string) => {
    if (!confirm("Bu kamerayı silmek istediğinize emin misiniz?")) return;
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/cameras/${cameraId}`,
        {
          method: "DELETE",
        },
      );
      const data = await response.json();
      if (data.success) {
        fetchCameras();
      }
    } catch (error) {
      console.error("Error deleting camera:", error);
    }
  };

  const filteredCameras = cameras.filter(
    (cam) =>
      cam.camera_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cam.ip_address?.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  return (
    <div className="space-y-8 animate-fade-in text-slate-900 pb-12">
      {isModalOpen &&
        mounted &&
        createPortal(
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setIsModalOpen(false)}
            ></div>
            <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl animate-fade-in flex flex-col max-h-[90vh]">
              {/* Modal Header */}
              <div className="bg-brand-teal p-5 flex items-center justify-between text-white">
                <div className="flex items-center gap-2">
                  <svg
                    className="h-6 w-6"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  <h3 className="text-sm font-black tracking-widest uppercase italic">
                    YENİ KAMERA KAYDI
                  </h3>
                </div>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 hover:bg-white/20 rounded-lg transition-colors"
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
                      strokeWidth={2.5}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              <div className="p-8 overflow-y-auto">
                {/* Tabs */}
                <div className="mb-8 flex gap-2 rounded-xl bg-slate-100 p-1.5 border border-slate-200">
                  <button
                    onClick={() => setActiveTab("smart")}
                    className={`flex-1 rounded-lg py-2.5 text-[11px] font-black uppercase tracking-widest transition-all ${activeTab === "smart" ? "bg-white text-brand-teal shadow-sm border border-slate-200" : "text-slate-500 hover:text-slate-800"}`}
                  >
                    AKILLI KEŞİF
                  </button>
                  <button
                    onClick={() => setActiveTab("manual")}
                    className={`flex-1 rounded-lg py-2.5 text-[11px] font-black uppercase tracking-widest transition-all ${activeTab === "manual" ? "bg-white text-brand-teal shadow-sm border border-slate-200" : "text-slate-500 hover:text-slate-800"}`}
                  >
                    MANUEL EKLEME
                  </button>
                </div>

                {activeTab === "smart" ? (
                  <div className="space-y-6">
                    <div className="bg-cyan-50 border border-cyan-100 rounded-xl p-5 flex gap-4 items-start">
                      <div className="p-2 bg-brand-teal rounded-lg text-white">
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
                            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                      <div>
                        <h5 className="font-bold text-cyan-900 text-sm">
                          ONVIF Otomatik Keşif
                        </h5>
                        <p className="text-xs text-cyan-700 mt-1 leading-relaxed">
                          Ağınızdaki ONVIF uyumlu cihazlar taranarak otomatik
                          olarak listelenir. Bu işlem kurumsal network
                          yapılandırmanıza göre değişiklik gösterebilir.
                        </p>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                        IP Aralığı (CIDR)
                      </label>
                      <div className="flex gap-3">
                        <input
                          type="text"
                          placeholder="192.168.1.0/24"
                          className="flex-1 rounded-xl bg-white border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 focus:border-brand-teal/50 outline-none transition-all shadow-sm"
                        />
                        <button className="bg-brand-teal text-white px-6 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-brand-teal/90 transition-all shadow-md shadow-brand-teal/20">
                          TARA
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleCreateCamera} className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
                      {[
                        {
                          label: "Kamera Adı",
                          key: "camera_name",
                          placeholder: "Örn: Ana Giriş",
                        },
                        {
                          label: "Lokasyon",
                          key: "camera_location",
                          placeholder: "Örn: A Blok - 1. Kat",
                        },
                        {
                          label: "IP Adresi",
                          key: "camera_ip",
                          placeholder: "192.168.1.100",
                        },
                        {
                          label: "Port",
                          key: "camera_port",
                          type: "number",
                          placeholder: "80",
                        },
                        {
                          label: "Protokol",
                          key: "camera_protocol",
                          placeholder: "http/rtsp",
                        },
                        {
                          label: "Kanal / Path",
                          key: "camera_path",
                          placeholder: "/video",
                        },
                        {
                          label: "Kullanıcı Adı",
                          key: "camera_username",
                          placeholder: "admin",
                        },
                        {
                          label: "Şifre",
                          key: "camera_password",
                          type: "password",
                          placeholder: "••••••••",
                        },
                      ].map((f) => (
                        <div key={f.key} className="space-y-2">
                          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                            {f.label}
                          </label>
                          <input
                            type={f.type || "text"}
                            placeholder={f.placeholder}
                            value={(formData as any)[f.key]}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                [f.key]: e.target.value,
                              })
                            }
                            className="w-full rounded-xl bg-white border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 focus:border-brand-teal/50 outline-none transition-all shadow-sm"
                            required={
                              f.key !== "camera_username" &&
                              f.key !== "camera_password"
                            }
                          />
                        </div>
                      ))}
                    </div>

                    <div className="pt-6 border-t border-slate-100 flex gap-4">
                      <button
                        type="button"
                        className="flex-1 rounded-xl bg-slate-50 border-2 border-slate-100 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest hover:bg-slate-100 transition-all"
                        onClick={() => setIsModalOpen(false)}
                      >
                        VAZGEÇ
                      </button>
                      <button
                        type="submit"
                        className="flex-1 rounded-xl bg-brand-teal py-4 text-[10px] font-black text-white shadow-xl shadow-brand-teal/30 uppercase tracking-widest hover:bg-brand-teal/90 transition-all"
                      >
                        KAMERAYI KAYDET
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Header Info */}
      <section className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex flex-col gap-2">
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
            Kamera Altyapısı
          </h2>
          <p className="text-slate-500 font-medium">
            Tesisinizdeki tüm aktif görüntüleme sistemlerini tek bir noktadan
            yönetin.
          </p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 rounded-xl bg-brand-teal px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-teal/20 transition-all hover:bg-brand-teal/90 hover:-translate-y-0.5"
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
              strokeWidth={3}
              d="M12 4v16m8-8H4"
            />
          </svg>
          YENİ KAMERA EKLE
        </button>
      </section>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200/50">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">
            Toplam Kamera
          </p>
          <h3 className="mt-3 text-3xl font-black text-slate-900 tracking-tight">
            {cameras.length} / 25
          </h3>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200/50">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">
            Aktif Analiz
          </p>
          <h3 className="mt-3 text-3xl font-black text-emerald-600 tracking-tight">
            {cameras.filter((c) => c.status === "active").length}{" "}
            <span className="text-xs font-bold text-slate-400 uppercase">
              SİSTEM
            </span>
          </h3>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200/50">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">
            Hata Durumu
          </p>
          <h3 className="mt-3 text-3xl font-black text-brand-orange tracking-tight">
            0{" "}
            <span className="text-xs font-bold text-slate-400 uppercase">
              KRİTİK
            </span>
          </h3>
        </div>
      </div>

      {/* Table Container */}
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col min-h-[500px]">
        {/* Table Header Section */}
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
                d="M4 6h16M4 10h16M4 14h16M4 18h16"
              />
            </svg>
            <h4 className="text-sm font-bold tracking-widest uppercase">
              KAYITLI KAMERA LİSTESİ
            </h4>
          </div>
          <div className="flex items-center gap-4">
            <div className="relative hidden sm:block">
              <input
                type="text"
                placeholder="Hızlı Arama..."
                className="bg-white/20 backdrop-blur-sm border border-white/30 rounded-lg px-8 py-1.5 text-xs font-bold text-white placeholder:text-white/60 focus:bg-white/30 focus:outline-none transition-all w-48"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <svg
                className="absolute left-2.5 top-2 h-3.5 w-3.5 text-white/60"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
            <button
              onClick={fetchCameras}
              className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
            >
              <svg
                className={`h-5 w-5 ${isLoading ? "animate-spin" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Table Content */}
        <div className="flex-1 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 text-[10px] font-black text-slate-500 uppercase tracking-widest border-b border-slate-100">
                <th className="px-8 py-5">SİSTEM ADI</th>
                <th className="px-8 py-5">AĞ BİLGİSİ</th>
                <th className="px-8 py-5">KONUM</th>
                <th className="px-8 py-5">DURUM</th>
                <th className="px-8 py-5 text-right">YÖNETİM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading && cameras.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-8 py-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <div className="h-8 w-8 border-4 border-slate-200 border-t-brand-teal rounded-full animate-spin"></div>
                      <p className="text-xs font-black text-slate-400 uppercase tracking-widest">
                        Veriler Yükleniyor...
                      </p>
                    </div>
                  </td>
                </tr>
              ) : filteredCameras.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-8 py-20 text-center">
                    <p className="text-sm font-bold text-slate-400 italic">
                      Kamera bulunamadı.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredCameras.map((camera) => (
                  <tr
                    key={camera.camera_id}
                    className="group hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-8 py-6">
                      <div className="flex flex-col">
                        <span className="text-sm font-black text-slate-900 group-hover:text-brand-teal transition-colors uppercase italic">
                          {camera.camera_name}
                        </span>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter mt-1">
                          ID: {camera.camera_id.split("-")[0]}...
                        </span>
                      </div>
                    </td>
                    <td className="px-8 py-6">
                      <div className="flex flex-col">
                        <span className="text-xs font-bold text-slate-700">
                          {camera.ip_address}
                        </span>
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1 opacity-60">
                          PORT: {camera.port || 80} /{" "}
                          {camera.protocol || "HTTP"}
                        </span>
                      </div>
                    </td>
                    <td className="px-8 py-6">
                      <span className="text-[10px] font-black text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg uppercase tracking-widest">
                        {camera.location}
                      </span>
                    </td>
                    <td className="px-8 py-6">
                      <span
                        className={`inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest ${camera.status === "active" ? "text-emerald-600" : "text-slate-400"}`}
                      >
                        <span
                          className={`h-2.5 w-2.5 rounded-full ring-4 ring-offset-1 ${camera.status === "active" ? "bg-emerald-500 ring-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.3)]" : "bg-slate-300 ring-slate-100"}`}
                        ></span>
                        {camera.status === "active" ? "ÇALIŞIYOR" : "PASİF"}
                      </span>
                    </td>
                    <td className="px-8 py-6 text-right">
                      <div className="flex justify-end gap-2">
                        <button className="p-2.5 rounded-xl border border-slate-100 bg-white text-slate-400 hover:text-brand-teal hover:border-brand-teal/30 hover:shadow-lg hover:shadow-brand-teal/10 transition-all">
                          <svg
                            className="h-4 w-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2.5}
                              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2.5}
                              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteCamera(camera.camera_id)}
                          className="p-2.5 rounded-xl border border-slate-100 bg-white text-slate-400 hover:text-red-500 hover:border-red-200 hover:shadow-lg hover:shadow-red-500/10 transition-all"
                        >
                          <svg
                            className="h-4 w-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2.5}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Info */}
        <div className="bg-slate-50 p-6 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-100">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">
            SmartSafe AI Enterprise Security System v2.1
          </p>
          <div className="flex gap-2">
            <span className="text-[10px] font-black text-brand-teal uppercase bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-sm">
              LISANS: AKTIF
            </span>
            <span className="text-[10px] font-black text-slate-500 uppercase bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-sm">
              REGION: TR-WEST-1
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
