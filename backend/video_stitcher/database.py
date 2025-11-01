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
        
        # Create index on word column for faster lookups (if not exists)
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_word_clips_word 
                ON word_clips(word COLLATE NOCASE)
            """)
            self.connection.commit()
            logger.debug("Ensured index on word_clips.word exists")
        except Exception as e:
            logger.warning(f"Could not create index: {e}")
        
        # Check for video_transcripts table (optional for phrase matching)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='video_transcripts'
        """)
        self.has_transcripts = cursor.fetchone() is not None
        
        if self.has_transcripts:
            # Create index on video_id for faster transcript lookups
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_video_transcripts_video_id 
                    ON video_transcripts(video_id)
                """)
                self.connection.commit()
                logger.debug("Ensured index on video_transcripts.video_id exists")
            except Exception as e:
                logger.warning(f"Could not create transcript index: {e}")
            
            logger.info("Phrase matching enabled (video_transcripts table found)")
        else:
            logger.info("Phrase matching disabled (video_transcripts table not found)")
        
        logger.debug("Database schema verified")
    
    def get_clip_info(self, word: str, exclude_video_ids: Optional[List[str]] = None) -> Optional[ClipInfo]:
        """Look up clip information for a single word, optionally excluding certain videos.
        
        Args:
            word: The word to search for (case-insensitive).
            exclude_video_ids: Optional list of video IDs to exclude from results.
            
        Returns:
            ClipInfo object if word is found, None otherwise.
        """
        cursor = self.connection.cursor()
        
        if exclude_video_ids:
            # Try to find a clip from a video not in the exclusion list
            placeholders = ','.join('?' * len(exclude_video_ids))
            cursor.execute(f"""
                SELECT word, video_id, start_time, duration 
                FROM word_clips 
                WHERE LOWER(word) = LOWER(?)
                AND video_id NOT IN ({placeholders})
                LIMIT 1
            """, (word, *exclude_video_ids))
            
            row = cursor.fetchone()
            if row is not None:
                logger.debug(f"Found non-repeated video for word '{word}': {row['video_id']}")
                return ClipInfo(
                    word=row['word'],
                    video_id=row['video_id'],
                    start_time=row['start_time'],
                    duration=row['duration']
                )
            
            # If no alternative found, fall back to any video (including excluded ones)
            logger.debug(f"No alternative video found for '{word}', using any available")
        
        # Standard query without exclusions
        cursor.execute("""
            SELECT word, video_id, start_time, duration 
            FROM word_clips 
            WHERE LOWER(word) = LOWER(?)
            LIMIT 1
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
    
    def get_transcript(self, video_id: str) -> Optional[List[List]]:
        """Get the full transcript for a video.
        
        Args:
            video_id: The YouTube video ID.
            
        Returns:
            List of [word, start_time, end_time] entries, or None if not found.
        """
        if not self.has_transcripts:
            return None
        
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT transcript_data FROM video_transcripts 
            WHERE video_id = ?
        """, (video_id,))
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        import json
        return json.loads(row['transcript_data'])
    
    def find_phrase_in_transcripts(self, phrase: str, exclude_video_ids: Optional[List[str]] = None) -> Optional[ClipInfo]:
        """Find a phrase (consecutive words) in the video transcripts, optionally excluding certain videos.
        
        Args:
            phrase: Space-separated words to find as a consecutive sequence.
            exclude_video_ids: Optional list of video IDs to exclude from results.
            
        Returns:
            ClipInfo with calculated start_time and duration spanning the phrase,
            or None if phrase is not found in any video.
        """
        if not self.has_transcripts:
            return None
        
        import json
        words = phrase.lower().split()
        if not words:
            return None
        
        cursor = self.connection.cursor()
        cursor.execute("SELECT video_id, transcript_data FROM video_transcripts")
        
        # First pass: try to find in videos NOT in exclusion list
        found_excluded = None
        for row in cursor.fetchall():
            video_id = row['video_id']
            transcript = json.loads(row['transcript_data'])
            
            # Search for consecutive word sequence
            for i in range(len(transcript) - len(words) + 1):
                # Check if words match
                matches = True
                for j, word in enumerate(words):
                    if transcript[i + j][0].lower() != word:
                        matches = False
                        break
                
                if matches:
                    # Calculate start_time and duration
                    start_time = transcript[i][1]  # Start of first word
                    end_time = transcript[i + len(words) - 1][2]  # End of last word
                    duration = end_time - start_time
                    
                    clip = ClipInfo(
                        word=phrase,  # Store the full phrase
                        video_id=video_id,
                        start_time=start_time,
                        duration=duration
                    )
                    
                    # If this video is not excluded, return immediately
                    if not exclude_video_ids or video_id not in exclude_video_ids:
                        logger.info(f"Found phrase '{phrase}' in non-repeated video {video_id}: {start_time}s-{end_time}s")
                        return clip
                    
                    # Store the first match from excluded videos as fallback
                    if found_excluded is None:
                        found_excluded = clip
                        logger.debug(f"Found phrase '{phrase}' in excluded video {video_id}, continuing search...")
                    
                    break  # Only use first occurrence per video
        
        # If we only found it in excluded videos, use that as fallback
        if found_excluded is not None:
            logger.info(f"No alternative found for phrase '{phrase}', using repeated video {found_excluded.video_id}")
            return found_excluded
        
        logger.debug(f"Phrase not found in any transcript: {phrase}")
        return None
    
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
