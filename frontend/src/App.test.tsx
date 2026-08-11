import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("shows ready search results and diagnostics only when enabled", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).includes("index/status")) return new Response(JSON.stringify({ state: "ready", processed: 3, failed_rows: 0, point_count: 3, elapsed_seconds: 1 }), { status: 200 });
      return new Response(JSON.stringify({ request_id: "r", query: "space", summary: "One match.", results: [{ app_id: 10, name: "Orbit Together", about: "Space co-op", platforms: { windows: true, mac: false, linux: true }, rating_percent: 90, reviews_count: 1000, developers: [], publishers: [], genres: ["Adventure"], categories: ["Co-op"], tags: ["Space"] }], debug: JSON.parse(String(init?.body)).debug ? { detected_language: "en", timings: { total_ms: 10 } } : undefined }), { status: 200 });
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

  it("renders a typed indexing failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ state: "failed", processed: 0, failed_rows: 0, point_count: 0, elapsed_seconds: 0, message: "CSV not found" }), { status: 200 }));
    render(<App />);
    expect(await screen.findByText("Indexing needs attention")).toBeInTheDocument();
    expect(screen.getByText("CSV not found")).toBeInTheDocument();
  });
});
