"""The reliability guard — AssetScope's "no source, no claim" enforcement step.

Before a landscape is finalized, the guard walks every narrative claim and every
asset row and checks that the source ids they cite actually resolve to evidence
in the :class:`CitationLedger`. Claims with no resolvable source are dropped (or
flagged ``unverified``, by policy); asset rows with no resolvable source are kept
but flagged ``verified=False``. The guard returns a :class:`GuardReport` with the
metrics the eval harness and UI consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from assetscope.guards.citation_ledger import CitationLedger
from assetscope.models import Claim, ClaimStatus, Landscape


@dataclass
class GuardReport:
    total_claims: int = 0
    supported_claims: int = 0
    unverified_claims: int = 0
    dropped_claims: int = 0
    total_assets: int = 0
    flagged_assets: int = 0
    pruned_source_refs: int = 0  # individual claim->source refs that didn't resolve
    notes: list[str] = field(default_factory=list)

    @property
    def citation_coverage(self) -> float:
        """Fraction of ALL submitted claims that ended up grounded by >= 1 valid
        source. Dropped claims count against coverage (so dropping half a
        landscape shows ~50%, not a misleading 100%)."""
        denom = self.total_claims
        return (self.supported_claims / denom) if denom else 1.0


class ReliabilityGuard:
    def __init__(self, drop_unsupported: bool = True) -> None:
        # If True, claims with zero resolvable sources are removed from the
        # narrative (DROPPED). If False, they are kept but flagged UNVERIFIED.
        self.drop_unsupported = drop_unsupported

    def apply(self, landscape: Landscape, ledger: CitationLedger) -> tuple[Landscape, GuardReport]:
        report = GuardReport(total_claims=len(landscape.claims), total_assets=len(landscape.assets))

        kept_claims: list[Claim] = []
        for claim in landscape.claims:
            ok, missing = ledger.resolve(claim.source_ids)
            report.pruned_source_refs += len(missing)
            if ok:
                for cid in ok:
                    ledger.note_reference(cid, claim.id)
                kept_claims.append(
                    Claim(
                        id=claim.id,
                        text=claim.text,
                        source_ids=ok,
                        status=ClaimStatus.SUPPORTED,
                        guard_note=(
                            f"pruned {len(missing)} unresolved source id(s): {missing}"
                            if missing
                            else ""
                        ),
                    )
                )
                report.supported_claims += 1
            else:
                # No resolvable source for this claim.
                if self.drop_unsupported:
                    report.dropped_claims += 1
                    report.notes.append(f"DROPPED unsupported claim: {claim.text[:120]}")
                    # not appended to kept_claims
                else:
                    report.unverified_claims += 1
                    kept_claims.append(
                        Claim(
                            id=claim.id,
                            text=claim.text,
                            source_ids=[],
                            status=ClaimStatus.UNVERIFIED,
                            guard_note="no resolvable source in the citation ledger",
                        )
                    )
                    report.notes.append(f"FLAGGED unverified claim: {claim.text[:120]}")

        # Asset rows: keep, but flag any whose sources don't resolve.
        cleaned_assets = []
        for idx, asset in enumerate(landscape.assets):
            ok, missing = ledger.resolve(asset.source_ids)
            for cid in ok:
                # Key by index so two rows sharing a name don't collide.
                ledger.note_reference(cid, f"asset:{idx}:{asset.asset_name}")
            verified = bool(ok)
            if not verified:
                report.flagged_assets += 1
            asset_copy = asset.model_copy(
                update={
                    "source_ids": ok,
                    "unresolved_source_ids": missing,
                    "verified": verified,
                }
            )
            cleaned_assets.append(asset_copy)

        # Final citation set = exactly the sources actually used by survivors.
        used_ids: set[str] = set()
        for c in kept_claims:
            used_ids.update(c.source_ids)
        for a in cleaned_assets:
            used_ids.update(a.source_ids)
        citations = [ledger.get(cid) for cid in used_ids if ledger.get(cid)]

        narrative = self._render_narrative(kept_claims)

        cleaned = landscape.model_copy(
            update={
                "claims": kept_claims,
                "assets": cleaned_assets,
                "citations": citations,
                "narrative": narrative or landscape.narrative,
                "dropped_claims": report.dropped_claims,
                "unverified_claims": report.unverified_claims,
            }
        )
        return cleaned, report

    @staticmethod
    def _render_narrative(claims: list[Claim]) -> str:
        parts = []
        for c in claims:
            if c.status == ClaimStatus.UNVERIFIED:
                parts.append(f"{c.text} _[unverified — no source]_")
            else:
                marks = " ".join(f"[{cid}]" for cid in c.source_ids)
                parts.append(f"{c.text} {marks}".strip())
        return " ".join(parts)
