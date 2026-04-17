"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { 
  LayoutDashboard, 
  Camera, 
  ShieldAlert, 
  BarChart3, 
  Users, 
  Settings, 
  LogOut,
  ShieldCheck
} from "lucide-react";

const menuItems = [
  {
    name: "Dashboard",
    icon: LayoutDashboard,
    path: "/",
  },
  {
    name: "Kameralar",
    icon: Camera,
    path: "/cameras",
  },
  {
    name: "İhlaller",
    icon: ShieldAlert,
    path: "/violations",
  },
  {
    name: "Raporlar",
    icon: BarChart3,
    path: "/reports",
  },
  {
    name: "Kullanıcılar",
    icon: Users,
    path: "/users",
  },
  {
    name: "Ayarlar",
    icon: Settings,
    path: "/settings",
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    localStorage.removeItem("user");
    router.push("/login");
  };

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-[280px] border-r border-slate-200 bg-slate-50 p-6 transition-colors duration-300">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="mb-10 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-teal text-white shadow-lg shadow-brand-teal/30">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-900">
            SmartSafe AI
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1">
          {menuItems.map((item) => {
            const isActive = pathname === item.path;
            const Icon = item.icon;
            
            const className = `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition-all cursor-pointer ${
              isActive
                ? "bg-brand-teal/10 text-brand-teal"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            }`;
            
            return (
              <Link
                key={item.path}
                href={item.path}
                className={className}
              >
                <Icon className={`h-5 w-5 ${isActive ? "text-brand-teal" : "text-slate-400"}`} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Bottom Menu */}
        <div className="mt-auto border-t border-slate-200 pt-6" lang="tr">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold text-slate-500 hover:bg-red-50 hover:text-red-600 transition-all cursor-pointer"
          >
            <LogOut className="h-5 w-5 text-slate-400 group-hover:text-red-600" />
            Çıkış Yap
          </button>
        </div>
      </div>
    </aside>
  );
}
