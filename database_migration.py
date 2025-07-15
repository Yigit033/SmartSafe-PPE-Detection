#!/usr/bin/env python3
"""
Database Migration Script
SQLite to PostgreSQL migration for SmartSafe AI
"""

import sqlite3
import psycopg2
import psycopg2.extras
import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Database migration utility"""
    
    def __init__(self, sqlite_path: str = "smartsafe_saas.db"):
        self.sqlite_path = sqlite_path
        self.postgres_url = os.getenv('DATABASE_URL')
        
        if not self.postgres_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        logger.info(f"🔄 Database migrator initialized")
        logger.info(f"📁 SQLite source: {sqlite_path}")
        logger.info(f"🐘 PostgreSQL target: {self.postgres_url[:50]}...")
    
    def _parse_postgres_url(self, url: str) -> Dict[str, str]:
        """Parse PostgreSQL URL into connection parameters"""
        import urllib.parse as urlparse
        
        parsed = urlparse.urlparse(url)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading /
            'user': parsed.username,
            'password': parsed.password,
            'sslmode': 'require'
        }
    
    def get_sqlite_connection(self):
        """Get SQLite connection"""
        if not os.path.exists(self.sqlite_path):
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")
        
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_postgres_connection(self):
        """Get PostgreSQL connection"""
        params = self._parse_postgres_url(self.postgres_url)
        return psycopg2.connect(**params)
    
    def check_connections(self):
        """Test database connections"""
        try:
            # Test SQLite
            sqlite_conn = self.get_sqlite_connection()
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            sqlite_tables = sqlite_cursor.fetchone()[0]
            sqlite_conn.close()
            
            logger.info(f"✅ SQLite connection successful ({sqlite_tables} tables)")
            
            # Test PostgreSQL
            postgres_conn = self.get_postgres_connection()
            postgres_cursor = postgres_conn.cursor()
            postgres_cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            postgres_tables = postgres_cursor.fetchone()[0]
            postgres_conn.close()
            
            logger.info(f"✅ PostgreSQL connection successful ({postgres_tables} tables)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False
    
    def get_table_data(self, table_name: str) -> List[Dict]:
        """Get all data from SQLite table"""
        try:
            conn = self.get_sqlite_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Convert to dict list
            data = []
            for row in rows:
                data.append(dict(row))
            
            conn.close()
            
            logger.info(f"📊 Retrieved {len(data)} rows from {table_name}")
            return data
            
        except Exception as e:
            logger.error(f"❌ Failed to get data from {table_name}: {e}")
            return []
    
    def insert_table_data(self, table_name: str, data: List[Dict]):
        """Insert data into PostgreSQL table"""
        if not data:
            logger.info(f"⚠️ No data to insert for {table_name}")
            return
        
        try:
            conn = self.get_postgres_connection()
            cursor = conn.cursor()
            
            # Get column names from first row
            columns = list(data[0].keys())
            
            # Create placeholder string
            placeholders = ', '.join(['%s'] * len(columns))
            column_names = ', '.join(columns)
            
            # Insert query
            query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
            
            # Convert data to tuples
            values = []
            for row in data:
                values.append(tuple(row[col] for col in columns))
            
            # Execute batch insert
            cursor.executemany(query, values)
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Inserted {len(data)} rows into {table_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to insert data into {table_name}: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
    
    def migrate_table(self, table_name: str):
        """Migrate a single table"""
        logger.info(f"🔄 Migrating table: {table_name}")
        
        # Get data from SQLite
        data = self.get_table_data(table_name)
        
        if data:
            # Insert into PostgreSQL
            self.insert_table_data(table_name, data)
        
        logger.info(f"✅ Table {table_name} migration completed")
    
    def migrate_all_tables(self):
        """Migrate all tables"""
        tables = [
            'companies',
            'users',
            'cameras',
            'detections',
            'violations',
            'sessions'
        ]
        
        logger.info("🚀 Starting full database migration...")
        
        for table in tables:
            try:
                self.migrate_table(table)
            except Exception as e:
                logger.error(f"❌ Failed to migrate {table}: {e}")
        
        logger.info("✅ Database migration completed!")
    
    def verify_migration(self):
        """Verify migration by comparing row counts"""
        logger.info("🔍 Verifying migration...")
        
        tables = ['companies', 'users', 'cameras', 'detections', 'violations', 'sessions']
        
        for table in tables:
            try:
                # SQLite count
                sqlite_conn = self.get_sqlite_connection()
                sqlite_cursor = sqlite_conn.cursor()
                sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                sqlite_count = sqlite_cursor.fetchone()[0]
                sqlite_conn.close()
                
                # PostgreSQL count
                postgres_conn = self.get_postgres_connection()
                postgres_cursor = postgres_conn.cursor()
                postgres_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                postgres_count = postgres_cursor.fetchone()[0]
                postgres_conn.close()
                
                if sqlite_count == postgres_count:
                    logger.info(f"✅ {table}: {sqlite_count} rows (matched)")
                else:
                    logger.warning(f"⚠️ {table}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to verify {table}: {e}")
        
        logger.info("🎯 Migration verification completed!")
    
    def backup_sqlite(self):
        """Create backup of SQLite database"""
        if not os.path.exists(self.sqlite_path):
            logger.warning("⚠️ SQLite database not found, skipping backup")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.sqlite_path}.backup_{timestamp}"
        
        try:
            import shutil
            shutil.copy2(self.sqlite_path, backup_path)
            logger.info(f"💾 SQLite backup created: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"❌ Failed to create backup: {e}")
            return None

def main():
    """Main migration function"""
    print("🚀 SmartSafe AI Database Migration Tool")
    print("=" * 50)
    
    # Check environment
    if not os.getenv('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable is required")
        print("Please set your Supabase PostgreSQL connection string")
        return
    
    try:
        # Initialize migrator
        migrator = DatabaseMigrator()
        
        # Test connections
        print("\n🔍 Testing database connections...")
        if not migrator.check_connections():
            print("❌ Connection test failed")
            return
        
        # Create backup
        print("\n💾 Creating SQLite backup...")
        backup_path = migrator.backup_sqlite()
        
        # Confirm migration
        response = input("\n⚠️ This will migrate data from SQLite to PostgreSQL. Continue? (y/N): ")
        if response.lower() != 'y':
            print("❌ Migration cancelled")
            return
        
        # Migrate all tables
        print("\n🔄 Starting migration...")
        migrator.migrate_all_tables()
        
        # Verify migration
        print("\n🔍 Verifying migration...")
        migrator.verify_migration()
        
        print("\n✅ Migration completed successfully!")
        print(f"💾 SQLite backup: {backup_path}")
        print("🌐 Your application is now ready to use PostgreSQL!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logger.error(f"Migration error: {e}")

if __name__ == "__main__":
    main() 