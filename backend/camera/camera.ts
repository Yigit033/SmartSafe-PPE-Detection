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
  group_id?: string;
  detection_zones?: any;
  created_at: string;
}

interface CameraGroup {
  group_id: string;
  company_id: string;
  name: string;
  location?: string;
  group_type?: string;
  camera_count?: number;
  active_cameras?: number;
  ppe_config?: any;
  created_at: string;
  updated_at: string;
}

interface CreateGroupRequest {
  company_id: string;
  name: string;
  location?: string;
  group_type?: string;
  ppe_config?: any;
}

interface UpdateGroupRequest {
  company_id: string;
  group_id: string;
  name?: string;
  location?: string;
  group_type?: string;
  ppe_config?: any;
}

interface SuccessResponse {
  success: boolean;
  error?: string;
  message?: string;
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
  group_id?: string;
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
  group_id?: string | null;
}

interface CameraSchedule {
  id?: number;
  company_id: string;
  camera_id: string;
  camera_type: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_enabled: boolean;
}

/**
 * Şirkete ait kameraları listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company/:company_id/cameras" },
  async ({
    company_id,
    status,
  }: {
    company_id: string;
    status?: string;
  }): Promise<{ success: boolean; cameras: Camera[] }> => {
    try {
      let whereClause = "WHERE company_id = $1";
      const params: any[] = [company_id];

      if (status) {
        whereClause += " AND status = $2";
        params.push(status);
      } else {
        whereClause += " AND status <> 'deleted'";
      }

      const res = await pool.query(
        `
        SELECT 
          camera_id, company_id, camera_name, location, ip_address, 
          port, protocol, stream_path, username, password, 
          status, NULL as channel_number, NULL as dvr_id, group_id, 'ip_camera' as camera_type,
          COALESCE(detection_zones, '[]'::jsonb) as detection_zones, created_at
        FROM cameras 
        ${whereClause}
        UNION ALL
        SELECT 
          dc.channel_id as camera_id, dc.company_id, dc.name as camera_name, 
          'DVR: ' || ds.name as location, ds.ip_address, ds.rtsp_port as port, 
          'rtsp' as protocol, dc.rtsp_path as stream_path, 
          ds.username, ds.password, dc.status, dc.channel_number, ds.dvr_id, NULL as group_id, 'dvr_channel' as camera_type,
          COALESCE(dc.detection_zones, '[]'::jsonb) as detection_zones, dc.created_at
        FROM dvr_channels dc
        JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
        ${whereClause.replace("company_id", "dc.company_id").replace("status", "dc.status")} AND ds.status <> 'deleted'
        ORDER BY
          channel_number ASC NULLS FIRST,
          camera_name ASC,
          created_at ASC
        `,
        params,
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
          status, group_id, created_at, updated_at
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
          params.group_id || null,
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

      // 1. Önce IP kameralarda (cameras tablosu) dene
      const camSetClause = keys
        .map((key, index) => `${key} = $${index + 3}`)
        .join(", ");
      const camValues = keys.map((key) => (updates as any)[key]);

      const camRes = await pool.query(
        `UPDATE cameras SET ${camSetClause}, updated_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND camera_id = $2`,
        [company_id, camera_id, ...camValues],
      );

      if ((camRes.rowCount ?? 0) > 0) {
        return { success: true };
      }

      // 2. Bulunamazsa DVR kanallarında (dvr_channels tablosu) dene
      // Kolon isimleri farklı olabilir: cameras.camera_name -> dvr_channels.name
      const dvrKeys = keys.map(k => k === "camera_name" ? "name" : k);
      
      // dvr_channels tablosunda olup olmadığını bildiğimiz kolonları filtrele (güvenlik için)
      const validDvrKeys = ["name", "status"]; 
      const filteredDvrKeys: string[] = [];
      const filteredDvrValues: any[] = [];
      
      dvrKeys.forEach((key, index) => {
        if (validDvrKeys.includes(key)) {
          filteredDvrKeys.push(key);
          filteredDvrValues.push(keys.map(k => (updates as any)[k])[index]);
        }
      });

      if (filteredDvrKeys.length > 0) {
        const dvrSetClause = filteredDvrKeys
          .map((key, index) => `${key} = $${index + 3}`)
          .join(", ");

        const dvrRes = await pool.query(
          `UPDATE dvr_channels SET ${dvrSetClause}, updated_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND channel_id = $2`,
          [company_id, camera_id, ...filteredDvrValues],
        );

        if ((dvrRes.rowCount ?? 0) > 0) {
          return { success: true };
        }
      }

      return { 
        success: false, 
        error: "Kamera bulunamadı (ne cameras ne de dvr_channels tablosunda)." 
      };
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
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      // violation_events.camera_id → cameras FK (legacy DB'lerde hâlâ olabilir); önce bağı kaldır.
      await client.query(
        "DELETE FROM violation_events WHERE company_id = $1 AND camera_id = $2",
        [company_id, camera_id],
      );
      await client.query(
        "DELETE FROM cameras WHERE company_id = $1 AND camera_id = $2",
        [company_id, camera_id],
      );
      await client.query("COMMIT");
      return { success: true };
    } catch (error: any) {
      try {
        await client.query("ROLLBACK");
      } catch {
        /* ignore */
      }
      console.error("Error deleting camera:", error);
      return { success: false, error: error.message };
    } finally {
      client.release();
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
            'rtsp' as protocol, dc.rtsp_path as stream_path, 
            ds.username, ds.password, dc.status, dc.created_at, 'dvr_channel' as camera_type
          FROM dvr_channels dc
          JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
          WHERE dc.company_id = $1 AND dc.channel_id = $2 AND dc.status <> 'deleted' AND ds.status <> 'deleted'
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
    zones: any[] | { coord_space?: string; zones: any[] };
  }): Promise<{ success: boolean; error?: string }> => {
    try {
      const payload =
        Array.isArray(zones)
          ? JSON.stringify({ coord_space: "video", zones })
          : JSON.stringify(zones);
      const camRes = await pool.query(
        "UPDATE cameras SET detection_zones = $1::jsonb, updated_at = CURRENT_TIMESTAMP WHERE company_id = $2 AND camera_id = $3",
        [payload, company_id, camera_id],
      );
      if ((camRes.rowCount ?? 0) > 0) {
        return { success: true };
      }
      const dvrRes = await pool.query(
        "UPDATE dvr_channels SET detection_zones = $1::jsonb, updated_at = CURRENT_TIMESTAMP WHERE company_id = $2 AND channel_id = $3 AND status <> 'deleted'",
        [payload, company_id, camera_id],
      );
      if ((dvrRes.rowCount ?? 0) > 0) {
        return { success: true };
      }
      return {
        success: false,
        error:
          "ROI kaydedilemedi: bu ID ile cameras veya dvr_channels kaydı bulunamadı.",
      };
    } catch (error: any) {
      console.error("Error saving ROI:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Şirkete ait kamera gruplarını listeler
 */
export const listGroups = api(
  { expose: true, method: "GET", path: "/company/:company_id/cameras/groups" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; groups: CameraGroup[]; error?: string }> => {
    try {
      const res = await pool.query(
        `
        SELECT 
          g.*,
          (SELECT COUNT(*) FROM cameras WHERE group_id = g.group_id) as camera_count,
          (SELECT COUNT(*) FROM cameras WHERE group_id = g.group_id AND status = 'active') as active_cameras
        FROM camera_groups g
        WHERE g.company_id = $1
        ORDER BY g.created_at DESC
        `,
        [company_id],
      );
      
      const groups = res.rows.map(row => ({
        ...row,
        camera_count: parseInt(row.camera_count || "0"),
        active_cameras: parseInt(row.active_cameras || "0")
      }));

      return { success: true, groups };
    } catch (error: any) {
      console.error("Error listing camera groups:", error);
      return { success: false, groups: [], error: error.message };
    }
  },
);

/**
 * Yeni bir kamera grubu oluşturur
 */
export const createGroup = api(
  { expose: true, method: "POST", path: "/company/:company_id/cameras/groups" },
  async (params: CreateGroupRequest): Promise<{ success: boolean; group_id?: string; error?: string }> => {
    const { company_id, name, location, group_type } = params;
    const group_id = `GRP_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;

    try {
      await pool.query(
        `
        INSERT INTO camera_groups (
          group_id, company_id, name, location, group_type, ppe_config,
          created_at, updated_at
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        `,
        [group_id, company_id, name, location || "", group_type || "general", JSON.stringify(params.ppe_config || {})],
      );

      return { success: true, group_id };
    } catch (error: any) {
      console.error("Error creating camera group:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kamera grubunu günceller
 */
export const updateGroup = api(
  { expose: true, method: "PATCH", path: "/company/:company_id/cameras/groups/:group_id" },
  async (params: UpdateGroupRequest): Promise<SuccessResponse> => {
    const { company_id, group_id, ...updates } = params;
    
    try {
      const keys = Object.keys(updates).filter(
        (k) => (updates as any)[k] !== undefined,
      );
      if (keys.length === 0) return { success: true };

      const setClause = keys
        .map((key, index) => `${key} = $${index + 3}`)
        .join(", ");
      
      const values = keys.map((key) => {
        const value = (updates as any)[key];
        if (key === "ppe_config" && typeof value === "object") {
          return JSON.stringify(value);
        }
        
        return value;
      });

      await pool.query(
        `UPDATE camera_groups SET ${setClause}, updated_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND group_id = $2`,
        [company_id, group_id, ...values],
      );

      return { success: true };
    } catch (error: any) {
      console.error("Error updating camera group:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kamera grubunu siler
 */
export const removeGroup = api(
  { expose: true, method: "DELETE", path: "/company/:company_id/cameras/groups/:group_id" },
  async ({
    company_id,
    group_id,
  }: {
    company_id: string;
    group_id: string;
  }): Promise<SuccessResponse> => {
    try {
      await pool.query(
        "UPDATE cameras SET group_id = NULL WHERE company_id = $1 AND group_id = $2",
        [company_id, group_id],
      );

      await pool.query(
        "DELETE FROM camera_groups WHERE company_id = $1 AND group_id = $2",
        [company_id, group_id],
      );

      return { success: true };
    } catch (error: any) {
      console.error("Error deleting camera group:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kamerayı bir gruba atar
 */
export const assignToGroup = api(
  { expose: true, method: "POST", path: "/company/:company_id/cameras/:camera_id/assign-group" },
  async (params: {
    company_id: string;
    camera_id: string;
    group_id: string | null;
  }): Promise<SuccessResponse> => {
    const { company_id, camera_id, group_id } = params;
    
    try {
      await pool.query(
        "UPDATE cameras SET group_id = $1, updated_at = CURRENT_TIMESTAMP WHERE company_id = $2 AND camera_id = $3",
        [group_id, company_id, camera_id],
      );
      
      return { success: true };
    } catch (error: any) {
      console.error("Error assigning camera to group:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Bir kameraya ait tüm zaman çizelgelerini listeler
 */
export const listSchedules = api(
  { expose: true, method: "GET", path: "/company/:company_id/cameras/:camera_id/schedules" },
  async (params: { company_id: string; camera_id: string }): Promise<{ success: boolean; schedules: CameraSchedule[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM camera_schedules WHERE company_id = $1 AND camera_id = $2 ORDER BY day_of_week ASC, start_time ASC",
        [params.company_id, params.camera_id],
      );
      return { success: true, schedules: res.rows };
    } catch (error: any) {
      console.error("Error listing schedules:", error);
      return { success: false, schedules: [] };
    }
  },
);

/**
 * Yeni bir zaman çizelgesi ekler veya mevcut olanı günceller
 */
export const saveSchedule = api(
  { expose: true, method: "POST", path: "/company/:company_id/cameras/:camera_id/schedules" },
  async (params: { 
    company_id: string; 
    camera_id: string; 
    camera_type: string;
    day_of_week: number;
    start_time: string;
    end_time: string;
    is_enabled?: boolean;
    id?: number;
  }): Promise<{ success: boolean; id?: number; error?: string }> => {
    try {
      if (params.id) {
        // Güncelleme
        await pool.query(
          `UPDATE camera_schedules SET 
            day_of_week = $1, start_time = $2, end_time = $3, 
            is_enabled = $4, updated_at = CURRENT_TIMESTAMP 
          WHERE id = $5 AND company_id = $6`,
          [params.day_of_week, params.start_time, params.end_time, params.is_enabled !== false, params.id, params.company_id]
        );
        return { success: true, id: params.id };
      } else {
        // Yeni Kayıt
        const res = await pool.query(
          `INSERT INTO camera_schedules (
            company_id, camera_id, camera_type, day_of_week, start_time, end_time, is_enabled
          ) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
          [params.company_id, params.camera_id, params.camera_type, params.day_of_week, params.start_time, params.end_time, params.is_enabled !== false]
        );
        return { success: true, id: res.rows[0].id };
      }
    } catch (error: any) {
      console.error("Error saving schedule:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Bir zaman çizelgesini siler
 */
export const deleteSchedule = api(
  { expose: true, method: "DELETE", path: "/company/:company_id/cameras/:camera_id/schedules/:id" },
  async (params: { company_id: string; camera_id: string; id: number }): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query("DELETE FROM camera_schedules WHERE id = $1 AND company_id = $2 AND camera_id = $3", [params.id, params.company_id, params.camera_id]);
      return { success: true };
    } catch (error: any) {
      console.error("Error deleting schedule:", error);
      return { success: false, error: error.message };
    }
  },
);
