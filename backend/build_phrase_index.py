#!/usr/bin/env python3
"""
Build Phrase N-gram Index from Existing Transcripts

This script extracts 2-5 word phrases from video transcripts and builds
an indexed lookup table for fast phrase matching.

Run once after adding the phrase_index table:
    python build_phrase_index.py

Expected time: ~5-10 minutes for 10,000 videos
"""

import sqlite3
import json
import hashlib
import time
from pathlib import Path
from typing import List, Tuple

DB_PATH = "./data/youglish.db"


def normalize_phrase(phrase: str) -> str:
    """Normalize phrase for consistent matching."""
    return phrase.lower().strip()


def phrase_hash(phrase: str) -> str:
    """Generate MD5 hash of normalized phrase for fast lookup."""
    normalized = normalize_phrase(phrase)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def extract_phrases(transcript: List[List], phrase_length: int) -> List[Tuple[str, float, float]]:
    """Extract all phrases of given length from transcript.
    
    Args:
        transcript: List of [word, start_time, end_time] entries
        phrase_length: Number of words in phrase (2-5)
        
    Returns:
        List of (phrase_text, start_time, end_time) tuples
    """
    phrases = []
    
    for i in range(len(transcript) - phrase_length + 1):
        # Extract words for this phrase
        words = [transcript[i + j][0] for j in range(phrase_length)]
        phrase_text = ' '.join(words)
        
        # Get start and end times
        start_time = transcript[i][1]  # Start of first word
        end_time = transcript[i + phrase_length - 1][2]  # End of last word
        
        phrases.append((phrase_text, start_time, end_time))
    
    return phrases


