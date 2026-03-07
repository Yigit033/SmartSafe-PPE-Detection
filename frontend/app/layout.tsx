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
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
        />
      </head>
      <body
        className={`${inter.className} antialiased bg-slate-50 text-slate-900`}
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
