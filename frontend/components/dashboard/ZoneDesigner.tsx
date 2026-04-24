"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  type ZonePoint,
  getObjectFitContainRect,
  videoNormToContainerPixel,
  containerPixelToVideoNorm,
  containerNormToVideoNorm,
} from "@/lib/detectionZones";
import { X, BoxSelect, Grab } from "lucide-react";
import MjpegCanvas from "@/components/camera/MjpegCanvas";

interface ZoneDesignerProps {
  imageUrl: string;
  initialZones?: ZonePoint[][];
  /** DB'den gelen: video = yeni format; container = eski düz dizi (konteyner 0–1) */
  zonesCoordSpace?: "video" | "container";
  onSave: (zones: ZonePoint[][]) => void;
  onClose: () => void;
}

export default function ZoneDesigner({
  imageUrl,
  initialZones = [],
  zonesCoordSpace = "video",
  onSave,
  onClose,
}: ZoneDesignerProps) {
  const defaultPoints: ZonePoint[] = [
    { x: 0.2, y: 0.2 },
    { x: 0.8, y: 0.2 },
    { x: 0.8, y: 0.8 },
    { x: 0.2, y: 0.8 },
  ];

  const imgRef = useRef<HTMLImageElement>(null);
  const [intrinsic, setIntrinsic] = useState({ w: 0, h: 0 });
  const legacyConvertedRef = useRef(false);

  const [points, setPoints] = useState<ZonePoint[]>(() => {
    if (
      initialZones &&
      initialZones.length > 0 &&
      initialZones[0] &&
      initialZones[0].length > 0
    ) {
      return initialZones[0].map((p) => ({ x: p.x, y: p.y }));
    }
    return defaultPoints;
  });

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<number | null>(null);

  const onImgLoad = useCallback(() => {
    const el = imgRef.current;
    if (!el || el.naturalWidth <= 0 || el.naturalHeight <= 0) return;
    setIntrinsic({ w: el.naturalWidth, h: el.naturalHeight });
  }, []);

  // Eski düz dizi (konteyner 0–1): canvas ve intrinsic hazır olunca bir kez video uzayına taşı
  useEffect(() => {
    if (zonesCoordSpace !== "container" || legacyConvertedRef.current) return;
    if (intrinsic.w <= 0 || intrinsic.h <= 0) return;

    let alive = true;
    const tryConvert = () => {
      if (!alive || legacyConvertedRef.current) return;
      const canvas = canvasRef.current;
      if (!canvas || canvas.width < 8 || canvas.height < 8) {
        requestAnimationFrame(tryConvert);
        return;
      }
      legacyConvertedRef.current = true;
      setPoints((prev) =>
        prev.map((p) =>
          containerNormToVideoNorm(
            p,
            canvas.width,
            canvas.height,
            intrinsic.w,
            intrinsic.h,
          ),
        ),
      );
    };
    requestAnimationFrame(tryConvert);
    return () => {
      alive = false;
    };
  }, [intrinsic.w, intrinsic.h, zonesCoordSpace]);

  const drawList = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = container.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    if (canvas.width !== rect.width || canvas.height !== rect.height) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const contain =
      intrinsic.w > 0 && intrinsic.h > 0
        ? getObjectFitContainRect(
            canvas.width,
            canvas.height,
            intrinsic.w,
            intrinsic.h,
          )
        : { x: 0, y: 0, w: canvas.width, h: canvas.height };

    const toPx = (p: ZonePoint) =>
      videoNormToContainerPixel(p, contain);

    drawPolygon(
      ctx,
      points,
      toPx,
      "rgba(20, 184, 166, 0.3)",
      "#00ffcc",
      "Analiz Bölgesi",
    );

    points.forEach((p, idx) => {
      const { x: cx, y: cy } = toPx(p);
      const isDragging = draggingIdx === idx;

      ctx.shadowBlur = isDragging ? 15 : 10;
      ctx.shadowColor = isDragging ? "#ffffff" : "#00ffcc";

      ctx.fillStyle = isDragging ? "white" : "#00ffcc";
      ctx.beginPath();
      ctx.arc(cx, cy, isDragging ? 10 : 8, 0, Math.PI * 2);
      ctx.fill();

      ctx.shadowBlur = 0;

      ctx.fillStyle = "#000";
      ctx.font = "bold 10px Inter";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText((idx + 1).toString(), cx, cy);
    });

    requestRef.current = requestAnimationFrame(drawList);
  }, [points, draggingIdx, intrinsic.w, intrinsic.h]);

  const drawPolygon = (
    ctx: CanvasRenderingContext2D,
    pts: ZonePoint[],
    toPx: (p: ZonePoint) => { x: number; y: number },
    fillColor: string,
    strokeColor: string,
    label: string,
  ) => {
    if (pts.length === 0) return;

    const p0 = toPx(pts[0]);
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    pts.forEach((p, i) => {
      if (i > 0) {
        const q = toPx(p);
        ctx.lineTo(q.x, q.y);
      }
    });
    ctx.closePath();

    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 4;
    ctx.setLineDash([8, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = strokeColor;
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label.toUpperCase(), p0.x, p0.y - 25);
  };

  useEffect(() => {
    requestRef.current = requestAnimationFrame(drawList);
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [drawList]);

  const getContainForEvent = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return { x: 0, y: 0, w: 1, h: 1 };
    }
    if (intrinsic.w <= 0 || intrinsic.h <= 0) {
      return { x: 0, y: 0, w: canvas.width, h: canvas.height };
    }
    return getObjectFitContainRect(
      canvas.width,
      canvas.height,
      intrinsic.w,
      intrinsic.h,
    );
  }, [intrinsic.w, intrinsic.h]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const contain = getContainForEvent();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hitPx = Math.max(12, Math.min(contain.w, contain.h) * 0.04);
    let foundIdx = -1;
    for (let i = 0; i < points.length; i++) {
      const hp = videoNormToContainerPixel(points[i], contain);
      if (Math.hypot(mx - hp.x, my - hp.y) < hitPx) {
        foundIdx = i;
        break;
      }
    }

    if (foundIdx !== -1) {
      setDraggingIdx(foundIdx);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingIdx === null || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const contain = getContainForEvent();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const vn = containerPixelToVideoNorm(mx, my, contain);

    const newPoints = [...points];
    newPoints[draggingIdx] = { x: vn.x, y: vn.y };
    setPoints(newPoints);
  };

  const handleMouseUp = () => {
    setDraggingIdx(null);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/95 backdrop-blur-3xl rounded-[2rem] overflow-hidden border border-white/10 shadow-2xl animate-fade-in select-none">
      <div className="bg-slate-800/80 p-6 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="bg-brand-teal p-3 rounded-2xl text-white shadow-xl shadow-brand-teal/20">
            <BoxSelect className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-base font-black text-white uppercase italic tracking-tighter">
              Bölge Analiz Editörü
            </h4>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest mt-1">
              Köşeleri sürükleyerek alanı optimize edin
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-3 rounded-2xl bg-white/5 text-white/40 hover:bg-red-500 hover:text-white transition-all duration-300"
        >
          <X className="w-6 h-6" />
        </button>
      </div>

      <div
        ref={containerRef}
        className="flex-1 relative bg-black overflow-hidden"
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {imageUrl && (
          <MjpegCanvas
            src={imageUrl}
            className="absolute inset-0 w-full h-full object-contain opacity-50 grayscale pointer-events-none"
            fps={15} // Editörde yüksek FPS'e gerek yok, network tasarrufu sağlar
            onDimensions={(nw, nh) => {
              setIntrinsic({ w: nw, h: nh });
            }}
          />
        )}
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          className={`absolute inset-0 w-full h-full z-20 ${draggingIdx !== null ? "cursor-grabbing" : "cursor-crosshair"}`}
        />

        {draggingIdx === null && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-30 pointer-events-none px-6 py-3 rounded-full bg-brand-teal/10 border border-brand-teal/20 backdrop-blur-md">
            <p className="text-[9px] font-black text-brand-teal uppercase tracking-[0.3em]">
              Noktaları Tut ve Sürükle
            </p>
          </div>
        )}
      </div>

      <div className="bg-slate-900/95 p-8 border-t border-white/5 flex items-center justify-between">
        <div className="flex gap-8">
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-brand-teal animate-pulse"></span>
            <span className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
              QUADRILATERAL MODE
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest leading-none">
              NORM (video): {points[0]?.x?.toFixed(2) || "0.00"},{" "}
              {points[0]?.y?.toFixed(2) || "0.00"}
            </span>
          </div>
        </div>

        <div className="flex gap-4">
          <button
            onClick={() => setPoints([])}
            className="px-6 py-4 rounded-2xl bg-red-500/10 text-red-500 text-[10px] font-black hover:bg-red-500/20 transition-all uppercase tracking-widest"
          >
            BÖLGEYİ TEMİZLE
          </button>
          <button
            onClick={() => setPoints(defaultPoints)}
            className="px-6 py-4 rounded-2xl bg-white/5 text-white/50 text-[10px] font-black hover:bg-white/10 transition-all uppercase tracking-widest"
          >
            VARSAYILAN
          </button>
          <button
            onClick={() => onSave([points])}
            className="px-12 py-4 rounded-2xl bg-brand-teal text-white text-[10px] font-black uppercase tracking-[0.25em] shadow-xl shadow-brand-teal/30 hover:scale-105 active:scale-95 transition-all"
          >
            BÖLGEYİ ONAYLA
          </button>
        </div>
      </div>
    </div>
  );
}
