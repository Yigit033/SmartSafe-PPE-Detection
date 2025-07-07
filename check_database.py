import sqlite3
import os

def check_database():
    db_path = 'smartsafe_saas.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} does not exist!")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_names = [table[0] for table in tables]
        print(f"✅ Database tables: {table_names}")
        
        # Check companies table
        if 'companies' in table_names:
            cursor.execute("SELECT COUNT(*) FROM companies")
            company_count = cursor.fetchone()[0]
            print(f"✅ Companies in database: {company_count}")
            
            if company_count > 0:
                cursor.execute("SELECT company_id, name, email, sector, subscription_status FROM companies LIMIT 3")
                companies = cursor.fetchall()
                print("📊 Sample companies:")
                for company in companies:
                    print(f"  - ID: {company[0]}, Name: {company[1]}, Email: {company[2]}, Sector: {company[3]}, Status: {company[4]}")
        
        # Check users table
        if 'users' in table_names:
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"✅ Users in database: {user_count}")
        
        # Check cameras table
        if 'cameras' in table_names:
            cursor.execute("SELECT COUNT(*) FROM cameras")
            camera_count = cursor.fetchone()[0]
            print(f"✅ Cameras in database: {camera_count}")
        
        conn.close()
        print("✅ Database connection test successful!")
        
    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    check_database() 