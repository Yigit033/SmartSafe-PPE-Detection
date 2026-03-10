import pkg from "pg";
const { Pool } = pkg;
const pool = new Pool({
  connectionString:
    "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas",
});
async function check() {
  try {
    const res = await pool.query(
      "SELECT column_name FROM information_schema.columns WHERE table_name = 'violation_events'",
    );
    console.log(
      "violation_events:",
      res.rows.map((r) => r.column_name),
    );

    const res2 = await pool.query(
      "SELECT column_name FROM information_schema.columns WHERE table_name = 'violations'",
    );
    console.log(
      "violations:",
      res2.rows.map((r) => r.column_name),
    );
  } catch (e) {
    console.error(e);
  } finally {
    process.exit(0);
  }
}
check();
