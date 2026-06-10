"""Discrepancy ledger writer.

Records every injected discrepancy as a single row. The ledger is the
validation ground truth for the matching engine: given a generated corpus,
the engine must find every entry (100% recall, 0 false positives).

Output: CSV for domain expert review in Excel, Parquet for the validation script.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    _PYARROW_AVAILABLE = False


class DiscrepancyClass(str, Enum):
    SHIPPED_NOT_INVOICED = "shipped-not-invoiced"
    SHORT_PAY = "short-pay"
    ORDERED_NOT_ASND = "ordered-not-asnd"
    UOM_MISMATCH = "uom-mismatch"
    MAPPING_DRIFT = "mapping-drift"
    DISCREPANCY_852 = "852-discrepancy"
    MISSING_ACK_997 = "997-missing-ack"


LEDGER_COLUMNS = [
    "partner",
    "doc_type",
    "isa_control_number",
    "field_path",
    "expected_value",
    "actual_value",
    "discrepancy_class",
    "dollar_impact",
]


@dataclass
class DiscrepancyEntry:
    partner: str
    doc_type: str
    isa_control_number: str
    field_path: str
    expected_value: str
    actual_value: str
    discrepancy_class: DiscrepancyClass
    dollar_impact: float


class DiscrepancyLedger:
    """Accumulates injected discrepancies and writes them to CSV and Parquet."""

    def __init__(self) -> None:
        self._entries: list[DiscrepancyEntry] = []

    def record(self, entry: DiscrepancyEntry) -> None:
        """Add one discrepancy entry to the ledger."""
        self._entries.append(entry)

    def entries(self) -> list[DiscrepancyEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def write(self, output_dir: str | Path) -> dict[str, Path | None]:
        """Write ledger to CSV and Parquet in output_dir.

        Returns a dict with keys "csv" and "parquet" (Parquet is None when
        pyarrow is not installed).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        rows = [_to_row(e) for e in self._entries]

        csv_path = output_dir / "discrepancy_ledger.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        parquet_path: Path | None = None
        if _PYARROW_AVAILABLE:
            parquet_path = output_dir / "discrepancy_ledger.parquet"
            table = pa.table({col: [r[col] for r in rows] for col in LEDGER_COLUMNS})
            pq.write_table(table, parquet_path)

        return {"csv": csv_path, "parquet": parquet_path}


def _to_row(entry: DiscrepancyEntry) -> dict:
    return {
        "partner": entry.partner,
        "doc_type": entry.doc_type,
        "isa_control_number": entry.isa_control_number,
        "field_path": entry.field_path,
        "expected_value": entry.expected_value,
        "actual_value": entry.actual_value,
        "discrepancy_class": entry.discrepancy_class.value,
        "dollar_impact": entry.dollar_impact,
    }
