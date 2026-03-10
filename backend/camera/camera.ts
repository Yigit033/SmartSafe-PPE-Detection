import { api } from "encore.dev/api";
import { v4 as uuidv4 } from "uuid";
import { pool } from "../db";

// Kamera için veri tipleri
interface Camera {
  camera_id: string;
  company_id: string;
  camera_name: string;
  location: string;
  ip_address: string;
  port: number;
  protocol: string;
  stream_path: string;
  username?: string;
  password?: string;
  status: string;
  camera_type?: "ip_camera" | "dvr_channel";
  channel_number?: number;
  dvr_id?: string;
  detection_zones?: any;
  created_at: string;
}

interface CreateCameraRequest {
  company_id: string;
  camera_name: string;
  camera_location: string;
  camera_ip: string;
  camera_port?: number;
  camera_protocol?: string;
  camera_path?: string;
  camera_username?: string;
  camera_password?: string;
}

interface UpdateCameraRequest {
  company_id: string;
  camera_id: string;
  camera_name?: string;
  location?: string;
  ip_address?: string;
  port?: number;
  protocol?: string;
  stream_path?: string;
  status?: string;
}

/**
 * Şirkete ait kameraları listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company/:company_id/cameras" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; cameras: Camera[] }> => {
    try {
      const res = await pool.query(
        `
        SELECT 
          camera_id, company_id, camera_name, location, ip_address, 
          port, protocol, stream_path, username, password, 
          status, NULL as channel_number, NULL as dvr_id, 'ip_camera' as camera_type, created_at
        FROM cameras 
        WHERE company_id = $1
        UNION ALL
        SELECT 
          dc.channel_id as camera_id, dc.company_id, dc.name as camera_name, 
          'DVR: ' || ds.name as location, ds.ip_address, ds.rtsp_port as port, 
          'rtsp' as protocol, '/channel=' || dc.channel_number as stream_path, 
          ds.username, ds.password, dc.status, dc.channel_number, ds.dvr_id, 'dvr_channel' as camera_type, dc.created_at
        FROM dvr_channels dc
        JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
        WHERE dc.company_id = $1
        ORDER BY created_at DESC
        `,
        [company_id],
      );
      return { success: true, cameras: res.rows };
    } catch (error) {
      console.error("Error listing cameras:", error);
      return { success: false, cameras: [] };
    }
  },
);

/**
 * Yeni bir kamera ekler
 */
