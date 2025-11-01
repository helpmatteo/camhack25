"""Video segment downloader module using yt-dlp."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import yt_dlp
except ImportError:
    raise ImportError("yt-dlp is required. Install it with: pip install yt-dlp")

from .database import ClipInfo

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Exception raised when video download fails."""
    pass


@dataclass
class VideoDownloaderConfig:
    """Configuration for video segment downloader."""
    output_directory: str = "./temp_clips"
    video_format: str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    max_retries: int = 3
    timeout: int = 30
    cookies_from_browser: str = None  # e.g., 'chrome', 'firefox', 'safari', 'edge'


class VideoSegmentDownloader:
    """Downloads specific segments from YouTube videos."""
    
    def __init__(self, config: VideoDownloaderConfig):
        """Initialize the video segment downloader.
        
        Args:
            config: Configuration for the downloader.
        """
        self.config = config
        self.output_dir = Path(config.output_directory)
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloader initialized with output directory: {self.output_dir}")
    
    def _make_download_range(self, start: float, end: float) -> Callable:
        """Create a download range function for yt-dlp.
        
        Args:
            start: Start time in seconds.
            end: End time in seconds.
            
        Returns:
            Callable that returns download range specification.
        """
        def download_range_func(info_dict, ydl):
            return [{
                'start_time': start,
                'end_time': end,
            }]
        return download_range_func
    
    def download_segment(self, clip_info: ClipInfo) -> str:
        """Download a specific video segment.
        
        Args:
            clip_info: Information about the clip to download.
            
        Returns:
            Path to the downloaded file.
            
        Raises:
            DownloadError: If download fails after retries.
        """
        # Calculate end time with small buffer
        buffer = 0.1
        start_time = max(0, clip_info.start_time - buffer)
        end_time = clip_info.start_time + clip_info.duration + buffer
        
        # Generate unique output filename (without extension - yt-dlp will add it)
        filename = f"{clip_info.video_id}_{clip_info.start_time:.2f}_{clip_info.duration:.2f}"
        output_template = str(self.output_dir / filename)
        
        # Check if segment already exists in cache (check for common extensions)
        for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
            cached_path = Path(output_template + ext)
            if cached_path.exists():
                logger.info(f"Using cached segment: {cached_path.name}")
                return str(cached_path)
        
        # Configure yt-dlp options with proper postprocessing for segments
        ydl_opts = {
            'format': self.config.video_format,
            'outtmpl': output_template + '.%(ext)s',
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
            'retries': self.config.max_retries,
            'socket_timeout': self.config.timeout,
            'download_ranges': self._make_download_range(start_time, end_time),
            'force_keyframes_at_cuts': True,
            'postprocessor_args': {
                'ffmpeg': ['-ss', str(start_time), '-t', str(end_time - start_time)]
            },
        }
        
        # Add cookie authentication if configured
        if self.config.cookies_from_browser:
            ydl_opts['cookiesfrombrowser'] = (self.config.cookies_from_browser,)
            logger.info(f"Using cookies from browser: {self.config.cookies_from_browser}")
        
        try:
            youtube_url = f"https://www.youtube.com/watch?v={clip_info.video_id}"
            logger.info(f"Downloading segment for word '{clip_info.word}' from {youtube_url}")
            logger.debug(f"Time range: {start_time:.2f}s to {end_time:.2f}s")
            
            # Track files before download
            files_before = set(self.output_dir.glob("*")) if self.output_dir.exists() else set()
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
            
            # Give a brief moment for file system to sync
            import time
            time.sleep(0.5)
            
            # Track files after download to find what was created
            files_after = set(self.output_dir.glob("*")) if self.output_dir.exists() else set()
            new_files = files_after - files_before
            
            # Find the downloaded file
            output_path = None
            
            # First, check if any new files were created
            if new_files:
                # Use the first new file (should only be one)
                output_path = list(new_files)[0]
                logger.debug(f"Found newly created file: {output_path}")
            else:
                # Fallback: look for files matching our pattern
                possible_extensions = ['.mp4', '.webm', '.mkv', '.m4a']
                for ext in possible_extensions:
                    potential_path = Path(output_template + ext)
                    if potential_path.exists():
                        output_path = potential_path
                        break
                
                # Also check for files with the video_id in the output directory
                if output_path is None:
                    for file in self.output_dir.glob(f"{clip_info.video_id}*"):
                        if file.stem.startswith(filename):
                            output_path = file
                            break
            
            if output_path is None or not output_path.exists():
                # List what files actually exist
                existing_files = list(self.output_dir.glob("*"))
                logger.error(f"Files in output directory: {existing_files}")
                logger.error(f"New files detected: {new_files}")
                raise DownloadError(
                    f"Download completed but file not found. Expected pattern: {filename}.*"
                )
            
            logger.info(f"Successfully downloaded: {output_path}")
            return str(output_path)
            
        except DownloadError:
            raise
        except Exception as e:
            error_msg = f"Failed to download segment for '{clip_info.word}': {str(e)}"
            logger.error(error_msg)
            raise DownloadError(error_msg) from e
    
    def cleanup_segment(self, file_path: str) -> None:
        """Delete a downloaded segment file.
        
        Args:
            file_path: Path to the file to delete.
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.debug(f"File does not exist, skipping cleanup: {file_path}")
            return
        
        try:
            path.unlink()
            logger.debug(f"Cleaned up file: {file_path}")
        except (PermissionError, FileNotFoundError) as e:
            logger.warning(f"Failed to cleanup file {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during cleanup of {file_path}: {str(e)}")
