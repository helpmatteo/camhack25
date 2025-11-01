import React, { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API || "http://localhost:8000";

function useYouTubeAPI() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (window.YT && window.YT.Player) {
      setReady(true);
      return;
    }

    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.body.appendChild(tag);

    const onReady = () => setReady(true);
    window.onYouTubeIframeAPIReady = onReady;

    return () => {
      if (window.onYouTubeIframeAPIReady === onReady) {
        window.onYouTubeIframeAPIReady = undefined;
      }
    };
  }, []);

  return ready;
}

function sentenceSplit(text) {
  const explicit = Array.from(text.matchAll(/"([^"]+)"/g)).map((m) => m[1]);
  if (explicit.length) {
    return explicit.map((s) => s.trim()).filter(Boolean);
  }

  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

async function searchExact(phrase, lang = "en") {
  const params = new URLSearchParams({ q: phrase, lang, limit: "5" });
  const response = await fetch(`${API}/search?${params}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function generateVideo(text, lang = "en", maxPhraseLength = 10) {
  const response = await fetch(`${API}/generate-video`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text, lang, max_phrase_length: maxPhraseLength }),
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error);
  }
  return response.json();
}

function ms(t) {
  const seconds = Math.floor(t % 60)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((t / 60) % 60).toString();
  const hours = Math.floor(t / 3600);
  return (hours > 0 ? hours + ":" : "") + minutes + ":" + seconds;
}

function PlaylistLinks({ segments }) {
  if (!segments.length) return null;

  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold mb-2 text-emerald-900">Timestamped links</h3>
      <ul className="space-y-1 text-sm">
        {segments.map((segment, index) => (
          <li key={`${segment.videoId}-${segment.start}-${index}`}>
            <a
              href={`https://www.youtube.com/watch?v=${segment.videoId}&t=${Math.floor(
                segment.start
              )}s`}
              target="_blank"
              rel="noreferrer"
              className="text-amber-600 hover:underline"
            >
              {index + 1}. {segment.title || segment.videoId} — {ms(segment.start)} (
              {segment.text.slice(0, 80)}…)
            </a>
          </li>
        ))}
      </ul>
      <p className="text-xs text-emerald-900/70 mt-2">
        Note: YouTube URLs support a start time but not an enforced end time. The in-app
        player below will stop at each segment’s end and auto-advance.
      </p>
    </div>
  );
}

function Player({ segments, activeIndex, onAdvance }) {
  const ready = useYouTubeAPI();
  const containerRef = useRef(null);
  const playerRef = useRef(null);

  const segment = segments[activeIndex];

  useEffect(() => {
    if (!ready || !containerRef.current || playerRef.current || !segment?.videoId) {
      return;
    }

    playerRef.current = new window.YT.Player(containerRef.current, {
      height: "390",
      width: "690",
      videoId: segment.videoId,
      playerVars: {
        autoplay: 1,
        controls: 1,
        modestbranding: 1,
        rel: 0,
        start: Math.floor(segment.start)
      },
      events: {
        onReady: (event) => {
          event.target.seekTo(segment.start, true);
          event.target.playVideo();
        }
      }
    });
  }, [ready, segment]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !segment?.videoId) return;

    try {
      player.loadVideoById({ videoId: segment.videoId, startSeconds: segment.start });
    } catch (error) {
      console.warn("Failed to load segment", error);
    }
  }, [activeIndex, segment]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !segment?.videoId) return;

    const interval = setInterval(() => {
      try {
        const current = player.getCurrentTime ? player.getCurrentTime() : 0;
        const end = segment.end ?? segment.start + 6;
        if (current && current >= end - 0.05) {
          onAdvance?.();
        }
      } catch (error) {
        console.warn("Failed to poll time", error);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [activeIndex, segment, onAdvance]);

  return (
    <div>
      <div id="yt" ref={containerRef} className="rounded-xl overflow-hidden shadow-lg" />
      <div className="mt-2 text-sm">
        {segment ? (
          <>
            <div className="font-semibold">{segment.title}</div>
            <div className="text-emerald-900/80">{segment.channel}</div>
            <div className="mt-1 whitespace-pre-wrap">{segment.text}</div>
            <div className="text-xs text-emerald-900/70 mt-1">
              {ms(segment.start)} → {ms(segment.end)} · Clip {activeIndex + 1} of {segments.length}
            </div>
          </>
        ) : (
          <div>Enter text and compose a timeline.</div>
        )}
      </div>
    </div>
  );
}

function Timeline({ segments, activeIndex, setActiveIndex }) {
  if (!segments.length) return null;

  return (
    <ol className="divide-y divide-green-800/20 rounded-xl border border-green-800/20 overflow-hidden">
      {segments.map((segment, index) => (
        <li
          key={`${segment.videoId}-${segment.start}-${index}`}
          onClick={() => setActiveIndex(index)}
          className={`p-3 cursor-pointer transition-transform transform hover:scale-105 ${
            index === activeIndex ? "bg-emerald-700/20" : "hover:bg-emerald-700/10"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="font-medium truncate mr-2">{segment.title || segment.videoId}</div>
            <div className="text-xs text-emerald-900/80">
              {ms(segment.start)} → {ms(segment.end)}
            </div>
          </div>
          <div className="text-xs text-emerald-900/80 truncate">{segment.channel}</div>
          <div className="text-sm mt-1 line-clamp-2">{segment.text}</div>
        </li>
      ))}
    </ol>
  );
}

