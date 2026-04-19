"use client";

import { Suspense, useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { abortAllStreams } from "@/lib/streamRegistry";
import { useConfirm } from "@/context/ConfirmContext";
import { 
  Router, 
  EyeOff, 
  Eye, 
  Plus, 
  Trash2, 
  Settings, 
  X, 
  Pencil, 
  MapPin, 
  Check, 
  History, 
  Calendar,
  MoreVertical,
  ChevronDown,
  Monitor,
  Activity,
  AlertTriangle,
  LayoutGrid,
  List as ListIcon,
  Search,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  Database,
  VideoOff,
  Camera
} from "lucide-react";
import { getCompanyId } from "@/lib/session";
import api from "@/lib/api";
import core from "@/lib/core";
import VideoRoiOverlay from "@/components/camera/VideoRoiOverlay";
import MjpegCanvas from "@/components/camera/MjpegCanvas";
import {
  normalizeDetectionZonesPayload,
  polygonToVideoSpaceForOverlay,
} from "@/lib/detectionZones";
import ScheduleModal from "@/components/camera/ScheduleModal";

export default function CamerasPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-slate-400 text-sm">
          Yükleniyor...
        </div>
      }
    >
      <CamerasContent />
    </Suspense>
  );
}

function CamerasContent() {
  const [cameras, setCameras] = useState<any[]>([]);
  const [managementCameras, setManagementCameras] = useState<any[]>([]);
  const [isManagementLoading, setIsManagementLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("smart");
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const { confirm } = useConfirm();

  const handleNavigate = (path: string) => {
    if (path === pathname) return;
    window.dispatchEvent(new Event("navigation:start"));
    abortAllStreams();
    router.push(path);
  };

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
  const [failedCameraDiagnostics, setFailedCameraDiagnostics] = useState<
    Record<string, string>
  >({});
  const [loadedCameras, setLoadedCameras] = useState<string[]>([]);
  const [streamLayoutByCamera, setStreamLayoutByCamera] = useState<
    Record<string, { nw: number; nh: number; cw: number; ch: number }>
  >({});
  const [privacyModeCameras, setPrivacyModeCameras] = useState<string[]>([]);

  const [refreshKey, setRefreshKey] = useState<number>(0);
  // Kamera başına stream key — sadece AI toggle'da güncellenir (stream yeniden bağlanır)
  const [streamKeys, setStreamKeys] = useState<Record<string, number>>({});
  const [isManageDvrsOpen, setIsManageDvrsOpen] = useState(false);
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);
  const [editingCameraName, setEditingCameraName] = useState<string>("");
  const [editingDvrId, setEditingDvrId] = useState<string | null>(null);
  const [editingDvrName, setEditingDvrName] = useState<string>("");
  const [dvrs, setDvrs] = useState<any[]>([]);
  const [expandedDvrIds, setExpandedDvrIds] = useState<string[]>([]);
  const [isDeletingDvr, setIsDeletingDvr] = useState(false);
  const [isDiscoveringDvr, setIsDiscoveringDvr] = useState<string | null>(null);

  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [selectedCameraForSchedule, setSelectedCameraForSchedule] =
    useState<any>(null);

  const prevFiltersRef = useRef<{ search: string } | null>(null);
  const searchParams = useSearchParams();
  const camerasPerPage = parseInt(searchParams.get("limit") || "6", 10);
  const currentPage = Math.max(
    0,
    parseInt(searchParams.get("page") || "1", 10) - 1,
  );

  const setLimit = (limit: number) => {
    const url = new URL(window.location.href);
    url.searchParams.set("limit", String(limit));
    url.searchParams.set("page", "1");
    handleNavigate(url.pathname + url.search);
  };

  const setCurrentPage = useCallback(
    (pageOrFn: number | ((prev: number) => number)) => {
      const next =
        typeof pageOrFn === "function" ? pageOrFn(currentPage) : pageOrFn;
      const url = new URL(window.location.href);
      url.searchParams.set("page", String(next + 1));
      handleNavigate(url.pathname + url.search);
    },
    [currentPage, router, pathname],
  );

  const companyId = getCompanyId();

  useEffect(() => {
    setMounted(true);
    // refreshKey artık stream URL'ine girmiyor, sadece iç yenileme için
    setRefreshKey(Date.now());
    fetchCameras("active");
    fetchDvrs();
    const savedPrivacy = localStorage.getItem("privacyModeCameras");
    if (savedPrivacy) setPrivacyModeCameras(JSON.parse(savedPrivacy));

    // Cleanup on unmount to release browser connections
    return () => {
      setCameras([]);
      setLoadedCameras([]);
    };
  }, []);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        // Sadece veri yenile, stream URL'ini değiştirme (titreme önleme)
        fetchCameras("active");
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    if (!companyId) return;

    const interval = setInterval(() => {
      syncAiStates(companyId, cameras);
    }, 20000);

    return () => clearInterval(interval);
  }, [companyId, cameras]);

  const fetchCameras = async (status?: string) => {
    const cid = getCompanyId();
    if (!cid) return;
    setLoadedCameras([]);
    setIsLoading(true);
    try {
      // @ts-ignore
      const data = await api.camera.list(cid, status ? { status } : undefined);
      if (data.success) {
        setCameras(data.cameras);
        if (!status || status === "active") {
          syncAiStates(cid, data.cameras);
        }
      }
    } catch (error: any) {
      console.error("Error fetching cameras:", error.message || error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchManagementCameras = async () => {
    const cid = getCompanyId();
    if (!cid) return;
    setIsManagementLoading(true);
    try {
      // @ts-ignore
      const data = await api.camera.list(cid);
      if (data.success) {
        setManagementCameras(data.cameras);
      }
    } catch (error: any) {
      console.error(
        "Error fetching management cameras:",
        error.message || error,
      );
    } finally {
      setIsManagementLoading(false);
    }
  };

  const syncAiStates = async (cid: string, _cams: any[]) => {
    try {
      const data = await core.getActiveDetections(cid);
      if (
        data.success &&
        data.active_camera_ids &&
        data.active_camera_ids.length > 0
      ) {
        setEnabledAiCameras(data.active_camera_ids);
      }
    } catch {
    }
  };

  const toggleAllPrivacy = () => {
    const next =
      privacyModeCameras.length === cameras.length
        ? []
        : cameras.map((c) => c.camera_id);
    setPrivacyModeCameras(next);
    localStorage.setItem("privacyModeCameras", JSON.stringify(next));
  };

  const toggleCameraPrivacy = (id: string) => {
    const next = privacyModeCameras.includes(id)
      ? privacyModeCameras.filter((cid) => cid !== id)
      : [...privacyModeCameras, id];
    setPrivacyModeCameras(next);
    localStorage.setItem("privacyModeCameras", JSON.stringify(next));
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
    setIsModalOpen(true);
  };

  const toggleCameraAi = async (id: string, currentStatus: boolean) => {
    setEnabledAiCameras((prev) =>
      prev.includes(id) ? prev.filter((cid) => cid !== id) : [...prev, id],
    );

    const newAiStatus = !currentStatus;

    try {
      if (newAiStatus) {
        await core.startDetection(companyId, id);
      } else {
        await core.stopDetection(companyId, id);
      }
      // Sadece bu kameranın stream key'ini güncelle → sadece o yeniden bağlanır
      setStreamKeys((prev) => ({ ...prev, [id]: Date.now() }));
    } catch (error) {
      console.error(`Error toggling AI:`, error);
    }
  };

  const isCameraAiEnabled = (item: any) => {
    return enabledAiCameras.includes(item.camera_id);
  };

  const fetchStreamDiagnostics = async (
    cameraId: string,
  ): Promise<string | null> => {
    if (!companyId) return null;
    try {
      const body = await core.getStreamDiagnostics(companyId, cameraId);
      const st = body && body.status ? body.status : {};
      const state = st.status || "unknown";
      const code =
        st.last_error_code || (body?.error?.code as string) || "UNKNOWN";
      const reason =
        st.status_reason || (body?.error?.message as string) || "unknown";
      return `State=${state} | Code=${code} | Reason=${reason}`;
    } catch {
      return null;
    }
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

  const fetchDvrs = async () => {
    if (!companyId) return;
    try {
      const data = await api.dvr.list(companyId);
      if (data.success) {
        setDvrs(data.systems || []);
      }
    } catch (error) {
      console.error("Error fetching DVRs:", error);
    }
  };

  const discoverChannels = async (dvrId: string) => {
    setIsDiscoveringDvr(dvrId);
    try {
      const data = await core.discoverDVRChannels(companyId, dvrId);
      if (data.success) {
        const inactive = data.inactive_count || 0;
        const msg =
          inactive > 0
            ? `${data.count} aktif kanal bulundu (${inactive} kanalda kamera bağlı değil).`
            : `${data.count} kanal başarıyla keşfedildi!`;
        await confirm({
          title: "KEŞİF TAMAMLANDI",
          message: msg,
          confirmText: "TAMAM",
          type: "info"
        });
        fetchCameras("active");
      } else {
        await confirm({
          title: "KÖK NEDEN HATASI",
          message: data.error || "Kanallar keşfedilemedi.",
          confirmText: "TAMAM",
          type: "danger"
        });
      }
    } catch (error) {
      console.error("Error discovering channels:", error);
      await confirm({
        title: "BAĞLANTI HATASI",
        message: "Sunucuyla bağlantı kurulamadı.",
        confirmText: "TAMAM",
        type: "danger"
      });
    } finally {
      setIsDiscoveringDvr(null);
    }
  };

  const deleteDvr = async (dvrId: string) => {
    const ok = await confirm({
      title: "CİHAZI KALDIR",
      message: "Bu DVR’yi listeden kaldırmak istiyor musunuz? Geçmiş ihlal ve raporlar korunur.",
      confirmText: "CİHAZI SİL",
      cancelText: "VAZGEÇ",
      type: "danger"
    });

    if (!ok) return;
    setIsDeletingDvr(true);
    try {
      const data = await api.dvr.remove(companyId, dvrId);
      if (data.success) {
        await confirm({
          title: "BAŞARILI",
          message: data.message || "Cihaz listeden kaldırıldı. Geçmiş kayıtlar korunur.",
          confirmText: "TAMAM",
          type: "info"
        });
        fetchDvrs();
        fetchCameras("active");
      } else {
        await confirm({
          title: "HATA",
          message: data.error || "DVR silinemedi.",
          confirmText: "TAMAM",
          type: "danger"
        });
      }
    } catch (error) {
      console.error("Error deleting DVR:", error);
      await confirm({
        title: "SİSTEM HATASI",
        message: "Sunucuyla bağlantı kurulamadı.",
        confirmText: "TAMAM",
        type: "danger"
      });
    } finally {
      setIsDeletingDvr(false);
    }
  };

  const toggleDvrExpand = (dvrId: string) => {
    setExpandedDvrIds((prev) =>
      prev.includes(dvrId)
        ? prev.filter((id) => id !== dvrId)
        : [...prev, dvrId],
    );
  };

  const handleInlineCameraSave = async (cameraId: string) => {
    if (!companyId || !editingCameraName.trim()) return;
    try {
      const data = await api.camera.update(companyId, cameraId, {
        camera_name: editingCameraName,
      });
      if (data.success) {
        setEditingCameraId(null);
        if (isManageDvrsOpen) {
          fetchManagementCameras();
        } else {
          fetchCameras("active");
        }
      } else {
        alert("Güncellenemedi: " + (data.error || "Bilinmeyen hata"));
      }
    } catch (error) {
      console.error("Error updating camera inline:", error);
    }
  };

  const handleInlineDvrSave = async (dvrId: string) => {
    if (!companyId || !editingDvrName.trim()) return;
    try {
      // @ts-ignore
      const data = await api.dvr.update(companyId, dvrId, {
        name: editingDvrName,
      });
      if (data.success) {
        setEditingDvrId(null);
        fetchDvrs();
      } else {
        await confirm({
          title: "GÜNCELLEME HATASI",
          message: data.error || "Bilinmeyen bir sorun oluştu.",
          confirmText: "TAMAM",
          type: "danger"
        });
      }
    } catch (error) {
      console.error("Error updating DVR inline:", error);
      await confirm({
        title: "BAĞLANTI HATASI",
        message: "Sunucu hatası oluştu.",
        confirmText: "TAMAM",
        type: "danger"
      });
    }
  };

  const toggleCameraStatus = async (camera: any) => {
    const cid = getCompanyId();
    if (!cid) return;
    const newStatus = camera.status === "active" ? "inactive" : "active";
    try {
      const data = await api.camera.update(cid, camera.camera_id, {
        status: newStatus,
      });
      if (data.success) {
        fetchCameras("active");
        if (isManageDvrsOpen) {
          fetchManagementCameras();
        }
      } else {
        alert("Durum güncellenemedi: " + (data.error || "Bilinmeyen hata"));
      }
    } catch (error) {
      console.error("Error updating camera status:", error);
    }
  };

  useEffect(() => {
    if (isManageDvrsOpen) {
      fetchDvrs();
      fetchManagementCameras();
    } else {
      fetchCameras("active");
    }
  }, [isManageDvrsOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
      const data = editingCamera
        ? await api.camera.update(
            companyId,
            editingCamera.camera_id,
            bodyData as any,
          )
        : await api.camera.create(companyId, bodyData as any);

      if (data.success) {
        setIsModalOpen(false);
        fetchCameras("active");
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
      const data = await api.camera.remove(companyId, cameraToDelete.camera_id);
      if (data.success) {
        setIsDeleteModalOpen(false);
        setCameraToDelete(null);
        fetchCameras("active");
      }
    } catch (error) {
      console.error("Error deleting camera:", error);
    }
  };

  const filteredCameras = cameras.filter((cam) => {
    const matchesSearch =
      cam.camera_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cam.ip_address?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  });

  const totalPages = Math.ceil(filteredCameras.length / camerasPerPage);
  const paginatedCameras = filteredCameras.slice(
    currentPage * camerasPerPage,
    (currentPage + 1) * camerasPerPage,
  );

  useEffect(() => {
    if (prevFiltersRef.current === null) {
      prevFiltersRef.current = { search: searchTerm };
      return;
    }
    const prev = prevFiltersRef.current;
    if (prev.search === searchTerm) {
      return;
    }
    prevFiltersRef.current = { search: searchTerm };
    const url = new URL(window.location.href);
    url.searchParams.delete("page");
    router.replace(url.pathname + url.search, { scroll: false });
  }, [searchTerm, router]);

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
                  <Trash2 className="w-10 h-10" />
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
                  <Settings className="w-5 h-5" />
                  <h3 className="text-sm font-black tracking-widest uppercase italic">
                    {editingCamera ? "KAMERA AYARLARI" : "YENİ KAMERA EKLE"}
                  </h3>
                </div>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 hover:bg-white/20 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
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
            onClick={() => setIsManageDvrsOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-white border border-slate-200 px-6 py-3.5 text-xs font-black text-slate-600 shadow-sm hover:bg-slate-50 transition-all cursor-pointer"
          >
            <Settings className="w-4 h-4" /> KAMERA YÖNETİMİ
          </button>
          <button
            onClick={toggleAllPrivacy}
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3.5 text-xs font-black text-slate-600 shadow-sm transition-all hover:bg-slate-50 cursor-pointer"
          >
            {privacyModeCameras.length === cameras.length ? (
              <EyeOff className="w-4 h-4" />
            ) : (
              <Eye className="w-4 h-4" />
            )}
            GİZLİLİK MODU
          </button>
          <button
            onClick={() => handleNavigate("/cameras/setup")}
            className="flex items-center gap-2 rounded-xl bg-brand-teal px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-teal/20 hover:bg-brand-teal/90 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" /> YENİ KAMERA EKLE
          </button>
        </div>
      </section>

      {filteredCameras.length === 0 && !isLoading ? (
        <div className="mt-12 flex flex-col items-center justify-center p-24 bg-white/40 rounded-[3rem] border-2 border-dashed border-slate-100 animate-fade-in min-h-[450px]">
          <div className="w-24 h-24 bg-slate-50/50 rounded-full flex items-center justify-center mb-8 border border-slate-100">
            <VideoOff className="w-10 h-10 text-slate-300" />
          </div>
          <h3 className="text-2xl font-bold text-slate-500 tracking-tight text-center">
            Henüz kayıtlı bir kamera bulunmuyor.
          </h3>
          <p className="text-[10px] text-slate-400 font-bold uppercase tracking-[0.25em] mt-3 text-center opacity-80">
            SİSTEM AKTİF - KAMERA TANIMLANMASI BEKLENİYOR
          </p>
        </div>
      ) : (
        <>
          <div
            className={`mt-12 grid gap-8 ${camerasPerPage === 1 ? "grid-cols-1 max-w-5xl mx-auto" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"}`}
          >
            {paginatedCameras.map((camera) => {
              const zonesPayload = normalizeDetectionZonesPayload(
                camera.detection_zones,
              );
              const streamLay = streamLayoutByCamera[camera.camera_id];
              const showRoiOverlay =
                zonesPayload.polygons.length > 0 &&
                zonesPayload.polygons[0].length > 0 &&
                !failedCameras.includes(camera.camera_id);

              return (
                <div
                  key={camera.camera_id}
                  className="group relative flex flex-col overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-lg hover:shadow-2xl transition-all duration-500"
                >
                  <div className="relative aspect-video bg-slate-900 overflow-hidden group-hover:ring-4 ring-brand-teal/10 transition-all duration-500">
                    <MjpegCanvas
                      src={
                         isCameraAiEnabled(camera)
                          ? `${core.getBaseUrl()}/api/company/${companyId}/video-feed/${camera.camera_id}${streamKeys[camera.camera_id] ? `?t=${streamKeys[camera.camera_id]}` : ''}`
                          : `${core.getBaseUrl()}/api/company/${companyId}/cameras/${camera.camera_id}/proxy-stream${streamKeys[camera.camera_id] ? `?t=${streamKeys[camera.camera_id]}` : ''}`
                      }
                      className={`w-full h-full transition-all duration-700 group-hover:scale-105 ${
                        failedCameras.includes(camera.camera_id)
                          ? "opacity-0"
                          : "opacity-100"
                      }`}
                      fps={30}
                      onDimensions={(nw, nh, cw, ch) => {
                        setStreamLayoutByCamera((prev) => ({
                          ...prev,
                          [camera.camera_id]: { nw, nh, cw, ch },
                        }));
                        setLoadedCameras((prev) => [
                          ...new Set([...prev, camera.camera_id]),
                        ]);
                        setFailedCameras((prev) =>
                          prev.filter((id) => id !== camera.camera_id),
                        );
                      }}
                      onError={() => {
                        setFailedCameras((prev) => [
                          ...new Set([...prev, camera.camera_id]),
                        ]);
                        fetchStreamDiagnostics(camera.camera_id).then(
                          (diag) => {
                            if (!diag) return;
                            setFailedCameraDiagnostics((prev) => ({
                              ...prev,
                              [camera.camera_id]: diag,
                            }));
                          },
                        );
                      }}
                    />

                    {showRoiOverlay && (
                      <VideoRoiOverlay
                        polygon={polygonToVideoSpaceForOverlay(
                          zonesPayload.polygons[0],
                          zonesPayload.coordSpace,
                          streamLay?.cw ?? 0,
                          streamLay?.ch ?? 0,
                          streamLay?.nw ?? 0,
                          streamLay?.nh ?? 0,
                        )}
                        naturalW={streamLay?.nw ?? 0}
                        naturalH={streamLay?.nh ?? 0}
                        className="absolute inset-0 z-10 h-full w-full opacity-70 transition-opacity duration-500 group-hover:opacity-100"
                      />
                    )}

                    {privacyModeCameras.includes(camera.camera_id) && (
                      <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/75 backdrop-blur-[1px] transition-all duration-500">
                        <div className="p-4 rounded-full border border-white/10 bg-black/40 shadow-2xl animate-pulse">
                          <EyeOff className="w-6 h-6 text-white/20" />
                        </div>
                      </div>
                    )}

                    {failedCameras.includes(camera.camera_id) && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/40 backdrop-blur-sm">
                        <VideoOff className="w-12 h-12 text-white/40 mb-2 animate-pulse" />
                        <p className="text-[10px] font-black text-white px-4 py-2 bg-red-500/80 rounded-xl uppercase tracking-widest shadow-2xl">
                          KAMERA BULUNAMADI
                        </p>
                        {failedCameraDiagnostics[camera.camera_id] && (
                          <p className="mt-2 text-[10px] font-mono text-white/70 px-3 text-center max-w-[90%]">
                            {failedCameraDiagnostics[camera.camera_id]}
                          </p>
                        )}
                      </div>
                    )}

                    <div className="absolute top-4 left-4 flex gap-2">
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleCameraAi(
                          camera.camera_id,
                          isCameraAiEnabled(camera),
                        );
                      }}
                      className={`absolute top-4 right-4 z-50 flex items-center gap-2 px-3 py-1.5 rounded-xl backdrop-blur-md border transition-all duration-500 shadow-xl cursor-pointer ${isCameraAiEnabled(camera) ? "bg-white/90 border-brand-teal text-brand-teal" : "bg-slate-900/40 border-white/10 text-white/50"}`}
                    >
                        {isCameraAiEnabled(camera) ? <Activity className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      <span className="text-[9px] font-black uppercase tracking-widest">
                        AI VIEW
                      </span>
                    </button>

                    <div className="absolute bottom-4 left-4 right-4 z-50 flex items-end justify-between transition-all duration-300">
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
                          type="button"
                          onClick={() =>
                            handleNavigate(
                              `/camera/${encodeURIComponent(camera.camera_id)}`,
                            )
                          }
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white text-brand-teal border border-slate-200 shadow-sm cursor-pointer transition-all hover:bg-brand-teal hover:text-white active:scale-95"
                          title="Tam Ekran"
                        >
                          <Maximize2 className="w-5 h-5" />
                        </button>
                        <button
                          onClick={() => toggleCameraPrivacy(camera.camera_id)}
                          className={`w-10 h-10 flex items-center justify-center rounded-xl bg-white border border-slate-200 transition-all duration-300 shadow-sm hover:shadow-lg cursor-pointer active:scale-95 ${privacyModeCameras.includes(camera.camera_id) ? "text-slate-900 border-slate-900" : "text-slate-500 hover:bg-slate-50"}`}
                          title="Gizlilik Modu"
                        >
                           {privacyModeCameras.includes(camera.camera_id) ? (
                            <EyeOff className="w-5 h-5" />
                          ) : (
                            <Eye className="w-5 h-5" />
                          )}
                        </button>
                        <button
                          onClick={() => openEditModal(camera)}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white text-slate-600 border border-slate-200 cursor-pointer hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-all duration-300 shadow-sm hover:shadow-lg hover:shadow-slate-900/20 active:scale-95"
                          title="Düzenle"
                        >
                          <Pencil className="w-5 h-5" />
                        </button>
                        <button
                          onClick={() => {
                            setSelectedCameraForSchedule(camera);
                            setIsScheduleModalOpen(true);
                          }}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white text-brand-teal border border-slate-200 cursor-pointer hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-all duration-300 shadow-sm hover:shadow-lg hover:shadow-brand-teal/20 active:scale-95"
                          title="Çalışma Saatleri"
                        >
                          <History className="w-5 h-5" />
                        </button>
                        <button
                          onClick={() => handleDeleteCamera(camera)}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white text-red-500 border border-slate-200 cursor-pointer hover:bg-red-500 hover:text-white hover:border-red-500 transition-all duration-300 shadow-sm hover:shadow-lg hover:shadow-red-500/20 active:scale-95"
                          title="Sil"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="p-6">
                    <h3 className="text-lg font-black text-slate-900 tracking-tight group-hover:text-brand-teal transition-colors">
                      {camera.camera_name}
                    </h3>
                    <div className="flex items-center gap-1.5 mt-1 text-slate-400">
                        <MapPin className="w-3 h-3" />
                      <span className="text-[10px] font-black tracking-widest">
                        {camera.location}
                      </span>
                    </div>


                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-12 flex items-center justify-center gap-3">
            {totalPages > 1 && (
              <>
                <button
                  onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
                  disabled={currentPage === 0}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-slate-600 hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-all disabled:opacity-30 disabled:pointer-events-none shadow-sm"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Önceki
                </button>

                <div className="flex items-center gap-1">
                  {Array.from({ length: totalPages }, (_, i) => (
                    <button
                      key={i}
                      onClick={() => setCurrentPage(i)}
                      className={`w-9 h-9 rounded-xl text-xs font-black transition-all ${
                        i === currentPage
                          ? "bg-brand-teal text-white shadow-lg shadow-brand-teal/30"
                          : "bg-white border border-slate-200 text-slate-500 hover:bg-slate-50"
                      }`}
                    >
                      {i + 1}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() =>
                    setCurrentPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={currentPage === totalPages - 1}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-slate-600 hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-all disabled:opacity-30 disabled:pointer-events-none shadow-sm"
                >
                  Sonraki
                  <ChevronRight className="w-4 h-4" />
                </button>
              </>
            )}

            <div className="flex items-center gap-1.5 p-1.5 bg-slate-50 border border-slate-200 rounded-2xl ml-4 shadow-inner">
              <button
                onClick={() => setLimit(1)}
                className={`flex items-center gap-2 px-3 h-9 rounded-xl transition-all ${camerasPerPage === 1 ? "bg-slate-900 text-white shadow-lg" : "text-slate-400 hover:bg-white"}`}
              >
                  <Monitor className="w-4 h-4" />
                <span className="text-[10px] font-black uppercase tracking-widest leading-none">
                  1
                </span>
              </button>
              <button
                onClick={() => setLimit(6)}
                className={`flex items-center gap-2 px-3 h-9 rounded-xl transition-all ${camerasPerPage === 6 ? "bg-slate-900 text-white shadow-lg" : "text-slate-400 hover:bg-white"}`}
              >
                  <LayoutGrid className="w-4 h-4" />
                <span className="text-[10px] font-black uppercase tracking-widest leading-none">
                  6
                </span>
              </button>
            </div>

            <span className="ml-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.1em]">
              {filteredCameras.length} KAMERA • SAYFA {currentPage + 1}/
              {totalPages || 1}
            </span>
          </div>
        </>
      )}



      {/* DVR Management Modal */}
      {isManageDvrsOpen &&
        mounted &&
        createPortal(
          <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-md"
              onClick={() => setIsManageDvrsOpen(false)}
            ></div>
            <div className="relative w-full max-w-2xl bg-white rounded-3xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
              <div className="bg-slate-900 p-6 flex items-center justify-between text-white">
                <div className="flex items-center gap-3">
                  <Settings className="w-5 h-5" />
                  <h3 className="font-black tracking-widest uppercase italic text-sm">
                    KAMERA VE SİSTEM YÖNETİMİ
                  </h3>
                </div>
                <button
                  onClick={() => setIsManageDvrsOpen(false)}
                  className="p-2 hover:bg-white/10 rounded-xl"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-8 overflow-y-auto">
                <div className="flex items-center justify-between mb-8">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                    YÖNETİLEBİLİR CİHAZ VE KAMERALAR
                  </p>
                  <button
                    onClick={() => handleNavigate("/cameras/setup")}
                    className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-brand-teal text-white text-[10px] font-black uppercase tracking-widest hover:bg-brand-teal/90 transition-all cursor-pointer shadow-sm hover:shadow-lg hover:shadow-brand-teal/20 active:scale-95"
                  >
                    <Plus className="w-4 h-4" /> YENİ EKLE
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-6">
                  {/* Standalone IP Cameras Section */}
                  {managementCameras.filter(c => !c.dvr_id).length > 0 && (
                    <div className="space-y-3">
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-2">
                        BAĞIMSIZ IP KAMERALAR
                      </p>
                      <div className="grid grid-cols-1 gap-2">
                        {managementCameras.filter(c => !c.dvr_id).map((camera) => (
                          <div
                            key={camera.camera_id}
                            className="flex items-center justify-between p-4 bg-slate-50 border border-slate-200/50 rounded-2xl hover:bg-slate-100 transition-all"
                          >
                            <div className="flex items-center gap-4 flex-1 overflow-hidden">
                              <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400">
                                <Camera className="w-6 h-6" />
                              </div>
                              <div className="flex-1 overflow-hidden">
                                {editingCameraId === camera.camera_id ? (
                                  <div className="flex items-center gap-2">
                                    <input
                                      autoFocus
                                      type="text"
                                      value={editingCameraName}
                                      onChange={(e) => setEditingCameraName(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") handleInlineCameraSave(camera.camera_id);
                                        if (e.key === "Escape") setEditingCameraId(null);
                                      }}
                                      className="h-8 bg-white border border-brand-teal rounded-lg px-2 text-[10px] font-black text-slate-900 w-full outline-none"
                                    />
                                    <button onClick={() => handleInlineCameraSave(camera.camera_id)} className="text-brand-teal p-1"><Check className="w-4 h-4" /></button>
                                    <button onClick={() => setEditingCameraId(null)} className="text-slate-400 p-1"><X className="w-4 h-4" /></button>
                                  </div>
                                ) : (
                                  <>
                                    <h4 className="font-black text-slate-900 text-[10px] truncate">{camera.camera_name}</h4>
                                    <p className="text-[8px] font-bold text-slate-400 tracking-tight uppercase">
                                      {camera.ip_address} • {camera.protocol?.toUpperCase()} • {camera.status === 'active' ? 'AKTİF' : 'PASİF'}
                                    </p>
                                  </>
                                )}
                              </div>
                            </div>
                            <div className="flex items-center gap-2 ml-4">
                              <button
                                onClick={() => toggleCameraStatus(camera)}
                                className={`w-9 h-9 flex items-center justify-center rounded-xl border border-transparent transition-all cursor-pointer ${camera.status === "active" ? "text-slate-400 hover:text-red-500 hover:bg-red-50 hover:border-red-100" : "text-brand-teal hover:bg-brand-teal/10 hover:border-brand-teal/20"}`}
                                title={camera.status === "active" ? "Kamerayı Gizle" : "Kamerayı Göster"}
                              >
                                {camera.status === "active" ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                              </button>
                              <button
                                onClick={() => {
                                  setEditingCameraId(camera.camera_id);
                                  setEditingCameraName(camera.camera_name || "");
                                }}
                                className="w-9 h-9 flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-200 rounded-xl transition-all cursor-pointer"
                                title="İsim Düzenle"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleDeleteCamera(camera)}
                                className="w-9 h-9 flex items-center justify-center text-red-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition-all cursor-pointer"
                                title="Tamamen Sil"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* DVR Systems Section */}
                  <div className="space-y-3">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-2">
                       DVR / NVR SİSTEMLERİ
                    </p>
                    {dvrs.length === 0 ? (
                      <div className="py-12 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                        <p className="text-[10px] font-black text-slate-400 uppercase text-center w-full">
                          Henüz DVR sistemi eklenmedi
                        </p>
                      </div>
                    ) : (
                    dvrs.map((dvr) => (
                      <div key={dvr.dvr_id} className="flex flex-col gap-2">
                        <div
                          className={`flex items-center justify-between p-4 bg-slate-50 rounded-2xl transition-all border border-slate-200/50 ${expandedDvrIds.includes(dvr.dvr_id) ? "rounded-b-none border-b-transparent" : "hover:bg-slate-100"}`}
                        >
                          <div className="flex items-center gap-4 flex-1">
                            <button
                              onClick={() => toggleDvrExpand(dvr.dvr_id)}
                              className={`w-8 h-8 flex items-center justify-center rounded-lg transition-all duration-300 cursor-pointer active:scale-90 ${expandedDvrIds.includes(dvr.dvr_id) ? "rotate-90 bg-brand-teal text-white shadow-md shadow-brand-teal/20" : "text-slate-400 hover:bg-slate-200 hover:text-slate-600"}`}
                            >
                              <ChevronRight className="w-4 h-4" />
                            </button>
                            <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400">
                              <Database className="w-6 h-6" />
                            </div>
                            <div className="flex-1">
                              {editingDvrId === dvr.dvr_id ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    autoFocus
                                    type="text"
                                    value={editingDvrName}
                                    onChange={(e) =>
                                      setEditingDvrName(e.target.value)
                                    }
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter")
                                        handleInlineDvrSave(dvr.dvr_id);
                                      if (e.key === "Escape")
                                        setEditingDvrId(null);
                                    }}
                                    className="h-8 bg-white border border-brand-teal rounded-lg px-2 text-[10px] font-black text-slate-900 w-full focus:outline-none shadow-sm shadow-brand-teal/10"
                                  />
                                  <button
                                    onClick={() =>
                                      handleInlineDvrSave(dvr.dvr_id)
                                    }
                                    className="w-7 h-7 flex items-center justify-center text-brand-teal hover:bg-brand-teal/10 rounded-lg shrink-0 cursor-pointer"
                                    title="Kaydet"
                                  >
                                    <Check className="w-4 h-4" />
                                  </button>
                                  <button
                                    onClick={() => setEditingDvrId(null)}
                                    className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg shrink-0 cursor-pointer"
                                    title="Vazgeç"
                                  >
                                    <X className="w-4 h-4" />
                                  </button>
                                </div>
                              ) : (
                                <h4 className="font-black text-slate-900 text-[10px] mb-0.5">
                                  {dvr.name}
                                </h4>
                              )}
                              <p className="text-[8px] font-bold text-slate-400 tracking-tight">
                                {dvr.ip_address} • {dvr.max_channels} KANAL •{" "}
                                {dvr.dvr_type}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => discoverChannels(dvr.dvr_id)}
                              disabled={isDiscoveringDvr === dvr.dvr_id}
                              className="flex items-center justify-center gap-2 px-4 h-9 rounded-xl bg-white border border-slate-200 text-slate-600 text-[9px] font-black uppercase tracking-widest hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-all cursor-pointer disabled:opacity-50 active:scale-95"
                            >
                              {isDiscoveringDvr === dvr.dvr_id ? (
                                <div className="h-3 w-3 border-2 border-slate-400 border-t-white rounded-full animate-spin" />
                              ) : (
                                <Search className="w-4 h-4" />
                              )}
                              KEŞFET
                            </button>
                            <button
                              onClick={() => {
                                setEditingDvrId(dvr.dvr_id);
                                setEditingDvrName(dvr.name || "");
                              }}
                              className="w-9 h-9 flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition-all cursor-pointer active:scale-95 border border-transparent"
                              title="DVR Adını Düzenle"
                            >
                              <Pencil className="w-5 h-5" />
                            </button>
                            <button
                              onClick={() => deleteDvr(dvr.dvr_id)}
                              disabled={isDeletingDvr}
                              className="w-9 h-9 flex items-center justify-center text-red-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition-all cursor-pointer disabled:opacity-50 active:scale-95 border border-transparent hover:border-red-100"
                            >
                              <Trash2 className="w-5 h-5" />
                            </button>
                          </div>
                        </div>

                        {/* Collapsible Channels Section */}
                        {expandedDvrIds.includes(dvr.dvr_id) && (
                          <div className="bg-slate-50/50 border-x border-b border-slate-200/50 rounded-b-2xl p-4 pt-0 -mt-2 animate-in fade-in slide-in-from-top-2 duration-300">
                            <div className="space-y-1 mt-4">
                              <div className="px-2 mb-2 flex items-center justify-between">
                                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">
                                  KEŞFEDİLEN KANALLAR
                                </span>
                                <span className="text-[8px] font-bold text-slate-300">
                                  {(() => {
                                    const dvrCams = managementCameras.filter(
                                      (c) => c.dvr_id === dvr.dvr_id,
                                    );
                                    return dvrCams.length;
                                  })()}{" "}
                                  ADET
                                </span>
                              </div>
                              <div className="grid grid-cols-1 gap-1">
                                {managementCameras.filter(
                                  (c) => c.dvr_id === dvr.dvr_id,
                                ).length === 0 ? (
                                  <div className="py-4 text-center">
                                    <p className="text-[9px] font-bold text-slate-400 uppercase italic">
                                      Henüz kanal keşfedilmedi. Keşfet butonunu
                                      kullanın.
                                    </p>
                                  </div>
                                ) : (
                                  managementCameras
                                    .filter((c) => c.dvr_id === dvr.dvr_id)
                                    .sort(
                                      (a, b) =>
                                        (a.channel_number || 0) -
                                        (b.channel_number || 0),
                                    )
                                    .map((camera) => (
                                      <div
                                        key={camera.camera_id}
                                        className="flex items-center justify-between p-2.5 bg-white border border-slate-100 rounded-xl hover:border-slate-300 transition-all group/channel"
                                      >
                                        <div className="flex items-center gap-3 flex-1 overflow-hidden">
                                          <div
                                            className={`w-7 h-7 flex-shrink-0 rounded-lg flex items-center justify-center text-[10px] font-black ${camera.status === "active" ? "bg-brand-teal text-white shadow-sm" : "bg-slate-100 text-slate-400 border border-slate-200"}`}
                                          >
                                            {camera.channel_number || "?"}
                                          </div>
                                          <div className="flex-1 overflow-hidden">
                                            {editingCameraId ===
                                            camera.camera_id ? (
                                              <input
                                                autoFocus
                                                type="text"
                                                value={editingCameraName}
                                                onChange={(e) =>
                                                  setEditingCameraName(
                                                    e.target.value,
                                                  )
                                                }
                                                onKeyDown={(e) => {
                                                  if (e.key === "Enter")
                                                    handleInlineCameraSave(
                                                      camera.camera_id,
                                                    );
                                                  if (e.key === "Escape")
                                                    setEditingCameraId(null);
                                                }}
                                                className="w-full bg-slate-50 border border-brand-teal text-[10px] font-black text-slate-900 px-2 py-1 rounded-lg outline-none"
                                              />
                                            ) : (
                                              <>
                                                <p className="text-[10px] font-black text-slate-900 truncate">
                                                  {camera.camera_name}
                                                </p>
                                                <p className="text-[8px] font-bold text-slate-400 uppercase tracking-tighter">
                                                  CH {camera.channel_number} •{" "}
                                                  {camera.status === "active"
                                                    ? "AKTİF"
                                                    : "GİZLİ"}
                                                </p>
                                              </>
                                            )}
                                          </div>
                                        </div>
                                        <div className="flex items-center gap-1 transition-opacity">
                                          {editingCameraId ===
                                          camera.camera_id ? (
                                            <>
                                              <button
                                                onClick={() =>
                                                  handleInlineCameraSave(
                                                    camera.camera_id,
                                                  )
                                                }
                                                className="w-8 h-8 flex items-center justify-center text-brand-teal hover:bg-brand-teal/10 rounded-lg transition-all cursor-pointer"
                                                title="Kaydet"
                                              >
                                                <Check className="w-5 h-5" />
                                              </button>
                                              <button
                                                onClick={() =>
                                                  setEditingCameraId(null)
                                                }
                                                className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all cursor-pointer"
                                                title="Vazgeç"
                                              >
                                                <X className="w-5 h-5" />
                                              </button>
                                            </>
                                          ) : (
                                            <>
                                              <button
                                                onClick={() =>
                                                  toggleCameraStatus(camera)
                                                }
                                                className={`w-8 h-8 flex items-center justify-center rounded-lg transition-all cursor-pointer ${camera.status === "active" ? "text-slate-400 hover:text-red-500 hover:bg-red-50" : "text-brand-teal hover:bg-brand-teal/10"}`}
                                                title={
                                                  camera.status === "active"
                                                    ? "Gizle"
                                                    : "Göster"
                                                }
                                              >
                                                 {camera.status === "active" ? (
                                                   <EyeOff className="w-5 h-5" />
                                                 ) : (
                                                   <Eye className="w-5 h-5" />
                                                 )}
                                              </button>
                                              <button
                                                onClick={() => {
                                                  setEditingCameraId(
                                                    camera.camera_id,
                                                  );
                                                  setEditingCameraName(
                                                    camera.camera_name || "",
                                                  );
                                                }}
                                                className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all cursor-pointer"
                                                title="Düzenle"
                                              >
                                                <Pencil className="w-5 h-5" />
                                              </button>
                                            </>
                                          )}
                                        </div>
                                      </div>
                                    ))
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
      {mounted &&
        createPortal(
          <ScheduleModal
            isOpen={isScheduleModalOpen}
            onClose={() => {
              setIsScheduleModalOpen(false);
              setSelectedCameraForSchedule(null);
            }}
            camera={selectedCameraForSchedule}
            companyId={companyId}
          />,
          document.body,
        )}
    </div>
  );
}
