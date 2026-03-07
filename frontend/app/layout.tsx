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
  const [isReady, setIsReady] = useState(false);
  const isPublicPage = pathname === "/login" || pathname === "/register";

  useEffect(() => {
    const user = localStorage.getItem("user");
    if (!user && !isPublicPage) {
      router.push("/login");
    } else if (user && isPublicPage) {
      router.push("/");
    } else {
      setIsReady(true);
    }
  }, [isPublicPage, router]);

  if (!isReady && !isPublicPage) {
    return (
      <html lang="tr">
        <body
          className={`${inter.className} bg-slate-50 flex items-center justify-center min-h-screen`}
        >
          <div className="flex flex-col items-center gap-4">
            <div className="h-12 w-12 border-4 border-brand-teal border-t-transparent rounded-full animate-spin"></div>
            <p className="text-slate-400 font-black text-xs uppercase tracking-widest">
              Sistem Yükleniyor...
            </p>
          </div>
        </body>
      </html>
    );
  }

  return (
    <html lang="tr">
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
        />
        <title>SmartSafe AI | Dashboard</title>
      </head>
      <body
        className={`${inter.className} antialiased bg-slate-50 text-slate-900`}
      >
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
      </body>
    </html>
  );
}
