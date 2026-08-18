const assert = require('assert');
const path = require('path');
const parseSse = require(path.join(__dirname, '../transforms/parse_sse.cjs'));

// Test 1: Normal SSE stream with results and summary_chunk events
const sampleSse = `event: results
data: {"results": [{"app_id": 10, "name": "Counter-Strike"}], "debug": {"detected_language": "en", "rewritten_query_en": "counter strike", "filters": {"operating_systems": ["windows"]}}}

event: summary_chunk
data: "Here is "

event: summary_chunk
data: "a summary of games."
`;

const parsed = parseSse(null, sampleSse);
assert.strictEqual(parsed.summary, "Here is a summary of games.");
assert.strictEqual(parsed.results.length, 1);
assert.strictEqual(parsed.results[0].app_id, 10);
assert.strictEqual(parsed.debug.detected_language, "en");
assert.strictEqual(parsed.debug.filters.operating_systems[0], "windows");

// Test 2: Error payload (e.g. 422 or 500 JSON)
const errorParsed = parseSse({ detail: "Invalid request" }, "");
assert.strictEqual(errorParsed.error, "Invalid request");
assert.strictEqual(errorParsed.summary, "");

// Test 3: SSE with JSON string chunks
const sseJsonChunks = `event: results
data: {"results": []}

event: summary_chunk
data: "Chunk 1 "

event: summary_chunk
data: "Chunk 2"
`;
const parsed3 = parseSse(null, sseJsonChunks);
assert.strictEqual(parsed3.summary, "Chunk 1 Chunk 2");
assert.strictEqual(parsed3.results.length, 0);

console.log("All parse_sse unit tests passed successfully!");
