import { api } from "encore.dev/api";
import { v4 as uuidv4 } from "uuid";
import * as bcrypt from "bcrypt";
import { pool } from "../db";

interface User {
  user_id: string;
  company_id: string;
  username: string;
  email: string;
  role: string;
  status: string;
}

interface ListUsersRequest {
  company_id: string;
}

interface CreateUserRequest {
  company_id: string;
  username: string;
  email: string;
  password: string;
  role?: string;
}

interface RemoveUserRequest {
  company_id: string;
  user_id: string;
}

interface LoginRequest {
  email: string;
  password: string;
}

interface LoginResponse {
  success: boolean;
  user?: User;
  error?: string;
}

/**
 * Şirketin tüm kullanıcılarını listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company/:company_id/users" },
  async (
    params: ListUsersRequest,
  ): Promise<{ success: boolean; users: User[] }> => {
    try {
      const res = await pool.query(
        "SELECT user_id, company_id, username, email, role, status FROM users WHERE company_id = $1 ORDER BY created_at DESC",
        [params.company_id],
      );
      return { success: true, users: res.rows };
    } catch (error) {
      console.error("Error listing users:", error);
      return { success: false, users: [] };
    }
  },
);

/**
 * Şirkete yeni bir kullanıcı ekler
 */
export const create = api(
  { expose: true, method: "POST", path: "/company/:company_id/users" },
  async (
    params: CreateUserRequest,
  ): Promise<{
    success: boolean;
    user_id?: string;
    error?: string;
  }> => {
    const user_id = uuidv4();
    const passwordHash = await bcrypt.hash(params.password, 12);

    try {
      await pool.query(
        `
        INSERT INTO users (
          user_id, company_id, username, email, password_hash, 
          role, status, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
      `,
        [
          user_id,
          params.company_id,
          params.username,
          params.email,
          passwordHash,
          params.role || "operator",
          "active",
        ],
      );

      return { success: true, user_id };
    } catch (error: any) {
      console.error("Error creating user:", error);
      return { success: false, error: error.message };
    }
  },
);

/**
 * Kullanıcı girişi yapar
 */
export const login = api(
  { expose: true, method: "POST", path: "/auth/login" },
  async (params: LoginRequest): Promise<LoginResponse> => {
    try {
      // Önce kullanıcıyı email ile bulalım
      const res = await pool.query(
        "SELECT user_id, company_id, username, email, password_hash, role, status FROM users WHERE email = $1",
        [params.email],
      );

      if (res.rows.length === 0) {
        return { success: false, error: "Kullanıcı bulunamadı" };
      }

      const userRow = res.rows[0];

      // Şifre kontrolü
      const passwordMatch = await bcrypt.compare(
        params.password,
        userRow.password_hash,
      );

      if (!passwordMatch) {
        return { success: false, error: "Geçersiz şifre" };
      }

      if (userRow.status !== "active") {
        return { success: false, error: "Hesabınız askıya alınmış" };
      }

      const { password_hash, ...user } = userRow;

      return {
        success: true,
        user: user as User,
      };
    } catch (error: any) {
      console.error("Login error:", error);
      return { success: false, error: "Sunucu hatası oluştu" };
    }
  },
);

/**
 * Bir kullanıcıyı siler
 */
export const remove = api(
  {
    expose: true,
    method: "DELETE",
    path: "/company/:company_id/users/:user_id",
  },
  async (
    params: RemoveUserRequest,
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query(
        "DELETE FROM users WHERE company_id = $1 AND user_id = $2",
        [params.company_id, params.user_id],
      );
      return { success: true };
    } catch (error: any) {
      console.error("Error deleting user:", error);
      return { success: false, error: error.message };
    }
  },
);
