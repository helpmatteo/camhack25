#!/usr/bin/env python3
"""Initialize the database schema."""
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "./data/youglish.db")
SCHEMA = open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r', encoding='utf8').read()

def init_database():
    """Initialize the database with schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"✓ Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_database()

