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
      <body className={`${inter.className} antialiased`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-[--sidebar-width] transition-all duration-300">
            <TopBar />
            <div className="p-8 animate-fade-in">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
