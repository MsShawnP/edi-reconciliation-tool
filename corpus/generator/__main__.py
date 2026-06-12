"""CLI entry point: generate synthetic X12 corpus and load it into Postgres.

Usage (via Makefile or direct):
    python -m corpus.generator --output corpus/output --seed 42

Generates corpus for all three partners (Walmart, UNFI, KeHE), applies
the injector, writes X12 files and discrepancy_ledger.csv to --output,
and loads all documents into the edi_raw.* tables via corpus.loader.

DATABASE_URL must be set in the environment.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from corpus.generator.base import read_partner_orders, CorpusError, SUPPORTED_PARTNERS
from corpus.generator.injector import Injector
from corpus.loader import load_corpus


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic X12 corpus and load to Postgres."
    )
    parser.add_argument("--output", default="corpus/output",
                        help="Directory to write X12 files and ledger CSV (default: corpus/output)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for reproducible generation (default: 42)")
    parser.add_argument("--injection-rate", type=float, default=0.3,
                        help="Fraction of documents to inject discrepancies into (default: 0.3)")
    parser.add_argument("--no-load", action="store_true",
                        help="Write files only; skip Postgres load")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    from corpus.generator.ledger import DiscrepancyLedger

    all_entries = []
    total_docs: dict[str, int] = {}

    for partner in sorted(SUPPORTED_PARTNERS):
        print(f"  [{partner}] Reading canonical orders from Cinderhaven...", flush=True)
        try:
            orders = read_partner_orders(partner)
        except CorpusError as exc:
            print(f"  [{partner}] ERROR: {exc}", file=sys.stderr)
            return 1

        print(f"  [{partner}] Generating X12 corpus ({len(orders)} orders)...", flush=True)
        gen = _get_partner_generator(partner)
        result = gen.generate(orders, seed=args.seed)

        print(f"  [{partner}] Injecting discrepancies (rate={args.injection_rate})...", flush=True)
        result = Injector().inject(result, rate=args.injection_rate, seed=args.seed)

        # Write X12 files to disk
        partner_dir = output_dir / partner
        partner_dir.mkdir(exist_ok=True)
        for doc_type, docs in result.documents.items():
            for i, raw in enumerate(docs):
                (partner_dir / f"{doc_type}_{i:04d}.x12").write_text(raw, encoding="utf-8")

        # Accumulate ledger entries
        all_entries.extend(result.ledger.entries())

        # Track doc counts
        for doc_type, docs in result.documents.items():
            total_docs[doc_type] = total_docs.get(doc_type, 0) + len(docs)

        if not args.no_load:
            print(f"  [{partner}] Loading {sum(len(d) for d in result.documents.values())} documents into edi_raw...", flush=True)
            counts = load_corpus(result, truncate=(partner == sorted(SUPPORTED_PARTNERS)[0]))
            for dt, n in counts.items():
                print(f"    {dt}: {n} rows", flush=True)

    # Write combined ledger CSV
    combined_ledger = DiscrepancyLedger()
    for entry in all_entries:
        combined_ledger.record(entry)

    paths = combined_ledger.write(output_dir)
    print(f"\n  Ledger: {paths['csv']} ({len(all_entries)} entries)")
    print(f"  X12 files written to: {output_dir}/")
    print(f"  Document totals: { {k: v for k, v in sorted(total_docs.items())} }")

    return 0


if __name__ == "__main__":
    sys.exit(main())
