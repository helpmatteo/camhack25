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

async function generateVideo(text, lang = "en", maxPhraseLength = 10, enhanceAudio = false, keepOriginalAudio = true) {
  const response = await fetch(`${API}/generate-video`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ 
      text, 
      lang, 
      max_phrase_length: maxPhraseLength,
      enhance_audio: enhanceAudio,
      keep_original_audio: keepOriginalAudio
    }),
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
    <ol className="divide-y divide-purple-200 rounded-xl border-2 border-purple-200 overflow-hidden bg-white/60 backdrop-blur-sm shadow-sm">
      {segments.map((segment, index) => (
        <li
          key={`${segment.videoId}-${segment.start}-${index}`}
          onClick={() => setActiveIndex(index)}
          className={`p-4 cursor-pointer transition-all duration-200 ${
            index === activeIndex 
              ? "bg-gradient-to-r from-purple-100 via-violet-100 to-fuchsia-100 border-l-4 border-fuchsia-500" 
              : "hover:bg-purple-50/80"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="font-semibold truncate mr-2 text-purple-900">{segment.title || segment.videoId}</div>
            <div className="text-xs font-medium text-purple-600 bg-purple-100 px-2 py-1 rounded-full">
              {ms(segment.start)} → {ms(segment.end)}
            </div>
          </div>
          <div className="text-xs text-purple-700/80 truncate mt-1">{segment.channel}</div>
          <div className="text-sm mt-2 line-clamp-2 text-gray-700">{segment.text}</div>
        </li>
      ))}
    </ol>
  );
}

export default function App() {
  const [text, setText] = useState("");
  const [segments, setSegments] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState("");
  const [generatingVideo, setGeneratingVideo] = useState(false);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState(null);
  const [originalVideoUrl, setOriginalVideoUrl] = useState(null);
  const [maxPhraseLength, setMaxPhraseLength] = useState(10);
  const [enhanceAudio, setEnhanceAudio] = useState(false);
  const [keepOriginalAudio, setKeepOriginalAudio] = useState(true);

  function advance() {
    setActiveIndex((current) => (current + 1 < segments.length ? current + 1 : current));
  }

  async function handleGenerateVideo() {
    setError("");
    setGeneratedVideoUrl(null);
    setOriginalVideoUrl(null);
    
    if (!text.trim()) {
      setError("Please enter some text first");
      return;
    }
    
    setGeneratingVideo(true);
    try {
      const result = await generateVideo(text, "en", maxPhraseLength, enhanceAudio, keepOriginalAudio);
      
      if (result.status === "success" && result.video_url) {
        setGeneratedVideoUrl(`${API}${result.video_url}`);
        if (result.original_video_url) {
          setOriginalVideoUrl(`${API}${result.original_video_url}`);
        }
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
    <div className="min-h-screen flex flex-col items-center justify-center p-4 sm:p-6 lg:p-8">
      <div className="w-full max-w-5xl">
        {/* Header */}
        <div className="text-center mb-6">
          <h1 className="text-6xl sm:text-7xl font-bold mb-3 bg-gradient-to-r from-violet-600 via-purple-600 to-fuchsia-600 bg-clip-text text-transparent drop-shadow-sm">
            ClipScribe
          </h1>
          <p className="text-lg sm:text-xl text-purple-700/80 font-medium">
            Generate videos from text using real YouTube clips
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-2xl p-6 sm:p-8 lg:p-10 border border-purple-200/30">
          {/* Text Input */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-purple-900 mb-2">
              Enter your text
            </label>
            <textarea
              className="w-full bg-white/60 border-2 border-purple-300/40 rounded-2xl py-4 px-6 text-lg transition-all duration-300 placeholder-purple-400/70 focus:border-purple-400 focus:ring-4 focus:ring-purple-200/50 focus:outline-none focus:bg-white/80 resize-none shadow-sm"
              placeholder="Type or paste your text here..."
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows="5"
            />
          </div>

          {/* Phrase Length Slider */}
          <div className="mb-6 p-5 bg-gradient-to-br from-purple-100/30 via-violet-100/30 to-fuchsia-100/30 rounded-2xl border border-purple-300/30 shadow-sm backdrop-blur-sm">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-purple-900">
                Phrase Length: <span className="text-fuchsia-600 font-bold">{maxPhraseLength}</span> word{maxPhraseLength !== 1 ? 's' : ''}
              </label>
              <span className="text-xs font-medium text-purple-600 bg-white/80 backdrop-blur-sm px-3 py-1.5 rounded-full shadow-sm border border-purple-200">
                {maxPhraseLength === 1 ? '🔤 Words only' : 
                 maxPhraseLength <= 5 ? '📝 Short' : 
                 maxPhraseLength <= 15 ? '📄 Medium' : 
                 '📖 Long'}
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="50"
              value={maxPhraseLength}
              onChange={(e) => setMaxPhraseLength(parseInt(e.target.value))}
              className="w-full h-3 bg-purple-200/50 rounded-full appearance-none cursor-pointer accent-fuchsia-600"
              style={{
                background: `linear-gradient(to right, #c026d3 0%, #c026d3 ${((maxPhraseLength - 1) / 49) * 100}%, #e9d5ff ${((maxPhraseLength - 1) / 49) * 100}%, #e9d5ff 100%)`
              }}
            />
            <div className="flex justify-between text-xs text-purple-500 font-medium mt-2">
              <span>1</span>
              <span>25</span>
              <span>50</span>
            </div>
                        <p className="text-xs text-purple-600/80 mt-3 flex items-center gap-1">
              <span>✨</span>
              <span>Longer phrases create smoother videos with fewer cuts</span>
            </p>
          </div>

          {/* Audio Enhancement Options */}
          <div className="mb-6 p-5 bg-gradient-to-br from-amber-100/30 via-orange-100/30 to-red-100/30 rounded-2xl border border-amber-300/30 shadow-sm backdrop-blur-sm">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-amber-900 flex items-center gap-2">
                <span>🎵</span>
                <span>Audio Enhancement (Auphonic)</span>
              </label>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={enhanceAudio}
                  onChange={(e) => setEnhanceAudio(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-amber-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
              </label>
            </div>
            
            {enhanceAudio && (
              <div className="mt-3 p-3 bg-white/50 rounded-lg border border-amber-200">
                <label className="flex items-center gap-2 text-sm text-amber-800">
                  <input
                    type="checkbox"
                    checked={keepOriginalAudio}
                    onChange={(e) => setKeepOriginalAudio(e.target.checked)}
                    className="w-4 h-4 text-amber-600 bg-gray-100 border-gray-300 rounded focus:ring-amber-500"
                  />
                  <span>Keep original audio for comparison</span>
                </label>
              </div>
            )}
            
            <p className="text-xs text-amber-600/80 mt-3 flex items-center gap-1">
              <span>🔊</span>
              <span>Applies noise reduction, volume leveling, and loudness normalization</span>
            </p>
            <p className="text-xs text-amber-500/70 mt-1 italic">
              Requires AUPHONIC_API_TOKEN environment variable
            </p>
          </div>

          {/* Generate Button */}
          <button
            onClick={handleGenerateVideo}
            disabled={generatingVideo || !text.trim()}
            className="w-full bg-gradient-to-r from-violet-600 via-purple-600 to-fuchsia-600 text-white px-8 py-4 rounded-2xl font-bold text-lg shadow-lg hover:shadow-2xl hover:from-violet-700 hover:via-purple-700 hover:to-fuchsia-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 transform hover:scale-[1.02] active:scale-[0.98]"
          >
            {generatingVideo ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Generating Video...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Generate Video
              </span>
            )}
          </button>

          {error && (
            <div className="mt-4 p-4 bg-red-50 border-2 border-red-300 rounded-2xl text-red-700 text-sm shadow-sm">
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <span className="font-semibold">Error:</span> {error}
                </div>
              </div>
            </div>
          )}

          {generatedVideoUrl && (
            <div className="mt-6 p-6 bg-gradient-to-br from-purple-100/30 via-violet-100/30 to-fuchsia-100/30 rounded-2xl border-2 border-purple-300/40 shadow-lg backdrop-blur-sm">
              <h3 className="text-xl font-bold mb-4 text-purple-900 flex items-center gap-2">
                <svg className="w-6 h-6 text-fuchsia-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {originalVideoUrl ? 'Your Videos are Ready - Compare Audio!' : 'Your Video is Ready!'}
              </h3>
              
              {originalVideoUrl ? (
                // Side-by-side comparison view
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Original Audio Video */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-center gap-2 py-2 px-4 bg-amber-200/50 rounded-lg border border-amber-300">
                      <svg className="w-5 h-5 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                      </svg>
                      <span className="font-semibold text-amber-800">Original Audio</span>
                    </div>
                    <video 
                      controls 
                      className="w-full rounded-xl shadow-xl border-2 border-amber-300/60"
                      src={originalVideoUrl}
                    >
                      Your browser does not support the video tag.
                    </video>
                    <a
                      href={originalVideoUrl}
                      download
                      className="inline-flex items-center gap-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white px-4 py-2 rounded-lg font-medium hover:from-amber-600 hover:to-orange-600 transition-all shadow-md hover:shadow-lg text-sm w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download Original
                    </a>
                  </div>

                  {/* Enhanced Audio Video */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-center gap-2 py-2 px-4 bg-emerald-200/50 rounded-lg border border-emerald-300">
                      <svg className="w-5 h-5 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                      </svg>
                      <span className="font-semibold text-emerald-800">Enhanced Audio ✨</span>
                    </div>
                    <video 
                      controls 
                      className="w-full rounded-xl shadow-xl border-2 border-emerald-300/60"
                      src={generatedVideoUrl}
                    >
                      Your browser does not support the video tag.
                    </video>
                    <a
                      href={generatedVideoUrl}
                      download
                      className="inline-flex items-center gap-2 bg-gradient-to-r from-emerald-500 to-green-500 text-white px-4 py-2 rounded-lg font-medium hover:from-emerald-600 hover:to-green-600 transition-all shadow-md hover:shadow-lg text-sm w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download Enhanced
                    </a>
                  </div>
                </div>
              ) : (
                // Single video view
                <div>
                  <video 
                    controls 
                    className="w-full rounded-xl shadow-xl border-2 border-white/80"
                    src={generatedVideoUrl}
                  >
                    Your browser does not support the video tag.
                  </video>
                  <div className="mt-4">
                    <a
                      href={generatedVideoUrl}
                      download
                      className="inline-flex items-center gap-2 bg-gradient-to-r from-violet-600 via-purple-600 to-fuchsia-600 text-white px-6 py-3 rounded-xl font-bold hover:from-violet-700 hover:via-purple-700 hover:to-fuchsia-700 transition-all shadow-md hover:shadow-xl transform hover:scale-105"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download Video
                    </a>
                  </div>
                </div>
              )}
              
              {originalVideoUrl && (
                <div className="mt-4 p-4 bg-white/50 rounded-lg border border-purple-200">
                  <p className="text-sm text-purple-700 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="font-medium">Tip:</span> Play both videos to hear the difference in audio quality!
                  </p>
                </div>
              )}
            </div>
          )}

          {segments.length > 0 && (
            <div className="mt-6">
              <div className="bg-gradient-to-br from-purple-100/30 via-violet-100/30 to-fuchsia-100/30 rounded-2xl p-6 border-2 border-purple-300/40 shadow-lg backdrop-blur-sm">
                <Player segments={segments} activeIndex={activeIndex} onAdvance={advance} />

                <div className="flex justify-center gap-3 mt-6">
                  <button
                    onClick={() => setActiveIndex((index) => Math.max(0, index - 1))}
                    className="px-6 py-2.5 rounded-xl bg-white/80 backdrop-blur-sm border-2 border-purple-200 hover:border-fuchsia-400 hover:bg-fuchsia-50 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-semibold text-purple-900 shadow-sm hover:shadow-md"
                    disabled={!segments.length || activeIndex === 0}
                  >
                    ← Previous
                  </button>
                  <button
                    onClick={() => setActiveIndex((index) => Math.min(segments.length - 1, index + 1))}
                    className="px-6 py-2.5 rounded-xl bg-white/80 backdrop-blur-sm border-2 border-purple-200 hover:border-fuchsia-400 hover:bg-fuchsia-50 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-semibold text-purple-900 shadow-sm hover:shadow-md"
                    disabled={!segments.length || activeIndex >= segments.length - 1}
                  >
                    Next →
                  </button>
                </div>

                <div className="mt-6">
                  <h3 className="text-lg font-bold mb-3 text-purple-900">Timeline</h3>
                  <Timeline segments={segments} activeIndex={activeIndex} setActiveIndex={setActiveIndex} />
                </div>

                <div className="mt-6">
                  <PlaylistLinks segments={segments} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

