/**
 * Reusable SSE Transform for Promptfoo HTTP Provider.
 * Parses the Steam Games RAG SSE stream format:
 *   event: results -> data: {"results": [...], "debug": {...}}
 *   event: summary_chunk -> data: "token string"
 *
 * Normalizes output to:
 * {
 *   summary: string,
 *   results: Array<GameResult>,
 *   debug: object | null,
 *   raw_events: Array<{ event: string, data: any }>
 * }
 */
function parseSse(json, text) {
  // If promptfoo already parsed an error object or JSON response
  if (json && typeof json === 'object' && (json.detail || json.error)) {
    return {
      summary: '',
      results: [],
      debug: null,
      error: json.detail || json.error,
      raw: text || JSON.stringify(json),
    };
  }

  const rawText = typeof text === 'string' && text.trim().length > 0
    ? text
    : (typeof json === 'string' ? json : JSON.stringify(json || ''));

  const lines = rawText.split(/\r?\n/);
  let currentEvent = 'message';
  const summaryChunks = [];
  let results = [];
  let debug = null;
  const rawEvents = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('event:')) {
      currentEvent = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      const dataStr = line.slice('data:'.length).trim();
      if (!dataStr) continue;

      let parsedData = dataStr;
      try {
        parsedData = JSON.parse(dataStr);
      } catch {
        parsedData = dataStr;
      }

      rawEvents.push({ event: currentEvent, data: parsedData });

      if (currentEvent === 'results') {
        if (parsedData && typeof parsedData === 'object') {
          if (Array.isArray(parsedData.results)) {
            results = parsedData.results;
          }
          if (parsedData.debug !== undefined) {
            debug = parsedData.debug;
          }
        }
      } else if (currentEvent === 'summary_chunk') {
        if (typeof parsedData === 'string') {
          summaryChunks.push(parsedData);
        } else if (parsedData && typeof parsedData.text === 'string') {
          summaryChunks.push(parsedData.text);
        } else if (parsedData !== null && parsedData !== undefined) {
          summaryChunks.push(String(parsedData));
        }
      } else if (parsedData && typeof parsedData === 'object' && Array.isArray(parsedData.results)) {
        // Fallback for results if event name was omitted
        results = parsedData.results;
        if (parsedData.debug !== undefined) {
          debug = parsedData.debug;
        }
      }
    } else if (line.trim() === '') {
      currentEvent = 'message';
    }
  }

  const summary = summaryChunks.join('');

  return {
    summary,
    results,
    debug,
    raw_events: rawEvents,
  };
}

module.exports = parseSse;
