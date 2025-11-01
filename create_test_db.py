"""
create_test_db.py - Creates a small test database for development and testing
"""

import sqlite3
from pathlib import Path

def create_test_database(db_path: str = "test_words.db"):
    """Create a test database with sample word-to-clip mappings."""
    
    # Remove existing database if it exists
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
        print(f"Removed existing database: {db_path}")
    
    # Create database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE word_clips (
            word TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL
        )
    """)
    
    # Sample data with real YouTube video IDs
    # Note: These are well-known public videos that should be available
    test_data = [
        # Using "Me at the zoo" - first YouTube video (jNQXAC9IVRw)
        ("hello", "jNQXAC9IVRw", 5.0, 1.5),
        ("world", "jNQXAC9IVRw", 10.0, 1.2),
        ("test", "jNQXAC9IVRw", 3.0, 1.0),
        
        # Using PSY - GANGNAM STYLE (9bZkp7q19f0)
        ("this", "9bZkp7q19f0", 20.0, 0.8),
        ("is", "9bZkp7q19f0", 25.0, 0.7),
        ("video", "9bZkp7q19f0", 30.0, 1.5),
        
        # Using popular educational content
        ("python", "kqtD5dpn9C8", 5.0, 1.3),
        ("code", "kqtD5dpn9C8", 10.0, 1.1),
        ("programming", "kqtD5dpn9C8", 15.0, 2.0),
        
        # More words for testing
        ("data", "jNQXAC9IVRw", 8.0, 0.9),
        ("structure", "9bZkp7q19f0", 35.0, 1.2),
        ("algorithm", "kqtD5dpn9C8", 20.0, 1.8),
    ]
    
    # Insert test data
    cursor.executemany("""
        INSERT INTO word_clips (word, video_id, start_time, duration)
        VALUES (?, ?, ?, ?)
    """, test_data)
    
    conn.commit()
    
    # Print statistics
    cursor.execute("SELECT COUNT(*) FROM word_clips")
    word_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT video_id) FROM word_clips")
    video_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(duration) FROM word_clips")
    avg_duration = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"Test Database Created: {db_path}")
    print(f"{'='*60}")
    print(f"Total words: {word_count}")
    print(f"Unique videos: {video_count}")
    print(f"Average clip duration: {avg_duration:.2f} seconds")
    print(f"{'='*60}\n")
    
    return db_path


if __name__ == "__main__":
    create_test_database()
    print("You can now use this database with:")
    print("  python -m video_stitcher.cli --text 'hello world' --database test_words.db")
    print("\nOr run tests with:")
    print("  pytest tests/ -v")
