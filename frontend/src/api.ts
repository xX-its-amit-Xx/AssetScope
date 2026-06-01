import type { AgentEvent } from "./types";

export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchHealth(): Promise<any> {
  const r = await fetch(`${API_BASE}/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

/**
 * Stream the agent's events from POST /query/stream. EventSource only supports
 * GET, so we read the SSE body ourselves from the fetch ReadableStream and
 * parse `event:`/`data:` blocks delimited by a blank line.
 */
export async function* streamQuery(
  query: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const resp = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`stream failed: ${resp.status} ${resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    // Split on blank line (handles \n\n and \r\n\r\n).
    while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + (buffer[idx] === "\r" ? 4 : 2));
      const dataLines = block
        .split(/\r?\n/)
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim());
      if (dataLines.length === 0) continue;
      try {
        const ev = JSON.parse(dataLines.join("\n")) as AgentEvent;
        yield ev;
      } catch {
        // ignore keep-alive / malformed chunks
      }
    }
  }
}
