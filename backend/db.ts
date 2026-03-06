import { Pool } from "pg";

// Python Core ile paylaşılan PostgreSQL bağlantı havuzu
export const pool = new Pool({
  connectionString:
    "postgresql://smartsafe:smartsafe2024db@127.0.0.1:5432/smartsafe_saas",
});

// Bağlantıyı test et
pool.on("connect", () => {
  console.log("🐘 Encore -> Shared PostgreSQL Connected Successfully");
});

pool.on("error", (err) => {
  console.error("❌ PostgreSQL Connection Error Details:", err.message);
});

// İlk bağlantıyı zorla (check)
pool
  .query("SELECT NOW()")
  .then(() => {
    console.log("✅ Initial Database Handshake OK");
  })
  .catch((err) => {
    console.error("❌ Initial Database Handshake FAILED:", err.message);
  });
