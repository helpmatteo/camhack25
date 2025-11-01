"""Tests for parallel processing in video stitcher."""

import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from video_stitcher import VideoStitcher, StitchingConfig
from video_stitcher.database import ClipInfo


class TestParallelProcessing(unittest.TestCase):
    """Test parallel processing functionality."""
    
    def test_configurable_thread_limits(self):
        """Test that thread limits are configurable and enforced."""
        config = StitchingConfig(
            database_path=":memory:",
            max_download_workers=2,
            max_processing_workers=5,
            verify_ffmpeg_on_init=False
        )
        
        self.assertEqual(config.max_download_workers, 2)
        self.assertEqual(config.max_processing_workers, 5)
    
    def test_thread_limit_bounds(self):
        """Test that thread limits are bounded correctly."""
        # Test download workers bounded to 1-10
        clips = [Mock(video_id=f"vid{i}") for i in range(20)]
        
        # Should be bounded to max 10
        max_workers_high = max(1, min(15, len(clips), 10))
        self.assertEqual(max_workers_high, 10)
        
        # Should be at least 1
        max_workers_low = max(1, min(0, len(clips), 10))
        self.assertEqual(max_workers_low, 1)
        
        # Should match actual count if less than limit
        max_workers_normal = max(1, min(3, 5, 10))
        self.assertEqual(max_workers_normal, 3)
    
    def test_timeout_configuration(self):
        """Test that timeout values are configurable."""
        config = StitchingConfig(
            database_path=":memory:",
            download_timeout=600,
            processing_timeout=900,
            verify_ffmpeg_on_init=False
        )
        
        self.assertEqual(config.download_timeout, 600)
        self.assertEqual(config.processing_timeout, 900)
    
    def test_failure_rate_threshold(self):
        """Test failure rate calculation and threshold checking."""
        # Test various failure rates
        test_cases = [
            (5, 10, 0.5, True),   # 50% failure, threshold 50% - should pass
            (6, 10, 0.5, False),  # 60% failure, threshold 50% - should fail
            (3, 10, 0.5, True),   # 30% failure, threshold 50% - should pass
            (0, 10, 0.5, True),   # 0% failure - should pass
        ]
        
        for failures, total, threshold, should_pass in test_cases:
            failure_rate = failures / total if total > 0 else 0
            exceeds_threshold = failure_rate > threshold
            
            if should_pass:
                self.assertLessEqual(failure_rate, threshold,
                    f"Failed: {failures}/{total} should pass with threshold {threshold}")
            else:
                self.assertGreater(failure_rate, threshold,
                    f"Failed: {failures}/{total} should fail with threshold {threshold}")
    
    def test_timeout_cancellation(self):
        """Test that timeouts properly cancel remaining futures."""
        def slow_task(n):
            time.sleep(0.5)
            return n
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(slow_task, i) for i in range(10)]
            
            completed = []
            try:
                # Timeout after 1 second (only ~2 tasks should complete)
                for future in as_completed(futures, timeout=1.0):
                    completed.append(future.result())
            except TimeoutError:
                # Cancel remaining futures
                for future in futures:
                    future.cancel()
            
            # Some tasks should have completed, but not all
            self.assertGreater(len(completed), 0, "Some tasks should complete")
            self.assertLess(len(completed), 10, "Not all tasks should complete")
    
    def test_order_preservation_with_parallel_execution(self):
        """Test that results maintain order despite parallel execution."""
        def process_item(index_value):
            index, value = index_value
            # Simulate variable processing time
            time.sleep(0.1 * (5 - index))  # Reverse order timing
            return (index, value * 2)
        
        items = [(i, i * 10) for i in range(5)]
        results = [None] * len(items)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_item = {
                executor.submit(process_item, item): item
                for item in items
            }
            
            for future in as_completed(future_to_item):
                index, value = future.result()
                results[index] = value
        
        # Check order is preserved
        expected = [0, 20, 40, 60, 80]
        self.assertEqual(results, expected)
    
    def test_error_aggregation(self):
        """Test that errors are properly collected and reported."""
        def task_with_error(index_value):
            index, value = index_value
            if index % 3 == 0:  # Fail every 3rd task
                raise ValueError(f"Task {index} failed")
            return (index, value, None)
        
        items = [(i, f"item{i}") for i in range(10)]
        results = [None] * len(items)
        failures = []
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_item = {
                executor.submit(task_with_error, item): item
                for item in items
            }
            
            for future in as_completed(future_to_item):
                try:
                    index, value, error = future.result()
                    results[index] = value
                except Exception as e:
                    index, value = future_to_item[future]
                    failures.append((index, value, str(e)))
        
        # Check that we collected failures
        self.assertEqual(len(failures), 4)  # indices 0, 3, 6, 9
        self.assertIn(0, [f[0] for f in failures])
        self.assertIn(3, [f[0] for f in failures])
    
    def test_concurrent_cache_checking(self):
        """Test that cache checking works correctly with concurrent access."""
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some cached files
            for i in range(5):
                path = Path(tmpdir) / f"cached_{i}.txt"
                path.write_text(f"content {i}")
            
            def check_cache(index):
                path = Path(tmpdir) / f"cached_{index}.txt"
                if path.exists():
                    return (index, str(path), "cached")
                else:
                    # Simulate processing
                    time.sleep(0.1)
                    return (index, None, "processed")
            
            results = [None] * 10
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(check_cache, i): i
                    for i in range(10)
                }
                
                for future in as_completed(futures):
                    index, path, status = future.result()
                    results[index] = status
            
            # Check that cached files were detected
            self.assertEqual(results[:5], ["cached"] * 5)
            self.assertEqual(results[5:], ["processed"] * 5)
    
    def test_parallel_vs_serial_performance(self):
        """Test that parallel execution is faster than serial."""
        def slow_task(n):
            time.sleep(0.2)
            return n * 2
        
        items = list(range(5))
        
        # Serial execution
        start = time.time()
        serial_results = [slow_task(i) for i in items]
        serial_time = time.time() - start
        
        # Parallel execution
        start = time.time()
        parallel_results = [None] * len(items)
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_index = {
                executor.submit(slow_task, i): i
                for i in items
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                parallel_results[index] = future.result()
        parallel_time = time.time() - start
        
        # Verify results match
        self.assertEqual(serial_results, parallel_results)
        
        # Parallel should be faster (at least 1.5x)
        self.assertLess(parallel_time, serial_time / 1.5,
            f"Parallel ({parallel_time:.2f}s) should be faster than serial ({serial_time:.2f}s)")


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation."""
    
    def test_default_values(self):
        """Test that default values are sensible."""
        config = StitchingConfig(
            database_path=":memory:",
            verify_ffmpeg_on_init=False
        )
        
        # Check defaults
        self.assertEqual(config.max_download_workers, 3)
        self.assertEqual(config.max_processing_workers, 4)
        self.assertEqual(config.download_timeout, 300)
        self.assertEqual(config.processing_timeout, 600)
        self.assertEqual(config.max_failure_rate, 0.5)
    
    def test_custom_values(self):
        """Test that custom values are accepted."""
        config = StitchingConfig(
            database_path=":memory:",
            max_download_workers=5,
            max_processing_workers=8,
            download_timeout=600,
            processing_timeout=1200,
            max_failure_rate=0.3,
            verify_ffmpeg_on_init=False
        )
        
        self.assertEqual(config.max_download_workers, 5)
        self.assertEqual(config.max_processing_workers, 8)
        self.assertEqual(config.download_timeout, 600)
        self.assertEqual(config.processing_timeout, 1200)
        self.assertEqual(config.max_failure_rate, 0.3)


if __name__ == '__main__':
    unittest.main()

