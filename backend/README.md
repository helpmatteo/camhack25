# YouGlish-lite Backend

A FastAPI backend for searching YouTube video transcripts with full-text search capabilities.

## Features

- **Full-text search** using SQLite FTS5 for fast phrase matching
- **Multi-language support** for filtering searches by language
- **RESTful API** with automatic documentation
- **CORS enabled** for frontend integration
- **YouTube data ingestion** from channels via YouTube API

## Prerequisites

- Python 3.8+
- pip

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database:
```bash
python init_db.py
```

## Running the Server

### Quick Start
```bash
python run.py
```

The server will start at `http://localhost:8000`

### Manual Start
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### Health Check
```
GET /health
```

Returns server status.

**Response:**
```json
{"ok": true}
```

### Search
```
GET /search?q=<phrase>&lang=<language>&limit=<number>
```

Search for exact phrases in video transcripts.

**Parameters:**
- `q` (required): Search phrase (exact match)
- `lang` (optional): Language code filter (e.g., "en", "es", "fr")
- `limit` (optional): Maximum results to return (default: 20)

**Response:**
```json
[
  {
    "id": 1,
    "video_id": "dQw4w9WgXcQ",
    "lang": "en",
    "t_start": 10.5,
    "t_end": 15.2,
    "text": "Never gonna give you up",
    "title": "Rick Astley - Never Gonna Give You Up",
    "channel_title": "Rick Astley"
  }
]
```

## Interactive API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Data Ingestion

To populate the database with YouTube data:

1. Create a `.env` file:
```bash
YOUTUBE_API_KEY=your_api_key_here
SEED_CHANNEL_IDS=UC_channel_id_1,UC_channel_id_2
DB_PATH=./data/youglish.db
```

2. Run the ingestion script:
```bash
python ingest.py
```

This will:
- Fetch videos from the specified channels
- Download available transcripts
- Store them in the database with FTS indexing

### Populating Video Metadata (Channel IDs)

After ingesting video data (especially from WhisperX), you can populate the `videos` table with metadata including channel IDs:

```bash
export YOUTUBE_API_KEY=your_api_key_here
python populate_video_metadata.py
```

This script will:
- Fetch all unique video IDs from your database
- Request metadata from YouTube API in batches of 50
- Populate the `videos` table with:
  - `channel_id`
  - `channel_title` 
  - `title`
  - `published_at`

Note: This is especially useful after running `ingest_whisperx.py` since that script only populates word-level timing data but not video metadata.

## Testing

Run the test suite:
```bash
python test_backend.py
```

Run server integration tests:
```bash
python test_server.py
```

## Project Structure

```
backend/
├── app.py              # FastAPI application & routes
├── db.py               # Database connection & search logic
├── ingest.py           # YouTube data ingestion script
├── youtube.py          # YouTube API wrapper
├── schema.sql          # Database schema with FTS5
├── init_db.py          # Database initialization script
├── run.py              # Server startup script
├── test_backend.py     # Backend functionality tests
├── test_server.py      # API integration tests
├── requirements.txt    # Python dependencies
└── data/               # SQLite database directory
    └── youglish.db
```

## Database Schema

### Tables

- `videos`: Stores video metadata (video_id, title, channel info)
- `segments`: Stores transcript segments with timestamps
- `segments_fts`: FTS5 virtual table for full-text search

### Full-Text Search

The backend uses SQLite's FTS5 (Full-Text Search) extension with:
- Unicode tokenization with diacritics removal
- Automatic triggers to keep FTS index in sync
- Phrase matching with quotes

## Environment Variables

- `DB_PATH`: Database file path (default: `./data/youglish.db`)
- `YOUTUBE_API_KEY`: YouTube Data API v3 key
- `SEED_CHANNEL_IDS`: Comma-separated list of YouTube channel IDs

## Troubleshooting

### Database not found
Run `python init_db.py` to create and initialize the database.

### No search results
The database needs to be populated first. Either:
1. Run `python ingest.py` to fetch data from YouTube
2. Or insert test data with `python test_backend.py`

### CORS errors
The API has CORS enabled for all origins (`allow_origins=["*"]`). For production, restrict this to specific domains.

## License

MIT

