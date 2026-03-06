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

interface AddUserParams {
  username: string;
  email: string;
  password: string;
  role?: string;
}

/**
 * Şirketin tüm kullanıcılarını listeler
 */
export const list = api(
  { expose: true, method: "GET", path: "/company/:company_id/users" },
  async ({
    company_id,
  }: {
    company_id: string;
  }): Promise<{ success: boolean; users: User[] }> => {
    try {
      const res = await pool.query(
        "SELECT user_id, company_id, username, email, role, status FROM users WHERE company_id = $1 ORDER BY created_at DESC",
        [company_id],
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
  async ({
    company_id,
    ...params
  }: { company_id: string } & AddUserParams): Promise<{
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
          company_id,
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
 * Bir kullanıcıyı siler
 */
export const remove = api(
  {
    expose: true,
    method: "DELETE",
    path: "/company/:company_id/users/:user_id",
  },
  async ({
    company_id,
    user_id,
  }: {
    company_id: string;
    user_id: string;
  }): Promise<{ success: boolean; error?: string }> => {
    try {
      await pool.query(
        "DELETE FROM users WHERE company_id = $1 AND user_id = $2",
        [company_id, user_id],
      );
      return { success: true };
    } catch (error: any) {
      console.error("Error deleting user:", error);
      return { success: false, error: error.message };
    }
  },
);
