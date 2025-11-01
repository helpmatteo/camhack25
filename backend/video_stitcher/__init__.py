"""Video Stitcher - A system for stitching together YouTube clips to form videos from text."""

from .database import WordClipDatabase, ClipInfo
from .video_stitcher import VideoStitcher, StitchingConfig

__version__ = "0.1.0"
__all__ = ["WordClipDatabase", "ClipInfo", "VideoStitcher", "StitchingConfig"]
