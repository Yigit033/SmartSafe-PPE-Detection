"use client";

import { Suspense, useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useRouter, useSearchParams } from "next/navigation";
import { getCompanyId } from "@/lib/session";

export default function CamerasPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-400 text-sm">Yükleniyor...</div>}>
      <CamerasContent />
    </Suspense>
  );
}

function CamerasContent() {
  const [cameras, setCameras] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("smart");
  const [mounted, setMounted] = useState(false);
  const router = useRouter();

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

  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [groups, setGroups] = useState<any[]>([]);
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [activeGroupFilter, setActiveGroupFilter] = useState<string>("all");
  const [isManageGroupsOpen, setIsManageGroupsOpen] = useState(false);
  const [isManageDvrsOpen, setIsManageDvrsOpen] = useState(false);
  const [dvrs, setDvrs] = useState<any[]>([]);
  const [isDeletingDvr, setIsDeletingDvr] = useState(false);
  const [isDiscoveringDvr, setIsDiscoveringDvr] = useState<string | null>(null);
  const [groupFormData, setGroupFormData] = useState({
    name: "",
    location: "",
    group_type: "general",
    ppe_config: {
      helmet: { is_required: true, confidence_threshold: 0.3 },
      safety_vest: { is_required: true, confidence_threshold: 0.3 },
      gloves: { is_required: false, confidence_threshold: 0.3 },
      glasses: { is_required: false, confidence_threshold: 0.3 },
      face_mask: { is_required: false, confidence_threshold: 0.3 },
      safety_shoes: { is_required: false, confidence_threshold: 0.3 },
      ear_protection: { is_required: false, confidence_threshold: 0.3 },
      harness: { is_required: false, confidence_threshold: 0.3 },
    },
  });
  const [editingGroup, setEditingGroup] = useState<any>(null);
  const prevFiltersRef = useRef<{ search: string; group: string } | null>(null);
  const searchParams = useSearchParams();
  const camerasPerPage = parseInt(searchParams.get("limit") || "6", 10);
  const currentPage = Math.max(0, parseInt(searchParams.get("page") || "1", 10) - 1);

  const setLimit = (limit: number) => {
    const url = new URL(window.location.href);
    url.searchParams.set("limit", String(limit));
    url.searchParams.set("page", "1");
    window.location.href = url.pathname + url.search;
  };

  const setCurrentPage = useCallback((pageOrFn: number | ((prev: number) => number)) => {
    const next = typeof pageOrFn === "function" ? pageOrFn(currentPage) : pageOrFn;
    const url = new URL(window.location.href);
    url.searchParams.set("page", String(next + 1));
    window.location.href = url.pathname + url.search;
  }, [currentPage]);

  const companyId = getCompanyId();

  useEffect(() => {
    setMounted(true);
    setRefreshKey(Date.now());
    fetchCameras();
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    const cid = getCompanyId();
    if (!cid) return;
    try {
      const response = await fetch(
        `http://127.0.0.1:4000/company/${cid}/cameras/groups`,
      );
      const data = await response.json();
      if (data.success) {
        setGroups(data.groups);
      } else {
        console.error("Groups fetch failed:", data.error);
      }
    } catch (error) {
      console.error("Error fetching groups:", error);
    }
  };

  const fetchCameras = async () => {
    const cid = getCompanyId();
    if (!cid) return;
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://127.0.0.1:4000/company/${cid}/cameras`,
      );
      const data = await response.json();
      if (data.success) {
        setCameras(data.cameras);
        syncAiStates(cid, data.cameras);
      } else {
        console.error("Cameras fetch failed:", data.error);
      }
    } catch (error) {
      console.error("Error fetching cameras:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const syncAiStates = async (cid: string, _cams: any[]) => {
    try {
      const res = await fetch(
        `http://127.0.0.1:5000/api/company/${cid}/active-detections`,
      );
      const data = await res.json();
      if (data.success && data.active_camera_ids?.length > 0) {
        setEnabledAiCameras(data.active_camera_ids);
      }
    } catch {
      // backend unreachable — keep default empty
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

  const fetchStreamDiagnostics = async (
    cameraId: string,
  ): Promise<string | null> => {
    if (!companyId) return null;
    try {
      const r = await fetch(
        `http://127.0.0.1:5000/api/company/${companyId}/cameras/${cameraId}/stream-status`,
        { cache: "no-store" },
      );
      const body = await r.json().catch(() => null);
      const st = body && body.status ? body.status : {};
      const state = st.status || "unknown";
      const code =
        st.last_error_code || (body?.error?.code as string) || "UNKNOWN";
      const reason =
        st.status_reason || (body?.error?.message as string) || "unknown";
      return `State=${state} | Code=${code} | Reason=${reason} | HTTP=${r.status}`;
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

  const handleAssignToGroup = async (
    camera_id: string,
    group_id: string | null,
  ) => {
    const cid = getCompanyId();
    if (!cid) return;
    try {
      const response = await fetch(
        `http://127.0.0.1:4000/company/${cid}/cameras/${camera_id}/assign-group`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ group_id }),
        },
      );
      const data = await response.json();
      if (data.success) {
        fetchCameras();
        fetchGroups();
      } else {
        alert("Atama başarısız: " + (data.error || "Bilinmeyen hata"));
      }
    } catch (error: any) {
      console.error("Error assigning to group:", error);
      alert("Atama sırasında ağ hatası oluştu.");
    }
  };

  const handleSaveGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const cid = getCompanyId();

    if (!cid) {
      alert("Hata: Şirket kimliği bulunamadı. Lütfen tekrar giriş yapın.");
      return;
    }

    const url = editingGroup
      ? `http://127.0.0.1:4000/company/${cid}/cameras/groups/${editingGroup.group_id}`
      : `http://127.0.0.1:4000/company/${cid}/cameras/groups`;

    const method = editingGroup ? "PATCH" : "POST";

    console.log("Saving group to:", url, method, groupFormData);

    try {
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(groupFormData),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Sunucu hatası (${response.status}): ${errorText}`);
      }

      const data = await response.json();
      if (data.success) {
        setIsGroupModalOpen(false);
        fetchGroups();
        // Reset form
        setGroupFormData({
          name: "",
          location: "",
          group_type: "general",
          ppe_config: {
            helmet: { is_required: true, confidence_threshold: 0.3 },
            safety_vest: { is_required: true, confidence_threshold: 0.3 },
            gloves: { is_required: false, confidence_threshold: 0.3 },
            glasses: { is_required: false, confidence_threshold: 0.3 },
            face_mask: { is_required: false, confidence_threshold: 0.3 },
            safety_shoes: { is_required: false, confidence_threshold: 0.3 },
            ear_protection: { is_required: false, confidence_threshold: 0.3 },
            harness: { is_required: false, confidence_threshold: 0.3 },
          },
        });
        setEditingGroup(null);
      } else {
        alert("Grup kaydedilemedi: " + (data.error || "Bilinmeyen hata"));
      }
    } catch (error: any) {
      console.error("Error saving group:", error);
      alert("Ağ hatası veya sunucuya erişilemedi: " + error.message);
    }
  };

  const handleDeleteGroup = async (group_id: string) => {
    const cid = getCompanyId();
    if (!cid) return;
    if (
      !confirm(
        "Bu grubu silmek istediğinizden emin misiniz? Kameralar gruptan çıkarılacaktır.",
      )
    )
      return;
    try {
      const response = await fetch(
        `http://127.0.0.1:4000/company/${cid}/cameras/groups/${group_id}`,
        { method: "DELETE" },
      );
      const data = await response.json();
      if (data.success) {
        fetchGroups();
        fetchCameras();
      } else {
        alert("Grup silinemedi: " + (data.error || "Bilinmeyen hata"));
      }
    } catch (error: any) {
      console.error("Error deleting group:", error);
      alert("Silme işlemi sırasında ağ hatası oluştu.");
    }
  };

  const fetchDvrs = async () => {
    if (!companyId) return;
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/dvr`,
      );
      const data = await response.json();
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
      const response = await fetch(
        `http://127.0.0.1:5000/api/company/${companyId}/dvr/${dvrId}/discover`,
        {
          method: "POST",
        },
      );
      const data = await response.json();
      if (data.success) {
        const inactive = data.inactive_count || 0;
        const msg = inactive > 0
          ? `${data.count} aktif kanal bulundu (${inactive} kanalda kamera bağlı değil).`
          : `${data.count} kanal başarıyla keşfedildi!`;
        alert(msg);
        fetchCameras();
      } else {
        alert(`Hata: ${data.error || "Kanallar keşfedilemedi."}`);
      }
    } catch (error) {
      console.error("Error discovering channels:", error);
      alert("Sunucuyla bağlantı kurulamadı.");
    } finally {
      setIsDiscoveringDvr(null);
    }
  };

  const deleteDvr = async (dvrId: string) => {
    if (
      !confirm(
        "Bu DVR sistemini ve bağlı tüm kanalları silmek istediğinize emin misiniz?",
      )
    )
      return;
    setIsDeletingDvr(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/dvr/${dvrId}`,
        {
          method: "DELETE",
        },
      );
      const data = await response.json();
      if (data.success) {
        fetchDvrs();
        fetchCameras();
      }
    } catch (error) {
      console.error("Error deleting DVR:", error);
    } finally {
      setIsDeletingDvr(false);
    }
  };

  useEffect(() => {
    if (isManageDvrsOpen) {
      fetchDvrs();
    }
  }, [isManageDvrsOpen]);

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

  const filteredCameras = cameras.filter((cam) => {
    const matchesSearch =
      cam.camera_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cam.ip_address?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesGroup =
      activeGroupFilter === "all" || cam.group_id === activeGroupFilter;
    return matchesSearch && matchesGroup;
  });

  const totalPages = Math.ceil(filteredCameras.length / camerasPerPage);
  const paginatedCameras = filteredCameras.slice(
    currentPage * camerasPerPage,
    (currentPage + 1) * camerasPerPage,
  );

  useEffect(() => {
    if (prevFiltersRef.current === null) {
      prevFiltersRef.current = { search: searchTerm, group: activeGroupFilter };
      return;
    }
    const prev = prevFiltersRef.current;
    if (prev.search === searchTerm && prev.group === activeGroupFilter) {
      return;
    }
    prevFiltersRef.current = { search: searchTerm, group: activeGroupFilter };
    const url = new URL(window.location.href);
    url.searchParams.delete("page");
    router.replace(url.pathname + url.search, { scroll: false });
  }, [searchTerm, activeGroupFilter, router]);

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
            <span className="material-symbols-rounded">router</span> DVR
            YÖNETİMİ
          </button>
          <button
            onClick={() => setIsManageGroupsOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-white border border-slate-200 px-6 py-3.5 text-xs font-black text-slate-600 shadow-sm hover:bg-slate-50 transition-all cursor-pointer"
          >
            <span className="material-symbols-rounded">folder_open</span> GRUP
            YÖNETİMİ
          </button>
          <button
            onClick={() => router.push("/cameras/setup")}
            className="flex items-center gap-2 rounded-xl bg-brand-teal px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-teal/20 hover:bg-brand-teal/90 transition-all cursor-pointer"
          >
            <span className="material-symbols-rounded">add</span> YENİ KAMERA
            EKLE
          </button>
        </div>
      </section>

      {/* Group Quick Filter */}
      {groups.length > 0 && (
        <section className="flex items-center gap-3 overflow-x-auto pb-2 scrollbar-hide">
          <button
            onClick={() => setActiveGroupFilter("all")}
            className={`px-6 py-2.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${activeGroupFilter === "all" ? "bg-slate-900 text-white shadow-lg" : "bg-white border text-slate-400 hover:border-slate-300"}`}
          >
            TÜMÜ ({cameras.length})
          </button>
          {groups.map((group) => (
            <button
              key={group.group_id}
              onClick={() => setActiveGroupFilter(group.group_id)}
              className={`px-6 py-2.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${activeGroupFilter === group.group_id ? "bg-brand-teal text-white shadow-lg" : "bg-white border text-slate-400 hover:border-slate-300"}`}
            >
              {group.name} ({group.camera_count})
            </button>
          ))}
        </section>
      )}

      {filteredCameras.length === 0 && !isLoading ? (
        <div className="mt-12 flex flex-col items-center justify-center p-24 bg-white/40 rounded-[3rem] border-2 border-dashed border-slate-100 animate-fade-in min-h-[450px]">
          <div className="w-24 h-24 bg-slate-50/50 rounded-full flex items-center justify-center mb-8 border border-slate-100">
            <span className="material-symbols-rounded text-slate-300 text-4xl">
              videocam_off
            </span>
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
        <div className={`mt-12 grid gap-8 ${camerasPerPage === 1 ? "grid-cols-1 max-w-5xl mx-auto" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"}`}>
          {paginatedCameras.map((camera) => (
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
                    fetchStreamDiagnostics(camera.camera_id).then((diag) => {
                      if (!diag) return;
                      setFailedCameraDiagnostics((prev) => ({
                        ...prev,
                        [camera.camera_id]: diag,
                      }));
                    });
                    (e.target as HTMLImageElement).src =
                      "https://images.unsplash.com/photo-1557683316-973673baf926?q=80&w=1000&auto=format&fit=crop";
                    (e.target as HTMLImageElement).className =
                      "w-full h-full object-cover opacity-10 grayscale";
                  }}
                  onLoad={() => {
                    setFailedCameras((prev) =>
                      prev.filter((id) => id !== camera.camera_id),
                    );
                    setFailedCameraDiagnostics((prev) => {
                      const { [camera.camera_id]: _omit, ...rest } = prev;
                      return rest;
                    });
                  }}
                />

                {/* 🎯 Analiz Bölgesi Overlay */}
                {camera.detection_zones &&
                  camera.detection_zones.length > 0 &&
                  camera.detection_zones[0].length > 0 &&
                  !failedCameras.includes(camera.camera_id) && (
                    <svg
                      className="absolute inset-0 w-full h-full pointer-events-none z-10 opacity-70 group-hover:opacity-100 transition-opacity duration-500"
                      viewBox="0 0 1 1"
                      preserveAspectRatio="none"
                    >
                      <polygon
                        points={camera.detection_zones[0]
                          .map((p: any) => `${p.x},${p.y}`)
                          .join(" ")}
                        fill="rgba(20, 184, 166, 0.25)"
                        stroke="#14b8a6"
                        strokeWidth="0.015"
                        strokeDasharray="0.04 0.02"
                        className="drop-shadow-[0_0_12px_rgba(20,184,166,0.6)]"
                      />
                      {camera.detection_zones[0].map((p: any, idx: number) => (
                        <circle
                          key={idx}
                          cx={p.x}
                          cy={p.y}
                          r="0.008"
                          fill="#14b8a6"
                        />
                      ))}
                    </svg>
                  )}

                {failedCameras.includes(camera.camera_id) && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/40 backdrop-blur-sm">
                    <span className="material-symbols-rounded text-white/40 text-5xl mb-2 animate-pulse">
                      videocam_off
                    </span>
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
                    {isCameraAiEnabled(camera)
                      ? "visibility"
                      : "visibility_off"}
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
                      type="button"
                      onClick={() =>
                        router.push(
                          `/camera/${encodeURIComponent(camera.camera_id)}`,
                        )
                      }
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

                {/* Group Selector */}
                <div className="mt-4 pt-4 border-t border-slate-50 flex items-center justify-between">
                  <div className="flex items-center gap-2 overflow-hidden">
                    <span className="material-symbols-rounded text-slate-300 text-sm flex-shrink-0">
                      folder
                    </span>
                    <select
                      value={camera.group_id || ""}
                      onChange={(e) =>
                        handleAssignToGroup(
                          camera.camera_id,
                          e.target.value === "" ? null : e.target.value,
                        )
                      }
                      className="bg-transparent text-[10px] font-bold text-slate-500 uppercase tracking-tight outline-none cursor-pointer hover:text-brand-teal transition-colors w-full"
                    >
                      <option value="">Grup Yok</option>
                      {groups.map((g) => (
                        <option key={g.group_id} value={g.group_id}>
                          {g.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 flex items-center justify-center gap-3">
          {totalPages > 1 && (
            <>
              <button
                onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
                disabled={currentPage === 0}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-slate-600 hover:bg-brand-teal hover:text-white hover:border-brand-teal transition-all disabled:opacity-30 disabled:pointer-events-none shadow-sm"
              >
                <span className="material-symbols-rounded text-sm">chevron_left</span>
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
                <span className="material-symbols-rounded text-sm">chevron_right</span>
              </button>
            </>
          )}

          <div className="flex items-center gap-1.5 p-1.5 bg-slate-50 border border-slate-200 rounded-2xl ml-4 shadow-inner">
            <button
              onClick={() => setLimit(1)}
              className={`flex items-center gap-2 px-3 h-9 rounded-xl transition-all ${camerasPerPage === 1 ? "bg-slate-900 text-white shadow-lg" : "text-slate-400 hover:bg-white"}`}
            >
              <span className="material-symbols-rounded text-sm">rectangle</span>
              <span className="text-[10px] font-black uppercase tracking-widest leading-none">1</span>
            </button>
            <button
              onClick={() => setLimit(6)}
              className={`flex items-center gap-2 px-3 h-9 rounded-xl transition-all ${camerasPerPage === 6 ? "bg-slate-900 text-white shadow-lg" : "text-slate-400 hover:bg-white"}`}
            >
              <span className="material-symbols-rounded text-sm">grid_view</span>
              <span className="text-[10px] font-black uppercase tracking-widest leading-none">6</span>
            </button>
          </div>

          <span className="ml-4 text-[10px] font-black text-slate-400 uppercase tracking-[0.1em]">
            {filteredCameras.length} KAMERA • SAYFA {currentPage + 1}/{totalPages || 1}
          </span>
        </div>
        </>
      )}

      <div className="flex items-center justify-between py-8 border-t border-slate-200 text-[10px] font-black text-slate-400 uppercase tracking-widest mt-12">
        <p>SmartSafe AI v2.5 • Enterprise VMS</p>
        <div className="flex gap-2">
          <span className="text-brand-teal bg-white border px-3 py-1 rounded-lg">
            STATUS: SECURE
          </span>
        </div>
      </div>

      {/* Group Management Modal */}
      {isManageGroupsOpen &&
        mounted &&
        createPortal(
          <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-md"
              onClick={() => setIsManageGroupsOpen(false)}
            ></div>
            <div className="relative w-full max-w-2xl bg-white rounded-3xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
              <div className="bg-slate-900 p-6 flex items-center justify-between text-white">
                <div className="flex items-center gap-3">
                  <span className="material-symbols-rounded">
                    folder_managed
                  </span>
                  <h3 className="font-black tracking-widest uppercase italic text-sm">
                    KAMERA GRUP YÖNETİMİ
                  </h3>
                </div>
                <button
                  onClick={() => setIsManageGroupsOpen(false)}
                  className="p-2 hover:bg-white/10 rounded-xl"
                >
                  <span className="material-symbols-rounded">close</span>
                </button>
              </div>

              <div className="p-8 overflow-y-auto">
                <div className="flex items-center justify-between mb-8">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                    MEVCUT GRUPLAR ({groups.length})
                  </p>
                  <button
                    onClick={() => {
                      setEditingGroup(null);
                      setGroupFormData({
                        name: "",
                        location: "",
                        group_type: "general",
                        ppe_config: {
                          helmet: {
                            is_required: true,
                            confidence_threshold: 0.3,
                          },
                          safety_vest: {
                            is_required: true,
                            confidence_threshold: 0.3,
                          },
                          gloves: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                          glasses: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                          face_mask: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                          safety_shoes: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                          ear_protection: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                          harness: {
                            is_required: false,
                            confidence_threshold: 0.3,
                          },
                        },
                      });
                      setIsGroupModalOpen(true);
                    }}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-teal text-white text-[10px] font-black uppercase tracking-widest hover:bg-brand-teal/90"
                  >
                    <span className="material-symbols-rounded text-sm">
                      add
                    </span>{" "}
                    YENİ GRUP
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-4">
                  {groups.length === 0 ? (
                    <div className="py-12 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                      <p className="text-[10px] font-black text-slate-400 uppercase">
                        Henüz grup oluşturulmadı
                      </p>
                    </div>
                  ) : (
                    groups.map((group) => (
                      <div
                        key={group.group_id}
                        className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl hover:bg-slate-100 transition-colors border border-slate-200/50"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400">
                            <span className="material-symbols-rounded">
                              folder
                            </span>
                          </div>
                          <div>
                            <h4 className="font-black text-slate-900 uppercase italic text-xs mb-0.5">
                              {group.name}
                            </h4>
                            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">
                              {group.location || "Lokasyon Belirtilmemiş"} •{" "}
                              {group.camera_count} Kamera
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => {
                              setEditingGroup(group);
                              setGroupFormData({
                                name: group.name,
                                location: group.location || "",
                                group_type: group.group_type || "general",
                                ppe_config: group.ppe_config || {
                                  helmet: {
                                    is_required: true,
                                    confidence_threshold: 0.3,
                                  },
                                  safety_vest: {
                                    is_required: true,
                                    confidence_threshold: 0.3,
                                  },
                                  gloves: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                  glasses: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                  face_mask: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                  safety_shoes: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                  ear_protection: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                  harness: {
                                    is_required: false,
                                    confidence_threshold: 0.3,
                                  },
                                },
                              });
                              setIsGroupModalOpen(true);
                            }}
                            className="p-2 text-slate-400 hover:text-slate-900 hover:bg-white rounded-lg transition-all"
                          >
                            <span className="material-symbols-rounded text-lg">
                              edit
                            </span>
                          </button>
                          <button
                            onClick={() => handleDeleteGroup(group.group_id)}
                            className="p-2 text-red-300 hover:text-red-500 hover:bg-white rounded-lg transition-all"
                          >
                            <span className="material-symbols-rounded text-lg">
                              delete
                            </span>
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Create/Edit Group Modal */}
      {isGroupModalOpen &&
        mounted &&
        createPortal(
          <div className="fixed inset-0 z-[140] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
              onClick={() => setIsGroupModalOpen(false)}
            ></div>
            <div className="relative w-full max-w-lg bg-white rounded-[2rem] overflow-hidden shadow-2xl animate-scale-in flex flex-col max-h-[90vh]">
              <div className="bg-brand-teal p-6 flex items-center justify-between text-white shrink-0">
                <h3 className="font-black tracking-widest uppercase italic text-xs">
                  {editingGroup ? "GRUBU DÜZENLE" : "YENİ GRUP OLUŞTUR"}
                </h3>
                <button
                  onClick={() => setIsGroupModalOpen(false)}
                  className="p-1 hover:bg-white/20 rounded-lg"
                >
                  <span className="material-symbols-rounded">close</span>
                </button>
              </div>
              <form
                onSubmit={handleSaveGroup}
                className="p-8 space-y-6 overflow-y-auto"
              >
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1">
                      Grup Adı
                    </label>
                    <input
                      type="text"
                      value={groupFormData.name}
                      onChange={(e) =>
                        setGroupFormData({
                          ...groupFormData,
                          name: e.target.value,
                        })
                      }
                      placeholder="Örn: Kuzey Cephe"
                      className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none focus:border-brand-teal"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1">
                      Lokasyon
                    </label>
                    <input
                      type="text"
                      value={groupFormData.location}
                      onChange={(e) =>
                        setGroupFormData({
                          ...groupFormData,
                          location: e.target.value,
                        })
                      }
                      placeholder="Örn: Ana Fabrika"
                      className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none focus:border-brand-teal"
                    />
                  </div>

                  <div className="space-y-3 pt-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1 block border-b border-slate-100 pb-2">
                      KGİ TESPİT AYARLARI
                    </label>
                    <div className="grid grid-cols-1 gap-3">
                      {Object.entries(groupFormData.ppe_config || {}).map(
                        ([key, config]: [string, any]) => (
                          <div
                            key={key}
                            className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100"
                          >
                            <div className="flex items-center gap-3">
                              <div
                                className={`w-8 h-8 rounded-lg flex items-center justify-center ${config.is_required ? "bg-brand-teal/10 text-brand-teal" : "bg-slate-200 text-slate-400"}`}
                              >
                                <span className="material-symbols-rounded text-sm">
                                  {key === "helmet"
                                    ? "engineering"
                                    : key === "safety_vest"
                                      ? "checkroom"
                                      : key === "gloves"
                                        ? "back_hand"
                                        : key === "glasses"
                                          ? "visibility"
                                          : key === "face_mask"
                                            ? "masks"
                                            : key === "safety_shoes"
                                              ? "ice_skating"
                                              : key === "ear_protection"
                                                ? "hearing"
                                                : "accessibility_new"}
                                </span>
                              </div>
                              <div>
                                <span className="text-[10px] font-black text-slate-700 uppercase tracking-tight">
                                  {key === "helmet"
                                    ? "KASK"
                                    : key === "safety_vest"
                                      ? "YELEK"
                                      : key === "gloves"
                                        ? "ELDİVEN"
                                        : key === "glasses"
                                          ? "GÖZLÜK"
                                          : key === "face_mask"
                                            ? "MASKE"
                                            : key === "safety_shoes"
                                              ? "AYAKKABI"
                                              : key === "ear_protection"
                                                ? "KULAKLIK"
                                                : "EMNİYET KEMERİ"}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center gap-4">
                              <div className="flex flex-col items-end gap-1">
                                <span className="text-[8px] font-black text-slate-400 uppercase tracking-tighter">
                                  {config.is_required ? "ZORUNLU" : "PASİF"}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const newPpeConfig = {
                                      ...groupFormData.ppe_config,
                                    } as any;
                                    newPpeConfig[key] = {
                                      ...config,
                                      is_required: !config.is_required,
                                    };
                                    setGroupFormData({
                                      ...groupFormData,
                                      ppe_config: newPpeConfig,
                                    });
                                  }}
                                  className={`relative w-10 h-5 rounded-full transition-all duration-300 ${config.is_required ? "bg-brand-teal" : "bg-slate-200"}`}
                                >
                                  <div
                                    className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all duration-300 ${config.is_required ? "left-6" : "left-1"}`}
                                  ></div>
                                </button>
                              </div>
                            </div>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-4 pt-4">
                  <button
                    type="button"
                    onClick={() => setIsGroupModalOpen(false)}
                    className="flex-1 py-4 text-[10px] font-black uppercase text-slate-400 rounded-xl bg-slate-50 hover:bg-slate-100"
                  >
                    VAZGEÇ
                  </button>
                  <button
                    type="submit"
                    className="flex-1 py-4 text-[10px] font-black uppercase text-white rounded-xl bg-brand-teal hover:bg-brand-teal/90 shadow-lg shadow-brand-teal/20"
                  >
                    KAYDET
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
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
                  <span className="material-symbols-rounded">router</span>
                  <h3 className="font-black tracking-widest uppercase italic text-sm">
                    DVR SİSTEM YÖNETİMİ
                  </h3>
                </div>
                <button
                  onClick={() => setIsManageDvrsOpen(false)}
                  className="p-2 hover:bg-white/10 rounded-xl"
                >
                  <span className="material-symbols-rounded">close</span>
                </button>
              </div>

              <div className="p-8 overflow-y-auto">
                <div className="flex items-center justify-between mb-8">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                    KAYITLI CİHAZLAR ({dvrs.length})
                  </p>
                  <button
                    onClick={() => router.push("/cameras/setup")}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-teal text-white text-[10px] font-black uppercase tracking-widest hover:bg-brand-teal/90"
                  >
                    <span className="material-symbols-rounded text-sm">
                      add
                    </span>{" "}
                    CİHAZ EKLE
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-4">
                  {dvrs.length === 0 ? (
                    <div className="py-12 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                      <p className="text-[10px] font-black text-slate-400 uppercase text-center w-full">
                        Henüz DVR sistemi eklenmedi
                      </p>
                    </div>
                  ) : (
                    dvrs.map((dvr) => (
                      <div
                        key={dvr.dvr_id}
                        className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl hover:bg-slate-100 transition-colors border border-slate-200/50"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-400">
                            <span className="material-symbols-rounded">
                              dns
                            </span>
                          </div>
                          <div>
                            <h4 className="font-black text-slate-900 uppercase italic text-xs mb-0.5">
                              {dvr.name}
                            </h4>
                            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">
                              {dvr.ip_address} • {dvr.max_channels} KANAL •{" "}
                              {dvr.dvr_type}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => discoverChannels(dvr.dvr_id)}
                            disabled={isDiscoveringDvr === dvr.dvr_id}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-200 text-slate-600 text-[9px] font-black uppercase tracking-widest hover:bg-brand-teal hover:text-white transition-all disabled:opacity-50"
                          >
                            {isDiscoveringDvr === dvr.dvr_id ? (
                              <div className="h-3 w-3 border-2 border-slate-400 border-t-white rounded-full animate-spin" />
                            ) : (
                              <span className="material-symbols-rounded text-sm">
                                search
                              </span>
                            )}
                            KEŞFET
                          </button>
                          <button
                            onClick={() => deleteDvr(dvr.dvr_id)}
                            disabled={isDeletingDvr}
                            className="p-2 text-red-300 hover:text-red-500 hover:bg-white rounded-lg transition-all disabled:opacity-50"
                          >
                            <span className="material-symbols-rounded text-lg">
                              delete
                            </span>
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
