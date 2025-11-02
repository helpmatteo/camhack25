import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from db import search_phrase, get_channels
from video_stitcher import VideoStitcher, StitchingConfig

# Load environment variables from .env file
load_dotenv()

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
    channel_id: Optional[str] = None


class ChannelInfo(BaseModel):
    channel_id: str
    channel_title: str
    video_count: int


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/channels", response_model=list[ChannelInfo])
def channels():
    """Get list of all available channels with video counts."""
    return get_channels()


@app.get("/search", response_model=list[SearchResponseItem])
def search(q: str, lang: Optional[str] = None, limit: int = 20, channel_id: Optional[str] = None):
    q = q.strip()
    if not q:
        raise HTTPException(400, detail="q is required")
    rows = search_phrase(q, lang, limit, channel_id)
    return rows


class GenerateVideoRequest(BaseModel):
    text: str
    lang: Optional[str] = "en"
    max_phrase_length: Optional[int] = 10  # Default to 10, range 1-50
    channel_id: Optional[str] = None  # Optional channel ID to filter clips
    
    # Clip extraction options
    clip_padding_start: Optional[float] = 0.15  # Padding before word start (seconds)
    clip_padding_end: Optional[float] = 0.15  # Padding after word end (seconds)
    
    # Visual enhancement options
    add_subtitles: Optional[bool] = False  # Add subtitle overlays
    aspect_ratio: Optional[str] = "16:9"  # Target aspect ratio ('16:9', '9:16', '1:1')
    watermark_text: Optional[str] = None  # Watermark text
    intro_text: Optional[str] = None  # Intro card text
    outro_text: Optional[str] = None  # Outro card text
    
    # Audio enhancement options
    enhance_audio: Optional[bool] = False  # Enable Auphonic audio enhancement
    keep_original_audio: Optional[bool] = True  # Keep original audio for comparison
    
    # Parallel processing options
    max_download_workers: Optional[int] = 3  # Max concurrent downloads (1-10)
    max_processing_workers: Optional[int] = 4  # Max concurrent processing tasks (1-10)
    download_timeout: Optional[int] = 300  # Download timeout in seconds
    processing_timeout: Optional[int] = 600  # Processing timeout in seconds
    max_failure_rate: Optional[float] = 0.5  # Maximum acceptable failure rate (0.0-1.0)


class GenerateVideoResponse(BaseModel):
    status: str
    video_url: Optional[str] = None
    original_video_url: Optional[str] = None  # URL for original audio version (if keep_original_audio enabled)
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
            incremental_stitching=False,  # Use fast batch concatenation
            cleanup_temp_files=True,
            max_phrase_length=max_phrase_length,
            # cleanup_temp_files=False,  # Keep cache for faster subsequent generations
            channel_id=request.channel_id,
            # Clip extraction options
            clip_padding_start=request.clip_padding_start or 0.15,
            clip_padding_end=request.clip_padding_end or 0.15,
            # Visual enhancement options
            add_subtitles=request.add_subtitles or False,
            aspect_ratio=request.aspect_ratio or "16:9",
            watermark_text=request.watermark_text,
            intro_text=request.intro_text,
            outro_text=request.outro_text,
            # Audio enhancement options
            enhance_audio=request.enhance_audio or False,
            keep_original_audio=request.keep_original_audio if request.keep_original_audio is not None else True,
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
        
        # Return the video URL(s)
        video_url = f"/videos/{output_filename}"
        original_video_url = None
        
        # Check if original video was saved (when audio enhancement + keep_original_audio)
        if request.enhance_audio and request.keep_original_audio:
            original_filename = f"generated_{timestamp}_original.mp4"
            original_video_path = Path("./output") / original_filename
            if original_video_path.exists():
                original_video_url = f"/videos/{original_filename}"
        
        return GenerateVideoResponse(
            status="success",
            video_url=video_url,
            original_video_url=original_video_url,
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

