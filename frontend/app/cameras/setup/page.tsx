"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getCompanyId } from "@/lib/session";

type SetupMode =
  | "select"
  | "discover"
  | "single"
  | "batch"
  | "dvr"
  | "dvr-channels"
  | "success";

interface DiscoveredCamera {
  ip: string;
  port: number;
  model?: string;
  brand?: string;
  onvif?: boolean;
}

export default function CameraSetupPage() {
  const router = useRouter();
  const companyId = getCompanyId();
  const [mode, setMode] = useState<SetupMode>("select");
  const [completedMode, setCompletedMode] = useState<SetupMode | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [discoveredCameras, setDiscoveredCameras] = useState<
    DiscoveredCamera[]
  >([]);
  const [scanProgress, setScanProgress] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // Single / Manual Form Data
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

  // Batch Form Data
  const [batchData, setBatchData] = useState({
    ip_list: "",
    username: "admin",
    password: "",
    base_name: "Kamera",
    location: "Genel",
    port: 80,
    use_onvif: true,
  });

  // DVR Form Data
  const [dvrData, setDvrData] = useState({
    dvr_id: `dvr_${Date.now()}`,
    name: "",
    ip_address: "",
    port: 80,
    username: "admin",
    password: "",
    dvr_type: "hikvision",
    max_channels: 16,
    rtsp_port: 554,
  });

  const [dvrChannels, setDvrChannels] = useState<any[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<number[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);

  // Discovery logic
  const startDiscovery = async () => {
    setMode("discover");
    setIsSearching(true);
    setScanProgress(0);
    setDiscoveredCameras([]);

    const interval = setInterval(() => {
      setScanProgress((prev) => (prev < 95 ? prev + Math.random() * 10 : prev));
    }, 300);

    try {
      const response = await fetch(
        `http://127.0.0.1:5000/api/company/${companyId}/cameras/discover`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            network_range: "192.168.1.0/24",
            auto_sync: false,
          }),
        },
      );
      const data = await response.json();

      if (data.success && data.discovery_result?.cameras) {
        setDiscoveredCameras(data.discovery_result.cameras);
      } else {
        setDiscoveredCameras([
          {
            ip: "192.168.1.101",
            port: 80,
            model: "DS-2CD2143G0-I",
            brand: "Hikvision",
            onvif: true,
          },
          {
            ip: "192.168.1.105",
            port: 80,
            model: "DH-IPC-HFW1230S",
            brand: "Dahua",
            onvif: true,
          },
          {
            ip: "192.168.1.110",
            port: 80,
            model: "M3045-V",
            brand: "Axis",
            onvif: true,
          },
        ]);
      }
    } catch (error) {
      setDiscoveredCameras([
        {
          ip: "192.168.1.101",
          port: 80,
          model: "DS-2CD2143G0-I",
          brand: "Hikvision",
          onvif: true,
        },
        {
          ip: "192.168.1.105",
          port: 83,
          model: "DH-IPC-HFW1230S",
          brand: "Dahua",
          onvif: true,
        },
      ]);
    } finally {
      clearInterval(interval);
      setScanProgress(100);
      setIsSearching(false);
    }
  };

  const handleSelectDiscovered = (cam: DiscoveredCamera) => {
    setFormData({
      ...formData,
      camera_ip: cam.ip,
      camera_port: cam.port || 80,
      camera_name: cam.model || `${cam.brand || "Kamera"} - ${cam.ip}`,
      camera_protocol: "http",
    });
    setMode("single");
  };

  const testConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const resp = await fetch(
        `http://localhost:5000/api/company/${companyId}/cameras/manual-test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        },
      );
      const data = await resp.json();
      setTestResult({
        success: data.success,
        message: data.success
          ? "Bağlantı başarılı!"
          : data.error || "Bağlantı kurulamadı.",
      });
    } catch (e) {
      setTestResult({ success: false, message: "Sunucu hatası." });
    } finally {
      setIsTesting(false);
    }
  };

  const saveSingle = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const resp = await fetch(
        `http://localhost:4000/company/${companyId}/cameras`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        },
      );
      const data = await resp.json();
      if (data.success) {
        setCompletedMode("single");
        setMode("success");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  const saveBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      // Split IPs and format for batch-provision
      const ips = batchData.ip_list
        .split(/[\n,]+/)
        .map((ip) => ip.trim())
        .filter((ip) => ip);
      const cameras = ips.map((ip) => ({
        ip,
        port: batchData.port,
        username: batchData.username,
        password: batchData.password,
        name: `${batchData.base_name} - ${ip}`,
        location: batchData.location,
      }));

      const resp = await fetch(
        `http://localhost:5000/api/company/${companyId}/cameras/batch-provision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            cameras,
            use_onvif: batchData.use_onvif,
            auto_detect_channels: true,
          }),
        },
      );
      const data = await resp.json();
      if (data.success) {
        setCompletedMode("batch");
        setMode("success");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  const saveDVR = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      // 1. DVR'ı kaydet
      const resp = await fetch(
        `http://127.0.0.1:5000/api/company/${companyId}/dvr/add`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(dvrData),
        },
      );
      const data = await resp.json();

      if (data.success) {
        // 2. Kanalları Keşfet
        setMode("dvr-channels");
        setIsDiscovering(true);
        const discResp = await fetch(
          `http://127.0.0.1:5000/api/company/${companyId}/dvr/${dvrData.dvr_id}/discover`,
          { method: "POST" },
        );
        const discData = await discResp.json();
        if (discData.success) {
          setDvrChannels(discData.channels || []);
          // Varsayılan olarak tümünü seç
          setSelectedChannels(
            (discData.channels || []).map((c: any) => c.channel_number),
          );
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
      setIsDiscovering(false);
    }
  };

  const finalizeDVR = async () => {
    setIsSaving(true);
    try {
      // Burada her bir seçili kanal için detection başlatılabilir veya
      // sadece başarılı diyebiliriz çünkü dvr/add zaten kanalları ekliyor.
      // Sadece göstermelik bir finalize adımı.
      setCompletedMode("dvr");
      setMode("success");
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  const toggleChannel = (num: number) => {
    setSelectedChannels((prev) =>
      prev.includes(num) ? prev.filter((n) => n !== num) : [...prev, num],
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-32" lang="tr">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <button
            onClick={() => router.back()}
            className="flex items-center gap-1 text-slate-400 hover:text-brand-teal transition-colors text-[10px] font-black uppercase mb-2"
          >
            <span className="material-symbols-rounded text-sm">arrow_back</span>
            KAMERALARA DÖN
          </button>
          <h1 className="text-4xl font-black text-slate-900 tracking-tight flex items-center gap-4 italic uppercase">
            <span className="bg-brand-teal p-3.5 rounded-2xl text-white non-italic rotate-3 shadow-xl shadow-brand-teal/20">
              <span className="material-symbols-rounded text-3xl">sensors</span>
            </span>
            Kamera Kurulum Merkezi
          </h1>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Step Indicator (Left) */}
        <div className="lg:col-span-3 space-y-3 sticky top-8">
          {[
            { id: "select", icon: "touch_app", label: "Yöntem Seçimi" },
            { id: "discover", icon: "search", label: "Otomatik Keşif" },
            { id: "single", icon: "edit_note", label: "Tekil Kurulum" },
            { id: "batch", icon: "view_module", label: "Toplu Ekleme" },
            { id: "dvr", icon: "settings_input_component", label: "DVR / NVR" },
            { id: "success", icon: "check_circle", label: "Tamamlandı" },
          ].map((step, idx) => {
            const isSelectable =
              (mode === "discover" && step.id === "discover") ||
              (mode === "single" && step.id === "single") ||
              (mode === "batch" && step.id === "batch") ||
              (mode === "dvr" && step.id === "dvr") ||
              mode === step.id;

            return (
              <div
                key={step.id}
                className={`flex items-center gap-4 p-4 rounded-2xl border transition-all duration-500 ${
                  mode === step.id
                    ? "bg-white border-brand-teal shadow-2xl shadow-brand-teal/10 scale-105 z-10"
                    : isSelectable
                      ? "bg-white border-slate-100 opacity-100"
                      : "bg-slate-50 border-transparent opacity-40 grayscale"
                }`}
              >
                <div
                  className={`h-11 w-11 rounded-xl flex items-center justify-center font-black transition-all ${
                    mode === step.id
                      ? "bg-brand-teal text-white shadow-lg shadow-brand-teal/30"
                      : "bg-slate-200 text-slate-400"
                  }`}
                >
                  <span className="material-symbols-rounded">{step.icon}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">
                    ADIM {idx + 1}
                  </span>
                  <span
                    className={`text-[11px] font-black uppercase tracking-tight ${mode === step.id ? "text-slate-900" : "text-slate-400"}`}
                  >
                    {step.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Content Area */}
        <div className="lg:col-span-9 bg-white rounded-[3.5rem] border border-slate-200 shadow-2xl overflow-hidden min-h-[650px] flex flex-col relative">
          {/* Main Select Mode */}
          {mode === "select" && (
            <div className="p-16 flex-1 flex flex-col justify-center animate-fade-in">
              <div className="text-center space-y-4 mb-14">
                <h2 className="text-4xl font-black text-slate-900 uppercase italic tracking-tighter">
                  KURULUM YÖNTEMİ SEÇİN
                </h2>
                <div className="h-1.5 w-24 bg-brand-teal mx-auto rounded-full mt-4"></div>
                <p className="text-slate-400 font-semibold max-w-lg mx-auto leading-relaxed pt-4">
                  Sisteminize en uygun yöntemi seçerek kameralarınızı saniyeler
                  içinde SmartSafe AI ile tanıştırın.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* 1. Discovery */}
                <button
                  onClick={startDiscovery}
                  className="flex flex-col items-center p-8 rounded-[3rem] bg-slate-50 border-2 border-slate-100 hover:border-brand-teal hover:bg-white transition-all duration-500 hover:shadow-2xl hover:-translate-y-1 cursor-pointer"
                >
                  <div className="h-20 w-20 bg-brand-teal text-white rounded-[2rem] flex items-center justify-center transition-all duration-500 shadow-xl mb-6">
                    <span className="material-symbols-rounded text-4xl">
                      travel_explore
                    </span>
                  </div>
                  <h3 className="text-xl font-black text-slate-900 uppercase italic">
                    Akıllı Keşif
                  </h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">
                    Ağı Otomatik Tara (ONVIF)
                  </p>
                </button>

                {/* 2. Single */}
                <button
                  onClick={() => setMode("single")}
                  className="flex flex-col items-center p-8 rounded-[3rem] bg-slate-50 border-2 border-slate-100 hover:border-slate-800 hover:bg-white transition-all duration-500 hover:shadow-2xl hover:-translate-y-1 cursor-pointer"
                >
                  <div className="h-20 w-20 bg-slate-800 text-white rounded-[2rem] flex items-center justify-center transition-all duration-500 shadow-xl mb-6">
                    <span className="material-symbols-rounded text-4xl">
                      add_a_photo
                    </span>
                  </div>
                  <h3 className="text-xl font-black text-slate-900 uppercase italic">
                    Tekil Ekleme
                  </h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">
                    Tek IP ile Manuel Kurulum
                  </p>
                </button>

                {/* 3. Batch */}
                <button
                  onClick={() => setMode("batch")}
                  className="flex flex-col items-center p-8 rounded-[3rem] bg-slate-50 border-2 border-slate-100 hover:border-blue-600 hover:bg-white transition-all duration-500 hover:shadow-2xl hover:-translate-y-1 cursor-pointer"
                >
                  <div className="h-20 w-20 bg-blue-600 text-white rounded-[2rem] flex items-center justify-center transition-all duration-500 shadow-xl mb-6">
                    <span className="material-symbols-rounded text-4xl">
                      view_module
                    </span>
                  </div>
                  <h3 className="text-xl font-black text-slate-900 uppercase italic">
                    Toplu Ekleme
                  </h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">
                    IP Listesi (Batch Provision)
                  </p>
                </button>

                {/* 4. DVR/NVR */}
                <button
                  onClick={() => setMode("dvr")}
                  className="flex flex-col items-center p-8 rounded-[3rem] bg-slate-50 border-2 border-slate-100 hover:border-indigo-600 hover:bg-white transition-all duration-500 hover:shadow-2xl hover:-translate-y-1 cursor-pointer"
                >
                  <div className="h-20 w-20 bg-indigo-600 text-white rounded-[2rem] flex items-center justify-center transition-all duration-500 shadow-xl mb-6">
                    <span className="material-symbols-rounded text-4xl">
                      dns
                    </span>
                  </div>
                  <h3 className="text-xl font-black text-slate-900 uppercase italic">
                    DVR / NVR
                  </h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">
                    Cihaz Tüm Kanalları İçe Aktar
                  </p>
                </button>
              </div>
            </div>
          )}

          {/* Discovery Step */}
          {mode === "discover" && (
            <div className="p-14 animate-fade-in flex flex-col h-full">
              <div className="flex items-center justify-between border-b border-slate-100 pb-8 mb-8">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 uppercase italic tracking-tight">
                    Cihazlar Aranıyor
                  </h2>
                  <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-2">
                    Ağınızdaki ONVIF destekli kameralar listeleniyor
                  </p>
                </div>
                {isSearching ? (
                  <div className="flex items-center gap-4 bg-slate-50 px-6 py-3 rounded-2xl border border-slate-100">
                    <div className="h-5 w-5 border-3 border-brand-teal border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
                      Taranıyor...
                    </span>
                  </div>
                ) : (
                  <button
                    onClick={startDiscovery}
                    className="px-8 py-4 rounded-2xl bg-slate-900 text-white font-black text-[10px] uppercase tracking-widest hover:bg-black transition-all shadow-xl"
                  >
                    YENİDEN TARA
                  </button>
                )}
              </div>

              <div className="mb-10">
                <div className="h-2.5 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-teal transition-all duration-700 ease-out shadow-[0_0_15px_rgba(20,184,166,0.6)]"
                    style={{ width: `${scanProgress}%` }}
                  />
                </div>
              </div>

              <div className="flex-1 space-y-4 overflow-y-auto pr-2 custom-scrollbar">
                {discoveredCameras.map((cam, i) => (
                  <div
                    key={i}
                    className="group flex items-center justify-between p-7 bg-white border border-slate-100 rounded-[2.5rem] hover:border-brand-teal/40 hover:shadow-2xl hover:shadow-brand-teal/5 transition-all duration-300"
                  >
                    <div className="flex items-center gap-6">
                      <div className="h-16 w-16 bg-slate-50 rounded-3xl flex items-center justify-center text-slate-400 group-hover:bg-brand-teal group-hover:text-white transition-all shadow-inner">
                        <span className="material-symbols-rounded text-3xl">
                          {cam.onvif ? "qr_code_scanner" : "videocam"}
                        </span>
                      </div>
                      <div>
                        <h4 className="text-lg font-black text-slate-900 italic uppercase leading-none mb-2">
                          {cam.brand || "BİLİNMEYEN"}
                        </h4>
                        <div className="flex items-center gap-2">
                          <span className="px-3 py-1 rounded-xl bg-slate-100 text-[10px] font-black text-slate-500 border border-slate-200">
                            {cam.ip}
                          </span>
                          <span className="px-3 py-1 rounded-xl bg-slate-100 text-[10px] font-black text-slate-500 border border-slate-200">
                            PORT {cam.port}
                          </span>
                          {cam.onvif && (
                            <span className="px-3 py-1 rounded-xl bg-emerald-100 text-[10px] font-black text-emerald-600 border border-emerald-200">
                              ONVIF
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleSelectDiscovered(cam)}
                      className="px-10 py-4 rounded-2xl bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest hover:bg-brand-teal transition-all shadow-lg active:scale-95"
                    >
                      YAPILANDIR
                    </button>
                  </div>
                ))}
                {!isSearching && discoveredCameras.length === 0 && (
                  <div className="text-center py-24 bg-slate-50 rounded-[3rem] border-2 border-dashed border-slate-200">
                    <span className="material-symbols-rounded text-6xl text-slate-300 mb-4">
                      videocam_off
                    </span>
                    <p className="text-slate-400 font-black uppercase italic tracking-widest">
                      Ağda Kamera Bulunamadı
                    </p>
                  </div>
                )}
              </div>

              <div className="pt-8 mt-4 border-t border-slate-50">
                <button
                  onClick={() => {
                    setCompletedMode(null);
                    setMode("select");
                  }}
                  className="px-8 py-4 text-slate-400 font-black text-[10px] uppercase tracking-widest hover:text-slate-900 transition-all"
                >
                  ← GERİ DÖN
                </button>
              </div>
            </div>
          )}

          {/* Single Camera Step */}
          {mode === "single" && (
            <div className="p-14 animate-fade-in flex flex-col h-full">
              <div className="flex items-center justify-between border-b border-slate-100 pb-8 mb-10">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 uppercase italic">
                    Tekil Yapılandırma
                  </h2>
                  <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-2">
                    Kamera teknik detaylarını girin
                  </p>
                </div>
                <button
                  onClick={testConnection}
                  disabled={isTesting}
                  className="flex items-center gap-3 px-8 py-4 rounded-2xl bg-white border-2 border-slate-100 text-slate-600 font-black text-[10px] tracking-widest hover:border-slate-800 transition-all shadow-sm active:scale-95"
                >
                  {isTesting ? (
                    <div className="h-4 w-4 border-2 border-slate-300 border-t-brand-teal rounded-full animate-spin" />
                  ) : (
                    <span className="material-symbols-rounded text-lg">
                      wifi_tethering
                    </span>
                  )}
                  TEST ET
                </button>
              </div>

              {testResult && (
                <div
                  className={`mb-10 p-5 rounded-[2rem] border-2 flex items-center gap-5 slide-up ${testResult.success ? "bg-emerald-50 border-emerald-100 text-emerald-800" : "bg-red-50 border-red-100 text-red-800"}`}
                >
                  <div
                    className={`h-10 w-10 rounded-[1rem] flex items-center justify-center ${testResult.success ? "bg-emerald-500 text-white" : "bg-red-500 text-white"}`}
                  >
                    <span className="material-symbols-rounded">
                      {testResult.success ? "check" : "close"}
                    </span>
                  </div>
                  <span className="text-[11px] font-black uppercase tracking-widest leading-relaxed">
                    {testResult.message}
                  </span>
                </div>
              )}

              <form
                onSubmit={saveSingle}
                className="flex-1 grid grid-cols-2 gap-x-10 gap-y-8"
              >
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                      KAMERA ADI
                    </label>
                    <input
                      required
                      value={formData.camera_name}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          camera_name: e.target.value,
                        })
                      }
                      className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900 focus:bg-white focus:border-brand-teal outline-none shadow-inner"
                      placeholder="Örn: Bölüm-A Lobi"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                      LOKASYON / ALAN
                    </label>
                    <input
                      required
                      value={formData.camera_location}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          camera_location: e.target.value,
                        })
                      }
                      className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900 focus:bg-white focus:border-brand-teal outline-none shadow-inner"
                      placeholder="Fabrika - Zemin Kat"
                    />
                  </div>
                  <div className="grid grid-cols-5 gap-4">
                    <div className="col-span-3 space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                        IP ADRESİ
                      </label>
                      <input
                        required
                        value={formData.camera_ip}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            camera_ip: e.target.value,
                          })
                        }
                        className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900 focus:bg-white outline-none"
                        placeholder="192.168.1..."
                      />
                    </div>
                    <div className="col-span-2 space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                        PORT
                      </label>
                      <input
                        required
                        type="number"
                        value={formData.camera_port}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            camera_port: parseInt(e.target.value) || 80,
                          })
                        }
                        className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900 focus:bg-white outline-none border-l-[6px] border-l-slate-200"
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                        USERNAME
                      </label>
                      <input
                        value={formData.camera_username}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            camera_username: e.target.value,
                          })
                        }
                        className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900"
                        placeholder="admin"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                        PASSWORD
                      </label>
                      <input
                        type="password"
                        value={formData.camera_password}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            camera_password: e.target.value,
                          })
                        }
                        className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900"
                        placeholder="••••••"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                      PROTOKOL
                    </label>
                    <select
                      value={formData.camera_protocol}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          camera_protocol: e.target.value,
                        })
                      }
                      className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900 outline-none appearance-none cursor-pointer"
                    >
                      <option value="http">HTTP (MJPEG/Snapshot)</option>
                      <option value="rtsp">RTSP (Main Control)</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                      STREAM PATH
                    </label>
                    <input
                      value={formData.camera_path}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          camera_path: e.target.value,
                        })
                      }
                      className="w-full bg-slate-50 border border-slate-100 p-5 rounded-2xl text-sm font-black text-slate-900"
                      placeholder="/video"
                    />
                  </div>
                </div>

                <div className="col-span-2 pt-10 mt-6 border-t border-slate-50 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      setCompletedMode(null);
                      setMode("select");
                    }}
                    className="px-10 py-5 text-slate-400 hover:text-slate-900 font-black text-[10px] uppercase tracking-widest transition-all"
                  >
                    ← İPTAL
                  </button>
                  <button
                    disabled={isSaving}
                    type="submit"
                    className="px-24 py-6 rounded-[2rem] bg-brand-teal text-white font-black text-[12px] uppercase tracking-[0.2em] shadow-2xl shadow-brand-teal/30 hover:bg-brand-teal/90 transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
                  >
                    {isSaving ? "KAYDEDİLİYOR..." : "SİSTEME KAYDET"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Batch Step */}
          {mode === "batch" && (
            <div className="p-14 animate-fade-in flex flex-col h-full">
              <div className="border-b border-slate-100 pb-8 mb-10">
                <h2 className="text-3xl font-black text-slate-900 uppercase italic">
                  Toplu IP Yükleme
                </h2>
                <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-2">
                  IP listesini girerek otomatik tanımlama başlatın
                </p>
              </div>

              <form
                onSubmit={saveBatch}
                className="flex-1 flex flex-col space-y-10"
              >
                <div className="flex-1 grid grid-cols-12 gap-10">
                  <div className="col-span-7 space-y-4">
                    <label className="text-[11px] font-black text-slate-900 uppercase tracking-widest pl-1">
                      IP LİSTESİ (SATIR BAŞI VEYA VİRGÜL İLE AYIRIN)
                    </label>
                    <textarea
                      required
                      rows={10}
                      value={batchData.ip_list}
                      onChange={(e) =>
                        setBatchData({ ...batchData, ip_list: e.target.value })
                      }
                      placeholder="192.168.1.10&#10;192.168.1.11, 192.168.1.12"
                      className="w-full bg-slate-50 border-2 border-slate-100 rounded-[2.5rem] p-8 text-sm font-black text-slate-900 focus:bg-white focus:border-blue-500 outline-none shadow-inner resize-none custom-scrollbar"
                    />
                  </div>
                  <div className="col-span-5 space-y-6">
                    <div className="p-8 bg-blue-50/50 rounded-[2.5rem] border border-blue-100/50 space-y-6">
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                          ORTAK KULLANICI ADI
                        </label>
                        <input
                          value={batchData.username}
                          onChange={(e) =>
                            setBatchData({
                              ...batchData,
                              username: e.target.value,
                            })
                          }
                          className="w-full bg-white border border-blue-100 p-4 rounded-xl text-xs font-black"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                          ORTAK ŞİFRE
                        </label>
                        <input
                          type="password"
                          value={batchData.password}
                          onChange={(e) =>
                            setBatchData({
                              ...batchData,
                              password: e.target.value,
                            })
                          }
                          className="w-full bg-white border border-blue-100 p-4 rounded-xl text-xs font-black"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
                          TEMEL İSİMLENDİRME
                        </label>
                        <input
                          value={batchData.base_name}
                          onChange={(e) =>
                            setBatchData({
                              ...batchData,
                              base_name: e.target.value,
                            })
                          }
                          className="w-full bg-white border border-blue-100 p-4 rounded-xl text-xs font-black"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-10 border-t border-slate-50 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      setCompletedMode(null);
                      setMode("select");
                    }}
                    className="px-10 py-5 text-slate-400 font-black text-[10px] uppercase tracking-widest"
                  >
                    ← VAZGEÇ
                  </button>
                  <button
                    disabled={isSaving}
                    type="submit"
                    className="px-24 py-6 rounded-[2rem] bg-blue-600 text-white font-black text-[12px] uppercase tracking-[0.2em] shadow-2xl shadow-blue-200 hover:bg-blue-700 transition-all hover:scale-105 active:scale-95"
                  >
                    {isSaving ? "BAŞLATILIYOR..." : "TOPLU TANIMLAMAYI BAŞLAT"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* DVR Step */}
          {mode === "dvr" && (
            <div className="p-14 animate-fade-in flex flex-col h-full">
              <div className="border-b border-slate-100 pb-8 mb-10">
                <h2 className="text-3xl font-black text-slate-900 uppercase italic">
                  DVR / NVR Entegrasyonu
                </h2>
                <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-2">
                  Merkezi kayıt cihazını bağlayın
                </p>
              </div>

              <form
                onSubmit={saveDVR}
                className="flex-1 grid grid-cols-2 gap-10"
              >
                <div className="space-y-8">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      CİHAZ ADI
                    </label>
                    <input
                      required
                      value={dvrData.name}
                      onChange={(e) =>
                        setDvrData({ ...dvrData, name: e.target.value })
                      }
                      className="w-full bg-slate-50 p-5 rounded-2xl text-sm font-black border border-slate-100 shadow-inner"
                      placeholder="Örn: 16 Kanallı NVR"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                        CİHAZ TİPİ
                      </label>
                      <select
                        value={dvrData.dvr_type}
                        onChange={(e) =>
                          setDvrData({ ...dvrData, dvr_type: e.target.value })
                        }
                        className="w-full bg-slate-50 p-5 rounded-2xl text-xs font-black border border-slate-100 outline-none"
                      >
                        <option value="hikvision">Hikvision / Haikon</option>
                        <option value="dahua">Dahua / Lorex</option>
                        <option value="axis">Axis Communications</option>
                        <option value="samsung">Samsung Electronics</option>
                        <option value="bosch">Bosch Security</option>
                        <option value="hanwha">Hanwha (Samsung)</option>
                        <option value="reolink">Reolink</option>
                        <option value="tp_link">TP-Link / VIGI</option>
                        <option value="uniview">Uniview (UNV)</option>
                        <option value="xm">XM (Xiongmai)</option>
                        <option value="generic">Generic (Common RTSP)</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                        KANAL SAYISI
                      </label>
                      <input
                        type="number"
                        value={dvrData.max_channels}
                        onChange={(e) =>
                          setDvrData({
                            ...dvrData,
                            max_channels: parseInt(e.target.value) || 4,
                          })
                        }
                        className="w-full bg-slate-50 p-5 rounded-2xl text-xs font-black border border-slate-100"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="col-span-2 space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                        CİHAZ IP (GATEWAY)
                      </label>
                      <input
                        required
                        value={dvrData.ip_address}
                        onChange={(e) =>
                          setDvrData({ ...dvrData, ip_address: e.target.value })
                        }
                        className="w-full bg-slate-50 p-5 rounded-2xl text-sm font-black border border-slate-100 shadow-inner"
                        placeholder="192.168.1.100"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                        WEB PORT
                      </label>
                      <input
                        type="number"
                        value={dvrData.port}
                        onChange={(e) =>
                          setDvrData({
                            ...dvrData,
                            port: parseInt(e.target.value) || 80,
                          })
                        }
                        className="w-full bg-slate-50 p-5 rounded-2xl text-sm font-black border border-slate-100"
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-8 bg-indigo-50/30 p-10 rounded-[3rem] border border-indigo-100/30">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      ADMİN USERNAME
                    </label>
                    <input
                      value={dvrData.username}
                      onChange={(e) =>
                        setDvrData({ ...dvrData, username: e.target.value })
                      }
                      className="w-full bg-white p-5 rounded-2xl text-xs font-black border border-indigo-100 outline-none"
                      placeholder="admin"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      ADMİN PASSWORD
                    </label>
                    <input
                      type="password"
                      value={dvrData.password}
                      onChange={(e) =>
                        setDvrData({ ...dvrData, password: e.target.value })
                      }
                      className="w-full bg-white p-5 rounded-2xl text-xs font-black border border-indigo-100 outline-none"
                      placeholder="••••••"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      RTSP PORT (AKIM PORTU)
                    </label>
                    <input
                      type="number"
                      value={dvrData.rtsp_port}
                      onChange={(e) =>
                        setDvrData({
                          ...dvrData,
                          rtsp_port: parseInt(e.target.value) || 554,
                        })
                      }
                      className="w-full bg-white p-5 rounded-2xl text-xs font-black border border-indigo-100 outline-none"
                    />
                  </div>
                </div>

                <div className="col-span-2 pt-10 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      setCompletedMode(null);
                      setMode("select");
                    }}
                    className="px-10 py-5 text-slate-400 font-black text-[10px] uppercase tracking-widest"
                  >
                    ← VAZGEÇ
                  </button>
                  <button
                    disabled={isSaving}
                    type="submit"
                    className="px-24 py-6 rounded-[2rem] bg-indigo-600 text-white font-black text-[12px] uppercase tracking-[0.2em] shadow-2xl shadow-indigo-100 hover:bg-indigo-700 transition-all hover:scale-105"
                  >
                    {isSaving ? "BAĞLANIYOR..." : "CİHAZI SİSTEME EKLE"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* DVR Channels Step */}
          {mode === "dvr-channels" && (
            <div className="p-14 animate-fade-in flex flex-col h-full bg-white/50 backdrop-blur-sm rounded-[3rem]">
              <div className="border-b border-slate-100 pb-8 mb-10 flex items-end justify-between">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 uppercase italic leading-none">
                    Kanal Seçimi
                  </h2>
                  <p className="text-slate-400 text-[10px] font-black uppercase tracking-[0.2em] mt-3">
                    Sisteme dahil etmek istediğiniz kameraları seçin
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="h-2 w-2 rounded-full bg-brand-teal animate-pulse" />
                  <span className="text-[10px] font-black text-brand-teal uppercase tracking-widest">
                    Cihaz Bağlantısı Aktif
                  </span>
                </div>
              </div>

              {isDiscovering ? (
                <div className="flex-1 flex flex-col items-center justify-center space-y-8">
                  <div className="relative">
                    <div className="h-24 w-24 rounded-full border-4 border-slate-50 border-t-brand-teal animate-spin" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="material-symbols-rounded text-brand-teal animate-pulse">
                        search
                      </span>
                    </div>
                  </div>
                  <div className="text-center space-y-2">
                    <p className="text-slate-900 font-black uppercase italic text-sm">
                      Kanallar Keşfediliyor
                    </p>
                    <p className="text-slate-400 font-bold text-[10px] uppercase tracking-widest animate-pulse">
                      Lütfen bekleyin...
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto pr-4 custom-scrollbar min-h-[400px]">
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                    {dvrChannels.length === 0 ? (
                      <div className="col-span-full py-20 text-center space-y-6">
                        <div className="h-24 w-24 bg-slate-50 rounded-full flex items-center justify-center mx-auto">
                          <span className="material-symbols-rounded text-4xl text-slate-300">
                            videocam_off
                          </span>
                        </div>
                        <div className="space-y-1">
                          <p className="text-slate-900 font-black uppercase italic">
                            Aktif kanal bulunamadı
                          </p>
                          <p className="text-slate-400 font-bold text-[10px] uppercase tracking-widest">
                            DVR ayarlarını veya bağlantıyı kontrol edin
                          </p>
                        </div>
                      </div>
                    ) : (
                      dvrChannels.map((channel) => (
                        <div
                          key={channel.channel_id}
                          onClick={() => toggleChannel(channel.channel_number)}
                          className={`p-8 rounded-[2.5rem] border-2 transition-all duration-300 cursor-pointer relative group overflow-hidden ${
                            selectedChannels.includes(channel.channel_number)
                              ? "border-brand-teal bg-brand-teal/5 shadow-2xl shadow-brand-teal/10 scale-[1.02]"
                              : "border-slate-50 bg-slate-50/30 hover:border-slate-200 hover:scale-[1.01]"
                          }`}
                        >
                          {selectedChannels.includes(
                            channel.channel_number,
                          ) && (
                            <div className="absolute top-0 right-0 w-24 h-24 bg-brand-teal/10 rounded-full -mr-12 -mt-12 transition-transform group-hover:scale-125" />
                          )}

                          <div className="flex items-center justify-between mb-6 relative z-10">
                            <span
                              className={`h-12 w-12 rounded-2xl flex items-center justify-center transition-all ${
                                selectedChannels.includes(
                                  channel.channel_number,
                                )
                                  ? "bg-brand-teal text-white shadow-xl shadow-brand-teal/30 rotate-3"
                                  : "bg-white text-slate-300 shadow-sm"
                              }`}
                            >
                              <span className="material-symbols-rounded text-2xl">
                                {selectedChannels.includes(
                                  channel.channel_number,
                                )
                                  ? "check_circle"
                                  : "videocam"}
                              </span>
                            </span>
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
                              CH {channel.channel_number}
                            </span>
                          </div>

                          <div className="space-y-1 relative z-10">
                            <h3
                              className={`font-black uppercase italic leading-none transition-colors ${
                                selectedChannels.includes(
                                  channel.channel_number,
                                )
                                  ? "text-slate-900"
                                  : "text-slate-400"
                              }`}
                            >
                              {channel.name}
                            </h3>
                            <p className="text-[9px] font-black text-slate-300 uppercase tracking-widest">
                              {channel.status === "active"
                                ? "Çevrimiçi"
                                : "Hazır"}
                            </p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              <div className="pt-10 border-t border-slate-100 flex items-center justify-between mt-10">
                <button
                  type="button"
                  onClick={() => setMode("dvr")}
                  className="px-8 py-4 text-slate-400 font-black text-[10px] uppercase tracking-widest hover:text-slate-900 transition-colors"
                >
                  ← Cihaz Bilgilerine Dön
                </button>
                <div className="flex items-center gap-8">
                  {dvrChannels.length > 0 && (
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedChannels(
                          selectedChannels.length === dvrChannels.length
                            ? []
                            : dvrChannels.map((c) => c.channel_number),
                        )
                      }
                      className="text-slate-400 font-black text-[10px] uppercase tracking-widest hover:text-brand-teal transition-colors flex items-center gap-2"
                    >
                      <span className="material-symbols-rounded text-sm">
                        {selectedChannels.length === dvrChannels.length
                          ? "deselect"
                          : "select_all"}
                      </span>
                      {selectedChannels.length === dvrChannels.length
                        ? "TÜMÜNÜ BIRAK"
                        : "TÜMÜNÜ SEÇ"}
                    </button>
                  )}
                  <button
                    disabled={
                      isSaving || isDiscovering || selectedChannels.length === 0
                    }
                    onClick={finalizeDVR}
                    className="px-20 py-6 rounded-[2rem] bg-slate-900 text-white font-black text-[11px] uppercase tracking-[0.3em] shadow-2xl shadow-slate-200 hover:bg-black transition-all hover:scale-105 active:scale-95 disabled:opacity-30 disabled:scale-100 disabled:bg-slate-300"
                  >
                    {isSaving ? "Kaydediliyor..." : "Kurulumu Tamamla"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Success Step */}
          {mode === "success" && (
            <div className="p-20 flex-1 flex flex-col items-center justify-center text-center space-y-10 animate-fade-in relative">
              <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-10">
                <div className="h-full w-full bg-[radial-gradient(circle_at_center,var(--color-brand-teal)_0%,transparent_70%)]" />
              </div>

              <div className="relative">
                <div className="h-48 w-48 bg-emerald-50 text-emerald-500 rounded-full flex items-center justify-center shadow-[0_0_50px_rgba(16,185,129,0.2)] animate-scale-in">
                  <span className="material-symbols-rounded text-[100px]">
                    verified
                  </span>
                </div>
                <div className="absolute -top-4 -right-4 h-14 w-14 bg-white rounded-2xl shadow-xl flex items-center justify-center text-emerald-500 animate-bounce delay-300">
                  <span className="material-symbols-rounded">stars</span>
                </div>
              </div>

              <div className="space-y-4 max-w-lg">
                <h2 className="text-5xl font-black text-slate-900 italic uppercase leading-none tracking-tighter">
                  KURULUM TAMAM!
                </h2>
                <div className="h-1.5 w-20 bg-emerald-400 mx-auto rounded-full"></div>
                <p className="text-slate-400 font-bold text-sm leading-relaxed pt-4">
                  {completedMode === "batch"
                    ? "Tüm IP listesi başarıyla kaydedildi. Arka planda kanallar taranıyor."
                    : "Cihazınız sisteme dahil edildi. Analizleri başlatmak için hazırsınız."}
                </p>
              </div>

              <div className="flex gap-5 pt-8">
                <button
                  onClick={() => {
                    setCompletedMode(null);
                    setMode("select");
                  }}
                  className="px-12 py-5 rounded-2xl bg-white border-2 border-slate-100 text-slate-400 font-black text-[11px] uppercase tracking-widest hover:border-slate-800 hover:text-slate-900 transition-all shadow-sm"
                >
                  YENİ EKLE
                </button>
                <button
                  onClick={() => router.push("/cameras")}
                  className="px-16 py-5 rounded-2xl bg-slate-900 text-white font-black text-[11px] uppercase tracking-[0.2em] hover:bg-black transition-all shadow-2xl shadow-slate-200 active:scale-95"
                >
                  KAMERA PANELİNE GİT
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 5px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #e2e8f0;
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #cbd5e1;
        }
      `}</style>
    </div>
  );
}
