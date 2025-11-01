"""Main video stitcher orchestrator module."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable, Tuple

from .database import WordClipDatabase, ClipInfo
from .downloader import VideoSegmentDownloader, VideoDownloaderConfig, DownloadError
from .video_processor import VideoProcessor
from .concatenator import VideoConcatenator

logger = logging.getLogger(__name__)


@dataclass
class StitchingConfig:
    """Configuration for the video stitcher."""
    database_path: str
    output_directory: str = "./output"
    temp_directory: str = "./temp"
    video_quality: str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    normalize_audio: bool = True
    incremental_stitching: bool = True
    cleanup_temp_files: bool = True
    verify_ffmpeg_on_init: bool = True  # Set to False to skip ffmpeg verification


class VideoStitcher:
    """Main class that orchestrates video stitching from text."""
    
    def __init__(self, config: StitchingConfig):
        """Initialize the video stitcher.
        
        Args:
            config: Configuration for the stitcher.
        """
        self.config = config
        
        # Create output directory
        self.output_dir = Path(config.output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create temp directory
        self.temp_dir = Path(config.temp_directory)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self.database = WordClipDatabase(config.database_path)
        
        # Initialize downloader
        downloader_config = VideoDownloaderConfig(
            output_directory=str(self.temp_dir / "downloads"),
            video_format=config.video_quality
        )
        self.downloader = VideoSegmentDownloader(downloader_config)
        
        # Initialize video processor
        self.processor = VideoProcessor(verify_on_init=config.verify_ffmpeg_on_init)
        
        # Initialize concatenator
        self.concatenator = VideoConcatenator(
            temp_dir=str(self.temp_dir / "concat")
        )
        
        logger.info("VideoStitcher initialized")
    
    def parse_text(self, text: str) -> List[str]:
        """Parse input text into individual words.
        
        Args:
            text: Input text to parse.
            
        Returns:
            List of words in lowercase, preserving order.
        """
        # Extract words using regex, convert to lowercase
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Remove empty strings
        words = [w for w in words if w]
        
        logger.debug(f"Parsed {len(words)} words from text: {words}")
        return words
    
    def lookup_clips(self, words: List[str]) -> Tuple[List[ClipInfo], List[str]]:
        """Look up clips for words in database, with phrase matching optimization.
        
        This method attempts to find longer consecutive phrases from the same video
        before falling back to individual word lookups. This creates smoother videos
        with fewer cuts when multiple consecutive words come from the same source.
        
        Args:
            words: List of words to look up.
            
        Returns:
            Tuple of (found_clips, missing_words).
        """
        logger.info(f"Looking up clips for {len(words)} words")
        
        found_clips = []
        missing_words = []
        i = 0
        
        while i < len(words):
            # Try to find longest phrase starting at position i
            best_clip = None
            best_length = 0
            
            # Only try phrase matching if transcripts are available
            if self.database.has_transcripts:
                # Try phrases from longest to shortest (max 10 words)
                max_phrase_len = min(10, len(words) - i)
                for phrase_len in range(max_phrase_len, 1, -1):  # Start from longest
                    phrase = ' '.join(words[i:i + phrase_len])
                    clip_info = self.database.find_phrase_in_transcripts(phrase)
                    
                    if clip_info is not None:
                        best_clip = clip_info
                        best_length = phrase_len
                        logger.info(f"Found {phrase_len}-word phrase: '{phrase}'")
                        break
            
            # If phrase matching succeeded, use it
            if best_clip is not None:
                found_clips.append(best_clip)
                i += best_length
            else:
                # Fall back to single word lookup
                word = words[i]
                clip_info = self.database.get_clip_info(word)
                
                if clip_info is None:
                    missing_words.append(word)
                    logger.warning(f"No clip found for word: {word}")
                else:
                    found_clips.append(clip_info)
                
                i += 1
        
        logger.info(
            f"Found {len(found_clips)} clips, {len(missing_words)} words missing"
        )
        
        return found_clips, missing_words
    
    def download_all_segments(
        self, 
        clips: List[ClipInfo],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Download all required video segments.
        
        Args:
            clips: List of clip information to download.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of downloaded file paths.
        """
        logger.info(f"Downloading {len(clips)} video segments")
        
        downloaded_paths = []
        
        for i, clip in enumerate(clips, start=1):
            try:
                if progress_callback:
                    progress_callback(i, len(clips))
                
                path = self.downloader.download_segment(clip)
                downloaded_paths.append(path)
                
            except DownloadError as e:
                logger.error(f"Failed to download clip for '{clip.word}': {e}")
                # Continue with other downloads
        
        logger.info(f"Successfully downloaded {len(downloaded_paths)}/{len(clips)} segments")
        return downloaded_paths
    
    def process_segments(
        self,
        segment_paths: List[str],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Process segments (normalize, re-encode) for concatenation.
        
        Args:
            segment_paths: List of video segment paths.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of processed file paths.
        """
        logger.info(f"Processing {len(segment_paths)} video segments")
        
        # Create processed subdirectory
        processed_dir = self.temp_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        processed_paths = []
        
        for i, segment_path in enumerate(segment_paths, start=1):
            if progress_callback:
                progress_callback(i, len(segment_paths))
            
            # Generate output path
            original_name = Path(segment_path).stem
            output_path = processed_dir / f"{original_name}_processed.mp4"
            
            try:
                if self.config.normalize_audio:
                    # Normalize audio first
                    temp_normalized = processed_dir / f"{original_name}_normalized.mp4"
                    self.processor.normalize_audio(segment_path, str(temp_normalized))
                    
                    # Then re-encode for consistency
                    self.processor.reencode_for_concat(
                        str(temp_normalized), 
                        str(output_path)
                    )
                    
                    # Clean up temp normalized file
                    if temp_normalized.exists():
                        temp_normalized.unlink()
                else:
                    # Just re-encode for consistency
                    self.processor.reencode_for_concat(segment_path, str(output_path))
                
                processed_paths.append(str(output_path))
                logger.debug(f"Processed segment: {output_path}")
                
            except Exception as e:
                logger.error(f"Failed to process segment {segment_path}: {e}")
                # Skip this segment
        
        logger.info(
            f"Successfully processed {len(processed_paths)}/{len(segment_paths)} segments"
        )
        return processed_paths
    
    def generate_video(
        self,
        text: str,
        output_filename: str,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Generate video from text.
        
        Main public API that orchestrates the entire pipeline.
        
        Args:
            text: Input text to convert to video.
            output_filename: Name of the output file.
            progress_callback: Optional callback for progress updates.
            
        Returns:
            Absolute path to the generated video file.
            
        Raises:
            ValueError: If no clips found for any words.
            RuntimeError: If video generation fails.
        """
        logger.info(f"Starting video generation from text: '{text}'")
        
        try:
            # Create full output path
            output_path = self.output_dir / output_filename
            
            # Step 1: Parse text into words
            logger.info("Step 1/5: Parsing text")
            words = self.parse_text(text)
            if not words:
                raise ValueError("No words found in input text")
            
            # Step 2: Lookup clips in database
            logger.info("Step 2/5: Looking up clips in database")
            clips, missing_words = self.lookup_clips(words)
            
            if not clips:
                raise ValueError(
                    f"No clips found for any words. Missing: {', '.join(missing_words)}"
                )
            
            if missing_words:
                logger.warning(
                    f"Continuing without {len(missing_words)} words: {', '.join(missing_words)}"
                )
            
            # Step 3: Download segments
            logger.info("Step 3/5: Downloading video segments")
            segments = self.download_all_segments(clips, progress_callback)
            
            if not segments:
                raise RuntimeError("Failed to download any video segments")
            
            # Step 4: Process segments
            logger.info("Step 4/5: Processing video segments")
            processed = self.process_segments(segments, progress_callback)
            
            if not processed:
                raise RuntimeError("Failed to process any video segments")
            
            # Step 5: Concatenate into final video
            logger.info("Step 5/5: Concatenating videos")
            if self.config.incremental_stitching:
                self.concatenator.concatenate_incremental(processed, str(output_path))
            else:
                self.concatenator.concatenate_videos(processed, str(output_path))
            
            logger.info(f"Video generation completed: {output_path}")
            
            return str(output_path.resolve())
            
        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            raise
        finally:
            # Cleanup temporary files if configured
            if self.config.cleanup_temp_files:
                logger.info("Cleaning up temporary files")
                try:
                    self.concatenator.cleanup()
                    
                    # Clean up downloaded and processed files
                    import shutil
                    downloads_dir = self.temp_dir / "downloads"
                    if downloads_dir.exists():
                        shutil.rmtree(downloads_dir, ignore_errors=True)
                    
                    processed_dir = self.temp_dir / "processed"
                    if processed_dir.exists():
                        shutil.rmtree(processed_dir, ignore_errors=True)
                    
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
    
    def close(self) -> None:
        """Close the video stitcher and release resources."""
        if hasattr(self, 'database'):
            self.database.close()
        logger.info("VideoStitcher closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
