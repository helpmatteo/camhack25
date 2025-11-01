"""Main video stitcher orchestrator module."""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    incremental_stitching: bool = False  # Changed default to False for better performance
    cleanup_temp_files: bool = True
    verify_ffmpeg_on_init: bool = True  # Set to False to skip ffmpeg verification
    max_phrase_length: int = 10  # Maximum number of consecutive words to match as a phrase (1-50)
    max_workers: int = 8  # Number of parallel workers (1=sequential, 2-8=parallel for performance)


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
        before falling back to individual word lookups. It also tries to avoid
        repeating videos unless necessary, creating more diverse output.
        
        Args:
            words: List of words to look up.
            
        Returns:
            Tuple of (found_clips, missing_words).
        """
        logger.info(f"Looking up clips for {len(words)} words")
        
        found_clips = []
        missing_words = []
        used_video_ids = []  # Track videos we've already used
        i = 0
        
        while i < len(words):
            # Try to find longest phrase starting at position i
            best_clip = None
            best_length = 0
            
            # Only try phrase matching if transcripts are available
            if self.database.has_transcripts:
                # Try phrases from longest to shortest (using configured max_phrase_length)
                max_phrase_len = min(self.config.max_phrase_length, len(words) - i)
                for phrase_len in range(max_phrase_len, 1, -1):  # Start from longest
                    phrase = ' '.join(words[i:i + phrase_len])
                    clip_info = self.database.find_phrase_in_transcripts(phrase, exclude_video_ids=used_video_ids)
                    
                    if clip_info is not None:
                        best_clip = clip_info
                        best_length = phrase_len
                        logger.info(f"Found {phrase_len}-word phrase: '{phrase}'")
                        break
            
            # If phrase matching succeeded, use it
            if best_clip is not None:
                found_clips.append(best_clip)
                used_video_ids.append(best_clip.video_id)
                i += best_length
            else:
                # Fall back to single word lookup
                word = words[i]
                clip_info = self.database.get_clip_info(word, exclude_video_ids=used_video_ids)
                
                if clip_info is None:
                    missing_words.append(word)
                    logger.warning(f"No clip found for word: {word}")
                else:
                    found_clips.append(clip_info)
                    used_video_ids.append(clip_info.video_id)
                
                i += 1
        
        # Log video diversity stats
        unique_videos = len(set(used_video_ids))
        if unique_videos < len(used_video_ids):
            logger.info(f"Video diversity: {unique_videos} unique videos used for {len(found_clips)} clips")
        else:
            logger.info(f"Video diversity: All clips from different videos ({unique_videos} unique)")
        
        logger.info(
            f"Found {len(found_clips)} clips, {len(missing_words)} words missing"
        )
        
        return found_clips, missing_words
    
    def download_all_segments(
        self, 
        clips: List[ClipInfo],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Download all required video segments in parallel.
        
        Args:
            clips: List of clip information to download.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of downloaded file paths in original order.
        """
        logger.info(f"Downloading {len(clips)} video segments (parallel)")
        
        downloaded_paths = [None] * len(clips)  # Preserve order
        completed = 0
        
        def download_clip(index, clip):
            """Download a single clip and return its index and path."""
            try:
                path = self.downloader.download_segment(clip, clip_index=index)
                return index, path, None
            except DownloadError as e:
                logger.error(f"Failed to download clip for '{clip.word}': {e}")
                return index, None, e
        
        # Use ThreadPoolExecutor for parallel downloads if max_workers > 1
        if self.config.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                # Submit all download tasks
                future_to_index = {
                    executor.submit(download_clip, i, clip): i 
                    for i, clip in enumerate(clips)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_index):
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(clips))
                    
                    index, path, error = future.result()
                    if path is not None:
                        downloaded_paths[index] = path
        else:
            # Sequential download (for debugging or single-threaded mode)
            for i, clip in enumerate(clips):
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(clips))
                
                index, path, error = download_clip(i, clip)
                if path is not None:
                    downloaded_paths[index] = path
        
        # Filter out failed downloads while preserving order
        successful_paths = [p for p in downloaded_paths if p is not None]
        
        if len(successful_paths) < len(clips):
            logger.warning(f"Only {len(successful_paths)}/{len(clips)} downloads succeeded")
            # Log which clips failed
            for i, path in enumerate(downloaded_paths):
                if path is None:
                    logger.warning(f"Failed to download clip {i}: {clips[i].word}")
        
        # Log the downloaded clips in order for debugging
        logger.debug(f"Downloaded clips in order:")
        for i, (clip, path) in enumerate(zip([c for c, p in zip(clips, downloaded_paths) if p is not None], successful_paths)):
            logger.debug(f"  {i}: '{clip.word}' from {clip.video_id} -> {Path(path).name}")
        
        logger.info(f"Successfully downloaded {len(successful_paths)}/{len(clips)} segments")
        return successful_paths
    
    def process_segments(
        self,
        segment_paths: List[str],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Process segments (normalize, re-encode) for concatenation in parallel.
        
        Args:
            segment_paths: List of video segment paths.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of processed file paths in original order.
        """
        logger.info(f"Processing {len(segment_paths)} video segments (parallel)")
        
        # Create processed subdirectory
        processed_dir = self.temp_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        processed_paths = [None] * len(segment_paths)  # Preserve order
        completed = 0
        
        def process_segment(index, segment_path):
            """Process a single segment and return its index and path."""
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
                
                logger.debug(f"Processed segment: {output_path}")
                return index, str(output_path), None
                
            except Exception as e:
                logger.error(f"Failed to process segment {segment_path}: {e}")
                return index, None, e
        
        # Use ThreadPoolExecutor for parallel processing if max_workers > 1
        if self.config.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                # Submit all processing tasks
                future_to_index = {
                    executor.submit(process_segment, i, path): i 
                    for i, path in enumerate(segment_paths)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_index):
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(segment_paths))
                    
                    index, path, error = future.result()
                    if path is not None:
                        processed_paths[index] = path
        else:
            # Sequential processing (for debugging or single-threaded mode)
            for i, path in enumerate(segment_paths):
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(segment_paths))
                
                index, processed_path, error = process_segment(i, path)
                if processed_path is not None:
                    processed_paths[index] = processed_path
        
        # Filter out failed processing while preserving order
        successful_paths = [p for p in processed_paths if p is not None]
        
        if len(successful_paths) < len(segment_paths):
            logger.warning(f"Only {len(successful_paths)}/{len(segment_paths)} segments processed successfully")
        
        # Log the order of processed files for debugging
        logger.debug(f"Processed files in order: {[Path(p).name for p in successful_paths]}")
        
        logger.info(
            f"Successfully processed {len(successful_paths)}/{len(segment_paths)} segments"
        )
        return successful_paths
    
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
        start_time = time.time()
        phase_times = {}
        
        logger.info(f"Starting video generation from text: '{text}'")
        
        try:
            # Create full output path
            output_path = self.output_dir / output_filename
            
            # Step 1: Parse text into words
            phase_start = time.time()
            logger.info("Step 1/5: Parsing text")
            words = self.parse_text(text)
            if not words:
                raise ValueError("No words found in input text")
            phase_times['parse'] = time.time() - phase_start
            logger.info(f"✓ Parsing completed in {phase_times['parse']:.2f}s")
            
            # Step 2: Lookup clips in database
            phase_start = time.time()
            logger.info("Step 2/5: Looking up clips in database")
            clips, missing_words = self.lookup_clips(words)
            phase_times['lookup'] = time.time() - phase_start
            logger.info(f"✓ Lookup completed in {phase_times['lookup']:.2f}s")
            
            if not clips:
                raise ValueError(
                    f"No clips found for any words. Missing: {', '.join(missing_words)}"
                )
            
            if missing_words:
                logger.warning(
                    f"Continuing without {len(missing_words)} words: {', '.join(missing_words)}"
                )
            
            # Step 3: Download segments
            phase_start = time.time()
            logger.info("Step 3/5: Downloading video segments")
            segments = self.download_all_segments(clips, progress_callback)
            phase_times['download'] = time.time() - phase_start
            logger.info(f"✓ Download completed in {phase_times['download']:.2f}s")
            
            if not segments:
                raise RuntimeError("Failed to download any video segments")
            
            # Step 4: Process segments
            phase_start = time.time()
            logger.info("Step 4/5: Processing video segments")
            processed = self.process_segments(segments, progress_callback)
            phase_times['process'] = time.time() - phase_start
            logger.info(f"✓ Processing completed in {phase_times['process']:.2f}s")
            
            if not processed:
                raise RuntimeError("Failed to process any video segments")
            
            # Step 5: Concatenate into final video (use batch mode for speed)
            phase_start = time.time()
            logger.info("Step 5/5: Concatenating videos")
            if self.config.incremental_stitching:
                # Slower incremental method (kept for compatibility)
                self.concatenator.concatenate_incremental(processed, str(output_path))
            else:
                # Fast batch concatenation (default)
                self.concatenator.concatenate_videos(processed, str(output_path))
            phase_times['concatenate'] = time.time() - phase_start
            logger.info(f"✓ Concatenation completed in {phase_times['concatenate']:.2f}s")
            
            # Calculate total time and display summary
            total_time = time.time() - start_time
            logger.info("=" * 60)
            logger.info("VIDEO GENERATION PERFORMANCE SUMMARY")
            logger.info("=" * 60)
            logger.info(f"  Parse text:       {phase_times.get('parse', 0):.2f}s ({phase_times.get('parse', 0)/total_time*100:.1f}%)")
            logger.info(f"  Lookup clips:     {phase_times.get('lookup', 0):.2f}s ({phase_times.get('lookup', 0)/total_time*100:.1f}%)")
            logger.info(f"  Download videos:  {phase_times.get('download', 0):.2f}s ({phase_times.get('download', 0)/total_time*100:.1f}%)")
            logger.info(f"  Process videos:   {phase_times.get('process', 0):.2f}s ({phase_times.get('process', 0)/total_time*100:.1f}%)")
            logger.info(f"  Concatenate:      {phase_times.get('concatenate', 0):.2f}s ({phase_times.get('concatenate', 0)/total_time*100:.1f}%)")
            logger.info("-" * 60)
            logger.info(f"  TOTAL TIME:       {total_time:.2f}s")
            logger.info("=" * 60)
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
