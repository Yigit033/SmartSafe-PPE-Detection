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

interface ListViolationsRequest {
  company_id: string;
}

interface ListAlertsRequest {
  company_id: string;
}

interface ResolveAlertRequest {
  company_id: string;
  alert_id: number;
}

interface ViolationEvent {
  event_id: string;
  company_id: string;
  camera_id: string;
  camera_name?: string;
  violation_type: string;
  start_time: number;
  end_time: number;
  snapshot_path: string;
  count: number;
  status: string;
}

/**
 * Şirketin ihlal olaylarını (Event-based) getirir
 */
export const getEvents = api(
  {
    expose: true,
    method: "GET",
    path: "/company/:company_id/violation-events",
  },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; events: ViolationEvent[] }> => {
    try {
      const res = await pool.query(
        `SELECT ve.*, c.camera_name 
         FROM violation_events ve
         LEFT JOIN cameras c ON ve.camera_id = c.camera_id
         WHERE ve.company_id = $1 
         ORDER BY ve.start_time DESC 
         LIMIT 200`,
        [company_id],
      );
      return { success: true, events: res.rows };
    } catch (error) {
      console.error("Error fetching violation events:", error);
      return { success: false, events: [] };
    }
  },
);

/**
 * Şirketin ihlal raporlarını getirir (Eski sistem uyumluluk için)
 */
export const getViolations = api(
  { expose: true, method: "GET", path: "/company/:company_id/violations" },
  async (
    params: ListViolationsRequest,
  ): Promise<{ success: boolean; violations: Violation[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM violations WHERE company_id = $1 ORDER BY timestamp DESC LIMIT 100",
        [params.company_id],
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
  async (
    params: ListAlertsRequest,
  ): Promise<{ success: boolean; alerts: Alert[] }> => {
    try {
      const res = await pool.query(
        "SELECT * FROM alerts WHERE company_id = $1 ORDER BY created_at DESC",
        [params.company_id],
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
  async (params: ResolveAlertRequest): Promise<{ success: boolean }> => {
    try {
      await pool.query(
        "UPDATE alerts SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND alert_id = $2",
        [params.company_id, params.alert_id],
      );
      return { success: true };
    } catch (error) {
      console.error("Error resolving alert:", error);
      return { success: false };
    }
  },
);
