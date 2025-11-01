import os
import httpx
from typing import List, Dict

API_KEY = os.getenv("YOUTUBE_API_KEY")
BASE = "https://www.googleapis.com/youtube/v3"

async def list_uploads_playlist_id(channel_id: str) -> str:
    url = f"{BASE}/channels"
    params = {"part":"contentDetails", "id": channel_id, "key": API_KEY}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items: return ""
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

async def list_videos_in_playlist(playlist_id: str, max_pages=3) -> List[Dict]:
    url = f"{BASE}/playlistItems"
    params = {"part":"snippet,contentDetails", "playlistId": playlist_id, "maxResults":50, "key": API_KEY}
    out = []
    async with httpx.AsyncClient(timeout=30) as client:
        page = 0
        while True:
            page += 1
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("items", []))
            nxt = data.get("nextPageToken")
            if not nxt or page >= max_pages: break
            params["pageToken"] = nxt
    return [{
        "video_id": it["contentDetails"]["videoId"],
        "title": it["snippet"]["title"],
        "channel_id": it["snippet"]["channelId"],
        "channel_title": it["snippet"]["channelTitle"],
        "published_at": it["contentDetails"].get("videoPublishedAt")
    } for it in out if it.get("contentDetails")]

