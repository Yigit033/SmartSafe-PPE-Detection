"use client";

import {
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import ZoneDesigner from "@/components/dashboard/ZoneDesigner";

type Props = {
  camera: any;
  companyId: string;
  enabledAiCameras: string[];
  onToggleAi: (cameraId: string, currentStatus: boolean) => Promise<void>;
  onZonesSaved?: () => void;
  topBarExtra?: ReactNode;
};

export default function CameraLiveView({
  camera,
  companyId,
  enabledAiCameras,
  onToggleAi,
  onZonesSaved,
  topBarExtra,
}: Props) {
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isZoneModalOpen, setIsZoneModalOpen] = useState(false);

  const isCameraAiEnabled = useCallback(
    (item: any) => enabledAiCameras.includes(item.camera_id),
    [enabledAiCameras],
  );

  const startStream = useCallback(
    (id: string) => {
      setStreamError(null);
      const isAi = isCameraAiEnabled({ camera_id: id });
      const url = isAi
        ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${id}?t=${Date.now()}`
        : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${id}/proxy-stream?t=${Date.now()}`;
      setStreamUrl(url);
    },
    [companyId, isCameraAiEnabled],
  );

  useEffect(() => {
    if (camera?.camera_id) {
      startStream(camera.camera_id);
    }
  }, [camera?.camera_id, enabledAiCameras, startStream]);

  const fetchStreamDiagnostics = async (cameraId: string) => {
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

  const handleSaveZones = async (zones: any[][]) => {
    if (!camera?.camera_id) return;
    try {
      const response = await fetch(
        `http://127.0.0.1:4000/company/${companyId}/cameras/${camera.camera_id}/roi`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ zones }),
        },
      );
      const data = await response.json();
      if (data.success) {
        setIsZoneModalOpen(false);
        onZonesSaved?.();
      }
    } catch (error) {
      console.error("Error saving zones:", error);
    }
  };

  if (!camera) return null;

  return (
    <div
      className="relative w-full min-h-[calc(100vh-8rem)] flex flex-col rounded-[2rem] border border-white/10 bg-black shadow-2xl overflow-hidden"
      lang="tr"
    >
      <div className="absolute top-4 left-4 right-4 z-10 flex flex-wrap items-center justify-between gap-3 pointer-events-none md:top-8 md:left-8 md:right-8">
        <div className="flex flex-col gap-1 pointer-events-auto min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <div className="bg-red-500 px-3 py-1 rounded-full text-white flex items-center gap-2 shadow-xl shrink-0">
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
              <span className="text-[10px] font-black uppercase tracking-wider">
                CANLI
              </span>
            </div>
            <h1 className="text-xl md:text-2xl font-black text-white italic drop-shadow-lg uppercase tracking-tight truncate">
              {camera.camera_name}
            </h1>
          </div>
          <p className="text-[10px] font-bold text-white/50 uppercase tracking-widest truncate">
            {camera.location}{" "}
            {camera.camera_type === "dvr_channel" ? "· DVR kanalı" : "· IP kamera"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 md:gap-4 pointer-events-auto">
          {topBarExtra}
          <div className="flex items-center gap-2 md:gap-3 bg-white/10 backdrop-blur-md px-3 py-2 rounded-2xl border border-white/10">
            <span className="text-[10px] font-black text-white/60 tracking-widest uppercase hidden sm:inline">
              ANALİZ BÖLGESİ
            </span>
            <button
              type="button"
              onClick={() => setIsZoneModalOpen(true)}
              className="flex items-center gap-2 px-3 py-1 rounded-xl bg-white/10 text-white hover:bg-white text-[10px] font-black uppercase tracking-widest hover:text-slate-900 transition-all cursor-pointer border border-white/10"
            >
              <span className="material-symbols-rounded text-sm">polyline</span>
              GÜNCELLE
            </button>
          </div>
          <div className="flex items-center gap-2 md:gap-3 bg-white/10 backdrop-blur-md px-3 py-2 rounded-2xl border border-white/10">
            <span className="text-[10px] font-black text-white/60 tracking-widest uppercase hidden sm:inline">
              BAĞLANTI
            </span>
            <button
              type="button"
              onClick={() => startStream(camera.camera_id)}
              className="flex items-center gap-2 px-3 py-1 rounded-xl bg-white/10 text-white hover:bg-white text-[10px] font-black uppercase tracking-widest hover:text-slate-900 transition-all cursor-pointer border border-white/10"
            >
              <span className="material-symbols-rounded text-sm">refresh</span>
              YENİLE
            </button>
          </div>
          <div className="flex items-center gap-2 md:gap-3 bg-white/10 backdrop-blur-md px-3 py-2 rounded-2xl border border-white/10">
            <span className="text-[10px] font-black text-white/60 tracking-widest uppercase hidden sm:inline">
              AI ANALİZ
            </span>
            <button
              type="button"
              onClick={async () => {
                const isAi = isCameraAiEnabled(camera);
                await onToggleAi(camera.camera_id, isAi);
                const nextAiEnabled = !isAi;
                const url = nextAiEnabled
                  ? `http://127.0.0.1:5000/api/company/${companyId}/video-feed/${camera.camera_id}?t=${Date.now()}`
                  : `http://127.0.0.1:5000/api/company/${companyId}/cameras/${camera.camera_id}/proxy-stream?t=${Date.now()}`;
                setStreamUrl(url);
              }}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${isCameraAiEnabled(camera) ? "bg-brand-teal" : "bg-white/20"}`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${isCameraAiEnabled(camera) ? "translate-x-6" : "translate-x-1"}`}
              />
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-black relative min-h-[50vh] mt-24 md:mt-28">
        {isZoneModalOpen && streamUrl ? (
          <div className="absolute inset-0 z-50 p-4 md:p-12">
            <ZoneDesigner
              imageUrl={streamUrl}
              initialZones={camera?.detection_zones || []}
              onSave={handleSaveZones}
              onClose={() => setIsZoneModalOpen(false)}
            />
          </div>
        ) : streamUrl ? (
          <div className="relative w-full h-full flex items-center justify-center bg-black">
            <img
              src={streamUrl}
              alt="Canlı Yayın"
              className="w-full h-full object-contain max-h-[80vh]"
              onError={async () => {
                const diag = await fetchStreamDiagnostics(camera.camera_id);
                if (diag) setStreamError(diag);
                setStreamUrl(null);
              }}
            />
            {camera?.detection_zones &&
              camera.detection_zones.length > 0 &&
              camera.detection_zones[0].length > 0 &&
              !isCameraAiEnabled(camera) && (
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none z-10 opacity-60"
                  viewBox="0 0 1 1"
                  preserveAspectRatio="none"
                >
                  <polygon
                    points={camera.detection_zones[0]
                      .map((p: any) => `${p.x},${p.y}`)
                      .join(" ")}
                    fill="rgba(20, 184, 166, 0.15)"
                    stroke="#14b8a6"
                    strokeWidth="0.01"
                    strokeDasharray="0.02 0.01"
                    className="drop-shadow-[0_0_10px_rgba(20,184,166,0.5)]"
                  />
                  {camera.detection_zones[0].map((p: any, idx: number) => (
                    <circle key={idx} cx={p.x} cy={p.y} r="0.005" fill="#14b8a6" />
                  ))}
                </svg>
              )}
          </div>
        ) : (
          <div className="text-white/20 text-center px-4">
            <span className="material-symbols-rounded text-[120px] animate-pulse">
              videocam_off
            </span>
            <p className="mt-4 font-black tracking-widest uppercase italic">
              SİNYAL YOK
            </p>
            {streamError && (
              <p className="mt-3 text-[10px] font-mono text-white/40 max-w-[90%] mx-auto">
                {streamError}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
