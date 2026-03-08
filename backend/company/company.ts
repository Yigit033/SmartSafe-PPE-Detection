import { api } from "encore.dev/api";
import { v4 as uuidv4 } from "uuid";
import * as bcrypt from "bcrypt";
import { pool } from "../db";

interface CreateCompanyParams {
  company_name: string;
  sector: string;
  contact_person: string;
  email: string;
  phone?: string;
  address?: string;
  subscription_type?: string;
  password?: string; // Admin kullanıcısı için şifre
}

interface CompanyResponse {
  company_id: string;
  company_name: string;
  api_key: string;
  admin_email: string;
}

interface Company {
  company_id: string;
  company_name: string;
  email: string;
  api_key: string;
  created_at: string;
  user_count: number;
}

interface UpdateProfileRequest {
  company_id: string;
  company_name?: string;
  sector?: string;
  contact_person?: string;
  email?: string;
}

interface UpdateNotificationsRequest {
  company_id: string;
  email_notifications: boolean;
  sms_notifications: boolean;
  push_notifications: boolean;
}

interface CompanyStats {
  active_cameras: number;
  today_violations: number;
  monthly_violations: number;
  avg_compliance_rate: number;
  active_workers: number;
  trends: {
    cameras: number;
    violations: number;
    compliance: number;
  };
}

/**
 * Şirket istatistiklerini getirir (Dashboard için)
 */
export const getStats = api(
  { expose: true, method: "GET", path: "/company/:company_id/stats" },
  async ({ company_id }: { company_id: string }): Promise<CompanyStats> => {
    try {
      // 1. Aktif Kamera Sayısı
      const camerasRes = await pool.query(
        "SELECT COUNT(*) as count FROM cameras WHERE company_id = $1 AND status = 'active'",
        [company_id],
      );
      const active_cameras = parseInt(camerasRes.rows[0].count);

      // 2. Geçen haftaki kamera sayısı (trend için)
      const lastWeekCamerasRes = await pool.query(
        "SELECT COUNT(*) as count FROM cameras WHERE company_id = $1 AND created_at < CURRENT_DATE - INTERVAL '7 days'",
        [company_id],
      );
      const last_week_cameras = parseInt(lastWeekCamerasRes.rows[0].count);

      // 3. Bugünkü İhlaller (violation_events tablosundan)
      const todayViolationsRes = await pool.query(
        "SELECT COUNT(*) as count FROM violation_events WHERE company_id = $1 AND (TO_TIMESTAMP(start_time))::DATE = CURRENT_DATE",
        [company_id],
      );
      const today_violations = parseInt(todayViolationsRes.rows[0].count);

      // 4. Dünkü İhlaller
      const yesterdayViolationsRes = await pool.query(
        "SELECT COUNT(*) as count FROM violation_events WHERE company_id = $1 AND (TO_TIMESTAMP(start_time))::DATE = CURRENT_DATE - INTERVAL '1 day'",
        [company_id],
      );
      const yesterday_violations = parseInt(
        yesterdayViolationsRes.rows[0].count,
      );

      // 5. Aylık İhlaller
      const monthlyViolationsRes = await pool.query(
        "SELECT COUNT(*) as count FROM violation_events WHERE company_id = $1 AND (TO_TIMESTAMP(start_time))::DATE > CURRENT_DATE - INTERVAL '30 days'",
        [company_id],
      );
      const monthly_violations = parseInt(monthlyViolationsRes.rows[0].count);

      // 6. Aktif Çalışan Sayısı (Unique track_id)
      const activeWorkersRes = await pool.query(
        "SELECT COUNT(DISTINCT track_id) as count FROM detections WHERE company_id = $1 AND DATE(timestamp) = CURRENT_DATE AND track_id IS NOT NULL",
        [company_id],
      );
      const active_workers = parseInt(activeWorkersRes.rows[0].count);

      // 7. Compliance Rate (Uyum Oranı)
      const complianceRes = await pool.query(
        `SELECT 
          CASE 
            WHEN SUM(people_detected) > 0 
            THEN (SUM(ppe_compliant)::FLOAT / NULLIF(SUM(people_detected), 0)::FLOAT * 100.0)
            ELSE 0 
          END as avg_compliance
        FROM detections 
        WHERE company_id = $1 AND DATE(timestamp) = CURRENT_DATE`,
        [company_id],
      );
      const avg_compliance_rate = parseFloat(
        complianceRes.rows[0].avg_compliance || "0",
      );

      // Trend hesaplamaları
      const cameras_trend = active_cameras - last_week_cameras;
      const violations_trend = today_violations - yesterday_violations;

      return {
        active_cameras,
        today_violations,
        monthly_violations,
        avg_compliance_rate,
        active_workers,
        trends: {
          cameras: cameras_trend,
          violations: violations_trend,
          compliance: 0, // Şimdilik statik
        },
      };
    } catch (error) {
      console.error("Error fetching company stats:", error);
      throw error;
    }
  },
);

/**
 * Yeni bir şirket ve bu şirkete bağlı bir Admin kullanıcısı oluşturur.
 */
