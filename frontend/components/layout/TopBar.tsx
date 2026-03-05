"use client";

import { usePathname } from "next/navigation";

export default function TopBar() {
  const pathname = usePathname();

  const getPageTitle = () => {
    switch (pathname) {
      case "/":
        return "GENEL BAKIŞ";
      case "/cameras":
        return "KAMERA YÖNETİMİ";
      case "/users":
        return "KULLANICI YÖNETİMİ";
      case "/reports":
        return "ANALİTİK RAPORLAR";
      case "/settings":
        return "SİSTEM AYARLARI";
      default:
        return "DASHBOARD";
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between px-8 glass-effect">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-black tracking-[0.2em] text-white/90">
          <span className="text-primary-500 mr-2">//</span>
          {getPageTitle()}
        </h1>
      </div>

      <div className="flex items-center gap-6">
        <button className="relative rounded-xl bg-white/5 p-2 text-slate-400 hover:text-white transition-all border border-white/5">
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>
        </button>

        <div className="flex items-center gap-4 pl-6 border-l border-white/10">
          <div className="text-right hidden sm:block">
            <p className="text-xs font-bold text-white uppercase tracking-wider">
              SmartSafe Demo
            </p>
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">
              Administrator
            </p>
          </div>
          <div className="h-9 w-9 overflow-hidden rounded-xl bg-primary-600 p-[1px] shadow-lg shadow-primary-500/20">
            <div className="flex h-full w-full items-center justify-center rounded-[10px] bg-slate-950 text-xs font-black text-white">
              SD
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
