import { FormEvent, useEffect, useRef, useState } from "react";
import type { ApiError, Game, IndexStatus, SearchResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "";

function GameCard({ game }: { game: Game }) {
  const [imageFailed, setImageFailed] = useState(false);
  const platforms = Object.entries(game.platforms)
    .filter(([, supported]) => supported)
    .map(([name]) => (name === "mac" ? "macOS" : name[0].toUpperCase() + name.slice(1)));
  return (
    <article className="game-card">
      <div className="image-wrap">
        {game.header_image && !imageFailed ? (
          <img src={game.header_image} alt="" onError={() => setImageFailed(true)} />
        ) : (
          <div className="image-fallback" aria-label="No game image">◈</div>
        )}
      </div>
      <div className="game-body">
        <div className="game-heading">
          <h3>{game.name}</h3>
          <span>{game.release_date ?? "Release date unknown"}</span>
        </div>
        <div className="metrics">
          <strong>{game.rating_percent == null ? "No rating" : `${game.rating_percent.toFixed(1)}%`}</strong>
          <span>{game.reviews_count.toLocaleString()} reviews</span>
          <span>{platforms.join(" · ") || "Platforms unknown"}</span>
        </div>
        <p>{game.about || "No description available."}</p>
        <div className="chips">
          {[...game.genres, ...game.tags].slice(0, 7).map((tag) => <span key={tag}>{tag}</span>)}
        </div>
        {(game.developers.length > 0 || game.publishers.length > 0) && (
          <small>
            {game.developers.length > 0 && <>By {game.developers.join(", ")}</>}
            {game.publishers.length > 0 && <> · Published by {game.publishers.join(", ")}</>}
          </small>
        )}
      </div>
    </article>
  );
}

function Diagnostics({ value }: { value: Record<string, unknown> }) {
  const providers = (value.providers ?? {}) as Record<string, { provider: string; model: string }>;
  const timings = (value.timings ?? {}) as Record<string, number>;
  return (
    <section className="diagnostics" aria-label="Search diagnostics">
      <h2>Diagnostics</h2>
      <dl>
        <div><dt>Language</dt><dd>{String(value.detected_language ?? "—")}</dd></div>
        <div><dt>English query</dt><dd>{String(value.rewritten_query_en ?? "—")}</dd></div>
        <div><dt>Fallback</dt><dd>{value.fallback_activated ? "OpenAI active" : "No"}</dd></div>
        <div><dt>Gemini attempts</dt><dd>{String(value.gemini_attempts ?? 0)}</dd></div>
        {Object.entries(providers).map(([stage, provider]) => (
          <div key={stage}><dt>{stage}</dt><dd>{provider.provider} · {provider.model}</dd></div>
        ))}
        {Object.entries(timings).map(([stage, duration]) => (
          <div key={stage}><dt>{stage}</dt><dd>{duration} ms</dd></div>
        ))}
      </dl>
      <details><summary>Raw diagnostics</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>
    </section>
  );
}

export default function App() {
  const [query, setQuery] = useState("");
  const [debug, setDebug] = useState(false);
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<ApiError["error"] | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<{ id: number; controller: AbortController } | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/index/status`, { signal: controller.signal });
        if (response.ok && !stopped) setIndex(await response.json());
      } catch (caught) {
        if (!stopped && (caught as Error).name !== "AbortError") {
          setIndex({ state: "failed", processed: 0, failed_rows: 0, point_count: 0, elapsed_seconds: 0, message: "Backend is unreachable" });
        }
      }
    };
    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => { stopped = true; controller.abort(); window.clearInterval(timer); };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim() || loading) return;
    activeRequest.current?.controller.abort();
    const id = ++sequence.current;
    const controller = new AbortController();
    activeRequest.current = { id, controller };
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), debug }),
        signal: controller.signal,
      });
      const body = await response.json();
      if (activeRequest.current?.id !== id) return;
      if (!response.ok) throw body as ApiError;
      setResult(body as SearchResponse);
    } catch (caught) {
      if ((caught as Error).name === "AbortError" || activeRequest.current?.id !== id) return;
      const apiError = caught as ApiError;
      setError(apiError.error ?? { code: "NETWORK_ERROR", message: "Could not reach the search service." });
      setResult(null);
    } finally {
      if (activeRequest.current?.id === id) setLoading(false);
    }
  };

  const ready = index?.state === "ready";
  return (
    <main>
      <header className="hero">
        <div className="eyebrow">LOCAL HYBRID DISCOVERY</div>
        <h1>Find the game you mean.</h1>
        <p>Search Steam’s catalog naturally, in any language.</p>
        <form onSubmit={submit}>
          <input aria-label="Search games" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try: cooperative space survival for Linux…" />
          <button disabled={loading || !ready || !query.trim()}>{loading ? "Searching…" : "Search"}</button>
        </form>
        <label className="debug-toggle"><input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} /> Show search diagnostics</label>
      </header>

      {index && !ready && (
        <section className={`status ${index.state}`} role="status">
          <strong>{index.state === "failed" ? "Indexing needs attention" : "Preparing the game index"}</strong>
          <span>{index.message ?? `${index.processed.toLocaleString()} games processed`}</span>
          {index.state === "indexing" && <progress />}
        </section>
      )}
      {error && <section className="error-state" role="alert"><strong>{error.code}</strong><p>{error.message}</p>{error.request_id && <small>Request {error.request_id}</small>}</section>}
      {result && (
        <section className="results">
          <div className="summary"><span>AI SUMMARY</span><p>{result.summary}</p></div>
          {result.results.length === 0 ? <div className="empty">No games to show. Try broadening the filters.</div> : result.results.map((game) => <GameCard key={game.app_id} game={game} />)}
          {debug && result.debug && <Diagnostics value={result.debug} />}
        </section>
      )}
    </main>
  );
}
