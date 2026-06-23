import os
import sqlite3
import json
from pathlib import Path

# Resolve path to project root
DB_PATH = "backend/reports.db"

def get_db_connection():
    """Returns a connection to the SQLite database. 
    Enables WAL mode to allow concurrent reads while writes occur."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Turn on Write-Ahead Logging for faster disk performance and better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Initializes the reports table if it doesn't exist yet."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            patient_name TEXT,
            age INTEGER,
            chief_complaint TEXT,
            severity TEXT,
            doctor_keyword TEXT,
            emergency_flag BOOLEAN CHECK (emergency_flag IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_state_json TEXT NOT NULL
        );
    """)
    
    # Create indexes on fields you will frequently search by
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON patient_reports(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_severity ON patient_reports(severity);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emergency ON patient_reports(emergency_flag);")
    
    conn.commit()
    conn.close()
    print(f"DATABASE LOG: SQLite database successfully initialized at {DB_PATH}")

def save_or_update_report(session_id: str, state_dict: dict):
    """Inserts or overwrites the final state document inside the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Extract structural search markers out of the state dictionary payload
    patient_name = state_dict.get("patient_name")
    age = state_dict.get("age")
    chief_complaint = state_dict.get("chief_complaint")
    severity = state_dict.get("severity")
    doctor_keyword = state_dict.get("doctor_keyword")
    emergency_flag = 1 if state_dict.get("emergency_flag") else 0
    raw_state_json = json.dumps(state_dict)

    try:
        cursor.execute("""
            INSERT INTO patient_reports (
                session_id, patient_name, age, chief_complaint, severity, doctor_keyword, emergency_flag, raw_state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                patient_name=excluded.patient_name,
                age=excluded.age,
                chief_complaint=excluded.chief_complaint,
                severity=excluded.severity,
                doctor_keyword=excluded.doctor_keyword,
                emergency_flag=excluded.emergency_flag,
                raw_state_json=excluded.raw_state_json;
        """, (session_id, patient_name, age, chief_complaint, severity, doctor_keyword, emergency_flag, raw_state_json))
        
        conn.commit()
        print(f"DATABASE LOG: Saved report session '{session_id}' to SQLite successfully.")
    except Exception as e:
        print(f"DATABASE CRITICAL ERROR: Failed to write session to SQL: {e}")
    finally:
        conn.close()