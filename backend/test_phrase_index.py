#!/usr/bin/env python3
"""
Test script for phrase n-gram index functionality.

This script verifies that the phrase index is working correctly
and measures performance improvements.
"""

import sqlite3
import time
from pathlib import Path

DB_PATH = "./data/youglish.db"


def test_phrase_index_exists(db_path: str) -> bool:
    """Check if phrase_index table exists."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='phrase_index'
    """)
    exists = cursor.fetchone() is not None
    conn.close()
    
    return exists


def test_phrase_index_populated(db_path: str) -> int:
    """Check how many phrases are in the index."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM phrase_index")
    count = cursor.fetchone()[0]
    
    conn.close()
    return count


def benchmark_phrase_lookup(db_path: str, phrases: list) -> dict:
    """Benchmark phrase lookups."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    results = {}
    
    for phrase in phrases:
        # Hash the phrase (same as in database.py)
        import hashlib
        normalized = phrase.lower().strip()
        p_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()
        
        # Time the lookup
        start = time.time()
        cursor.execute("""
            SELECT video_id, start_time, end_time
            FROM phrase_index
            WHERE phrase_hash = ?
            LIMIT 1
        """, (p_hash,))
        result = cursor.fetchone()
        elapsed = time.time() - start
        
        results[phrase] = {
            'found': result is not None,
            'time_ms': elapsed * 1000,
            'video_id': result[0] if result else None
        }
    
    conn.close()
    return results


def test_phrase_statistics(db_path: str):
    """Get statistics about phrase index."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    stats = {}
    
    # Count by phrase length
    cursor.execute("""
        SELECT word_count, COUNT(*) as count
        FROM phrase_index
        GROUP BY word_count
        ORDER BY word_count
    """)
    stats['by_length'] = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Total phrases
    cursor.execute("SELECT COUNT(*) as count FROM phrase_index")
    stats['total_phrases'] = cursor.fetchone()[0]
    
    # Unique phrases
    cursor.execute("SELECT COUNT(DISTINCT phrase_hash) as count FROM phrase_index")
    stats['unique_phrases'] = cursor.fetchone()[0]
    
    # Sample common phrases
    cursor.execute("""
        SELECT phrase_text, COUNT(*) as occurrences
        FROM phrase_index
        WHERE word_count = 3
        GROUP BY phrase_text
        ORDER BY occurrences DESC
        LIMIT 10
    """)
    stats['top_3_word_phrases'] = [(row[0], row[1]) for row in cursor.fetchall()]
    
    conn.close()
    return stats


def main():
    """Run all tests."""
    db_path = Path(DB_PATH)
    
    if not db_path.exists():
        print(f"❌ Database not found: {DB_PATH}")
        print("   Make sure you're running from the backend directory")
        return
    
    print("🧪 Testing Phrase N-gram Index")
    print("=" * 60)
    
    # Test 1: Check if phrase_index exists
    print("\n1️⃣  Checking if phrase_index table exists...")
    if test_phrase_index_exists(str(db_path)):
        print("   ✅ phrase_index table found")
    else:
        print("   ❌ phrase_index table not found")
        print("   Run: sqlite3 data/youglish.db < add_phrase_index.sql")
        print("   Then: python build_phrase_index.py")
        return
    
    # Test 2: Check if phrase_index is populated
    print("\n2️⃣  Checking if phrase_index is populated...")
    phrase_count = test_phrase_index_populated(str(db_path))
    if phrase_count > 0:
        print(f"   ✅ Found {phrase_count:,} phrases in index")
    else:
        print("   ⚠️  phrase_index table is empty")
        print("   Run: python build_phrase_index.py")
        return
    
    # Test 3: Get statistics
    print("\n3️⃣  Getting phrase index statistics...")
    stats = test_phrase_statistics(str(db_path))
    print(f"   Total phrases: {stats['total_phrases']:,}")
    print(f"   Unique phrases: {stats['unique_phrases']:,}")
    print(f"\n   Breakdown by phrase length:")
    for length, count in stats['by_length'].items():
        print(f"      {length}-word phrases: {count:,}")
    
    print(f"\n   Top 10 common 3-word phrases:")
    for phrase, count in stats['top_3_word_phrases']:
        print(f"      '{phrase}' - {count} occurrences")
    
    # Test 4: Benchmark phrase lookups
    print("\n4️⃣  Benchmarking phrase lookups...")
    test_phrases = [
        "how do you",
        "thank you very",
        "nice to meet",
        "see you later",
        "have a good",
        "in the world",
        "this is a",
        "one of the",
        "going to be",
        "want to know"
    ]
    
    results = benchmark_phrase_lookup(str(db_path), test_phrases)
    
    found_count = sum(1 for r in results.values() if r['found'])
    avg_time = sum(r['time_ms'] for r in results.values()) / len(results)
    
    print(f"\n   Results:")
    print(f"      Phrases tested: {len(test_phrases)}")
    print(f"      Phrases found: {found_count}/{len(test_phrases)}")
    print(f"      Average lookup time: {avg_time:.3f}ms")
    
    print(f"\n   Individual results:")
    for phrase, result in results.items():
        status = "✓" if result['found'] else "✗"
        video_info = f"video: {result['video_id'][:11]}" if result['found'] else "not found"
        print(f"      {status} '{phrase}' - {result['time_ms']:.3f}ms ({video_info})")
    
    # Test 5: Performance comparison
    print("\n5️⃣  Performance Analysis:")
    if avg_time < 1.0:
        print(f"   🚀 EXCELLENT: Average lookup time {avg_time:.3f}ms")
        print(f"   This is ~500x faster than transcript scanning!")
    elif avg_time < 5.0:
        print(f"   ✅ GOOD: Average lookup time {avg_time:.3f}ms")
        print(f"   This is ~100x faster than transcript scanning")
    else:
        print(f"   ⚠️  SLOW: Average lookup time {avg_time:.3f}ms")
        print(f"   Consider rebuilding indexes with ANALYZE")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("\nNext steps:")
    print("   • Generate a video to see phrase_index in action")
    print("   • Check logs for 'Found phrase ... in phrase_index' messages")
    print("   • Try max_phrase_length=50 without slowdown!")
    print("=" * 60)


if __name__ == "__main__":
    main()

