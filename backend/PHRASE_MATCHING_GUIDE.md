# Phrase Matching Guide

## Overview

The video stitcher now includes **phrase matching** - an intelligent feature that creates smoother videos by using longer clips when consecutive words come from the same source video, rather than cutting between individual word clips.

## How It Works

### Before (Individual Words)
When you request: "hello world how are you"

**Old behavior:** 5 separate clips, 5 cuts
- Clip 1: "hello" (0.5s from video A)
- Clip 2: "world" (0.6s from video A) 
- Clip 3: "how" (0.4s from video A)
- Clip 4: "are" (0.3s from video A)
- Clip 5: "you" (0.5s from video A)

### After (Phrase Matching)
**New behavior:** 1 continuous clip, 0 cuts
- Clip 1: "hello world how are you" (2.3s from video A)

Much smoother! 🎬

## Setup

### 1. Migrate Your Database

First, add the new `video_transcripts` table to your existing database:

```bash
cd backend
python migrate_db.py data/youglish.db
```

This adds a new table without affecting your existing `word_clips` data.

### 2. Re-ingest Your Data

Update your database with full transcript information:

```bash
python ingest_whisperx.py
```

This will:
- Keep all your existing word-to-clip mappings (backward compatible)
- Add complete transcript data for phrase matching
- Show progress: words inserted + transcripts stored

## Usage

### Using the CLI

The phrase matching works automatically - no changes to your commands:

```bash
# Simple text generation
python -m video_stitcher.cli \
  --text "hello world how are you" \
  --database data/youglish.db \
  --output output/my_video.mp4

# With verbose logging (see phrase matching in action)
python -m video_stitcher.cli \
  --text "the quick brown fox jumps" \
  --database data/youglish.db \
  --output output/fox_video.mp4 \
  --verbose
```

### Using the Python API

```python
from video_stitcher import VideoStitcher, StitchingConfig

# Create configuration
config = StitchingConfig(
    database_path="data/youglish.db",
    output_directory="./output"
)

# Initialize stitcher
stitcher = VideoStitcher(config)

# Generate video (phrase matching happens automatically)
output_path = stitcher.generate_video(
    text="hello world how are you today",
    output_filename="greeting.mp4"
)

print(f"Video created: {output_path}")
```

## How Phrase Matching Works

### Algorithm

1. **Try longest phrases first** (up to 10 words)
2. **Search transcripts** for consecutive word matches
3. **Fall back to individual words** if no phrase found
4. **Repeat** for remaining words

### Example Walkthrough

Input: "hello world how are you"

```
Step 1: Try "hello world how are you" (5 words) → Not found
Step 2: Try "hello world how are" (4 words) → Not found  
Step 3: Try "hello world how" (3 words) → Not found
Step 4: Try "hello world" (2 words) → ✓ Found in video_1!
  → Add clip for "hello world" (0.0s - 1.1s)
  → Move to position 2 (skip past "hello" and "world")

Step 5: Try "how are you" (3 words) → ✓ Found in video_1!
  → Add clip for "how are you" (1.1s - 2.3s)
  → Done!

Result: 2 clips instead of 5, both from same video = seamless!
```

### Benefits

✅ **Smoother videos** - Fewer cuts between clips  
✅ **Natural flow** - Preserves original speech rhythm  
✅ **Better audio** - Less audio processing artifacts  
✅ **Faster processing** - Fewer segments to download/process  
✅ **Backward compatible** - Falls back to word-by-word if needed

## Testing Phrase Matching

Run the test suite to verify everything works:

```bash
cd backend
python test_phrase_matching.py
```

Expected output:
```
✓ Test 1: Single words lookup
✓ Test 2: Two-word phrase 'hello world'
✓ Test 3: Three-word phrase 'how are you'
✓ Test 4: Mixed lookup (phrase + individual)
✓ Test 5: Different videos (no phrase)
✓ Test 6: Missing word handling

All tests passed! ✓
```

## Monitoring Phrase Matching

### Verbose Mode

Use `--verbose` flag to see phrase matching in action:

