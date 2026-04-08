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
  /** IP kamera: DB camera_id; DVR (PR3): COALESCE ile dvr_channel_id üzerinden doldurulur */
  camera_id: string;
  dvr_channel_id?: string | null;
  camera_name?: string;
  violation_type: string;
  start_time: number;
  end_time: number;
  snapshot_path: string;
  count: number;
  status: string;
}

/** PR3 şeması: source_type + dvr_channel_id (migration 2+3 uygulanmış DB). */
const VIOLATION_EVENTS_QUERY_PR3 = `
  SELECT ve.*, COALESCE(c.camera_name, dc.name) AS camera_name
  FROM violation_events ve
  LEFT JOIN cameras c
    ON c.company_id = ve.company_id
   AND ve.source_type = 'camera'
   AND c.camera_id = ve.camera_id
  LEFT JOIN dvr_channels dc
    ON dc.company_id = ve.company_id
   AND ve.source_type = 'dvr_channel'
   AND dc.channel_id = ve.dvr_channel_id
  WHERE ve.company_id = $1
  ORDER BY ve.start_time DESC
  LIMIT 200`;

/**
 * Eski şema: source_type / dvr_channel_id yok — kamera adı için cameras veya
 * camera_id ile dvr_channels eşlemesi (kanal id’si camera_id’de tutulmuş DVR satırları).
 */
const VIOLATION_EVENTS_QUERY_LEGACY = `
  SELECT ve.*, COALESCE(c.camera_name, dc.name) AS camera_name
  FROM violation_events ve
  LEFT JOIN cameras c
    ON c.company_id = ve.company_id AND c.camera_id = ve.camera_id
  LEFT JOIN dvr_channels dc
    ON dc.company_id = ve.company_id AND dc.channel_id = ve.camera_id
  WHERE ve.company_id = $1
  ORDER BY ve.start_time DESC
  LIMIT 200`;

function mapViolationEventRows(rows: any[]): ViolationEvent[] {
  return rows.map((row) => ({
    ...row,
    camera_id: String(row.camera_id ?? row.dvr_channel_id ?? ""),
  }));
}

/** PR3 kolonları yoksa her istekte hatalı SQL denemek Postgres ERROR log üretir; bir kez kontrol edilir. */
let violationEventsSchemaMode: "pr3" | "legacy" | null = null;

async function getViolationEventsQuerySql(): Promise<string> {
  if (violationEventsSchemaMode !== null) {
    return violationEventsSchemaMode === "pr3"
      ? VIOLATION_EVENTS_QUERY_PR3
      : VIOLATION_EVENTS_QUERY_LEGACY;
  }
  const probe = await pool.query(
    `SELECT 1 AS ok
     FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'violation_events'
       AND column_name = 'source_type'
     LIMIT 1`,
  );
  const hasPr3 = probe.rows.length > 0;
  violationEventsSchemaMode = hasPr3 ? "pr3" : "legacy";
  if (!hasPr3) {
    console.warn(
      "violation_events: PR3 columns not present; using legacy SQL until backend/company/migrations/2_violation_events_expand_pr1.up.sql is applied.",
    );
  }
  return hasPr3 ? VIOLATION_EVENTS_QUERY_PR3 : VIOLATION_EVENTS_QUERY_LEGACY;
}

/**
 * Şirketin ihlal olaylarını (Event-based) getirir.
 * PR3: `source_type` üzerinden ayrı join — OR / SUBSTRING yok. `camera_id` alanı API’de
 * her zaman anlamlı string (DVR’da dvr_channel_id ile geri uyum).
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
      const sql = await getViolationEventsQuerySql();
      const res = await pool.query(sql, [company_id]);
      const events = mapViolationEventRows(res.rows);
      return { success: true, events };
    } catch (error) {
      console.error("Error fetching violation events:", error);
      return { success: false, events: [] };
    }
  },
);

/**
 * Şirkete ait tüm ihlal olaylarını (violation_events) siler.
 * Diskteki snapshot dosyaları silinmez; yalnızca veritabanı kayıtları kaldırılır.
 * GET ile aynı path'te başka method kullanılamaz (Encore route çakışması).
 */
export const deleteAllEvents = api(
  {
    expose: true,
    method: "POST",
    path: "/company/:company_id/violation-events/delete-all",
  },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; deleted: number }> => {
    try {
      const res = await pool.query(
        "DELETE FROM violation_events WHERE company_id = $1",
        [company_id],
      );
      const deleted =
        typeof res.rowCount === "number" ? res.rowCount : 0;
      return { success: true, deleted };
    } catch (error) {
      console.error("Error deleting all violation events:", error);
      return { success: false, deleted: 0 };
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
