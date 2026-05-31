from __future__ import annotations

import hashlib
import re

from sourceloop.domain.bom import BomLine

_STRIP_PATTERN = re.compile(r"[-/._\s]+")


def _normalize_mpn(mpn: str) -> str:
    """Uppercase + strip separators for matching. NOT for display."""
    return _STRIP_PATTERN.sub("", mpn).upper()


def _normalize_description(desc: str) -> str:
    """Lowercase, collapse whitespace, sort tokens."""
    tokens = sorted(desc.lower().split())
    return " ".join(tokens)


def build_part_key(mpn: str, manufacturer: str | None = None) -> str:
    """
    Build normalized_part_key from an MPN string directly (no BomLine).
    Used by WarmupService and other non-parsing callers.
    """
    if mpn and mpn.strip():
        return f"mpn:{_normalize_mpn(mpn.strip())}"
    return f"desc:{hashlib.sha1((manufacturer or 'unknown').encode()).hexdigest()[:16]}"


def derive(line: BomLine) -> str:
    """
    Derive normalized_part_key for a BomLine.

    Branded (MPN present): mpn:{NORMALIZED_MPN}
      - STM32F103C8T6, stm32f103c8t6, STM32F103-C8T6 → mpn:STM32F103C8T6
      - TODO(step-2): manufacturer disambiguation for genuinely colliding MPNs

    No MPN (commodity/custom): desc:{sha1(normalized_desc)[:16]}
      - Never hits Tier-A — desc: keys are Tier-B/C only
    """
    if line.mpn and line.mpn.strip():
        normalized = _normalize_mpn(line.mpn.strip())
        return f"mpn:{normalized}"

    # Fall back to description hash
    desc = line.raw_description or ""
    if not desc.strip():
        desc = line.raw_designator or f"line_{line.line_no}"
    normalized_desc = _normalize_description(desc)
    digest = hashlib.sha1(normalized_desc.encode()).hexdigest()[:16]
    return f"desc:{digest}"
