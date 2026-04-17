"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface MjpegCanvasProps {
  src: string;
  alt?: string;
  className?: string;
  fps?: number; 
  onDimensions?: (width: number, height: number, clientWidth: number, clientHeight: number) => void;
  onError?: () => void;
}

/**
 * MjpegCanvas: <img> etiketi yerine MJPEG akışını fetch/stream ile yöneten,
 * sayfadan ayrıldığında bağlantıyı anında koparan verimli görüntüleyici.
 */
const MjpegCanvas: React.FC<MjpegCanvasProps> = ({ 
  src, 
  className = "", 
  fps = 30,
  onDimensions,
  onError
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let lastFrameTime = 0;
    const frameInterval = 1000 / fps;

    const startStream = async () => {
      // Önceki isteği iptal et
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(src, { signal: controller.signal });
        
        if (!response.ok) {
          throw new Error(`Stream hatası: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("Stream okunamadı");

        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");
        if (!ctx || !canvas) return;

        // Kareleri ayırmak için MJPEG boundary parsing (Simple version)
        // Not: Gerçek MJPEG stream'lerde kareler 0xFF 0xD8 ile başlar, 0xFF 0xD9 ile biter.
        let chunks = new Uint8Array(0);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // Yeni veriyi birleştir
          const newChunks = new Uint8Array(chunks.length + value.length);
          newChunks.set(chunks);
          newChunks.set(value, chunks.length);
          chunks = newChunks;

          // JPEG başlagıç (0xFFD8) ve bitiş (0xFFD9) noktalarını bul
          let start = -1;
          for (let i = 0; i < chunks.length - 1; i++) {
            if (chunks[i] === 0xff && chunks[i + 1] === 0xd8) {
              start = i;
              break;
            }
          }

          if (start === -1) {
            if (chunks.length > 1024 * 1024) chunks = new Uint8Array(0); // Buffer taşarsa sıfırla
            continue;
          }

          let end = -1;
          for (let i = start + 2; i < chunks.length - 1; i++) {
            if (chunks[i] === 0xff && chunks[i + 1] === 0xd9) {
              end = i + 2;
              break;
            }
          }

          if (end !== -1) {
            const now = performance.now();
            if (now - lastFrameTime >= frameInterval) {
              const frameData = chunks.slice(start, end);
              const blob = new Blob([frameData], { type: "image/jpeg" });
              const url = URL.createObjectURL(blob);
              
              const img = new Image();
              img.onload = () => {
                // Canvas boyutlarını görüntüye göre ayarla (ilk karede)
                if (canvas.width !== img.width || canvas.height !== img.height) {
                  canvas.width = img.width;
                  canvas.height = img.height;
                  
                  // Boyutları dışarı bildir
                  if (onDimensions) {
                    onDimensions(img.width, img.height, canvas.clientWidth, canvas.clientHeight);
                  }
                }
                
                // En yüksek kalite ayarları
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = 'high';
                
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);
                setIsLoading(false);
              };
              img.src = url;
              lastFrameTime = now;
            }
            
            // İşlenen kısmı buffer'dan at
            chunks = chunks.slice(end);
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        console.error("MJPEG Stream Error:", err);
        setError("Görüntü akışı kesildi.");
        setIsLoading(false);
      }
    };

    startStream();

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [src, fps]);

  return (
    <div className={`relative overflow-hidden bg-slate-900 group ${className}`}>
      <canvas 
        ref={canvasRef} 
        style={{ imageRendering: 'auto' }}
        className="w-full h-full object-contain"
      />
      
      {isLoading && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/40">
          <RefreshCw className="w-6 h-6 text-brand-teal animate-spin" />
        </div>
      )}

      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900 text-slate-400 p-4 text-center">
          <AlertCircle className="w-8 h-8 mb-2 text-red-500" />
          <p className="text-xs">{error}</p>
        </div>
      )}
    </div>
  );
};

export default MjpegCanvas;
