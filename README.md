# Video Stitcher

A Python system that takes text input, looks up YouTube clips for each word in a SQLite database, downloads video segments, and stitches them into a final video.

## Features

- 🎬 **Text-to-Video**: Convert any text into a video using pre-mapped word clips
- 🔍 **Database-Driven**: SQLite database maps words to specific YouTube video segments
- 🎵 **Audio Normalization**: Ensures consistent audio levels across all clips
- ⚡ **Incremental Processing**: Memory-efficient video concatenation
- 🛠️ **Flexible CLI**: Easy-to-use command-line interface
- 🧪 **Well-Tested**: Comprehensive test suite with fixtures

## Requirements

- Python 3.7+
- ffmpeg (for video processing)
- Internet connection (for downloading YouTube videos)

## Installation

### 1. Install ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install yt-dlp
pip install pytest  # For running tests
```

## Quick Start

### Creating a Test Database

First, create a SQLite database with word-to-clip mappings. You can use the test fixture from our test suite or create your own:

```python
import sqlite3

# Create database
conn = sqlite3.connect('my_words.db')
cursor = conn.cursor()

# Create table
cursor.execute("""
    CREATE TABLE word_clips (
        word TEXT PRIMARY KEY,
        video_id TEXT NOT NULL,
        start_time REAL NOT NULL,
        duration REAL NOT NULL
    )
""")

# Add word mappings (video_id, start time in seconds, duration in seconds)
words = [
    ("hello", "jNQXAC9IVRw", 5.0, 1.5),
    ("world", "jNQXAC9IVRw", 10.0, 1.2),
    ("python", "kqtD5dpn9C8", 5.0, 1.3),
]

cursor.executemany("""
    INSERT INTO word_clips (word, video_id, start_time, duration)
    VALUES (?, ?, ?, ?)
""", words)

conn.commit()
conn.close()
```

### Using the CLI

```bash
python -m video_stitcher.cli --text "hello world" --database my_words.db
```

This will create a video at `./output/output.mp4` containing clips for "hello" and "world" stitched together.

### Advanced CLI Usage

```bash
# Custom output location
python -m video_stitcher.cli \
    --text "hello world python" \
    --database my_words.db \
    --output my_video.mp4 \
    --output-dir ./videos

# Verbose mode for debugging
python -m video_stitcher.cli \
    --text "hello world" \
    --database my_words.db \
    --verbose

# Keep temporary files
python -m video_stitcher.cli \
    --text "hello world" \
    --database my_words.db \
    --no-cleanup

# Disable audio normalization
python -m video_stitcher.cli \
    --text "hello world" \
    --database my_words.db \
    --no-normalize
```

## Python API

### Basic Usage

```python
from video_stitcher import VideoStitcher, StitchingConfig

# Create configuration
config = StitchingConfig(
    database_path="my_words.db",
    output_directory="./output",
    temp_directory="./temp"
)

# Create stitcher and generate video
with VideoStitcher(config) as stitcher:
    output_path = stitcher.generate_video(
        text="hello world python",
        output_filename="output.mp4"
    )
    
print(f"Video created: {output_path}")
```

### With Progress Callback

```python
from video_stitcher import VideoStitcher, StitchingConfig

def show_progress(current, total):
    print(f"Processing: {current}/{total} ({current/total*100:.1f}%)")

config = StitchingConfig(database_path="my_words.db")

with VideoStitcher(config) as stitcher:
    output_path = stitcher.generate_video(
        text="hello world",
        output_filename="output.mp4",
        progress_callback=show_progress
    )
```

### Custom Configuration

```python
from video_stitcher import VideoStitcher, StitchingConfig

config = StitchingConfig(
    database_path="my_words.db",
    output_directory="./my_videos",
    temp_directory="./temp_processing",
    video_quality="bestvideo[height<=1080]+bestaudio/best[height<=1080]",  # 1080p
    normalize_audio=True,
    incremental_stitching=True,
    cleanup_temp_files=True
)

