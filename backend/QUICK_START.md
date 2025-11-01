# Video Stitcher - Quick Start Guide

## What Is This?

The Video Stitcher generates videos from text by finding and combining clips of real people speaking each word from a database of YouTube videos. With **phrase matching**, it creates smooth, natural-looking videos.

## Quick Start (3 Steps)

### 1. Set Up Database

```bash
# If you have an existing database, migrate it
cd backend
python migrate_db.py data/youglish.db

# Ingest data (WhisperX format)
python ingest_whisperx.py
```

### 2. Generate Your First Video

```bash
python -m video_stitcher.cli \
  --text "hello world" \
  --database data/youglish.db \
  --output my_first_video.mp4
```

### 3. Watch It!

Open `my_first_video.mp4` in your video player.

## Key Features

### 🎯 Phrase Matching (NEW!)
Automatically combines consecutive words from the same video for smoother output:
- **Before:** 10 words = 10 clips = 9 cuts
- **After:** 10 words = 2-3 clips = 1-2 cuts

### 📊 Smart Database
Two-table design:
- `word_clips`: Fast individual word lookup
- `video_transcripts`: Full transcript data for phrases

### 🎬 Professional Quality
- Consistent video encoding (H.264, 30fps)
- Normalized audio levels
- Smooth transitions
- Automatic cleanup

## Common Commands

### Generate with Verbose Logging
```bash
python -m video_stitcher.cli \
  --text "your text here" \
  --database data/youglish.db \
  --output video.mp4 \
  --verbose
```

### Check Database Stats
```bash
python -c "
from video_stitcher.database import WordClipDatabase
db = WordClipDatabase('data/youglish.db')
print(db.get_database_stats())
"
```

### Test Everything
```bash
# Test phrase matching
python test_phrase_matching.py

# Test full system
pytest tests/test_video_stitcher.py -v
```

## Python API

### Basic Usage
```python
from video_stitcher import VideoStitcher, StitchingConfig

config = StitchingConfig(
    database_path="data/youglish.db",
    output_directory="./output"
)

stitcher = VideoStitcher(config)
video_path = stitcher.generate_video(
    text="hello world",
    output_filename="greeting.mp4"
)
```

### With Progress Callback
```python
def on_progress(current, total):
    print(f"Progress: {current}/{total}")

video_path = stitcher.generate_video(
    text="hello world",
    output_filename="greeting.mp4",
    progress_callback=on_progress
)
```

### Custom Configuration
```python
config = StitchingConfig(
    database_path="data/youglish.db",
    output_directory="./output",
    temp_directory="./temp",
    video_quality="bestvideo[height<=1080]+bestaudio",
    normalize_audio=True,
    incremental_stitching=True,
    cleanup_temp_files=True,
    verify_ffmpeg_on_init=True
)
```

## File Structure

```
backend/
├── video_stitcher/          # Main package
│   ├── __init__.py          # Package exports
│   ├── database.py          # Database interface
│   ├── downloader.py        # YouTube downloader
│   ├── video_processor.py   # FFmpeg operations
│   ├── concatenator.py      # Video stitching
│   ├── video_stitcher.py    # Main orchestrator
│   └── cli.py               # Command-line interface
├── data/
│   └── youglish.db          # Word/video database
├── ingest_whisperx.py       # Data ingestion script
├── migrate_db.py            # Database migration
├── test_phrase_matching.py  # Phrase matching tests
└── tests/
    └── test_video_stitcher.py  # Full test suite
```

## Requirements

### System Dependencies
- Python 3.8+
- ffmpeg (for video processing)
- yt-dlp (for downloading)

### Install
```bash
pip install -r requirements.txt
```

### Check Installation
```bash
# Check ffmpeg
ffmpeg -version

# Check yt-dlp
yt-dlp --version

# Check Python packages
python -c "import sqlite3, pytest; print('OK')"
```

## Workflow

### 1. Data Preparation
```
WhisperX JSONL → ingest_whisperx.py → SQLite Database
                                        ├── word_clips
                                        └── video_transcripts
```

### 2. Video Generation
```
Text Input → Parse Words → Phrase Matching → Download Clips → Process → Stitch → Output
```

### 3. Phrase Matching Logic
```
For each word:
  1. Try longest phrase (up to 10 words)
  2. Search transcripts for match
  3. If found: use phrase clip
  4. If not found: try shorter phrase
  5. If no phrase: use single word
  6. Move to next word
```

## Tips & Tricks

### 🚀 Performance
- Use `incremental_stitching=True` for memory efficiency
- Enable `cleanup_temp_files=True` to save disk space
- Lower `video_quality` for faster processing

### 🎨 Quality
- Use `normalize_audio=True` for consistent volume
- Keep phrases under 10 words for best matching
- Check logs with `--verbose` to understand behavior

### 🐛 Debugging
- Run with `--verbose` to see detailed logs
- Check `temp/` directory if video fails
- Use `verify_ffmpeg_on_init=False` for unit tests
- Examine database with: `sqlite3 data/youglish.db`

### 📈 Optimization
- More videos in database = better phrase matching
- Common words = more clip options
- Longer phrases = smoother output

## Troubleshooting

### "Database file not found"
```bash
# Check path
ls data/youglish.db

# Create if missing
python ingest_whisperx.py
```

### "Table 'video_transcripts' does not exist"
```bash
# Run migration
python migrate_db.py data/youglish.db
```

### "No clip found for word: xyz"
- Word doesn't exist in database
- Add more source videos
- Use alternative spelling

### "Failed to download segment"
- Check internet connection
- Video might be private/deleted
- Try again (temporary YouTube issue)

### "FFmpeg not found"
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg

# Check installation
ffmpeg -version
```

## Examples

### Example 1: Simple Greeting
```bash
python -m video_stitcher.cli \
  --text "hello my name is alice" \
  --database data/youglish.db \
  --output greetings/alice.mp4
```

### Example 2: Technical Phrase
```bash
python -m video_stitcher.cli \
  --text "machine learning is transforming artificial intelligence" \
  --database data/youglish.db \
  --output tech/ml_ai.mp4 \
  --verbose
```

### Example 3: Batch Processing
```python
from video_stitcher import VideoStitcher, StitchingConfig

config = StitchingConfig(database_path="data/youglish.db")
stitcher = VideoStitcher(config)

texts = [
    "hello world",
    "good morning",
    "thank you"
]

for i, text in enumerate(texts):
    stitcher.generate_video(
        text=text,
        output_filename=f"video_{i}.mp4"
    )
```

## Resources

- **Phrase Matching Guide**: See `PHRASE_MATCHING_GUIDE.md` for details
- **API Documentation**: Inline docstrings in all modules
- **Test Suite**: `tests/test_video_stitcher.py`
- **Example Tests**: `test_phrase_matching.py`

## Support

### Check Logs
```bash
# Run with verbose mode
python -m video_stitcher.cli --text "test" --database data/youglish.db --output test.mp4 --verbose
```

### Verify Setup
```bash
# Run all tests
pytest tests/ -v

# Run phrase matching tests
python test_phrase_matching.py
```

### Database Inspection
```bash
# Open database
sqlite3 data/youglish.db

# Check tables
.tables

# Count words
SELECT COUNT(*) FROM word_clips;

# Count transcripts
SELECT COUNT(*) FROM video_transcripts;

# Sample data
SELECT * FROM word_clips LIMIT 5;
```

---

**Ready to create your first video?** Run:
```bash
python -m video_stitcher.cli --text "hello world" --database data/youglish.db --output hello.mp4 --verbose
```