"use client";

import type { ZonePoint } from "@/lib/detectionZones";

type Props = {
  /** İlk poligon; koordinatlar video uzayında 0–1 */
  polygon: ZonePoint[];
  /** img naturalWidth / naturalHeight; 0 ise overlay çizilmez */
  naturalW: number;
  naturalH: number;
  className?: string;
};

/**
 * object-contain ile aynı hizalama: viewBox video en-boy oranında, xMidYMid meet.
 */
export default function VideoRoiOverlay({
  polygon,
  naturalW,
  naturalH,
  className = "",
}: Props) {
  if (
    polygon.length < 3 ||
    naturalW <= 0 ||
    naturalH <= 0 ||
    !Number.isFinite(naturalW) ||
    !Number.isFinite(naturalH)
  ) {
    return null;
  }

  const pts = polygon.map((p) => `${p.x * naturalW},${p.y * naturalH}`).join(" ");

  return (
    <svg
      className={`pointer-events-none ${className}`}
      width="100%"
      height="100%"
      viewBox={`0 0 ${naturalW} ${naturalH}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <polygon
        points={pts}
        fill="rgba(20, 184, 166, 0.15)"
        stroke="#14b8a6"
        strokeWidth={Math.max(2, naturalW * 0.002)}
        strokeDasharray={`${naturalW * 0.02} ${naturalW * 0.01}`}
      />
      {polygon.map((p, idx) => (
        <circle
          key={idx}
          cx={p.x * naturalW}
          cy={p.y * naturalH}
          r={Math.max(3, naturalW * 0.006)}
          fill="#14b8a6"
        />
      ))}
    </svg>
  );
}
