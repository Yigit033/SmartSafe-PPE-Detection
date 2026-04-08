/**
 * Sadece backend/company/migrations/*.sql dosyalarını sırayla çalıştırır.
 *
 * Kullanım:
 *   DATABASE_URL=... node scripts/migrate_company.cjs
 *   npm run migrate:company
 *
 * Tüm backend migration'ları için: npm run migrate
 */
const { Client } = require("pg");
const fs = require("fs");
const path = require("path");

const MIG_DIR = path.join(__dirname, "..", "company", "migrations");

async function main() {
  const connectionString =
    process.env.DATABASE_URL ||
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";

  const client = new Client({ connectionString });

  try {
    await client.connect();
    console.log("Connected (company migrations only).");

    const files = fs
      .readdirSync(MIG_DIR)
      .filter((f) => f.endsWith(".sql"))
      .sort();

    if (files.length === 0) {
      console.warn("No .sql files in", MIG_DIR);
      return;
    }

    for (const file of files) {
      const rel = `company/migrations/${file}`;
      console.log(`Running: ${rel}`);
      const sql = fs.readFileSync(path.join(MIG_DIR, file), "utf8");
      await client.query(sql);
      console.log(`OK: ${rel}`);
    }

    console.log("Company migrations finished.");
  } catch (err) {
    console.error("Migration error:", err.message);
    process.exit(1);
  } finally {
    await client.end();
  }
}

main();
