import sqlite3
import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import config
from lead_models import CustomerLead

class LeadDatabase:
    """
    SQLite Database Manager for Customer Leads.
    Provides thread-safe persistence and querying of extracted customer data.
    """
    def __init__(self, db_path: str = config.SQLITE_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates leads table if not exists."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    occupation TEXT NOT NULL,
                    income TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    product_interest TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON customer_leads(session_id);")
            conn.commit()

    def save_lead(self, lead: CustomerLead, session_id: str) -> int:
        """
        Inserts or updates customer lead for a given session.
        Returns the record id.
        """
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check if a lead already exists for this session
            cursor.execute("SELECT id FROM customer_leads WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
            row = cursor.fetchone()
            
            if row:
                lead_id = row["id"]
                cursor.execute("""
                    UPDATE customer_leads 
                    SET name = ?, occupation = ?, income = ?, phone_number = ?, product_interest = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    lead.name, lead.occupation, lead.income, lead.phone_number,
                    lead.product_interest, lead.notes, now, lead_id
                ))
            else:
                cursor.execute("""
                    INSERT INTO customer_leads (session_id, name, occupation, income, phone_number, product_interest, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, lead.name, lead.occupation, lead.income, lead.phone_number,
                    lead.product_interest, lead.notes, now, now
                ))
                lead_id = cursor.lastrowid

            conn.commit()
            return lead_id

    def get_lead_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve lead by session id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customer_leads WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_all_leads(self) -> List[Dict[str, Any]]:
        """Retrieve all leads stored in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customer_leads ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_lead_by_session(self, session_id: str):
        """Delete lead record for testing."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM customer_leads WHERE session_id = ?", (session_id,))
            conn.commit()

# Singleton instance
_db_instance: Optional[LeadDatabase] = None

def get_lead_db() -> LeadDatabase:
    global _db_instance
    if _db_instance is None:
        _db_instance = LeadDatabase()
    return _db_instance

if __name__ == "__main__":
    db = get_lead_db()
    test_lead = CustomerLead(
        name="สมชาย ใจดี",
        occupation="วิศวกรซอฟต์แวร์",
        income="75,000 บาท/เดือน",
        phone_number="0891234567",
        product_interest="ประกันชีวิต FWD",
        notes="สะดวกช่วงเย็นหลัง 18:00"
    )
    rec_id = db.save_lead(test_lead, "test_session_001")
    print(f"Saved test lead with ID: {rec_id}")
    retrieved = db.get_lead_by_session("test_session_001")
    print("Retrieved Lead:", retrieved)
