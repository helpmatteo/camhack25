# ClipScribe 🎬

Generate engaging videos from text using real YouTube clips with word-level precision.

**Key Features:**
- 🎯 **Intelligent phrase matching** - Combines consecutive words from the same video for smoother output
- 🎵 **Professional audio enhancement** - Optional Auphonic integration for noise reduction and normalization
- 📝 **Interactive subtitles** - Click any word to jump to that moment in the video
- ⚡ **Fast parallel processing** - Concurrent download and processing for speed
- 🔍 **Full-text search** - Find and preview clips before generating

Built with FastAPI, React + Vite, FFmpeg, and SQLite FTS5.

---

## Quick Start

```bash
# 1. Backend setup
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your YouTube API key

# 2. Initialize database
python ingest.py           # Fetch video transcripts
python ingest_whisperx.py  # Import word-level timing data

# 3. Start servers (in separate terminals)
python run.py              # Backend on http://localhost:8000
cd ../frontend && npm i && npm run dev  # Frontend on http://localhost:5173
```

**Make sure you're logged into YouTube in Chrome** - the backend uses your browser cookies for authentication.

---

## Features

### 🎯 Intelligent Video Generation
- **Phrase matching**: Automatically finds multi-word phrases from the same video
- **Word-level precision**: Falls back to individual words when phrases aren't available
- **Smart clip extraction**: Adds subtle padding for natural transitions
- **Placeholder cards**: Creates title cards for missing words

### 🎵 Audio Enhancement (Optional)
- **Auphonic integration**: Professional noise reduction and normalization
- **Side-by-side comparison**: Keep original audio to hear the difference
- **Automatic processing**: Extract → enhance → merge workflow
- **Free tier available**: 2 hours/month on Auphonic

### 📝 Interactive Subtitles
- **Real-time sync**: Highlights current word as video plays
- **Clickable words**: Jump to any word instantly
- **Auto-scroll**: Keeps active word visible
- **Accurate timing**: Only includes clips that made it into the final video

### ⚡ Performance
- **Parallel processing**: Concurrent downloads and video processing
- **Batch concatenation**: Fast FFmpeg-based stitching
- **Smart caching**: Reuses processed segments
- **Configurable workers**: Adjust parallelism for your hardware

---

## Setup

### Prerequisites
- Python 3.8+
- Node.js 16+
- FFmpeg installed (`brew install ffmpeg` on macOS)
- Chrome browser with YouTube login (for cookie authentication)

### Backend Configuration

1. **Create `.env` file**:
```bash
cd backend
cp .env.example .env
```

2. **Edit `.env`** with your settings:
```env
# Required
YOUTUBE_API_KEY=your_youtube_api_key_here
SEED_CHANNEL_IDS=UCYO_jab_esuFRV4b17AJtAw,UC8butISFwT-Wl7EV0hUK0BQ

# Optional - Audio Enhancement
AUPHONIC_API_TOKEN=your_auphonic_token  # Get 2 free hours/month

# Optional - Cookie Source
COOKIES_FROM_BROWSER=chrome  # or firefox, safari, etc.
```

3. **Initialize database**:
```bash
python ingest.py              # Fetch transcripts from YouTube
python ingest_whisperx.py     # Import word-level timing data (526k words)
```

### Frontend Setup

```bash
cd frontend
npm install
```

Set custom API URL if needed:
```bash
VITE_API=http://localhost:8000 npm run dev
```

---

## Usage

### Generate Videos

1. Open the web interface at `http://localhost:5173`
2. Enter your text (e.g., "don't worry it's working")
3. Adjust phrase length slider (1-50 words)
4. Optional: Enable audio enhancement
5. Click **Generate Video**

### API Endpoints

#### `POST /generate-video`
Generate a stitched video from text.

**Request**:
```json
{
  "text": "hello world",
  "max_phrase_length": 10,
  "enhance_audio": false,
  "keep_original_audio": true,
  "add_subtitles": false,
  "aspect_ratio": "16:9"
}
```

**Response**:
```json
{
  "status": "success",
  "video_url": "/videos/generated_1234567890.mp4",
  "word_timings": [
    {"word": "hello", "start": 0.0, "end": 0.5},
    {"word": "world", "start": 0.5, "end": 1.2}
  ],
  "original_video_url": "/videos/generated_1234567890_original.mp4"
}
```

#### `GET /search`
Search for phrases in video transcripts.

```bash
curl 'http://localhost:8000/search?q=hello%20world&lang=en&limit=20'
```

---

## Advanced Configuration

