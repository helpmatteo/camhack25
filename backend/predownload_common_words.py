"""
Pre-download the most common words to dramatically speed up video generation.

This script downloads clips for the most frequently used words and caches them
locally, eliminating YouTube download time for future generations.
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from video_stitcher import VideoStitcher, StitchingConfig

DB_PATH = "./data/youglish.db"
TEMP_DIR = "./temp"


def get_top_words(n=1000, min_clips=1):
    """Get the N most common words from the database."""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT word, COUNT(*) as clip_count
        FROM word_clips
        GROUP BY word
        HAVING clip_count >= ?
        ORDER BY clip_count DESC
        LIMIT ?
    """, (min_clips, n))
    
    words = [(row[0], row[1]) for row in cursor.fetchall()]
    conn.close()
    
    return words


def predownload_words(words_list, max_clips_per_word=5, channel_id=None):
    """Pre-download clips for a list of words.
    
    Args:
        words_list: List of (word, clip_count) tuples
        max_clips_per_word: Maximum number of clips to download per word
        channel_id: Optional channel ID to filter clips
    """
    
    print("="*60)
    print("Pre-downloading Common Words")
    print("="*60)
    print(f"Words to process: {len(words_list)}")
    print(f"Max clips per word: {max_clips_per_word}")
    if channel_id:
        print(f"Filtering to channel: {channel_id}")
    print()
    
    # Initialize video stitcher (this will handle caching)
    config = StitchingConfig(
        database_path=DB_PATH,
        output_directory="./output",
        temp_directory=TEMP_DIR,
        video_quality="bestvideo[height<=480]+bestaudio/best[height<=480]",  # Faster downloads
        normalize_audio=False,  # Skip for pre-download
        incremental_stitching=True,
        cleanup_temp_files=False,  # Keep cached downloads
        verify_ffmpeg_on_init=False,
        channel_id=channel_id
    )
    
    total_words = len(words_list)
    total_downloaded = 0
    total_cached = 0
    total_failed = 0
    
    start_time = time.time()
    
    with VideoStitcher(config) as stitcher:
        for i, (word, clip_count) in enumerate(words_list, 1):
            word_start = time.time()
            
            try:
                # Look up clips for this word (limited)
                clips, missing = stitcher.lookup_clips([word] * min(max_clips_per_word, clip_count))
                
                if not clips:
                    print(f"[{i}/{total_words}] ⚠️  {word:<15} - No clips found")
                    total_failed += 1
                    continue
                
                # Download segments (this will cache them)
                downloaded_paths = stitcher.download_all_segments(clips[:max_clips_per_word])
                
                word_time = time.time() - word_start
                
                if len(downloaded_paths) == len(clips):
                    # Check if any were cached
                    if word_time < 1.0:
                        status = "✓ (cached)"
                        total_cached += 1
                    else:
                        status = "✓"
                        total_downloaded += 1
                else:
                    status = f"⚠️  ({len(downloaded_paths)}/{len(clips)} clips)"
                    total_failed += 1
                
                # Progress indicator
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                eta = avg_time * (total_words - i)
                
                print(f"[{i}/{total_words}] {status:<12} {word:<15} "
                      f"({len(downloaded_paths)} clips, {word_time:.1f}s) "
                      f"ETA: {eta/60:.1f}m")
                
                # Small delay to avoid overwhelming YouTube
                if total_downloaded > 0 and total_downloaded % 10 == 0:
                    time.sleep(1)
                
            except Exception as e:
                print(f"[{i}/{total_words}] ✗ {word:<15} - Error: {e}")
                total_failed += 1
                continue
    
    total_time = time.time() - start_time
    
    print("\n" + "="*60)
    print("Pre-download Complete!")
    print("="*60)
    print(f"Total words processed: {total_words}")
    print(f"Successfully downloaded: {total_downloaded}")
    print(f"Already cached: {total_cached}")
    print(f"Failed: {total_failed}")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Average time per word: {total_time/total_words:.1f} seconds")
    print()
    
    # Calculate cache statistics
    downloads_dir = Path(TEMP_DIR) / "downloads"
    if downloads_dir.exists():
        cached_files = list(downloads_dir.glob("*"))
        total_size = sum(f.stat().st_size for f in cached_files if f.is_file())
        total_size_mb = total_size / (1024 * 1024)
        
        print("Cache Statistics:")
        print(f"Cached files: {len(cached_files)}")
        print(f"Cache size: {total_size_mb:.1f} MB")
        print(f"Cache location: {downloads_dir}")
    
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-download common words for faster video generation"
    )
    parser.add_argument(
        "-n", "--top-n",
        type=int,
        default=100,
        help="Number of top words to download (default: 100)"
    )
    parser.add_argument(
        "-c", "--clips-per-word",
        type=int,
        default=3,
        help="Max clips to download per word (default: 3)"
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="Optional channel ID to filter clips"
    )
    parser.add_argument(
        "--min-clips",
        type=int,
        default=1,
        help="Minimum clips required for word to be included (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Get top words
    print(f"Analyzing top {args.top_n} words...")
    words = get_top_words(args.top_n, args.min_clips)
    
    if not words:
        print("No words found in database!")
        sys.exit(1)
    
    print(f"Found {len(words)} words to pre-download")
    
    # Estimate
    total_clips = sum(min(count, args.clips_per_word) for _, count in words)
    estimated_time = total_clips * 5 / 4  # 5s per clip, 4 parallel
    estimated_size = total_clips * 0.5  # 0.5 MB per clip
    
    print(f"\nEstimates:")
    print(f"  Total clips: ~{total_clips}")
    print(f"  Estimated time: ~{estimated_time/60:.1f} minutes")
    print(f"  Estimated storage: ~{estimated_size:.0f} MB")
    print()
    
    response = input("Proceed with pre-download? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    # Pre-download
    predownload_words(words, args.clips_per_word, args.channel)


if __name__ == "__main__":
    main()

