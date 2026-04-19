import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Birden fazla lockfile (ör. kullanıcı profilinde package-lock.json) varken Next yanlış kök seçip
  // frontend/node_modules içindeki paketleri (lucide-react vb.) çözemeyebilir.
  outputFileTracingRoot: path.join(process.cwd()),
  output: "standalone",
  devIndicators: false,
  webpack: (config, { dev }) => {
    // Modül çözümlemesini önce bu projenin node_modules'ına yönlendir (üst dizin lockfile kaynaklı sapmaya karşı).
    if (!config.resolve) {
      config.resolve = {};
    }
    config.resolve.modules = [
      path.join(process.cwd(), "node_modules"),
      "node_modules",
    ];
    if (dev) {
      config.watchOptions = {
        poll: 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
};

export default nextConfig;
