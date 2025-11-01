import os
import re
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from db import search_phrase
from video_stitcher import VideoStitcher, StitchingConfig

app = FastAPI(title="YouGlish-lite API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount output directory for serving generated videos
OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

class SearchResponseItem(BaseModel):
    id: int
    video_id: str
    lang: str
    t_start: float
    t_end: float
    text: str
    title: Optional[str] = None
    channel_title: Optional[str] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/search", response_model=list[SearchResponseItem])
def search(q: str, lang: Optional[str] = None, limit: int = 20):
    q = q.strip()
    if not q:
        raise HTTPException(400, detail="q is required")
    rows = search_phrase(q, lang, limit)
    return rows


class GenerateVideoRequest(BaseModel):
    text: str
    lang: Optional[str] = "en"
    max_phrase_length: Optional[int] = 10  # Default to 10, range 1-50


class GenerateVideoResponse(BaseModel):
    status: str
    video_url: Optional[str] = None
    message: Optional[str] = None
    missing_words: Optional[List[str]] = None


@app.post("/generate-video", response_model=GenerateVideoResponse)
def generate_video(request: GenerateVideoRequest):
    """
    Generate a video by stitching together clips of individual words.
    
    Args:
        request: GenerateVideoRequest with text and optional lang
        
    Returns:
        GenerateVideoResponse with video URL or error message
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(400, detail="text is required")
    
    # Parse text into words
    words = re.findall(r'\b\w+\b', text.lower())
    if not words:
        raise HTTPException(400, detail="No valid words found in text")
    
    try:
        # Validate max_phrase_length
        max_phrase_length = request.max_phrase_length or 10
        if not (1 <= max_phrase_length <= 50):
            raise HTTPException(400, detail="max_phrase_length must be between 1 and 50")
        
        # Use the existing video_stitcher with word_clips database
        # Note: we're using the youglish.db which should have word_clips table
        config = StitchingConfig(
            database_path="./data/youglish.db",
            output_directory="./output",
            temp_directory="./temp",
            video_quality="bestvideo[height<=720]+bestaudio/best[height<=720]",
            normalize_audio=True,
            incremental_stitching=True,
            cleanup_temp_files=True,
            max_phrase_length=max_phrase_length
        )
        
        # Generate unique filename
        timestamp = int(time.time())
        output_filename = f"generated_{timestamp}.mp4"
        
        # Generate the video
        with VideoStitcher(config) as stitcher:
            # The video stitcher will handle word lookup and stitching
            output_path = stitcher.generate_video(
                text=text,
                output_filename=output_filename
            )
        
        # Return the video URL
        video_url = f"/videos/{output_filename}"
        
        return GenerateVideoResponse(
            status="success",
            video_url=video_url,
            message=f"Video generated successfully with {len(words)} words"
        )
    
    except ValueError as e:
        # Handle case where no clips found
        error_msg = str(e)
        if "No clips found" in error_msg or "missing" in error_msg.lower():
            # Extract missing words if possible
            missing = [w for w in words]  # Simplified - could be improved
            return GenerateVideoResponse(
                status="partial_failure",
                message=error_msg,
                missing_words=missing
            )
        raise HTTPException(400, detail=error_msg)
    
    except Exception as e:
        raise HTTPException(500, detail=f"Video generation failed: {str(e)}")

