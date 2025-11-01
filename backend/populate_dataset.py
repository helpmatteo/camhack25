#!/usr/bin/env python3
"""Populate database with sample YouTube videos (no API key required)."""
import sqlite3
import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

DB_PATH = os.getenv("DB_PATH", "./data/youglish.db")

# Popular educational videos with transcripts
SAMPLE_VIDEOS = [
    # TED Talks
    {
        "video_id": "9bZkp7q19f0",
        "title": "Sir Ken Robinson: Do schools kill creativity?",
        "channel_id": "UCAuUUnT6oDeKwE6v1NGQxug",
        "channel_title": "TED",
        "published_at": "2007-01-06"
    },
    {
        "video_id": "8S0FDjFBj8o",
        "title": "Your body language may shape who you are | Amy Cuddy",
        "channel_id": "UCAuUUnT6oDeKwE6v1NGQxug",
        "channel_title": "TED",
        "published_at": "2012-10-01"
    },
    # Khan Academy
    {
        "video_id": "SrPZZBxEkJ0",
        "title": "Introduction to Limits",
        "channel_id": "UClqhvGmHcvWL9w3R48t9QXA",
        "channel_title": "Khan Academy",
        "published_at": "2008-07-09"
    },
    {
        "video_id": "coaUaWzGP5A",
        "title": "What is Calculus Used For?",
        "channel_id": "UClqhvGmHcvWL9w3R48t9QXA",
        "channel_title": "Khan Academy",
        "published_at": "2016-02-01"
    },
    # Crash Course
    {
        "video_id": "dGiQaabX3_o",
        "title": "World War II: Crash Course World History #38",
        "channel_id": "UCX6b17PVsYBQ0ip5gyeme-Q",
        "channel_title": "CrashCourse",
        "published_at": "2012-10-18"
    },
    {
        "video_id": "BRvfCTRScP4",
        "title": "The Internet: Crash Course Computer Science #29",
        "channel_id": "UCX6b17PVsYBQ0ip5gyeme-Q",
        "channel_title": "CrashCourse",
        "published_at": "2017-09-13"
    },
    # National Geographic
    {
        "video_id": "t7tA3NNKF0Q",
        "title": "What is the universe expanding into?",
        "channel_id": "UCpVm7bg6pXKo1Pr6k5kxG9A",
        "channel_title": "National Geographic",
        "published_at": "2014-11-14"
    },
    # MIT OpenCourseWare
    {
        "video_id": "0K8i8w4zPTA",
        "title": "Introduction to Computer Science and Programming",
        "channel_id": "UCEBb1b_L6zDS3xTUrIALZOw",
        "channel_title": "MIT OpenCourseWare",
        "published_at": "2011-01-21"
    },
    # Vsauce
    {
        "video_id": "Xc4xYacTu-E",
        "title": "What Is The Resolution Of The Eye?",
        "channel_id": "UC6nSFpj9HTCZ5t-N3Rm3-HA",
        "channel_title": "Vsauce",
        "published_at": "2013-10-17"
    },
    # Veritasium
    {
        "video_id": "Z_nJUxUj1z4",
        "title": "The Surprising Secret of Synchronization",
        "channel_id": "UCHnyfMqiRRG1u-2MsSQLbXA",
        "channel_title": "Veritasium",
        "published_at": "2019-06-25"
    },
    # AsapSCIENCE
    {
        "video_id": "oNQGmCLxPF0",
        "title": "What If You Stopped Sleeping?",
        "channel_id": "UCC552Sd-3nyi_tk2BudLUzA",
        "channel_title": "AsapSCIENCE",
        "published_at": "2013-06-13"
    },
    # SciShow
    {
        "video_id": "M_Gg_7XWj-g",
        "title": "Why Do We Have Different Blood Types?",
        "channel_id": "UCZYTClx2T1of7BRZ86-8fow",
        "channel_title": "SciShow",
        "published_at": "2013-05-08"
    },
    # Physics Girl
    {
        "video_id": "GlWNuzrqe7U",
        "title": "Why is the Sky Blue?",
        "channel_id": "UC7DdEm33SyaTDtWYGO2CwdA",
        "channel_title": "Physics Girl",
        "published_at": "2015-03-03"
    },
    # Numberphile
    {
        "video_id": "s7tWHJfhiyo",
        "title": "One to a Million",
        "channel_id": "UCoxcjq-8xIDTYp3uz647V5A",
        "channel_title": "Numberphile",
        "published_at": "2012-09-17"
    },
    # Smarter Every Day
    {
        "video_id": "GeyDf4ooPdo",
        "title": "How do Wings actually Work?",
        "channel_id": "UC6107grRI4m0o2-emgoDnAA",
        "channel_title": "SmarterEveryDay",
        "published_at": "2022-08-19"
    },
]

