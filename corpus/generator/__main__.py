"""CLI entry point: generate synthetic X12 corpus and load it into Postgres.

Usage (via Makefile or direct):
    python -m corpus.generator --output corpus/output --seed 42

Generates corpus for all three partners (Walmart, UNFI, KeHE), applies
the injector, and loads documents into edi_raw.* tables in order-chunks
so the Python process never holds more than --chunk-size orders in memory
at once.

DATABASE_URL must be set in the environment.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from corpus.generator.base import read_partner_orders, CorpusError, SUPPORTED_PARTNERS
from corpus.generator.injector import Injector
from corpus.loader import (
    _connect, _ensure_schema, _ensure_tables, _truncate_tables,
    _insert_rows, _TABLES, _EXPANDERS,
)
from parser.x12_parser import parse_document
from parser.models import X12ParseError


def _get_partner_generator(partner: str):
    if partner == "walmart":
        from corpus.generator.partners.walmart import WalmartGenerator
        return WalmartGenerator()
    if partner == "unfi":
        from corpus.generator.partners.unfi import UnfiGenerator
        return UnfiGenerator()
    if partner == "kehe":
        from corpus.generator.partners.kehe import KeheGenerator
        return KeheGenerator()
    raise ValueError(f"Unknown partner: {partner}")


def _stream_load(result, conn, truncate: bool) -> dict[str, int]:
    """Parse one doc-type at a time, write all rows via execute_values (one round trip)."""
    loaded_at = datetime.now(tz=timezone.utc)
    row_counts: dict[str, int] = {k: 0 for k in _TABLES}

    with conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            _ensure_tables(cur)
            if truncate:
                _truncate_tables(cur)

            for doc_type, raw_docs in result.documents.items():
                if doc_type not in _EXPANDERS:
                    continue
                expected_cls, expander = _EXPANDERS[doc_type]
                rows: list = []

                for raw in raw_docs:
                    try:
                        parsed = parse_document(raw)
                    except X12ParseError as exc:
                        print(f"    WARN {doc_type}: {exc}", flush=True)
                        continue
                    if not isinstance(parsed, expected_cls):
                        continue
                    rows.extend(expander(parsed, loaded_at))

                if rows:
                    _insert_rows(cur, _TABLES[doc_type], rows)
                    row_counts[doc_type] = len(rows)
                    print(f"    {doc_type}: {row_counts[doc_type]} rows", flush=True)

    return row_counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic X12 corpus and load to Postgres."
    )
    parser.add_argument("--output", default="corpus/output",
                        help="Directory for ledger CSV (default: corpus/output)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed (default: 42)")
    parser.add_argument("--injection-rate", type=float, default=0.3,
                        help="Discrepancy injection rate (default: 0.3)")
    parser.add_argument("--no-load", action="store_true",
                        help="Skip Postgres load (ledger CSV only)")
    parser.add_argument("--partners", default=",".join(sorted(SUPPORTED_PARTNERS)),
                        help="Comma-separated partners to run (default: all)")
    parser.add_argument("--chunk-size", type=int, default=200,
                        help="Orders per generation+load chunk (default: 200)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    from corpus.generator.ledger import DiscrepancyLedger

    partners = [p.strip() for p in args.partners.split(",")]
    all_entries = []
    total_rows: dict[str, int] = {}
    first_chunk = True  # controls truncate — only on the very first DB write

    for partner in partners:
        print(f"\n[{partner}] Reading canonical orders...", flush=True)
        try:
            all_orders = read_partner_orders(partner)
        except CorpusError as exc:
            print(f"[{partner}] ERROR: {exc}", file=sys.stderr)
            return 1

        gen = _get_partner_generator(partner)
        injector = Injector()
        chunks = [
            all_orders[i:i + args.chunk_size]
            for i in range(0, len(all_orders), args.chunk_size)
        ]
        print(f"[{partner}] {len(all_orders)} orders -> {len(chunks)} chunks of <={args.chunk_size}", flush=True)

        for chunk_idx, orders in enumerate(chunks):
            result = gen.generate(orders, seed=args.seed + chunk_idx)
            result = injector.inject(result, rate=args.injection_rate, seed=args.seed + chunk_idx)
            all_entries.extend(result.ledger.entries())

            if args.no_load:
                continue

            doc_total = sum(len(d) for d in result.documents.values())
            print(f"  chunk {chunk_idx+1}/{len(chunks)}: {len(orders)} orders, {doc_total} docs", flush=True)

            for attempt in range(3):
                try:
                    conn = _connect()
                    counts = _stream_load(result, conn, truncate=first_chunk)
                    conn.close()
                    first_chunk = False
                    for dt, n in counts.items():
                        total_rows[dt] = total_rows.get(dt, 0) + n
                    break
                except Exception as exc:
                    if attempt == 2:
                        print(f"  chunk {chunk_idx+1} FAILED: {exc}", file=sys.stderr)
                        return 1
                    print(f"  chunk {chunk_idx+1} retry {attempt+1}/3: {exc}", flush=True)
                    time.sleep(5)

        print(f"[{partner}] Done.", flush=True)

    combined_ledger = DiscrepancyLedger()
    for entry in all_entries:
        combined_ledger.record(entry)
    paths = combined_ledger.write(output_dir)

    print(f"\nLedger: {paths['csv']} ({len(all_entries)} entries)")
    if total_rows:
        print(f"DB totals: { {k: v for k, v in sorted(total_rows.items()) if v} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