export default function App() {
  const [text, setText] = useState("");
  const [lang, setLang] = useState("en");
  const [loading, setLoading] = useState(false);
  const [segments, setSegments] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState("");
  const [generatingVideo, setGeneratingVideo] = useState(false);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState(null);
  const [maxPhraseLength, setMaxPhraseLength] = useState(10);

  async function compose() {
    setError("");
    const clauses = sentenceSplit(text);
    if (!clauses.length) return;

    setLoading(true);
    try {
      const out = [];
      for (const clause of clauses) {
        const query = clause.startsWith("\"") ? clause : `"${clause}"`;
        const hits = await searchExact(query.replace(/^\"|\"$/g, ""), lang);
        if (hits.length) {
          const topHit = hits[0];
          out.push({
            videoId: topHit.video_id,
            start: topHit.t_start,
            end: Math.max(topHit.t_end, topHit.t_start + 2),
            text: topHit.text,
            title: topHit.title,
            channel: topHit.channel_title
          });
        }
      }
      setSegments(out);
      setActiveIndex(0);
    } catch (error) {
      setError(String(error.message || error));
    } finally {
      setLoading(false);
    }
  }

  function advance() {
    setActiveIndex((current) => (current + 1 < segments.length ? current + 1 : current));
  }

  async function handleGenerateVideo() {
    setError("");
    setGeneratedVideoUrl(null);
    
    if (!text.trim()) {
      setError("Please enter some text first");
      return;
    }
    
    setGeneratingVideo(true);
    try {
      const result = await generateVideo(text, lang, maxPhraseLength);
      
      if (result.status === "success" && result.video_url) {
        setGeneratedVideoUrl(`${API}${result.video_url}`);
      } else if (result.status === "partial_failure") {
        setError(result.message || "Some words could not be found");
      } else {
        setError("Video generation failed");
      }
    } catch (error) {
      setError(String(error.message || error));
    } finally {
      setGeneratingVideo(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-2xl glass-card p-8">
        <h1 className="text-5xl font-bold mb-2 title-animation">ClipScribe</h1>
        <p className="text-lg mb-8 title-animation" style={{ animationDelay: '0.2s' }}>
          Paste text. We find exact-phrase caption hits and play them in sequence.
        </p>
        
        <div className="relative mb-4">
          <textarea
            className="w-full bg-transparent border-2 border-green-800/50 rounded-2xl py-4 px-6 text-lg transition-shadow duration-300 placeholder-green-900/60"
            placeholder='e.g. "how do you do". "nice to meet you". "see you soon".'
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows="3"
          />
          <div className="absolute right-5 bottom-5 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-sm">Lang</label>
              <input
                value={lang}
                onChange={(event) => setLang(event.target.value)}
                className="bg-white/40 border border-green-800/50 rounded-lg px-2 py-1 w-20"
              />
            </div>
            <button
              onClick={compose}
              disabled={loading || !text.trim()}
              className="bg-emerald-700 text-white px-6 py-2 rounded-full font-semibold shadow-lg hover:bg-emerald-800 disabled:opacity-50 transition-transform transform hover:scale-105"
            >
              {loading ? "Composing…" : "Compose"}
            </button>
            <button
              onClick={handleGenerateVideo}
              disabled={generatingVideo || !text.trim()}
              className="bg-purple-700 text-white px-6 py-2 rounded-full font-semibold shadow-lg hover:bg-purple-800 disabled:opacity-50 transition-transform transform hover:scale-105"
            >
              {generatingVideo ? "Generating…" : "Generate Video"}
            </button>
          </div>
        </div>

        <div className="mb-6 p-4 bg-white/40 rounded-xl border border-green-800/30">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-semibold text-emerald-900">
              Max Phrase Length: <span className="text-purple-700">{maxPhraseLength} word{maxPhraseLength !== 1 ? 's' : ''}</span>
            </label>
            <span className="text-xs text-emerald-900/70">
              {maxPhraseLength === 1 ? 'Individual words only' : 
               maxPhraseLength <= 5 ? 'Short phrases' : 
               maxPhraseLength <= 15 ? 'Medium phrases' : 
               'Long phrases'}
            </span>
          </div>
          <input
            type="range"
            min="1"
            max="50"
            value={maxPhraseLength}
            onChange={(e) => setMaxPhraseLength(parseInt(e.target.value))}
            className="w-full h-2 bg-emerald-200 rounded-lg appearance-none cursor-pointer accent-purple-700"
            style={{
              background: `linear-gradient(to right, #7c3aed 0%, #7c3aed ${((maxPhraseLength - 1) / 49) * 100}%, #d1fae5 ${((maxPhraseLength - 1) / 49) * 100}%, #d1fae5 100%)`
            }}
          />
          <div className="flex justify-between text-xs text-emerald-900/60 mt-1">
            <span>1</span>
            <span>25</span>
            <span>50</span>
          </div>
          <p className="text-xs text-emerald-900/70 mt-2">
            Higher values create smoother videos by matching longer consecutive word sequences from the same video clip.
          </p>
        </div>

        {error && <div className="text-red-600 text-sm mt-2 mb-4">{error}</div>}

        {generatedVideoUrl && (
          <div className="mt-6 p-4 bg-purple-100/50 rounded-xl">
            <h3 className="text-xl font-semibold mb-3 text-purple-900">Generated Video</h3>
            <video 
              controls 
              className="w-full rounded-lg shadow-lg"
              src={generatedVideoUrl}
            >
              Your browser does not support the video tag.
            </video>
            <div className="mt-3 flex gap-2">
              <a
                href={generatedVideoUrl}
                download
                className="inline-block bg-purple-700 text-white px-4 py-2 rounded-full font-semibold hover:bg-purple-800 transition"
              >
                Download Video
              </a>
            </div>
          </div>
        )}

        {segments.length > 0 && (
          <div className="w-full mt-8">
            <Player segments={segments} activeIndex={activeIndex} onAdvance={advance} />

            <div className="flex justify-center gap-4 mt-4">
              <button
                onClick={() => setActiveIndex((index) => Math.max(0, index - 1))}
                className="px-4 py-2 rounded-full border border-green-800/50 hover:bg-white/60 disabled:opacity-50"
                disabled={!segments.length || activeIndex === 0}
              >
                ◀ Prev
              </button>
              <button
                onClick={() => setActiveIndex((index) => Math.min(segments.length - 1, index + 1))}
                className="px-4 py-2 rounded-full border border-green-800/50 hover:bg-white/60 disabled:opacity-50"
                disabled={!segments.length || activeIndex >= segments.length - 1}
              >
                Next ▶
              </button>
            </div>

            <div className="mt-6">
              <h3 className="text-xl font-semibold mb-3">Timeline</h3>
              <Timeline segments={segments} activeIndex={activeIndex} setActiveIndex={setActiveIndex} />
            </div>

            <div className="mt-6">
               <PlaylistLinks segments={segments} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