def get_conn():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def upsert_video(conn, v):
    """Insert or update video metadata."""
    conn.execute(
        """
        INSERT INTO videos(video_id, title, channel_id, channel_title, published_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(video_id) DO UPDATE SET 
            title=excluded.title,
            channel_id=excluded.channel_id, 
            channel_title=excluded.channel_title,
            published_at=excluded.published_at
        """,
        (v["video_id"], v["title"], v["channel_id"], v["channel_title"], v.get("published_at")),
    )

def insert_segments(conn, video_id, lang, transcript):
    """Insert transcript segments."""
    rows = [
        (
            video_id,
            lang,
            float(item["start"]),
            float(item["start"]) + float(item.get("duration", 0)),
            item["text"].strip(),
            "CAPTION",
        ) for item in transcript if item.get("text")
    ]
    conn.executemany(
        """
        INSERT INTO segments(video_id, lang, t_start, t_end, text, source)
        VALUES(?,?,?,?,?,?)
        """,
        rows,
    )

def fetch_and_store_transcript(conn, video):
    """Fetch transcript for a video and store in database."""
    video_id = video["video_id"]
    
    try:
        # First, upsert the video metadata
        upsert_video(conn, video)
        
        # Try to get transcript list
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as e:
            print(f"  ✗ No transcripts available for {video_id}: {str(e)[:50]}")
            return False
        
        # Try to find the best transcript
        transcript = None
        lang = 'en'
        
        # Try English first (manual then auto-generated)
        try:
            transcript = transcript_list.find_transcript(['en'])
            lang = 'en'
        except:
            # Try any available transcript
            try:
                for available_transcript in transcript_list:
                    transcript = available_transcript
                    lang = transcript.language_code
                    break
            except:
                pass
        
        if not transcript:
            print(f"  ✗ No usable transcript found for {video_id}")
            return False
        
        # Fetch the actual transcript data
        transcript_data = transcript.fetch()
        
        if not transcript_data:
            print(f"  ✗ Empty transcript for {video_id}")
            return False
            
        insert_segments(conn, video_id, lang, transcript_data)
        conn.commit()
        
        # Get stats
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM segments WHERE video_id = ?",
            (video_id,)
        )
        count = cursor.fetchone()[0]
        
        print(f"  ✓ {video['title'][:60]}")
        print(f"    └─ {count} segments ({lang})")
        return True
            
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"  ✗ Transcript disabled for {video_id}")
        return False
    except Exception as e:
        print(f"  ✗ Error processing {video_id}: {str(e)[:50]}")
        return False

def main():
    """Main function to populate database."""
    print("="*70)
    print("YouTube Transcript Database Population")
    print("="*70)
    print(f"\nDatabase: {DB_PATH}")
    print(f"Videos to process: {len(SAMPLE_VIDEOS)}")
    print("\nFetching transcripts (this may take 1-2 minutes)...\n")
    
    conn = get_conn()
    
    # Clear existing data (optional - comment out to keep test data)
    print("Clearing existing data...")
    conn.execute("DELETE FROM segments")
    conn.execute("DELETE FROM videos")
    conn.commit()
    print("✓ Database cleared\n")
    
    success_count = 0
    fail_count = 0
    
    for i, video in enumerate(SAMPLE_VIDEOS, 1):
        print(f"[{i}/{len(SAMPLE_VIDEOS)}]")
        if fetch_and_store_transcript(conn, video):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    conn.close()
    
    # Final statistics
    print("="*70)
    print("Summary")
    print("="*70)
    
    conn = get_conn()
    cursor = conn.execute("SELECT COUNT(*) FROM videos")
    video_count = cursor.fetchone()[0]
    
    cursor = conn.execute("SELECT COUNT(*) FROM segments")
    segment_count = cursor.fetchone()[0]
    
    cursor = conn.execute("SELECT COUNT(DISTINCT lang) FROM segments")
    lang_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"Videos in database: {video_count}")
    print(f"Transcript segments: {segment_count}")
    print(f"Languages: {lang_count}")
    print(f"\nSuccess: {success_count} | Failed: {fail_count}")
    print("\n" + "="*70)
    
    if segment_count > 0:
        print("✓ Database populated successfully!")
        print("\nYou can now start the server:")
        print("  python run.py")
        print("\nAnd search for phrases like:")
        print('  curl "http://localhost:8000/search?q=neural+network"')
        print('  curl "http://localhost:8000/search?q=physics"')
    else:
        print("✗ No data was added to the database.")
        print("This might be due to network issues or unavailable transcripts.")

if __name__ == "__main__":
    main()

