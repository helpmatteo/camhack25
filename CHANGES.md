# Recent Changes - Port Auto-Detection & YouTube Authentication

## Summary

Fixed two major issues:
1. ✅ **Port conflicts** - Backend now auto-detects available ports
2. ✅ **YouTube bot detection** - Backend now uses browser cookies for authentication

## What Changed

### 1. Auto Port Detection (`backend/run.py`)

**Before:**
- Always tried to use port 8000
- Failed if port was in use

**After:**
- Automatically finds first available port (8000, 8001, 8002, etc.)
- Writes port to `frontend/.env.local` so frontend connects correctly
- Shows which port is being used on startup

**New features:**
```python
def find_available_port(start_port=8000, max_attempts=100)
def write_frontend_env(port)
```

### 2. YouTube Cookie Authentication

**Files Modified:**
- `backend/video_stitcher/downloader.py` - Added cookie support to yt-dlp
- `backend/video_stitcher/video_stitcher.py` - Added cookies_from_browser config
- `backend/app.py` - Read COOKIES_FROM_BROWSER env var

**New Configuration:**
```python
# In StitchingConfig
cookies_from_browser: str = None

# In VideoDownloaderConfig  
cookies_from_browser: str = None
```

**Environment Variable:**
```bash
COOKIES_FROM_BROWSER=chrome  # or firefox, safari, edge, etc.
```

**How it works:**
1. Extracts cookies from your browser (where you're logged into YouTube)
2. Uses them to authenticate video downloads
3. Bypasses YouTube's bot detection

### 3. New Files Created

#### `start.sh`
Convenient script to start both backend and frontend:
```bash
./start.sh
```
- Starts backend on auto-detected port
- Updates frontend config automatically
- Starts frontend dev server
- Ctrl+C stops both

#### `YOUTUBE_COOKIE_SETUP.md`
Complete guide for setting up YouTube authentication:
- Why it's needed
- How to configure different browsers
- Troubleshooting steps
- Security notes

#### `TROUBLESHOOTING.md`
Comprehensive troubleshooting guide:
- Port conflicts (now auto-fixed)
- YouTube authentication issues
- Common errors and solutions
- Quick diagnostic checklist

#### `backend/.env.example` (attempted)
Example environment file showing available options

### 4. Documentation Updates

#### `README.md`
- Added YouTube Authentication section
- Added Quick Start with `./start.sh`
- Updated usage instructions
- Referenced new troubleshooting docs

## How to Use

### Option 1: Use the Startup Script (Easiest)
```bash
./start.sh
```

### Option 2: Manual Start
```bash
# Terminal 1 - Backend
cd backend
python run.py

# Terminal 2 - Frontend
cd frontend
npm run dev
```

## Requirements

### Must Have:
1. ✅ Logged into YouTube in Chrome (or another browser)
2. ✅ Browser installed on system where backend runs

### Optional:
- Set `COOKIES_FROM_BROWSER` env var to use a different browser

## Testing Your Setup

1. **Start servers:**
   ```bash
   ./start.sh
   ```

2. **Check backend logs for:**
   ```
   ✓ Updated frontend config to use port 8001
   YouTube cookies from: chrome
   💡 Tip: Make sure you're logged into YouTube in Chrome
   ```

3. **Try generating a video:**
   - Open frontend in browser
   - Enter some text: "hello world"
   - Click "Generate Video"
   - Should work without bot detection errors!

## Troubleshooting

If you see errors, check:

### Port Issues
✅ **Auto-fixed!** The backend will find an available port automatically.

### YouTube Bot Detection
```
ERROR: [youtube] Sign in to confirm you're not a bot
```

**Fix:**
1. Make sure you're logged into YouTube in Chrome
2. Restart the backend
3. See `YOUTUBE_COOKIE_SETUP.md` for detailed help

### Frontend Can't Connect
If frontend shows network errors:
1. Restart frontend (it will pick up new backend port)
2. Or use `./start.sh` to start both together

## Configuration Reference

### Environment Variables

Create `backend/.env`:
```bash
# Database
DB_PATH=./data/youglish.db

# YouTube Authentication (NEW)
COOKIES_FROM_BROWSER=chrome

# YouTube API (existing)
YOUTUBE_API_KEY=your_key_here
SEED_CHANNEL_IDS=channel1,channel2
```

### Supported Browsers
- chrome (default)
- firefox
- safari (macOS only)
- edge
- chromium
- opera
- brave

## Benefits

### Before:
- ❌ Manual port management
- ❌ Port conflicts caused errors
- ❌ YouTube blocked video downloads
- ❌ Lots of manual configuration

### After:
- ✅ Automatic port detection
- ✅ Frontend auto-configures
- ✅ YouTube authentication works
- ✅ One command to start everything
- ✅ Comprehensive troubleshooting docs

## Migration Notes

If you were running the old version:

1. **Stop all servers** (Ctrl+C)
2. **Pull/checkout latest code** (you already have it)
3. **Login to YouTube in Chrome**
4. **Restart:** `./start.sh`
5. **Done!** No other changes needed

Your existing database, data files, and configuration remain unchanged.

## Next Steps

1. Test video generation with the new setup
2. If using a browser other than Chrome, set `COOKIES_FROM_BROWSER`
3. Read `YOUTUBE_COOKIE_SETUP.md` for advanced configuration
4. Enjoy seamless video generation! 🎉

