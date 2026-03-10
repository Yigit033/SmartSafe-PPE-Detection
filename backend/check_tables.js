import pkg from "pg";
const { Pool } = pkg;
const pool = new Pool({
  connectionString:
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas",
});
async function check() {
  try {
    const res = await pool.query(
      "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'",
    );
    console.log(res.rows.map((r) => r.tablename));
  } catch (e) {
    console.error(e);
  } finally {
    process.exit(0);
  }
}
check();
