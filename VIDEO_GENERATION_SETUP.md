# Video Generation Setup Guide

This guide explains how to set up and use the video generation feature that creates stitched videos from user input text.

## Overview

The system takes a sentence like "hello world" and:
1. Breaks it into individual words
2. Finds video clips where each word is spoken
3. Downloads the specific segments from YouTube
4. Stitches them together into a single video
5. Serves the final video to the user

## Quick Start

### 1. Install Dependencies

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
# Apply schema (creates word_clips table)
sqlite3 data/youglish.db < schema.sql
```

### 3. Ingest Word-Level Data

```bash
# This populates the word_clips table from the WhisperX JSONL file
python ingest_whisperx.py
```

Expected output:
- Total entries processed: ~527,000
- Unique words: ~100,000
- Unique videos: ~55,000

### 4. Start the Backend

```bash
uvicorn app:app --reload --port 8000
```

### 5. Start the Frontend

```bash
cd ../frontend
npm run dev
```

Open http://localhost:5173

## How to Use

1. Enter text in the input box (e.g., "hello world")
2. Click the purple **"Generate Video"** button
3. Wait for video generation (may take 30-60 seconds)
4. Watch or download the generated video

## Architecture

### Backend (`backend/`)

**New Files:**
- `ingest_whisperx.py` - Parses JSONL and populates database
- Updated `app.py` - Added `/generate-video` endpoint
- Updated `schema.sql` - Added `word_clips` table

**Key Components:**
- `POST /generate-video` - Main API endpoint
- `VideoStitcher` - Existing class that handles video downloading and stitching
- `word_clips` table - Maps words to video clips with timing

### Frontend (`frontend/src/`)

**Updated Files:**
- `App.jsx` - Added Generate Video button and video player

**Key Features:**
- Generate Video button
- Video player with download link
- Error handling for missing words
- Loading states

### Database Schema

```sql
CREATE TABLE word_clips (
  word TEXT NOT NULL,
  video_id TEXT NOT NULL,
  start_time REAL NOT NULL,
  duration REAL NOT NULL,
  PRIMARY KEY (word, video_id, start_time)
);

CREATE INDEX idx_word_clips_word ON word_clips(word);
```

### Data Format

The WhisperX JSONL file contains:
```json
[
  {
    "role": "user",
    "content": [
      {"type": "video", "video": "video/youtube/VIDEO_ID.mp4", "video_start": 5.0, "video_end": 10.0}
    ]
  },
  {
    "role": "assistant",
    "content": [
      {"type": "text_stream", "text_stream": [[5.0, 5.5, "hello"], [5.5, 6.0, "world"], ...]}
    ]
  }
]
```

## API Usage

### Generate Video Request

```bash
curl -X POST http://localhost:8000/generate-video \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world", "lang": "en"}'
```

### Response

```json
{
  "status": "success",
  "video_url": "/videos/generated_1730000000.mp4",
  "message": "Video generated successfully with 2 words"
}
```

## Troubleshooting

### "No clips found for any words"

- Ensure the database is populated: `sqlite3 data/youglish.db "SELECT COUNT(*) FROM word_clips;"`
- Try simpler, common words first (e.g., "hello", "the", "and")

### "FFmpeg not found"

- Install FFmpeg: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)

### Video generation is slow

- First generation is slower due to YouTube downloads
- Subsequent generations with same words are faster (cached)
- Complex sentences take longer (more clips to download)

### Missing words in output

- The system will skip words not found in the database
- Check the response for `missing_words` array
- Try alternative phrasing

## Performance Notes

- **First generation**: 30-60 seconds (downloads required)
- **Database size**: ~14M word clips from 526K video segments
- **Coverage**: ~100K unique words
- **Video quality**: 720p by default (configurable)

## Future Improvements

- [ ] Background job processing for long videos
- [ ] Progress tracking during generation
- [ ] Word pronunciation variants
- [ ] Multi-language support
- [ ] Caching of downloaded segments
- [ ] Batch video generation
- [ ] Custom video quality selection

## Dataset Credit

The word-level timing data comes from the [Live-WhisperX-526K dataset](https://huggingface.co/datasets/chenjoya/Live-WhisperX-526K) by chenjoya, which provides accurate word-level transcriptions with timestamps for YouTube videos.

