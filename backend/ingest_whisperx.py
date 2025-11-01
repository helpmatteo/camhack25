"""
Ingest WhisperX word-level transcription data into the database.

This script parses the live_whisperx_526k_with_seeks.jsonl file and populates
the word_clips table with word-level timing information from YouTube videos.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DB_PATH = "./data/youglish.db"
JSONL_PATH = "./data/live_whisperx_526k_with_seeks.jsonl"


def parse_text_stream(text_stream: List[List]) -> List[Tuple[str, float, float]]:
    """
    Parse the text_stream format into word entries.
    
    Args:
        text_stream: List of [start_time, end_time, word] entries
        
    Returns:
        List of (word, start_time, duration) tuples
    """
    words = []
    for entry in text_stream:
        if len(entry) >= 3:
            start_time = float(entry[0])
            end_time = float(entry[1])
            word = str(entry[2]).lower().strip()
            
            # Filter out empty words and punctuation-only
            if word and word.isalnum():
                duration = end_time - start_time
                words.append((word, start_time, duration))
    
    return words


def extract_video_id(video_path: str) -> str:
    """
    Extract YouTube video ID from the video path.
    
    Args:
        video_path: Path like "video/youtube/VIDEO_ID.mp4" or "video/youtube/VIDEO_ID_start-end_fps.mp4"
        
    Returns:
        The YouTube video ID (11 characters)
    """
    # Extract filename without extension
    filename = Path(video_path).stem
    
    # YouTube video IDs are always 11 characters
    # The format is: VIDEO_ID_start-end_fps or just VIDEO_ID
    # So we need to extract the first 11 characters of the filename
    if len(filename) >= 11:
        video_id = filename[:11]
    else:
        # Fallback: try splitting on underscore
        video_id = filename.split('_')[0]
    
    return video_id


def ingest_jsonl(jsonl_path: str, db_path: str, batch_size: int = 1000):
    """
    Ingest the JSONL file into the database.
    
    Args:
        jsonl_path: Path to the JSONL file
        db_path: Path to the SQLite database
        batch_size: Number of records to insert at once
    """
    print(f"Opening database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create word_clips table (for backward compatibility)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS word_clips (
            word TEXT NOT NULL,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL,
            PRIMARY KEY (word, video_id, start_time)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_clips_word ON word_clips(word)")
    
    # Create video_transcripts table (for phrase matching)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_transcripts (
            video_id TEXT PRIMARY KEY,
            transcript_data TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            duration REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_transcripts_video_id ON video_transcripts(video_id)")
    
    print(f"Reading JSONL file: {jsonl_path}")
    
    total_words = 0
    total_entries = 0
    total_transcripts = 0
    batch = []
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                # The file format has conversation entries
                data = json.loads(line)
                
                # Skip the last line which contains seek indices
                if isinstance(data, bytes) or (isinstance(data, str) and data.startswith('[')):
                    print(f"Skipping seek indices line")
                    continue
                
                # Extract video info from the first user message
                if isinstance(data, list) and len(data) >= 2:
                    user_msg = data[0]
                    assistant_msg = data[1]
                    
                    # Get video_id from user content
                    if 'content' in user_msg and isinstance(user_msg['content'], list):
                        video_info = None
                        for item in user_msg['content']:
                            if isinstance(item, dict) and item.get('type') == 'video':
                                video_info = item
                                break
                        
                        if not video_info:
                            continue
                        
                        video_id = extract_video_id(video_info['video'])
                        
                        # Get text_stream from assistant content
                        if 'content' in assistant_msg and isinstance(assistant_msg['content'], list):
                            for item in assistant_msg['content']:
                                if isinstance(item, dict) and item.get('type') == 'text_stream':
                                    text_stream = item.get('text_stream', [])
                                    
                                    # Parse words from text_stream
                                    words = parse_text_stream(text_stream)
                                    
                                    # Store individual words (for backward compatibility)
                                    for word, start_time, duration in words:
                                        batch.append((word, video_id, start_time, duration))
                                        total_words += 1
                                    
                                    # Store complete transcript for phrase matching
                                    if words:
                                        # Store as JSON: [[word, start_time, end_time], ...]
                                        transcript_json = json.dumps([
                                            [w, st, st + dur] for w, st, dur in words
                                        ])
                                        duration = words[-1][1] + words[-1][2] if words else 0
                                        
                                        cursor.execute("""
                                            INSERT OR REPLACE INTO video_transcripts 
                                            (video_id, transcript_data, word_count, duration)
                                            VALUES (?, ?, ?, ?)
                                        """, (video_id, transcript_json, len(words), duration))
                                        total_transcripts += 1
                                    
                                    break
                    
                    total_entries += 1
                    
                    # Insert batch
                    if len(batch) >= batch_size:
                        cursor.executemany(
                            "INSERT OR IGNORE INTO word_clips (word, video_id, start_time, duration) VALUES (?, ?, ?, ?)",
                            batch
                        )
                        conn.commit()
                        print(f"Processed {total_entries} entries, {total_words} words, {total_transcripts} transcripts...")
                        batch = []
            
            except json.JSONDecodeError as e:
                print(f"Error parsing line {line_num}: {e}")
                continue
            except Exception as e:
                print(f"Error processing line {line_num}: {e}")
                continue
    
    # Insert remaining batch
    if batch:
        cursor.executemany(
            "INSERT OR IGNORE INTO word_clips (word, video_id, start_time, duration) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()
    
    # Get statistics
    cursor.execute("SELECT COUNT(*) FROM word_clips")
    total_in_db = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT word) FROM word_clips")
    unique_words = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT video_id) FROM word_clips")
    unique_videos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM video_transcripts")
    total_transcripts_db = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n{'='*60}")
    print("Ingestion Complete!")
    print(f"{'='*60}")
    print(f"Total entries processed: {total_entries}")
    print(f"Total word clips in database: {total_in_db}")
    print(f"Total transcripts stored: {total_transcripts_db}")
    print(f"Unique words: {unique_words}")
    print(f"Unique videos: {unique_videos}")
    print(f"{'='*60}\n")


def main():
    """Main entry point."""
    jsonl_path = Path(JSONL_PATH)
    db_path = Path(DB_PATH)
    
    if not jsonl_path.exists():
        print(f"Error: JSONL file not found: {jsonl_path}")
        sys.exit(1)
    
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print("WhisperX Data Ingestion")
    print(f"{'='*60}\n")
    
    ingest_jsonl(str(jsonl_path), str(db_path))


if __name__ == "__main__":
    main()

