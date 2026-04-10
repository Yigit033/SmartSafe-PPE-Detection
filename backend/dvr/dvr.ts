import { api } from "encore.dev/api";
import { v4 as uuidv4 } from "uuid";
import { pool } from "../db";

interface DVRSystem {
  dvr_id: string;
  company_id: string;
  name: string;
  ip_address: string;
  port: number;
  username: string;
  dvr_type: string;
  status: string;
}

interface ListDVRRequest {
  company_id: string;
}

interface CreateDVRRequest {
  company_id: string;
  name: string;
  ip_address: string;
  port?: number;
  username?: string;
  password?: string;
  dvr_type?: string;
  protocol?: string;
  api_path?: string;
  rtsp_port?: number;
  max_channels?: number;
}

interface RemoveDVRRequest {
  company_id: string;
  dvr_id: string;
}

/**
 * Şirketin DVR sistemlerini listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company/:company_id/dvr" },
  async (
    params: ListDVRRequest,
  ): Promise<{ success: boolean; systems: any[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM dvr_systems WHERE company_id = $1 AND status <> 'deleted' ORDER BY created_at DESC",
        [params.company_id],
      );
      return { success: true, systems: res.rows };
    } catch (error) {
      console.error("Error listing DVR systems:", error);
      return { success: false, systems: [] };
    }
  },
);

/**
 * Yeni bir DVR sistemi ekler
 */
export const create = api(
  { expose: true, method: "POST", path: "/company/:company_id/dvr" },
  async (
    params: CreateDVRRequest,
  ): Promise<{
    success: boolean;
    dvr_id?: string;
    restored?: boolean;
    message?: string;
    error?: string;
  }> => {
    const dvr_id = `DVR_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;
    try {
      const existing = await pool.query(
        `SELECT dvr_id, status FROM dvr_systems WHERE company_id = $1 AND ip_address = $2`,
        [params.company_id, params.ip_address],
      );
      if (existing.rows.length > 0) {
        const row = existing.rows[0] as { dvr_id: string; status: string };
        if (String(row.status).toLowerCase() === "deleted") {
          await pool.query(
            `
            UPDATE dvr_systems SET
              name = $1, port = $2, username = $3, password = $4,
              dvr_type = $5, protocol = $6, api_path = $7, rtsp_port = $8,
              max_channels = $9, status = $10, updated_at = CURRENT_TIMESTAMP
            WHERE company_id = $11 AND dvr_id = $12
            `,
            [
              params.name,
              params.port || 80,
              params.username || "admin",
              params.password || "",
              params.dvr_type || "generic",
              params.protocol || "http",
              params.api_path || "/api",
              params.rtsp_port || 554,
              params.max_channels || 16,
              "inactive",
              params.company_id,
              row.dvr_id,
            ],
          );
          await pool.query(
            `
            UPDATE dvr_channels
            SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
            WHERE company_id = $1 AND dvr_id = $2 AND status = 'deleted'
            `,
            [params.company_id, row.dvr_id],
          );
          return {
            success: true,
            dvr_id: row.dvr_id,
            restored: true,
            message:
              "Bu IP’de daha önce kaldırılmış bir DVR bulundu; kayıt geri yüklendi. Geçmiş ihlal kayıtları korunur. Kanalları güncellemek için keşif önerilir.",
          };
        }
        return {
          success: false,
          error:
            "Bu şirket için bu IP ile kayıtlı bir DVR zaten var. Aynı NVR'ı iki kez ekleyemezsiniz.",
        };
      }

      await pool.query(
        `
        INSERT INTO dvr_systems (
          dvr_id, company_id, name, ip_address, port, 
          username, password, dvr_type, protocol, api_path, 
          rtsp_port, max_channels, status, created_at, updated_at
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      `,
        [
          dvr_id,
          params.company_id,
          params.name,
          params.ip_address,
          params.port || 80,
          params.username || "admin",
          params.password || "",
          params.dvr_type || "generic",
          params.protocol || "http",
          params.api_path || "/api",
          params.rtsp_port || 554,
          params.max_channels || 16,
          "inactive",
        ],
      );

      return { success: true, dvr_id };
    } catch (error: any) {
      console.error("Error creating DVR system:", error);
      if (error?.code === "23505") {
        return {
          success: false,
          error:
            "Bu şirket için bu IP ile kayıtlı bir DVR zaten var. Aynı NVR'ı iki kez ekleyemezsiniz.",
        };
      }
      return { success: false, error: error.message };
    }
  },
);

/**
 * Bir DVR sistemini siler
 */
export const remove = api(
  { expose: true, method: "DELETE", path: "/company/:company_id/dvr/:dvr_id" },
  async (
    params: RemoveDVRRequest,
  ): Promise<{ success: boolean; message?: string; error?: string }> => {
    try {
      // Soft delete to preserve violation_events history (FKs prevent hard delete).
      await pool.query("BEGIN");
      await pool.query(
        `
        UPDATE dvr_channels
        SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
        WHERE company_id = $1 AND dvr_id = $2 AND status <> 'deleted'
        `,
        [params.company_id, params.dvr_id],
      );
      await pool.query(
        `
        UPDATE dvr_systems
        SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
        WHERE company_id = $1 AND dvr_id = $2 AND status <> 'deleted'
        `,
        [params.company_id, params.dvr_id],
      );
      await pool.query("COMMIT");
      return {
        success: true,
        message:
          "DVR listeden kaldırıldı (kayıtlar silinmedi). Geçmiş ihlal ve raporlar aynı kalır; tekrar eklediğinizde aynı IP ile geri yüklenebilir.",
      };
    } catch (error: any) {
      try {
        await pool.query("ROLLBACK");
      } catch {
        // ignore rollback errors
      }
      console.error("Error deleting DVR system:", error);
      return { success: false, error: error.message };
    }
  },
);
