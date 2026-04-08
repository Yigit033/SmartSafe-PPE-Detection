/**
 * violation_events PR migration'ları — varsayılan sadece PR1 (2_*.sql).
 * PR3 (3_*.sql) veri önkoşulu gerektirir; isteğe bağlı.
 *
 * Kullanım:
 *   DATABASE_URL=... node scripts/migrate_violation_events.cjs
 *   npm run migrate:violations
 *
 * PR3'ü de çalıştırmak için (önce PR2 backfill / kod deploy koşullarını sağlayın):
 *   node scripts/migrate_violation_events.cjs --pr3
 *   npm run migrate:violations:pr3
 */
const { Client } = require("pg");
const fs = require("fs");
const path = require("path");

const MIG_DIR = path.join(__dirname, "..", "company", "migrations");

const FILE_PR1 = "2_violation_events_expand_pr1.up.sql";
const FILE_PR3 = "3_violation_events_contract_pr3.up.sql";

async function main() {
  const runPr3 = process.argv.includes("--pr3");
  const connectionString =
    process.env.DATABASE_URL ||
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";

  const client = new Client({ connectionString });
  const files = [FILE_PR1];
  if (runPr3) files.push(FILE_PR3);

  try {
    await client.connect();
    console.log("Connected (violation_events migrations).");
    if (!runPr3) {
      console.log("PR3 skipped. To run PR3: add flag --pr3 (see script header).");
    }

    for (const file of files) {
      const full = path.join(MIG_DIR, file);
      if (!fs.existsSync(full)) {
        console.error("File not found:", full);
        process.exit(1);
      }
      const rel = `company/migrations/${file}`;
      console.log(`Running: ${rel}`);
      const sql = fs.readFileSync(full, "utf8");
      await client.query(sql);
      console.log(`OK: ${rel}`);
    }

    console.log("violation_events migration step(s) finished.");
  } catch (err) {
    console.error("Migration error:", err.message);
    process.exit(1);
  } finally {
    await client.end();
  }
}

main();
