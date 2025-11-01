# Troubleshooting Guide

## Common Issues and Solutions

### 1. Port Already in Use

**Error:**
```
ERROR: [Errno 48] Address already in use
```

**Solution:**
✅ **FIXED!** The backend now automatically finds an available port. Just restart:
```bash
cd backend
python run.py
```

The server will automatically:
- Find an available port (8000, 8001, 8002, etc.)
- Update the frontend configuration
- Display the port being used

### 2. YouTube Bot Detection

**Error:**
```
ERROR: [youtube] Sign in to confirm you're not a bot
```

**Solution:**
✅ **FIXED!** The backend now uses browser cookies for authentication.

**What you need to do:**
1. Make sure you're logged into YouTube in Chrome (or your preferred browser)
2. Restart the backend: `cd backend && python run.py`
3. The backend will automatically extract your YouTube cookies

**See detailed help:** `YOUTUBE_COOKIE_SETUP.md`

**Change browser:**
```bash
# Create .env file if it doesn't exist
cd backend
echo "COOKIES_FROM_BROWSER=firefox" >> .env
```

Supported browsers: chrome, firefox, safari, edge, brave, opera

### 3. Frontend Can't Connect to Backend

**Error:**
```
Failed to fetch
Network error
```

**Solution:**
The backend auto-updates the frontend configuration, but if the frontend was already running:

1. Stop the frontend (Ctrl+C)
2. Start it again: `npm run dev`
3. It will now use the correct backend port

**Or use the startup script:**
```bash
./start.sh
```

This starts both servers with proper configuration.

### 4. Video Generation Returns 500 Error

**Possible causes:**

#### A. YouTube Authentication (Most Common)
- **Check:** Are you logged into YouTube in your browser?
- **Fix:** Log into YouTube in Chrome and restart the backend

#### B. Missing Video Clips
- **Check:** Is the database populated with clips?
- **Fix:** Run `python ingest_whisperx.py` in the backend directory

#### C. FFmpeg Not Installed
- **Check:** Run `ffmpeg -version`
- **Fix:**
  ```bash
  # macOS
  brew install ffmpeg
  
  # Linux
  sudo apt-get install ffmpeg
  
  # Windows
  # Download from ffmpeg.org
  ```

#### D. Disk Space
- **Check:** Do you have enough disk space for temp files?
- **Fix:** Free up disk space or change temp directory in the code

### 5. Frontend Port Conflicts

**Issue:** Frontend says "Port 5173 is in use"

**Solution:**
✅ Vite (the frontend dev server) automatically tries other ports. Look for the message:
```
➜  Local:   http://localhost:5175/
```

Just use whatever port it chose.

### 6. Database Not Found

**Error:**
```
⚠ Database not found. Initializing...
```

**Solution:**
This is normal on first run. The backend will initialize the database automatically.

If you want to populate it with data:
```bash
cd backend
python ingest.py              # Fetch YouTube transcripts
python ingest_whisperx.py     # Add word-level clips
```

### 7. Startup Script Doesn't Work

**Error:**
```
Permission denied: ./start.sh
```

**Solution:**
```bash
chmod +x start.sh
./start.sh
```

### 8. Browser Cookie Extraction Fails

**Error:**
```
Failed to extract cookies from browser
```

**Solutions:**

1. **Make sure the browser is installed** on the system running the backend
2. **Make sure you're logged into YouTube** in that browser
3. **Try a different browser:**
   ```bash
   export COOKIES_FROM_BROWSER=firefox
   python run.py
   ```
4. **Close the browser** before running (some browsers lock their cookie database)
5. **Check browser profile:** Make sure you're using the default profile

**Still not working?**
See `YOUTUBE_COOKIE_SETUP.md` for alternative cookie export methods.

## Getting Help

1. **Check the logs** - The backend prints detailed error messages
2. **Read the documentation:**
   - `README.md` - Main setup guide
   - `YOUTUBE_COOKIE_SETUP.md` - YouTube authentication
   - `backend/PHRASE_MATCHING_GUIDE.md` - Video generation details
3. **Common log messages:**
   - `Using cookies from browser: chrome` ✅ Good!
   - `No clip found for word: xyz` ⚠️ Database needs more data
   - `Failed to download segment` ⚠️ YouTube authentication issue

## Quick Diagnostic Checklist

When something goes wrong, check:

- [ ] Backend server is running
- [ ] Frontend is running
- [ ] You're logged into YouTube in Chrome (or configured browser)
- [ ] Database exists and has data
- [ ] FFmpeg is installed
- [ ] You have disk space for temp files
- [ ] Ports are available (auto-detected, but check logs)
- [ ] No firewall blocking localhost connections

## Still Having Issues?

1. **Restart everything:**
   ```bash
   # Stop all servers (Ctrl+C)
   ./start.sh  # Start fresh
   ```

2. **Check versions:**
   ```bash
   python --version  # Should be 3.8+
   node --version    # Should be 14+
   ffmpeg -version   # Should be installed
   ```

3. **Clear caches:**
   ```bash
   cd backend
   rm -rf __pycache__
   rm -rf temp/*
   
   cd ../frontend
   rm -rf node_modules/.vite
   ```

4. **Reinstall dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt --upgrade
   
   cd ../frontend
   npm ci
   ```

