import type { Asset, Citation, Claim, GuardReport, Landscape } from "./types";

type CiteIndex = Record<string, Citation>;

export function buildCiteIndex(landscape: Landscape): CiteIndex {
  const idx: CiteIndex = {};
  for (const c of landscape.citations) idx[c.id] = c;
  return idx;
}

export function CiteChips({ ids, idx }: { ids: string[]; idx: CiteIndex }) {
  if (!ids?.length) return <span className="cite" style={{ color: "var(--muted)" }}>—</span>;
  return (
    <span className="cites">
      {ids.map((id) => {
        const c = idx[id];
        const cls = c ? c.source_type : "";
        const label = id.replace(/^OT:/, "");
        return c?.url ? (
          <a
            key={id}
            className={`cite ${cls}`}
            href={c.url}
            target="_blank"
            rel="noreferrer"
            title={c.title || id}
          >
            {label}
          </a>
        ) : (
          <span key={id} className="cite" title="unresolved">{label}</span>
        );
      })}
    </span>
  );
}

export function PlanTrace({ plan }: { plan: string[] }) {
  if (!plan?.length) return null;
  return (
    <div className="section plan">
      <h2>Plan</h2>
      <div className="card">
        <ol>
          {plan.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export interface TraceEntry {
  kind: "tool_call" | "tool_result" | "message" | "status";
  tool?: string;
  args?: Record<string, any>;
  summary?: string;
  error?: string | null;
  text?: string;
  n?: number;
}

export function ToolTrace({ entries }: { entries: TraceEntry[] }) {
  if (!entries.length) return null;
  return (
    <div className="section">
      <h2>Agent trace</h2>
      <div className="trace">
        {entries.map((e, i) => {
          if (e.kind === "message")
            return <div className="msg" key={i}>💭 {e.text}</div>;
          if (e.kind === "status")
            return <div className="msg" key={i}>• {e.text}</div>;
          if (e.kind === "tool_call")
            return (
              <div className="trace-item" key={i}>
                <span className="badge-n">#{e.n}</span>
                <span className="tool">{e.tool}</span>
                <span className="args">{JSON.stringify(e.args)}</span>
              </div>
            );
          // tool_result
          return (
            <div className={`trace-item ${e.error ? "err" : ""}`} key={i}>
              <span className="tool">↳ {e.tool}</span>
              <span className="summary">{e.error ? `error: ${e.error}` : e.summary}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function pct(x: number) {
  return `${(100 * x).toFixed(0)}%`;
}

export function GuardBar({ guard, toolCalls }: { guard: GuardReport; toolCalls: number }) {
  const covClass = guard.citation_coverage >= 0.99 ? "good" : "warn";
  const halClass = guard.dropped_claims + guard.unverified_claims === 0 ? "good" : "warn";
  return (
    <div className="section">
      <h2>Reliability guard</h2>
      <div className="card guard">
        <div className="metric">
          <span className={`v ${covClass}`}>{pct(guard.citation_coverage)}</span>
          <span className="k">citation coverage</span>
        </div>
        <div className="metric">
          <span className="v">{guard.supported_claims}</span>
          <span className="k">supported claims</span>
        </div>
        <div className="metric">
          <span className={`v ${halClass}`}>{guard.dropped_claims}</span>
          <span className="k">claims dropped</span>
        </div>
        <div className="metric">
          <span className="v">{guard.flagged_assets}</span>
          <span className="k">assets flagged</span>
        </div>
        <div className="metric">
          <span className="v">{toolCalls}</span>
          <span className="k">tool calls</span>
        </div>
      </div>
    </div>
  );
}

export function LandscapeTable({ landscape, idx }: { landscape: Landscape; idx: CiteIndex }) {
  const cols = ["Asset", "Company", "Target", "Mechanism", "Indication", "Phase", "Latest readout", "Sources"];
  return (
    <div className="section">
      <h2>Competitive landscape ({landscape.assets.length} assets)</h2>
      <div className="table-wrap">
        <table className="landscape">
          <thead>
            <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {landscape.assets.map((a: Asset, i) => (
              <tr key={i} className={a.verified ? "" : "unverified-row"}>
                <td className="asset">
                  {a.asset_name}
                  {!a.verified && <span className="flag">unverified</span>}
                </td>
                <td>{a.company}</td>
                <td>{a.target}</td>
                <td>{a.mechanism}</td>
                <td>{a.indication}</td>
                <td>{a.phase}</td>
                <td>{a.latest_readout}</td>
                <td><CiteChips ids={a.source_ids} idx={idx} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Narrative({ landscape, idx }: { landscape: Landscape; idx: CiteIndex }) {
  if (!landscape.claims?.length) return null;
  return (
    <div className="section narrative">
      <h2>Narrative summary</h2>
      <div className="card">
        {landscape.claims.map((c: Claim) => (
          <p key={c.id}>
            {c.status === "unverified" ? (
              <span className="unverified">{c.text} (unverified — no source)</span>
            ) : (
              <>
                {c.text} <CiteChips ids={c.source_ids} idx={idx} />
              </>
            )}
          </p>
        ))}
        {landscape.limitations && (
          <div className="limitations">
            <strong>Limitations:</strong> {landscape.limitations}
          </div>
        )}
      </div>
    </div>
  );
}
