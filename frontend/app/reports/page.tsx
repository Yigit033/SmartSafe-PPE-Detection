"use client";

import { useState, useEffect } from "react";

export default function ReportsPage() {
  const [violations, setViolations] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const companyId = "COMP_EE37F274";

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://localhost:4000/company/${companyId}/violations`,
      );
      const data = await response.json();
      if (data.success) {
        setViolations(data.violations);
      }
    } catch (error) {
      console.error("Error fetching reports:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-slate-900 pb-12" lang="tr">
      <section className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex flex-col gap-2">
          <h2 className="text-3xl font-extrabold tracking-tight">
            Analitik Raporlar
          </h2>
          <p className="text-slate-500 font-medium">
            Tesis genelindeki güvenlik ihlalleri ve PPE uyumluluk
            istatistikleri.
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-xl bg-brand-orange px-8 py-3.5 text-xs font-black text-white shadow-xl shadow-brand-orange/20 transition-all hover:bg-brand-orange/90 cursor-pointer">
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          PDF RAPORU İNDİR
        </button>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col min-h-[500px]">
          <div className="bg-brand-teal p-4 flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
              </svg>
              <h4 className="text-sm font-bold tracking-widest uppercase">
                SON GÜVENLİK İHLALLERİ
              </h4>
            </div>
          </div>
          <div className="flex-1 overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50 text-[10px] font-black text-slate-500 uppercase tracking-widest border-b border-slate-100">
                  <th className="px-8 py-5">KAMERA</th>
                  <th className="px-8 py-5">İHLAL TÜRÜ</th>
                  <th className="px-8 py-5">ZAMAN</th>
                  <th className="px-8 py-5 text-right">DETAY</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="px-8 py-20 text-center">
                      <div className="flex flex-col items-center gap-3">
                        <div className="h-8 w-8 border-4 border-slate-200 border-t-brand-teal rounded-full animate-spin"></div>
                        <p className="text-xs font-black text-slate-400 uppercase tracking-widest">
                          Yükleniyor...
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : violations.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-8 py-20 text-center">
                      <p className="text-sm font-bold text-slate-400 italic">
                        Kayıtlı ihlal verisi bulunamadı.
                      </p>
                    </td>
                  </tr>
                ) : (
                  violations.map((v) => (
                    <tr
                      key={v.violation_id}
                      className="group hover:bg-slate-50/50 transition-colors text-slate-900 font-bold uppercase italic text-sm"
                    >
                      <td className="px-8 py-6">{v.camera_id}</td>
                      <td className="px-8 py-6 text-xs text-red-600 font-black">
                        {v.violation_type}
                      </td>
                      <td className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-tight italic">
                        {new Date(v.timestamp).toLocaleString()}
                      </td>
                      <td className="px-8 py-6 text-right">
                        <button className="text-brand-teal hover:underline text-[10px] font-black tracking-widest leading-none cursor-pointer">
                          İNCELE
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <section className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6 border-b border-slate-100 pb-2 italic">
              HAFTALIK ÖZET
            </h5>
            <div className="space-y-6">
              <div>
                <div className="flex justify-between text-xs font-black italic items-center mb-2">
                  <span className="text-slate-500 uppercase">PPE UYUMU</span>
                  <span className="text-emerald-600">92%</span>
                </div>
                <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 w-[92%]"></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs font-black italic items-center mb-2">
                  <span className="text-slate-500 uppercase">
                    KRİTİK İHLALLER
                  </span>
                  <span className="text-red-500">12 ADET</span>
                </div>
                <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-red-500 w-[40%]"></div>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-brand-orange p-8 shadow-xl shadow-brand-orange/20 text-white">
            <h5 className="text-xs font-black uppercase tracking-widest mb-2 italic">
              BİLGİ
            </h5>
            <p className="text-xs font-bold leading-relaxed opacity-90">
              Bu veriler anlık olarak AI motoru tarafından işlenip
              kaydedilmektedir. Raporlama periyodunu ayarlardan
              değiştirebilirsiniz.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
