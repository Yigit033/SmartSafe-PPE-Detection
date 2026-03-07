import { api } from "encore.dev/api";
import { pool } from "../db";

interface SubscriptionInfo {
  subscription_type: string;
  max_cameras: number;
  status: string;
  auto_renewal: boolean;
  subscription_end?: string;
}

interface GetSubscriptionRequest {
  company_id: string;
}

interface UpdatePlanRequest {
  company_id: string;
  plan: string;
  max_cameras: number;
}

interface ToggleAutoRenewalRequest {
  company_id: string;
  enabled: boolean;
}

/**
 * Şirketin abonelik bilgilerini getirir
 */
export const getInfo = api(
  { expose: true, method: "GET", path: "/company/:company_id/subscription" },
  async (
    params: GetSubscriptionRequest,
  ): Promise<{ success: boolean; subscription?: SubscriptionInfo }> => {
    try {
      const res = await pool.query(
        "SELECT subscription_type, max_cameras, status, auto_renewal, subscription_end FROM companies WHERE company_id = $1",
        [params.company_id],
      );
      return { success: true, subscription: res.rows[0] };
    } catch (error) {
      console.error("Error fetching subscription:", error);
      return { success: false };
    }
  },
);

/**
 * Abonelik planını günceller
 */
export const updatePlan = api(
  {
    expose: true,
    method: "POST",
    path: "/company/:company_id/subscription/plan",
  },
  async (params: UpdatePlanRequest): Promise<{ success: boolean }> => {
    try {
      await pool.query(
        "UPDATE companies SET subscription_type = $1, max_cameras = $2, updated_at = CURRENT_TIMESTAMP WHERE company_id = $3",
        [params.plan, params.max_cameras, params.company_id],
      );
      return { success: true };
    } catch (error) {
      console.error("Error updating plan:", error);
      return { success: false };
    }
  },
);

/**
 * Otomatik yenilemeyi açar/kapatır
 */
export const toggleAutoRenewal = api(
  {
    expose: true,
    method: "POST",
    path: "/company/:company_id/subscription/auto-renewal",
  },
  async (params: ToggleAutoRenewalRequest): Promise<{ success: boolean }> => {
    try {
      await pool.query(
        "UPDATE companies SET auto_renewal = $1, updated_at = CURRENT_TIMESTAMP WHERE company_id = $2",
        [params.enabled, params.company_id],
      );
      return { success: true };
    } catch (error) {
      console.error("Error toggling auto-renewal:", error);
      return { success: false };
    }
  },
);
