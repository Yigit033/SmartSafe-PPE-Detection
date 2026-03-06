import { api } from "encore.dev/api";
import { pool } from "../db";

interface Violation {
  violation_id: number;
  camera_id: string;
  missing_ppe: string;
  violation_type: string;
  confidence: number;
  timestamp: string;
}

interface Alert {
  alert_id: number;
  camera_id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  status: string;
  created_at: string;
}

/**
 * Şirketin ihlal raporlarını getirir
 */
export const getViolations = api(
  { expose: true, method: "GET", path: "/company/:company_id/violations" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; violations: Violation[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM violations WHERE company_id = $1 ORDER BY timestamp DESC LIMIT 100",
        [company_id],
      );
      return { success: true, violations: res.rows };
    } catch (error) {
      console.error("Error fetching violations:", error);
      return { success: false, violations: [] };
    }
  },
);

/**
 * Şirketin aktif uyarılarını getirir
 */
export const getAlerts = api(
  { expose: true, method: "GET", path: "/company/:company_id/alerts" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; alerts: Alert[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM alerts WHERE company_id = $1 ORDER BY created_at DESC",
        [company_id],
      );
      return { success: true, alerts: res.rows };
    } catch (error) {
      console.error("Error fetching alerts:", error);
      return { success: false, alerts: [] };
    }
  },
);

/**
 * Bir uyarıyı çözüldü olarak işaretler
 */
export const resolveAlert = api(
  {
    expose: true,
    method: "POST",
    path: "/company/:company_id/alerts/:alert_id/resolve",
  },
  async ({
    company_id,
    alert_id,
  }: {
    company_id: string;
    alert_id: number;
  }): Promise<{ success: boolean }> => {
    try {
      await pool.query(
        "UPDATE alerts SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND alert_id = $2",
        [company_id, alert_id],
      );
      return { success: true };
    } catch (error) {
      console.error("Error resolving alert:", error);
      return { success: false };
    }
  },
);
