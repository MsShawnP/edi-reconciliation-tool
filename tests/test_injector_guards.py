"""Tests for injector guards (finding #16 causes 4 and 5).

Cause 4: one-injection-per-document — a single 856/810 cannot receive
         two corruptions in the same pass.
Cause 5: per-PO removal — removing an 856 for a PO removes ALL 856s
         for that PO (fixes Walmart two-856 split).
"""
from corpus.generator.injector import (
    Injector,
    _build_po_to_doc_indices,
    _isa_ctrl,
    _po_from_856,
)
from corpus.generator import GenerateResult
from corpus.generator.ledger import DiscrepancyLedger


def _make_856(isa: int, po: str, sku: str = "CHP-AS-001", qty: int = 24) -> str:
    """Minimal 856 document for testing."""
    return (
        f"ISA*00*          *00*          *ZZ*CINDERHAVEN     *ZZ*WALMARTUS       *260610*1200*^*00501*{isa:09d}*0*T*:~\n"
        f"GS*SH*CINDERHAVEN*WALMARTUS*20260610*1200*1*X*005010~\n"
        f"ST*856*0001~\n"
        f"BSN*00*SHIP-001*20260610*1200~\n"
        f"HL*1**S~\n"
        f"HL*2*1*O~\n"
        f"PRF*{po}~\n"
        f"HL*3*2*I~\n"
        f"LIN*1*IN*{sku}~\n"
        f"SN1**{qty}*CA~\n"
        f"CTT*3~\n"
        f"SE*10*0001~\n"
        f"GE*1*1~\n"
        f"IEA*1*{isa:09d}~"
    )


def _make_810(isa: int, po: str, sku: str = "CHP-AS-001", qty: int = 288) -> str:
    """Minimal 810 document for testing."""
    return (
        f"ISA*00*          *00*          *ZZ*CINDERHAVEN     *ZZ*WALMARTUS       *260610*1200*^*00501*{isa:09d}*0*T*:~\n"
        f"GS*IN*CINDERHAVEN*WALMARTUS*20260610*1200*1*X*005010~\n"
        f"ST*810*0001~\n"
        f"BIG*20260610*INV-001**{po}~\n"
        f"IT1*1*{qty}*EA*3.9583**IN*{sku}~\n"
        f"TDS*{int(qty * 3.9583 * 100)}~\n"
        f"SE*5*0001~\n"
        f"GE*1*1~\n"
        f"IEA*1*{isa:09d}~"
    )


def _make_850(isa: int, po: str, sku: str = "CHP-AS-001", qty: int = 24) -> str:
    """Minimal 850 document for testing."""
    return (
        f"ISA*00*          *00*          *ZZ*WALMARTUS       *ZZ*CINDERHAVEN     *260610*1200*^*00501*{isa:09d}*0*T*:~\n"
        f"GS*PO*WALMARTUS*CINDERHAVEN*20260610*1200*1*X*005010~\n"
        f"ST*850*0001~\n"
        f"BEG*00*SA*{po}**20260610~\n"
        f"PO1*1*{qty}*CA*47.50**IN*{sku}~\n"
        f"CTT*1~\n"
        f"SE*4*0001~\n"
        f"GE*1*1~\n"
        f"IEA*1*{isa:09d}~"
    )


class TestBuildPoToDocIndices:
    def test_single_856_per_po(self):
        docs = [_make_856(1001, "PO-001"), _make_856(1002, "PO-002")]
        result = _build_po_to_doc_indices(docs, _po_from_856)
        assert result == {"PO-001": [0], "PO-002": [1]}

    def test_two_856s_per_po(self):
        docs = [
            _make_856(1001, "PO-001"),
            _make_856(1002, "PO-001"),
            _make_856(1003, "PO-002"),
        ]
        result = _build_po_to_doc_indices(docs, _po_from_856)
        assert result["PO-001"] == [0, 1]
        assert result["PO-002"] == [2]


class TestOneInjectionPerDocument:
    def test_856_not_double_injected(self):
        """A single 856 should not receive both SN1 bump AND LIN corruption."""
        ledger = DiscrepancyLedger()
        docs_856 = [_make_856(1001, "PO-001")]
        result = GenerateResult(
            partner="walmart",
            documents={
                "850": [_make_850(2001, "PO-001")],
                "856": docs_856,
                "810": [_make_810(3001, "PO-001")],
                "820": [], "997": [],
            },
            ledger=ledger,
        )
        # High rate to maximize chance of double injection
        injected = Injector().inject(result, rate=1.0, seed=42)

        isa_counts: dict[str, int] = {}
        for entry in injected.ledger.entries():
            if entry.doc_type == "856":
                isa = entry.isa_control_number
                isa_counts[isa] = isa_counts.get(isa, 0) + 1

        for isa, count in isa_counts.items():
            assert count <= 1, f"856 ISA {isa} was injected {count} times"


class TestPerPoRemoval:
    def test_both_856s_removed_for_walmart_split(self):
        """When ordered-not-asnd fires for a PO with two 856s, both are removed."""
        ledger = DiscrepancyLedger()
        result = GenerateResult(
            partner="walmart",
            documents={
                "850": [_make_850(2001, "PO-001")],
                "856": [
                    _make_856(1001, "PO-001", qty=14),
                    _make_856(1002, "PO-001", qty=10),
                ],
                "810": [_make_810(3001, "PO-001")],
                "820": [], "997": [],
            },
            ledger=ledger,
        )
        injected = Injector().inject(result, rate=1.0, seed=42)

        asnd_entries = [
            e for e in injected.ledger.entries()
            if e.discrepancy_class.value == "ordered-not-asnd"
        ]
        if asnd_entries:
            remaining_po_001 = [
                doc for doc in injected.documents["856"]
                if _po_from_856(doc) == "PO-001"
            ]
            assert len(remaining_po_001) == 0, (
                f"Expected 0 remaining 856s for PO-001, got {len(remaining_po_001)}"
            )
