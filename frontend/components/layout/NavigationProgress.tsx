"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

/**
 * Thin progress bar at the top of the page that shows during navigation.
 * Automatically appears when pathname changes and fades out after page renders.
 */
export default function NavigationProgress() {
  const pathname = usePathname();
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevPathname = useRef(pathname);

  useEffect(() => {
    // Sayfa değiştiğinde bar'ı bitir
    if (prevPathname.current !== pathname) {
      prevPathname.current = pathname;
      
      if (timerRef.current) clearInterval(timerRef.current);
      
      setProgress(100);
      
      // Kısa bir süre bekleyip bar'ı gizle
      const timeout = setTimeout(() => {
        setVisible(false);
        // Bar görünmez olduktan sonra sıfırla ki geri giderken görünmesin
        setTimeout(() => setProgress(0), 200);
      }, 300);
      
      return () => clearTimeout(timeout);
    }
  }, [pathname]);

  useEffect(() => {
    const handler = () => {
      if (timerRef.current) clearInterval(timerRef.current);
      
      setVisible(true);
      setProgress(5); // %5 ile başla

      let current = 5;
      timerRef.current = setInterval(() => {
        // Gerçekçi bir "tın tın" ilerleme - hedefe yaklaştıkça yavaşlar
        // 0.05 katsayısı daha yumuşak bir akış sağlar
        const increment = (95 - current) * 0.05;
        current += increment;
        
        setProgress(current);
      }, 200); // 200ms aralıklarla güncelle
    };

    window.addEventListener("navigation:start", handler);
    return () => {
      window.removeEventListener("navigation:start", handler);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className="fixed top-0 left-0 z-[9999] h-[3px] bg-brand-teal transition-all duration-300 ease-out"
      style={{
        width: `${progress}%`,
        boxShadow: progress < 100 ? "0 0 10px rgba(20, 184, 166, 0.5)" : "none",
        opacity: progress >= 100 ? 0 : 1, // Bittiğinde yavaşça silin
      }}
    />
  );
}
