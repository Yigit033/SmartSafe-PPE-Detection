import { Pool } from "pg";

// Shared PostgreSQL connection pool (supports Docker service names)
export const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas",
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