with VideoStitcher(config) as stitcher:
    output_path = stitcher.generate_video(
        text="hello world",
        output_filename="hd_output.mp4"
    )
```

## Configuration Options

### StitchingConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_path` | str | Required | Path to SQLite database |
| `output_directory` | str | `"./output"` | Directory for output videos |
| `temp_directory` | str | `"./temp"` | Directory for temporary files |
| `video_quality` | str | `"bestvideo[height<=720]+bestaudio/best[height<=720]"` | yt-dlp format string |
| `normalize_audio` | bool | `True` | Enable audio normalization |
| `incremental_stitching` | bool | `True` | Use incremental concatenation (memory efficient) |
| `cleanup_temp_files` | bool | `True` | Delete temporary files after completion |

## Database Schema

The SQLite database must contain a table named `word_clips` with the following schema:

```sql
CREATE TABLE word_clips (
    word TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    start_time REAL NOT NULL,
    duration REAL NOT NULL
);
```

### Fields

- **word**: The word in lowercase (primary key)
- **video_id**: YouTube video ID (11 characters, e.g., "dQw4w9WgXcQ")
- **start_time**: Start time in seconds (float)
- **duration**: Duration in seconds (float)

### Example Data

```sql
INSERT INTO word_clips (word, video_id, start_time, duration) VALUES
    ('hello', 'jNQXAC9IVRw', 5.0, 1.5),
    ('world', 'jNQXAC9IVRw', 10.0, 1.2),
    ('python', 'kqtD5dpn9C8', 5.0, 1.3);
```

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test

```bash
pytest tests/test_video_stitcher.py::TestDatabase::test_get_clip_info_existing_word -v
```

### Run With Coverage

```bash
pytest tests/ --cov=video_stitcher --cov-report=html
```

### Test Database Generator

The test suite includes a fixture that generates a test database:

```python
import pytest
from tests.test_video_stitcher import test_database

def test_my_feature(test_database):
    # test_database is a path to a SQLite database with sample data
    pass
```

## Project Structure

```
video_stitcher/
├── __init__.py              # Package initialization
├── database.py              # Database interface module
├── downloader.py            # Video segment downloader
├── video_processor.py       # Video processing (ffmpeg)
├── concatenator.py          # Video concatenation
├── video_stitcher.py        # Main orchestrator
└── cli.py                   # Command-line interface

tests/
├── __init__.py
└── test_video_stitcher.py   # Comprehensive test suite

docs/
└── stitcher.txt             # Implementation plan

README.md                     # This file
example.py                    # Usage examples
requirements.txt              # Python dependencies
```

## Troubleshooting

### "ffmpeg is not installed"

Make sure ffmpeg is installed and available in your PATH. Test with:
```bash
ffmpeg -version
```

### "Database file not found"

Ensure the database file exists and the path is correct:
```python
from pathlib import Path
print(Path("my_words.db").exists())  # Should print True
```

### "Failed to download segment"

This can happen if:
- Video is not available in your region
- Video has been deleted
- Network connection issues
- Invalid video_id

Check video availability:
```bash
yt-dlp --get-title "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Memory Issues with Large Videos

Enable incremental stitching (default):
```python
config = StitchingConfig(
    database_path="my_words.db",
    incremental_stitching=True
)
```

### Temporary Files Not Cleaned Up

Files are cleaned up automatically unless:
- `cleanup_temp_files=False` in config
- Process was interrupted (Ctrl+C)
- An error occurred

Manually clean up:
```bash
rm -rf ./temp ./output
```

## Performance

Typical performance on a modern machine:

- Download segment: < 5 seconds per clip
- Process segment: < 2 seconds per clip
- Concatenate 10 clips: < 10 seconds
- **Total for 10-word video: < 2 minutes**

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Built with [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube downloads
- Uses [ffmpeg](https://ffmpeg.org/) for video processing
- Inspired by word-based video composition projects

## Support

For issues, questions, or contributions, please visit the GitHub repository.