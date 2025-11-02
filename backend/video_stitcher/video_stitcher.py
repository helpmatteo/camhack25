"""Main video stitcher orchestrator module."""

import logging
import re
import time
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
    incremental_stitching: bool = False  # Changed default to False for better performance
    cleanup_temp_files: bool = True
    verify_ffmpeg_on_init: bool = True  # Set to False to skip ffmpeg verification
    max_phrase_length: int = 10  # Maximum number of consecutive words to match as a phrase (1-50)
    max_workers: int = 8  # Number of parallel workers (1=sequential, 2-8=parallel for performance)
    channel_id: Optional[str] = None  # Optional channel ID to filter clips to
    
    # Clip extraction options
    clip_padding_start: float = 0  # Padding before word start (seconds) for cleaner cuts
    clip_padding_end: float = 0  # Padding after word end (seconds) for cleaner cuts
    
    # Visual enhancement options
    add_subtitles: bool = False  # Add subtitle overlays to clips
    aspect_ratio: str = "16:9"  # Target aspect ratio ('16:9', '9:16', '1:1')
    watermark_text: Optional[str] = None  # Watermark text to add
    intro_text: Optional[str] = None  # Intro card text
    outro_text: Optional[str] = None  # Outro card text


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
        # Extract words using regex that preserves contractions, convert to lowercase
        # This pattern matches words with optional internal apostrophes (don't, isn't, etc.)
        words = re.findall(r"\b[\w']+\b", text.lower())
        
        # Remove empty strings and standalone apostrophes
        words = [w for w in words if w and w != "'"]
        
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
        return downloaded_paths  # Return full list with None values preserved for indexing
    
    def process_segments(
        self,
        segment_paths: List[str],
        clips: List[ClipInfo],
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Process segments (normalize, re-encode) for concatenation in parallel.
        
        Args:
            segment_paths: List of video segment paths.
            clips: List of clip info objects corresponding to segment paths.
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
        
        def process_segment(index, segment_path, clip_info=None):
            """Process a single segment and return its index and path."""
            # Generate output path
            original_name = Path(segment_path).stem
            output_path = processed_dir / f"{original_name}_processed.mp4"
            segment_name = clip_info.word if clip_info else Path(segment_path).name
            
            # Check if already processed (cache)
            if output_path.exists():
                logger.debug(f"Using cached processed segment: {output_path.name}")
                return (index, str(output_path), None)
            
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
                            return (index, None, e)
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
                    return (index, None, e)
                
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
                return index, str(output_path), None
                
            except Exception as e:
                logger.error(f"Failed to process segment {segment_path}: {e}")
                return index, None, e
        
        # Use ThreadPoolExecutor for parallel processing if max_workers > 1
        if self.config.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                # Submit all processing tasks
                future_to_index = {
                    executor.submit(process_segment, i, path, clips[i] if i < len(clips) else None): i 
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
                
                clip_info_item = clips[i] if i < len(clips) else None
                index, processed_path, error = process_segment(i, path, clip_info_item)
                if processed_path is not None:
                    processed_paths[index] = processed_path
        
        # Filter out failed processing while preserving order and clip association
        # Return tuples of (path, clip) for successful segments only
        successful_results = []
        for i, path in enumerate(processed_paths):
            if path is not None and i < len(clips):
                successful_results.append((path, clips[i]))
        
        if len(successful_results) < len(segment_paths):
            logger.warning(f"Only {len(successful_results)}/{len(segment_paths)} segments processed successfully")
        
        # Log the order of processed files for debugging
        logger.debug(f"Processed files in order: {[Path(p).name for p, _ in successful_results]}")
        
        logger.info(
            f"Successfully processed {len(successful_results)}/{len(segment_paths)} segments"
        )
        return successful_results
    
    def generate_video(
        self,
        text: str,
        output_filename: str,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[str, List[dict]]:
        """Generate video from text.
        
        Main public API that orchestrates the entire pipeline.
        
        Args:
            text: Input text to convert to video.
            output_filename: Name of the output file.
            progress_callback: Optional callback for progress updates.
            
        Returns:
            Tuple of (absolute path to the generated video file, list of word timings).
            Word timings format: [{"word": str, "start": float, "end": float}, ...]
            
        Raises:
            ValueError: If no clips found for any words.
            RuntimeError: If video generation fails.
        """
        start_time = time.time()
        phase_times = {}
        word_timings = []  # Track word timings for interactive subtitles
        
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
                    f"No clips found for any words. Missing: {', '.join(missing_words) if missing_words else 'all words'}"
                )
            
            if missing_words:
                logger.info(
                    f"Using placeholders for {len(missing_words)} words: {', '.join(missing_words)}"
                )
            
            # Step 3: Download segments
            phase_start = time.time()
            logger.info("Step 3/5: Downloading video segments")
            segments = self.download_all_segments(clips, progress_callback)
            phase_times['download'] = time.time() - phase_start
            logger.info(f"✓ Download completed in {phase_times['download']:.2f}s")
            
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
            
            # Filter segments and clips to only include non-None segments
            valid_segments = []
            valid_clips = []
            for i, seg in enumerate(segments):
                if seg is not None:
                    valid_segments.append(seg)
                    valid_clips.append(clips[i] if i < len(clips) else None)
            
            # Step 4: Process segments
            phase_start = time.time()
            logger.info("Step 4/5: Processing video segments")
            processed_results = self.process_segments(valid_segments, valid_clips, progress_callback)
            phase_times['process'] = time.time() - phase_start
            logger.info(f"✓ Processing completed in {phase_times['process']:.2f}s")
            
            if not processed_results:
                raise RuntimeError("Failed to process any video segments")
            
            # Verify we have processed segments for all clips (placeholders included)
            expected_count = len([c for c in clips])
            if len(processed_results) != expected_count:
                logger.warning(
                    f"Processed segment count ({len(processed_results)}) doesn't match clip count ({expected_count}). "
                    f"Missing {expected_count - len(processed_results)} segments."
                )
            
            # Step 5: Add intro/outro cards and concatenate
            logger.info("Step 5/5: Adding intro/outro and concatenating videos")
            all_videos = []
            current_timestamp = 0.0  # Track cumulative timestamp
            
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
                current_timestamp += 2.0  # Intro card is 2 seconds
            
            # Add processed segments in order and track timings
            # processed_results is a list of (video_path, clip) tuples
            # This ensures word timings only include clips that made it into the final video
            for video_path, clip in processed_results:
                all_videos.append(video_path)
                
                # Get actual video duration from the processed file
                try:
                    props = self.processor.verify_video_properties(video_path)
                    clip_duration = props.get('duration', clip.duration)
                except Exception as e:
                    logger.warning(f"Could not get duration for {video_path}, using clip duration: {e}")
                    clip_duration = clip.duration
                
                # Record word timing only for clips that made it into final video
                word_timings.append({
                    "word": clip.word,
                    "start": current_timestamp,
                    "end": current_timestamp + clip_duration
                })
                
                current_timestamp += clip_duration
            
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
            phase_start = time.time()
            if self.config.incremental_stitching:
                self.concatenator.concatenate_incremental(all_videos, str(output_path))
            else:
                self.concatenator.concatenate_videos(all_videos, str(output_path))
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
            logger.info(f"Generated {len(word_timings)} word timings for interactive subtitles")
            
            return str(output_path.resolve()), word_timings
            
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
