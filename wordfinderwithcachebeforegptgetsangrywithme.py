import random
import time
import shelve
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# --- CONFIG ---
API_KEY = "YOUR_YOUTUBE_API_KEY"   # <-- replace
SEARCH_TERMS = ["music","news","tutorial","gaming","interview","travel","science","history"]
CACHE_FILE = "yt_cache.db"
MAX_SEARCHES = 20          # max times we'll call the search API in a single run
MAX_ATTEMPTS = 500         # global safety cap of how many videos to check
TARGET_WORD = input("Enter the word to search for: ").strip().lower()

# build youtube client
youtube = build("youtube", "v3", developerKey=API_KEY)

# --- helper: search that prefers videos with captions ---
def youtube_search(query, page_token=None, max_results=50):
    """
    Performs one search.list call, requesting videos that *have captions* where possible.
    Returns (items, nextPageToken)
    """
    req = youtube.search().list(
        q=query,
        part="id,snippet",
        type="video",
        maxResults=max_results,
        videoCaption="closedCaption"  # only return videos that report closed captions
    )
    if page_token:
        req = req.execute().get  # placeholder to keep style (we'll pass token below)
    # pass pageToken separately to avoid confusion
    params = req.build_http_request().uri  # not necessary — we'll just call with token below

    # easier: call with pageToken param explicitly
    params = {
        "q": query,
        "part": "id,snippet",
        "type": "video",
        "maxResults": max_results,
        "videoCaption": "closedCaption"
    }
    if page_token:
        params["pageToken"] = page_token

    response = youtube.search().list(**params).execute()
    items = response.get("items", [])
    next_token = response.get("nextPageToken")
    return items, next_token

# --- caching helpers ---
def add_ids_to_cache(db, query, items):
    ids = [it["id"]["videoId"] for it in items if it.get("id") and it["id"].get("videoId")]
    if "video_ids" not in db:
        db["video_ids"] = []
    existing = set(db["video_ids"])
    new = [i for i in ids if i not in existing]
    if new:
        db["video_ids"] = db["video_ids"] + new

def cache_transcript(db, video_id, transcript_text):
    if "transcripts" not in db:
        db["transcripts"] = {}
    ts = db["transcripts"]
    ts[video_id] = transcript_text
    db["transcripts"] = ts

def get_cached_transcript(db, video_id):
    ts = db.get("transcripts", {})
    return ts.get(video_id)

# --- main routine ---
def find_in_transcripts(target_word):
    attempts = 0
    search_calls = 0
    with shelve.open(CACHE_FILE) as db:
        # ensure keys exist
        db.setdefault("video_ids", [])
        db.setdefault("checked", set())

        # primary loop: try cached IDs first, then perform a new search when exhausted
        while attempts < MAX_ATTEMPTS:
            # choose an unchecked cached id if possible
            cached_ids = [vid for vid in db["video_ids"] if vid not in db.get("checked", set())]
            if not cached_ids and search_calls >= MAX_SEARCHES:
                print("No more cached IDs and search call limit reached. Stopping.")
                break

            if not cached_ids:
                # perform a new search call
                search_calls += 1
                query = random.choice(SEARCH_TERMS)
                print(f"[search {search_calls}] Querying API for '{query}' (attempting to get many results)...")
                try:
                    items, next_tok = youtube_search(query, None, max_results=50)
                except Exception as e:
                    print("Search failed:", e)
                    time.sleep(1)
                    continue
                add_ids_to_cache(db, query, items)
                db.sync()
                # optionally page through a second page (careful with quota)
                # You can add logic here to fetch next_tok sometimes to get more IDs.
                continue  # go back to pick from cached ids

            # pick a random cached id to reduce repeated checking order
            video_id = random.choice(cached_ids)
            db_checked = set(db.get("checked", set()))
            db_checked.add(video_id)
            db["checked"] = db_checked
            db.sync()

            # check cached transcript first
            transcript_text = get_cached_transcript(db, video_id)
            if transcript_text is None:
                # fetch transcript (this does NOT use Data API quota)
                try:
                    entries = YouTubeTranscriptApi.get_transcript(video_id)
                    # join transcript lines into single text for searching and caching
                    transcript_text = " ".join(e.get("text", "") for e in entries).lower()
                    cache_transcript(db, video_id, transcript_text)
                    db.sync()
                except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
                    # no transcript available despite search hint — skip
                    print(f"({attempts+1}) No transcript for {video_id}, skipping.")
                    attempts += 1
                    continue
                except Exception as e:
                    print(f"({attempts+1}) Error fetching transcript for {video_id}: {e}")
                    attempts += 1
                    continue

            attempts += 1
            if target_word in transcript_text:
                # find a snippet with the word if possible
                snippet = next((s for s in transcript_text.split(". ") if target_word in s), None)
                print("✅ Found:", f"https://www.youtube.com/watch?v={video_id}")
                if snippet:
                    print("Snippet:", snippet.strip())
                return video_id

            # not found — loop
            if attempts % 20 == 0:
                # polite pause to avoid bursts (and reduce chance of rate limit)
                time.sleep(0.5)

        print("Stopped: reached attempt/search limits without finding the word.")
        return None

if __name__ == "__main__":
    result = find_in_transcripts(TARGET_WORD)
    if result:
        print("Done.")
    else:
        print("Word not found in the budgeted search.")
