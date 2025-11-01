"""Comprehensive tests for the video stitcher system."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from video_stitcher.database import WordClipDatabase, ClipInfo


# Test Database Generator Fixture
@pytest.fixture
def test_database(tmp_path):
    """Create a test SQLite database with sample word-clip mappings.
    
    This fixture creates a database with 15 sample words mapped to various
    YouTube videos with different durations.
    
    Args:
        tmp_path: pytest temporary directory fixture.
        
    Returns:
        Path to the test database file.
    """
    db_path = tmp_path / "test_words.db"
    
    # Create database and table
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create the word_clips table
    cursor.execute("""
        CREATE TABLE word_clips (
            word TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL
        )
    """)
    
    # Sample data with real YouTube video IDs (educational/public domain content)
    # Note: These are example IDs - in production, ensure videos are available
    test_data = [
        ("hello", "jNQXAC9IVRw", 5.0, 1.5),      # "Me at the zoo" - first YouTube video
        ("world", "jNQXAC9IVRw", 10.0, 1.2),     
        ("test", "jNQXAC9IVRw", 15.0, 1.0),
        ("this", "9bZkp7q19f0", 20.0, 0.8),      # PSY - GANGNAM STYLE
        ("is", "9bZkp7q19f0", 25.0, 0.7),
        ("video", "9bZkp7q19f0", 30.0, 1.5),
        ("python", "kqtD5dpn9C8", 5.0, 1.3),     # Python programming content
        ("code", "kqtD5dpn9C8", 10.0, 1.1),
        ("programming", "kqtD5dpn9C8", 15.0, 2.0),
        ("computer", "dQw4w9WgXcQ", 5.0, 1.4),   # Rick Astley - Never Gonna Give You Up
        ("science", "dQw4w9WgXcQ", 10.0, 1.6),
        ("algorithm", "dQw4w9WgXcQ", 15.0, 1.8),
        ("data", "OPf0YbXqDm0", 5.0, 0.9),       # Mark Rober video
        ("structure", "OPf0YbXqDm0", 10.0, 1.2),
        ("learning", "OPf0YbXqDm0", 15.0, 1.7),
    ]
    
    # Insert test data
    cursor.executemany("""
        INSERT INTO word_clips (word, video_id, start_time, duration)
        VALUES (?, ?, ?, ?)
    """, test_data)
    
    conn.commit()
    conn.close()
    
    return str(db_path)


# Database Module Tests
class TestDatabase:
    """Test the database interface module."""
    
    def test_database_connection_success(self, test_database):
        """Test that database opens successfully with valid path."""
        db = WordClipDatabase(test_database)
        assert db.connection is not None
        db.close()
    
    def test_database_connection_failure(self, tmp_path):
        """Test that FileNotFoundError is raised with invalid path."""
        invalid_path = tmp_path / "nonexistent.db"
        
        with pytest.raises(FileNotFoundError):
            WordClipDatabase(str(invalid_path))
    
    def test_get_clip_info_existing_word(self, test_database):
        """Test get_clip_info returns correct data for existing word."""
        db = WordClipDatabase(test_database)
        
        clip_info = db.get_clip_info("hello")
        
        assert clip_info is not None
        assert clip_info.word == "hello"
        assert clip_info.video_id == "jNQXAC9IVRw"
        assert clip_info.start_time == 5.0
        assert clip_info.duration == 1.5
        
        db.close()
    
    def test_get_clip_info_case_insensitive(self, test_database):
        """Test get_clip_info is case-insensitive."""
        db = WordClipDatabase(test_database)
        
        clip_info = db.get_clip_info("HELLO")
        
        assert clip_info is not None
        assert clip_info.word == "hello"
        
        db.close()
    
    def test_get_clip_info_missing_word(self, test_database):
        """Test get_clip_info returns None for missing word."""
        db = WordClipDatabase(test_database)
        
        clip_info = db.get_clip_info("nonexistent")
        
        assert clip_info is None
        
        db.close()
    
    def test_get_clips_for_words_maintains_order(self, test_database):
        """Test batch lookup maintains word order."""
        db = WordClipDatabase(test_database)
        
        words = ["world", "hello", "test"]
        results = db.get_clips_for_words(words)
        
        assert len(results) == 3
        assert results[0].word == "world"
        assert results[1].word == "hello"
        assert results[2].word == "test"
        
        db.close()
    
    def test_get_clips_for_words_mixed(self, test_database):
        """Test batch lookup handles mix of found/missing words."""
        db = WordClipDatabase(test_database)
        
        words = ["hello", "missing", "world"]
        results = db.get_clips_for_words(words)
        
        assert len(results) == 3
        assert results[0] is not None
        assert results[0].word == "hello"
        assert results[1] is None
        assert results[2] is not None
        assert results[2].word == "world"
        
        db.close()
    
    def test_get_database_stats(self, test_database):
        """Test database statistics are accurate."""
        db = WordClipDatabase(test_database)
        
        stats = db.get_database_stats()
        
        assert stats['total_words'] == 15
        assert stats['unique_videos'] == 5
        assert stats['avg_duration'] > 0
        
        db.close()
    
    def test_context_manager(self, test_database):
        """Test database works as context manager."""
        with WordClipDatabase(test_database) as db:
            clip_info = db.get_clip_info("hello")
            assert clip_info is not None


# Helper function to create a minimal test database
@pytest.fixture
def minimal_test_database(tmp_path):
    """Create a minimal test database with just 3 words for quick testing."""
    db_path = tmp_path / "minimal_test.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE word_clips (
            word TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL
        )
    """)
    
    # Minimal data for quick tests
    test_data = [
        ("hello", "jNQXAC9IVRw", 5.0, 1.0),
        ("world", "jNQXAC9IVRw", 10.0, 1.0),
        ("test", "jNQXAC9IVRw", 15.0, 1.0),
    ]
    
    cursor.executemany("""
        INSERT INTO word_clips (word, video_id, start_time, duration)
        VALUES (?, ?, ?, ?)
    """, test_data)
    
    conn.commit()
    conn.close()
    
    return str(db_path)


