const { Client } = require('pg');
const fs = require('fs');
const path = require('path');

async function runMigrations() {
    const connectionString = process.env.DATABASE_URL || "postgresql://smartsafe:smartsafe2024@127.0.0.1:5432/smartsafe_saas";
    const client = new Client({ connectionString });

    try {
        await client.connect();
        console.log("Connected to PostgreSQL for migrations.");

        // Migration dosyalarının yolu
        const migrationsDir = path.join(__dirname, '../camera/migrations');
        const migrationFiles = fs.readdirSync(migrationsDir)
                                .filter(f => f.endsWith('.sql'))
                                .sort(); // 1_..., 2_... olarak sırala

        for (const file of migrationFiles) {
            console.log(`Running migration: ${file}`);
            const sql = fs.readFileSync(path.join(migrationsDir, file), 'utf8');
            
            // IF NOT EXISTS mantığını SQL içinde hallettiğimiz için direkt execute edebiliriz
            await client.query(sql);
            console.log(`Successfully completed: ${file}`);
        }

        console.log("All migrations executed successfully.");
    } catch (err) {
        console.error("Migration error:", err.message);
        process.exit(1);
    } finally {
        await client.end();
    }
}

runMigrations();
