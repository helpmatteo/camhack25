# YouTube Cookie Authentication Setup

## The Problem

YouTube has implemented bot detection that blocks automated video downloads. You'll see errors like:

```
ERROR: [youtube] Sign in to confirm you're not a bot.
```

## The Solution

Use browser cookies to authenticate downloads. The app can extract cookies from your browser where you're already logged into YouTube.

## Setup Instructions

### 1. Sign into YouTube in Your Browser

1. Open Chrome (or your preferred browser)
2. Go to [youtube.com](https://youtube.com)
3. Sign into your YouTube/Google account
4. ✅ That's it! Keep the browser installed on your system

### 2. Configure the Backend

The backend is already configured to use Chrome by default. If you want to use a different browser:

1. Create a `.env` file in the `backend` directory:
   ```bash
   cd backend
   cp .env.example .env
   ```

2. Edit `.env` and set your browser:
   ```bash
   COOKIES_FROM_BROWSER=chrome  # or firefox, safari, edge, brave, etc.
   ```

### 3. Supported Browsers

- `chrome` - Google Chrome (default)
- `firefox` - Mozilla Firefox
- `safari` - Safari (macOS only)
- `edge` - Microsoft Edge
- `chromium` - Chromium
- `opera` - Opera
- `brave` - Brave Browser

### 4. Restart the Backend

After configuration, restart your backend server:

```bash
cd backend
python run.py
```

## How It Works

The app uses `yt-dlp`'s `--cookies-from-browser` feature to:
1. Read your browser's cookie database
2. Extract YouTube authentication cookies
3. Use them to download videos as if you were browsing normally

## Security Notes

- ✅ Cookies are read locally from your browser
- ✅ No cookies are sent to any external servers (except YouTube)
- ✅ Your account credentials remain secure
- ⚠️ The browser must be installed on the system running the backend

## Troubleshooting

### "Failed to extract cookies"
- Make sure the browser is installed
- Make sure you're logged into YouTube in that browser
- Try a different browser

### Still getting bot detection errors
- Clear your browser cache and cookies
- Sign out and sign back into YouTube
- Try using a different Google account
- Use a different browser

### "Browser not found"
- Check the browser name in your `.env` file
- Make sure the browser is installed on your system
- Try using the full browser path (advanced)

## Testing

To test if cookie extraction is working:

1. Try generating a video from the frontend
2. Check the backend logs for: `Using cookies from browser: chrome`
3. If successful, you should see video downloads proceeding normally

## Alternative: Cookie File

If browser cookie extraction doesn't work, you can manually export cookies:

1. Install a browser extension like "Get cookies.txt LOCALLY"
2. Export cookies for youtube.com
3. Save to `backend/youtube_cookies.txt`
4. Update the downloader code to use `cookiefile` instead of `cookiesfrombrowser`

## Need Help?

Check the yt-dlp documentation:
- [Cookie extraction guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
- [Browser cookie support](https://github.com/yt-dlp/yt-dlp#cookies)