# Video Stitcher Module Tests
class TestVideoStitcher:
    """Test the main video stitcher module."""
    
    def test_parse_text(self, minimal_test_database):
        """Test text parsing extracts words correctly."""
        from video_stitcher.video_stitcher import VideoStitcher, StitchingConfig
        
        config = StitchingConfig(
            database_path=minimal_test_database,
            verify_ffmpeg_on_init=False  # Skip ffmpeg verification for this test
        )
        stitcher = VideoStitcher(config)
        
        text = "Hello, world! This is a TEST."
        words = stitcher.parse_text(text)
        
        assert words == ["hello", "world", "this", "is", "a", "test"]
        
        stitcher.close()
    
    def test_lookup_clips(self, minimal_test_database):
        """Test clip lookup separates found and missing words."""
        from video_stitcher.video_stitcher import VideoStitcher, StitchingConfig
        
        config = StitchingConfig(
            database_path=minimal_test_database,
            verify_ffmpeg_on_init=False  # Skip ffmpeg verification for this test
        )
        stitcher = VideoStitcher(config)
        
        words = ["hello", "missing", "world"]
        found_clips, missing_words = stitcher.lookup_clips(words)
        
        assert len(found_clips) == 2
        assert len(missing_words) == 1
        assert missing_words[0] == "missing"
        
        stitcher.close()


# Error Handling Tests
class TestErrorHandling:
    """Test error handling throughout the system."""
    
    def test_invalid_database_schema(self, tmp_path):
        """Test that ValueError is raised for invalid schema."""
        db_path = tmp_path / "invalid_schema.db"
        
        # Create database with wrong schema
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE word_clips (wrong_column TEXT)")
        conn.commit()
        conn.close()
        
        with pytest.raises(ValueError, match="Missing required columns"):
            WordClipDatabase(str(db_path))
    
    def test_missing_table(self, tmp_path):
        """Test that ValueError is raised when table doesn't exist."""
        db_path = tmp_path / "no_table.db"
        
        # Create empty database
        conn = sqlite3.connect(str(db_path))
        conn.close()
        
        with pytest.raises(ValueError, match="Table 'word_clips' does not exist"):
            WordClipDatabase(str(db_path))


# Integration test placeholder (requires network and ffmpeg)
@pytest.mark.skip(reason="End-to-end test requires network access and ffmpeg")
def test_generate_video_end_to_end(minimal_test_database, tmp_path):
    """Test complete video generation from text.
    
    This test is skipped by default as it requires:
    - Network access to download YouTube videos
    - ffmpeg installed and available
    - Significant time to complete
    
    To run this test manually:
    pytest -v -k test_generate_video_end_to_end --run-network-tests
    """
    from video_stitcher.video_stitcher import VideoStitcher, StitchingConfig
    
    config = StitchingConfig(
        database_path=minimal_test_database,
        output_directory=str(tmp_path / "output"),
        temp_directory=str(tmp_path / "temp"),
        cleanup_temp_files=False  # Keep files for inspection
    )
    
    with VideoStitcher(config) as stitcher:
        output_path = stitcher.generate_video(
            text="hello world test",
            output_filename="test_output.mp4"
        )
        
        # Verify output exists
        assert Path(output_path).exists()
        assert Path(output_path).stat().st_size > 0
        
        # Verify it's a valid video (basic check)
        from video_stitcher.video_processor import VideoProcessor
        processor = VideoProcessor()
        properties = processor.verify_video_properties(output_path)
        
        assert properties['duration'] > 0
        assert properties['width'] > 0
        assert properties['height'] > 0


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
