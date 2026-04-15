import Client, { Local } from "./client";

/**
 * SmartSafe API Configuration
 */
const isLocalhost =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1");

// NEXT_PUBLIC_BACKEND_URL tanımlıysa önceliklidir.
// Geliştirme modunda http://localhost:4477, Üretim (Nginx) modunda /api kullanılır.
const defaultBaseURL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  (process.env.NODE_ENV === "production" 
    ? (typeof window !== "undefined" ? window.location.origin + "/api" : "/api") 
    : Local);

/**
 * Creates a client for API calls.
 */
export function createServerClient(token?: string, baseURL?: string) {
  const targetURL = baseURL || defaultBaseURL;

  // SmartSafe'de şu an için Bearer token yerine session-based veya api-key bazlı
  // bir yapı olabilir. Eğer auth token gerekirse buraya eklenebilir.
  let authToken = token;
  if (!authToken && typeof window !== "undefined") {
    // Sessiondan çekmek istenirse burası güncellenebilir
    // authToken = localStorage.getItem("token") || undefined;
  }

  const options: any = {
    requestInit: {
      headers: {
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
    },
  };

  return new Client(targetURL, options);
}

/**
 * Singleton instance for general use
 */
const api = createServerClient();

export default api;
