const { Client } = require('pg');

async function checkSchema() {
    const connectionString = "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";
    const client = new Client({ connectionString });

    try {
        await client.connect();
        const res = await client.query(`
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'camera_groups'
        `);
        console.log("Columns in camera_groups:");
        console.table(res.rows);
    } catch (err) {
        console.error("Error:", err.message);
    } finally {
        await client.end();
    }
}

checkSchema();
