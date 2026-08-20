import { FormEvent, useRef, useState } from "react";
import type { ApiError, Game } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "";

function GameCard({ game }: { game: Game }) {
  const [imageFailed, setImageFailed] = useState(false);
  const platforms = Object.entries(game.platforms)
    .filter(([, supported]) => supported)
    .map(([name]) => (name === "mac" ? "macOS" : name[0].toUpperCase() + name.slice(1)));
  return (
    <a
      className="game-link"
      href={`https://store.steampowered.com/app/${game.app_id}`}
      target="_blank"
      rel="noopener noreferrer"
    >
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
    </a>
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

type MarkdownBlock =
  | { type: "paragraph"; content: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] };

function renderInline(text: string) {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const rawLines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let currentBlock: MarkdownBlock | null = null;

  for (const rawLine of rawLines) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      currentBlock = null;
      continue;
    }

    const ulMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    const olMatch = trimmed.match(/^\d+[.)]\s+(.+)$/);

    if (ulMatch) {
      const lastBlock = blocks[blocks.length - 1];
      if (lastBlock && lastBlock.type === "ul") {
        lastBlock.items.push(ulMatch[1]);
        currentBlock = lastBlock;
      } else {
        currentBlock = { type: "ul", items: [ulMatch[1]] };
        blocks.push(currentBlock);
      }
    } else if (olMatch) {
      const lastBlock = blocks[blocks.length - 1];
      if (lastBlock && lastBlock.type === "ol") {
        lastBlock.items.push(olMatch[1]);
        currentBlock = lastBlock;
      } else {
        currentBlock = { type: "ol", items: [olMatch[1]] };
        blocks.push(currentBlock);
      }
    } else {
      if (currentBlock && currentBlock.type === "paragraph") {
        currentBlock.content += ` ${trimmed}`;
      } else if (currentBlock && (currentBlock.type === "ul" || currentBlock.type === "ol")) {
        currentBlock.items[currentBlock.items.length - 1] += ` ${trimmed}`;
      } else {
        currentBlock = { type: "paragraph", content: trimmed };
        blocks.push(currentBlock);
      }
    }
  }

  return blocks;
}

function formatRecommendation(raw: string) {
  const text = raw
    .replace(/^```(?:json)?\s*[\s\S]*?```\s*/i, "")
    .replace(/^```(?:json)?\s*\{[\s\S]*$/i, "")
    .trim();

  if (!text) return null;

  const blocks = parseMarkdownBlocks(text);
  return blocks.map((block, bIdx) => {
    if (block.type === "ul") {
      return (
        <ul key={bIdx}>
          {block.items.map((item, iIdx) => (
            <li key={iIdx}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    }
    if (block.type === "ol") {
      return (
        <ol key={bIdx}>
          {block.items.map((item, iIdx) => (
            <li key={iIdx}>{renderInline(item)}</li>
          ))}
        </ol>
      );
    }
    return <p key={bIdx}>{renderInline(block.content)}</p>;
  });
}

export default function App() {
  const [query, setQuery] = useState("");
  const [debug, setDebug] = useState(false);
  const [results, setResults] = useState<Game[]>([]);
  const [summary, setSummary] = useState("");
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<ApiError["error"] | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<{ id: number; controller: AbortController } | null>(null);
  const sequence = useRef(0);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim() || loading) return;
    activeRequest.current?.controller.abort();
    const id = ++sequence.current;
    const controller = new AbortController();
    activeRequest.current = { id, controller };

    setLoading(true);
    setError(null);
    setResults([]);
    setSummary("");
    setDiagnostics(null);
    setHasSearched(true);

    try {
      const response = await fetch(`${API_URL}/api/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), debug }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.json();
        throw body;
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("Stream not readable");

      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (activeRequest.current?.id !== id) return;

        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";

        for (const chunk of chunks) {
          if (!chunk.trim()) continue;

          let eventType = "message";
          let data = "";

          for (const line of chunk.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice("event: ".length).trim();
            } else if (line.startsWith("data: ")) {
              data = line.slice("data: ".length).trim();
            }
          }

          if (eventType === "results" && data) {
            const parsed = JSON.parse(data);
            setResults(parsed.results || []);
            setDiagnostics(parsed.debug || null);
          } else if (eventType === "summary_chunk" && data) {
            const parsedChunk = JSON.parse(data);
            setSummary(prev => prev + parsedChunk);
          }
        }
      }
    } catch (caught) {
      if ((caught as Error).name === "AbortError" || activeRequest.current?.id !== id) return;
      const apiError = caught as ApiError;
      setError(apiError.error ?? { code: "NETWORK_ERROR", message: "Could not reach the search service." });
      setHasSearched(false);
    } finally {
      if (activeRequest.current?.id === id) setLoading(false);
    }
  };

  return (
    <main>
      <header className="hero">
        <div className="eyebrow">SEMANTIC GAME DISCOVERY</div>
        <h2>Search Steam by meaning.</h2>
        <p>Search naturally across Steam’s catalog, in any language.</p>
        <form onSubmit={submit}>
          <input aria-label="Search games" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Open-world games with exploration and base building" />
          <button disabled={loading || !query.trim()}>{loading ? "Searching…" : "Search"}</button>
        </form>
        <label className="debug-toggle"><input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} /> Show search diagnostics</label>
      </header>

      {error && <section className="error-state" role="alert"><strong>{error.code}</strong><p>{error.message}</p>{error.request_id && <small>Request {error.request_id}</small>}</section>}
      {hasSearched && !error && (
        <section className="results">
          <div className="summary">
            <span>AI RECOMMENDATION</span>
            {summary ? (
              formatRecommendation(summary)
            ) : loading ? (
              <p className="thinking">Thinking...</p>
            ) : null}
          </div>
          {results.length === 0 && !loading ? <div className="empty">No games to show. Try broadening the filters.</div> : results.map((game) => <GameCard key={game.app_id} game={game} />)}
          {debug && diagnostics && <Diagnostics value={diagnostics} />}
        </section>
      )}
    </main>
  );
}
