import { api } from "encore.dev/api";
import { v4 as uuidv4 } from "uuid";
import * as bcrypt from "bcrypt";
import { pool } from "../db";
import { SECTOR_PPE_CONFIGS } from "./sector_config";

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
  phone?: string;
  address?: string;
  ppe_requirements?: any[];
  compliance_settings?: any;
}

interface UpdateNotificationsRequest {
  company_id: string;
  email_notifications: boolean;
  sms_notifications: boolean;
  push_notifications: boolean;
  violation_alerts: boolean;
  telegram_notifications: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
}

interface ResolveChatRequest {
  bot_token?: string;
  chat_id_or_url: string;
}

interface CompanyStats {
  /** Aktif IP kameralar + aktif DVR kanalları (toplam) */
  active_cameras: number;
  /** Abonelik / şirket kapasitesi (dashboard paydası) */
  max_cameras: number;
  today_violations: number;
  monthly_violations: number;
  avg_compliance_rate: number;
  active_workers: number;
  trends: {
    cameras: number;
    violations: number;
    compliance: number;
  };
  /** Son 7 günün uyum grafiği verisi */
  compliance_trend: { day: string; rate: number }[];
  hourly_compliance: { hour: number; rate: number }[];
  /** İstatistiksel ihlal tipleri dağılımı (son 30 gün) */
  violation_types: { type: string; count: number }[];
  /** Bugünün saatlik ihlal dağılımı */
  hourly_violations: { hour: number; count: number }[];
}

/**
 * Şirket istatistiklerini getirir (Dashboard için)
 */
