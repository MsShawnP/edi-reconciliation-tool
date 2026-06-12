"""Discrepancy injector.

Takes a clean GenerateResult from a partner generator and applies the seven
discrepancy types at a configurable rate. Every injection is recorded to the
result's ledger so the matching engine can be validated against it.

Usage:
    result = WalmartGenerator().generate(orders, seed=42)
    result = Injector().inject(result, rate=0.15, seed=99)
"""
from __future__ import annotations

import random
from copy import deepcopy

from corpus.generator import GenerateResult
from corpus.generator.ledger import DiscrepancyClass, DiscrepancyEntry


class Injector:
    def inject(
        self,
        result: GenerateResult,
        rate: float = 0.15,
        seed: int = 0,
    ) -> GenerateResult:
        """Apply all seven discrepancy types to *result* at the given injection rate.

        Returns a new GenerateResult with modified document strings and a
        fully-populated ledger (original ledger entries are preserved).
        """
        rng = random.Random(seed)
        docs = {k: list(v) for k, v in result.documents.items()}
        ledger = result.ledger

        # Guard: track which documents have already been injected so no
        # single 856/810 receives two corruptions in the same pass.
        injected_isas: set[str] = set()

        # Build lookup tables needed across injection types
        po_price = _build_po_price_index(docs.get("850", []))
        po_to_856_idxs = _build_po_to_doc_indices(docs.get("856", []), _po_from_856)

        # 1. shipped-not-invoiced — increase SN1 qty in selected 856s
        docs["856"] = _inject_shipped_not_invoiced(
            docs.get("856", []), rng, rate, po_price, ledger, result.partner,
            injected_isas,
        )

        # 2. short-pay — reduce RMR amount in selected 820s
        docs["820"] = _inject_short_pay(
            docs.get("820", []), rng, rate, ledger, result.partner,
        )

        # 3. ordered-not-asnd — remove ALL 856s for a selected 850's PO
        docs["850"], docs["856"] = _inject_ordered_not_asnd(
            docs.get("850", []), docs.get("856", []),
            rng, rate, po_price, po_to_856_idxs, ledger, result.partner,
            injected_isas,
        )

        # 4. uom-mismatch — adjust Walmart IT1 eaches by a non-case-divisible delta
        if result.partner == "walmart":
            docs["810"] = _inject_uom_mismatch(
                docs.get("810", []), rng, rate, ledger, result.partner,
                injected_isas,
            )

        # 5. mapping-drift — replace a SKU in a 856 LIN segment with an unknown code
        docs["856"] = _inject_mapping_drift(
            docs.get("856", []), rng, rate, ledger, result.partner,
            injected_isas,
        )

        # 6. 852-discrepancy — reduce ZA sell-through quantity in selected 852s
        docs["852"] = _inject_852_discrepancy(
            docs.get("852", []), rng, rate, ledger, result.partner,
        )

        # 7. 997-missing-ack — drop selected 997 documents
        docs["997"] = _inject_997_missing_ack(
            docs.get("997", []), rng, rate, ledger, result.partner,
        )

        return GenerateResult(partner=result.partner, documents=docs, ledger=ledger)


# ---------------------------------------------------------------------------
# Injection helpers
# ---------------------------------------------------------------------------

def _inject_shipped_not_invoiced(
    docs: list[str], rng: random.Random, rate: float,
    po_price: dict[str, float], ledger, partner: str,
    injected_isas: set[str],
) -> list[str]:
    out = []
    for doc in docs:
        isa = _isa_ctrl(doc)
        if rng.random() < rate and isa not in injected_isas:
            po = _po_from_856(doc)
            unit_price = po_price.get(po, 100.0)
            doc, delta = _bump_sn1(doc, rng)
            if delta > 0:
                injected_isas.add(isa)
                ledger.record(DiscrepancyEntry(
                    partner=partner,
                    doc_type="856",
                    isa_control_number=isa,
                    field_path="SN1.quantity",
                    expected_value=str(_get_sn1_qty(doc) - delta),
                    actual_value=str(_get_sn1_qty(doc)),
                    discrepancy_class=DiscrepancyClass.SHIPPED_NOT_INVOICED,
                    dollar_impact=round(delta * unit_price, 2),
                ))
        out.append(doc)
    return out


def _inject_short_pay(
    docs: list[str], rng: random.Random, rate: float, ledger, partner: str,
) -> list[str]:
    out = []
    for doc in docs:
        if rng.random() < rate:
            doc, delta = _reduce_rmr(doc, rng)
            if delta > 0:
                ledger.record(DiscrepancyEntry(
                    partner=partner,
                    doc_type="820",
                    isa_control_number=_isa_ctrl(doc),
                    field_path="RMR.payment_amount",
                    expected_value=str(_rmr_amount(doc) + delta),
                    actual_value=str(_rmr_amount(doc)),
                    discrepancy_class=DiscrepancyClass.SHORT_PAY,
                    dollar_impact=round(delta, 2),
                ))
        out.append(doc)
    return out


