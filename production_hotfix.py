#!/usr/bin/env python3
"""
Production Hotfix Script
Simple fix for missing updated_at column in production
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def apply_production_hotfix():
    """Apply simple production hotfix for missing column"""
    try:
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("❌ DATABASE_URL environment variable not set")
            return False
        
        # Connect to database
        connection = psycopg2.connect(
            database_url,
            sslmode='prefer',
            cursor_factory=RealDictCursor
        )
        cursor = connection.cursor()
        
        logger.info("✅ Connected to production database")
        
        # Check if updated_at column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cameras' AND column_name = 'updated_at'
        """)
        
        if not cursor.fetchone():
            logger.info("🔧 Adding missing updated_at column to cameras table")
            cursor.execute("""
                ALTER TABLE cameras 
                ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)
            connection.commit()
            logger.info("✅ Added updated_at column successfully")
        else:
            logger.info("✅ updated_at column already exists")
        
        # Update existing rows to have updated_at = created_at
        cursor.execute("""
            UPDATE cameras 
            SET updated_at = created_at 
            WHERE updated_at IS NULL
        """)
        connection.commit()
        logger.info("✅ Updated existing rows with updated_at values")
        
        cursor.close()
        connection.close()
        logger.info("🎉 Production hotfix applied successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Production hotfix failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = apply_production_hotfix()
    if success:
        print("🎉 Production hotfix completed successfully!")
    else:
        print("❌ Production hotfix failed!")
        sys.exit(1) 