export const create = api(
  { expose: true, method: "POST", path: "/company/:company_id/cameras" },
  async (
    params: CreateCameraRequest,
  ): Promise<{
    success: boolean;
    camera_id?: string;
    error?: string;
  }> => {
    const { company_id } = params;

    // 1. Abonelik/Limit Kontrolü (Basit versiyon)
    const companyRes = await pool.query(
      "SELECT max_cameras FROM companies WHERE company_id = $1",
      [company_id],
    );
    const cameraCountRes = await pool.query(
      "SELECT COUNT(*) FROM cameras WHERE company_id = $1",
      [company_id],
    );

    const maxCameras = companyRes.rows[0]?.max_cameras || 25;
    const currentCameras = parseInt(cameraCountRes.rows[0].count);

    if (currentCameras >= maxCameras) {
      return {
        success: false,
        error: `Kamera limiti aşıldı! (${currentCameras}/${maxCameras})`,
      };
    }

    const camera_id = `CAM_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;

    try {
      await pool.query(
        `
        INSERT INTO cameras (
          camera_id, company_id, camera_name, location, ip_address, 
          port, protocol, stream_path, username, password, 
          status, created_at, updated_at
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      `,
        [
          camera_id,
          company_id,
          params.camera_name,
          params.camera_location,
          params.camera_ip,
          params.camera_port || 8080,
          params.camera_protocol || "http",
          params.camera_path || "/video",
          params.camera_username || "",
          params.camera_password || "",
          "active",
        ],
      );

      return { success: true, camera_id };
    } catch (error: any) {
      console.error("Error creating camera:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Mevcut bir kamerayı günceller
 */
export const update = api(
  {
    expose: true,
    method: "PATCH",
    path: "/company/:company_id/cameras/:camera_id",
  },
  async (
    params: UpdateCameraRequest,
  ): Promise<{
    success: boolean;
    error?: string;
  }> => {
    const { company_id, camera_id, ...updates } = params;
    try {
      const keys = Object.keys(updates).filter(
        (k) => (updates as any)[k] !== undefined,
      );
      if (keys.length === 0) return { success: true };

      const setClause = keys
        .map((key, index) => `${key} = $${index + 3}`)
        .join(", ");
      const values = keys.map((key) => (updates as any)[key]);

      await pool.query(
        `UPDATE cameras SET ${setClause}, updated_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND camera_id = $2`,
        [company_id, camera_id, ...values],
      );

      return { success: true };
    } catch (error: any) {
      console.error("Error updating camera:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Bir kamerayı siler
 */
export const remove = api(
  {
    expose: true,
    method: "DELETE",
    path: "/company/:company_id/cameras/:camera_id",
  },
  async ({
    company_id,
    camera_id,
  }: {
    company_id: string;
    camera_id: string;
  }): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query(
        "DELETE FROM cameras WHERE company_id = $1 AND camera_id = $2",
        [company_id, camera_id],
      );
      return { success: true };
    } catch (error: any) {
      console.error("Error deleting camera:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kameradan anlık görüntü (snapshot) alır
 */
export const getSnapshot = api(
  {
    expose: true,
    method: "GET",
    path: "/company/:company_id/cameras/:camera_id/snapshot",
  },
  async ({
    company_id,
    camera_id,
  }: {
    company_id: string;
    camera_id: string;
  }): Promise<{ success: boolean; image?: string; error?: string }> => {
    try {
      // Önce normal kameralarda ara
      let res = await pool.query(
        "SELECT *, 'ip_camera' as camera_type FROM cameras WHERE company_id = $1 AND camera_id = $2",
        [company_id, camera_id],
      );

      // Bulunamazsa DVR kanallarında ara
      if (res.rows.length === 0) {
        res = await pool.query(
          `
          SELECT 
            dc.channel_id as camera_id, dc.company_id, dc.name as camera_name, 
            'DVR: ' || ds.name as location, ds.ip_address, ds.rtsp_port as port, 
            'rtsp' as protocol, '/channel=' || dc.channel_number as stream_path, 
            ds.username, ds.password, dc.status, dc.created_at, 'dvr_channel' as camera_type
          FROM dvr_channels dc
          JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
          WHERE dc.company_id = $1 AND dc.channel_id = $2
          `,
          [company_id, camera_id],
        );
      }

      if (res.rows.length === 0) {
        return { success: false, error: "Kamera bulunamadı" };
      }

      const camera: Camera = res.rows[0];
      const { protocol, ip_address, port, username, password } = camera;

      // Snapshot URL'lerini dene (IP Webcam ve genel path'ler)
      const snapshotPaths = [
        "/shot.jpg",
        "/photoaf.jpg",
        "/photo.jpg",
        "/snapshot.jpg",
        "/image.jpg",
      ];

      let lastError = "";

      for (const path of snapshotPaths) {
        const url = `${protocol}://${ip_address}:${port}${path}`;
        try {
          const headers: Record<string, string> = {};
          if (username && password) {
            const auth = Buffer.from(`${username}:${password}`).toString(
              "base64",
            );
            headers["Authorization"] = `Basic ${auth}`;
          }

          const response = await fetch(url, {
            headers,
            // @ts-ignore - Encore fetch might have slight differences
            signal: AbortSignal.timeout(5000),
          });

          if (response.ok) {
            const arrayBuffer = await response.arrayBuffer();
            const base64 = Buffer.from(arrayBuffer).toString("base64");
            const contentType =
              response.headers.get("content-type") || "image/jpeg";
            return {
              success: true,
              image: `data:${contentType};base64,${base64}`,
            };
          }
        } catch (e: any) {
          lastError = e.message;
          continue;
        }
      }

      return {
        success: false,
        error: `Kameradan görüntü alınamadı: ${lastError}`,
      };
    } catch (error: any) {
      console.error("Error getting snapshot:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kameranın ROI (Region of Interest) bölgelerini kaydeder
 */
export const saveROI = api(
  {
    expose: true,
    method: "POST",
    path: "/company/:company_id/cameras/:camera_id/roi",
  },
  async ({
    company_id,
    camera_id,
    zones,
  }: {
    company_id: string;
    camera_id: string;
    zones: any[];
  }): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query(
        "UPDATE cameras SET detection_zones = $1, updated_at = CURRENT_TIMESTAMP WHERE company_id = $2 AND camera_id = $3",
        [JSON.stringify(zones), company_id, camera_id],
      );
      return { success: true };
    } catch (error: any) {
      console.error("Error saving ROI:", error);
      return { success: false, error: error.message };
    }
  },
);
