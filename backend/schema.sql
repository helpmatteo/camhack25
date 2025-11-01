PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  title TEXT,
  channel_id TEXT,
  channel_title TEXT,
  lang_default TEXT,
  published_at TEXT
);

CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  lang TEXT NOT NULL,
  t_start REAL NOT NULL,
  t_end REAL NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'CAPTION',
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

-- FTS index over segments.text
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
  text,
  content='segments',
  content_rowid='id',
  tokenize = 'unicode61 remove_diacritics 2'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
  INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;

-- Word clips table for video stitching
CREATE TABLE IF NOT EXISTS word_clips (
  word TEXT NOT NULL,
  video_id TEXT NOT NULL,
  start_time REAL NOT NULL,
  duration REAL NOT NULL,
  PRIMARY KEY (word, video_id, start_time)
);

CREATE INDEX IF NOT EXISTS idx_word_clips_word ON word_clips(word);

