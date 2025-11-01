import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube import list_uploads_playlist_id, list_videos_in_playlist

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "./data/youglish.db")
SEED = [s.strip() for s in os.getenv("SEED_CHANNEL_IDS", "").split(",") if s.strip()]

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r', encoding='utf8').read()



def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn





def ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()





def upsert_video(conn, v):
    conn.execute(
        """
        INSERT INTO videos(video_id, title, channel_id, channel_title, published_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(video_id) DO UPDATE SET title=excluded.title,
          channel_id=excluded.channel_id, channel_title=excluded.channel_title,
          published_at=excluded.published_at
        """,
        (v["video_id"], v["title"], v["channel_id"], v["channel_title"], v.get("published_at")),
    )





def insert_segments(conn, video_id, lang, transcript):
    # transcript: list of {text, start, duration}
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





async def harvest_channel(channel_id: str):
    conn = db()
    try:
        ensure_schema(conn)
        uploads = await list_uploads_playlist_id(channel_id)
        if not uploads:
            print(f"No uploads playlist for {channel_id}")
            return
        videos = await list_videos_in_playlist(uploads, max_pages=5)
        for v in videos:
            upsert_video(conn, v)
            # Try multiple languages; default to 'en' first, then fall back to any available
            try:
                transcripts = YouTubeTranscriptApi.list_transcripts(v["video_id"])  # returns TranscriptList
            except Exception as e:
                print(f"list_transcripts failed for {v['video_id']}: {e}")
                continue



            chosen = None
            # Prefer English manual → English auto → any manual → any auto
            prio = [
                ("en", True), ("en", False)
            ] + [(None, True), (None, False)]



            for lang, must_manual in prio:
                for t in transcripts:
                    try:
                        is_manual = not t.is_generated
                        if lang and t.language_code.split('-')[0] != lang:
                            continue
                        if must_manual and not is_manual:
                            continue
                        chosen = t
                        break
                    except Exception:
                        continue
                if chosen:
                    break



            if not chosen:
                # take first available
                try:
                    for t in transcripts:
                        chosen = t
                        break
                except Exception:
                    chosen = None



            if not chosen:
                print(f"No transcripts for {v['video_id']}")
                continue



            try:
                tr = chosen.fetch()
                lang = chosen.language_code
                insert_segments(conn, v["video_id"], lang, tr)
                conn.commit()
                print(f"Inserted {len(tr)} segments for {v['video_id']}")
            except (TranscriptsDisabled, NoTranscriptFound) as e:
                print(f"No transcript for {v['video_id']}: {e}")
            except Exception as e:
                print(f"fetch/insert failed for {v['video_id']}: {e}")
    finally:
        conn.close()





async def main():
    tasks = [harvest_channel(c) for c in SEED]
    await asyncio.gather(*tasks)



if __name__ == "__main__":
    asyncio.run(main())

