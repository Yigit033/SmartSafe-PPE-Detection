/**
 * Kullanıcı oturumu ile ilgili yardımcı fonksiyonlar
 */

export interface UserSession {
  user_id: string;
  company_id: string;
  username: string;
  email: string;
  role: string;
  status: string;
}

/**
 * localStorage'dan oturum açmış kullanıcıyı döndürür
 */
export function getUser(): UserSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("user");
    if (!raw) return null;
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

/**
 * Oturum açmış kullanıcının company_id'sini döndürür
 */
export function getCompanyId(): string {
  const user = getUser();
  return user?.company_id || "";
}
