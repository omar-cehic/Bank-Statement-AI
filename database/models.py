import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self, db_path="database/database.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_database(self):
        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = self.get_connection()
        cursor = conn.cursor()

        # Create transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                description TEXT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                balance DECIMAL(10,2),
                category TEXT,
                confidence_score DECIMAL(3,2) DEFAULT 0.0,
                statement_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create statements table to track uploaded files
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                s3_key TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT 0,
                transaction_count INTEGER DEFAULT 0
            )
        ''')

        conn.commit()
        conn.close()

    def transaction_exists(self, date, description, amount, conn):
        """
        Check if a transaction with the same date, description, and amount
        already exists in the database.

        Args:
            date (str): Transaction date in YYYY-MM-DD format
            description (str): Transaction description
            amount (float): Transaction amount (signed — negative for credits)
            conn: Active database connection to reuse

        Returns:
            bool: True if a matching transaction already exists
        """
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM transactions WHERE date = ? AND description = ? AND amount = ? LIMIT 1",
            (date, description, amount)
        )
        return cursor.fetchone() is not None

    def test_connection(self):
        """Test database connection and return basic info"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get table count
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            # Get transaction count
            cursor.execute("SELECT COUNT(*) FROM transactions")
            transaction_count = cursor.fetchone()[0]

            conn.close()

            return {
                'status': 'connected',
                'tables': [table[0] for table in tables],
                'transaction_count': transaction_count
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}