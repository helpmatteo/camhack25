import os
import sqlite3
from typing import List, Dict

DB_PATH = os.getenv("DB_PATH", "./data/youglish.db")



def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn





def search_phrase(q: str, lang: str = None, limit: int = 20) -> List[Dict]:
    # Exact phrase using FTS5 with quotes. We also filter by lang if provided.
    sql = (
        "SELECT s.id, s.video_id, s.lang, s.t_start, s.t_end, s.text, v.title, v.channel_title "
        "FROM segments s JOIN segments_fts f ON s.id=f.rowid JOIN videos v ON v.video_id=s.video_id "
        "WHERE f.text MATCH ? "
    )
    params = [f'"{q}"']
    if lang:
        sql += " AND s.lang LIKE ?"
        params.append(f"{lang}%")
    sql += " ORDER BY s.t_start LIMIT ?"
    params.append(int(limit))

    with get_conn() as c:
        cur = c.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        return rows

