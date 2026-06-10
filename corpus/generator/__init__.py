"""EDI corpus generator package.

Defines the PartnerGenerator Protocol and GenerateResult type that partner
modules must implement. Partner modules import CanonicalOrder and friends
directly from corpus.generator.base; the ledger types from corpus.generator.ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from corpus.generator.base import CanonicalOrder
    from corpus.generator.ledger import DiscrepancyLedger


@dataclass
class GenerateResult:
    """Result of a corpus generation run for one trading partner."""
    partner: str
    documents: dict[str, list[str]]  # {"850": [...raw X12 strings...], "856": [...], ...}
    ledger: "DiscrepancyLedger"


@runtime_checkable
class PartnerGenerator(Protocol):
    """Interface that every partner module must implement (U2)."""

    def generate(self, orders: "list[CanonicalOrder]", seed: int) -> GenerateResult:
        """Generate synthetic X12 documents from canonical Cinderhaven orders.

        Args:
            orders: Canonical orders for this partner from read_partner_orders().
            seed:   RNG seed for reproducible corpus generation.

        Returns:
            GenerateResult with all six document types and a populated ledger.
        """
        ...
