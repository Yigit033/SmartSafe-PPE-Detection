"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { usePathname } from "next/navigation";
import { registerStream, unregisterStream } from "@/lib/streamRegistry";

interface MjpegCanvasProps {
  src: string;
  alt?: string;
  className?: string;
  fps?: number;
  onDimensions?: (width: number, height: number, clientWidth: number, clientHeight: number) => void;
  onError?: () => void;
}

/**
 * MjpegCanvas: MJPEG stream'i fetch/stream ile okuyup <img> üzerine çizen,
 * native browser scaling sayesinde tam kalitede görüntü veren bileşen.
 * Canvas yerine <img> kullanımı — GPU-accelerated, bulanıklık yok.
 */
const MjpegCanvas: React.FC<MjpegCanvasProps> = ({
  src,
  className = "",
  fps = 30,
  onDimensions,
  onError,
}) => {
  const imgRef = useRef<HTMLImageElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasFrame, setHasFrame] = useState(false);       // En az 1 kare geldi mi?
  const [isReconnecting, setIsReconnecting] = useState(false); // Yeniden bağlanıyor mu?
  const abortControllerRef = useRef<AbortController | null>(null);
  const fpsRef = useRef(fps);
  const prevBlobRef = useRef<string | null>(null);
  const startStreamRef = useRef<(() => void) | null>(null);
  useEffect(() => { fpsRef.current = fps; }, [fps]);

  // Sayfa değişince stream'i anında iptal et
  const pathname = usePathname();
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [pathname]);

  // Tab arka plana geçince durdur, öne gelince yeniden başlat
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
          unregisterStream(abortControllerRef.current);
          abortControllerRef.current = null;
        }
      } else if (document.visibilityState === "visible") {
        setIsReconnecting(true); // Son kare üzeri overlay
        startStreamRef.current?.();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  useEffect(() => {
    let lastFrameTime = 0;

    const startStream = async () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        unregisterStream(abortControllerRef.current);
      }

      if (document.visibilityState === "hidden") return;

      // Her yeni baglantida boyutlari bir kez bildir (reconnect sonrasi loadedCameras guncellenir)
      let sessionDimensionsReported = false;

      const controller = new AbortController();
      abortControllerRef.current = controller;
      registerStream(controller);
      setError(null);

      try {
        const response = await fetch(src, { signal: controller.signal });

        if (!response.ok) {
          throw new Error(`Stream hatası: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("Stream okunamadı");

        let chunks = new Uint8Array(0);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // Yeni veriyi birleştir
          const merged = new Uint8Array(chunks.length + value.length);
          merged.set(chunks);
          merged.set(value, chunks.length);
          chunks = merged;

          // JPEG başlangıç (0xFFD8) bul
          let start = -1;
          for (let i = 0; i < chunks.length - 1; i++) {
            if (chunks[i] === 0xff && chunks[i + 1] === 0xd8) {
              start = i;
              break;
            }
          }
          if (start === -1) {
            if (chunks.length > 2 * 1024 * 1024) chunks = new Uint8Array(0);
            continue;
          }

          // JPEG bitiş (0xFFD9) bul
          let end = -1;
          for (let i = start + 2; i < chunks.length - 1; i++) {
            if (chunks[i] === 0xff && chunks[i + 1] === 0xd9) {
              end = i + 2;
              break;
            }
          }

          if (end !== -1) {
            const now = performance.now();
            const frameInterval = 1000 / fpsRef.current;

            if (now - lastFrameTime >= frameInterval) {
              const frameData = chunks.slice(start, end);
              const blob = new Blob([frameData], { type: "image/jpeg" });
              const url = URL.createObjectURL(blob);

              const imgEl = imgRef.current;
              if (imgEl) {
                imgEl.onload = () => {
                  if (prevBlobRef.current) {
                    URL.revokeObjectURL(prevBlobRef.current);
                  }
                  prevBlobRef.current = url;

                  // Her yeni baglantiyla ilk frame gelince onDimensions'i cagir
                  // Boylece reconnect sonrasi CANLI badge geri gelir
                  if (!sessionDimensionsReported && onDimensions) {
                    sessionDimensionsReported = true;
                    onDimensions(
                      imgEl.naturalWidth,
                      imgEl.naturalHeight,
                      imgEl.clientWidth,
                      imgEl.clientHeight
                    );
                  }
                  setHasFrame(true);
                  setIsReconnecting(false);
                };
                imgEl.src = url;
              }

              lastFrameTime = now;
            }

            chunks = chunks.slice(end);
          }
        }
      } catch (err: any) {
        if (err.name === "AbortError") return;
        console.error("MJPEG Stream Error:", err);
        setError("Görüntü akışı kesildi.");
        setIsReconnecting(false);
        onError?.();
      }
    };

    startStream();
    startStreamRef.current = startStream; // visibility handler için sakla

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        unregisterStream(abortControllerRef.current);
      }
      // Kalan blob'u temizle
      if (prevBlobRef.current) {
        URL.revokeObjectURL(prevBlobRef.current);
        prevBlobRef.current = null;
      }
    };
  }, [src]);

  return (
    <div className={`relative overflow-hidden bg-slate-900 ${className}`}>
      {/* Son kare her zaman görünür */}
      <img
        ref={imgRef}
        alt=""
        className="w-full h-full object-contain"
        style={{ opacity: hasFrame ? 1 : 0, transition: "opacity 0.3s" }}
      />

      {/* İlk kare bekleniyor */}
      {!hasFrame && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
          <RefreshCw className="w-5 h-5 text-brand-teal animate-spin" />
        </div>
      )}

      {/* Status Badges Container */}
      {(hasFrame || isReconnecting) && !error && (
        <div className="absolute top-4 left-4 flex items-center gap-3">
          {hasFrame && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-red-500 text-white shadow-lg">
              <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
              <span className="text-[8px] font-black uppercase tracking-tighter">CANLI</span>
            </div>
          )}
          
          {isReconnecting && (
            <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-black/40 backdrop-blur-sm text-white shadow-lg transition-all">
              <RefreshCw className="w-3 h-3 animate-spin text-brand-teal" />
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80 text-slate-400 p-4 text-center">
          <AlertCircle className="w-8 h-8 mb-2 text-red-500" />
          <p className="text-xs">{error}</p>
        </div>
      )}
    </div>
  );
};

export default MjpegCanvas;
