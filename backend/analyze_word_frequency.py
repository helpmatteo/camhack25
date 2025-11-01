"""
Analyze word frequency in the database to identify most common words
that should be pre-downloaded for optimal performance.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = "./data/youglish.db"


def analyze_word_frequency():
    """Analyze word frequency distribution in the database."""
    
    print("="*60)
    print("Word Frequency Analysis")
    print("="*60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get total unique words
    cursor.execute("SELECT COUNT(DISTINCT word) FROM word_clips")
    total_unique_words = cursor.fetchone()[0]
    
    # Get total clips
    cursor.execute("SELECT COUNT(*) FROM word_clips")
    total_clips = cursor.fetchone()[0]
    
    print(f"\nDataset Statistics:")
    print(f"  Total unique words: {total_unique_words:,}")
    print(f"  Total clips: {total_clips:,}")
    print(f"  Average clips per word: {total_clips / total_unique_words:.1f}")
    
    # Analyze frequency distribution
    print(f"\n{'Rank':<8} {'Word':<20} {'Clips':<10} {'% of Total':<12} {'Cumulative %':<15}")
    print("-" * 65)
    
    cursor.execute("""
        SELECT word, COUNT(*) as clip_count
        FROM word_clips
        GROUP BY word
        ORDER BY clip_count DESC
        LIMIT 100
    """)
    
    cumulative_clips = 0
    for rank, (word, clip_count) in enumerate(cursor.fetchall(), 1):
        cumulative_clips += clip_count
        percent = (clip_count / total_clips) * 100
        cumulative_percent = (cumulative_clips / total_clips) * 100
        
        print(f"{rank:<8} {word:<20} {clip_count:<10} {percent:>6.2f}%      {cumulative_percent:>6.2f}%")
        
        # Show summary at key milestones
        if rank == 10:
            print(f"\n→ Top 10 words cover {cumulative_percent:.1f}% of all clips")
        elif rank == 50:
            print(f"\n→ Top 50 words cover {cumulative_percent:.1f}% of all clips")
        elif rank == 100:
            print(f"\n→ Top 100 words cover {cumulative_percent:.1f}% of all clips")
    
    # Calculate recommendations
    print("\n" + "="*60)
    print("Pre-download Recommendations")
    print("="*60)
    
    for top_n in [100, 500, 1000, 5000]:
        cursor.execute("""
            SELECT SUM(clip_count) as total
            FROM (
                SELECT COUNT(*) as clip_count
                FROM word_clips
                GROUP BY word
                ORDER BY clip_count DESC
                LIMIT ?
            )
        """, (top_n,))
        
        covered_clips = cursor.fetchone()[0]
        coverage_percent = (covered_clips / total_clips) * 100
        estimated_storage_mb = (covered_clips * 500) / (1024 * 1024)  # ~500KB per clip
        
        print(f"\nTop {top_n:,} words:")
        print(f"  Coverage: {coverage_percent:.1f}% of all clips")
        print(f"  Estimated clips: {covered_clips:,}")
        print(f"  Estimated storage: {estimated_storage_mb:.0f} MB")
    
    # Estimate total storage for all words
    print(f"\nAll {total_unique_words:,} words:")
    estimated_total_gb = (total_clips * 500) / (1024 * 1024 * 1024)
    print(f"  Total clips: {total_clips:,}")
    print(f"  Estimated storage: {estimated_total_gb:.1f} GB")
    
    conn.close()
    
    print("\n" + "="*60)
    print("Recommendation: Pre-download top 1,000 words")
    print("This provides ~70-80% coverage with manageable storage")
    print("="*60 + "\n")


def get_top_words_for_predownload(n=1000, output_file="top_words.txt"):
    """Export top N words to a file for pre-downloading."""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT word, COUNT(*) as clip_count
        FROM word_clips
        GROUP BY word
        ORDER BY clip_count DESC
        LIMIT ?
    """, (n,))
    
    words = [row[0] for row in cursor.fetchall()]
    
    output_path = Path(output_file)
    output_path.write_text("\n".join(words))
    
    print(f"Exported top {n} words to: {output_path}")
    print(f"Total words: {len(words)}")
    
    conn.close()
    
    return words


if __name__ == "__main__":
    analyze_word_frequency()
    
    # Optionally export top words
    if len(sys.argv) > 1 and sys.argv[1] == "--export":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
        get_top_words_for_predownload(n)

