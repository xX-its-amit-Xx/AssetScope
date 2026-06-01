import type { Citation, Landscape } from "./types";

function download(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50) || "landscape";
}

function citeIndex(ls: Landscape): Record<string, Citation> {
  return Object.fromEntries(ls.citations.map((c): [string, Citation] => [c.id, c]));
}

const COLS = ["Asset", "Company", "Target", "Mechanism", "Indication", "Phase", "Latest readout", "Verified", "Source IDs", "Source URLs"];

function rowsFor(ls: Landscape): string[][] {
  const idx = citeIndex(ls);
  return ls.assets.map((a) => [
    a.asset_name, a.company, a.target, a.mechanism, a.indication, a.phase, a.latest_readout,
    a.verified ? "yes" : "no",
    a.source_ids.join("; "),
    a.source_ids.map((id) => idx[id]?.url || id).join("; "),
  ]);
}

export function exportCSV(ls: Landscape) {
  const cell = (s: string) => `"${(s ?? "").replace(/"/g, '""')}"`;
  const body = [COLS, ...rowsFor(ls)].map((r) => r.map(cell).join(",")).join("\r\n");
  download(`assetscope-${slug(ls.query)}.csv`, body, "text/csv");
}

export function exportMarkdown(ls: Landscape) {
  const idx = citeIndex(ls);
  const cite = (ids: string[]) =>
    ids.map((id) => (idx[id]?.url ? `[${id}](${idx[id].url})` : id)).join(" ") || "—";
  const lines: string[] = [];
  lines.push(`# AssetScope — competitive landscape`);
  lines.push("");
  lines.push(`**Query:** ${ls.query}`);
  lines.push(`**Generated:** ${new Date().toISOString()}  ·  tool calls: ${ls.tool_calls}  ·  dropped claims: ${ls.dropped_claims}`);
  lines.push("");
  lines.push("| Asset | Company | Target | Mechanism | Indication | Phase | Latest readout | Sources |");
  lines.push("|---|---|---|---|---|---|---|---|");
  for (const a of ls.assets) {
    const md = (s: string) => (s || "").replace(/\|/g, "\\|").replace(/\n/g, " ");
    lines.push(
      `| ${md(a.asset_name)}${a.verified ? "" : " ⚠️unverified"} | ${md(a.company)} | ${md(a.target)} | ${md(a.mechanism)} | ${md(a.indication)} | ${md(a.phase)} | ${md(a.latest_readout)} | ${cite(a.source_ids)} |`,
    );
  }
  lines.push("");
  lines.push("## Narrative");
  for (const c of ls.claims) {
    lines.push(`- ${c.text} ${cite(c.source_ids)}`);
  }
  if (ls.limitations) {
    lines.push("");
    lines.push(`> **Limitations:** ${ls.limitations}`);
  }
  lines.push("");
  lines.push("---");
  lines.push("_AssetScope is a research tool — not medical, clinical, regulatory, or financial advice. Verify every cited source._");
  download(`assetscope-${slug(ls.query)}.md`, lines.join("\n"), "text/markdown");
}