def build_phrase_index(db_path: str, phrase_lengths: List[int] = [2, 3, 4, 5], batch_size: int = 1000):
    """Build phrase index from all video transcripts.
    
    Args:
        db_path: Path to SQLite database
        phrase_lengths: List of phrase lengths to index (default: 2-5 words)
        batch_size: Number of phrases to insert at once
    """
    print(f"🔨 Building phrase index from transcripts...")
    print(f"   Database: {db_path}")
    print(f"   Phrase lengths: {phrase_lengths}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if phrase_index table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='phrase_index'
    """)
    if not cursor.fetchone():
        print("❌ Error: phrase_index table doesn't exist")
        print("   Run: sqlite3 data/youglish.db < backend/add_phrase_index.sql")
        conn.close()
        return
    
    # Clear existing data (in case we're rebuilding)
    print("🗑️  Clearing existing phrase index...")
    cursor.execute("DELETE FROM phrase_index")
    conn.commit()
    
    # Get total number of transcripts
    cursor.execute("SELECT COUNT(*) as count FROM video_transcripts")
    total_videos = cursor.fetchone()['count']
    
    if total_videos == 0:
        print("❌ No transcripts found in database")
        print("   Run: python ingest_whisperx.py to populate transcripts")
        conn.close()
        return
    
    print(f"📊 Processing {total_videos} video transcripts...")
    
    # Fetch all transcripts
    cursor.execute("SELECT video_id, transcript_data FROM video_transcripts")
    
    batch = []
    total_phrases = 0
    processed_videos = 0
    start_time = time.time()
    
    for row in cursor.fetchall():
        video_id = row['video_id']
        transcript = json.loads(row['transcript_data'])
        
        # Extract phrases of each length
        for phrase_length in phrase_lengths:
            phrases = extract_phrases(transcript, phrase_length)
            
            for phrase_text, start, end in phrases:
                # Generate hash for fast lookup
                p_hash = phrase_hash(phrase_text)
                
                batch.append((
                    p_hash,
                    phrase_text,
                    video_id,
                    start,
                    end,
                    phrase_length
                ))
                total_phrases += 1
            
            # Insert batch
            if len(batch) >= batch_size:
                cursor.executemany("""
                    INSERT OR IGNORE INTO phrase_index 
                    (phrase_hash, phrase_text, video_id, start_time, end_time, word_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                batch = []
        
        processed_videos += 1
        
        # Progress update every 100 videos
        if processed_videos % 100 == 0:
            elapsed = time.time() - start_time
            rate = processed_videos / elapsed
            eta = (total_videos - processed_videos) / rate if rate > 0 else 0
            print(f"   Progress: {processed_videos}/{total_videos} videos "
                  f"({processed_videos/total_videos*100:.1f}%) - "
                  f"{total_phrases:,} phrases - "
                  f"ETA: {eta/60:.1f}m")
    
    # Insert remaining batch
    if batch:
        cursor.executemany("""
            INSERT OR IGNORE INTO phrase_index 
            (phrase_hash, phrase_text, video_id, start_time, end_time, word_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
    
    # Get final statistics
    cursor.execute("SELECT COUNT(*) as count FROM phrase_index")
    indexed_phrases = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(DISTINCT phrase_hash) as count FROM phrase_index")
    unique_phrases = cursor.fetchone()['count']
    
    elapsed = time.time() - start_time
    
    print(f"\n✅ Phrase index built successfully!")
    print(f"   Videos processed: {processed_videos:,}")
    print(f"   Total phrase entries: {indexed_phrases:,}")
    print(f"   Unique phrases: {unique_phrases:,}")
    print(f"   Time taken: {elapsed/60:.1f} minutes")
    print(f"   Rate: {processed_videos/elapsed:.1f} videos/sec")
    
    # Show breakdown by phrase length
    print(f"\n📊 Phrase breakdown:")
    for length in phrase_lengths:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM phrase_index 
            WHERE word_count = ?
        """, (length,))
        count = cursor.fetchone()['count']
        print(f"   {length}-word phrases: {count:,}")
    
    # Show some sample phrases
    print(f"\n🔍 Sample phrases (3-word):")
    cursor.execute("""
        SELECT phrase_text, COUNT(*) as occurrences
        FROM phrase_index
        WHERE word_count = 3
        GROUP BY phrase_text
        ORDER BY occurrences DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"   '{row['phrase_text']}' - {row['occurrences']} occurrences")
    
    # Analyze for query optimization
    print(f"\n🔧 Running ANALYZE for query optimization...")
    cursor.execute("ANALYZE phrase_index")
    conn.commit()
    
    # Check database size
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()['size']
    print(f"\n💾 Database size: {db_size / (1024*1024):.1f} MB")
    
    conn.close()
    print(f"\n🎉 Done! Phrase index is ready for fast lookups.")


def test_phrase_lookup(db_path: str, test_phrases: List[str]):
    """Test phrase lookup performance.
    
    Args:
        db_path: Path to SQLite database
        test_phrases: List of phrases to test
    """
    print(f"\n🧪 Testing phrase lookup performance...")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    for phrase in test_phrases:
        p_hash = phrase_hash(phrase)
        
        start = time.time()
        cursor.execute("""
            SELECT video_id, start_time, end_time
            FROM phrase_index
            WHERE phrase_hash = ?
            LIMIT 1
        """, (p_hash,))
        result = cursor.fetchone()
        elapsed = time.time() - start
        
        if result:
            print(f"   ✓ '{phrase}' - Found in {elapsed*1000:.2f}ms (video: {result['video_id']})")
        else:
            print(f"   ✗ '{phrase}' - Not found ({elapsed*1000:.2f}ms)")
    
    conn.close()


if __name__ == "__main__":
    db_path = Path(DB_PATH)
    
    if not db_path.exists():
        print(f"❌ Database not found: {DB_PATH}")
        print("   Make sure you're running from the backend directory")
        exit(1)
    
    # Build the index
    build_phrase_index(str(db_path))
    
    # Test with some common phrases
    test_phrases = [
        "how do you",
        "thank you very",
        "nice to meet",
        "see you later",
        "have a good"
    ]
    test_phrase_lookup(str(db_path), test_phrases)

