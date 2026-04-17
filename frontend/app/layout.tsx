"use client";

import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const inter = Inter({ subsets: ["latin"] });

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const router = useRouter();
  // Hydration safety:
  // - We avoid rendering auth-gated UI until after mount so server/client first paint match.
  // - Browser extensions (e.g. Grammarly) may inject attributes into <body>, so we suppress warnings there.
  const [mounted, setMounted] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const isPublicPage = pathname === "/login" || pathname === "/register";

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const user = localStorage.getItem("user");
    if (!user && !isPublicPage) {
      router.push("/login");
    } else if (user && isPublicPage) {
      router.push("/");
    } else {
      setIsReady(true);
    }
  }, [isPublicPage, mounted, router]);

  // Render content based on readiness
  const renderContent = () => {
    // Until mounted, render a stable shell to prevent hydration mismatch.
    if (!mounted) {
      return (
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 border-4 border-brand-teal border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-400 font-black text-xs uppercase tracking-widest">
            Sistem Yükleniyor...
          </p>
        </div>
      );
    }

    if (!isReady && !isPublicPage) {
      return (
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 border-4 border-brand-teal border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-400 font-black text-xs uppercase tracking-widest">
            Sistem Yükleniyor...
          </p>
        </div>
      );
    }

    return (
      <div className="flex min-h-screen">
        {!isPublicPage && <Sidebar />}
        <div className={isPublicPage ? "flex-1 w-full" : "flex-1 pl-[280px]"}>
          {!isPublicPage && <TopBar />}
          <main
            className={
              isPublicPage
                ? "w-full min-h-screen"
                : "p-8 animate-fade-in w-full text-slate-900"
              }
          >
            {children}
          </main>
        </div>
      </div>
    );
  };

  return (
    <html lang="tr" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"
          rel="stylesheet"
        />
        <title>SmartSafe AI | Dashboard</title>
      </head>
      <body
        suppressHydrationWarning
        className={`${inter.className} ${!mounted || (!isReady && !isPublicPage) ? "bg-slate-50 flex items-center justify-center min-h-screen" : "antialiased bg-slate-50 text-slate-900"}`}
      >
        {renderContent()}
      </body>
    </html>
  );
}
