"""Shared X12 formatting utilities for corpus generators."""
from __future__ import annotations

from datetime import date, timedelta


def x12_date_short(date_str: str) -> str:
    """YYYY-MM-DD → YYMMDD for ISA interchange date."""
    return date_str.replace("-", "")[2:]


def x12_date_long(date_str: str) -> str:
    """YYYY-MM-DD → YYYYMMDD for GS and body segment dates."""
    return date_str.replace("-", "")


def add_days(date_str: str, days: int) -> str:
    """Add N calendar days to YYYY-MM-DD; return YYYY-MM-DD."""
    return (date.fromisoformat(date_str) + timedelta(days=days)).isoformat()


def make_doc(
    sender: str,
    receiver: str,
    func_id: str,
    isa_ctrl: int,
    gs_ctrl: int,
    st_ctrl: int,
    trans_set: str,
    body_segs: list[str],
    date_str: str,
    time_str: str = "1200",
) -> str:
    """Assemble a complete single-transaction X12 interchange.

    body_segs: segments between ST and SE (do not include ST or SE).
    Returns all segments joined by newlines, each ending with ~.
    """
    s = f"{sender:<15}"[:15]
    r = f"{receiver:<15}"[:15]
    ds = x12_date_short(date_str)
    dl = x12_date_long(date_str)
    ctrl_str = f"{st_ctrl:04d}"
    seg_count = 2 + len(body_segs)  # ST + body + SE

    segs = [
        f"ISA*00*          *00*          *ZZ*{s}*ZZ*{r}*{ds}*{time_str}*^*00501*{isa_ctrl:09d}*0*T*:~",
        f"GS*{func_id}*{sender.strip()}*{receiver.strip()}*{dl}*{time_str}*{gs_ctrl}*X*005010~",
        f"ST*{trans_set}*{ctrl_str}~",
        *body_segs,
        f"SE*{seg_count}*{ctrl_str}~",
        f"GE*1*{gs_ctrl}~",
        f"IEA*1*{isa_ctrl:09d}~",
    ]
    return "\n".join(segs)


def get_isa_control(doc: str) -> str:
    """Return ISA13 (interchange control number) as a string, or '' if not found."""
    for seg in doc.split("\n"):
        if seg.startswith("ISA*"):
            fields = seg.rstrip("~").split("*")
            return fields[13] if len(fields) > 13 else ""
    return ""


def get_segment(doc: str, seg_id: str) -> list[str] | None:
    """Return the fields of the first matching segment, or None."""
    prefix = seg_id + "*"
    for seg in doc.split("\n"):
        if seg.startswith(prefix):
            return seg.rstrip("~").split("*")
    return None


def replace_segment(doc: str, seg_id: str, new_fields: list[str]) -> str:
    """Replace the first occurrence of seg_id with new_fields. Returns doc unchanged if not found."""
    prefix = seg_id + "*"
    lines = doc.split("\n")
    for i, seg in enumerate(lines):
        if seg.startswith(prefix):
            lines[i] = "*".join(new_fields) + "~"
            return "\n".join(lines)
    return doc


# SKU → case_pack_qty. Copied from seed_config.PRODUCT_LINES (FROZEN: cinderhaven-data-v2).
# Do not edit unless seed_config FROZEN block is updated.
CASE_PACK: dict[str, int] = {
    "CHP-AS-001": 12, "CHP-AS-002": 12, "CHP-AS-003": 24, "CHP-AS-004": 12,
    "CHP-AS-005": 12, "CHP-AS-006": 12, "CHP-AS-007": 12, "CHP-AS-008": 12,
    "CHP-AS-009": 12, "CHP-AS-010": 12,
    "CHP-PS-001": 12, "CHP-PS-002": 12, "CHP-PS-003": 12, "CHP-PS-004": 6,
    "CHP-PS-005": 24, "CHP-PS-006": 24, "CHP-PS-007": 24, "CHP-PS-008": 24,
    "CHP-PS-009": 12, "CHP-PS-010": 12,
    "CHP-SC-001": 12, "CHP-SC-002": 12, "CHP-SC-003": 12, "CHP-SC-004": 12,
    "CHP-SC-005": 12, "CHP-SC-006": 12, "CHP-SC-007": 12, "CHP-SC-008": 6,
    "CHP-SC-009": 12, "CHP-SC-010": 12,
    "CHP-DG-001": 12, "CHP-DG-002": 12, "CHP-DG-003": 24, "CHP-DG-004": 24,
    "CHP-DG-005": 12, "CHP-DG-006": 12, "CHP-DG-007": 12, "CHP-DG-008": 12,
    "CHP-DG-009": 12, "CHP-DG-010": 12,
    "CHP-SB-001": 24, "CHP-SB-002": 24, "CHP-SB-003": 12, "CHP-SB-004": 24,
    "CHP-SB-005": 24, "CHP-SB-006": 12, "CHP-SB-007": 24, "CHP-SB-008": 12,
    "CHP-SB-009": 24, "CHP-SB-010": 12,
}

_DEFAULT_CASE_PACK = 12
