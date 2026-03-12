import pandas as pd
from sqlalchemy import create_engine
import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# ==========================================
# CONFIGURATION
# ==========================================

# 1. SETUP FIREBASE
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. SETUP POSTGRESQL (Update your password)
# Replace 'your_app_name' with the actual name of your Django app (e.g., 'core', 'api', 'fireapp')
DB_CONNECTION_STR = (
    "postgresql://postgres:YOUR_PASSWORD@localhost:5432/fire_monitoring_db"
)
db_connection = create_engine(DB_CONNECTION_STR)

# 3. DEFINE TABLES TO MIGRATE
# We list them in order so "parent" data (like Users/Addresses) goes first.
# 'auth_user' is the default Django user table.
TABLE_MAP = {
    "auth_user": "users_auth",
    "sensors_address": "addresses",
    "sensors_firestation": "fire_stations",
    "sensors_userprofile": "user_profiles",
    "sensors_houselayout": "house_layouts",
    "sensors_dutyassignment": "duty_assignments",
    "sensors_sensor": "sensors",
    "sensors_sensordatalog": "sensor_logs",
    "sensors_maintenance": "maintenance_records",
    "sensors_report": "incident_reports",
}


# ==========================================
# MIGRATION LOGIC
# ==========================================
def migrate():
    print("🚀 Starting Full Database Migration...\n")

    for sql_table, firebase_collection in TABLE_MAP.items():
        print(f"--> Processing Table: '{sql_table}'...")

        try:
            # 1. Read from Postgres
            df = pd.read_sql(sql_table, db_connection)

            # 2. Clean Data
            # Convert all data to string first to avoid serialization errors with unique SQL types
            # (You can remove .astype(str) if you want to keep integers as numbers,
            #  but dates often cause issues if not converted)
            df = df.applymap(
                lambda x: (
                    str(x) if isinstance(x, (datetime.date, datetime.datetime)) else x
                )
            )

            # Fix Empty values (NaN) -> None (Null)
            df = df.where(pd.notnull(df), None)

            records = df.to_dict(orient="records")
            total_records = len(records)
            print(
                f"    Found {total_records} rows. Uploading to '{firebase_collection}'..."
            )

            if total_records == 0:
                print("    Skipping (Table is empty).")
                continue

            # 3. Upload to Firestore in Batches
            batch = db.batch()
            count = 0
            total_uploaded = 0

            for row in records:
                # Use the SQL 'id' as the Document ID to keep relationships working
                doc_id = str(row["id"])

                doc_ref = db.collection(firebase_collection).document(doc_id)
                batch.set(doc_ref, row)

                count += 1
                total_uploaded += 1

                # Commit every 400 documents (Firestore limit is 500)
                if count >= 400:
                    batch.commit()
                    batch = db.batch()
                    print(f"    ...committed {total_uploaded} records")
                    count = 0

            # Commit leftovers
            if count > 0:
                batch.commit()

            print(f"    ✅ Successfully finished '{firebase_collection}'\n")

        except Exception as e:
            print(f"    ❌ Error migrating '{sql_table}': {e}\n")

    print("🎉 All Tables Processed!")


if __name__ == "__main__":
    migrate()
