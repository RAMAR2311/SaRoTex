import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app
from models import db

app = create_app()

with app.app_context():
    try:
        print("Cleaning the database (Neon)...")
        # Get all tables in a safe order for deletion
        tables = reversed(db.metadata.sorted_tables)
        
        for table in tables:
            # Table name string
            table_name = table.name
            
            # Keep users table structure but only delete extra users or keep it as is
            if table_name == 'users':
                # Preserve admin users so the user doesn't get locked out
                db.session.execute(db.text(f"DELETE FROM {table_name} WHERE rol != 'admin';"))
                print(f"Skipping complete TRUNCATE on '{table_name}' to preserve admin access.")
            else:
                # Use TRUNCATE with CASCADE for Postgres
                db.session.execute(db.text(f"TRUNCATE TABLE {table_name} CASCADE;"))
                print(f"TRUNCATE TABLE '{table_name}' completed.")
        
        db.session.commit()
        print("\nSUCCESS: All data (Sales, Products, Providers, Payments, etc.) has been cleared. Returning to 0.")
        
    except Exception as e:
        db.session.rollback()
        print(f"ERROR resetting database: {str(e)}")
