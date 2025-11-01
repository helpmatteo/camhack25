"""Video concatenation module for stitching video segments together."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class VideoConcatenator:
    """Concatenates multiple video segments into a single output file."""
    
    def __init__(self, temp_dir: str = "./temp_concat"):
        """Initialize the video concatenator.
        
        Args:
            temp_dir: Directory for temporary files.
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Track temporary files for cleanup
        self.temp_files = []
        
        logger.info(f"VideoConcatenator initialized with temp dir: {self.temp_dir}")
    
    def create_concat_file(self, video_paths: List[str]) -> str:
        """Create a concat file for ffmpeg concat demuxer.
        
        Args:
            video_paths: List of video file paths to concatenate.
            
        Returns:
            Path to the concat file.
        """
        concat_file_path = self.temp_dir / "concat_list.txt"
        
        with open(concat_file_path, 'w') as f:
            for video_path in video_paths:
                # Use absolute paths and escape single quotes
                abs_path = Path(video_path).resolve()
                # Escape single quotes in the path by replacing ' with '\''
                escaped_path = str(abs_path).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        self.temp_files.append(str(concat_file_path))
        logger.debug(f"Created concat file: {concat_file_path}")
        
        return str(concat_file_path)
    
    def _validate_video_streams(self, video_path: str) -> bool:
        """Validate that a video file has valid streams.
        
        Args:
            video_path: Path to the video file to validate.
            
        Returns:
            True if video has valid streams, False otherwise.
        """
        try:
            # Check file size - if too small, likely corrupted
            file_size = Path(video_path).stat().st_size
            if file_size < 1000:  # Less than 1KB is suspicious
                logger.warning(f"Video file too small ({file_size} bytes): {video_path}")
                return False
            
            # Use ffprobe to check if video has valid streams
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_type',
                '-of', 'default=nokey=1:noprint_wrappers=1',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.warning(f"ffprobe validation failed for {video_path}: {result.stderr}")
                return False
            
            # Check if we got a video stream indicator
            if 'video' not in result.stdout.lower():
                logger.warning(f"No video stream found in {video_path}")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error validating video {video_path}: {e}")
            return False
    
    def concatenate_videos(
        self, 
        video_paths: List[str], 
        output_path: str
    ) -> None:
        """Concatenate videos using ffmpeg concat demuxer.
        
        Args:
            video_paths: List of video file paths to concatenate.
            output_path: Path to the output file.
            
        Raises:
            ValueError: If any input file doesn't exist or is invalid.
            RuntimeError: If concatenation fails.
        """
        if not video_paths:
            raise ValueError("No video paths provided for concatenation")
        
        # Verify all input files exist and have valid streams
        for path in video_paths:
            if not Path(path).exists():
                raise ValueError(f"Input file does not exist: {path}")
            
            # Validate that the video has valid streams
            if not self._validate_video_streams(path):
                raise ValueError(
                    f"Input file does not have valid video streams: {path}. "
                    f"The file may be corrupted or empty."
                )
        
        logger.info(f"Concatenating {len(video_paths)} videos to {output_path}")
        
        # Create concat file
        concat_file = self.create_concat_file(video_paths)
        
        # Run ffmpeg concat command with re-encoding for compatibility
        # This ensures all videos are properly stitched even with different codecs
        # Videos are validated before this point to ensure they have valid streams
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-map', '0',             # Map all streams from input
            '-c:v', 'libx264',       # Re-encode video to h264
            '-preset', 'medium',     # Balanced encoding speed/quality
            '-crf', '23',            # Good quality
            '-pix_fmt', 'yuv420p',   # Ensure compatible pixel format
            '-c:a', 'aac',           # Re-encode audio to aac (or copy if not present)
            '-b:a', '128k',          # Audio bitrate
            '-ar', '44100',          # Audio sample rate
            '-movflags', '+faststart',  # Enable streaming
            '-threads', '0',         # Use all CPU cores
            '-y',  # Overwrite without prompting
            output_path
        ]
        
        try:
            logger.debug(f"Running ffmpeg concat command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            
            # Verify output was created and has size > 0
            output_file = Path(output_path)
            if not output_file.exists():
                raise RuntimeError("Output file was not created")
            
            if output_file.stat().st_size == 0:
                raise RuntimeError("Output file is empty")
            
            logger.info(f"Successfully concatenated {len(video_paths)} videos to {output_path}")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Concatenation failed: {e.stderr}"
            logger.error(error_msg)
            logger.error(f"Concat file contents: {Path(concat_file).read_text() if Path(concat_file).exists() else 'N/A'}")
            raise RuntimeError(error_msg) from e
        finally:
            # Cleanup concat file
            if Path(concat_file).exists():
                Path(concat_file).unlink()
                if concat_file in self.temp_files:
                    self.temp_files.remove(concat_file)
    
    def concatenate_incremental(
        self, 
        video_paths: List[str], 
        output_path: str
    ) -> None:
        """Concatenate videos incrementally to minimize memory/storage.
        
        Uses incremental approach: A + B = C, C + D = E, etc.
        
        Args:
            video_paths: List of video file paths to concatenate.
            output_path: Path to the output file.
            
        Raises:
            ValueError: If less than 2 videos provided.
            RuntimeError: If concatenation fails.
        """
        if len(video_paths) < 2:
            if len(video_paths) == 1:
                # Just copy the single file
                shutil.copy2(video_paths[0], output_path)
                logger.info(f"Single video copied to {output_path}")
                return
            else:
                raise ValueError("At least one video is required")
        
        logger.info(
            f"Incrementally concatenating {len(video_paths)} videos to {output_path}"
        )
        
        # Validate first video before copying
        if not self._validate_video_streams(video_paths[0]):
            raise ValueError(
                f"First video file does not have valid streams: {video_paths[0]}. "
                f"The file may be corrupted or empty."
            )
        
        # Start with a copy of the first video
        current_video = self.temp_dir / "incremental_0.mp4"
        shutil.copy2(video_paths[0], current_video)
        self.temp_files.append(str(current_video))
        
        # Validate the copied file has valid streams
        if not self._validate_video_streams(str(current_video)):
            raise ValueError(
                f"Copied video file does not have valid streams: {current_video}. "
                f"The source file may be corrupted."
            )
        
        # Iteratively concatenate each subsequent video
        for i, next_video in enumerate(video_paths[1:], start=1):
            logger.info(f"Processing video {i + 1}/{len(video_paths)}: {next_video}")
            
            # Validate next video before concatenation
            if not self._validate_video_streams(next_video):
                raise ValueError(
                    f"Video file does not have valid streams: {next_video}. "
                    f"The file may be corrupted or empty."
                )
            
            # Validate current video still has valid streams
            if not self._validate_video_streams(str(current_video)):
                raise ValueError(
                    f"Current video file lost valid streams: {current_video}. "
                    f"This may indicate a problem with a previous concatenation step."
                )
            
            temp_output = self.temp_dir / f"incremental_{i}.mp4"
            self.temp_files.append(str(temp_output))
            
            # Concatenate current + next → temp_output
            try:
                self.concatenate_videos(
                    [str(current_video), next_video],
                    str(temp_output)
                )
                
                # Validate the output has valid streams before continuing
                if not self._validate_video_streams(str(temp_output)):
                    raise RuntimeError(
                        f"Concatenated output does not have valid streams: {temp_output}. "
                        f"Concatenation may have failed silently."
                    )
            except Exception as e:
                logger.error(
                    f"Failed to concatenate {current_video} + {next_video} -> {temp_output}: {e}"
                )
                raise
            
            # Delete the previous current video
            if current_video.exists():
                current_video.unlink()
                self.temp_files.remove(str(current_video))
            
            # Update current video to the new output
            current_video = temp_output
        
        # Rename final result to output path
        shutil.move(str(current_video), output_path)
        if str(current_video) in self.temp_files:
            self.temp_files.remove(str(current_video))
        
        logger.info(f"Incremental concatenation completed: {output_path}")
    
    def cleanup(self) -> None:
        """Remove all temporary files and directories."""
        logger.info("Cleaning up temporary files")
        
        # Remove tracked temporary files
        for temp_file in self.temp_files[:]:  # Copy list to avoid modification during iteration
            try:
                path = Path(temp_file)
                if path.exists():
                    path.unlink()
                    logger.debug(f"Deleted temp file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {str(e)}")
            finally:
                self.temp_files.remove(temp_file)
        
        # Remove temp directory
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.debug(f"Removed temp directory: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to remove temp directory {self.temp_dir}: {str(e)}")
