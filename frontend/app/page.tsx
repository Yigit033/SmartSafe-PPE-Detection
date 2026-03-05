const stats = [
  {
    name: "Aktif Kameralar",
    value: "24 / 25",
    icon: "video",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    name: "PPE Uyum Oranı",
    value: "98.2%",
    icon: "shield",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
  },
  {
    name: "Günlük İhlaller",
    value: "12",
    icon: "warning",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  {
    name: "İşlenen Görüntü",
    value: "1.2M",
    icon: "cpu",
    color: "text-purple-400",
    bg: "bg-purple-500/10",
  },
];

export default function Home() {
  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header Info */}
      <section className="flex flex-col gap-1">
        <h2 className="text-3xl font-bold tracking-tight text-white drop-shadow-sm">
          Hoş Geldiniz, SmartSafe Demo
        </h2>
        <p className="text-slate-400">
          Bugün tesisinizdeki güvenlik durumu stabil görünüyor.
        </p>
      </section>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="group card-glow overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 p-6 transition-all duration-300"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">
                  {stat.name}
                </p>
                <h3 className="mt-2 text-3xl font-bold text-white tracking-tight">
                  {stat.value}
                </h3>
              </div>
              <div
                className={`${stat.bg} flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-500 group-hover:scale-110 group-hover:rotate-6`}
              >
                <span className={`text-2xl ${stat.color}`}>
                  {stat.icon === "video" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                      />
                    </svg>
                  )}
                  {stat.icon === "shield" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                      />
                    </svg>
                  )}
                  {stat.icon === "warning" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                  )}
                  {stat.icon === "cpu" && (
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
                      />
                    </svg>
                  )}
                </span>
              </div>
            </div>
            <div className="mt-6 flex items-center gap-3">
              <span className="flex items-center gap-1 text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
                <svg
                  className="h-3 w-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 10l7-7m0 0l7 7m-7-7v18"
                  />
                </svg>
                12%
              </span>
              <span className="text-xs font-medium text-slate-500">
                geçen haftaya göre
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* Main Analytics Placeholder */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/50 p-8 card-glow transition-all">
          <div className="mb-8 flex items-center justify-between">
            <h4 className="text-lg font-bold text-white italic tracking-wide">
              GÜVENLİK TRENDİ
            </h4>
            <div className="flex items-center gap-2 rounded-xl bg-slate-950 p-1.5 border border-slate-800">
              <button className="rounded-lg px-4 py-1.5 text-xs font-bold bg-primary-600 text-white shadow-lg shadow-primary-500/20">
                Haftalık
              </button>
              <button className="rounded-lg px-4 py-1.5 text-xs font-bold text-slate-500 hover:text-slate-300">
                Aylık
              </button>
            </div>
          </div>
          <div className="flex h-[320px] items-center justify-center rounded-2xl bg-slate-950/40 border border-dashed border-slate-800">
            <p className="text-sm italic text-slate-500 animate-pulse text-center leading-relaxed">
              Analitik grafik motoru başlatılıyor...
              <br />
              <span className="text-xs opacity-50">v2.0.4-stable</span>
            </p>
          </div>
        </section>

        {/* Recent Activity */}
        <section className="rounded-3xl border border-slate-800 bg-slate-900/50 p-8 card-glow transition-all">
          <h4 className="mb-8 text-lg font-bold text-white italic tracking-wide uppercase">
            Son Etkinlikler
          </h4>
          <div className="space-y-8">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="group relative flex gap-6">
                <div className="flex flex-col items-center">
                  <div
                    className={`h-4 w-4 shrink-0 rounded-full ${i % 2 === 0 ? "bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.6)]" : "bg-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.6)]"}`}
                  ></div>
                  {i < 4 && (
                    <div className="mt-2 h-full w-0.5 bg-gradient-to-b from-slate-700 to-transparent"></div>
                  )}
                </div>
                <div className="space-y-2 pb-6">
                  <p className="text-sm font-bold text-slate-100 group-hover:text-white transition-colors">
                    {i % 2 === 0
                      ? "KKD İhlali Tespit Edildi"
                      : "Kamera Bağlantısı Kontrol Edildi"}
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {i % 2 === 0
                      ? "Kamera #4 - B Bölgesi - Baretsiz Giriş Algılandı. Sorumluya bildirim gönderildi."
                      : "Sistem AI motoru tarafından rutin kontrol gerçekleştirildi. 0.02ms gecikme."}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase font-black text-slate-500 tracking-[0.2em]">
                      {i * 10} DAKİKA ÖNCE
                    </span>
                    <span className="h-1 w-1 rounded-full bg-slate-600"></span>
                    <span className="text-[10px] font-bold text-primary-400">
                      LOG-04{i}X
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <button className="mt-4 w-full rounded-2xl border border-slate-800 bg-slate-950/50 py-4 text-xs font-black uppercase tracking-widest text-slate-500 transition-all hover:bg-slate-900 hover:text-white hover:border-slate-700">
            Tüm Etkinliği Görüntüle
          </button>
        </section>
      </div>
    </div>
  );
}