def _inject_ordered_not_asnd(
    docs_850: list[str], docs_856: list[str],
    rng: random.Random, rate: float,
    po_price: dict[str, float],
    po_to_856_idxs: dict[str, list[int]],
    ledger, partner: str,
    injected_isas: set[str],
) -> tuple[list[str], list[str]]:
    removal_idxs: set[int] = set()
    for doc_850 in docs_850:
        if rng.random() < rate * 0.5:  # lower rate — removes whole documents
            po = _po_from_850(doc_850)
            if po not in po_to_856_idxs:
                continue
            idxs = po_to_856_idxs[po]
            # Skip if any of this PO's 856s were already injected
            if any(_isa_ctrl(docs_856[i]) in injected_isas for i in idxs if i not in removal_idxs):
                continue
            # Remove ALL 856s for this PO (fixes Walmart two-856 split)
            for idx in idxs:
                injected_isas.add(_isa_ctrl(docs_856[idx]))
                removal_idxs.add(idx)
            ordered_qty = _total_po1_qty(doc_850)
            unit_price = po_price.get(po, 100.0)
            ledger.record(DiscrepancyEntry(
                partner=partner,
                doc_type="850",
                isa_control_number=_isa_ctrl(doc_850),
                field_path="856.missing",
                expected_value=f"ASN for PO {po}",
                actual_value="none",
                discrepancy_class=DiscrepancyClass.ORDERED_NOT_ASND,
                dollar_impact=round(ordered_qty * unit_price, 2),
            ))
    new_856 = [doc for i, doc in enumerate(docs_856) if i not in removal_idxs]
    return docs_850, new_856


def _inject_uom_mismatch(
    docs: list[str], rng: random.Random, rate: float, ledger, partner: str,
    injected_isas: set[str],
) -> list[str]:
    """Add 1 extra each to an IT1 line so post-conversion qty diverges."""
    out = []
    for doc in docs:
        isa = _isa_ctrl(doc)
        if rng.random() < rate and isa not in injected_isas:
            doc, modified = _bump_it1_ea(doc)
            if modified:
                injected_isas.add(isa)
                ledger.record(DiscrepancyEntry(
                    partner=partner,
                    doc_type="810",
                    isa_control_number=isa,
                    field_path="IT1.quantity_ea",
                    expected_value="case-exact",
                    actual_value="off-by-1-each",
                    discrepancy_class=DiscrepancyClass.UOM_MISMATCH,
                    dollar_impact=0.0,
                ))
        out.append(doc)
    return out


def _inject_mapping_drift(
    docs: list[str], rng: random.Random, rate: float, ledger, partner: str,
    injected_isas: set[str],
) -> list[str]:
    out = []
    for doc in docs:
        isa = _isa_ctrl(doc)
        if rng.random() < rate * 0.5 and isa not in injected_isas:
            doc, replaced = _corrupt_lin_sku(doc)
            if replaced:
                injected_isas.add(isa)
                ledger.record(DiscrepancyEntry(
                    partner=partner,
                    doc_type="856",
                    isa_control_number=isa,
                    field_path="LIN.item_number",
                    expected_value="valid-sku",
                    actual_value="UNKNOWN-ITEM",
                    discrepancy_class=DiscrepancyClass.MAPPING_DRIFT,
                    dollar_impact=0.0,
                ))
        out.append(doc)
    return out


def _inject_852_discrepancy(
    docs: list[str], rng: random.Random, rate: float, ledger, partner: str,
) -> list[str]:
    out = []
    for doc in docs:
        if rng.random() < rate:
            doc, delta = _reduce_za(doc, rng)
            if delta > 0:
                ledger.record(DiscrepancyEntry(
                    partner=partner,
                    doc_type="852",
                    isa_control_number=_isa_ctrl(doc),
                    field_path="ZA.quantity_sold",
                    expected_value=str(_get_za_qty(doc) + delta),
                    actual_value=str(_get_za_qty(doc)),
                    discrepancy_class=DiscrepancyClass.DISCREPANCY_852,
                    dollar_impact=0.0,
                ))
        out.append(doc)
    return out


def _inject_997_missing_ack(
    docs: list[str], rng: random.Random, rate: float, ledger, partner: str,
) -> list[str]:
    out = []
    for doc in docs:
        if rng.random() < rate * 0.5:
            ledger.record(DiscrepancyEntry(
                partner=partner,
                doc_type="997",
                isa_control_number=_isa_ctrl(doc),
                field_path="997.missing",
                expected_value="ACK within 48h",
                actual_value="none",
                discrepancy_class=DiscrepancyClass.MISSING_ACK_997,
                dollar_impact=0.0,
            ))
            # Drop this 997 from the corpus
            continue
        out.append(doc)
    return out


# ---------------------------------------------------------------------------
# X12 string manipulation
# ---------------------------------------------------------------------------

def _isa_ctrl(doc: str) -> str:
    for seg in doc.split("\n"):
        if seg.startswith("ISA*"):
            f = seg.rstrip("~").split("*")
            return f[13] if len(f) > 13 else ""
    return ""


def _po_from_850(doc: str) -> str:
    for seg in doc.split("\n"):
        if seg.startswith("BEG*"):
            return seg.rstrip("~").split("*")[3]
    return ""


