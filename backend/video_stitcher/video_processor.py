"""Video processing module for normalizing and preparing video segments."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

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
                text=True,
                timeout=30  # Add timeout to prevent hanging on corrupted files
            )
            logger.debug(f"Audio normalization completed: {output_path}")
        except subprocess.TimeoutExpired:
            error_msg = f"Audio normalization timed out (file may be corrupted): {input_path}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.CalledProcessError as e:
            # Check if error is due to corrupted input
            if "Invalid NAL unit" in e.stderr or "Invalid data" in e.stderr or "Error splitting" in e.stderr:
                error_msg = f"Audio normalization failed - input file appears corrupted: {input_path}"
                logger.error(error_msg)
                logger.debug(f"FFmpeg stderr: {e.stderr}")
                raise RuntimeError(error_msg) from e
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
    
    def add_subtitle_overlay(
        self, 
        input_path: str, 
        output_path: str, 
        text: str,
        font_size: int = 48,
        font_color: str = "white",
        bg_color: str = "black@0.6",
        position: str = "bottom"
    ) -> None:
        """Add subtitle text overlay to video.
        
        Args:
            input_path: Path to input video file.
            output_path: Path to output video file.
            text: Text to display as subtitle.
            font_size: Font size for subtitle text.
            font_color: Color for subtitle text.
            bg_color: Background color with opacity (format: color@opacity).
            position: Position of subtitle ('top', 'center', 'bottom').
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Adding subtitle overlay: {text}")
        
        # Escape special characters in text for ffmpeg
        text_escaped = text.replace("'", "'\\\\\\''").replace(":", "\\:")
        
        # Determine vertical position
        if position == "top":
            y_pos = "h*0.1"
        elif position == "center":
            y_pos = "(h-text_h)/2"
        else:  # bottom
            y_pos = "h-text_h-h*0.1"
        
        # Build drawtext filter
        drawtext_filter = (
            f"drawtext=text='{text_escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"x=(w-text_w)/2:"
            f"y={y_pos}:"
            f"box=1:"
            f"boxcolor={bg_color}:"
            f"boxborderw=10"
        )
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', drawtext_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'copy',  # Copy audio stream
            '-y',
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Subtitle overlay completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Subtitle overlay failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def resize_to_aspect_ratio(
        self,
        input_path: str,
        output_path: str,
        aspect_ratio: str = "16:9",
        pad_color: str = "black"
    ) -> None:
        """Resize and pad video to specific aspect ratio.
        
        Args:
            input_path: Path to input video file.
            output_path: Path to output video file.
            aspect_ratio: Target aspect ratio ('16:9', '9:16', '1:1').
            pad_color: Color for padding bars.
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Resizing to aspect ratio {aspect_ratio}: {input_path}")
        
        # Define target resolutions
        resolutions = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1080, 1080)
        }
        
        if aspect_ratio not in resolutions:
            raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")
        
        target_width, target_height = resolutions[aspect_ratio]
        
        # Scale and pad to maintain aspect ratio
        scale_filter = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
        )
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', scale_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'copy',
            '-y',
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Aspect ratio resize completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Aspect ratio resize failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def add_watermark(
        self,
        input_path: str,
        output_path: str,
        watermark_text: str,
        position: str = "bottom-right",
        opacity: float = 0.7
    ) -> None:
        """Add watermark text to video.
        
        Args:
            input_path: Path to input video file.
            output_path: Path to output video file.
            watermark_text: Text to display as watermark.
            position: Position of watermark ('top-left', 'top-right', 'bottom-left', 'bottom-right').
            opacity: Opacity of watermark (0.0 to 1.0).
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Adding watermark: {watermark_text}")
        
        # Escape special characters
        text_escaped = watermark_text.replace("'", "'\\\\\\''").replace(":", "\\:")
        
        # Determine position
        positions = {
            "top-left": ("10", "10"),
            "top-right": ("w-text_w-10", "10"),
            "bottom-left": ("10", "h-text_h-10"),
            "bottom-right": ("w-text_w-10", "h-text_h-10")
        }
        
        x_pos, y_pos = positions.get(position, positions["bottom-right"])
        
        # Calculate alpha for font color
        alpha_hex = format(int(opacity * 255), '02x')
        
        drawtext_filter = (
            f"drawtext=text='{text_escaped}':"
            f"fontsize=24:"
            f"fontcolor=white@{opacity}:"
            f"x={x_pos}:"
            f"y={y_pos}:"
            f"shadowcolor=black@0.5:"
            f"shadowx=2:"
            f"shadowy=2"
        )
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', drawtext_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'copy',
            '-y',
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Watermark completed: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Watermark failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def create_title_card(
        self,
        output_path: str,
        text: str,
        duration: float = 2.0,
        width: int = 1920,
        height: int = 1080,
        bg_color: str = "black",
        text_color: str = "white"
    ) -> None:
        """Create a title card video with text.
        
        Args:
            output_path: Path to output video file.
            text: Text to display on card.
            duration: Duration of card in seconds.
            width: Width of video.
            height: Height of video.
            bg_color: Background color.
            text_color: Text color.
            
        Raises:
            RuntimeError: If ffmpeg command fails.
        """
        logger.info(f"Creating title card: {text}")
        
        # Escape special characters
        text_escaped = text.replace("'", "'\\\\\\''").replace(":", "\\:")
        
        drawtext_filter = (
            f"drawtext=text='{text_escaped}':"
            f"fontsize=72:"
            f"fontcolor={text_color}:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2"
        )
        
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'color=c={bg_color}:s={width}x{height}:d={duration}:r=30',
            '-f', 'lavfi',
            '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
            '-vf', drawtext_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-shortest',
            '-y',
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            logger.debug(f"Title card created: {output_path}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Title card creation failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
