const { Client } = require("pg");

const connectionString =
  process.env.DATABASE_URL ||
  "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";

(async () => {
  const c = new Client({ connectionString });
  await c.connect();

  const cols = await c.query(
    `SELECT column_name, data_type
       FROM information_schema.columns
      WHERE table_name = 'violation_events'
        AND column_name IN ('start_time', 'end_time')
      ORDER BY column_name`,
  );
  console.log("Columns:");
  for (const r of cols.rows) {
    console.log(`  ${r.column_name}: ${r.data_type}`);
  }

  const count = await c.query("SELECT COUNT(*)::int AS n FROM violation_events");
  console.log(`Total rows in violation_events: ${count.rows[0].n}`);

  const recent = await c.query(
    `SELECT event_id, company_id, camera_id, violation_type, start_time, status
       FROM violation_events
       ORDER BY start_time DESC NULLS LAST
       LIMIT 5`,
  );
  console.log("Most recent rows:");
  for (const r of recent.rows) {
    console.log(
      `  ${r.event_id} | ${r.company_id} | ${r.camera_id} | ${r.violation_type} | start=${r.start_time} | ${r.status}`,
    );
  }

  await c.end();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
