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
    clip_padding_start: float = 0.15  # Padding before word start (seconds)
    clip_padding_end: float = 0.15  # Padding after word end (seconds)


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
        # Apply configurable padding to ensure clean word boundaries
        # Padding helps account for speech recognition inaccuracies and natural speech flow
        start_time = max(0, clip_info.start_time - self.config.clip_padding_start)
        end_time = clip_info.start_time + clip_info.duration + self.config.clip_padding_end
        
        logger.debug(
            f"Downloading with padding: original={clip_info.start_time:.2f}s-{clip_info.start_time + clip_info.duration:.2f}s, "
            f"padded={start_time:.2f}s-{end_time:.2f}s"
        )
        
        # Generate unique output filename (without extension - yt-dlp will add it)
        filename = f"{clip_info.video_id}_{clip_info.start_time:.2f}_{clip_info.duration:.2f}"
        output_template = str(self.output_dir / filename)
        
        # Check if segment already exists in cache (check for common extensions)
        for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
            cached_path = Path(output_template + ext)
            if cached_path.exists():
                logger.info(f"Using cached segment: {cached_path.name}")
                return str(cached_path)
        
        # Configure yt-dlp options
        # Note: We use download_ranges ONLY, without postprocessor_args to avoid
        # double-processing which can corrupt the video stream
        ydl_opts = {
            'format': self.config.video_format,
            'outtmpl': output_template + '.%(ext)s',
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
            'retries': self.config.max_retries,
            'socket_timeout': self.config.timeout,
            'download_ranges': self._make_download_range(start_time, end_time),
            'force_keyframes_at_cuts': True,  # Ensure clean cuts at keyframes
            'ignoreerrors': False,  # Don't ignore errors, we want to catch them
            'no_check_certificate': False,  # Keep SSL verification
            'extract_flat': False,  # We need full extraction for segments
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
            
            # Validate that the downloaded segment is not corrupted
            if not self._validate_segment(str(output_path)):
                logger.warning(f"Downloaded segment appears corrupted, attempting to re-download: {output_path}")
                # Delete corrupted file
                output_path.unlink(missing_ok=True)
                raise DownloadError(f"Downloaded segment is corrupted: {output_path}")
            
            logger.info(f"Successfully downloaded: {output_path}")
            return str(output_path)
            
        except DownloadError:
            raise
        except yt_dlp.utils.DownloadError as e:
            # Extract more specific error information from yt-dlp
            error_msg = str(e)
            # Check for common error patterns
            if "Private video" in error_msg or "Video unavailable" in error_msg:
                error_msg = f"Video unavailable or private: {clip_info.video_id}"
            elif "HTTP Error" in error_msg or "403" in error_msg:
                error_msg = f"HTTP error (may be rate limited): {error_msg[:200]}"
            elif "Unable to download" in error_msg:
                error_msg = f"Unable to download video: {error_msg[:200]}"
            
            logger.error(f"yt-dlp error for '{clip_info.word}' (video {clip_info.video_id}): {error_msg}")
            raise DownloadError(f"Failed to download segment for '{clip_info.word}': {error_msg}") from e
        except Exception as e:
            error_msg = f"Failed to download segment for '{clip_info.word}': {str(e)}"
            logger.error(f"Unexpected error for '{clip_info.word}' (video {clip_info.video_id}): {error_msg}")
            raise DownloadError(error_msg) from e
    
    def _validate_segment(self, file_path: str) -> bool:
        """Validate that a video segment is not corrupted.
        
        Args:
            file_path: Path to the video file to validate.
            
        Returns:
            True if the segment appears valid, False if corrupted.
        """
        import subprocess
        
        try:
            # Check file size - if too small, likely corrupted
            file_size = Path(file_path).stat().st_size
            if file_size < 1000:  # Less than 1KB is suspicious
                logger.warning(f"Segment file too small ({file_size} bytes): {file_path}")
                return False
            
            # Use ffprobe to check if video is readable
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-count_frames',
                '-show_entries', 'stream=nb_read_frames',
                '-of', 'default=nokey=1:noprint_wrappers=1',
                file_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning(f"ffprobe validation failed for {file_path}: {result.stderr}")
                return False
            
            # Check if we got at least 1 frame
            try:
                frame_count = int(result.stdout.strip())
                if frame_count < 1:
                    logger.warning(f"No frames found in segment: {file_path}")
                    return False
            except (ValueError, AttributeError):
                logger.warning(f"Could not parse frame count for {file_path}")
                return False
            
            logger.debug(f"Segment validated successfully: {frame_count} frames in {file_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Validation timeout for {file_path}")
            return False
        except Exception as e:
            logger.warning(f"Validation error for {file_path}: {e}")
            return False
    
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
