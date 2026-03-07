"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";

// Mock data for initial state
const INITIAL_CAMERAS = [
  {
    camera_id: "CAM-01",
    camera_name: "Ana Giriş",
    ip_address: "161.9.13.92",
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

  const [editingCamera, setEditingCamera] = useState<any>(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [cameraToDelete, setCameraToDelete] = useState<any>(null);
  const [enabledAiCameras, setEnabledAiCameras] = useState<string[]>([]);
  const [failedCameras, setFailedCameras] = useState<string[]>([]);

  const [isPreviewModalOpen, setIsPreviewModalOpen] = useState(false);
  const [previewCamera, setPreviewCamera] = useState<any>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState<number>(0);

  const companyId = "COMP_EE37F274";

  useEffect(() => {
    setMounted(true);
    setRefreshKey(Date.now());
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

        // --- 🎯 AUTO-START AI DETECTION ---
        // Varsayılan olarak kapalı gelmesi istendiği için otomatik başlatma kaldırıldı.
        // Kullanıcı 'AI VIEW' butonuna bastığında ilgili kamera için başlatılacak.
      }
    } catch (error) {
      console.error("Error fetching cameras:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const openAddModal = () => {
    setEditingCamera(null);
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
    setStreamUrl(null);
    setIsModalOpen(true);
  };

  const toggleCameraAi = async (id: string, currentStatus: boolean) => {
    // UI'daki durumu anında güncelle (optimistic update)
    setEnabledAiCameras((prev) =>
      prev.includes(id) ? prev.filter((cid) => cid !== id) : [...prev, id],
    );

    // Backend'e haber ver (Yeni durum currentStatus'un tersi olacak)
    const newAiStatus = !currentStatus;
    const endpoint = newAiStatus ? "start-detection" : "stop-detection";

    try {
      await fetch(
        `http://127.0.0.1:5000/api/company/${companyId}/${endpoint}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: id }),
        },
      );
      // Görüntüleri tazelemek için refreshKey'i güncelle
      setRefreshKey(Date.now());
    } catch (error) {
      console.error(`Error toggling AI ${endpoint}:`, error);
    }
  };

  const isCameraAiEnabled = (item: any) => {
    return enabledAiCameras.includes(item.camera_id);
  };

  const startStream = (id: string) => {
    setStreamError(null);
    const camera = cameras.find((c) => c.camera_id === id);
    const isAi = camera && isCameraAiEnabled(camera);
    const streamUrl = isAi
      ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${id}?t=${Date.now()}`
      : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${id}/proxy-stream?t=${Date.now()}`;

    setStreamUrl(streamUrl);
  };

  const openPreviewModal = (camera: any) => {
    setPreviewCamera(camera);
    startStream(camera.camera_id);
    setIsPreviewModalOpen(true);
  };

  const openEditModal = (camera: any) => {
    setEditingCamera(camera);
    setFormData({
      camera_name: camera.camera_name || "",
      camera_location: camera.location || "",
      camera_ip: camera.ip_address || "",
      camera_port: camera.port || 80,
      camera_protocol: camera.protocol || "http",
      camera_path: camera.stream_path || "/video",
      camera_username: "",
      camera_password: "",
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = editingCamera
      ? `http://localhost:4000/company/${companyId}/cameras/${editingCamera.camera_id}`
      : `http://localhost:4000/company/${companyId}/cameras`;

    const method = editingCamera ? "PATCH" : "POST";
    const bodyData = editingCamera
      ? {
          camera_name: formData.camera_name,
          location: formData.camera_location,
          ip_address: formData.camera_ip,
          port: formData.camera_port,
          protocol: formData.camera_protocol,
          stream_path: formData.camera_path,
        }
      : formData;

    try {
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyData),
      });
      const data = await response.json();
      if (data.success) {
        setIsModalOpen(false);
        fetchCameras();
      }
    } catch (error) {
      console.error("Error submitting camera:", error);
    }
  };

  const handleDeleteCamera = (camera: any) => {
    setCameraToDelete(camera);
    setIsDeleteModalOpen(true);
  };

  const confirmDeleteCamera = async () => {
    if (!cameraToDelete) return;
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/cameras/${cameraToDelete.camera_id}`,
        {
          method: "DELETE",
        },
      );
      const data = await response.json();
      if (data.success) {
        setIsDeleteModalOpen(false);
        setCameraToDelete(null);
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
    <div className="space-y-8 animate-fade-in text-slate-900 pb-12" lang="tr">
      {/* Delete Confirmation Modal */}
      {isDeleteModalOpen &&
        mounted &&
        createPortal(
          <div
            className="fixed inset-0 z-[130] flex items-center justify-center p-4"
            lang="tr"
          >
            <div
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-md"
              onClick={() => setIsDeleteModalOpen(false)}
            ></div>
            <div className="relative w-full max-w-md overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl animate-scale-in flex flex-col p-8">
              <div className="text-center">
                <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-red-50 text-red-500">
                  <span className="material-symbols-rounded text-4xl">
                    delete
                  </span>
                </div>
                <h3 className="text-xl font-black text-slate-900 uppercase italic tracking-tight">
                  KAYDI SİLİYORUZ
                </h3>
                <p className="mt-4 text-sm font-semibold text-slate-500 leading-relaxed">
                  <span className="text-brand-teal font-black">
                    {cameraToDelete?.camera_name}
                  </span>{" "}
                  isimli kamerayı silmek istediğinize emin misiniz?
                </p>
              </div>
              <div className="flex gap-4 mt-8">
                <button
                  onClick={() => setIsDeleteModalOpen(false)}
                  className="flex-1 rounded-xl bg-slate-100 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest hover:bg-slate-200 transition-all cursor-pointer"
                >
                  VAZGEÇ
                </button>
                <button
                  onClick={confirmDeleteCamera}
                  className="flex-1 rounded-xl bg-red-500 py-4 text-[10px] font-black text-white uppercase tracking-widest hover:bg-red-600 transition-all cursor-pointer"
                >
                  EVET, SİL
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Add/Edit Modal */}
      {isModalOpen &&
        mounted &&
        createPortal(
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center p-4"
            lang="tr"
          >
            <div
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setIsModalOpen(false)}
            ></div>
            <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl animate-fade-in flex flex-col max-h-[90vh]">
              <div className="bg-brand-teal p-5 flex items-center justify-between text-white">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-rounded">settings</span>
                  <h3 className="text-sm font-black tracking-widest uppercase italic">
                    {editingCamera ? "KAMERA AYARLARI" : "YENİ KAMERA EKLE"}
                  </h3>
                </div>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 hover:bg-white/20 rounded-lg transition-colors"
                >
                  <span className="material-symbols-rounded">close</span>
                </button>
              </div>
              <div className="p-8 overflow-y-auto">
                <form onSubmit={handleSubmit} className="space-y-6">
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
                        placeholder: "Örn: A Blok",
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
                              [f.key]:
                                f.type === "number"
                                  ? parseInt(e.target.value) || 0
                                  : e.target.value,
                            })
                          }
                          className="w-full rounded-xl bg-white border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 focus:border-brand-teal/50 outline-none transition-all shadow-sm"
                          required
                        />
                      </div>
                    ))}
                  </div>
                  <div className="pt-6 border-t border-slate-100 flex gap-4">
                    <button
                      type="button"
                      className="flex-1 rounded-xl bg-slate-50 border-2 border-slate-100 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest hover:bg-slate-100"
                      onClick={() => setIsModalOpen(false)}
                    >
                      VAZGEÇ
                    </button>
                    <button
                      type="submit"
                      className="flex-1 rounded-xl bg-brand-teal py-4 text-[10px] font-black text-white uppercase tracking-widest hover:bg-brand-teal/90"
                    >
                      {editingCamera ? "GÜNCELLE" : "KAYDET"}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Preview Modal */}
      {isPreviewModalOpen &&
        mounted &&
        createPortal(
          <div
            className="fixed inset-0 z-[150] flex items-center justify-center p-0 md:p-12 animate-fade-in"
            lang="tr"
          >
            <div
              className="absolute inset-0 bg-slate-950/95 backdrop-blur-2xl"
              onClick={() => setIsPreviewModalOpen(false)}
            ></div>
            <div className="relative w-full h-full max-w-6xl max-h-[90vh] overflow-hidden rounded-none md:rounded-[3rem] border border-white/10 bg-black shadow-2xl flex flex-col">
              <div className="absolute top-8 left-8 right-8 z-10 flex items-center justify-between pointer-events-none">
                <div className="flex flex-col gap-1 pointer-events-auto">
                  <div className="flex items-center gap-3">
                    <div className="bg-red-500 px-3 py-1 rounded-full text-white flex items-center gap-2 shadow-xl">
                      <span className="h-2 w-2 rounded-full bg-white animate-pulse"></span>
                      <span className="text-[10px] font-black uppercase tracking-wider">
                        CANLI
                      </span>
                    </div>
                    <h3 className="text-2xl font-black text-white italic drop-shadow-lg uppercase tracking-tight">
                      {previewCamera?.camera_name}
                    </h3>
                  </div>
                </div>
                <div className="flex items-center gap-4 pointer-events-auto">
                  <div className="flex items-center gap-3 bg-white/10 backdrop-blur-md px-4 py-2 rounded-2xl border border-white/10">
                    <span className="text-[10px] font-black text-white/60 tracking-widest uppercase">
                      AI ANALİZ
                    </span>
                    <button
                      onClick={async () => {
                        const isAi = isCameraAiEnabled(previewCamera);
                        await toggleCameraAi(previewCamera.camera_id, isAi);

                        // Force refresh the specific stream with the corrected route
                        const nextAiEnabled = !isAi;
                        const streamUrl = nextAiEnabled
                          ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${previewCamera.camera_id}?t=${Date.now()}`
                          : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${previewCamera.camera_id}/proxy-stream?t=${Date.now()}`;

                        setStreamUrl(streamUrl);
                      }}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${isCameraAiEnabled(previewCamera) ? "bg-brand-teal" : "bg-white/20"}`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${isCameraAiEnabled(previewCamera) ? "translate-x-6" : "translate-x-1"}`}
                      />
                    </button>
                  </div>
                  <button
                    onClick={() => setIsPreviewModalOpen(false)}
                    className="p-4 rounded-2xl bg-white/10 text-white hover:bg-red-500 transition-all cursor-pointer"
                  >
                    <span className="material-symbols-rounded text-3xl">
                      close
                    </span>
                  </button>
                </div>
              </div>
              <div className="flex-1 flex items-center justify-center bg-black">
                {streamUrl ? (
                  <img
                    src={streamUrl}
                    alt="Canlı Yayın"
                    className="w-full h-full object-contain"
                    onError={() => setStreamUrl(null)}
                  />
                ) : (
                  <div className="text-white/20 text-center">
                    <span className="material-symbols-rounded text-[120px] animate-pulse">
                      videocam_off
                    </span>
                    <p className="mt-4 font-black tracking-widest uppercase italic">
                      SİNYAL YOK
                    </p>
                  </div>
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
            Kamera Panoraması
          </h2>
          <p className="text-slate-500 font-medium">
            Tesisinizdeki tüm sistemleri tek bir merkezden izleyin ve yönetin.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={openAddModal}
            className="flex items-center gap-2 rounded-xl bg-brand-teal px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-teal/20 hover:bg-brand-teal/90 transition-all cursor-pointer"
          >
            <span className="material-symbols-rounded">add</span> YENİ KAMERA
            EKLE
          </button>
        </div>
      </section>

      <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {filteredCameras.map((camera) => (
          <div
            key={camera.camera_id}
            className="group relative flex flex-col overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-lg hover:shadow-2xl transition-all duration-500"
          >
            <div className="relative aspect-video bg-slate-900 overflow-hidden group-hover:ring-4 ring-brand-teal/10 transition-all duration-500">
              <img
                src={
                  isCameraAiEnabled(camera)
                    ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${camera.camera_id}?t=${refreshKey}`
                    : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${camera.camera_id}/proxy-stream?t=${refreshKey}`
                }
                alt={camera.camera_name}
                className="w-full h-full object-contain bg-slate-950 transition-transform duration-700 group-hover:scale-105"
                onError={(e) => {
                  setFailedCameras((prev) => [
                    ...new Set([...prev, camera.camera_id]),
                  ]);
                  (e.target as HTMLImageElement).src =
                    "https://images.unsplash.com/photo-1557683316-973673baf926?q=80&w=1000&auto=format&fit=crop";
                  (e.target as HTMLImageElement).className =
                    "w-full h-full object-cover opacity-10 grayscale";
                }}
                onLoad={() => {
                  setFailedCameras((prev) =>
                    prev.filter((id) => id !== camera.camera_id),
                  );
                }}
              />

              {failedCameras.includes(camera.camera_id) && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/40 backdrop-blur-sm">
                  <span className="material-symbols-rounded text-white/40 text-5xl mb-2 animate-pulse">
                    videocam_off
                  </span>
                  <p className="text-[10px] font-black text-white px-4 py-2 bg-red-500/80 rounded-xl uppercase tracking-widest shadow-2xl">
                    KAMERA BULUNAMADI
                  </p>
                </div>
              )}

              <div className="absolute top-4 left-4 flex gap-2">
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-white shadow-lg transition-colors duration-500 ${failedCameras.includes(camera.camera_id) ? "bg-slate-700" : "bg-red-500"}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full bg-white ${failedCameras.includes(camera.camera_id) ? "" : "animate-pulse"}`}
                  ></span>
                  <span className="text-[8px] font-black uppercase tracking-tighter text-white">
                    {failedCameras.includes(camera.camera_id)
                      ? "BAĞLANTI YOK"
                      : "CANLI"}
                  </span>
                </div>
                {isCameraAiEnabled(camera) && (
                  <div className="bg-brand-teal px-2.5 py-1 rounded-lg text-white shadow-lg animate-pulse">
                    <span className="text-[8px] font-black uppercase tracking-tighter italic">
                      AI ANALİZ AKTİF
                    </span>
                  </div>
                )}
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleCameraAi(camera.camera_id, isCameraAiEnabled(camera));
                }}
                className={`absolute top-4 right-4 z-20 flex items-center gap-2 px-3 py-1.5 rounded-xl backdrop-blur-md border transition-all duration-500 translate-x-4 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 shadow-xl cursor-pointer ${isCameraAiEnabled(camera) ? "bg-emerald-500/90 border-emerald-400 text-white" : "bg-slate-900/60 border-white/10 text-white/50"}`}
              >
                <span className="material-symbols-rounded text-sm">
                  {isCameraAiEnabled(camera) ? "visibility" : "visibility_off"}
                </span>
                <span className="text-[9px] font-black uppercase tracking-widest">
                  AI VIEW
                </span>
              </button>

              <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-300">
                <div className="bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-slate-200 shadow-xl">
                  <p className="text-[8px] font-black text-slate-400 uppercase mb-0.5">
                    IP ADDRESS
                  </p>
                  <p className="text-[10px] font-bold text-slate-900">
                    {camera.ip_address}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => openPreviewModal(camera)}
                    className="p-2.5 rounded-xl bg-brand-teal text-white shadow-xl cursor-pointer"
                  >
                    <span className="material-symbols-rounded text-lg">
                      fullscreen
                    </span>
                  </button>
                  <button
                    onClick={() => openEditModal(camera)}
                    className="p-2.5 rounded-xl bg-white text-slate-600 border border-slate-200 cursor-pointer"
                  >
                    <span className="material-symbols-rounded text-lg">
                      edit
                    </span>
                  </button>
                  <button
                    onClick={() => handleDeleteCamera(camera)}
                    className="p-2.5 rounded-xl bg-white text-red-500 border border-slate-200 cursor-pointer"
                  >
                    <span className="material-symbols-rounded text-lg">
                      delete
                    </span>
                  </button>
                </div>
              </div>
            </div>
            <div className="p-6">
              <h3 className="text-lg font-black text-slate-900 uppercase italic tracking-tight group-hover:text-brand-teal transition-colors">
                {camera.camera_name}
              </h3>
              <div className="flex items-center gap-1.5 mt-1 text-slate-400">
                <span className="material-symbols-rounded text-xs">
                  location_on
                </span>
                <span className="text-[10px] font-black uppercase italic tracking-widest">
                  {camera.location}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between py-8 border-t border-slate-200 text-[10px] font-black text-slate-400 uppercase tracking-widest mt-12">
        <p>SmartSafe AI v2.5 • Enterprise VMS</p>
        <div className="flex gap-2">
          <span className="text-brand-teal bg-white border px-3 py-1 rounded-lg">
            STATUS: SECURE
          </span>
        </div>
      </div>
    </div>
  );
}
