"""Main video stitcher orchestrator module."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
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
    max_phrase_length: int = 10  # Maximum number of consecutive words to match as a phrase (1-50)
    cookies_from_browser: str = None  # Browser to extract cookies from (e.g., 'chrome', 'firefox', 'safari')
    channel_id: Optional[str] = None  # Optional channel ID to filter clips to
    
    # Clip extraction options
    clip_padding_start: float = 0.15  # Padding before word start (seconds) for cleaner cuts
    clip_padding_end: float = 0.15  # Padding after word end (seconds) for cleaner cuts
    
    # Visual enhancement options
    add_subtitles: bool = False  # Add subtitle overlays to clips
    aspect_ratio: str = "16:9"  # Target aspect ratio ('16:9', '9:16', '1:1')
    watermark_text: Optional[str] = None  # Watermark text to add
    intro_text: Optional[str] = None  # Intro card text
    outro_text: Optional[str] = None  # Outro card text
    
    # Parallel processing limits
    max_download_workers: int = 3  # Max concurrent downloads (1-10, recommend 2-4 to avoid rate limits)
    max_processing_workers: int = 4  # Max concurrent video processing tasks (1-10)
    download_timeout: int = 300  # Overall timeout for all downloads in seconds (5 minutes)
    processing_timeout: int = 600  # Overall timeout for all processing in seconds (10 minutes)
    max_failure_rate: float = 0.5  # Maximum acceptable failure rate (0.0-1.0, e.g., 0.5 = 50%)


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
            video_format=config.video_quality,
            cookies_from_browser=config.cookies_from_browser,
            clip_padding_start=config.clip_padding_start,
            clip_padding_end=config.clip_padding_end
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
        For words without clips, placeholder ClipInfo objects are inserted.
        
        Args:
            words: List of words to look up.
            
        Returns:
            Tuple of (found_clips_with_placeholders, missing_words).
            The clips list includes placeholder ClipInfo objects for missing words.
        """
        logger.info(f"Looking up clips for {len(words)} words")
        if self.config.channel_id:
            logger.info(f"Filtering clips to channel: {self.config.channel_id}")
        
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
                    clip_info = self.database.find_phrase_in_transcripts(
                        phrase, 
                        exclude_video_ids=used_video_ids,
                        channel_id=self.config.channel_id,
                        padding_start=self.config.clip_padding_start,
                        padding_end=self.config.clip_padding_end
                    )
                    
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
                clip_info = self.database.get_clip_info(
                    word, 
                    exclude_video_ids=used_video_ids,
                    channel_id=self.config.channel_id
                )
                
                if clip_info is None:
                    missing_words.append(word)
                    logger.warning(f"No clip found for word: {word}, will use placeholder")
                    # Create placeholder ClipInfo
                    placeholder = ClipInfo(
                        word=word,
                        video_id="PLACEHOLDER",  # Special marker for placeholders
                        start_time=0.0,
                        duration=1.0  # Default duration for placeholder
                    )
                    found_clips.append(placeholder)
                else:
                    found_clips.append(clip_info)
                    used_video_ids.append(clip_info.video_id)
                
                i += 1
        
        # Log video diversity stats (excluding placeholders)
        real_clips = [c for c in found_clips if c.video_id != "PLACEHOLDER"]
        unique_videos = len(set(c.video_id for c in real_clips))
        if unique_videos < len(real_clips):
            logger.info(f"Video diversity: {unique_videos} unique videos used for {len(real_clips)} clips")
        else:
            logger.info(f"Video diversity: All clips from different videos ({unique_videos} unique)")
        
        logger.info(
            f"Found {len(real_clips)} clips, {len(missing_words)} words using placeholders"
        )
        
        return found_clips, missing_words
    
    def download_all_segments(
        self, 
        clips: List[ClipInfo],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Download all required video segments in parallel.
        Skips placeholder clips (they will be generated separately).
        
        Args:
            clips: List of clip information to download.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of downloaded file paths in same order as input clips.
            Placeholder clips will have None in their position.
            
        Raises:
            RuntimeError: If too many downloads fail or timeout occurs.
        """
        logger.info(f"Downloading {len(clips)} video segments (parallel)")
        
        # Filter out placeholders for downloading
        real_clips = [(i, clip) for i, clip in enumerate(clips) if clip.video_id != "PLACEHOLDER"]
        
        if not real_clips:
            logger.info("No real clips to download (all placeholders)")
            return [None] * len(clips)
        
        # Use configurable thread limit with safety bounds
        max_workers = max(1, min(self.config.max_download_workers, len(real_clips), 10))
        logger.info(f"Using {max_workers} concurrent download workers")
        
        downloaded_paths = [None] * len(clips)  # Preserve order, including placeholders
        failed_downloads = []  # Track failures for error reporting
        completed = 0
        
        def download_with_index(index_clip):
            """Download a clip and return its index and path."""
            index, clip = index_clip
            try:
                path = self.downloader.download_segment(clip)
                return (index, path, None, clip.word)
            except DownloadError as e:
                logger.error(f"Failed to download clip for '{clip.word}': {e}")
                return (index, None, e, clip.word)
            except Exception as e:
                logger.error(f"Unexpected error downloading '{clip.word}': {e}")
                return (index, None, e, clip.word)
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all downloads (only real clips)
                future_to_clip = {
                    executor.submit(download_with_index, (i, clip)): (i, clip)
                    for i, clip in real_clips
                }
                
                # Process as they complete with timeout
                try:
                    for future in as_completed(future_to_clip, timeout=self.config.download_timeout):
                        index, path, error, word = future.result()
                        if path:
                            downloaded_paths[index] = path
                        else:
                            failed_downloads.append((index, word, error))
                        
                        completed += 1
                        if progress_callback:
                            progress_callback(completed, len(real_clips))
                            
                except TimeoutError:
                    logger.error(
                        f"Download batch timed out after {self.config.download_timeout} seconds "
                        f"({completed}/{len(real_clips)} completed)"
                    )
                    # Cancel remaining futures
                    for future in future_to_clip:
                        future.cancel()
                    raise RuntimeError(
                        f"Download timeout: only {completed}/{len(real_clips)} completed in "
                        f"{self.config.download_timeout}s"
                    )
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error(f"Download batch failed: {e}")
            raise RuntimeError(f"Download batch failed: {e}") from e
        
        # Count successful downloads
        successful_paths = [p for p in downloaded_paths if p is not None]
        placeholder_count = sum(1 for clip in clips if clip.video_id == "PLACEHOLDER")
        
        # Check failure rate
        failure_rate = len(failed_downloads) / len(real_clips) if real_clips else 0
        if failure_rate > self.config.max_failure_rate:
            # Collect detailed error information
            failed_details = []
            for _, word, error in failed_downloads[:10]:  # Show first 10
                error_str = str(error) if error else "Unknown error"
                # Truncate very long error messages
                if len(error_str) > 100:
                    error_str = error_str[:97] + "..."
                failed_details.append(f"{word} ({error_str})")
            
            error_msg = (
                f"Download failure rate too high: {len(failed_downloads)}/{len(real_clips)} "
                f"({failure_rate:.1%}) failed (max allowed: {self.config.max_failure_rate:.1%}). "
                f"Failed words with errors: {'; '.join(failed_details)}"
                + ("..." if len(failed_downloads) > 10 else "")
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        if failed_downloads:
            logger.warning(
                f"{len(failed_downloads)} downloads failed but within acceptable threshold "
                f"({failure_rate:.1%} < {self.config.max_failure_rate:.1%})"
            )
        
        logger.info(
            f"Successfully downloaded {len(successful_paths)}/{len(real_clips)} segments, "
            f"{placeholder_count} placeholders to generate"
        )
        return downloaded_paths
    
    def process_segments(
        self,
        segment_paths: List[str],
        clips: List[ClipInfo],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Process segments (normalize, re-encode, add enhancements) for concatenation in parallel.
        
        Args:
            segment_paths: List of video segment paths.
            clips: List of clip info objects corresponding to segment paths.
            progress_callback: Optional callback function(current, total).
            
        Returns:
            List of processed file paths in same order as input.
            
        Raises:
            RuntimeError: If too many processing tasks fail or timeout occurs.
        """
        logger.info(f"Processing {len(segment_paths)} video segments (parallel)")
        
        # Create processed subdirectory
        processed_dir = self.temp_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        processed_paths = [None] * len(segment_paths)  # Preserve order
        failed_processing = []  # Track failures
        completed = 0
        
        def process_with_index(index_path_clip):
            """Process a segment and return its index and output path."""
            index, segment_path, clip_info = index_path_clip
            original_name = Path(segment_path).stem
            output_path = processed_dir / f"{original_name}_processed.mp4"
            segment_name = clip_info.word if clip_info else Path(segment_path).name
            
            # Check if already processed (cache)
            if output_path.exists():
                logger.debug(f"Using cached processed segment: {output_path.name}")
                return (index, str(output_path), None, segment_name)
            
            try:
                current_path = segment_path
                
                # Step 1: Normalize audio if configured
                if self.config.normalize_audio:
                    temp_normalized = processed_dir / f"{original_name}_normalized.mp4"
                    try:
                        self.processor.normalize_audio(current_path, str(temp_normalized))
                        current_path = str(temp_normalized)
                    except RuntimeError as e:
                        if "corrupted" in str(e).lower():
                            logger.warning(f"Skipping corrupted segment: {segment_path}")
                            return (index, None, e, segment_name)
                        raise
                
                # Step 2: Re-encode for consistency
                temp_reencoded = processed_dir / f"{original_name}_reencoded.mp4"
                try:
                    self.processor.reencode_for_concat(current_path, str(temp_reencoded))
                    # Validate the re-encoded file
                    if not temp_reencoded.exists() or temp_reencoded.stat().st_size < 1000:
                        raise RuntimeError(f"Re-encoded file is invalid: {temp_reencoded}")
                    current_path = str(temp_reencoded)
                except Exception as e:
                    logger.error(f"Failed to re-encode segment {segment_path}: {e}")
                    return (index, None, e, segment_name)
                
                # Step 3: Resize to aspect ratio if needed
                if self.config.aspect_ratio != "16:9":
                    temp_resized = processed_dir / f"{original_name}_resized.mp4"
                    self.processor.resize_to_aspect_ratio(
                        current_path,
                        str(temp_resized),
                        self.config.aspect_ratio
                    )
                    current_path = str(temp_resized)
                
                # Step 4: Add subtitles if configured
                if self.config.add_subtitles and clip_info:
                    temp_subtitled = processed_dir / f"{original_name}_subtitled.mp4"
                    self.processor.add_subtitle_overlay(
                        current_path,
                        str(temp_subtitled),
                        clip_info.word
                    )
                    current_path = str(temp_subtitled)
                
                # Step 5: Add watermark if configured
                if self.config.watermark_text:
                    temp_watermarked = processed_dir / f"{original_name}_watermarked.mp4"
                    self.processor.add_watermark(
                        current_path,
                        str(temp_watermarked),
                        self.config.watermark_text
                    )
                    current_path = str(temp_watermarked)
                
                # Move final result to output path
                if current_path != str(output_path):
                    import shutil
                    shutil.move(current_path, str(output_path))
                
                # Clean up temporary files
                for temp_file in [
                    processed_dir / f"{original_name}_normalized.mp4",
                    processed_dir / f"{original_name}_reencoded.mp4",
                    processed_dir / f"{original_name}_resized.mp4",
                    processed_dir / f"{original_name}_subtitled.mp4",
                    processed_dir / f"{original_name}_watermarked.mp4"
                ]:
                    if temp_file.exists() and temp_file != output_path:
                        temp_file.unlink()
                
                logger.debug(f"Processed segment: {output_path}")
                return (index, str(output_path), None, segment_name)
                
            except Exception as e:
                logger.error(f"Failed to process segment {segment_path}: {e}")
                return (index, None, e, segment_name)
        
        # Use configurable thread limit with safety bounds
        max_workers = max(1, min(self.config.max_processing_workers, len(segment_paths), 10))
        logger.info(f"Using {max_workers} concurrent processing workers")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all processing tasks
                future_to_segment = {
                    executor.submit(process_with_index, (i, path, clips[i] if i < len(clips) else None)): (i, path)
                    for i, path in enumerate(segment_paths)
                }
                
                # Process as they complete with timeout
                try:
                    for future in as_completed(future_to_segment, timeout=self.config.processing_timeout):
                        index, path, error, name = future.result()
                        if path:
                            processed_paths[index] = path
                        else:
                            failed_processing.append((index, name, error))
                        
                        completed += 1
                        if progress_callback:
                            progress_callback(completed, len(segment_paths))
                            
                except TimeoutError:
                    logger.error(
                        f"Processing batch timed out after {self.config.processing_timeout} seconds "
                        f"({completed}/{len(segment_paths)} completed)"
                    )
                    # Cancel remaining futures
                    for future in future_to_segment:
                        future.cancel()
                    raise RuntimeError(
                        f"Processing timeout: only {completed}/{len(segment_paths)} completed in "
                        f"{self.config.processing_timeout}s"
                    )
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error(f"Processing batch failed: {e}")
            raise RuntimeError(f"Processing batch failed: {e}") from e
        
        # Filter out None values (failed processing)
        successful_paths = [p for p in processed_paths if p is not None]
        
        # Check failure rate
        failure_rate = len(failed_processing) / len(segment_paths) if segment_paths else 0
        if failure_rate > self.config.max_failure_rate:
            failed_names = [name for _, name, _ in failed_processing[:10]]  # Show first 10
            error_msg = (
                f"Processing failure rate too high: {len(failed_processing)}/{len(segment_paths)} "
                f"({failure_rate:.1%}) failed (max allowed: {self.config.max_failure_rate:.1%}). "
                f"Failed segments: {', '.join(failed_names)}"
                + ("..." if len(failed_processing) > 10 else "")
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        if failed_processing:
            logger.warning(
                f"{len(failed_processing)} segments failed but within acceptable threshold "
                f"({failure_rate:.1%} < {self.config.max_failure_rate:.1%})"
            )
        else:
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
                    f"No clips found for any words. Missing: {', '.join(missing_words) if missing_words else 'all words'}"
                )
            
            if missing_words:
                logger.info(
                    f"Using placeholders for {len(missing_words)} words: {', '.join(missing_words)}"
                )
            
            # Step 3: Download segments and create placeholders
            logger.info("Step 3/5: Downloading video segments and creating placeholders")
            segments = self.download_all_segments(clips, progress_callback)
            
            # Create placeholder videos for missing words
            placeholder_dir = self.temp_dir / "placeholders"
            placeholder_dir.mkdir(parents=True, exist_ok=True)
            width, height = self._get_target_dimensions()
            
            for i, clip in enumerate(clips):
                if clip.video_id == "PLACEHOLDER":
                    placeholder_path = placeholder_dir / f"placeholder_{i}_{clip.word}.mp4"
                    logger.info(f"Creating placeholder for word: {clip.word}")
                    self.processor.create_title_card(
                        str(placeholder_path),
                        clip.word,
                        duration=clip.duration,
                        width=width,
                        height=height,
                        bg_color="gray",
                        text_color="white"
                    )
                    segments[i] = str(placeholder_path)
            
            # Verify we have at least some segments (either downloaded or placeholders)
            if not any(seg is not None for seg in segments):
                raise RuntimeError("Failed to download or create any video segments")
            
            # Step 4: Process segments
            logger.info("Step 4/5: Processing video segments")
            # Rebuild segments list maintaining order with placeholders
            processed_segments = [None] * len(segments)
            
            # Process only real segments first
            real_segments_to_process = []
            real_clips_to_process = []
            real_indices = []
            
            for i, (seg, clip) in enumerate(zip(segments, clips)):
                if seg is not None and clip.video_id != "PLACEHOLDER":
                    real_segments_to_process.append(seg)
                    real_clips_to_process.append(clip)
                    real_indices.append(i)
            
            if real_segments_to_process:
                processed_real = self.process_segments(
                    real_segments_to_process, 
                    real_clips_to_process, 
                    progress_callback
                )
                # Map processed segments back to their original positions
                for idx, processed_path in zip(real_indices, processed_real):
                    processed_segments[idx] = processed_path
            
            # Process placeholders (they're already in correct format, just need to resize if needed)
            for i, (seg, clip) in enumerate(zip(segments, clips)):
                if seg is not None and clip.video_id == "PLACEHOLDER":
                    # Placeholders already created with correct dimensions, but may need aspect ratio adjustment
                    if self.config.aspect_ratio != "16:9":
                        temp_resized = self.temp_dir / "processed" / f"placeholder_{i}_resized.mp4"
                        temp_resized.parent.mkdir(parents=True, exist_ok=True)
                        self.processor.resize_to_aspect_ratio(
                            seg,
                            str(temp_resized),
                            self.config.aspect_ratio
                        )
                        processed_segments[i] = str(temp_resized)
                    else:
                        processed_segments[i] = seg
            
            # Build final list maintaining exact order (including placeholders)
            # Only include segments that were successfully processed/created
            processed = []
            for i, seg in enumerate(processed_segments):
                if seg is not None:
                    processed.append(seg)
                else:
                    # If a segment failed, log warning but continue
                    logger.warning(f"Segment at index {i} failed to process, skipping")
            
            if not processed:
                raise RuntimeError("Failed to process any video segments")
            
            # Verify we have processed segments for all clips (placeholders included)
            expected_count = len([c for c in clips])
            if len(processed) != expected_count:
                logger.warning(
                    f"Processed segment count ({len(processed)}) doesn't match clip count ({expected_count}). "
                    f"Missing {expected_count - len(processed)} segments."
                )
            
            # Step 5: Add intro/outro cards and concatenate
            logger.info("Step 5/5: Adding intro/outro and concatenating videos")
            all_videos = []
            
            # Add intro card if configured
            if self.config.intro_text:
                intro_path = self.temp_dir / "intro_card.mp4"
                # Get dimensions from first video segment
                width, height = self._get_target_dimensions()
                self.processor.create_title_card(
                    str(intro_path),
                    self.config.intro_text,
                    duration=2.0,
                    width=width,
                    height=height
                )
                all_videos.append(str(intro_path))
            
            # Add processed segments in order (placeholders are already included)
            all_videos.extend(processed)
            
            # Add outro card if configured
            if self.config.outro_text:
                outro_path = self.temp_dir / "outro_card.mp4"
                width, height = self._get_target_dimensions()
                self.processor.create_title_card(
                    str(outro_path),
                    self.config.outro_text,
                    duration=2.0,
                    width=width,
                    height=height
                )
                all_videos.append(str(outro_path))
            
            # Concatenate everything
            if self.config.incremental_stitching:
                self.concatenator.concatenate_incremental(all_videos, str(output_path))
            else:
                self.concatenator.concatenate_videos(all_videos, str(output_path))
            
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
    
    def _get_target_dimensions(self) -> Tuple[int, int]:
        """Get target video dimensions based on aspect ratio configuration.
        
        Returns:
            Tuple of (width, height) in pixels.
        """
        resolutions = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1080, 1080)
        }
        return resolutions.get(self.config.aspect_ratio, (1920, 1080))
    
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