### Video Generation Options

```python
{
  "text": "your text here",
  "max_phrase_length": 10,          # 1-50, longer = smoother videos
  "clip_padding_start": 0.15,       # Seconds before word
  "clip_padding_end": 0.15,         # Seconds after word
  "add_subtitles": false,           # Burn-in subtitles
  "aspect_ratio": "16:9",           # or "9:16", "1:1"
  "watermark_text": null,           # Optional watermark
  "intro_text": null,               # Optional intro card
  "outro_text": null,               # Optional outro card
  "enhance_audio": false,           # Auphonic enhancement
  "keep_original_audio": true,      # Save comparison file
  "max_download_workers": 3,        # Parallel downloads
  "max_processing_workers": 4       # Parallel processing
}
```

### Audio Enhancement Setup

1. **Get Auphonic API token**: [Sign up](https://auphonic.com/) (2 free hours/month)
2. **Add to `.env`**: `AUPHONIC_API_TOKEN=your_token`
3. **Enable in UI**: Toggle "Audio Enhancement" when generating videos

**What it does**:
- Noise reduction (dynamic/speech_isolation method)
- Hum removal (50/60 Hz mains)
- Volume leveling
- Loudness normalization (-16 LUFS)
- De-reverb and de-breath processing

📖 See `AUPHONIC_SETUP.md` for detailed configuration options.

### Command Line Interface

```bash
# Generate video via CLI
python -m video_stitcher.cli \
  --text "hello world" \
  --database data/youglish.db \
  --output test.mp4 \
  --max-phrase-length 10 \
  --enhance-audio \
  --verbose

# Test phrase matching
python test_phrase_matching.py
```

---

## Architecture

```
backend/
  ├── app.py                    # FastAPI server
  ├── db.py                     # Database queries
  ├── ingest.py                 # YouTube transcript fetcher
  ├── ingest_whisperx.py        # Word-level data importer
  ├── video_stitcher/           # Video generation engine
  │   ├── video_stitcher.py     # Main orchestrator
  │   ├── database.py           # Word/phrase lookup
  │   ├── downloader.py         # yt-dlp integration
  │   ├── video_processor.py    # FFmpeg operations
  │   ├── concatenator.py       # Video stitching
  │   └── auphonic_client.py    # Audio enhancement
  └── data/
      ├── youglish.db           # SQLite + FTS5 index
      └── live_whisperx_526k_with_seeks.jsonl

frontend/
  └── src/
      └── App.jsx               # React UI with interactive subtitles
```

### How It Works

1. **Phrase Matching**: Searches for longest consecutive word sequences in the same video
2. **Fallback**: Uses individual words when phrases aren't found
3. **Download**: Extracts specific time segments using yt-dlp
4. **Processing**: Normalizes audio, re-encodes for consistency, adds optional effects
5. **Enhancement**: Optional Auphonic processing for professional audio
6. **Concatenation**: Stitches all segments using FFmpeg
7. **Subtitles**: Generates word timings for interactive playback

---

## Troubleshooting

### Video Generation Issues

**"Failed to download segment"**
- Ensure you're logged into YouTube in Chrome
- Try: `COOKIES_FROM_BROWSER=firefox` in `.env` if using Firefox
- See `YOUTUBE_COOKIE_SETUP.md` for detailed auth setup

**"No clips found for word"**
- Word may not exist in the 526k word database
- Try different phrasing or check spelling
- System will create placeholder title cards for missing words

**"Auphonic API token not set"**
- Add `AUPHONIC_API_TOKEN` to `.env`
- Get token from https://auphonic.com/
- Run `pip install python-dotenv` if missing

### Performance Tuning

**Slow generation?**
- Increase `max_download_workers` (default: 3)
- Increase `max_processing_workers` (default: 4)
- Disable `enhance_audio` for faster results
- Use shorter `max_phrase_length` for quicker lookups

**Out of memory?**
- Decrease worker counts
- Process videos sequentially (set workers to 1)
- Clear temp directory: `rm -rf backend/temp/*`

---

## Tech Stack

**Backend:**
- FastAPI - Modern Python web framework
- SQLite + FTS5 - Full-text search index
- yt-dlp - YouTube video downloader
- FFmpeg - Video/audio processing
- Auphonic API - Professional audio enhancement

**Frontend:**
- React 18 + Vite - Fast development and build
- Tailwind CSS - Utility-first styling
- YouTube IFrame API - Video playback

**Data:**
- WhisperX transcriptions - Word-level timing accuracy
- 526k word database - Comprehensive clip coverage