```bash
python -m video_stitcher.cli \
  --text "the quick brown fox" \
  --database data/youglish.db \
  --output output/test.mp4 \
  --verbose
```

Look for log messages like:
```
INFO: Found 3-word phrase: 'the quick brown'
INFO: Found 2-word phrase: 'hello world'
DEBUG: Phrase not found in any transcript: xyz
```

### Check Database Stats

```python
from video_stitcher.database import WordClipDatabase

db = WordClipDatabase("data/youglish.db")
stats = db.get_database_stats()

print(f"Total words: {stats['total_words']}")
print(f"Unique videos: {stats['unique_videos']}")
print(f"Phrase matching: {'Enabled' if db.has_transcripts else 'Disabled'}")
```

## Troubleshooting

### Phrase Matching Not Working?

**Check if transcripts table exists:**
```bash
sqlite3 data/youglish.db "SELECT COUNT(*) FROM video_transcripts;"
```

If error → Run migration: `python migrate_db.py data/youglish.db`

**Check if transcripts have data:**
```bash
sqlite3 data/youglish.db "SELECT COUNT(*) FROM video_transcripts;"
```

If zero → Run ingestion: `python ingest_whisperx.py`

### Still Using Individual Words?

This is normal when:
- Words come from different videos (can't combine)
- Phrase not found in any single video
- Only single words requested

The system automatically falls back to word-by-word lookup.

### Performance Issues?

Phrase matching adds minimal overhead:
- ~10ms per word for phrase search
- Saves time by reducing clips to process
- Net result: Usually faster overall!

## Advanced Configuration

### Adjust Maximum Phrase Length

Default is 10 words. To customize, edit `video_stitcher.py`:

```python
# In lookup_clips method
max_phrase_len = min(15, len(words) - i)  # Changed from 10 to 15
```

### Disable Phrase Matching

If you need to disable it temporarily:

```python
# Option 1: Use database without video_transcripts table
config = StitchingConfig(
    database_path="old_database.db",  # Database without transcripts
    ...
)

# Option 2: Database will automatically detect and disable
# if video_transcripts table doesn't exist
```

## Data Format

### video_transcripts Table Schema

```sql
CREATE TABLE video_transcripts (
    video_id TEXT PRIMARY KEY,
    transcript_data TEXT NOT NULL,  -- JSON: [[word, start, end], ...]
    word_count INTEGER,
    duration REAL
);
```

### Transcript Data Format

Stored as JSON array:
```json
[
    ["hello", 0.0, 0.5],
    ["world", 0.5, 1.1],
    ["how", 1.1, 1.5]
]
```

Each entry: `[word, start_time, end_time]`

## Examples

### Example 1: Short Greeting
```bash
python -m video_stitcher.cli \
  --text "hello how are you" \
  --database data/youglish.db \
  --output greetings/hello.mp4
```

**Result:** Likely 1-2 clips (depending on source videos)

### Example 2: Longer Sentence
```bash
python -m video_stitcher.cli \
  --text "the quick brown fox jumps over the lazy dog" \
  --database data/youglish.db \
  --output animals/fox.mp4 \
  --verbose
```

**Result:** Multiple phrases combined for smooth flow

### Example 3: Mixed Sources
```bash
python -m video_stitcher.cli \
  --text "artificial intelligence is transforming technology" \
  --database data/youglish.db \
  --output tech/ai.mp4
```

**Result:** Best effort phrase matching with fallback to words

## Best Practices

1. **Use verbose mode** during development to understand behavior
2. **Keep transcripts updated** - Re-ingest when adding new videos
3. **Monitor clip count** - Fewer clips = better phrase matching
4. **Test with common phrases** - Verify quality before production
5. **Check logs** - Look for "Found N-word phrase" messages

## Summary

Phrase matching makes your generated videos significantly smoother by:
- Finding longer consecutive clips from source videos
- Reducing the number of cuts and transitions
- Maintaining natural speech flow
- Preserving audio quality

It works automatically with zero configuration changes - just migrate your database and re-ingest your data!

---

**Questions?** Check the logs with `--verbose` or examine the test suite in `test_phrase_matching.py` for detailed examples.
