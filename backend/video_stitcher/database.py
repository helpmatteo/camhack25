"""Database interface module for querying word-to-clip mappings."""

import sqlite3
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ClipInfo:
    """Information about a video clip for a word."""
    word: str
    video_id: str
    start_time: float
    duration: float


class WordClipDatabase:
    """Database interface for looking up video clips by word."""
    
    def __init__(self, db_path: str):
        """Initialize database connection.
        
        Args:
            db_path: Path to the SQLite database file.
            
        Raises:
            FileNotFoundError: If database file doesn't exist.
            ValueError: If database schema is invalid.
        """
        self.db_path = Path(db_path)
        
        # Verify database file exists
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        # Open SQLite connection
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        
        # Verify table schema
        self._verify_schema()
        
        logger.info(f"Database opened: {db_path}")
    
    def _verify_schema(self) -> None:
        """Verify that the word_clips table exists with correct schema.
        
        Raises:
            ValueError: If table doesn't exist or schema is incorrect.
        """
        cursor = self.connection.cursor()
        
        # Check if word_clips table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='word_clips'
        """)
        
        if cursor.fetchone() is None:
            raise ValueError("Table 'word_clips' does not exist in database")
        
        # Verify columns
        cursor.execute("PRAGMA table_info(word_clips)")
        columns = {row['name'] for row in cursor.fetchall()}
        required_columns = {'word', 'video_id', 'start_time', 'duration'}
        
        if not required_columns.issubset(columns):
            missing = required_columns - columns
            raise ValueError(f"Missing required columns in word_clips table: {missing}")
        
        logger.debug("Database schema verified")
    
    def get_clip_info(self, word: str) -> Optional[ClipInfo]:
        """Look up clip information for a single word.
        
        Args:
            word: The word to search for (case-insensitive).
            
        Returns:
            ClipInfo object if word is found, None otherwise.
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT word, video_id, start_time, duration 
            FROM word_clips 
            WHERE LOWER(word) = LOWER(?)
        """, (word,))
        
        row = cursor.fetchone()
        if row is None:
            logger.debug(f"Word not found in database: {word}")
            return None
        
        return ClipInfo(
            word=row['word'],
            video_id=row['video_id'],
            start_time=row['start_time'],
            duration=row['duration']
        )
    
    def get_clips_for_words(self, words: List[str]) -> List[Optional[ClipInfo]]:
        """Look up clip information for multiple words.
        
        Args:
            words: List of words to search for.
            
        Returns:
            List of ClipInfo objects (or None for missing words) in same order as input.
        """
        if not words:
            return []
        
        cursor = self.connection.cursor()
        
        # Build query with placeholders
        placeholders = ','.join('?' * len(words))
        query = f"""
            SELECT word, video_id, start_time, duration 
            FROM word_clips 
            WHERE LOWER(word) IN ({placeholders})
        """
        
        # Execute query with lowercase words
        cursor.execute(query, [w.lower() for w in words])
        
        # Build dictionary of results (lowercase key)
        results = {}
        for row in cursor.fetchall():
            results[row['word'].lower()] = ClipInfo(
                word=row['word'],
                video_id=row['video_id'],
                start_time=row['start_time'],
                duration=row['duration']
            )
        
        # Build output list maintaining input order
        output = []
        for word in words:
            clip_info = results.get(word.lower())
            if clip_info is None:
                logger.warning(f"Word not found in database: {word}")
            output.append(clip_info)
        
        return output
    
    def get_database_stats(self) -> dict:
        """Get statistics about the database.
        
        Returns:
            Dictionary with keys: total_words, unique_videos, avg_duration.
        """
        cursor = self.connection.cursor()
        
        # Count total words
        cursor.execute("SELECT COUNT(*) as count FROM word_clips")
        total_words = cursor.fetchone()['count']
        
        # Count unique videos
        cursor.execute("SELECT COUNT(DISTINCT video_id) as count FROM word_clips")
        unique_videos = cursor.fetchone()['count']
        
        # Calculate average duration
        cursor.execute("SELECT AVG(duration) as avg FROM word_clips")
        avg_duration = cursor.fetchone()['avg'] or 0.0
        
        stats = {
            'total_words': total_words,
            'unique_videos': unique_videos,
            'avg_duration': avg_duration
        }
        
        logger.info(f"Database stats: {stats}")
        return stats
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        self.close()
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()
            logger.debug("Database connection closed")
