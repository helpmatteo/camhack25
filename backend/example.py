"""
example.py - Usage examples for the Video Stitcher system

This file demonstrates various ways to use the video stitcher.
"""

import logging
from pathlib import Path

from video_stitcher import VideoStitcher, StitchingConfig


def example_1_basic_usage():
    """Example 1: Basic Usage
    
    Simplest way to generate a video from text.
    """
    print("\n" + "="*60)
    print("Example 1: Basic Usage")
    print("="*60)
    
    # Create configuration
    config = StitchingConfig(
        database_path="my_words.db",  # Replace with your database path
        output_directory="./output",
        temp_directory="./temp"
    )
    
    # Generate video
    with VideoStitcher(config) as stitcher:
        output_path = stitcher.generate_video(
            text="hello world",
            output_filename="example1_output.mp4"
        )
    
    print(f"\nVideo created: {output_path}")
    print("="*60 + "\n")


def example_2_with_progress():
    """Example 2: With Progress Callback
    
    Shows how to track progress during video generation.
    """
    print("\n" + "="*60)
    print("Example 2: With Progress Callback")
    print("="*60)
    
    def show_progress(current, total):
        """Progress callback function."""
        percentage = (current / total) * 100
        print(f"Progress: {current}/{total} ({percentage:.1f}%)")
    
    config = StitchingConfig(database_path="my_words.db")
    
    with VideoStitcher(config) as stitcher:
        output_path = stitcher.generate_video(
            text="hello world test",
            output_filename="example2_output.mp4",
            progress_callback=show_progress
        )
    
    print(f"\nVideo created: {output_path}")
    print("="*60 + "\n")


def example_3_custom_config():
    """Example 3: Custom Configuration
    
    Demonstrates advanced configuration options.
    """
    print("\n" + "="*60)
    print("Example 3: Custom Configuration")
    print("="*60)
    
    # Custom configuration
    config = StitchingConfig(
        database_path="my_words.db",
        output_directory="./my_videos",
        temp_directory="./temp_processing",
        video_quality="bestvideo[height<=1080]+bestaudio/best[height<=1080]",  # 1080p
        normalize_audio=True,
        incremental_stitching=True,
        cleanup_temp_files=True
    )
    
    print(f"Output directory: {config.output_directory}")
    print(f"Video quality: {config.video_quality}")
    print(f"Audio normalization: {config.normalize_audio}")
    print(f"Cleanup temp files: {config.cleanup_temp_files}")
    
    with VideoStitcher(config) as stitcher:
        output_path = stitcher.generate_video(
            text="python programming",
            output_filename="example3_hd_output.mp4"
        )
    
    print(f"\nVideo created: {output_path}")
    print("="*60 + "\n")


def example_4_error_handling():
    """Example 4: Error Handling
    
    Shows how to handle errors gracefully.
    """
    print("\n" + "="*60)
    print("Example 4: Error Handling")
    print("="*60)
    
    config = StitchingConfig(database_path="my_words.db")
    
    try:
        with VideoStitcher(config) as stitcher:
            output_path = stitcher.generate_video(
                text="hello world nonexistent_word",
                output_filename="example4_output.mp4"
            )
        
        print(f"\nVideo created: {output_path}")
        print("Note: Some words may have been skipped if not in database")
        
    except ValueError as e:
        print(f"\nError: {e}")
        print("This happens when no clips are found for any words.")
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        print("Check logs for details.")
    
    print("="*60 + "\n")


def example_5_database_stats():
    """Example 5: Database Statistics
    
    Shows how to query database information.
    """
    print("\n" + "="*60)
    print("Example 5: Database Statistics")
    print("="*60)
    
    from video_stitcher.database import WordClipDatabase
    
    try:
        with WordClipDatabase("my_words.db") as db:
            stats = db.get_database_stats()
            
            print(f"\nDatabase Statistics:")
            print(f"  Total words: {stats['total_words']}")
            print(f"  Unique videos: {stats['unique_videos']}")
            print(f"  Average clip duration: {stats['avg_duration']:.2f} seconds")
            
            # Look up specific word
            clip_info = db.get_clip_info("hello")
            if clip_info:
                print(f"\nExample clip for 'hello':")
                print(f"  Video ID: {clip_info.video_id}")
                print(f"  Start time: {clip_info.start_time}s")
                print(f"  Duration: {clip_info.duration}s")
    
    except FileNotFoundError:
        print("\nDatabase not found. Please create a database first.")
    
    print("="*60 + "\n")


