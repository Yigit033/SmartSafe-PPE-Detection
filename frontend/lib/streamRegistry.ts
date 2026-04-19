/**
 * Global MJPEG stream registry.
 * Allows any component (e.g. Sidebar) to abort ALL active streams
 * before navigating — prevents browser connection limit blocking navigation.
 */
const controllers = new Set<AbortController>();

export function registerStream(controller: AbortController) {
  controllers.add(controller);
}

export function unregisterStream(controller: AbortController) {
  controllers.delete(controller);
}

export function abortAllStreams() {
  controllers.forEach((ctrl) => {
    try { ctrl.abort(); } catch {}
  });
  controllers.clear();
}
