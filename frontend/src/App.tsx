import { useRef, useState } from "react";
import { streamQuery } from "./api";
import {
  buildCiteIndex,
  GuardBar,
  LandscapeTable,
  Narrative,
  PlanTrace,
  ToolTrace,
  type TraceEntry,
} from "./components";
import type { GuardReport, Landscape } from "./types";

const EXAMPLES = [
  "competitive landscape for oral GLP-1 agonists in obesity",
  "KRAS G12C inhibitors in non-small cell lung cancer",
  "BTK inhibitors and degraders in B-cell malignancies",
];

export function App() {
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState<string[]>([]);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [guard, setGuard] = useState<GuardReport | null>(null);
  const [landscape, setLandscape] = useState<Landscape | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function reset() {
    setPlan([]);
    setTrace([]);
    setGuard(null);
    setLandscape(null);
    setError(null);
    setStatus("");
  }

  async function run(q: string) {
    if (!q.trim() || running) return;
    reset();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      for await (const ev of streamQuery(q, ctrl.signal)) {
        switch (ev.type) {
          case "status":
            setStatus(ev.data.message);
            setTrace((t) => [...t, { kind: "status", text: ev.data.message }]);
            break;
          case "plan":
            setPlan(ev.data.plan || []);
            break;
          case "message":
            setTrace((t) => [...t, { kind: "message", text: ev.data.text }]);
            break;
          case "tool_call":
            setTrace((t) => [
              ...t,
              { kind: "tool_call", tool: ev.data.tool, args: ev.data.args, n: ev.data.call_index },
            ]);
            break;
          case "tool_result":
            setTrace((t) => [
              ...t,
              { kind: "tool_result", tool: ev.data.tool, summary: ev.data.summary, error: ev.data.error },
            ]);
            break;
          case "guard":
            setGuard(ev.data as GuardReport);
            break;
          case "landscape":
            setLandscape(ev.data.landscape as Landscape);
            break;
          case "error":
            setError(ev.data.message);
            break;
          case "done":
            setStatus("Done.");
            break;
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") setError(String(e?.message ?? e));
    } finally {
      setRunning(false);
    }
  }

  const idx = landscape ? buildCiteIndex(landscape) : {};

  return (
    <div className="app">
      <div className="header">
        <h1>
          <span className="logo">AssetScope</span>
        </h1>
        <span className="tagline">agentic competitive intelligence for biopharma · every claim cited</span>
      </div>

      <form
        className="searchbar"
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. competitive landscape for oral GLP-1 agonists in obesity"
          disabled={running}
        />
        <button type="submit" disabled={running || !query.trim()}>
          {running ? "Researching…" : "Run"}
        </button>
      </form>

      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => { setQuery(ex); run(ex); }} disabled={running}>
            {ex}
          </button>
        ))}
      </div>

      {running && (
        <div className="msg">
          <span className="spinner" />
          {status || "Working…"}
        </div>
      )}
      {error && <div className="error-box">⚠ {error}</div>}

      <PlanTrace plan={plan} />
      <ToolTrace entries={trace} />
      {guard && <GuardBar guard={guard} toolCalls={landscape?.tool_calls ?? 0} />}
      {landscape && landscape.assets.length > 0 && (
        <>
          <LandscapeTable landscape={landscape} idx={idx} />
          <Narrative landscape={landscape} idx={idx} />
        </>
      )}

      <div className="footer">
        AssetScope is a research tool. It is <strong>not medical, clinical, regulatory or
        financial advice</strong>. Verify every cited source before relying on it. Sources:
        ClinicalTrials.gov, Open Targets, ChEMBL (EMBL-EBI), PubMed. Licensed under GPL-3.0.
      </div>
    </div>
  );
}
