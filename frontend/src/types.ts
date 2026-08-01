export type IndexStatus = {
  state: "waiting" | "indexing" | "ready" | "failed";
  processed: number;
  failed_rows: number;
  point_count: number;
  elapsed_seconds: number;
  message?: string;
};

export type Game = {
  app_id: number;
  name: string;
  release_date?: string;
  about: string;
  header_image?: string;
  platforms: { windows: boolean; mac: boolean; linux: boolean };
  rating_percent?: number;
  reviews_count: number;
  developers: string[];
  publishers: string[];
  genres: string[];
  categories: string[];
  tags: string[];
};

export type SearchResponse = {
  request_id: string;
  query: string;
  summary: string;
  results: Game[];
  debug?: Record<string, unknown>;
};

export type ApiError = { error: { code: string; message: string; request_id?: string } };
