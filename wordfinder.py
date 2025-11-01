import random
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- CONFIG ---
API_KEY = "AIzaSyBKJYDwdFglq1nOggr1opPFUG5KIjTvOls"
SEARCH_TERMS = ["music", "news", "funny", "tutorial", "interview", "travel", "random", "gaming"]
TARGET_WORD = input("Enter the word to search for: ").lower()

# --- YouTube Search ---
youtube = build("youtube", "v3", developerKey=API_KEY)

def get_random_video():
    """Searches YouTube for a random keyword and returns a random video ID."""
    query = random.choice(SEARCH_TERMS)
    request = youtube.search().list(
        q=query,
        part="snippet",
        type="video",
        maxResults=10
    )
    response = request.execute()
    items = response.get("items", [])
    if not items:
        return None
    return random.choice(items)["id"]["videoId"]

# --- Transcript Search ---
def video_contains_word(video_id, word):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        for entry in transcript:
            if word in entry["text"].lower():
                return True, entry["text"]
        return False, None
    except Exception:
        # Could be no captions or region restrictions
        return False, None

# --- Main Loop ---
attempts = 0
while True:
    attempts += 1
    video_id = get_random_video()
    if not video_id:
        continue
    found, line = video_contains_word(video_id, TARGET_WORD)
    if found:
        print(f"✅ Found '{TARGET_WORD}' in video: https://www.youtube.com/watch?v={video_id}")
        print(f"Example line: {line}")
        break
    else:
        print(f"({attempts}) No match in https://www.youtube.com/watch?v={video_id}")