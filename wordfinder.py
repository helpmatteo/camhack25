import sqlite3
import random
import time
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

API_KEY = "YOUR_YOUTUBE_API_KEY"
youtube = build("youtube", "v3", developerKey=API_KEY)

DB_FILE = "youtube_transcripts.db"

# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            title TEXT,
            channel TEXT,
            transcript TEXT
        )
    """)
    # Full-text index for fast search
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts 
        USING fts5(id, transcript)
    """)
    conn.commit()
    conn.close()

# ---------- DATA ACCESS HELPERS ----------
def insert_video(video_id, title, channel, transcript):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("REPLACE INTO videos (id, title, channel, transcript) VALUES (?, ?, ?, ?)",
                (video_id, title, channel, transcript))
    cur.execute("REPLACE INTO transcripts_fts (id, transcript) VALUES (?, ?)", (video_id, transcript))
    conn.commit()
    conn.close()

def video_exists(video_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM videos WHERE id=?", (video_id,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def search_word(word):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM transcripts_fts WHERE transcripts_fts MATCH ?", (word,))
    results = cur.fetchall()
    conn.close()
    return [r[0] for r in results]

# ---------- YOUTUBE HELPERS ----------
def fetch_playlist_videos(playlist_id, limit=100):
    """Get up to `limit` videos from a playlist."""
    results = []
    page_token = None
    while len(results) < limit:
        req = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=min(50, limit - len(results)),
            pageToken=page_token
        )
        resp = req.execute()
        for item in resp.get("items", []):
            vid = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            results.append((vid, title, channel))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results

def fetch_channel_uploads(channel_id, limit=100):
    """Fetch recent uploads from a channel by channel_id."""
    # First get uploads playlist
    req = youtube.channels().list(part="contentDetails", id=channel_id)
    resp = req.execute()
    uploads_id = resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return fetch_playlist_videos(uploads_id, limit)

def get_transcript_text(video_id):
    """Try to fetch transcript text."""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(entry["text"] for entry in transcript)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
        return None
    except Exception as e:
        print(f"Error fetching transcript for {video_id}: {e}")
        return None

# ---------- PREPOPULATE ----------
def prepopulate_from_channel(channel_id, limit=100):
    print(f"Prepopulating from channel {channel_id} (up to {limit} videos)...")
    videos = fetch_channel_uploads(channel_id, limit)
    for vid, title, channel in videos:
        if video_exists(vid):
            continue
        txt = get_transcript_text(vid)
        if txt:
            insert_video(vid, title, channel, txt)
            print(f"✔️ Cached {title[:40]}...")
        else:
            print(f"❌ No transcript for {title[:40]}")
        time.sleep(0.2)  # be nice to YouTube

# ---------- MAIN SEARCH ----------
def find_word(word):
    ids = search_word(word)
    if not ids:
        print(f"No cached transcripts contain '{word}'.")
        return None
    vid = random.choice(ids)
    print(f"✅ Found '{word}' in https://www.youtube.com/watch?v={vid}")
    return vid

# ---------- RUN ----------
if __name__ == "__main__":
    init_db()
    choice = input("Prepopulate (p) or search (s)? ").strip().lower()

    if choice == "p":
        ch_id = input("Enter channel ID (not username): ").strip()
        prepopulate_from_channel(ch_id, limit=100)

    elif choice == "s":
        word = input("Enter word to search for: ").lower().strip()
        find_word(word)