def example_6_create_test_database():
    """Example 6: Create a Test Database
    
    Shows how to create a simple test database programmatically.
    """
    print("\n" + "="*60)
    print("Example 6: Create Test Database")
    print("="*60)
    
    import sqlite3
    
    db_path = "example_words.db"
    
    # Create database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS word_clips (
            word TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            duration REAL NOT NULL
        )
    """)
    
    # Sample data - using first YouTube video and popular videos
    test_data = [
        ("hello", "jNQXAC9IVRw", 5.0, 1.5),
        ("world", "jNQXAC9IVRw", 10.0, 1.2),
        ("test", "jNQXAC9IVRw", 15.0, 1.0),
        ("python", "kqtD5dpn9C8", 5.0, 1.3),
        ("code", "kqtD5dpn9C8", 10.0, 1.1),
    ]
    
    # Clear existing data and insert new
    cursor.execute("DELETE FROM word_clips")
    cursor.executemany("""
        INSERT INTO word_clips (word, video_id, start_time, duration)
        VALUES (?, ?, ?, ?)
    """, test_data)
    
    conn.commit()
    conn.close()
    
    print(f"\nTest database created: {db_path}")
    print(f"Contains {len(test_data)} word mappings")
    print("\nYou can now use this database with:")
    print(f"  python -m video_stitcher.cli --text 'hello world' --database {db_path}")
    print("="*60 + "\n")


def example_7_batch_processing():
    """Example 7: Batch Processing
    
    Generate multiple videos from different texts.
    """
    print("\n" + "="*60)
    print("Example 7: Batch Processing")
    print("="*60)
    
    texts = [
        ("hello world", "video1.mp4"),
        ("python code", "video2.mp4"),
        ("test hello", "video3.mp4"),
    ]
    
    config = StitchingConfig(
        database_path="my_words.db",
        output_directory="./batch_output"
    )
    
    print(f"\nProcessing {len(texts)} videos...")
    
    with VideoStitcher(config) as stitcher:
        for i, (text, filename) in enumerate(texts, 1):
            try:
                print(f"\n[{i}/{len(texts)}] Generating: {filename}")
                print(f"Text: '{text}'")
                
                output_path = stitcher.generate_video(
                    text=text,
                    output_filename=filename
                )
                
                print(f"✓ Created: {output_path}")
                
            except Exception as e:
                print(f"✗ Failed: {e}")
    
    print("\nBatch processing completed!")
    print("="*60 + "\n")


def main():
    """Run all examples."""
    # Setup logging
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings and errors
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "#"*60)
    print("# Video Stitcher - Usage Examples")
    print("#"*60)
    
    # Check if example database exists
    if not Path("my_words.db").exists():
        print("\nNote: Database 'my_words.db' not found.")
        print("Creating an example database first...\n")
        example_6_create_test_database()
        
        # Update all examples to use the example database
        global_db_path = "example_words.db"
    else:
        global_db_path = "my_words.db"
    
    # List of examples
    examples = [
        ("Example 6: Create Test Database", example_6_create_test_database),
        ("Example 5: Database Statistics", example_5_database_stats),
        ("Example 1: Basic Usage", example_1_basic_usage),
        ("Example 2: With Progress", example_2_with_progress),
        ("Example 3: Custom Config", example_3_custom_config),
        ("Example 4: Error Handling", example_4_error_handling),
        ("Example 7: Batch Processing", example_7_batch_processing),
    ]
    
    print("\nAvailable examples:")
    for i, (name, func) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\nNote: Examples 1-4 and 7 require ffmpeg and internet connection.")
    print("They will attempt to download videos from YouTube.\n")
    
    choice = input("Enter example number to run (or 'all' for all examples): ").strip()
    
    if choice.lower() == 'all':
        for name, func in examples:
            try:
                func()
            except Exception as e:
                print(f"\nError in {name}: {e}\n")
    elif choice.isdigit() and 1 <= int(choice) <= len(examples):
        name, func = examples[int(choice) - 1]
        try:
            func()
        except Exception as e:
            print(f"\nError: {e}\n")
    else:
        print("Invalid choice. Please run again and select a valid example number.")


if __name__ == "__main__":
    main()
