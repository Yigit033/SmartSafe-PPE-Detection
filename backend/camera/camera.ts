import { api } from "encore.dev/api";

interface CameraTestParams {
  name: string;
  ip_address: string;
  port: number;
  username?: string;
  password?: string;
  protocol: string;
  stream_path: string;
}

interface CameraTestResponse {
  success: boolean;
  message: string;
  test_results?: any;
}

/**
 * Kamera bağlantısını test eder (Python Core üzerinden)
 */
export const test = api(
  { expose: true, method: "POST", path: "/cameras/test" },
  async (params: CameraTestParams): Promise<CameraTestResponse> => {
    try {
      const companyId = "demo";
      const response = await fetch(
        `http://localhost:5000/api/company/${companyId}/cameras/test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        },
      );

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as {
          message?: string;
        };
        return {
          success: false,
          message:
            errorData.message ||
            "Python Core test isteğine olumsuz yanıt verdi.",
        };
      }

      const data = (await response.json()) as CameraTestResponse;
      return data;
    } catch (error) {
      return {
        success: false,
        message:
          "Python Core servisine ulaşılamadı. Python uygulamasının (app.py) çalıştığından emin olun.",
      };
    }
  },
);

interface ManualTestResponse {
  success: boolean;
  message: string;
  test_results?: any;
  image_base64?: string;
}

interface DiscoverResponse {
  success: boolean;
  message: string;
  cameras?: any[];
}

/**
 * Kapsamlı kamera testi (Bağlantı + Görüntü + AI)
 */
export const manualTest = api(
  { expose: true, method: "POST", path: "/cameras/manual-test" },
  async (params: CameraTestParams): Promise<ManualTestResponse> => {
    console.log("🚀 Manual Test başlatılıyor...", params.ip_address);
    try {
      const companyId = "demo";
      const response = await fetch(
        `http://localhost:5000/api/company/${companyId}/cameras/manual-test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        },
      );
      console.log("📥 Python Core yanıt verdi:", response.status);
      const data = (await response.json()) as ManualTestResponse;
      return data;
    } catch (error) {
      console.error("❌ Manual Test hatası:", error);
      return { success: false, message: "Kapsamlı test başlatılamadı." };
    }
  },
);

/**
 * Mevcut ağdaki kameraları tarar
 */
export const discover = api(
  { expose: true, method: "POST", path: "/cameras/discover" },
  async (params: { network_range: string }): Promise<DiscoverResponse> => {
    try {
      const companyId = "demo";
      const response = await fetch(
        `http://localhost:5000/api/company/${companyId}/cameras/discover`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        },
      );
      return (await response.json()) as DiscoverResponse;
    } catch (error) {
      return {
        success: false,
        message: "Kamera tarama işlemi başlatılamadı.",
      };
    }
  },
);
