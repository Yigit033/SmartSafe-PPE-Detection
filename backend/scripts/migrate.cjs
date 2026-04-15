/**
 * PostgreSQL migrations — tek giriş noktası.
 *
 * backend/<service>/migrations/*.sql dosyalarını keşfeder; servis sırası:
 *   1) company → 2) user → 3) camera → 4) diğer servisler (alfabetik)
 *
 * Yeni Encore servisi eklerken: <service>/migrations/ altına 1_*.sql, 2_*.sql koyun.
 * Gerekirse SERVICE_ORDER dizisine ekleyerek sırayı sabitleyin.
 */
const { Client } = require("pg");
const fs = require("fs");
const path = require("path");

const BACKEND_ROOT = path.join(__dirname, "..");

/** Tanımlı sıra: kiracı / kullanıcı / kamera özellikleri. Listede olmayan servisler en sonda (A–Z). */
const SERVICE_ORDER = ["company", "user", "camera"];

function serviceSortPriority(serviceName) {
  const i = SERVICE_ORDER.indexOf(serviceName);
  return i === -1 ? 1000 : i;
}

/**
 * @returns {{ service: string, dir: string }[]}
 */
function discoverMigrationDirs() {
  const out = [];
  let entries;
  try {
    entries = fs.readdirSync(BACKEND_ROOT, { withFileTypes: true });
  } catch (e) {
    console.error("Cannot read backend root:", BACKEND_ROOT, e.message);
    return out;
  }

  for (const ent of entries) {
    if (!ent.isDirectory()) continue;
    const service = ent.name;
    // atlanan yardımcı dizinler
    if (service === "node_modules" || service.startsWith(".")) continue;

    const migDir = path.join(BACKEND_ROOT, service, "migrations");
    if (!fs.existsSync(migDir)) continue;
    const st = fs.statSync(migDir);
    if (!st.isDirectory()) continue;

    out.push({ service, dir: migDir });
  }

  out.sort((a, b) => {
    const pa = serviceSortPriority(a.service);
    const pb = serviceSortPriority(b.service);
    if (pa !== pb) return pa - pb;
    return a.service.localeCompare(b.service);
  });

  return out;
}

/**
 * @param {string} migDir
 * @returns {string[]}
 */
function listSqlFiles(migDir) {
  return fs
    .readdirSync(migDir)
    .filter((f) => f.endsWith(".sql"))
    .sort();
}

async function runMigrations() {
  const connectionString =
    process.env.DATABASE_URL ||
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";

  const client = new Client({ connectionString });

  try {
    await client.connect();
    console.log("Connected to PostgreSQL for migrations.");

    // Create tracking table if not exists
    await client.query(`
      CREATE TABLE IF NOT EXISTS _migrations (
        id SERIAL PRIMARY KEY,
        service TEXT NOT NULL,
        filename TEXT NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(service, filename)
      );
    `);

    const roots = discoverMigrationDirs();
    if (roots.length === 0) {
      console.warn("No service migrations directories found under backend.");
      return;
    }

    console.log(
      "Migration plan (service order):",
      roots.map((r) => r.service).join(" → "),
    );

    for (const { service, dir } of roots) {
      const files = listSqlFiles(dir);
      if (files.length === 0) {
        continue;
      }

      for (const file of files) {
        // Check if already applied
        const { rows } = await client.query(
          "SELECT id FROM _migrations WHERE service = $1 AND filename = $2",
          [service, file]
        );

        if (rows.length > 0) {
          // Already applied
          continue;
        }

        const rel = `${service}/migrations/${file}`;
        console.log(`Running migration: ${rel}`);
        const sql = fs.readFileSync(path.join(dir, file), "utf8");
        
        try {
          await client.query("BEGIN");
          await client.query(sql);
          await client.query(
            "INSERT INTO _migrations (service, filename) VALUES ($1, $2)",
            [service, file]
          );
          await client.query("COMMIT");
          console.log(`Successfully completed: ${rel}`);
        } catch (execErr) {
          await client.query("ROLLBACK");
          console.error(`Error in ${rel}:`, execErr.message);
          throw execErr;
        }
      }
    }

    console.log("All pending migrations executed successfully.");
  } catch (err) {
    console.error("Migration fatal error:", err.message);
    process.exit(1);
  } finally {
    await client.end();
  }
}

runMigrations();
