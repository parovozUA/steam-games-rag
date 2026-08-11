import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

function createSseResponse(payload: {
  results: unknown[];
  summary: string;
  debug?: Record<string, unknown>;
}) {
  const encoder = new TextEncoder();
  const resultsData = JSON.stringify({ results: payload.results, debug: payload.debug });
  const summaryData = JSON.stringify(payload.summary);
  const streamContent = `event: results\ndata: ${resultsData}\n\nevent: summary_chunk\ndata: ${summaryData}\n\n`;

  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(streamContent));
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("App", () => {
  it("shows search results and diagnostics only when enabled", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const isDebug = Boolean(JSON.parse(String(init?.body || "{}")).debug);
      return createSseResponse({
        results: [
          {
            app_id: 10,
            name: "Orbit Together",
            about: "Space co-op",
            platforms: { windows: true, mac: false, linux: true },
            rating_percent: 90,
            reviews_count: 1000,
            developers: [],
            publishers: [],
            genres: ["Adventure"],
            categories: ["Co-op"],
            tags: ["Space"],
          },
        ],
        summary: "One match found.",
        debug: isDebug ? { detected_language: "en", timings: { total_ms: 10 } } : undefined,
      });
    });

    render(<App />);
    const input = screen.getByLabelText("Search games");
    await userEvent.type(input, "space");
    await waitFor(() => expect(screen.getByRole("button", { name: "Search" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Orbit Together")).toBeInTheDocument();
    const steamLink = screen.getByRole("link", { name: /Orbit Together/ });
    expect(steamLink).toHaveAttribute("href", "https://store.steampowered.com/app/10");
    expect(steamLink).toHaveAttribute("target", "_blank");
    expect(steamLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByLabelText("Search diagnostics")).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Show search diagnostics"));
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByLabelText("Search diagnostics")).toBeInTheDocument();
  });

  it("handles API search network error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    render(<App />);
    const input = screen.getByLabelText("Search games");
    await userEvent.type(input, "space");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("NETWORK_ERROR")).toBeInTheDocument();
  });
});
