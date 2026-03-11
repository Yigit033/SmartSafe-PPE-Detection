const { Client } = require('pg');

async function checkTables() {
    const connectionString = "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";
    const client = new Client({ connectionString });

    try {
        await client.connect();
        const res = await client.query(`
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        `);
        console.log("Tables in public schema:");
        console.table(res.rows);
    } catch (err) {
        console.error("Error:", err.message);
    } finally {
        await client.end();
    }
}

checkTables();
