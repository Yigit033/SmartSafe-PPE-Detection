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
    <header
      className="sticky top-0 z-30 flex h-16 w-full items-center justify-between px-8 bg-white/80 backdrop-blur-md border-b border-slate-200"
      lang="tr"
    >
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-black tracking-[0.2em] text-slate-800">
          <span className="text-brand-teal mr-2">//</span>
          {getPageTitle()}
        </h1>
      </div>

      <div className="flex items-center gap-6">
        <button className="relative rounded-xl bg-slate-100 p-2 text-slate-500 hover:text-slate-900 transition-all border border-slate-200 cursor-pointer">
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
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"></span>
        </button>

        <div className="flex items-center gap-4 pl-6 border-l border-slate-200">
          <div className="text-right hidden sm:block">
            <p className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              SmartSafe Demo
            </p>
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest leading-none mt-1">
              Administrator
            </p>
          </div>
          <div className="h-9 w-9 overflow-hidden rounded-xl bg-brand-teal p-[1px] shadow-sm">
            <div className="flex h-full w-full items-center justify-center rounded-[10px] bg-white text-xs font-black text-brand-teal">
              SD
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