def _po_from_856(doc: str) -> str:
    for seg in doc.split("\n"):
        if seg.startswith("PRF*"):
            return seg.rstrip("~").split("*")[1]
    return ""


def _build_po_price_index(docs_850: list[str]) -> dict[str, float]:
    """po_number → unit_price of the first PO1 line."""
    index: dict[str, float] = {}
    for doc in docs_850:
        po = ""
        for seg in doc.split("\n"):
            if seg.startswith("BEG*"):
                po = seg.rstrip("~").split("*")[3]
            elif seg.startswith("PO1*") and po:
                f = seg.rstrip("~").split("*")
                try:
                    index[po] = float(f[4])
                except (IndexError, ValueError):
                    pass
    return index


def _build_po_to_doc_indices(docs: list[str], key_fn) -> dict[str, list[int]]:
    """Map key_fn(doc) → ALL indices in docs list for that key."""
    index: dict[str, list[int]] = {}
    for i, doc in enumerate(docs):
        k = key_fn(doc)
        if k:
            index.setdefault(k, []).append(i)
    return index


def _total_po1_qty(doc: str) -> int:
    total = 0
    for seg in doc.split("\n"):
        if seg.startswith("PO1*"):
            f = seg.rstrip("~").split("*")
            try:
                total += int(f[2])
            except (IndexError, ValueError):
                pass
    return total


def _bump_sn1(doc: str, rng: random.Random) -> tuple[str, int]:
    """Increase the first SN1 quantity by 1–5 cases. Returns (doc, delta)."""
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("SN1*"):
            f = seg.rstrip("~").split("*")
            try:
                orig = int(f[2])
                delta = rng.randint(1, max(1, orig // 5))
                f[2] = str(orig + delta)
                lines[i] = "*".join(f) + "~"
                return "\n".join(lines), delta
            except (IndexError, ValueError):
                pass
    return doc, 0


def _get_sn1_qty(doc: str) -> int:
    for seg in doc.split("\n"):
        if seg.startswith("SN1*"):
            f = seg.rstrip("~").split("*")
            try:
                return int(f[2])
            except (IndexError, ValueError):
                pass
    return 0


def _reduce_rmr(doc: str, rng: random.Random) -> tuple[str, float]:
    """Reduce the first RMR payment amount by up to 10% (max $500). Returns (doc, delta)."""
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("RMR*"):
            f = seg.rstrip("~").split("*")
            try:
                orig = float(f[4])
                cap = min(500.0, orig * 0.1)
                delta = round(rng.uniform(min(50.0, cap), cap), 2)
                new_amt = round(orig - delta, 2)
                f[4] = f"{new_amt:.2f}"
                lines[i] = "*".join(f) + "~"
                # Also update BPR amount
                doc2 = "\n".join(lines)
                doc2 = _update_bpr_amount(doc2, new_amt)
                return doc2, delta
            except (IndexError, ValueError):
                pass
    return doc, 0.0


def _update_bpr_amount(doc: str, new_amt: float) -> str:
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("BPR*"):
            f = seg.rstrip("~").split("*")
            if len(f) > 2:
                f[2] = f"{new_amt:.2f}"
                lines[i] = "*".join(f) + "~"
                break
    return "\n".join(lines)


def _rmr_amount(doc: str) -> float:
    for seg in doc.split("\n"):
        if seg.startswith("RMR*"):
            f = seg.rstrip("~").split("*")
            try:
                return float(f[4])
            except (IndexError, ValueError):
                pass
    return 0.0


def _bump_it1_ea(doc: str) -> tuple[str, bool]:
    """Add 1 to the first IT1 quantity (in eaches) to create UoM mismatch."""
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("IT1*"):
            f = seg.rstrip("~").split("*")
            try:
                orig = int(f[2])
                f[2] = str(orig + 1)
                lines[i] = "*".join(f) + "~"
                return "\n".join(lines), True
            except (IndexError, ValueError):
                pass
    return doc, False


def _corrupt_lin_sku(doc: str) -> tuple[str, bool]:
    """Replace the first LIN item number with an unknown SKU."""
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("LIN*"):
            f = seg.rstrip("~").split("*")
            if len(f) >= 3:
                f[3] = "UNKNOWN-ITEM"
                lines[i] = "*".join(f) + "~"
                return "\n".join(lines), True
    return doc, False


def _reduce_za(doc: str, rng: random.Random) -> tuple[str, int]:
    """Reduce first ZA sell-through quantity by 10–30%. Returns (doc, delta)."""
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith("ZA*"):
            f = seg.rstrip("~").split("*")
            try:
                orig = int(f[2])
                delta = max(1, int(orig * rng.uniform(0.10, 0.30)))
                f[2] = str(orig - delta)
                lines[i] = "*".join(f) + "~"
                return "\n".join(lines), delta
            except (IndexError, ValueError):
                pass
    return doc, 0


def _get_za_qty(doc: str) -> int:
    for seg in doc.split("\n"):
        if seg.startswith("ZA*"):
            f = seg.rstrip("~").split("*")
            try:
                return int(f[2])
            except (IndexError, ValueError):
                pass
    return 0
