"""Video processing module for normalizing and preparing video segments."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles video processing operations using ffmpeg."""
    
    def __init__(self, verify_on_init: bool = True):
        """Initialize the video processor.
        
        Args:
            verify_on_init: If True, verify ffmpeg is available on initialization.
                           Set to False to skip verification (useful for testing).
        
        Raises:
            RuntimeError: If ffmpeg is not installed and verify_on_init is True.
        """
        if verify_on_init:
            self._verify_ffmpeg()
        logger.info("VideoProcessor initialized")
    
    def _verify_ffmpeg(self) -> None:
        """Verify that ffmpeg is installed and available.
        
        Raises:
            RuntimeError: If ffmpeg is not found or verification times out.
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True,
                timeout=10  # Increased timeout from 5 to 10 seconds
            )
            logger.debug("ffmpeg is available")
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg verification timed out - may be slow or hung")
            raise RuntimeError(
                "ffmpeg verification timed out. "
                "ffmpeg may be installed but not responding correctly. "
                "Try running 'ffmpeg -version' manually to diagnose the issue."
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                "ffmpeg is not installed or not in PATH. "
                "Please install ffmpeg: https://ffmpeg.org/download.html"
            ) from e
    
    def normalize_audio(self, input_path: str, output_path: str) -> None:
        """Normalize audio levels using ffmpeg loudnorm filter.
        
        Args:
            input_path: Path to input video file.
            output_path: Path to output video file.
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Normalizing audio: {input_path} -> {output_path}")
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
            '-c:v', 'libx264',       # Re-encode video for consistency
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-r', '30',              # Set frame rate
            '-g', '30',              # Keyframe interval
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',              # Stereo audio
            '-y',  # Overwrite without prompting
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Audio normalization completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Audio normalization failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def reencode_for_concat(self, input_path: str, output_path: str) -> None:
        """Re-encode video to ensure consistent format for concatenation.
        
        Args:
            input_path: Path to input video file.
            output_path: Path to output video file.
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Re-encoding video: {input_path} -> {output_path}")
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',  # Ensure consistent pixel format
            '-r', '30',              # Set frame rate to 30fps for consistency
            '-g', '30',              # Keyframe interval (1 per second at 30fps)
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',              # Stereo audio
            '-movflags', '+faststart',  # Enable streaming
            '-y',  # Overwrite without prompting
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Re-encoding completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Re-encoding failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def trim_exact(
        self, 
        input_path: str, 
        start: float, 
        duration: float, 
        output_path: str
    ) -> None:
        """Trim video to exact timestamp with precision.
        
        Args:
            input_path: Path to input video file.
            start: Start time in seconds.
            duration: Duration in seconds.
            output_path: Path to output video file.
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(
            f"Trimming video: {input_path} (start={start}s, duration={duration}s) -> {output_path}"
        )
        
        cmd = [
            'ffmpeg',
            '-ss', str(start),
            '-i', input_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-y',  # Overwrite without prompting
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Trimming completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Trimming failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def verify_video_properties(self, file_path: str) -> Dict:
        """Get video properties using ffprobe.
        
        Args:
            file_path: Path to video file.
            
        Returns:
            Dictionary with video properties (codec, width, height, duration, bitrate).
            
        Raises:
            RuntimeError: If ffprobe command fails.
        """
        logger.debug(f"Verifying video properties: {file_path}")
        
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            file_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            
            data = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = None
            audio_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and video_stream is None:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and audio_stream is None:
                    audio_stream = stream
            
            properties = {
                'format': data.get('format', {}).get('format_name', 'unknown'),
                'duration': float(data.get('format', {}).get('duration', 0)),
                'bitrate': int(data.get('format', {}).get('bit_rate', 0)),
            }
            
            if video_stream:
                properties.update({
                    'video_codec': video_stream.get('codec_name', 'unknown'),
                    'width': video_stream.get('width', 0),
                    'height': video_stream.get('height', 0),
                    'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                })
            
            if audio_stream:
                properties.update({
                    'audio_codec': audio_stream.get('codec_name', 'unknown'),
                    'sample_rate': int(audio_stream.get('sample_rate', 0)),
                })
            
            logger.debug(f"Video properties: {properties}")
            return properties
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to get video properties: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except (json.JSONDecodeError, KeyError) as e:
            error_msg = f"Failed to parse video properties: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
