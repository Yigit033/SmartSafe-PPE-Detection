/**
 * Kamera listesi (/cameras) için tam sayfa geçişi.
 * SPA önbelleği + MJPEG/img ilk yükleme sorunlarında pagination ile aynı etkiyi verir.
 */
export function goToCamerasPage(): void {
  if (typeof window === "undefined") return;
  window.location.assign("/cameras");
}
