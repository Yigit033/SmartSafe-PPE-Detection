"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getCompanyId } from "@/lib/session";
import { goToCamerasPage } from "@/lib/camerasNavigation";
import CameraLiveView from "@/components/camera/CameraLiveView";

import api from "@/lib/api";
import core from "@/lib/core";

function CameraDetailContent() {
  const params = useParams();
  const rawId = params?.id;
  const cameraId = Array.isArray(rawId) ? rawId[0] : rawId;
  const decodedId = cameraId ? decodeURIComponent(cameraId) : "";

  const companyId = getCompanyId();
  const [camera, setCamera] = useState<any | null>(undefined);
  const [enabledAiCameras, setEnabledAiCameras] = useState<string[]>([]);


  const syncAiStates = useCallback(async (cid: string) => {
    try {
      const data = await core.getActiveDetections(cid);
      if (data.success && data.active_camera_ids && data.active_camera_ids.length > 0) {
        setEnabledAiCameras(data.active_camera_ids);
      }
    } catch {
      /* core kapalı olabilir */
    }
  }, []);

  const loadCamera = useCallback(async () => {
    const cid = getCompanyId();
    if (!cid || !decodedId) {
      setCamera(null);
      return;
    }
    try {
      const data = await api.camera.list(cid);
      if (data.success && Array.isArray(data.cameras)) {
        const found = data.cameras.find(
          (c: any) => c.camera_id === decodedId,
        );
        setCamera(found ?? null);
        await syncAiStates(cid);
      } else {
        setCamera(null);
      }
    } catch {
      setCamera(null);
    }
  }, [decodedId, syncAiStates]);

  useEffect(() => {
    loadCamera();
  }, [loadCamera]);

  const toggleCameraAi = async (id: string, currentStatus: boolean) => {
    const cid = getCompanyId();
    if (!cid) return;
    const newAiStatus = !currentStatus;
    const endpoint = newAiStatus ? "start-detection" : "stop-detection";
    setEnabledAiCameras((prev) =>
      newAiStatus ? [...prev, id] : prev.filter((x) => x !== id),
    );
    try {
      await fetch(`http://127.0.0.1:5000/api/company/${cid}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_id: id }),
      });
      await syncAiStates(cid);
    } catch (e) {
      console.error(e);
      await syncAiStates(cid);
    }
  };

  if (!companyId) {
    return (
      <div className="p-12 text-center text-slate-500">
        Oturum bulunamadı.{" "}
        <Link href="/login" className="text-brand-teal font-bold">
          Giriş
        </Link>
      </div>
    );
  }

  if (camera === undefined) {
    return (
      <div className="p-12 text-center text-slate-400 text-sm animate-pulse">
        Yükleniyor…
      </div>
    );
  }

  if (!camera) {
    return (
      <div className="max-w-lg mx-auto p-12 text-center space-y-4">
        <p className="text-slate-700 font-bold">Kamera bulunamadı.</p>
        <button
          type="button"
          onClick={() => goToCamerasPage()}
          className="text-brand-teal font-black uppercase text-sm tracking-widest"
        >
          ← Kamera listesine dön
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => goToCamerasPage()}
          className="flex items-center gap-2 rounded-xl bg-white border border-slate-200 px-4 py-2.5 text-xs font-black text-slate-600 shadow-sm hover:bg-slate-50"
        >
          <span className="material-symbols-rounded text-lg">arrow_back</span>
          Kameralar
        </button>
      </div>

      <CameraLiveView
        camera={camera}
        companyId={companyId}
        enabledAiCameras={enabledAiCameras}
        onToggleAi={toggleCameraAi}
        onZonesSaved={loadCamera}
      />
    </div>
  );
}

export default function CameraDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-slate-400 text-sm">Yükleniyor…</div>
      }
    >
      <CameraDetailContent />
    </Suspense>
  );
}
