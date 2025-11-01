"""
Populate video metadata (channel_id, title, etc.) for all videos in the database.

This script fetches video metadata from the YouTube API for all video IDs
found in the word_clips/video_transcripts tables and populates the videos table.
"""

import os
import sqlite3
import sys
import time
from typing import List, Dict, Set
import httpx

DB_PATH = "./data/youglish.db"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
BATCH_SIZE = 50  # YouTube API allows up to 50 video IDs per request
REQUEST_DELAY = 0.1  # Small delay between requests to avoid rate limiting


def get_all_video_ids(db_path: str) -> List[str]:
    """Get all unique video IDs from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get video IDs from video_transcripts (or word_clips as fallback)
    cursor.execute("SELECT DISTINCT video_id FROM video_transcripts ORDER BY video_id")
    video_ids = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return video_ids


def get_existing_video_ids(db_path: str) -> Set[str]:
    """Get video IDs that already exist in the videos table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT video_id FROM videos WHERE channel_id IS NOT NULL")
    existing_ids = {row[0] for row in cursor.fetchall()}
    
    conn.close()
    return existing_ids


def fetch_video_metadata_batch(video_ids: List[str]) -> List[Dict]:
    """
    Fetch video metadata from YouTube API for a batch of video IDs.
    
    Args:
        video_ids: List of YouTube video IDs (max 50)
        
    Returns:
        List of video metadata dictionaries
    """
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable is not set")
    
    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "snippet",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
        "maxResults": 50
    }
    
    try:
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        videos = []
        for item in data.get("items", []):
            video_id = item["id"]
            snippet = item["snippet"]
            
            videos.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", "")
            })
        
        return videos
    
    except httpx.HTTPError as e:
        print(f"HTTP error fetching video metadata: {e}")
        return []
    except Exception as e:
        print(f"Error fetching video metadata: {e}")
        return []


def insert_video_metadata(db_path: str, videos: List[Dict]):
    """Insert or update video metadata in the database."""
    if not videos:
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Use INSERT OR REPLACE to handle both new and existing videos
    cursor.executemany(
        """
        INSERT OR REPLACE INTO videos (video_id, title, channel_id, channel_title, published_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (v["video_id"], v["title"], v["channel_id"], v["channel_title"], v["published_at"])
            for v in videos
        ]
    )
    
    conn.commit()
    conn.close()


def main():
    """Main entry point."""
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY environment variable is not set")
        print("Please set it with: export YOUTUBE_API_KEY='your-api-key'")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print("Video Metadata Population")
    print(f"{'='*60}\n")
    
    # Get all video IDs
    print("Fetching video IDs from database...")
    all_video_ids = get_all_video_ids(DB_PATH)
    print(f"Found {len(all_video_ids)} unique video IDs")
    
    # Check which ones already have metadata
    existing_ids = get_existing_video_ids(DB_PATH)
    print(f"Already have metadata for {len(existing_ids)} videos")
    
    # Filter to only videos that need metadata
    video_ids_to_fetch = [vid for vid in all_video_ids if vid not in existing_ids]
    print(f"Need to fetch metadata for {len(video_ids_to_fetch)} videos")
    
    if not video_ids_to_fetch:
        print("\nAll videos already have metadata!")
        return
    
    # Process in batches
    total_batches = (len(video_ids_to_fetch) + BATCH_SIZE - 1) // BATCH_SIZE
    total_fetched = 0
    total_failed = 0
    
    print(f"\nProcessing {total_batches} batches of up to {BATCH_SIZE} videos each...")
    
    for i in range(0, len(video_ids_to_fetch), BATCH_SIZE):
        batch = video_ids_to_fetch[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        
        print(f"Batch {batch_num}/{total_batches}: Fetching {len(batch)} videos...", end=" ")
        
        videos = fetch_video_metadata_batch(batch)
        
        if videos:
            insert_video_metadata(DB_PATH, videos)
            total_fetched += len(videos)
            print(f"✓ Got {len(videos)} videos")
        else:
            total_failed += len(batch)
            print(f"✗ Failed")
        
        # Small delay to avoid rate limiting
        if i + BATCH_SIZE < len(video_ids_to_fetch):
            time.sleep(REQUEST_DELAY)
    
    print(f"\n{'='*60}")
    print("Metadata Population Complete!")
    print(f"{'='*60}")
    print(f"Successfully fetched: {total_fetched} videos")
    print(f"Failed to fetch: {total_failed} videos")
    print(f"{'='*60}\n")
    
    # Show final statistics
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos WHERE channel_id IS NOT NULL")
    total_with_metadata = cursor.fetchone()[0]
    conn.close()
    
    print(f"Total videos in database with metadata: {total_with_metadata}")


if __name__ == "__main__":
    main()

