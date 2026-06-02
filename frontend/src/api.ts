import type { AgentEvent, Landscape, LandscapeDiff, LandscapeSummary } from "./types";

export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchHealth(): Promise<any> {
  const r = await fetch(`${API_BASE}/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function listLandscapes(): Promise<LandscapeSummary[]> {
  const r = await fetch(`${API_BASE}/landscapes`);
  if (!r.ok) return [];
  return r.json();
}

export async function loadLandscape(id: string): Promise<Landscape> {
  const r = await fetch(`${API_BASE}/landscapes/${id}`);
  if (!r.ok) throw new Error(`load ${r.status}`);
  return (await r.json()).landscape as Landscape;
}

export async function diffLandscape(id: string): Promise<LandscapeDiff | null> {
  const r = await fetch(`${API_BASE}/landscapes/${id}/diff`);
  if (r.status === 404) return null; // no prior run of this query
  if (!r.ok) throw new Error(`diff ${r.status}`);
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

    // Split on a blank line; use the actual matched separator length (handles
    // \n\n, \r\n\r\n and mixed forms) instead of guessing it.
    const sep = /\r?\n\r?\n/;
    let m: RegExpExecArray | null;
    while ((m = sep.exec(buffer)) !== null) {
      const block = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
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
