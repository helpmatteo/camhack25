import json
from typing import List, Dict

def load_jsonl(file_path: str):
    """Generator that yields each line (JSON object or list) from a JSONL file."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def find_text_in_timestamps(word_entries: list, query: str) -> list:
    """
    Given a list of [start, end, word] or {"start":..., "end":..., "word":...} entries,
    return matches with timestamps for each word in the query.
    """
    query_tokens = query.strip().split()
    n = len(query_tokens)
    results = []

    # Extract words safely
    words = []
    for entry in word_entries:
        if isinstance(entry, list) and len(entry) >= 3:
            words.append(entry[2])
        elif isinstance(entry, dict) and "word" in entry:
            words.append(entry["word"])
        else:
            words.append("")  # placeholder for malformed entries

    for i in range(len(words) - n + 1):
        window = [w.lower() for w in words[i:i+n]]
        if window == [qt.lower() for qt in query_tokens]:
            # extract timestamps
            matched_words = word_entries[i:i+n]
            clip_words = []
            for w in matched_words:
                if isinstance(w, list):
                    clip_words.append({"word": w[2], "start": w[0], "end": w[1]})
                elif isinstance(w, dict):
                    clip_words.append({"word": w["word"], "start": w["start"], "end": w["end"]})
            results.append({
                "start_time": clip_words[0]["start"],
                "end_time": clip_words[-1]["end"],
                "words": clip_words
            })

    return results



def search_dataset(file_path: str, query: str, max_videos: int = 10, max_results: int = 10):
    """
    Search through the local JSONL dataset for the given query string.
    Returns a list of matches with video IDs and word-level timestamps.
    """
    results = []
    for i, record in enumerate(load_jsonl(file_path)):
        if i >= max_videos:
            break

        # Try to extract the actual list of [start, end, word]
        if isinstance(record, dict):
            # Some records might have fields like "segments", "words", or "data"
            word_entries = record.get("segments") or record.get("words") or record.get("data")
            video_id = record.get("video_id", f"video_{i}")
        elif isinstance(record, list):
            word_entries = record
            video_id = f"video_{i}"
        else:
            continue  # Skip unexpected structures

        if not isinstance(word_entries, list):
            continue

        matches = find_text_in_timestamps(word_entries, query)
        for m in matches:
            m["video_id"] = video_id
            results.append(m)
            if len(results) >= max_results:
                return results

    return results


if __name__ == "__main__":
    dataset_path = r"C:\Users\thoma\Downloads\live_whisperx_526k_with_seeks.jsonl"
    query_text = "we"  # 🔍 your search text

    matches = search_dataset(dataset_path, query_text, max_videos=50, max_results=5)

    if not matches:
        print("❌ No matches found.")
    else:
        for m in matches:
            print(f"\n🎥 Video ID: {m['video_id']}")
            print(f"🕒 Clip: {m['start_time']:.2f}s → {m['end_time']:.2f}s")
            print("🗣️ Words:")
            for w in m["words"]:
                print(f"  {w['word']}  {w['start']} → {w['end']}")
