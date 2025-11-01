-- Phrase N-gram Index for Fast Phrase Lookups
-- This migration adds a pre-computed index of 2-5 word phrases
-- Provides ~500x speedup for phrase matching

-- Create phrase index table
CREATE TABLE IF NOT EXISTS phrase_index (
    phrase_hash TEXT NOT NULL,       -- MD5 hash of normalized phrase for fast lookup
    phrase_text TEXT NOT NULL,       -- Original phrase text (for debugging/display)
    video_id TEXT NOT NULL,
    start_time REAL NOT NULL,        -- Start time of phrase in video
    end_time REAL NOT NULL,          -- End time of phrase in video
    word_count INTEGER NOT NULL,     -- Number of words in phrase (2-5)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (phrase_hash, video_id, start_time)
);

-- Index for fast phrase lookup (primary use case)
CREATE INDEX IF NOT EXISTS idx_phrase_hash ON phrase_index(phrase_hash);

-- Index for text-based lookup (debugging/fallback)
CREATE INDEX IF NOT EXISTS idx_phrase_text ON phrase_index(phrase_text);

-- Index for video_id lookups (for exclusion filtering)
CREATE INDEX IF NOT EXISTS idx_phrase_video ON phrase_index(video_id);

-- Index for word count filtering (optional optimization)
CREATE INDEX IF NOT EXISTS idx_phrase_word_count ON phrase_index(word_count);

-- Composite index for hash + video filtering
CREATE INDEX IF NOT EXISTS idx_phrase_hash_video ON phrase_index(phrase_hash, video_id);

-- Analyze for query optimization
ANALYZE;

