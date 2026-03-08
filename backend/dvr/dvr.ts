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
  ): Promise<{ success: boolean; systems: DVRSystem[] }> => {
    try {
      const res = await pool.query(
        "SELECT dvr_id, company_id, name, ip_address, port, username, dvr_type, status FROM dvr_systems WHERE company_id = $1 ORDER BY created_at DESC",
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
    error?: string;
  }> => {
    const dvr_id = `DVR_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;
    try {
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
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query(
        "DELETE FROM dvr_systems WHERE company_id = $1 AND dvr_id = $2",
        [params.company_id, params.dvr_id],
      );
      return { success: true };
    } catch (error: any) {
      console.error("Error deleting DVR system:", error);
      return { success: false, error: error.message };
    }
  },
);
