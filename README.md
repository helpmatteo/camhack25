# YouGlish‑lite MVP (M1)

**Scope:**

- Seed 2–3 channels.
- Fetch transcripts → store as `(video_id, lang, t_start, t_end, text)`.
- Index with **SQLite FTS5**.
- REST: `GET /search?q="exact phrase"&lang=en&limit=20`.
- Frontend: React + **YouTube IFrame Player**; hits list + **Next**.
- **No ASR, no semantics.**

Tested locally on macOS/Linux. Windows works with minor path tweaks.

---

## 0) Repo layout

```
youglish-mvp/
  backend/
    app.py
    db.py
    ingest.py
    youtube.py
    schema.sql
    requirements.txt
    .env.example
    data/
      youglish.db                        # Main database
      live_whisperx_526k_with_seeks.jsonl  # WhisperX transcription data
    video_stitcher/                      # Video stitching module
      cli.py
      video_stitcher.py
      database.py
      downloader.py
      concatenator.py
      video_processor.py
  frontend/
    index.html
    package.json
    vite.config.js
    src/
      main.jsx
      App.jsx
      api.js
      Player.jsx
      Search.jsx
      index.css
  README.md
```

---

## 1) Data Files

The `backend/data/` directory contains:

### youglish.db

SQLite database with FTS5 full-text search index containing:

- Video metadata (video_id, title, channel info)
- Transcript segments with timestamps (t_start, t_end, text)
- Language information

Created by running `python ingest.py` or `python init_db.py`.

### live_whisperx_526k_with_seeks.jsonl

WhisperX transcription data with word-level timing information (526k entries).

**Format:** JSONL (JSON Lines) with each line containing:

- `video_id`: YouTube video ID
- `word`: Transcribed word
- `start`: Start timestamp (seconds)
- `end`: End timestamp (seconds)
- Additional metadata from WhisperX processing

This dataset enables word-level video clip extraction for the video stitcher module.

---

## 2) Backend Setup

### 2.1 Install dependencies

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2.2 Configure environment

Copy `.env.example` to `.env` and fill in your YouTube API key and channel IDs:

```bash
cp .env.example .env
```

Edit `.env`:

```
YOUTUBE_API_KEY=YOUR_YT_DATA_API_KEY
SEED_CHANNEL_IDS=UCYO_jab_esuFRV4b17AJtAw,UC8butISFwT-Wl7EV0hUK0BQ
DB_PATH=./data/youglish.db
```

### 2.3 Seed database

```bash
python ingest.py
```

This will:

- Fetch videos from the specified channels
- Download transcripts (preferring English manual captions)
- Store segments in SQLite with FTS5 indexing

Expect many videos to be skipped (no captions available). That's fine.

### 2.4 Run backend server

```bash
uvicorn app:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

---

## 3) Frontend Setup

### 3.1 Install dependencies

```bash
cd frontend
npm i
```

### 3.2 Run development server

```bash
npm run dev
```

Open `http://localhost:5173` in your browser.

If your API runs elsewhere, set the environment variable:

```bash
VITE_API=http://localhost:8000 npm run dev
```

---

## 4) Video Generation Setup

### 4.0 YouTube Authentication (Required)

⚠️ **Important:** YouTube now requires authentication to download videos to prevent bot detection.

**Quick Setup:**
1. Make sure you're logged into YouTube in Chrome (or your preferred browser)
2. That's it! The backend will automatically use your browser's cookies

**Need to use a different browser?**
- See `YOUTUBE_COOKIE_SETUP.md` for detailed instructions
- Set `COOKIES_FROM_BROWSER` environment variable to your browser name

### 4.1 Migrate Database (First Time Only)

Add support for phrase matching to improve video smoothness:

```bash
cd backend
source .venv/bin/activate
python migrate_db.py data/youglish.db
```

This creates the `video_transcripts` table for storing complete video transcripts.

### 4.2 Ingest WhisperX Word-Level Data

Populate the database with word-level and full transcript data:

```bash
python ingest_whisperx.py
```

This will parse the `live_whisperx_526k_with_seeks.jsonl` file and create:
- Word-to-clip mappings (~526k entries)
- Complete video transcripts with timestamps (for phrase matching)

### 4.3 Test Video Generation

Verify everything works:

```bash
# Test phrase matching
python test_phrase_matching.py

# Generate a test video
python -m video_stitcher.cli \
  --text "hello world" \
  --database data/youglish.db \
  --output test_hello.mp4 \
  --verbose
```

### 4.4 Generate Videos from Text

Once the database is populated, users can:

