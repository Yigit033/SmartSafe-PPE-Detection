import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SmartSafe AI | Dashboard",
  description: "Enterprise PPE Detection Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body
        className={`${inter.className} antialiased bg-slate-950 text-slate-50`}
      >
        <div className="flex min-h-screen">
          <Sidebar />
          {/* Sidebar fix: Always use fixed padding to prevent overlap */}
          <div className="flex-1 pl-[280px]">
            <TopBar />
            <main className="p-8 animate-fade-in max-w-[1600px] mx-auto">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