export const getStats = api(
  { expose: true, method: "GET", path: "/company/:company_id/stats" },
  async ({ company_id }: { company_id: string }): Promise<CompanyStats> => {
    try {
      // Ortamlar arası (dev/prod) tip farklılığını (timestamp vs double precision) otomatik algıla
      const typeCheckRes = await pool.query(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 'violation_events' AND column_name = 'start_time' LIMIT 1"
      );
      const isUnixTimestamp = typeCheckRes.rows[0]?.data_type === 'double precision';
      
      // Tip bazlı tarih cast fonksiyonu
      const timeCast = (col: string) => isUnixTimestamp ? `TO_TIMESTAMP(${col})` : col;
      const dateCast = (col: string) => `(${timeCast(col)})::DATE`;

      // 0. Şirket kapasitesi
      const capRes = await pool.query(
        "SELECT COALESCE(max_cameras, 25)::int AS max_cameras FROM companies WHERE company_id = $1",
        [company_id],
      );
      const max_cameras = parseInt(capRes.rows[0]?.max_cameras ?? "25", 10);

      // 1. Aktif kameralar & DVR kanalları
      const camerasRes = await pool.query(
        `SELECT
           (SELECT COUNT(*)::bigint FROM cameras WHERE company_id = $1 AND status = 'active')
         + (SELECT COUNT(*)::bigint FROM dvr_channels WHERE company_id = $1 AND status = 'active')
         AS count`,
        [company_id],
      );
      const active_cameras = parseInt(String(camerasRes.rows[0].count), 10);

      // 2. Geçen haftaki kamera sayısı (Trend için)
      const lastWeekCamerasRes = await pool.query(
        `SELECT
           (SELECT COUNT(*)::bigint FROM cameras WHERE company_id = $1 AND created_at < CURRENT_DATE - INTERVAL '7 days')
         + (SELECT COUNT(*)::bigint FROM dvr_channels WHERE company_id = $1 AND created_at < CURRENT_DATE - INTERVAL '7 days')
         AS count`,
        [company_id],
      );
      const last_week_cameras = parseInt(String(lastWeekCamerasRes.rows[0].count), 10);

      // 3. İhlal sayıları (Bugün, Dün, Aylık)
      const violationCountsRes = await pool.query(
        `SELECT
          COUNT(*) FILTER (WHERE ${dateCast('start_time')} = CURRENT_DATE) as today,
          COUNT(*) FILTER (WHERE ${dateCast('start_time')} = CURRENT_DATE - INTERVAL '1 day') as yesterday,
          COUNT(*) FILTER (WHERE ${dateCast('start_time')} > CURRENT_DATE - INTERVAL '30 days') as monthly
         FROM violation_events
         WHERE company_id = $1`,
        [company_id],
      );
      const today_violations = parseInt(violationCountsRes.rows[0].today);
      const yesterday_violations = parseInt(violationCountsRes.rows[0].yesterday);
      const monthly_violations = parseInt(violationCountsRes.rows[0].monthly);

      // 4. Aktif Çalışan Sayısı & Uyum Oranı (Bugün)
      const dailyMetricsRes = await pool.query(
        `SELECT
          COUNT(DISTINCT track_id) as active_workers,
          CASE 
            WHEN SUM(people_detected) > 0 
            THEN (SUM(ppe_compliant)::FLOAT / NULLIF(SUM(people_detected), 0)::FLOAT * 100.0)
            ELSE 0 
          END as avg_compliance
         FROM detections
         WHERE company_id = $1 AND ${dateCast('timestamp')} = CURRENT_DATE`,
        [company_id],
      );
      const active_workers = parseInt(dailyMetricsRes.rows[0].active_workers);
      const avg_compliance_rate = parseFloat(dailyMetricsRes.rows[0].avg_compliance || "0");

      // 5. Compliance Trend (Son 7 Günlük)
      const complianceTrendRes = await pool.query(
        `SELECT 
            TO_CHAR(${dateCast('timestamp')}, 'YYYY-MM-DD') as day,
            AVG(CASE WHEN people_detected > 0 THEN (ppe_compliant::FLOAT / people_detected::FLOAT * 100.0) ELSE 0 END) as rate
         FROM detections 
         WHERE company_id = $1 AND ${timeCast('timestamp')} > CURRENT_DATE - INTERVAL '7 days'
         GROUP BY ${dateCast('timestamp')}
         ORDER BY day ASC`,
        [company_id],
      );
      const compliance_trend = complianceTrendRes.rows.map(r => ({
        day: r.day,
        rate: Math.round(parseFloat(r.rate || "0") * 10) / 10
      }));

      // 5b. Saatlik Compliance Trend (Bugün)
      const hourlyComplianceRes = await pool.query(
        `SELECT 
            EXTRACT(HOUR FROM ${timeCast('timestamp')}) as hour,
            AVG(CASE WHEN people_detected > 0 THEN (ppe_compliant::FLOAT / people_detected::FLOAT * 100.0) ELSE 0 END) as rate
         FROM detections 
         WHERE company_id = $1 AND ${dateCast('timestamp')} = CURRENT_DATE
         GROUP BY hour
         ORDER BY hour ASC`,
        [company_id],
      );
      const hourly_compliance = hourlyComplianceRes.rows.map(r => ({
        hour: parseInt(r.hour),
        rate: Math.round(parseFloat(r.rate || "0") * 10) / 10
      }));

      // 6. Violation Types Dağılımı (Son 30 Gün)
      const violationTypesRes = await pool.query(
        `SELECT 
            violation_type, 
            COUNT(*) as count 
          FROM violation_events 
          WHERE company_id = $1 AND ${dateCast('start_time')} > CURRENT_DATE - INTERVAL '30 days'
          GROUP BY violation_type
          ORDER BY count DESC`,
        [company_id],
      );
      const violation_types = violationTypesRes.rows.map(r => ({
        type: r.violation_type,
        count: parseInt(r.count)
      }));

      // 7. Saatlik İhlal Dağılımı (Bugün)
      const hourlyViolationsRes = await pool.query(
        `SELECT 
            EXTRACT(HOUR FROM ${timeCast('start_time')})::int as hour,
            COUNT(*) as count
          FROM violation_events
          WHERE company_id = $1 AND ${dateCast('start_time')} = CURRENT_DATE
          GROUP BY hour
          ORDER BY hour ASC`,
        [company_id],
      );
      const hourly_violations = hourlyViolationsRes.rows.map(r => ({
        hour: r.hour,
        count: parseInt(r.count)
      }));

      // Trend hesaplamaları
      const cameras_trend = active_cameras - last_week_cameras;
      const violations_trend = today_violations - yesterday_violations;

      return {
        active_cameras,
        max_cameras,
        today_violations,
        monthly_violations,
        avg_compliance_rate,
        active_workers,
        trends: {
          cameras: cameras_trend,
          violations: violations_trend,
          compliance: 0, // Opsiyonel: Geçen haftaya göre fark hesaplanabilir
        },
        compliance_trend,
        hourly_compliance,
        violation_types,
        hourly_violations
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
      // Sektöre göre varsayılan PPE kurallarını al
      const sectorConfig = SECTOR_PPE_CONFIGS[params.sector] || SECTOR_PPE_CONFIGS.manufacturing;

      await client.query(
        `
        INSERT INTO companies (
          company_id, company_name, sector, contact_person, email, 
          phone, address, subscription_type, api_key, status, 
          max_cameras, created_at, updated_at,
          ppe_requirements, compliance_settings
        ) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, $12, $13)
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
          JSON.stringify(sectorConfig.ppe_requirements),
          JSON.stringify(sectorConfig.compliance_settings),
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
        (SELECT COUNT(*) FROM users u WHERE u.company_id = c.company_id AND u.deleted_at IS NULL)::int as user_count
        FROM companies c
        WHERE c.deleted_at IS NULL
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
  company?: any;
  error?: string;
  system_bot_username?: string;
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
        "SELECT * FROM companies WHERE company_id = $1 AND deleted_at IS NULL",
        [company_id],
      );
      if (res.rows.length === 0) {
        return { success: false, error: "Şirket bulunamadı" };
      }
      return { 
        success: true, 
        company: res.rows[0],
        system_bot_username: process.env.DEFAULT_TELEGRAM_BOT_USERNAME 
      };
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

      // JSON alanlarını stringify et, diğerlerini direkt gönder
      const values = keys.map((key) => {
        const val = (updates as any)[key];
        if (key === "ppe_requirements" || key === "compliance_settings") {
          return typeof val === "string" ? val : JSON.stringify(val);
        }
        return val;
      });

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
      violation_alerts,
      telegram_notifications,
      telegram_bot_token,
      telegram_chat_id,
    } = params;
    try {
      await pool.query(
        `
        UPDATE companies SET 
        email_notifications = $1, 
        sms_notifications = $2, 
        push_notifications = $3, 
        violation_alerts = $4,
        telegram_notifications = $5,
        telegram_bot_token = $6,
        telegram_chat_id = $7,
        updated_at = CURRENT_TIMESTAMP 
        WHERE company_id = $8
      `,
        [
          email_notifications,
          sms_notifications,
          push_notifications,
          violation_alerts,
          telegram_notifications,
          telegram_bot_token || null,
          telegram_chat_id || null,
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

      // Soft Delete: Veriyi kalıcı olarak silmek yerine deleted_at işaretle
      // Bu sayede yanlışlıkla silinen veriler tek bir SQL ile geri getirilebilir
      await client.query(
        "UPDATE users SET deleted_at = CURRENT_TIMESTAMP WHERE company_id = $1 AND deleted_at IS NULL",
        [company_id],
      );
      await client.query(
        "UPDATE companies SET deleted_at = CURRENT_TIMESTAMP, status = 'deleted' WHERE company_id = $1 AND deleted_at IS NULL",
        [company_id],
      );

      await client.query("COMMIT");
      console.log(`🗑️ Soft-deleted company ${company_id} and associated users`);
      return { success: true };
    } catch (error) {
      await client.query("ROLLBACK");
      console.error("Error soft-deleting company:", error);
      return { success: false };
    } finally {
      client.release();
    }
  },
);

/**
 * Telegram URL veya kullanıcı adından sayısal Chat ID'yi çözer
 */
export const resolveTelegramChatId = api(
  { expose: true, method: "POST", path: "/company/resolve-telegram-chat" },
  async (params: ResolveChatRequest): Promise<{ success: boolean; chat_id?: string; error?: string }> => {
    let target = params.chat_id_or_url.trim();
    
    // URL temizleme
    target = target.replace(/^https?:\/\/t\.me\//, "");
    target = target.replace(/^t\.me\//, "");
    
    // Eğer davet linki (+...) ise, API üzerinden çözemeyiz (Telegram kısıtı)
    if (target.includes("+")) {
      return { 
        success: false, 
        error: "Davet linkleri (+...) API üzerinden doğrudan çözülemez. Lütfen botu gruba ekleyip sayısal ID'yi giriniz." 
      };
    }

    // Kullanıcı adı ise başına @ ekle
    if (!target.startsWith("@") && !/^-?\d+$/.test(target)) {
      target = "@" + target;
    }

    // Halihazırda sayısal ID ise direkt dön
    if (/^-?\d+$/.test(target)) {
      return { success: true, chat_id: target };
    }

    const bot_token = params.bot_token || process.env.DEFAULT_TELEGRAM_BOT_TOKEN;
    if (!bot_token) {
      return { success: false, error: "Bot token tanımlı değil." };
    }

    try {
      const url = `https://api.telegram.org/bot${bot_token}/getChat?chat_id=${target}`;
      const response = await fetch(url);
      const data: any = await response.json();

      if (data.ok) {
        return { success: true, chat_id: String(data.result.id) };
      } else {
        return { success: false, error: data.description || "Bulunamadı" };
      }
    } catch (error) {
      return { success: false, error: "Telegram bağlantı hatası" };
    }
  },
);
