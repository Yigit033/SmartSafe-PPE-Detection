/**
 * Global MJPEG stream registry.
 * Allows any component (e.g. Sidebar) to abort ALL active streams
 * before navigating — prevents browser connection limit blocking navigation.
 */
const controllers = new Set<AbortController>();
const activeStreamUrls = new Set<string>();

export function registerStream(controller: AbortController, url?: string) {
  controllers.add(controller);
  if (url) activeStreamUrls.add(url);
}

export function unregisterStream(controller: AbortController, url?: string) {
  controllers.delete(controller);
  if (url) activeStreamUrls.delete(url);
}

export function abortAllStreams() {
  controllers.forEach((ctrl) => {
    try { ctrl.abort(); } catch {}
  });
  controllers.clear();
  activeStreamUrls.clear();
}

/** Core'a aktif stream'leri durdurmasını söyler (fire-and-forget). AI analizi etkilenmez. */
export function notifyCoreToStopStreams(coreBaseUrl: string, companyId: string) {
  if (!companyId || !coreBaseUrl) return;
  try {
    navigator.sendBeacon(
      `${coreBaseUrl}/api/company/${companyId}/cameras/stop-streams`,
      new Blob([JSON.stringify({})], { type: 'application/json' })
    );
  } catch {
    // sendBeacon başarısız olursa sessizce geç — fetch zaten abort edildi
  }
}
