import { Pool } from "pg";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

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

// --- 🚀 AUTO-MIGRATION LOGIC ---
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function runAutoMigrations() {
  console.log("🔄 Checking for pending database migrations...");
  
  try {
    // Backend altındaki tüm servis klasörlerini tara (camera, user, company vb.)
    const backendRoot = __dirname;
    const services = fs.readdirSync(backendRoot).filter(f => 
      fs.statSync(path.join(backendRoot, f)).isDirectory() && !f.startsWith(".") && f !== "node_modules" && f !== "scripts"
    );

    for (const service of services) {
      const migrationsDir = path.join(backendRoot, service, "migrations");
      
      if (fs.existsSync(migrationsDir)) {
        const files = fs.readdirSync(migrationsDir)
          .filter(f => f.endsWith(".sql"))
          .sort();

        if (files.length > 0) {
          console.log(`📂 Found migrations in ${service}: ${files.length} files`);
          for (const file of files) {
            const sql = fs.readFileSync(path.join(migrationsDir, file), "utf8");
            try {
              await pool.query(sql);
              console.log(`   ✅ Executed: ${service}/${file}`);
            } catch (err: any) {
              console.error(`   ❌ Failed: ${service}/${file} - ${err.message}`);
              // Bazı hatalar (kolon zaten var vb.) kritik olmayabilir, devam et.
            }
          }
        }
      }
    }
    console.log("✅ Auto-migrations completed.");
  } catch (err: any) {
    console.error("❌ Error during auto-migrations:", err.message);
  }
}

// İlk bağlantıyı zorla ve migration'ları çalıştır
pool
  .query("SELECT NOW()")
  .then(async () => {
    console.log("✅ Initial Database Handshake OK");
    await runAutoMigrations();
  })
  .catch((err) => {
    console.error("❌ Initial Database Handshake FAILED:", err.message);
  });
