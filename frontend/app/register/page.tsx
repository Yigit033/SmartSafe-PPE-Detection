"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import api from "@/lib/api";
import { 
  Building2, 
  User, 
  Phone, 
  Mail, 
  MapPin, 
  Factory, 
  ChevronDown, 
  Lock, 
  Eye, 
  EyeOff, 
  Rocket, 
  AlertCircle 
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    company_name: "",
    contact_person: "",
    phone: "",
    email: "",
    address: "",
    sector: "",
    subscription_type: "professional",
    password: "",
  });

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await api.company.create(formData as any);
      router.push("/login?registered=true");
    } catch (err: any) {
      setError(
        err.message || "Kayıt işlemi sırasında bir hata oluştu.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen bg-slate-50 flex items-center justify-center p-4 py-12"
      lang="tr"
    >
      <div className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl overflow-hidden border border-slate-100 animate-fade-in">
        {/* Header */}
        <div className="bg-gradient-to-br from-brand-teal to-brand-teal/80 p-8 text-white text-center">
          <div className="flex justify-center mb-4">
            <div className="bg-white/20 p-3 rounded-2xl backdrop-blur-md">
              <Building2 className="w-8 h-8 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Şirket Kaydı</h1>
          <p className="text-brand-teal-light/80 mt-2">
            SmartSafe AI ile güvenli çalışma alanları oluşturun
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-8 space-y-6">
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-xl flex items-center gap-3 animate-shake">
              <AlertCircle className="w-5 h-5 text-red-500" />
              <p className="text-red-700 text-sm font-medium">{error}</p>
            </div>
          )}

          {/* Subscription Tab Like Selection */}
          <div className="grid grid-cols-2 gap-4 p-1 bg-slate-100 rounded-2xl">
            <button
              type="button"
              onClick={() =>
                setFormData({ ...formData, subscription_type: "starter" })
              }
              className={`py-2 text-sm font-bold rounded-xl transition-all ${
                formData.subscription_type === "starter"
                  ? "bg-white text-brand-teal shadow-md"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Başlangıç
            </button>
            <button
              type="button"
              onClick={() =>
                setFormData({ ...formData, subscription_type: "professional" })
              }
              className={`py-2 text-sm font-bold rounded-xl transition-all ${
                formData.subscription_type === "professional"
                  ? "bg-white text-brand-teal shadow-md"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Profesyonel
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Company Name */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                ŞİRKET ADI *
              </label>
              <div className="relative group">
                <Building2 className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <input
                  required
                  type="text"
                  name="company_name"
                  value={formData.company_name}
                  onChange={handleChange}
                  placeholder="Şirket ismini giriniz"
                  className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
                />
              </div>
            </div>

            {/* Contact Person */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                YETKİLİ KİŞİ *
              </label>
              <div className="relative group">
                <User className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <input
                  required
                  type="text"
                  name="contact_person"
                  value={formData.contact_person}
                  onChange={handleChange}
                  placeholder="Ad Soyad"
                  className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
                />
              </div>
            </div>

            {/* Phone */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                TELEFON
              </label>
              <div className="relative group">
                <Phone className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  placeholder="+90 5xx xxx xx xx"
                  className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
                />
              </div>
            </div>

            {/* E-mail */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                E-POSTA *
              </label>
              <div className="relative group">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <input
                  required
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="ornek@sirket.com"
                  className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
                />
              </div>
            </div>
          </div>

          {/* Address */}
          <div className="space-y-2">
            <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
              ADRES
            </label>
            <div className="relative group">
              <MapPin className="absolute left-4 top-4 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
              <textarea
                name="address"
                value={formData.address}
                onChange={handleChange}
                placeholder="Şirket merkez adresi"
                rows={2}
                className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Industry / Sector */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                SEKTÖR *
              </label>
              <div className="relative group">
                <Factory className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <select
                  required
                  name="sector"
                  value={formData.sector}
                  onChange={handleChange}
                  className="w-full pl-12 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal appearance-none transition-all text-slate-700 cursor-pointer"
                >
                  <option value="">Sektör Seçiniz</option>
                  <option value="construction">İnşaat</option>
                  <option value="manufacturing">İmalat</option>
                  <option value="chemical">Kimya</option>
                  <option value="food">Gıda</option>
                  <option value="warehouse">Lojistik / Depolama</option>
                  <option value="energy">Enerji</option>
                  <option value="petrochemical">Petrokimya</option>
                  <option value="marine">Denizcilik / Tersane</option>
                  <option value="aviation">Havacılık</option>
                </select>
                <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none w-5 h-5" />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-2">
              <label className="text-xs font-black text-slate-400 uppercase tracking-widest px-1">
                ŞİFRE *
              </label>
              <div className="relative group">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-teal transition-colors w-5 h-5" />
                <input
                  required
                  type={showPassword ? "text" : "password"}
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder="••••••••••••"
                  className="w-full pl-12 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-teal/20 focus:border-brand-teal transition-all text-slate-700"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-brand-teal transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="w-5 h-5" />
                  ) : (
                    <Eye className="w-5 h-5" />
                  )}
                </button>
              </div>
            </div>
          </div>

          <button
            disabled={loading}
            type="submit"
            className="w-full py-4 bg-brand-teal hover:bg-brand-teal-dark text-white font-bold rounded-2xl shadow-lg shadow-brand-teal/30 flex items-center justify-center gap-3 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-70 disabled:hover:scale-100"
          >
            {loading ? (
              <div className="h-5 w-5 border-3 border-white/30 border-t-white rounded-full animate-spin"></div>
            ) : (
              <>
                <Rocket className="w-5 h-5" />
                Kayıt Ol & Başlat
              </>
            )}
          </button>

          <div className="text-center pt-2">
            <p className="text-sm text-slate-500">
              Zaten bir hesabınız var mı?{" "}
              <Link
                href="/login"
                className="text-brand-teal font-bold hover:underline"
              >
                Giriş Yap
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
