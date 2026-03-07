"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (searchParams.get("registered") === "true") {
      setSuccess("Kayıt işleminiz başarıyla tamamlandı. Giriş yapabilirsiniz.");
    }
  }, [searchParams]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch("http://localhost:4000/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const result = await response.json();

      if (result.success) {
        localStorage.setItem("user", JSON.stringify(result.user));
        router.push("/");
      } else {
        setError(
          result.error || "Giriş başarısız. Bilgilerinizi kontrol edin.",
        );
      }
    } catch (err) {
      setError("Bağlantı hatası oluştu. Lütfen tekrar deneyin.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md w-full animate-fade-in">
      {/* Brand area */}
      <div className="text-center mb-8">
        <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-teal text-white shadow-lg shadow-brand-teal/20 mb-4 font-black">
          <svg
            className="h-10 w-10"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2.5}
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
        </div>
        <h1 className="text-4xl font-black text-slate-900 tracking-tight">
          Smart<span className="text-brand-teal">Safe</span>
        </h1>
        <p className="text-slate-500 font-bold mt-2 uppercase tracking-widest text-xs">
          Yapay Zeka Destekli İş Güvenliği
        </p>
      </div>

      <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-xl shadow-slate-200/50 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-brand-teal/5 rounded-full -mr-16 -mt-16 blur-2xl"></div>
        <div className="absolute bottom-0 left-0 w-32 h-32 bg-brand-orange/5 rounded-full -ml-16 -mb-16 blur-2xl"></div>

        <form onSubmit={handleLogin} className="space-y-6 relative">
          {success && (
            <div className="bg-emerald-50 border border-emerald-100 text-emerald-600 px-4 py-3 rounded-xl text-xs font-bold leading-relaxed flex items-center gap-2">
              <span className="material-symbols-rounded text-sm">
                check_circle
              </span>
              {success}
            </div>
          )}

          <div>
            <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2 ml-1">
              E-POSTA ADRESİ
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ornek@sirket.com"
              className="w-full px-5 py-4 bg-slate-50 border border-slate-100 rounded-2xl focus:ring-4 focus:ring-brand-teal/10 focus:border-brand-teal outline-none transition-all font-semibold text-slate-900 placeholder:text-slate-300"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-2 ml-1">
              <label className="block text-xs font-black text-slate-400 uppercase tracking-widest">
                ŞİFRE
              </label>
              <a
                href="#"
                className="text-[10px] font-bold text-brand-teal hover:text-teal-700 transition-colors uppercase underline underline-offset-2"
              >
                Şifremi Unuttum
              </a>
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-5 py-4 pr-14 bg-slate-50 border border-slate-100 rounded-2xl focus:ring-4 focus:ring-brand-teal/10 focus:border-brand-teal outline-none transition-all font-semibold text-slate-900 placeholder:text-slate-300"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-brand-teal transition-colors"
              >
                <span className="material-symbols-rounded text-[20px]">
                  {showPassword ? "visibility_off" : "visibility"}
                </span>
              </button>
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 px-4 py-3 rounded-xl text-xs font-bold flex items-center gap-2 tracking-tight">
              <span className="material-symbols-rounded text-sm">error</span>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-slate-900 hover:bg-black text-white py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-slate-900/10 disabled:opacity-70 group"
          >
            <span className="flex items-center justify-center gap-2">
              {loading ? (
                <div className="animate-spin h-5 w-5 border-3 border-white/30 border-t-white rounded-full"></div>
              ) : (
                <>
                  SİSTEME GİRİŞ YAP{" "}
                  <span className="material-symbols-rounded text-lg group-hover:translate-x-1 transition-transform">
                    arrow_forward
                  </span>
                </>
              )}
            </span>
          </button>

          <div className="text-center pt-2">
            <p className="text-sm text-slate-500 font-medium">
              Henüz bir hesabınız yok mu?{" "}
              <Link
                href="/register"
                className="text-brand-teal font-black hover:underline underline-offset-4 tracking-tight"
              >
                Şimdi Ücretsiz Kayıt Ol
              </Link>
            </p>
          </div>
        </form>
      </div>

      <p className="text-center text-slate-400 text-[10px] font-bold mt-8 uppercase tracking-[0.2em]">
        © 2026 SmartSafe AI Security • v2.1.0 Enterprise
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div
      className="min-h-screen bg-slate-50 flex items-center justify-center p-4"
      lang="tr"
    >
      <Suspense
        fallback={
          <div className="animate-pulse flex flex-col items-center gap-4">
            <div className="h-12 w-12 border-4 border-brand-teal border-t-transparent rounded-full animate-spin"></div>
            <p className="text-slate-400 font-black text-xs uppercase tracking-widest">
              Sayfa Yükleniyor...
            </p>
          </div>
        }
      >
        <LoginContent />
      </Suspense>
    </div>
  );
}
