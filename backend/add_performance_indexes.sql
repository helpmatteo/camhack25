-- Performance optimization indexes
-- Run this to speed up database queries

-- Index for video_id lookups (helps with channel filtering and video diversity)
CREATE INDEX IF NOT EXISTS idx_word_clips_video_id ON word_clips(video_id);

-- Composite index for channel filtering
CREATE INDEX IF NOT EXISTS idx_word_clips_word_video ON word_clips(word, video_id);

-- Index for start_time range queries
CREATE INDEX IF NOT EXISTS idx_word_clips_timing ON word_clips(video_id, start_time);

-- Index for channel lookups in videos table
CREATE INDEX IF NOT EXISTS idx_videos_channel_id ON videos(channel_id);

-- Optimize video_transcripts lookups
CREATE INDEX IF NOT EXISTS idx_video_transcripts_video ON video_transcripts(video_id, word_count);

-- Statistics for query optimizer
ANALYZE;

-- Vacuum to optimize database file
VACUUM;