export const create = api(
  { expose: true, method: "POST", path: "/company" },
  async (params: CreateCompanyParams): Promise<CompanyResponse> => {
    const company_id = `COMP_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;
    const user_id = `USER_${uuidv4().replace(/-/g, "").substring(0, 8).toUpperCase()}`;
    const apiKey = uuidv4().replace(/-/g, "");

    // Şifre belirtilmemişse varsayılan bir şifre ata (Güvenlik için frontend'den gelmesi önerilir)
    const password = params.password || "smartsafe2024";
    const passwordHash = await bcrypt.hash(password, 12);

    const client = await pool.connect();

    try {
      await client.query("BEGIN");

      // 1. Şirketi oluştur
      await client.query(
        `
        INSERT INTO companies (
          company_id, company_name, sector, contact_person, email, 
          phone, address, subscription_type, api_key, status, 
          max_cameras, created_at, updated_at
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      `,
        [
          company_id,
          params.company_name,
          params.sector,
          params.contact_person,
          params.email,
          params.phone || null,
          params.address || null,
          params.subscription_type || "professional",
          apiKey,
          "active",
          25,
        ],
      );

      // 2. Şirketin Admin kullanıcısını oluştur
      await client.query(
        `
        INSERT INTO users (
          user_id, company_id, username, email, password_hash, 
          role, status, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
      `,
        [
          user_id,
          company_id,
          params.contact_person,
          params.email,
          passwordHash,
          "admin",
          "active",
        ],
      );

      await client.query("COMMIT");

      return {
        company_id,
        company_name: params.company_name,
        api_key: apiKey,
        admin_email: params.email,
      };
    } catch (error) {
      await client.query("ROLLBACK");
      console.error("Error in transaction creating company/user:", error);
      throw error;
    } finally {
      client.release();
    }
  },
);

/**
 * Tüm şirketleri listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company" },
  async (): Promise<{ companies: Company[] }> => {
    try {
      const res = await pool.query(`
        SELECT c.company_id, c.company_name, c.email, c.api_key, c.created_at,
        (SELECT COUNT(*) FROM users u WHERE u.company_id = c.company_id)::int as user_count
        FROM companies c
        ORDER BY c.created_at DESC
      `);
      return { companies: res.rows };
    } catch (error) {
      console.error("Error listing companies:", error);
      throw error;
    }
  },
);

interface GetCompanyResponse {
  success: boolean;
  company?: any; // We can use 'any' here or define a full Company interface
  error?: string;
}

/**
 * Belirli bir şirketin tüm detaylarını getirir
 */
export const getById = api(
  { expose: true, method: "GET", path: "/company/:company_id" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<GetCompanyResponse> => {
    try {
      const res = await pool.query(
        "SELECT * FROM companies WHERE company_id = $1",
        [company_id],
      );
      if (res.rows.length === 0) {
        return { success: false, error: "Şirket bulunamadı" };
      }
      return { success: true, company: res.rows[0] };
    } catch (error) {
      console.error("Error getting company by id:", error);
      return { success: false, error: "Sunucu hatası" };
    }
  },
);

/**
 * Şirket profil bilgilerini günceller
 */
export const updateProfile = api(
  { expose: true, method: "PATCH", path: "/company/:company_id" },
  async (params: UpdateProfileRequest): Promise<{ success: boolean }> => {
    const { company_id, ...updates } = params;
    try {
      const keys = Object.keys(updates).filter(
        (k) => (updates as any)[k] !== undefined,
      );
      if (keys.length === 0) return { success: true };

      const setClause = keys
        .map((key, index) => `${key} = $${index + 2}`)
        .join(", ");
      const values = keys.map((key) => (updates as any)[key]);

      await pool.query(
        `UPDATE companies SET ${setClause}, updated_at = CURRENT_TIMESTAMP WHERE company_id = $1`,
        [company_id, ...values],
      );
      return { success: true };
    } catch (error) {
      console.error("Error updating company profile:", error);
      return { success: false };
    }
  },
);

/**
 * Şirket bildirim ayarlarını günceller
 */
export const updateNotifications = api(
  { expose: true, method: "PATCH", path: "/company/:company_id/notifications" },
  async (params: UpdateNotificationsRequest): Promise<{ success: boolean }> => {
    const {
      company_id,
      email_notifications,
      sms_notifications,
      push_notifications,
    } = params;
    try {
      await pool.query(
        `
        UPDATE companies SET 
        email_notifications = $1, 
        sms_notifications = $2, 
        push_notifications = $3, 
        updated_at = CURRENT_TIMESTAMP 
        WHERE company_id = $4
      `,
        [
          email_notifications,
          sms_notifications,
          push_notifications,
          company_id,
        ],
      );
      return { success: true };
    } catch (error) {
      console.error("Error updating notifications:", error);
      return { success: false };
    }
  },
);

/**
 * Şirket hesabını tamamen siler
 */
export const remove = api(
  { expose: true, method: "DELETE", path: "/company/:company_id" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean }> => {
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      await client.query("DELETE FROM users WHERE company_id = $1", [
        company_id,
      ]);
      await client.query("DELETE FROM cameras WHERE company_id = $1", [
        company_id,
      ]);
      await client.query("DELETE FROM companies WHERE company_id = $1", [
        company_id,
      ]);
      await client.query("COMMIT");
      return { success: true };
    } catch (error) {
      await client.query("ROLLBACK");
      console.error("Error deleting company:", error);
      return { success: false };
    } finally {
      client.release();
    }
  },
);
