/**
 * Analiz bölgeleri: DB'de artık { coord_space, zones } veya eski düz dizi.
 * Video uzayı (0–1) = object-fit: contain ile görünen piksel dikdörtgeni.
 */

export type ZonePoint = { x: number; y: number };

export type DetectionZonesCoordSpace = "video" | "container";

export function normalizeDetectionZonesPayload(raw: unknown): {
  polygons: ZonePoint[][];
  coordSpace: DetectionZonesCoordSpace;
} {
  if (raw == null) {
    return { polygons: [], coordSpace: "video" };
  }
  if (typeof raw === "object" && raw !== null && !Array.isArray(raw)) {
    const o = raw as { coord_space?: string; zones?: unknown };
    if (Array.isArray(o.zones)) {
      const cs = o.coord_space === "video" ? "video" : "container";
      return { polygons: o.zones as ZonePoint[][], coordSpace: cs };
    }
  }
  if (Array.isArray(raw)) {
    return { polygons: raw as ZonePoint[][], coordSpace: "container" };
  }
  return { polygons: [], coordSpace: "video" };
}

/** CSS object-fit: contain ile aynı içerik dikdörtgeni */
export function getObjectFitContainRect(
  containerW: number,
  containerH: number,
  intrinsicW: number,
  intrinsicH: number,
): { x: number; y: number; w: number; h: number } {
  if (
    containerW <= 0 ||
    containerH <= 0 ||
    intrinsicW <= 0 ||
    intrinsicH <= 0
  ) {
    return { x: 0, y: 0, w: Math.max(containerW, 1), h: Math.max(containerH, 1) };
  }
  const scale = Math.min(containerW / intrinsicW, containerH / intrinsicH);
  const w = intrinsicW * scale;
  const h = intrinsicH * scale;
  const x = (containerW - w) / 2;
  const y = (containerH - h) / 2;
  return { x, y, w, h };
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

/** Tam konteyner pikseli → video normalize (içerik kutusuna göre) */
export function containerPixelToVideoNorm(
  px: number,
  py: number,
  rect: { x: number; y: number; w: number; h: number },
): ZonePoint {
  if (rect.w <= 0 || rect.h <= 0) {
    return { x: 0, y: 0 };
  }
  return {
    x: clamp01((px - rect.x) / rect.w),
    y: clamp01((py - rect.y) / rect.h),
  };
}

/** Video normalize → konteyner pikseli (canvas çizimi için) */
export function videoNormToContainerPixel(
  p: ZonePoint,
  rect: { x: number; y: number; w: number; h: number },
): { x: number; y: number } {
  return {
    x: rect.x + clamp01(p.x) * rect.w,
    y: rect.y + clamp01(p.y) * rect.h,
  };
}

/** Eski (konteyner 0–1) noktayı video 0–1'e çevir */
export function containerNormToVideoNorm(
  p: ZonePoint,
  containerW: number,
  containerH: number,
  intrinsicW: number,
  intrinsicH: number,
): ZonePoint {
  const rect = getObjectFitContainRect(
    containerW,
    containerH,
    intrinsicW,
    intrinsicH,
  );
  const px = p.x * containerW;
  const py = p.y * containerH;
  return containerPixelToVideoNorm(px, py, rect);
}

/** Önizleme SVG’si için: eski konteyner-normalize poligonu video 0–1’e çevirir. */
export function polygonToVideoSpaceForOverlay(
  poly: ZonePoint[],
  coordSpace: DetectionZonesCoordSpace,
  containerW: number,
  containerH: number,
  natW: number,
  natH: number,
): ZonePoint[] {
  if (
    coordSpace !== "container" ||
    containerW <= 0 ||
    containerH <= 0 ||
    natW <= 0 ||
    natH <= 0
  ) {
    return poly;
  }
  return poly.map((p) =>
    containerNormToVideoNorm(p, containerW, containerH, natW, natH),
  );
}
