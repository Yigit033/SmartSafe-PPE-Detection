"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";

interface Point {
  x: number;
  y: number;
}

interface ZoneDesignerProps {
  imageUrl: string;
  initialZones?: Point[][];
  onSave: (zones: Point[][]) => void;
  onClose: () => void;
}

export default function ZoneDesigner({
  imageUrl,
  initialZones = [],
  onSave,
  onClose,
}: ZoneDesignerProps) {
  // Varsayılan olarak ekranın ortasında 4 nokta (bir karesel alan) ile başlatıyoruz
  const defaultPoints: Point[] = [
    { x: 0.2, y: 0.2 },
    { x: 0.8, y: 0.2 },
    { x: 0.8, y: 0.8 },
    { x: 0.2, y: 0.8 },
  ];

  // Eğer mevcut bir bölge varsa onu yükle, yoksa default 4 noktayı kullan
  const [points, setPoints] = useState<Point[]>(() => {
    if (
      initialZones &&
      initialZones.length > 0 &&
      initialZones[0] &&
      initialZones[0].length > 0
    ) {
      return initialZones[0];
    }
    return defaultPoints;
  });

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<number | null>(null);

  // Çizim Fonksiyonu
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

    // Ana Çokgeni Çiz
    drawPolygon(
      ctx,
      points,
      "rgba(20, 184, 166, 0.3)",
      "#00ffcc",
      "Analiz Bölgesi",
    );

    // Tutma Noktalarını (Handles) Çiz
    points.forEach((p, idx) => {
      const isDragging = draggingIdx === idx;

      // Gölge ve Glow Efekti
      ctx.shadowBlur = isDragging ? 15 : 10;
      ctx.shadowColor = isDragging ? "#ffffff" : "#00ffcc";

      // Dış Halka
      ctx.fillStyle = isDragging ? "white" : "#00ffcc";
      ctx.beginPath();
      ctx.arc(
        p.x * canvas.width,
        p.y * canvas.height,
        isDragging ? 10 : 8,
        0,
        Math.PI * 2,
      );
      ctx.fill();

      ctx.shadowBlur = 0;

      // İç Sayı/İndikatör
      ctx.fillStyle = "#000";
      ctx.font = "bold 10px Inter";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        (idx + 1).toString(),
        p.x * canvas.width,
        p.y * canvas.height,
      );
    });

    requestRef.current = requestAnimationFrame(drawList);
  }, [points, draggingIdx]);

  const drawPolygon = (
    ctx: CanvasRenderingContext2D,
    pts: Point[],
    fillColor: string,
    strokeColor: string,
    label: string,
  ) => {
    if (pts.length === 0) return;
    const w = canvasRef.current!.width;
    const h = canvasRef.current!.height;

    ctx.beginPath();
    ctx.moveTo(pts[0].x * w, pts[0].y * h);
    pts.forEach((p, i) => {
      if (i > 0) ctx.lineTo(p.x * w, p.y * h);
    });
    ctx.closePath();

    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 4;
    ctx.setLineDash([8, 4]); // Modern kesikli çizgi
    ctx.stroke();
    ctx.setLineDash([]);

    // Etiket
    ctx.fillStyle = strokeColor;
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label.toUpperCase(), pts[0].x * w, pts[0].y * h - 25);
  };

  useEffect(() => {
    requestRef.current = requestAnimationFrame(drawList);
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [drawList]);

  // Sürükleme Olayları
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left) / rect.width;
    const mouseY = (e.clientY - rect.top) / rect.height;

    // Tıklanan noktayı bul (Eşik değer %5 mesafe)
    const threshold = 0.05;
    const foundIdx = points.findIndex((p) => {
      const dist = Math.sqrt(
        Math.pow(p.x - mouseX, 2) + Math.pow(p.y - mouseY, 2),
      );
      return dist < threshold;
    });

    if (foundIdx !== -1) {
      setDraggingIdx(foundIdx);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingIdx === null || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();

    // Sınırları kontrol et (0-1 arası)
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));

    const newPoints = [...points];
    newPoints[draggingIdx] = { x, y };
    setPoints(newPoints);
  };

  const handleMouseUp = () => {
    setDraggingIdx(null);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/95 backdrop-blur-3xl rounded-[3rem] overflow-hidden border border-white/10 shadow-2xl animate-fade-in select-none">
      {/* Header */}
      <div className="bg-slate-800/80 p-6 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="bg-brand-teal p-3 rounded-2xl text-white shadow-xl shadow-brand-teal/20">
            <span className="material-symbols-rounded text-2xl">crop_free</span>
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
          <span className="material-symbols-rounded">close</span>
        </button>
      </div>

      {/* Editor Space */}
      <div
        ref={containerRef}
        className="flex-1 relative bg-black overflow-hidden"
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {imageUrl && (
          <img
            src={imageUrl}
            alt="Stream"
            className="absolute inset-0 w-full h-full object-contain opacity-50 grayscale pointer-events-none"
          />
        )}
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          className={`absolute inset-0 w-full h-full z-20 ${draggingIdx !== null ? "cursor-grabbing" : "cursor-crosshair"}`}
        />

        {/* Helper Overlay */}
        {draggingIdx === null && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-30 pointer-events-none px-6 py-3 rounded-full bg-brand-teal/10 border border-brand-teal/20 backdrop-blur-md">
            <p className="text-[9px] font-black text-brand-teal uppercase tracking-[0.3em]">
              Noktaları Tut ve Sürükle
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
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
              NORM: {points[0]?.x?.toFixed(2) || "0.00"},{" "}
              {points[0]?.y?.toFixed(2) || "0.00"}
            </span>
          </div>
        </div>

        <div className="flex gap-4">
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
