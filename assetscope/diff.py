"""Diff two competitive landscapes of the same query — the core CI job of
tracking change over time: which assets are new, which dropped out, and which
advanced (phase change, fresh readout, new sources).

Assets are matched across runs by a normalized name key, with a fallback to a
shared source id (so a renamed-but-same-source asset still lines up). The result
is JSON-serializable for the API and a future DiffView.
"""

from __future__ import annotations

import re

from assetscope.models import Asset, Landscape

_DELTA_FIELDS = ["company", "target", "mechanism", "indication", "phase", "latest_readout"]


def _akey(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _match(old_assets: list[Asset], new_assets: list[Asset]) -> tuple[list, set, set]:
    """Return (pairs, matched_old_idx, matched_new_idx). Match by name key first,
    then by any shared source id."""
    pairs: list[tuple[int, int]] = []
    matched_old: set[int] = set()
    matched_new: set[int] = set()

    old_by_name: dict[str, int] = {}
    for i, a in enumerate(old_assets):
        old_by_name.setdefault(_akey(a.asset_name), i)
    for j, na in enumerate(new_assets):
        i = old_by_name.get(_akey(na.asset_name))
        if i is not None and i not in matched_old:
            pairs.append((i, j))
            matched_old.add(i)
            matched_new.add(j)

    # Fallback: match leftovers by shared source id.
    for j, na in enumerate(new_assets):
        if j in matched_new:
            continue
        nsrc = set(na.source_ids)
        for i, oa in enumerate(old_assets):
            if i in matched_old:
                continue
            if nsrc & set(oa.source_ids):
                pairs.append((i, j))
                matched_old.add(i)
                matched_new.add(j)
                break
    return pairs, matched_old, matched_new


def diff_landscapes(old: Landscape, new: Landscape) -> dict:
    pairs, matched_old, matched_new = _match(old.assets, new.assets)

    added = [a.model_dump() for j, a in enumerate(new.assets) if j not in matched_new]
    removed = [a.model_dump() for i, a in enumerate(old.assets) if i not in matched_old]

    changed = []
    for i, j in pairs:
        oa, na = old.assets[i], new.assets[j]
        deltas = {}
        for f in _DELTA_FIELDS:
            ov, nv = (getattr(oa, f) or "").strip(), (getattr(na, f) or "").strip()
            if ov != nv:
                deltas[f] = {"old": ov, "new": nv}
        new_sources = sorted(set(na.source_ids) - set(oa.source_ids))
        if deltas or new_sources:
            changed.append({
                "asset_name": na.asset_name,
                "changes": deltas,
                "new_source_ids": new_sources,
            })

    return {
        "query": new.query,
        "added": added,
        "removed": removed,
        "changed": changed,
        "n_added": len(added),
        "n_removed": len(removed),
        "n_changed": len(changed),
        "unchanged": len(pairs) - len(changed),
    }
