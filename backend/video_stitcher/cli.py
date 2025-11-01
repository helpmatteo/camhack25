"""Command-line interface for the video stitcher."""

import argparse
import logging
import sys
from pathlib import Path

from .video_stitcher import VideoStitcher, StitchingConfig


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level.
    
    Args:
        verbose: If True, enable DEBUG level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    if verbose:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def progress_callback(current: int, total: int) -> None:
    """Print progress to console.
    
    Args:
        current: Current item number.
        total: Total number of items.
    """
    percentage = (current / total) * 100
    print(f"Progress: {current}/{total} ({percentage:.1f}%)", end='\r')
    if current == total:
        print()  # New line when complete


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Video Stitcher - Create videos from text using YouTube clips',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  %(prog)s --text "hello world" --database words.db
  
  # Custom output location
  %(prog)s --text "hello world" --database words.db --output my_video.mp4 --output-dir ./videos
  
  # Verbose mode with debug logging
  %(prog)s --text "hello world" --database words.db --verbose
  
  # Keep temporary files for debugging
  %(prog)s --text "hello world" --database words.db --no-cleanup
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--text',
        type=str,
        required=True,
        help='Input text to convert to video'
    )
    
    parser.add_argument(
        '--database',
        type=str,
        required=True,
        help='Path to SQLite database with word-clip mappings'
    )
    
    # Optional arguments
    parser.add_argument(
        '--output',
        type=str,
        default='output.mp4',
        help='Output video filename (default: output.mp4)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./output',
        help='Output directory (default: ./output)'
    )
    
    parser.add_argument(
        '--temp-dir',
        type=str,
        default='./temp',
        help='Temporary files directory (default: ./temp)'
    )
    
    parser.add_argument(
        '--quality',
        type=str,
        default='bestvideo[height<=720]+bestaudio/best[height<=720]',
        help='Video quality format for yt-dlp (default: 720p)'
    )
    
    parser.add_argument(
        '--max-phrase-length',
        type=int,
        default=10,
        choices=range(1, 51),
        metavar='[1-50]',
        help='Maximum number of consecutive words to match as a phrase (default: 10, range: 1-50)'
    )
    
    parser.add_argument(
        '--padding-start',
        type=float,
        default=0.15,
        metavar='SECONDS',
        help='Padding before word start for cleaner cuts (default: 0.15 seconds)'
    )
    
    parser.add_argument(
        '--padding-end',
        type=float,
        default=0.15,
        metavar='SECONDS',
        help='Padding after word end for cleaner cuts (default: 0.15 seconds)'
    )
    
    parser.add_argument(
        '--no-normalize',
        action='store_true',
        help='Disable audio normalization'
    )
    
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Keep temporary files (useful for debugging)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Verify database exists
        if not Path(args.database).exists():
            print(f"Error: Database file not found: {args.database}", file=sys.stderr)
            return 1
        
        # Create configuration
        config = StitchingConfig(
            database_path=args.database,
            output_directory=args.output_dir,
            temp_directory=args.temp_dir,
            video_quality=args.quality,
            normalize_audio=not args.no_normalize,
            incremental_stitching=True,
            cleanup_temp_files=not args.no_cleanup,
            max_phrase_length=args.max_phrase_length,
            clip_padding_start=args.padding_start,
            clip_padding_end=args.padding_end
        )
        
        # Print summary
        print("\n" + "="*60)
        print("Video Stitcher")
        print("="*60)
        print(f"Input text: {args.text}")
        print(f"Database: {args.database}")
        print(f"Output: {args.output_dir}/{args.output}")
        print(f"Max phrase length: {config.max_phrase_length} words")
        print(f"Clip padding: {config.clip_padding_start}s before, {config.clip_padding_end}s after")
        print(f"Audio normalization: {'enabled' if config.normalize_audio else 'disabled'}")
        print(f"Cleanup temp files: {'yes' if config.cleanup_temp_files else 'no'}")
        print("="*60 + "\n")
        
        # Create stitcher and generate video
        with VideoStitcher(config) as stitcher:
            output_path = stitcher.generate_video(
                text=args.text,
                output_filename=args.output,
                progress_callback=progress_callback
            )
        
        # Print success summary
        print("\n" + "="*60)
        print("SUCCESS!")
        print("="*60)
        print(f"Video created: {output_path}")
        print(f"You can now play: {output_path}")
        print("="*60 + "\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.", file=sys.stderr)
        logger.info("Operation cancelled by user")
        return 130  # Standard exit code for SIGINT
        
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
        logger.exception("Fatal error occurred")
        return 1


if __name__ == '__main__':
    sys.exit(main())
