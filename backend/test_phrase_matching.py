#!/usr/bin/env python3
"""Test script for phrase matching functionality."""

import sqlite3
import json
import tempfile
from pathlib import Path

from video_stitcher import VideoStitcher, StitchingConfig


def create_test_db_with_transcripts():
    """Create a test database with both word_clips and video_transcripts."""
    # Create temporary database
    db_file = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE word_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE video_transcripts (
            video_id TEXT PRIMARY KEY,
            transcript_data TEXT NOT NULL,
            word_count INTEGER,
            duration REAL
        )
    """)
    
    # Add test data
    # Video 1: "hello world how are you"
    video1_id = "test_video_1"
    video1_words = [
        ("hello", 0.0, 0.5),
        ("world", 0.5, 0.6),
        ("how", 1.1, 0.4),
        ("are", 1.5, 0.3),
        ("you", 1.8, 0.5)
    ]
    
    # Insert individual words
    for word, start, duration in video1_words:
        cursor.execute(
            "INSERT INTO word_clips (word, video_id, start_time, duration) VALUES (?, ?, ?, ?)",
            (word, video1_id, start, duration)
        )
    
    # Insert transcript
    transcript1 = [[w, st, st + dur] for w, st, dur in video1_words]
    cursor.execute(
        "INSERT INTO video_transcripts (video_id, transcript_data, word_count, duration) VALUES (?, ?, ?, ?)",
        (video1_id, json.dumps(transcript1), len(video1_words), 2.3)
    )
    
    # Video 2: "the quick brown fox"
    video2_id = "test_video_2"
    video2_words = [
        ("the", 0.0, 0.3),
        ("quick", 0.3, 0.5),
        ("brown", 0.8, 0.6),
        ("fox", 1.4, 0.4)
    ]
    
    # Insert individual words
    for word, start, duration in video2_words:
        cursor.execute(
            "INSERT INTO word_clips (word, video_id, start_time, duration) VALUES (?, ?, ?, ?)",
            (word, video2_id, start, duration)
        )
    
    # Insert transcript
    transcript2 = [[w, st, st + dur] for w, st, dur in video2_words]
    cursor.execute(
        "INSERT INTO video_transcripts (video_id, transcript_data, word_count, duration) VALUES (?, ?, ?, ?)",
        (video2_id, json.dumps(transcript2), len(video2_words), 1.8)
    )
    
    # Add a standalone word not in any phrase
    cursor.execute(
        "INSERT INTO word_clips (word, video_id, start_time, duration) VALUES (?, ?, ?, ?)",
        ("goodbye", "test_video_3", 0.0, 0.8)
    )
    
    conn.commit()
    conn.close()
    
    print(f"Created test database: {db_path}")
    print(f"Video 1 ({video1_id}): {' '.join([w for w, _, _ in video1_words])}")
    print(f"Video 2 ({video2_id}): {' '.join([w for w, _, _ in video2_words])}")
    print()
    
    return db_path


def test_phrase_matching(db_path):
    """Test phrase matching functionality."""
    print("=" * 60)
    print("Testing Phrase Matching")
    print("=" * 60)
    print()
    
    # Create stitcher (without ffmpeg verification for testing)
    config = StitchingConfig(
        database_path=db_path,
        output_directory="./test_output",
        verify_ffmpeg_on_init=False
    )
    
    stitcher = VideoStitcher(config)
    
    # Test 1: Single words
    print("Test 1: Single words lookup")
    words = ["hello", "fox", "goodbye"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips: {[c.word for c in clips]}")
    print(f"  Missing: {missing}")
    assert len(clips) == 3
    assert len(missing) == 0
    print("  ✓ Passed")
    print()
    
    # Test 2: Two-word phrase from same video
    print("Test 2: Two-word phrase 'hello world'")
    words = ["hello", "world"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips")
    for clip in clips:
        print(f"    - '{clip.word}' from {clip.video_id} ({clip.start_time}s, {clip.duration:.2f}s)")
    assert len(clips) == 1  # Should be combined into one phrase
    assert clips[0].word == "hello world"
    assert clips[0].video_id == "test_video_1"
    assert abs(clips[0].start_time - 0.0) < 0.01
    assert abs(clips[0].duration - 1.1) < 0.01  # 0.0 to 1.1
    print("  ✓ Passed - Combined into single clip!")
    print()
    
    # Test 3: Longer phrase
    print("Test 3: Four-word phrase 'how are you' (skipping 'world')")
    words = ["how", "are", "you"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips")
    for clip in clips:
        print(f"    - '{clip.word}' from {clip.video_id} ({clip.start_time}s, {clip.duration:.2f}s)")
    assert len(clips) == 1  # Should be combined
    assert clips[0].word == "how are you"
    print("  ✓ Passed - Combined into single clip!")
    print()
    
    # Test 4: Mixed - phrase + individual word
    print("Test 4: Mixed lookup 'the quick brown goodbye'")
    words = ["the", "quick", "brown", "goodbye"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips")
    for clip in clips:
        print(f"    - '{clip.word}' from {clip.video_id} ({clip.start_time}s, {clip.duration:.2f}s)")
    assert len(clips) == 2  # "the quick brown" as one, "goodbye" as another
    assert clips[0].word == "the quick brown"
    assert clips[0].video_id == "test_video_2"
    assert clips[1].word == "goodbye"
    assert clips[1].video_id == "test_video_3"
    print("  ✓ Passed - Correctly mixed phrase + individual!")
    print()
    
    # Test 5: Words from different videos (no phrase match)
    print("Test 5: Words from different videos 'hello quick'")
    words = ["hello", "quick"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips")
    for clip in clips:
        print(f"    - '{clip.word}' from {clip.video_id} ({clip.start_time}s, {clip.duration:.2f}s)")
    assert len(clips) == 2  # Can't combine - different videos
    assert clips[0].word == "hello"
    assert clips[1].word == "quick"
    print("  ✓ Passed - Correctly kept separate (different videos)!")
    print()
    
    # Test 6: Missing word handling
    print("Test 6: Missing word 'notfound' in middle")
    words = ["hello", "notfound", "world"]
    clips, missing = stitcher.lookup_clips(words)
    print(f"  Input: {words}")
    print(f"  Found {len(clips)} clips: {[c.word for c in clips]}")
    print(f"  Missing: {missing}")
    assert len(clips) == 2  # "hello" and "world" separate (missing word breaks phrase)
    assert clips[0].word == "hello"
    assert clips[1].word == "world"
    assert len(missing) == 1
    assert missing[0] == "notfound"
    print("  ✓ Passed - Missing word correctly breaks phrase!")
    print()
    
    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


def main():
    """Run the tests."""
    # Create test database
    db_path = create_test_db_with_transcripts()
    
    try:
        # Run tests
        test_phrase_matching(db_path)
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
        print(f"\nCleaned up test database")


if __name__ == "__main__":
    main()