1. Enter a sentence in the frontend (e.g., "hello world")
2. Click **"Generate Video"** button
3. The system will:
   - Find video clips using phrase matching (combines consecutive words when possible)
   - Download the specific segments
   - Stitch them together smoothly
   - Serve the final video

**New Feature: Phrase Matching** 🎯
- Automatically combines consecutive words from the same video
- Creates smoother videos with fewer cuts
- Falls back to individual words when phrases aren't found
- See `backend/PHRASE_MATCHING_GUIDE.md` for details

### 4.5 Documentation

- **Quick Start**: See `backend/QUICK_START.md` for basic usage
- **Phrase Matching**: See `backend/PHRASE_MATCHING_GUIDE.md` for advanced features
- **API Reference**: Check inline docstrings in `backend/video_stitcher/`

---

## 5) Usage

### Quick Start (Both Servers)

```bash
./start.sh
```

This automatically starts both backend and frontend with auto-port detection.

### Manual Start

1. Put your channel IDs and API key in `backend/.env`.
2. Run `python ingest.py` to build the DB. Expect many videos to be skipped (no captions). That's fine.
3. Run `python ingest_whisperx.py` to populate word-level clips for video generation.
4. Make sure you're logged into YouTube in Chrome (for cookie authentication).
5. Start API: `cd backend && python run.py` (auto-detects available port).
6. Start frontend: `npm run dev` in `/frontend`.
7. Query **exact phrases** (don't rely on fuzzy; use the real phrase). Click **Next** to advance through hits.
8. Or enter text and click **"Generate Video"** to create a stitched video from individual word clips.

---

## 5) API Endpoints

### GET /health

Health check endpoint.

### GET /search

Search for exact phrases in transcripts.

**Query parameters:**

- `q` (required): Search phrase (exact match)
- `lang` (optional): Language filter (e.g., "en")
- `limit` (optional): Maximum number of results (default: 20)

**Example:**

```bash
curl 'http://localhost:8000/search?q=%22radio%20telescope%22&lang=en&limit=5' | jq
```

### POST /generate-video

Generate a stitched video from individual word clips.

**Request body:**

```json
{
  "text": "hello world",
  "lang": "en"
}
```

**Response:**

```json
{
  "status": "success",
  "video_url": "/videos/generated_1234567890.mp4",
  "message": "Video generated successfully with 2 words"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/generate-video \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world", "lang": "en"}'
```

---

## 7) Audio Enhancement with Auphonic (Optional)

The video stitcher now supports professional audio enhancement using the [Auphonic API](https://auphonic.com/). This feature:

- **Removes background noise** from different video sources
- **Normalizes volume levels** across clips
- **Applies loudness normalization** (LUFS standard)
- **Eliminates humming and rumbling** sounds

### Quick Setup

1. **Get an Auphonic API token** (2 hours/month free):
   - Sign up at [https://auphonic.com/](https://auphonic.com/)
   - Go to Account Settings → API
   - Generate a new token

2. **Configure the token**:
   ```bash
   # Add to backend/.env
   echo 'AUPHONIC_API_TOKEN=your_token_here' >> backend/.env
   ```

3. **Enable in the UI**:
   - Toggle "Audio Enhancement (Auphonic)" when generating videos
   - Optionally keep original audio for comparison

### What Happens

When enabled, the video stitcher:
1. Generates the video normally
2. Extracts audio to MP3
3. Uploads to Auphonic for processing
4. Downloads enhanced audio
5. Merges it back into the video

### Comparison Files

With "Keep original audio" enabled, you get:
- `output/generated_TIMESTAMP.mp4` - Enhanced version
- `output/generated_TIMESTAMP_original.mp4` - Original version
- `output/audio_comparison/` - Both MP3 files for comparison

📖 **Full documentation**: See [AUPHONIC_SETUP.md](./AUPHONIC_SETUP.md) for detailed setup instructions and troubleshooting.

---

## 8) Notes & Next Steps

- **Timing**: We're using caption chunk boundaries. It's good enough for MVP. Add forced alignment later for word‑level highlights.
- **IFrame events**: For auto‑advance at segment end, wire the full YouTube JS API and listen to `onStateChange` + poll currentTime; seek to `end` + small epsilon.
- **Index growth**: For more than a few million segments, upgrade to Elasticsearch/OpenSearch.
- **Safety**: We never download video. Playback is via official embed only.

---

## 9) Hardening Checklist (Post‑MVP)

- Retry/backoff and quota handling on YouTube API.
- Language partitions per‑index for speed.
- Channel allow/deny lists to keep result quality high.
- Basic caching layer for `/search` hot queries.
- Simple telemetry: log query, top1 clickthrough, dwell, next‑rate.
