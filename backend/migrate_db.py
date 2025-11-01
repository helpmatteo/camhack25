"""
Database schema migration: Add video_transcripts table

This migration adds a new table to store complete video transcripts
with word-level timestamps, enabling efficient phrase matching.
"""

import sqlite3
from pathlib import Path

DB_PATH = "./data/youglish.db"


def migrate_database(db_path: str):
    """Add video_transcripts table to the database."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create video_transcripts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_transcripts (
            video_id TEXT PRIMARY KEY,
            transcript_data TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            duration REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_transcripts_video_id 
        ON video_transcripts(video_id)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Migration complete: video_transcripts table created")


if __name__ == "__main__":
    db_path = Path(DB_PATH)
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    
    migrate_database(str(db_path))
